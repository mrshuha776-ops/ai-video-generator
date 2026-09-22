#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Video Generator — Colab Video Engine (render_script.py)
==========================================================
Consumes a project_config.json (produced by app.py) and renders the
final MP4 using 100% free tools:

  * edge-tts       -> voiceover + word-level timing (for subtitles)
  * Pollinations   -> AI images (flux model, free, no key)
  * Pexels API     -> stock video clips (free key)
  * Pixabay API    -> free background music (free key)
  * FFmpeg         -> Ken Burns motion, burn-in word-by-word subtitles,
                      sidechain auto-ducking, concat, mux

Run in Google Colab:
    !pip install edge-tts requests
    # (ffmpeg is pre-installed on Colab)
    !python render_script.py --config project_config.json --pexels-key XXX
    #  --pixabay-key YYY --out /content/drive/MyDrive/AI_Videos/out.mp4
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

try:
    import edge_tts
except Exception:
    edge_tts = None


# ============================================================================
# Utilities
# ============================================================================
def log(msg: str):
    print(f"[render] {msg}", flush=True)


def run(cmd, **kw):
    """Run a shell command, raise on error."""
    log(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if res.returncode != 0:
        log("STDERR:\n" + res.stderr[-3000:])
        raise RuntimeError(f"Command failed: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return res


def ffprobe_duration(path: str) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def has_nvenc() -> bool:
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                             capture_output=True, text=True).stdout
        return "h264_nvenc" in enc
    except Exception:
        return False


def _available_encoders() -> set:
    try:
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                             capture_output=True, text=True).stdout
        return {line.split()[1] for line in enc.splitlines()
                if line.strip().startswith("V")}
    except Exception:
        return set()


_ENC_CACHE = None


def video_encoder(preset="medium", crf=20):
    """Auto-detect the best available H.264 encoder.

    Priority: h264_nvenc (GPU) > libx264 (Colab default) > libopenh264 > h264_vaapi.
    This makes the tool work across ffmpeg builds that disable libx264.
    """
    global _ENC_CACHE
    if _ENC_CACHE is None:
        _ENC_CACHE = _available_encoders()
    encs = _ENC_CACHE

    def opts(name, *args):
        return ["-c:v", name, *args, "-pix_fmt", "yuv420p"]

    if "h264_nvenc" in encs and has_nvenc():
        log("Encoder: h264_nvenc (GPU)")
        return opts("h264_nvenc", "-preset", "p4", "-rc", "vbr", "-b:v", "6M")
    if "libx264" in encs:
        log("Encoder: libx264")
        return opts("libx264", "-preset", preset, "-crf", str(crf))
    if "libopenh264" in encs:
        log("Encoder: libopenh264 (libx264 not available)")
        return opts("libopenh264", "-b:v", "6M")
    if "h264_vaapi" in encs:
        log("Encoder: h264_vaapi")
        return opts("h264_vaapi", "-b:v", "6M")
    # last resort: try the generic name (experimental native)
    log("Encoder: h264 (fallback, experimental)")
    return ["-c:v", "h264", "-strict", "experimental", "-pix_fmt", "yuv420p"]


AUDIO_ENC = ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]


# ============================================================================
# edge-tts: voiceover + word boundaries
# ============================================================================
async def synth_voice(text: str, voice: str, audio_path: str, words_path: str):
    """Synthesize with edge-tts; return list of {text,start,end} (seconds).

    edge-tts 7.x defaults to SentenceBoundary; we force WordBoundary so we get
    per-word timing for the TikTok-style subtitle highlight.
    """
    if edge_tts is None:
        raise RuntimeError("edge-tts not installed (pip install edge-tts)")
    try:
        communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    except TypeError:
        # older edge-tts (<7) used WordBoundary by default with no kwarg
        communicate = edge_tts.Communicate(text, voice)
    words = []
    audio_data = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            # offset/duration are in 100-nanosecond units
            start = chunk["offset"] / 1e7
            dur = chunk["duration"] / 1e7
            words.append({"text": chunk["text"], "start": start, "end": start + dur})
    with open(audio_path, "wb") as f:
        f.write(bytes(audio_data))
    json.dump(words, open(words_path, "w"), ensure_ascii=False)
    return words


def normalize_words(words, audio_path):
    """Rescale word timings to match the real audio duration (robust)."""
    if not words:
        return words
    dur = ffprobe_duration(audio_path)
    if dur <= 0:
        return words
    max_end = max(w["end"] for w in words)
    if max_end <= 0:
        # units were probably ms -> convert
        for w in words:
            w["start"] /= 1e3
            w["end"] /= 1e3
        max_end = max(w["end"] for w in words)
    # if word span is way off the audio, rescale linearly
    if not (0.85 * dur <= max_end <= 1.15 * dur) and max_end > 0:
        factor = dur / max_end
        for w in words:
            w["start"] *= factor
            w["end"] *= factor
    return words


# ============================================================================
# Visuals
# ============================================================================
def fetch_pollinations_image(prompt: str, w: int, h: int, out_path: str,
                             seed: int = 42) -> str:
    """Free AI image via Pollinations (flux model, no key, no logo)."""
    url = ("https://image.pollinations.ai/prompt/"
           f"{requests.utils.quote(prompt)}?width={w}&height={h}"
           f"&seed={seed}&nologo=true&model=flux")
    log(f"Pollinations image -> {prompt[:50]}")
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)
    return out_path


def fetch_pexels_video(query: str, api_key: str, orientation: str,
                       out_path: str) -> str:
    """Free stock video via Pexels API."""
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY required for stock_video scenes")
    url = "https://api.pexels.com/videos/search"
    r = requests.get(url, params={"query": query, "per_page": 15,
                                   "orientation": orientation},
                     headers={"Authorization": api_key}, timeout=30)
    r.raise_for_status()
    vids = r.json().get("videos", [])
    if not vids:
        raise RuntimeError(f"No Pexels videos for: {query}")
    # pick best mp4 file (prefer ~720p landscape or 1080 portrait)
    best = None
    for v in vids:
        for f in v.get("video_files", []):
            if f.get("file_type") == "video/mp4":
                best = f
                if 700 <= f.get("width", 0) <= 1400:
                    best = f
                    break
        if best:
            break
    if not best:
        raise RuntimeError(f"No downloadable mp4 in Pexels results for: {query}")
    link = best["link"]
    log(f"Pexels video -> {link}")
    rr = requests.get(link, timeout=120, stream=True)
    rr.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in rr.iter_content(8192):
            f.write(chunk)
    return out_path


# ============================================================================
# Background music (Pixabay free, fallback to silence)
# ============================================================================
def fetch_pixabay_music(query: str, api_key: str, out_path: str) -> str:
    if not api_key:
        raise RuntimeError("PIXABAY_API_KEY required for background music")
    url = "https://pixabay.com/api/music/"
    r = requests.get(url, params={"key": api_key, "q": query, "per_page": 5},
                      timeout=30)
    r.raise_for_status()
    hits = r.json().get("hits", [])
    if not hits:
        raise RuntimeError(f"No Pixabay music for: {query}")
    link = hits[0].get("audio", "")
    if link.startswith("//"):
        link = "https:" + link
    log(f"Pixabay music -> {link}")
    rr = requests.get(link, timeout=120, stream=True)
    rr.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in rr.iter_content(8192):
            f.write(chunk)
    return out_path


def make_silence(duration: float, out_path: str) -> str:
    """Generate a silent audio track (fallback when no music).

    Uses WAV/pcm so it is valid on every ffmpeg build (no external encoder
    dependency, no container/codec extension mismatch).
    """
    run(["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"anullsrc=channel_layout=stereo:sample_rate=44100",
         "-t", f"{duration:.3f}", "-c:a", "pcm_s16le", out_path])
    return out_path


# ============================================================================
# Ken Burns / scene video builder
# ============================================================================
def ken_burns_vf(scene_index: int, fps: int, frames: int, w: int, h: int) -> str:
    """Return a zoompan video filter chain with alternating motion."""
    base = int(w * 1.5), int(h * 1.5)
    bw, bh = base
    variant = scene_index % 4
    if variant == 0:   # slow zoom-in, centered
        z = "min(zoom+0.0008,1.28)"
        x = "iw/2-(iw/zoom/2)"; y = "ih/2-(ih/zoom/2)"
    elif variant == 1:  # slow zoom-out, centered
        z = "if(lte(on,0),1.28,max(1.0,zoom-0.0008))"
        x = "iw/2-(iw/zoom/2)"; y = "ih/2-(ih/zoom/2)"
    elif variant == 2:  # zoom-in with rightward drift
        z = "min(zoom+0.0009,1.25)"
        x = "if(lte(on,0),iw/2-(iw/zoom/2),min(iw-iw/zoom, (iw/2-(iw/zoom/2))+on*0.6))"
        y = "ih/2-(ih/zoom/2)"
    else:               # zoom-in with downward drift
        z = "min(zoom+0.0009,1.25)"
        x = "iw/2-(iw/zoom/2)"
        y = "if(lte(on,0),ih/2-(ih/zoom/2),min(ih-ih/zoom, (ih/2-(ih/zoom/2))+on*0.5))"
    return (
        f"scale={bw}:{bh}:force_original_aspect_ratio=increase,"
        f"crop={bw}:{bh},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},"
        f"format=yuv420p"
    )


def build_image_scene(image_path, audio_path, dur, fps, w, h, idx, out_path):
    frames = max(1, int(round(dur * fps)))
    vf = ken_burns_vf(idx, fps, frames, w, h)
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", image_path, "-i", audio_path,
           "-t", f"{dur:.3f}", "-vf", vf, "-r", str(fps),
           *video_encoder(), *AUDIO_ENC, "-shortest", out_path]
    run(cmd)


def build_stock_scene(video_path, audio_path, dur, fps, w, h, out_path):
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
          f"crop={w}:{h},fps={fps},format=yuv420p")
    cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", video_path,
           "-i", audio_path, "-t", f"{dur:.3f}", "-vf", vf,
           "-r", str(fps), *video_encoder(), *AUDIO_ENC, "-shortest", out_path]
    run(cmd)


# ============================================================================
# Word-by-word ASS subtitles (TikTok style)
# ============================================================================
def ass_time(sec: float) -> str:
    if sec < 0:
        sec = 0
    cs = int(round(sec * 100))
    h = cs // 360000
    m = (cs % 360000) // 6000
    s = (cs % 6000) // 100
    c = cs % 100
    return f"{h:d}:{m:02d}:{s:02d}.{c:02d}"


def write_ass(flat_words, w, h, out_path):
    """Write an ASS file with TikTok-style word highlighting.

    flat_words: list of {text, start, end} with GLOBAL timestamps (seconds).
    """
    fontsize = max(28, int(h * 0.046))
    margin_v = int(h * 0.10)
    outline = max(3, int(h * 0.004))
    shadow = max(1, int(h * 0.0015))
    yellow = "&H0000FFFF&"   # BGR -> yellow
    white = "&H00FFFFFF&"

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: {w}\nPlayResY: {h}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default, DejaVu Sans, {fs}, {pc}, &H000000FF, &H00000000, "
        "&H64000000, 1, 0, 0, 0, 100, 100, 0, 0, 1, {ol}, {sh}, 2, 60, 60, "
        "{mv}, 1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    ).format(w=w, h=h, fs=fontsize, pc=white, ol=outline, sh=shadow, mv=margin_v)

    # group words into lines (~28 chars or sentence end)
    lines = []
    cur = []
    cur_len = 0
    max_chars = 30
    for w_ in flat_words:
        txt = w_["text"]
        cur.append(w_)
        cur_len += len(txt) + 1
        ends_sentence = bool(re.search(r"[.!?…\"']\s*$", txt))
        if cur_len >= max_chars or ends_sentence:
            lines.append(cur)
            cur = []
            cur_len = 0
    if cur:
        lines.append(cur)

    events = []
    for line in lines:
        if not line:
            continue
        line_start = line[0]["start"]
        line_end = line[-1]["end"]
        for i, wd in enumerate(line):
            start = wd["start"]
            # end = next word start, or line end for last word
            if i + 1 < len(line):
                end = line[i + 1]["start"]
            else:
                end = max(line_end, start + 0.15)
            # build text: full line, active word highlighted
            parts = []
            for j, ww in enumerate(line):
                if j == i:
                    parts.append(r"{\c" + yellow + r"}" + ww["text"] +
                                 r"{\c" + white + r"}")
                else:
                    parts.append(ww["text"])
            text = " ".join(parts)
            events.append(
                f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}\n"
            )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.writelines(events)
    return out_path


# ============================================================================
# Final assembly: concat + subtitles + ducked music
# ============================================================================
def concat_scenes(scene_paths, out_path):
    list_file = out_path + ".list.txt"
    with open(list_file, "w") as f:
        for p in scene_paths:
            p_abs = os.path.abspath(p).replace("'", "'\\''")
            f.write(f"file '{p_abs}'\n")
    # identical encoding per scene -> concat demuxer with -c copy
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
           "-c", "copy", out_path]
    try:
        run(cmd)
    except Exception:
        # fallback: re-encode
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
             *video_encoder(), *AUDIO_ENC, out_path])
    return out_path


def render_final(concat_path, ass_path, music_path, out_path,
                 music_vol=0.35, subs_enabled=True, music_enabled=True):
    """Burn subtitles + mix ducked background music."""
    dur = ffprobe_duration(concat_path)

    if music_enabled and music_path and os.path.exists(music_path) \
            and ffprobe_duration(music_path) > 0:
        # sidechain ducking: music is compressed by the narration (voiceover)
        vfilter = f"[0:v]ass={ass_path}[v]" if subs_enabled else "[0:v]copy[v]"
        fg = (
            vfilter + ";" +
            f"[1:a]atrim=duration={dur:.3f},volume={music_vol}[mv];"
            "[mv][0:a]sidechaincompress=threshold=0.05:ratio=6:"
            "attack=20:release=400[ducked];"
            "[0:a][ducked]amix=inputs=2:duration=first:"
            "dropout_transition=0:weights=1 0.7[a]"
        )
        cmd = ["ffmpeg", "-y", "-i", concat_path, "-i", music_path,
               "-filter_complex", fg,
               "-map", "[v]", "-map", "[a]",
               *video_encoder(), *AUDIO_ENC,
               "-movflags", "+faststart", out_path]
    else:
        # no music: just burn subtitles (or copy) and keep narration
        if subs_enabled:
            cmd = ["ffmpeg", "-y", "-i", concat_path, "-i", ass_path,
                   "-filter_complex", f"[0:v]ass={ass_path}[v]",
                   "-map", "[v]", "-map", "0:a",
                   *video_encoder(), *AUDIO_ENC,
                   "-movflags", "+faststart", out_path]
        else:
            cmd = ["ffmpeg", "-y", "-i", concat_path,
                   *video_encoder(), *AUDIO_ENC,
                   "-movflags", "+faststart", out_path]
    run(cmd)
    return out_path


# ============================================================================
# Main pipeline
# ============================================================================
def render(config_path, out_path, pexels_key, pixabay_key, work_dir=None):
    work_dir = work_dir or tempfile.mkdtemp(prefix="aivideo_")
    os.makedirs(work_dir, exist_ok=True)
    log(f"Work dir: {work_dir}")

    cfg = json.load(open(config_path, encoding="utf-8"))
    w = cfg["resolution"]["width"]
    h = cfg["resolution"]["height"]
    fps = cfg.get("fps", 30)
    voice = cfg["voice"]
    lang = cfg.get("language", "en")
    fmt = cfg.get("format", "short")
    orientation = "portrait" if fmt == "short" else "landscape"
    subs_enabled = cfg.get("subtitles", {}).get("enabled", True)
    music_cfg = cfg.get("music", {})
    music_enabled = music_cfg.get("enabled", True)
    music_vol = music_cfg.get("volume", 0.35)
    music_query = music_cfg.get("query", "cinematic")

    scenes = cfg["scenes"]
    log(f"Rendering {len(scenes)} scenes @ {w}x{h} {fps}fps (voice={voice})")

    scene_paths = []
    all_words = []           # global word timings
    offset = 0.0            # cumulative scene start

    for i, sc in enumerate(scenes):
        log(f"--- Scene {i+1}/{len(scenes)} ---")
        audio_path = os.path.join(work_dir, f"s{i:02d}.mp3")
        words_path = os.path.join(work_dir, f"s{i:02d}.words.json")

        # 1. voiceover
        asyncio.run(synth_voice(sc["narration"], voice, audio_path, words_path))
        words = json.load(open(words_path))
        words = normalize_words(words, audio_path)
        audio_dur = ffprobe_duration(audio_path)
        if audio_dur <= 0:
            audio_dur = float(sc.get("duration", 5))
        # use the REAL audio duration for the video length
        scene_dur = audio_dur

        # 2. visual
        vtype = sc.get("visual_type", "ai_image")
        if vtype == "ai_image":
            vpath = os.path.join(work_dir, f"s{i:02d}.img.jpg")
            fetch_pollinations_image(sc["visual_prompt"], w, h, vpath, seed=42 + i)
            scene_path = os.path.join(work_dir, f"s{i:02d}.mp4")
            build_image_scene(vpath, audio_path, scene_dur, fps, w, h, i, scene_path)
        else:
            vpath = os.path.join(work_dir, f"s{i:02d}.stock.mp4")
            fetch_pexels_video(sc["visual_prompt"], pexels_key, orientation, vpath)
            scene_path = os.path.join(work_dir, f"s{i:02d}.mp4")
            build_stock_scene(vpath, audio_path, scene_dur, fps, w, h, scene_path)

        scene_paths.append(scene_path)

        # 3. accumulate global word timings for subtitles
        for wd in words:
            all_words.append({
                "text": wd["text"],
                "start": offset + wd["start"],
                "end": offset + wd["end"],
            })
        offset += scene_dur
        log(f"  scene dur={scene_dur:.2f}s, cumulative={offset:.2f}s")

    # 4. concat
    log("Concatenating scenes...")
    concat_path = os.path.join(work_dir, "concat.mp4")
    concat_scenes(scene_paths, concat_path)

    # 5. subtitles (ASS)
    ass_path = os.path.join(work_dir, "subs.ass")
    if subs_enabled:
        log("Building word-by-word subtitles (ASS)...")
        write_ass(all_words, w, h, ass_path)

    # 6. music
    music_path = None
    if music_enabled:
        music_path = os.path.join(work_dir, "music.wav")
        try:
            fetched = os.path.join(work_dir, "music_fetched")
            fetch_pixabay_music(music_query, pixabay_key, fetched)
            music_path = fetched
            log("Background music fetched.")
        except Exception as e:
            log(f"Music fetch failed ({e}); using silence.")
            make_silence(offset, music_path)

    # 7. final render (subs + ducked music)
    log("Final render (subtitles + auto-ducked music)...")
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    render_final(concat_path, ass_path if subs_enabled else None,
                 music_path, out_path,
                 music_vol=music_vol, subs_enabled=subs_enabled,
                 music_enabled=music_enabled)
    log(f"DONE -> {out_path}  ({os.path.getsize(out_path)/1e6:.1f} MB)")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="AI Video Generator — Colab renderer")
    ap.add_argument("--config", required=True, help="project_config.json path")
    ap.add_argument("--out", default="output.mp4", help="output MP4 path")
    ap.add_argument("--pexels-key", default=os.environ.get("PEXELS_API_KEY", ""),
                    help="Pexels API key (free: https://www.pexels.com/api/)")
    ap.add_argument("--pixabay-key", default=os.environ.get("PIXABAY_API_KEY", ""),
                    help="Pixabay API key (free: https://pixabay.com/api/)")
    ap.add_argument("--work-dir", default=None, help="temp working directory")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        log("FFmpeg not found. On Colab run: !apt-get install -y ffmpeg")
        sys.exit(1)
    if not args.pexels_key:
        log("WARNING: no PEXELS_API_KEY — stock_video scenes will fail.")

    t0 = time.time()
    try:
        render(args.config, args.out, args.pexels_key, args.pixabay_key,
               args.work_dir)
        log(f"Total time: {time.time()-t0:.1f}s")
    except Exception as e:
        log(f"FATAL: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

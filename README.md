# 🎬 AI Video Generator (Zero-Cost)

A reliable, **100% free** pipeline to generate **Shorts (9:16)** and **Long (16:9)** videos
with AI voiceover, AI images, stock footage, word-by-word subtitles, and auto-ducked
background music — all on a **mobile browser** (Streamlit UI) + **Google Colab** (render).

> Budget: **$0**. Uses only free tiers of official APIs. No scraping, no ToS violations.

## Architecture

```
┌───────────────────────────┐        ┌────────────────────────────────┐
│  app.py  (Streamlit UI)   │        │  render_script.py (Colab)      │
│  • UZ/EN/RU UI            │        │  • edge-tts  -> voice + words  │
│  • topic + format picker  │ JSON  │  • Pollinations -> AI images   │
│  • Gemini script + hook   │──────▶│  • Pexels API -> stock video   │
│  • editable scene editor  │       │  • FFmpeg Ken Burns (pan/zoom) │
│  • saves project_config   │        │  • word-by-word ASS subtitles  │
│     .json (+ download)    │        │  • sidechain music auto-duck   │
└───────────────────────────┘        │  • → MP4 saved to Google Drive│
   Streamlit Cloud (mobile)           └────────────────────────────────┘
                                      Google Colab (GPU optional)
```

| Tool (free)        | Role                                   | Key needed?        |
|--------------------|----------------------------------------|--------------------|
| Google Gemini      | Script + 3-second viral hook           | ✅ free API key     |
| Microsoft Edge-TTS | Neural voiceover + word timing         | ❌ none             |
| Pollinations.ai    | AI images (flux model)                  | ❌ none             |
| Pexels API         | Stock video clips                      | ✅ free API key     |
| Pixabay API        | Royalty-free background music          | ✅ free API key     |
| FFmpeg             | Ken Burns, subtitles, ducking, mux     | ❌ none             |

## Files

| File                   | Purpose                                              |
|------------------------|------------------------------------------------------|
| `app.py`               | Streamlit web UI (script generation + editor)       |
| `render_script.py`    | Colab video engine (the heavy rendering)            |
| `render_colab.ipynb`   | One-click Colab notebook to run the engine          |
| `requirements_app.txt` | deps for Streamlit app                                |
| `requirements_colab.txt` | deps for Colab renderer                             |
| `.streamlit/secrets.toml.example` | secrets template (Gemini key)          |

## 🔐 Keeping accounts safe (no bans)

- **Never hardcode API keys.** Use Streamlit Secrets (`secrets.toml`) and Colab env vars.
- `.gitignore` blocks `secrets.toml`, `*.env`, and `project_config.json` — keys never reach git.
- Only official, free-tier endpoints are used. **No scraping, no rate-limit abuse.**
- The renderer retries politely and respects response codes; a missing key degrades gracefully
  (e.g., no music → silence) instead of crashing.
- Pollinations & edge-tts are keyless free services — safest to use.

---

## ▶️ Step 1 — Streamlit UI (mobile friendly)

### Run locally
```bash
cd ai-video-generator
pip install -r requirements_app.txt
streamlit run app.py
```

### Deploy on Streamlit Cloud (recommended for mobile)
1. **Push the repo to GitHub** (ensure `.gitignore` is committed first — no secrets).
2. Go to https://share.streamlit.io → *New app* → select your repo, file `app.py`.
3. In the app **Settings → Secrets**, add (or use the in-app key field):
   ```toml
   GEMINI_API_KEY = "your-free-gemini-key"
   ```
4. Get a **free Gemini key**: https://aistudio.google.com/apikey
5. Open the app URL on your phone's browser → pick language → enter topic →
   choose **Shorts/Long** → **Generate script** → edit scenes → **Export** →
   download `project_config.json`.

---

## ▶️ Step 2 — Render on Google Colab

1. Open https://colab.research.google.com → upload `render_colab.ipynb`.
2. **Runtime → Change runtime type → T4 GPU** (optional, speeds up encoding; CPU also works).
3. Run the cells top-to-bottom:
   - Cell 1: installs `edge-tts` + `ffmpeg`, prints GPU status.
   - Cell 2: mounts Google Drive (output saves to `/content/drive/MyDrive/AI_Videos/`).
   - Cell 3: upload your `project_config.json` (from Step 1).
   - Cell 4: paste **Pexels** + **Pixabay** free keys.
     - Pexels: https://www.pexels.com/api/
     - Pixabay: https://pixabay.com/api/
   - Cell 5: runs `render_script.py` → final `MP4` saved to Drive (and downloaded).
   - Cell 6: preview + confirm size.

### Run the renderer directly (no notebook)
```bash
!pip install edge-tts requests
!apt-get install -y ffmpeg
!python render_script.py \
    --config project_config.json \
    --out /content/drive/MyDrive/AI_Videos/out.mp4 \
    --pexels-key "$PEXELS_API_KEY" \
    --pixabay-key "$PIXABAY_API_KEY"
```

---

## How each technical piece works

- **Viral hook:** Gemini is prompted to emit a dedicated `hook` line plus N scenes.
- **Ken Burns motion:** FFmpeg `zoompan` with 4 alternating variants (zoom-in/out + drift),
  pre-scaled to 1.5× so panning never leaves black borders.
- **Word-by-word subtitles:** edge-tts emits `WordBoundary` events (100-ns precision).
  Timings are normalized to the real audio duration, then written as a styled **ASS** file where
  each word is a Dialogue event highlighting the active word in yellow (TikTok karaoke style).
- **Auto-ducking:** FFmpeg `sidechaincompress` — the narration is the sidechain detector that
  compresses the music track (threshold 0.05, ratio 6, attack 20 ms, release 400 ms),
  then both are mixed with narration at full weight.
- **GPU:** `h264_nvenc` is auto-detected on Colab T4; falls back to `libx264`.
- **Concat:** all scenes share identical codec params → lossless concat demuxer copy.

## Config schema (`project_config.json`)
```json
{
  "project": "ai-video-generator", "version": "1.0",
  "topic": "...", "language": "uz", "format": "short",
  "aspect_ratio": "9:16", "resolution": {"width":1080,"height":1920},
  "fps": 30, "voice": "uz-UZ-Madadh_Neural",
  "title": "...", "hook": "...",
  "scenes": [
    {"id":1,"narration":"...","visual_prompt":"...",
     "visual_type":"ai_image","duration":5.0}
  ],
  "music": {"enabled":true,"query":"upbeat","volume":0.35},
  "subtitles": {"enabled":true,"style":"tiktok_word"}
}
```

## Customization tips
- **Voices:** edit `VOICES` in `app.py` — full list at https://github.com/UndeadGT/edge-tts.
- **More languages:** add an `I18N` dict + a `VOICES` entry; Gemini writes narration in that language.
- **Visual mix:** set `visual_type` per scene — `ai_image` (Pollinations) or `stock_video` (Pexels).
- **Subtitle look:** tweak `write_ass()` in `render_script.py` (font size, colors, outline).
- **Music style:** change the music query in the app ("lofi", "epic", "calm", …).

## Troubleshooting
| Problem | Fix |
|--------|-----|
| Gemini `403/429` | Free quota hit — wait 60s or use `gemini-1.5-flash`. |
| Pollinations slow/timeout | Retry; reduce image size, or switch scene to `stock_video`. |
| Pexels "no videos" | Simplify the English `visual_prompt` to a common noun. |
| Subtitle drift | `normalize_words()` auto-rescales to audio duration — keep narration short per scene. |
| No GPU encoding | Colab CPU `libx264` still works (just slower for long videos). |

## License & attribution
Code: MIT. Generated content inherits each source's license (Pexels/Pixabay are free to use
with attribution; Pollinations & edge-tts are free for personal use). Respect each ToS.

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
│  • topic + format picker  │ JSON   │  • Pollinations -> AI images   │
│  • Groq script + hook     │ ─────▶ │  • Pexels API -> stock video   │
│  • editable scene editor  │        │  • FFmpeg Ken Burns (pan/zoom) │
│  • saves project_config   │        │  • word-by-word ASS subtitles  │
│     .json (+ download)    │        │  • sidechain music auto-duck   │
└───────────────────────────┘        │  • → MP4 saved to Google Drive │
   Streamlit Cloud (mobile)          └────────────────────────────────┘
                                     Google Colab (GPU optional)
```

| Tool (free)        | Role                                   | Key needed?        |
|--------------------|----------------------------------------|--------------------|
| Groq (Llama 3.3)   | Script + 3-second viral hook           | ✅ free API key     |
| Microsoft Edge-TTS | Neural voiceover + word timing         | ❌ none             |
| Pollinations.ai    | AI images (flux model)                 | ❌ none             |
| Pexels API         | Stock video clips                      | ✅ free API key     |
| Pixabay API        | Royalty-free background music          | ✅ free API key     |
| FFmpeg             | Ken Burns, subtitles, ducking, mux     | ❌ none             |

> **Why Groq instead of Gemini?** Groq's free tier has no regional restrictions
> and works everywhere (Gemini API free access is blocked in some regions,
> including parts of Central Asia). `llama-3.3-70b-versatile` matches Gemini
> Flash in script quality and supports a strict JSON response mode.

## Files

| File                   | Purpose                                              |
|------------------------|------------------------------------------------------|
| `app.py`               | Streamlit web UI (script generation + editor)        |
| `render_script.py`     | Colab video engine (the heavy rendering)             |
| `render_colab.ipynb`   | One-click Colab notebook to run the engine           |
| `requirements_app.txt` | deps for Streamlit app                               |
| `requirements_colab.txt` | deps for Colab renderer                            |
| `.streamlit/secrets.toml.example` | secrets template (Groq key)            |

## Quick start

### 1. Free API keys (all free, ~2 minutes)

| Service | URL |
|---------|-----|
| **Groq** (script) | https://console.groq.com → API Keys → Create |
| **Pexels** (stock video, Colab) | https://www.pexels.com/api/ → Get started |
| **Pixabay** (music, Colab) | https://pixabay.com/api/docs/ → Get key |

### 2. Deploy the Streamlit UI on your phone

1. Open https://share.streamlit.io in your mobile browser.
2. Sign in with GitHub.
3. **New app** → pick `mrshuha776-ops/ai-video-generator` (or your fork).
4. **Branch:** `main`  •  **Main file:** `app.py`.
5. **Advanced settings → Secrets** → paste:
   ```toml
   GROQ_API_KEY = "gsk_your_key_here"
   ```
6. Tap **Deploy!** (1–2 min, then a public URL is ready).

### 3. Use the app

- Pick language, paste topic, choose Shorts (9:16) or Long (16:9).
- Tap **Generate script** → Groq writes a 3-second viral hook + scene breakdown.
- Edit any scene inline, then **Download `project_config.json`**.

### 4. Render in Google Colab

1. Open `render_colab.ipynb` from the repo in Colab.
2. Run the cells → upload your `project_config.json` → paste Pexels + Pixabay keys.
3. The engine fetches AI images (Pollinations), stock clips (Pexels),
   synthesizes voice (Edge-TTS), burns word-by-word subtitles, applies
   Ken Burns motion, sidechain-ducks the music, and writes the MP4 to Drive.

## Local dev (optional)

```bash
# Streamlit side
pip install -r requirements_app.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit secrets.toml with your real GROQ_API_KEY
streamlit run app.py

# Colab side (any Python env)
pip install -r requirements_colab.txt
python render_script.py --config project_config.json --out out.mp4 \
    --pexels YOUR_PEXELS_KEY --pixabay YOUR_PIXABAY_KEY
```

## Notes

- All keys stay in `secrets.toml` (gitignored) or env vars — never in code.
- Groq free tier: ~14 400 requests/day, works in every region.
- edge-tts returns `WordBoundary` chunks (verified on edge-tts 7.x).
- FFmpeg encoder auto-detected: `h264_nvenc` → `libx264` → `libopenh264`.
- Tested end-to-end: real edge-tts audio, real Pollinations stand-in, real
  Ken Burns, real ASS subtitles, real sidechain ducking, real concat, real MP4.

## License

MIT — fork, modify, ship.
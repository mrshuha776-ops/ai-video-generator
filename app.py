#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Video Generator — Streamlit Web Interface (app.py)
=====================================================
Zero-cost script generation using Google Gemini (free tier).
Generates a viral hook + scene breakdown, lets the user edit it,
and exports a project_config.json that render_script.py (Google Colab)
consumes to render the final MP4.

Run locally:
    pip install -r requirements_app.txt
    streamlit run app.py

Run on Streamlit Cloud (mobile friendly):
    1. Push this repo to GitHub (NO API keys in code).
    2. Deploy on streamlit.io/cloud -> set GEMINI_API_KEY in Secrets.
    3. Open the app URL on a mobile browser.
"""

import json
import os
import re
import tempfile
import datetime

import streamlit as st

# --- Optional dependency: google-generativeai ---------------------------------
try:
    import google.generativeai as genai
    HAS_GENAI = True
except Exception:
    HAS_GENAI = False


# ============================================================================
# Internationalization (Uzbek / English / Russian)
# ============================================================================
I18N = {
    "uz": {
        "title": "AI Video Generator",
        "subtitle": "Bepul AI video yaratuvchi — Gemini + Edge-TTS + Pollinations + Pexels",
        "tab_setup": "Sozlash",
        "tab_script": "Ssenariy",
        "tab_export": "Eksport",
        "language": "Til",
        "api_key": "Gemini API kaliti (bepul)",
        "api_key_help": "Bepul oling: https://aistudio.google.com/apikey",
        "api_key_secret": "Yoki Streamlit Secrets'da GEMINI_API_KEY ni o'rnating.",
        "model": "Gemini modeli",
        "topic": "Video mavzusi",
        "topic_ph": "Masalan: 5 daqiqada ingliz tilini o'rganish sirlari",
        "format": "Format",
        "format_short": "Shorts (9:16)",
        "format_long": "Uzun (16:9)",
        "voice": "Ovoz (Edge-TTS)",
        "generate": "Ssenariy yaratish",
        "generating": "Gemini ishlayapti... Iltimos kuting",
        "hook": "Viral hook (3 soniya)",
        "hook_help": "Birinchi 3 soniyada to'xtatuvchi, qiziqarli ochish",
        "scenes": "Sahnalar",
        "scene": "Sahna",
        "narration": "Ovoz matni (narratsiya)",
        "visual_prompt": "Visual tavsifi (inglizcha)",
        "visual_type": "Visual turi",
        "vt_image": "AI rasm",
        "vt_video": "Stock video",
        "duration": "Davomiylik (s)",
        "title_field": "Video sarlavhasi",
        "description": "Tavsif (YouTube/Shorts)",
        "tags": "Teglar (vergul bilan)",
        "save": "Loyiha konfiguratsiyasini saqlash",
        "saved": "Saqlandi! Endi eksport qiling.",
        "download": "project_config.json yuklab olish",
        "config_preview": "Konfiguratsiya (JSON)",
        "need_key": "Iltimos, Gemini API kalitini kiriting.",
        "genai_missing": "`google-generativeai` topilmadi. requirements_app.txt ni o'rnating.",
        "error": "Xato yuz berdi",
        "music": "Fon musiqasi",
        "music_query": "Musiqa uslubi (kalit so'z)",
        "music_vol": "Musiqa balandligi",
        "subtitles": "Subtitrlar (so'zma-so'z, TikTok uslubi)",
        "advanced": "Qo'shimcha sozlamalar",
        "fps": "FPS",
        "tip_drive": "Colab'da render qilganda video Google Drive'ga saqlanadi.",
        "render_next": "Keyingi qadam: Google Colab'da render qiling",
        "render_steps": (
            "1. render_colab.ipynb ni Google Colab'da oching\n"
            "2. project_config.json'ni yuklang (yoki Drive'ga qo'ying)\n"
            "3. PEXELS_API_KEY va PIXABAY_API_KEY ni kiriting\n"
            "4. Barcha hujayirlarni ishga tushiring — MP4 Drive'ga saqlanadi"
        ),
        "about": "Bu vosita 100% bepul: Gemini (ssenariy), Edge-TTS (ovoz), "
                 "Pollinations.ai (AI rasmlar), Pexels (stock video), FFmpeg (render).",
    },
    "en": {
        "title": "AI Video Generator",
        "subtitle": "Zero-cost AI video maker — Gemini + Edge-TTS + Pollinations + Pexels",
        "tab_setup": "Setup",
        "tab_script": "Script",
        "tab_export": "Export",
        "language": "Language",
        "api_key": "Gemini API key (free)",
        "api_key_help": "Get one free: https://aistudio.google.com/apikey",
        "api_key_secret": "Or set GEMINI_API_KEY in Streamlit Secrets.",
        "model": "Gemini model",
        "topic": "Video topic",
        "topic_ph": "e.g. 5 secrets to learning English in minutes",
        "format": "Format",
        "format_short": "Shorts (9:16)",
        "format_long": "Long (16:9)",
        "voice": "Voice (Edge-TTS)",
        "generate": "Generate script",
        "generating": "Gemini is working... please wait",
        "hook": "Viral hook (3 seconds)",
        "hook_help": "A scroll-stopping, curiosity-driven opener",
        "scenes": "Scenes",
        "scene": "Scene",
        "narration": "Voiceover text (narration)",
        "visual_prompt": "Visual description (English)",
        "visual_type": "Visual type",
        "vt_image": "AI image",
        "vt_video": "Stock video",
        "duration": "Duration (s)",
        "title_field": "Video title",
        "description": "Description (YouTube/Shorts)",
        "tags": "Tags (comma separated)",
        "save": "Save project config",
        "saved": "Saved! Now export it.",
        "download": "Download project_config.json",
        "config_preview": "Config (JSON)",
        "need_key": "Please enter your Gemini API key.",
        "genai_missing": "`google-generativeai` not found. Install requirements_app.txt.",
        "error": "An error occurred",
        "music": "Background music",
        "music_query": "Music style (keyword)",
        "music_vol": "Music volume",
        "subtitles": "Subtitles (word-by-word, TikTok style)",
        "advanced": "Advanced",
        "fps": "FPS",
        "tip_drive": "Rendering on Colab saves the MP4 to Google Drive.",
        "render_next": "Next step: render on Google Colab",
        "render_steps": (
            "1. Open render_colab.ipynb in Google Colab\n"
            "2. Upload your project_config.json (or place on Drive)\n"
            "3. Enter PEXELS_API_KEY and PIXABAY_API_KEY\n"
            "4. Run all cells — MP4 is saved to Drive"
        ),
        "about": "This tool is 100% free: Gemini (script), Edge-TTS (voice), "
                 "Pollinations.ai (AI images), Pexels (stock video), FFmpeg (render).",
    },
    "ru": {
        "title": "AI Video Generator",
        "subtitle": "Бесплатный AI видео-генератор — Gemini + Edge-TTS + Pollinations + Pexels",
        "tab_setup": "Настройка",
        "tab_script": "Сценарий",
        "tab_export": "Экспорт",
        "language": "Язык",
        "api_key": "Gemini API ключ (бесплатно)",
        "api_key_help": "Получить бесплатно: https://aistudio.google.com/apikey",
        "api_key_secret": "Или задайте GEMINI_API_KEY в Streamlit Secrets.",
        "model": "Gemini модель",
        "topic": "Тема видео",
        "topic_ph": "напр. 5 секретов изучения английского за минуты",
        "format": "Формат",
        "format_short": "Shorts (9:16)",
        "format_long": "Длинное (16:9)",
        "voice": "Голос (Edge-TTS)",
        "generate": "Создать сценарий",
        "generating": "Gemini работает... подождите",
        "hook": "Вирусный хук (3 секунды)",
        "hook_help": "Цепляющее начало, останавливающее скролл",
        "scenes": "Сцены",
        "scene": "Сцена",
        "narration": "Текст озвучки",
        "visual_prompt": "Описание визуала (английский)",
        "visual_type": "Тип визуала",
        "vt_image": "AI изображение",
        "vt_video": "Stock видео",
        "duration": "Длительность (с)",
        "title_field": "Заголовок видео",
        "description": "Описание (YouTube/Shorts)",
        "tags": "Теги (через запятую)",
        "save": "Сохранить конфиг проекта",
        "saved": "Сохранено! Теперь экспортируйте.",
        "download": "Скачать project_config.json",
        "config_preview": "Конфигурация (JSON)",
        "need_key": "Пожалуйста, введите Gemini API ключ.",
        "genai_missing": "`google-generativeai` не найден. Установите requirements_app.txt.",
        "error": "Произошла ошибка",
        "music": "Фоновая музыка",
        "music_query": "Стиль музыки (ключевое слово)",
        "music_vol": "Громкость музыки",
        "subtitles": "Субтитры (по словам, TikTok стиль)",
        "advanced": "Дополнительно",
        "fps": "FPS",
        "tip_drive": "Рендер в Colab сохраняет MP4 в Google Drive.",
        "render_next": "Следующий шаг: рендер в Google Colab",
        "render_steps": (
            "1. Откройте render_colab.ipynb в Google Colab\n"
            "2. Загрузите project_config.json (или на Drive)\n"
            "3. Введите PEXELS_API_KEY и PIXABAY_API_KEY\n"
            "4. Запустите все ячейки — MP4 сохранится на Drive"
        ),
        "about": "Инструмент 100% бесплатный: Gemini (сценарий), Edge-TTS (голос), "
                 "Pollinations.ai (AI изображения), Pexels (stock видео), FFmpeg (рендер).",
    },
}

LANG_NAMES = {"uz": "O'zbekcha", "en": "English", "ru": "Русский"}

# Default Edge-TTS voices per language (verified against edge-tts 7.x voice list)
# Run `edge-tts --list-voices` to see the full, always-current list.
VOICES = {
    "uz": ["uz-UZ-MadinaNeural", "uz-UZ-SardorNeural"],
    "en": ["en-US-AvaNeural", "en-US-AndrewNeural", "en-US-EmmaNeural",
           "en-US-BrianNeural", "en-GB-SoniaNeural", "en-GB-RyanNeural"],
    "ru": ["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"],
}

# Format presets
FORMATS = {
    "short": {"ratio": "9:16", "w": 1080, "h": 1920, "scenes": 7,
              "wps": 12, "target": "45-60 seconds", "music": "upbeat"},
    "long":  {"ratio": "16:9", "w": 1920, "h": 1080, "scenes": 24,
              "wps": 20, "target": "4-6 minutes", "music": "cinematic"},
}


# ============================================================================
# Gemini helpers
# ============================================================================
SCHEMA_DOC = (
    "{\n"
    '  "title": "short catchy video title",\n'
    '  "hook": "the 3-second viral hook line only",\n'
    '  "scenes": [\n'
    '    {\n'
    '      "narration": "voiceover text in the target language",\n'
    '      "visual_prompt": "English description for image generation OR a short English Pexels search query",\n'
    '      "visual_type": "ai_image or stock_video",\n'
    '      "duration": 5\n'
    '    }\n'
    '  ],\n'
    '  "description": "1-2 sentence video description for YouTube/Shorts",\n'
    '  "tags": ["tag1", "tag2", "tag3"]\n'
    "}\n"
)


def build_prompt(topic: str, lang_name: str, lang_code: str, fmt_key: str) -> str:
    """Build the Gemini prompt (instructions in English, output narration in target lang)."""
    f = FORMATS[fmt_key]
    n = f["scenes"]
    wps = f["wps"]
    target = f["target"]
    narration_lang = lang_name

    prompt = (
        "You are a professional viral short-form video scriptwriter.\n"
        f"Create a {fmt_key.upper()} video script about: \"{topic}\".\n"
        f"The narration MUST be written in {narration_lang} (language code: {lang_code}).\n"
        f"The visual_prompt fields MUST be in English.\n\n"
        "REQUIREMENTS:\n"
        "1. Write a 3-second VIRAL HOOK: a bold, curiosity-driven, scroll-stopping opening line.\n"
        f"2. Break the content into exactly {n} scenes.\n"
        f"3. Each scene narration ~{wps} words, natural and engaging to speak aloud.\n"
        f"4. Total target duration: {target}.\n"
        "5. visual_type = \"ai_image\" for conceptual/abstract/illustrative visuals;\n"
        "   visual_type = \"stock_video\" for real-world footage (people, nature, cities, actions).\n"
        "6. The LAST scene MUST end with a clear call-to-action (CTA).\n"
        "7. duration = estimated seconds the narration takes (match speaking pace ~2.5 words/sec).\n\n"
        "Return ONLY a JSON object (no markdown, no code fences, no extra text) "
        "with EXACTLY this schema:\n"
        + SCHEMA_DOC
    )
    return prompt


def clean_json_response(text: str) -> str:
    """Strip markdown fences and extract the JSON object."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # Fallback: extract from first { to last }
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        text = text[first:last + 1]
    return text


def generate_script(api_key: str, prompt: str, model_name: str) -> dict:
    """Call Gemini free tier and return parsed dict."""
    if not HAS_GENAI:
        raise RuntimeError("google-generativeai is not installed.")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    # Ask for JSON; wrap in try/except for safety
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.85,
                top_p=0.95,
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        )
    except Exception:
        # Older SDKs don't support response_mime_type; retry without it
        response = model.generate_content(prompt)

    raw = response.text if hasattr(response, "text") else str(response.candidates[0].content)
    cleaned = clean_json_response(raw)
    data = json.loads(cleaned)

    # Validate / normalize
    if "scenes" not in data or not isinstance(data["scenes"], list):
        raise ValueError("Gemini response missing 'scenes' array.")
    for i, sc in enumerate(data["scenes"], 1):
        sc.setdefault("id", i)
        sc["id"] = sc.get("id", i)
        sc.setdefault("visual_type", "ai_image")
        sc.setdefault("duration", 5)
        if sc["visual_type"] not in ("ai_image", "stock_video"):
            sc["visual_type"] = "ai_image"
    data.setdefault("title", "")
    data.setdefault("hook", "")
    data.setdefault("description", "")
    data.setdefault("tags", [])
    return data


# ============================================================================
# Config builder
# ============================================================================
def build_config(state: dict) -> dict:
    fmt_key = state["fmt_key"]
    f = FORMATS[fmt_key]
    scenes = []
    for sc in state["scenes"]:
        scenes.append({
            "id": sc.get("id", len(scenes) + 1),
            "narration": sc["narration"],
            "visual_prompt": sc["visual_prompt"],
            "visual_type": sc["visual_type"],
            "duration": float(sc["duration"]),
        })
    return {
        "project": "ai-video-generator",
        "version": "1.0",
        "created": datetime.datetime.utcnow().isoformat() + "Z",
        "topic": state["topic"],
        "language": state["lang"],
        "language_name": LANG_NAMES[state["lang"]],
        "format": fmt_key,
        "aspect_ratio": f["ratio"],
        "resolution": {"width": f["w"], "height": f["h"]},
        "fps": state["fps"],
        "voice": state["voice"],
        "title": state["title"],
        "hook": state["hook"],
        "description": state["description"],
        "tags": [t.strip() for t in state["tags"].split(",") if t.strip()],
        "scenes": scenes,
        "music": {
            "enabled": state["music_enabled"],
            "query": state["music_query"],
            "volume": state["music_vol"],
        },
        "subtitles": {
            "enabled": state["subs_enabled"],
            "style": "tiktok_word",
        },
    }


def save_config(cfg: dict) -> str:
    """Save to Google Drive path (if GDRIVE_PATH set & exists) else temp folder."""
    gdrive = os.environ.get("GDRIVE_PATH", "")
    name = "project_config.json"
    if gdrive and os.path.isdir(gdrive):
        path = os.path.join(gdrive, name)
    else:
        path = os.path.join(tempfile.gettempdir(), name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    return path


# ============================================================================
# Streamlit UI
# ============================================================================
def init_state():
    if "lang" not in st.session_state:
        st.session_state.lang = "uz"
    if "scenes" not in st.session_state:
        st.session_state.scenes = []
    if "hook" not in st.session_state:
        st.session_state.hook = ""
    if "title" not in st.session_state:
        st.session_state.title = ""


def main():
    st.set_page_config(page_title="AI Video Generator", page_icon="🎬",
                       layout="centered", initial_sidebar_state="expanded")
    init_state()

    t = I18N[st.session_state.lang]

    # --- Sidebar: language + setup --------------------------------------------
    with st.sidebar:
        st.header("⚙️")
        lang_opts = list(LANG_NAMES.keys())
        idx = lang_opts.index(st.session_state.lang)
        new_lang = st.selectbox(
            t["language"],
            options=lang_opts,
            index=idx,
            format_func=lambda x: LANG_NAMES[x],
            key="lang_sel",
        )
        if new_lang != st.session_state.lang:
            st.session_state.lang = new_lang
            st.rerun()

        t = I18N[st.session_state.lang]

        # API key (Secrets > manual input)
        default_key = st.secrets.get("GEMINI_API_KEY", "") if hasattr(st, "secrets") else ""
        api_key = st.text_input(
            t["api_key"], value=default_key, type="password",
            help=t["api_key_help"], key="gem_key")
        if not default_key:
            st.caption("💡 " + t["api_key_secret"])

        model = st.selectbox(t["model"],
                             ["gemini-2.0-flash", "gemini-2.5-flash",
                              "gemini-1.5-flash", "gemini-2.0-flash-lite"],
                             index=0, key="model_sel")

        st.divider()
        st.caption("ℹ️ " + t["about"])

    # --- Header ----------------------------------------------------------------
    st.title("🎬 " + t["title"])
    st.caption(t["subtitle"])

    tab_setup, tab_script, tab_export = st.tabs([t["tab_setup"], t["tab_script"], t["tab_export"]])

    # --- TAB: Setup ------------------------------------------------------------
    with tab_setup:
        st.subheader(t["tab_setup"])
        topic = st.text_input(t["topic"], placeholder=t["topic_ph"], key="topic_input")
        fmt_key = st.radio(
            t["format"],
            options=["short", "long"],
            format_func=lambda x: t["format_short"] if x == "short" else t["format_long"],
            horizontal=True, key="fmt_key_radio")
        st.session_state["fmt_key"] = fmt_key

        voices = VOICES[st.session_state.lang]
        voice = st.selectbox(t["voice"], options=voices, key="voice_sel")
        st.session_state["voice"] = voice

        with st.expander(t["advanced"]):
            fps = st.select_slider(t["fps"], options=[24, 25, 30, 60], value=30, key="fps_sel")
            st.session_state["fps"] = fps

            music_enabled = st.checkbox(t["music"], value=True, key="me_sel")
            music_query = st.text_input(
                t["music_query"],
                value=FORMATS[fmt_key]["music"],
                key="mq_sel")
            music_vol = st.slider(t["music_vol"], 0.0, 1.0, 0.35, 0.05, key="mv_sel")
            st.session_state["music_enabled"] = music_enabled
            st.session_state["music_query"] = music_query
            st.session_state["music_vol"] = music_vol

            subs_enabled = st.checkbox(t["subtitles"], value=True, key="se_sel")
            st.session_state["subs_enabled"] = subs_enabled

        if st.button("✨ " + t["generate"], type="primary", use_container_width=True):
            if not api_key:
                st.warning(t["need_key"])
            elif not HAS_GENAI:
                st.error(t["genai_missing"])
            elif not topic.strip():
                st.warning(t["topic_ph"])
            else:
                with st.spinner(t["generating"]):
                    try:
                        prompt = build_prompt(topic.strip(), LANG_NAMES[st.session_state.lang],
                                              st.session_state.lang, fmt_key)
                        data = generate_script(api_key, prompt, model)
                        st.session_state.scenes = data["scenes"]
                        st.session_state.hook = data.get("hook", "")
                        st.session_state.title = data.get("title", "")
                        st.session_state.desc = data.get("description", "")
                        st.session_state.tags_str = ", ".join(data.get("tags", []))
                        st.session_state.topic = topic.strip()
                        st.success("✅ " + t["saved"])
                        st.rerun()
                    except Exception as e:
                        st.error(f"{t['error']}: {e}")

    # --- TAB: Script (editable) ------------------------------------------------
    with tab_script:
        if not st.session_state.scenes:
            st.info("👈 " + t["generate"])
        else:
            st.subheader(t["tab_script"])
            st.session_state.title = st.text_input(t["title_field"],
                                                   value=st.session_state.title, key="t_field")
            st.session_state.hook = st.text_area(
                t["hook"], value=st.session_state.hook, height=80,
                help=t["hook_help"], key="h_field")

            st.divider()
            st.subheader(t["scenes"])
            st.session_state.desc = st.text_area(t["description"],
                                                 value=getattr(st.session_state, "desc", ""),
                                                 height=60, key="d_field")
            st.session_state.tags_str = st.text_input(
                t["tags"], value=getattr(st.session_state, "tags_str", ""), key="g_field")

            edited = []
            for i, sc in enumerate(st.session_state.scenes):
                with st.container(border=True):
                    c1, c2, c3 = st.columns([0.5, 4, 1.5])
                    c1.markdown(f"**{t['scene']} {i+1}**")
                    narration = c2.text_area(t["narration"], value=sc.get("narration", ""),
                                             height=70, key=f"n_{i}", label_visibility="collapsed")
                    vprompt = c2.text_input(t["visual_prompt"], value=sc.get("visual_prompt", ""),
                                            key=f"v_{i}")
                    vtype = c3.selectbox(t["visual_type"],
                                         options=["ai_image", "stock_video"],
                                         index=0 if sc.get("visual_type") != "stock_video" else 1,
                                         format_func=lambda x: t["vt_image"] if x == "ai_image" else t["vt_video"],
                                         key=f"vt_{i}")
                    dur = c3.number_input(t["duration"], min_value=1.0, max_value=120.0,
                                          value=float(sc.get("duration", 5)), step=0.5, key=f"d_{i}")
                    edited.append({
                        "id": i + 1, "narration": narration,
                        "visual_prompt": vprompt, "visual_type": vtype, "duration": dur,
                    })
            st.session_state.scenes = edited
            st.session_state.desc = getattr(st.session_state, "desc", "")
            st.session_state.tags_str = getattr(st.session_state, "tags_str", "")

            # total duration
            total = sum(s["duration"] for s in edited)
            st.caption(f"⏱️ ~{total:.0f}s · {len(edited)} {t['scenes'].lower()}")

    # --- TAB: Export -----------------------------------------------------------
    with tab_export:
        if not st.session_state.scenes:
            st.info("👈 " + t["generate"])
        else:
            st.subheader(t["tab_export"])
            st.session_state.topic = getattr(st.session_state, "topic", "")

            cfg = build_config({
                "topic": st.session_state.topic,
                "lang": st.session_state.lang,
                "fmt_key": st.session_state.get("fmt_key", "short"),
                "fps": st.session_state.get("fps", 30),
                "voice": st.session_state.voice,
                "title": st.session_state.title,
                "hook": st.session_state.hook,
                "description": getattr(st.session_state, "desc", ""),
                "tags": getattr(st.session_state, "tags_str", ""),
                "scenes": st.session_state.scenes,
                "music_enabled": st.session_state.get("music_enabled", True),
                "music_query": st.session_state.get("music_query", "cinematic"),
                "music_vol": st.session_state.get("music_vol", 0.35),
                "subs_enabled": st.session_state.get("subs_enabled", True),
            })

            # Save + show path
            path = save_config(cfg)
            st.success(f"✅ {t['saved']} `{path}`")
            st.caption(t["tip_drive"])

            st.download_button(
                "📥 " + t["download"],
                data=json.dumps(cfg, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name="project_config.json",
                mime="application/json",
                use_container_width=True,
            )

            with st.expander(t["config_preview"], expanded=False):
                st.json(cfg)

            st.divider()
            st.subheader("🚀 " + t["render_next"])
            st.code(t["render_steps"])


if __name__ == "__main__":
    main()

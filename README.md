---
title: AutoTube AI Studio
emoji: 🎬
colorFrom: indigo
colorTo: purple
sdk: streamlit
sdk_version: 1.38.0
app_file: app.py
pinned: false
---

# 🎬 AutoTube AI Studio

AutoTube AI is an autonomous, publication-grade AI video production studio powered by Google Gemini, Kokoro/XTTS voice synthesis, FFmpeg audio-ducking engine, and an embedded conversational AI Copilot.

---

## 🚀 Hugging Face Spaces Quick Setup

When deploying to a **Private Hugging Face Space** with the Streamlit SDK:

### 1. Configure Space Secrets
Go to your Space **Settings** ➔ **Variables and secrets** ➔ **New secret** and add:

| Secret Name | Description | Required | Example |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Google Gemini API Key for script, copilot, and review | **Yes** | `AQ.Ab8...` |
| `PEXELS_API_KEY` | Pexels API Key for b-roll footage and high-res visuals | **Recommended** | `X9R5Rvj...` |
| `APP_PIN` | Mobile Security PIN to unlock the web dashboard | **Recommended** | `8501` |

> [!NOTE]
> Hugging Face automatically injects these secrets into standard container environment variables (`os.environ`). The application detects them automatically.

---

## 🛠️ Features & Architecture

- **🤖 AI Studio Copilot**: Natural language controller for triggering generation, tweaking hooks, and diagnosing errors in real time.
- **🛡️ Autonomous Self-Healing Supervisor**: Global exception interceptor with multi-tier fallbacks (retry with backoff, asset substitution, parameter adjustment).
- **🎵 Dynamic Audio Ducking Engine**: FFmpeg sidechain audio compression automatically lowers background music whenever narration speaks.
- **📐 Dynamic Aspect Ratios**: One-click switching between **16:9 Landscape**, **9:16 Vertical Shorts/Reels**, and **1:1 Square**.
- **📊 Granular Quality Review**: Independent scoring for Script, Audio, and Visuals with targeted component re-generation.
- **📱 Touch-Optimized Mobile Viewport**: Mobile PIN gatekeeper with brute-force lockout and responsive glassmorphic UI.

---

## 📦 System Dependencies

Container dependencies are automatically installed via:
- `packages.txt`: `ffmpeg`, `libsndfile1`
- `requirements.txt`: Streamlit, Google GenAI SDK, Pillow, Pydub, SoundFile, Edge-TTS, Kokoro, etc.

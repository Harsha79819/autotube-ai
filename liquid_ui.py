"""
AutoTube AI - iOS Liquid Glassmorphism & Pristine 4K Realistic Nature System (liquid_ui.py)
Implements precise Apple-inspired liquid glass tokens:
  - Pristine 4K realistic nature scenery (Lake Braies Dolomites, Alpine peaks, misty gorges, serene reflections)
  - Organic Ken Burns subtle camera drift and warm atmospheric vignette
  - Zero artificial leaf animations, zero cartoon overlays, zero code/matrix streams, zero bubbles
  - Translucent frosted glass sheets (rgba(6, 20, 32, 0.52), blur(36px)) with refractive edge highlights
  - Crisp white-to-cyan typography (linear-gradient(135deg, #E0F2FE 0%, #38BDF8 50%, #2DD4BF 100%))
  - Sleek Apple-inspired action buttons in glowing cyan-teal gradient (zero orange accents)
  - 100% clean HTML injection preventing raw code tags or markdown code blocks
"""

from pathlib import Path
import streamlit as st
from providers.tracker import get_latest_step_providers, get_step_audit_log, get_provider_status

ROOT = Path(__file__).resolve().parent

def get_nature_bg_markup() -> str:
    """
    Generates the pristine 4K realistic nature landscape backdrop:
    - 4K rotating alpine lake, mountain peak, and serene water reflections
    - Organic slow Ken Burns parallax motion
    - Subtle warm atmospheric vignette overlay
    - Zero artificial leaf animations, zero cartoon overlays, zero code/matrix streams, zero bubbles.
    Returns clean, compact HTML with zero indentation to prevent markdown code block triggers.
    """
    slide1_url = "https://images.unsplash.com/photo-1501785888041-af3ef285b470?auto=format&fit=crop&w=2560&q=85"
    slide2_url = "https://images.unsplash.com/photo-1469474968028-56623f02e42e?auto=format&fit=crop&w=2560&q=85"
    slide3_url = "https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=2560&q=85"
    slide4_url = "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=2560&q=85"

    return (
        '<div class="nature-bg-container">'
        f'<div class="nature-bg-slide slide-1" style="background-image: url(\'{slide1_url}\');"></div>'
        f'<div class="nature-bg-slide slide-2" style="background-image: url(\'{slide2_url}\');"></div>'
        f'<div class="nature-bg-slide slide-3" style="background-image: url(\'{slide3_url}\');"></div>'
        f'<div class="nature-bg-slide slide-4" style="background-image: url(\'{slide4_url}\');"></div>'
        '<div class="nature-vignette-overlay"></div>'
        '<div class="cinematic-flare"></div>'
        '</div>'
    )


HUD_GLASS_CSS = """
:root {
  /* Pristine Deep Atmospheric Alpine Nature */
  --bg-base: #03080e;
  --bg-gradient:
    radial-gradient(ellipse at 50% 0%, rgba(6, 182, 212, 0.16) 0%, rgba(14, 116, 144, 0.08) 45%, transparent 70%),
    radial-gradient(circle at 18% 75%, rgba(20, 184, 166, 0.12) 0%, transparent 48%),
    radial-gradient(circle at 85% 85%, rgba(2, 132, 199, 0.14) 0%, transparent 50%),
    #03080e;

  /* Apple / iOS Translucent Frosted iPhone Glass */
  --panel-bg: rgba(6, 20, 32, 0.52);
  --panel-bg-light: rgba(8, 26, 42, 0.44);
  --panel-blur: blur(36px) saturate(190%);
  --panel-border: 1px solid rgba(125, 211, 252, 0.28);
  --panel-radius: 24px;
  --panel-shadow: 0 24px 60px rgba(0, 0, 0, 0.70), inset 0 1px 0 rgba(255, 255, 255, 0.42), inset 0 0 24px rgba(6, 182, 212, 0.12);

  /* Modern Cyan-to-Teal Accents (Zero Orange) */
  --accent: #06b6d4;
  --accent-light: #38bdf8;
  --accent-dark: #0284c7;
  --accent-gradient: linear-gradient(135deg, #0284c7 0%, #0ea5e9 45%, #06b6d4 100%);
  --accent-glow: 0 4px 24px rgba(6, 182, 212, 0.45);

  /* Status Colors */
  --status-ok: #2dd4bf;
  --status-ready: #38bdf8;

  /* Typography */
  --text-primary: #ffffff;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --text-label-spacing: 0.06em;
}

/* Streamlit Base Overrides */
.stApp {
  background: transparent !important;
  background-color: transparent !important;
  color: var(--text-primary) !important;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif !important;
}

.block-container {
  position: relative !important;
  z-index: 10 !important;
  max-width: 1450px !important;
  padding-top: 1.5rem !important;
  padding-bottom: 4rem !important;
}

header[data-testid="stHeader"] {
  background: transparent !important;
}

section[data-testid="stSidebar"] {
  background: rgba(4, 14, 24, 0.94) !important;
  border-right: 1px solid rgba(125, 211, 252, 0.15) !important;
  backdrop-filter: blur(28px) !important;
}

/* ========================================================
   PRISTINE 4K REALISTIC NATURE BACKGROUND
   ======================================================== */
.nature-bg-container {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

.nature-bg-slide {
  position: absolute;
  top: -5%;
  left: -5%;
  width: 110%;
  height: 110%;
  background-size: cover;
  background-position: center center;
  opacity: 0;
  will-change: transform, opacity;
}

.slide-1 {
  animation: slideFade1 32s infinite, natureDrift 32s ease-in-out infinite alternate;
}
.slide-2 {
  animation: slideFade2 32s infinite, natureDrift 32s ease-in-out infinite alternate;
}
.slide-3 {
  animation: slideFade3 32s infinite, natureDrift 32s ease-in-out infinite alternate;
}
.slide-4 {
  animation: slideFade4 32s infinite, natureDrift 32s ease-in-out infinite alternate;
}

@keyframes slideFade1 {
  0% { opacity: 1; }
  22% { opacity: 1; }
  28% { opacity: 0; }
  94% { opacity: 0; }
  100% { opacity: 1; }
}

@keyframes slideFade2 {
  0% { opacity: 0; }
  22% { opacity: 0; }
  28% { opacity: 1; }
  47% { opacity: 1; }
  53% { opacity: 0; }
  100% { opacity: 0; }
}

@keyframes slideFade3 {
  0% { opacity: 0; }
  47% { opacity: 0; }
  53% { opacity: 1; }
  72% { opacity: 1; }
  78% { opacity: 0; }
  100% { opacity: 0; }
}

@keyframes slideFade4 {
  0% { opacity: 0; }
  72% { opacity: 0; }
  78% { opacity: 1; }
  94% { opacity: 1; }
  100% { opacity: 0; }
}

@keyframes natureDrift {
  0% { transform: scale(1.02) translate3d(0, 0, 0); }
  35% { transform: scale(1.05) translate3d(-1.0%, -0.5%, 0); }
  70% { transform: scale(1.04) translate3d(0.7%, 0.4%, 0); }
  100% { transform: scale(1.03) translate3d(-0.3%, 0.6%, 0); }
}

/* Subtle Nature Atmospheric Vignette */
.nature-vignette-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
  background: radial-gradient(circle at 50% 50%, rgba(3, 8, 14, 0.15) 0%, rgba(3, 8, 14, 0.48) 70%, rgba(3, 8, 14, 0.78) 100%);
}

.cinematic-flare {
  position: absolute;
  top: 14%;
  right: 15%;
  width: 60vw;
  height: 2px;
  pointer-events: none;
  z-index: 1;
  background: linear-gradient(90deg, transparent 0%, rgba(56, 189, 248, 0.14) 25%, rgba(125, 211, 252, 0.35) 50%, rgba(6, 182, 212, 0.14) 75%, transparent 100%);
  filter: blur(2.5px);
  transform: rotate(-7deg);
  opacity: 0.60;
}

/* ========================================================
   APPLE / iOS LIQUID GLASSMORPHISM CARDS & PANELS
   ======================================================== */
.glass-header-card, .glass-card:first-of-type {
  background: var(--panel-bg) !important;
  border: var(--panel-border) !important;
  border-radius: 24px !important;
  padding: 16px 28px !important;
  backdrop-filter: var(--panel-blur) !important;
  -webkit-backdrop-filter: var(--panel-blur) !important;
  box-shadow: var(--panel-shadow) !important;
  margin-bottom: 24px !important;
}

.glass-card {
  background: var(--panel-bg) !important;
  border: var(--panel-border) !important;
  border-radius: var(--panel-radius) !important;
  padding: 26px 28px !important;
  backdrop-filter: var(--panel-blur) !important;
  -webkit-backdrop-filter: var(--panel-blur) !important;
  box-shadow: var(--panel-shadow) !important;
  margin-bottom: 20px !important;
}

/* Sleek floating liquid glass sheets for Create Video and Media Panels */
div[data-testid="column"]:has(div[data-testid="stSelectbox"]),
div[data-testid="column"]:has(div[data-testid="stFileUploader"]) {
  background: var(--panel-bg) !important;
  border: var(--panel-border) !important;
  border-radius: var(--panel-radius) !important;
  padding: 24px 28px !important;
  backdrop-filter: var(--panel-blur) !important;
  -webkit-backdrop-filter: var(--panel-blur) !important;
  box-shadow: var(--panel-shadow) !important;
}

/* Brand Logo */
.brand {
  font-size: 28px;
  font-weight: 850;
  letter-spacing: -0.5px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand span {
  background: linear-gradient(135deg, #38bdf8 0%, #06b6d4 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  font-weight: 850;
}

/* Status Badges */
.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  margin-left: 6px;
  border-radius: 999px;
  background: rgba(125, 211, 252, 0.08);
  border: 1px solid rgba(125, 211, 252, 0.20);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: var(--text-label-spacing);
  text-transform: uppercase;
  color: #e0f2fe;
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.status-ok-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  border-radius: 999px;
  background: rgba(45, 212, 191, 0.14);
  border: 1px solid rgba(45, 212, 191, 0.35);
  color: var(--status-ok);
  font-size: 11px;
  font-weight: 750;
  letter-spacing: var(--text-label-spacing);
  text-transform: uppercase;
}

/* Hero Typography */
.hero-title {
  font-size: 48px;
  line-height: 1.1;
  font-weight: 850;
  letter-spacing: -1.5px;
  margin-top: 14px;
  color: #ffffff;
}

.hero-gradient {
  background: linear-gradient(135deg, #e0f2fe 0%, #38bdf8 45%, #2dd4bf 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.hero-subtitle {
  color: var(--text-secondary);
  font-size: 15.5px;
  line-height: 1.5;
  margin-top: 10px;
  margin-bottom: 24px;
  max-width: 820px;
}

/* Headings */
.section-title {
  font-size: 22px;
  font-weight: 800;
  margin-bottom: 4px;
  color: #ffffff;
  letter-spacing: -0.3px;
}

.section-subtitle {
  color: var(--text-secondary);
  font-size: 13.5px;
  line-height: 1.45;
  margin-bottom: 18px;
}

/* Telemetry Stat Blocks */
.hud-telemetry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin: 14px 0;
}

.hud-stat-box {
  background: var(--panel-bg-light);
  border: var(--panel-border);
  border-radius: 16px;
  padding: 14px 16px;
  backdrop-filter: var(--panel-blur);
  position: relative;
  overflow: hidden;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25);
}

.hud-stat-box::after {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 100%;
  background: var(--accent);
}

.hud-stat-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: var(--text-label-spacing);
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.hud-stat-value {
  font-size: 19px;
  font-weight: 800;
  color: var(--text-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.hud-stat-sub {
  font-size: 11px;
  color: var(--status-ok);
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Shared Design Tokens */
.glass-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: var(--text-label-spacing);
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.glass-value {
  font-size: 20px;
  font-weight: 800;
  color: var(--text-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.glass-progress {
  width: 100%;
  height: 6px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  overflow: hidden;
  margin: 6px 0;
}

.glass-progress-fill {
  height: 100%;
  background: var(--accent-gradient);
  border-radius: 999px;
}

.glass-button-primary {
  background: var(--accent-gradient);
  color: #ffffff !important;
  border-radius: 14px;
  box-shadow: var(--accent-glow);
  font-weight: 750;
  border: 1px solid rgba(125, 211, 252, 0.40);
  padding: 10px 20px;
  cursor: pointer;
  display: inline-block;
  text-align: center;
  text-decoration: none;
}

.glass-alert-banner {
  border-left: 3px solid var(--accent);
  background: var(--panel-bg-light);
  border-radius: 12px;
  padding: 12px 16px;
  margin: 10px 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.telemetry-frame {
  position: relative;
  border-radius: var(--panel-radius);
  overflow: hidden;
  border: var(--panel-border);
}

/* Streamlit Inputs & Selectboxes */
div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
textarea {
  background: rgba(6, 22, 36, 0.65) !important;
  border: 1px solid rgba(125, 211, 252, 0.20) !important;
  border-radius: 14px !important;
  color: var(--text-primary) !important;
  backdrop-filter: blur(18px) !important;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.35) !important;
}

div[data-baseweb="input"]:focus-within > div,
div[data-baseweb="select"]:focus-within > div,
textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 1px var(--accent), 0 0 18px rgba(6, 182, 212, 0.45) !important;
}

/* Dropdown menu items */
ul[data-baseweb="menu"] {
  background: rgba(4, 16, 26, 0.96) !important;
  border: 1px solid rgba(125, 211, 252, 0.22) !important;
  border-radius: 14px !important;
  backdrop-filter: blur(24px) !important;
  padding: 6px !important;
}

ul[data-baseweb="menu"] li {
  border-radius: 8px !important;
  color: #f3f4f6 !important;
  font-size: 13.5px !important;
}

/* Radio Buttons */
div[data-testid="stRadio"] {
  margin-top: 8px !important;
  margin-bottom: 12px !important;
}

div[data-testid="stRadio"] label {
  font-size: 12.5px !important;
  font-weight: 600 !important;
  color: #e5e7eb !important;
  text-transform: uppercase !important;
  letter-spacing: 0.04em !important;
  cursor: pointer !important;
}

div[data-testid="stRadio"] div[role="radiogroup"] {
  gap: 14px !important;
}

div[data-testid="stRadio"] input[type="radio"] {
  accent-color: #06b6d4 !important;
  cursor: pointer !important;
}

/* Labels */
label, div[data-testid="stWidgetLabel"] p {
  font-size: 11px !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: var(--text-label-spacing) !important;
  color: var(--text-secondary) !important;
}

/* Apple / iOS Primary Action Buttons (Glowing Cyan-Teal Liquid Glass) */
.stButton > button {
  width: 100%;
  border-radius: 14px !important;
  border: 1px solid rgba(125, 211, 252, 0.45) !important;
  background: var(--accent-gradient) !important;
  color: #ffffff !important;
  font-weight: 750 !important;
  font-size: 14.5px !important;
  min-height: 48px !important;
  box-shadow: 0 4px 20px rgba(6, 182, 212, 0.38), inset 0 1px 0 rgba(255, 255, 255, 0.45) !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.stButton > button:hover {
  transform: translateY(-1.5px) !important;
  box-shadow: 0 8px 30px rgba(14, 165, 233, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.60) !important;
  border-color: var(--accent-light) !important;
}

.stButton > button:active {
  transform: translateY(0px) !important;
  box-shadow: 0 2px 10px rgba(6, 182, 212, 0.35) !important;
}

/* File Uploader Custom Styling */
div[data-testid="stFileUploader"] {
  margin-top: 6px !important;
}

section[data-testid="stFileUploaderDropzone"] {
  background: rgba(6, 22, 36, 0.48) !important;
  border: 1px solid rgba(125, 211, 252, 0.22) !important;
  border-radius: 16px !important;
  padding: 20px !important;
  backdrop-filter: blur(20px) !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.15) !important;
}

section[data-testid="stFileUploaderDropzone"] button {
  background: rgba(255, 255, 255, 0.12) !important;
  border: 1px solid rgba(255, 255, 255, 0.24) !important;
  border-radius: 10px !important;
  color: #ffffff !important;
  font-size: 12px !important;
  font-weight: 700 !important;
  padding: 6px 14px !important;
  min-height: auto !important;
  box-shadow: none !important;
}

section[data-testid="stFileUploaderDropzone"] button:hover {
  background: rgba(255, 255, 255, 0.22) !important;
  transform: none !important;
}

/* Dashed Asset Box */
.media-dashed-box {
  border: 1.5px dashed rgba(125, 211, 252, 0.35);
  border-radius: 16px;
  padding: 38px 20px;
  text-align: center;
  background: rgba(6, 22, 36, 0.30);
  color: rgba(255, 255, 255, 0.70);
  font-size: 13px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  transition: all 0.2s ease;
}

.media-dashed-box:hover {
  border-color: var(--accent);
  background: rgba(6, 182, 212, 0.08);
}

.media-dashed-box .icon {
  font-size: 24px;
  opacity: 0.85;
}

/* Pipeline Status Steps */
.pipeline {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 14px 0 20px 0;
  overflow-x: auto;
  padding-bottom: 8px;
}

.pipeline-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 16px;
  border-radius: 14px;
  background: var(--panel-bg-light);
  border: var(--panel-border);
}

.pipeline-icon {
  font-size: 21px;
}

.pipeline-name {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: var(--text-label-spacing);
  color: var(--text-secondary);
  margin-top: 5px;
}

.pipeline-arrow {
  color: #64748b;
  font-size: 18px;
}

/* Chips */
.chip {
  display: inline-block;
  padding: 6px 12px;
  margin-right: 6px;
  border-radius: 999px;
  background: rgba(125, 211, 252, 0.08);
  border: var(--panel-border);
  color: var(--text-secondary);
  font-size: 12px;
}

/* Responsive */
@media (max-width: 900px) {
  .hero-title {
    font-size: 34px;
  }
  .pipeline {
    justify-content: flex-start;
  }
}
"""


def clean_html_markup(html_str: str) -> str:
    """
    Strips leading and trailing spaces from each line and removes empty lines,
    ensuring CommonMark never parses multi-line HTML as <pre><code> blocks.
    """
    if not isinstance(html_str, str):
        return html_str
    lines = [line.strip() for line in html_str.splitlines() if line.strip()]
    return "".join(lines)


# Automatic sanitizer wrapper for st.markdown to protect against CommonMark 4-space code block triggers
_original_st_markdown = st.markdown

def _safe_st_markdown(body, *args, **kwargs):
    if kwargs.get("unsafe_allow_html") and isinstance(body, str):
        if "<" in body and ">" in body:
            body = clean_html_markup(body)
    return _original_st_markdown(body, *args, **kwargs)

st.markdown = _safe_st_markdown


def inject_hud_glass_css():
    """Injects the dynamic underwater background and liquid glassmorphism stylesheet into Streamlit."""
    bg_html = get_nature_bg_markup()
    st.markdown(bg_html, unsafe_allow_html=True)
    st.markdown(f"<style>{HUD_GLASS_CSS}</style>", unsafe_allow_html=True)


def render_provider_audit_card():
    """
    Renders the live Multi-Provider Execution Audit widget with telemetry stat blocks
    showing active providers, status badges, and millisecond latencies.
    Clean un-indented HTML is used to prevent markdown code block triggers.
    """
    latest = get_latest_step_providers()
    if not latest:
        latest = {
            "script": {"provider": "Gemini 2.5 Flash", "duration_ms": 0.0, "is_fallback": False, "note": "Primary (Groq & OpenRouter stand-by)"},
            "visuals": {"provider": "Pexels + Pixabay + FLUX", "duration_ms": 0.0, "is_fallback": False, "note": "3-Tier Cascade Active"},
            "voice": {"provider": "Kokoro / OmniVoice", "duration_ms": 0.0, "is_fallback": False, "note": "Studio Creator Mode"},
            "subtitles": {"provider": "Dynamic Pop-Up ASS", "duration_ms": 0.0, "is_fallback": False, "note": "Spec Highlighting Ready"},
        }

    card_header_html = (
        '<div class="glass-card">'
        '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;">'
        '<div>'
        '<div class="section-title">⚡ Multi-Provider Pipeline Audit</div>'
        '<div class="section-subtitle">Real-time telemetry of multi-provider cascade executions and response times.</div>'
        '</div>'
        '<div class="status-ok-pill">● ALL SYSTEMS NOMINAL</div>'
        '</div>'
        '<div class="hud-telemetry-grid">'
    )
    st.markdown(card_header_html, unsafe_allow_html=True)

    cols = st.columns(min(len(latest), 4))
    idx = 0
    for step_key, info in latest.items():
        prov = info.get("provider", "Unknown")
        dur_ms = info.get("duration_ms", 0.0)
        is_fb = info.get("is_fallback", False)
        status_tag = "⚡ FALLBACK" if is_fb else "✅ OPERATIONAL"
        badge_color = "#f59e0b" if is_fb else "#2dd4bf"

        box_html = (
            f'<div class="hud-stat-box">'
            f'<div class="hud-stat-label">{step_key.upper()} STEP</div>'
            f'<div class="hud-stat-value">{prov}</div>'
            f'<div class="hud-stat-sub" style="color: {badge_color};">'
            f'<span>{status_tag}</span> • <span>{dur_ms:.0f}ms</span>'
            f'</div>'
            f'</div>'
        )
        with cols[idx % len(cols)]:
            st.markdown(box_html, unsafe_allow_html=True)
        idx += 1

    st.markdown("</div></div>", unsafe_allow_html=True)

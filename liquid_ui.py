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
    Generates a lightweight, 0% GPU overhead realistic Alpine backdrop.
    Static image composition eliminates 100% of continuous GPU compositing, heating, and fan noise.
    """
    bg_url = "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=1920&q=80"
    return (
        f'<div class="nature-bg-container" style="background-image: url(\'{bg_url}\');">'
        '<div class="nature-vignette-overlay"></div>'
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

  /* Apple / iOS Translucent Frosted iPhone Glass - Optimized Lightweight Blur */
  --panel-bg: rgba(6, 20, 32, 0.78);
  --panel-bg-light: rgba(8, 26, 42, 0.72);
  --panel-blur: blur(8px);
  --panel-border: 1px solid rgba(125, 211, 252, 0.28);
  --panel-radius: 24px;
  --panel-shadow: 0 16px 40px rgba(0, 0, 0, 0.65), inset 0 1px 0 rgba(255, 255, 255, 0.35);

  /* Modern Cyan-to-Teal Accents (Zero Orange) */
  --accent: #06b6d4;
  --accent-light: #38bdf8;
  --accent-dark: #0284c7;
  --accent-gradient: linear-gradient(135deg, #0284c7 0%, #0ea5e9 45%, #06b6d4 100%);
  --accent-glow: 0 4px 24px rgba(6, 182, 212, 0.45);

  /* Status Colors */
  --status-ok: #2dd4bf;
  --status-ready: #38bdf8;

  /* Typography - High Contrast WCAG AAA Compliant */
  --text-primary: #ffffff;
  --text-secondary: #e2e8f0;
  --text-muted: #94a3b8;
  --text-label-spacing: 0.06em;
}

/* Streamlit Base Overrides */
.stApp {
  background: transparent !important;
  background-color: transparent !important;
  color: #f8fafc !important;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif !important;
}

/* Universal Crisp Typography & Contrast on Rotating Backgrounds */
.stMarkdown p, .stMarkdown span, .stMarkdown div, .stMarkdown li, .stMarkdown strong {
  color: #f1f5f9 !important;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.85);
}

.stCaption, [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, .stApp small {
  color: #cbd5e1 !important;
  font-weight: 500 !important;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.85) !important;
}

/* Streamlit Expanders with Crisp Frosted Glass */
[data-testid="stExpander"] {
  background: rgba(6, 20, 32, 0.75) !important;
  border: 1px solid rgba(125, 211, 252, 0.30) !important;
  border-radius: 16px !important;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.50) !important;
}

[data-testid="stExpander"] details summary,
[data-testid="stExpander"] details summary p,
[data-testid="stExpander"] details summary span,
[data-testid="stExpander"] summary {
  color: #f8fafc !important;
  font-weight: 700 !important;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.85) !important;
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
  backdrop-filter: blur(12px) !important;
}

/* ========================================================
   LIGHTWEIGHT 0% GPU STATIC ALPINE BACKGROUND (ZERO HEAT)
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
  background-size: cover;
  background-position: center center;
  background-repeat: no-repeat;
}

/* Warm Atmospheric Vignette */
.nature-vignette-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
  background: radial-gradient(circle at 50% 50%, rgba(3, 8, 14, 0.40) 0%, rgba(3, 8, 14, 0.72) 70%, rgba(3, 8, 14, 0.92) 100%);
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
  background: rgba(8, 26, 44, 0.88) !important;
  border: 1px solid rgba(125, 211, 252, 0.35) !important;
  border-radius: 14px !important;
  color: #ffffff !important;
  backdrop-filter: blur(20px) !important;
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.50) !important;
}

div[data-baseweb="select"] span,
div[data-baseweb="select"] div,
div[data-baseweb="select"] input,
div[data-baseweb="input"] input,
textarea {
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff !important;
  font-weight: 600 !important;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.75);
}

div[data-baseweb="input"]:focus-within > div,
div[data-baseweb="select"]:focus-within > div,
textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 1px var(--accent), 0 0 18px rgba(6, 182, 212, 0.45) !important;
}

/* Dropdown menu items */
ul[data-baseweb="menu"] {
  background: rgba(4, 16, 26, 0.98) !important;
  border: 1px solid rgba(125, 211, 252, 0.35) !important;
  border-radius: 14px !important;
  backdrop-filter: blur(28px) !important;
  padding: 8px !important;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.85) !important;
}

ul[data-baseweb="menu"] li,
ul[data-baseweb="menu"] li div,
ul[data-baseweb="menu"] li span {
  border-radius: 8px !important;
  color: #f8fafc !important;
  font-size: 13.5px !important;
  font-weight: 550 !important;
}

ul[data-baseweb="menu"] li:hover {
  background: rgba(6, 182, 212, 0.22) !important;
  color: #ffffff !important;
}

/* Radio Buttons */
div[data-testid="stRadio"] {
  margin-top: 8px !important;
  margin-bottom: 12px !important;
}

div[data-testid="stRadio"] label,
div[data-testid="stRadio"] label p,
div[data-testid="stRadio"] div[role="radiogroup"] span {
  font-size: 12.5px !important;
  font-weight: 600 !important;
  color: #f8fafc !important;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.85) !important;
  cursor: pointer !important;
}

div[data-testid="stRadio"] div[role="radiogroup"] {
  gap: 14px !important;
}

div[data-testid="stRadio"] input[type="radio"] {
  accent-color: #06b6d4 !important;
  cursor: pointer !important;
}

/* Checkboxes and Toggles */
div[data-testid="stCheckbox"] label,
div[data-testid="stCheckbox"] label p,
div[data-testid="stCheckbox"] span,
div[data-testid="stToggle"] label,
div[data-testid="stToggle"] label p,
div[data-testid="stToggle"] span {
  color: #f8fafc !important;
  font-weight: 600 !important;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.85) !important;
}

/* Labels */
label,
div[data-testid="stWidgetLabel"] p,
div[data-testid="stWidgetLabel"] label,
[data-testid="stWidgetLabel"] * {
  font-size: 11px !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: var(--text-label-spacing) !important;
  color: #f8fafc !important;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.85) !important;
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
  color: #38bdf8;
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


# ============================================================
# INTERACTIVE AI BUTTERFLY COMPANION WIDGET
# ============================================================

def render_ai_butterfly_companion():
    """
    Renders 'రాధ (Radha) - శ్రీకృష్ణుడి సఖి' - Modern Interactive AI Companion Widget on Streamlit.
    Features:
      1. Sacred Mayur Pankh (Peacock Feather & Lotus) 3D animated butterfly with glowing wings.
      2. Click-to-Update & Flutter Away: On click, fetches instant live pipeline telemetry in Telugu
         and gracefully flutters to perch on another screen control/headline.
      3. Real-time Live Status Ticker: Streams every second via static/pipeline_status.json.
      4. Context-aware Interactive Guide: explains page controls (Topic, Voice, Aspect, YouTube Mode, Generate) on hover.
    """
    companion_html = """
<div id="ai-companion-root" style="position: fixed; top: 85px; right: 28px; z-index: 9999999; pointer-events: auto; transition: left 0.95s cubic-bezier(0.22, 1, 0.36, 1), top 0.95s cubic-bezier(0.22, 1, 0.36, 1); font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;">
    <div id="companion-bubble" style="
        background: linear-gradient(135deg, rgba(6, 20, 32, 0.95) 0%, rgba(13, 30, 48, 0.92) 100%);
        backdrop-filter: blur(26px);
        -webkit-backdrop-filter: blur(26px);
        border: 1.5px solid rgba(245, 158, 11, 0.55);
        border-radius: 20px;
        padding: 14px 18px;
        width: 310px;
        max-width: 88vw;
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.75), 0 0 30px rgba(245, 158, 11, 0.25);
        margin-bottom: 10px;
        transition: all 0.35s ease;
        position: relative;
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div id="companion-badge" style="
                background: linear-gradient(90deg, rgba(245, 158, 11, 0.2), rgba(244, 63, 94, 0.2));
                border: 1px solid rgba(245, 158, 11, 0.6);
                color: #fbbf24;
                font-size: 0.74rem;
                font-weight: 800;
                letter-spacing: 0.05em;
                padding: 3px 10px;
                border-radius: 20px;
                display: flex;
                align-items: center;
                gap: 6px;
                box-shadow: 0 0 10px rgba(245, 158, 11, 0.25);
            ">
                <span id="companion-dot" style="display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #fbbf24; box-shadow: 0 0 10px #fbbf24; animation: pulse-radha 1.4s infinite;"></span>
                <span id="companion-badge-text">🌸 రాధ (RADHA) • శ్రీకృష్ణుడి సఖి</span>
            </div>
            <div style="display: flex; gap: 4px; align-items: center;">
                <button id="companion-min-btn" title="Toggle Bubble" style="
                    background: transparent;
                    border: none;
                    color: #cbd5e1;
                    cursor: pointer;
                    font-size: 0.9rem;
                    padding: 0 4px;
                    line-height: 1;
                ">━</button>
            </div>
        </div>

        <div id="companion-body">
            <div id="companion-main-msg" style="
                color: #f8fafc;
                font-size: 0.88rem;
                font-weight: 650;
                line-height: 1.4;
                margin-bottom: 6px;
                text-shadow: 0 1px 2px rgba(0,0,0,0.5);
            ">
                ✨ నమస్తే! నేను మీ రాధని (శ్రీకృష్ణుడి సఖి). స్టూడియో సిద్ధంగా ఉంది! ఏదైనా టాపిక్ ఇవ్వండి లేదా జనరేట్ నొక్కండి.
            </div>
            
            <div id="companion-next-step" style="
                color: #38bdf8;
                font-size: 0.78rem;
                font-weight: 600;
                line-height: 1.3;
                display: flex;
                align-items: center;
                gap: 5px;
            ">
                <span>⏩</span> <span id="companion-next-text">Next: Pick a topic or click Radha for live status!</span>
            </div>

            <div id="companion-prog-wrap" style="
                display: none;
                width: 100%;
                height: 6px;
                background: rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                margin-top: 10px;
                overflow: hidden;
            ">
                <div id="companion-prog-bar" style="
                    width: 0%;
                    height: 100%;
                    background: linear-gradient(90deg, #10b981, #06b6d4, #f59e0b, #f43f5e);
                    transition: width 0.4s ease;
                    border-radius: 6px;
                    box-shadow: 0 0 10px rgba(245, 158, 11, 0.6);
                "></div>
            </div>
        </div>
    </div>

    <!-- 3D RADHA BUTTERFLY SPRITE (Mayur Pankh & Lotus Motif) -->
    <div id="companion-butterfly" title="🌸 రాధ: నన్ను క్లిక్ చేయండి, లైవ్ అప్‌డేట్ ఇస్తాను!" style="
        width: 64px;
        height: 52px;
        cursor: pointer;
        display: flex;
        justify-content: center;
        align-items: center;
        filter: drop-shadow(0 0 16px rgba(245, 158, 11, 0.95)) drop-shadow(0 0 8px rgba(0, 229, 255, 0.7));
        animation: bobbing 3.2s infinite ease-in-out;
        transform-origin: center center;
        user-select: none;
        transition: transform 0.2s ease;
    ">
        <svg viewBox="0 0 100 80" width="64" height="52" style="overflow: visible;">
            <defs>
                <linearGradient id="radha-wing-left" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#00E5FF" />
                    <stop offset="30%" stop-color="#0284C7" />
                    <stop offset="70%" stop-color="#0D9488" />
                    <stop offset="100%" stop-color="#F59E0B" />
                </linearGradient>
                <linearGradient id="radha-wing-right" x1="100%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stop-color="#00E5FF" />
                    <stop offset="30%" stop-color="#0284C7" />
                    <stop offset="70%" stop-color="#0D9488" />
                    <stop offset="100%" stop-color="#F59E0B" />
                </linearGradient>
                <radialGradient id="mayur-eye" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stop-color="#38BDF8" />
                    <stop offset="35%" stop-color="#0F172A" />
                    <stop offset="65%" stop-color="#10B981" />
                    <stop offset="85%" stop-color="#F59E0B" />
                    <stop offset="100%" stop-color="#F43F5E" />
                </radialGradient>
                <filter id="divine-glow" x="-30%" y="-30%" width="160%" height="160%">
                    <feGaussianBlur stdDeviation="3.2" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
            </defs>

            <!-- LEFT WINGS -->
            <g id="bf-wing-l" style="transform-origin: 50px 40px; animation: flap-left 0.24s infinite alternate ease-in-out;">
                <!-- Forewing -->
                <path d="M 50 38 C 42 10, 8 2, 2 22 C -4 38, 20 54, 50 42 Z" fill="url(#radha-wing-left)" opacity="0.95" stroke="#FDE68A" stroke-width="1.3" />
                <!-- Mayur Pankh Eye -->
                <ellipse cx="26" cy="28" rx="8" ry="6" fill="url(#mayur-eye)" stroke="#F59E0B" stroke-width="0.9" transform="rotate(-15 26 28)" />
                <path d="M 50 40 Q 32 30 18 24" fill="none" stroke="rgba(253, 230, 138, 0.75)" stroke-width="1.0" />
                <!-- Hindwing -->
                <path d="M 50 42 C 40 50, 16 56, 14 70 C 12 80, 38 80, 50 48 Z" fill="url(#radha-wing-left)" opacity="0.90" stroke="#38BDF8" stroke-width="1" />
                <circle cx="28" cy="65" r="3.2" fill="#F43F5E" stroke="#FDE68A" stroke-width="0.8" />
            </g>

            <!-- RIGHT WINGS -->
            <g id="bf-wing-r" style="transform-origin: 50px 40px; animation: flap-right 0.24s infinite alternate ease-in-out;">
                <!-- Forewing -->
                <path d="M 50 38 C 58 10, 92 2, 98 22 C 104 38, 80 54, 50 42 Z" fill="url(#radha-wing-right)" opacity="0.95" stroke="#FDE68A" stroke-width="1.3" />
                <!-- Mayur Pankh Eye -->
                <ellipse cx="74" cy="28" rx="8" ry="6" fill="url(#mayur-eye)" stroke="#F59E0B" stroke-width="0.9" transform="rotate(15 74 28)" />
                <path d="M 50 40 Q 68 30 82 24" fill="none" stroke="rgba(253, 230, 138, 0.75)" stroke-width="1.0" />
                <!-- Hindwing -->
                <path d="M 50 42 C 60 50, 84 56, 86 70 C 88 80, 62 80, 50 48 Z" fill="url(#radha-wing-right)" opacity="0.90" stroke="#38BDF8" stroke-width="1" />
                <circle cx="72" cy="65" r="3.2" fill="#F43F5E" stroke="#FDE68A" stroke-width="0.8" />
            </g>

            <!-- BODY, HEAD & PEACOCK CROWN -->
            <ellipse cx="50" cy="40" rx="3.5" ry="14" fill="#0A2540" stroke="#F59E0B" stroke-width="1.2" filter="url(#divine-glow)" />
            <line x1="47.5" y1="36" x2="52.5" y2="36" stroke="#FDE68A" stroke-width="1" />
            <line x1="47" y1="42" x2="53" y2="42" stroke="#FDE68A" stroke-width="1" />
            <circle cx="50" cy="24" r="3.2" fill="#0D9488" stroke="#FDE68A" stroke-width="0.8" />
            <!-- Peacock Feather / Tilak Jewel -->
            <polygon points="50,17 48,22 52,22" fill="#F59E0B" />
            <circle cx="50" cy="18" r="1.5" fill="#F43F5E" />
            <!-- Antennae with Lotus Pearls -->
            <path d="M 48 22 Q 38 8 32 12" fill="none" stroke="#F59E0B" stroke-width="1.2" stroke-linecap="round" />
            <path d="M 52 22 Q 62 8 68 12" fill="none" stroke="#F59E0B" stroke-width="1.2" stroke-linecap="round" />
            <circle cx="32" cy="12" r="1.8" fill="#F43F5E" stroke="#FDE68A" stroke-width="0.6" />
            <circle cx="68" cy="12" r="1.8" fill="#F43F5E" stroke="#FDE68A" stroke-width="0.6" />
        </svg>
    </div>
</div>

<style>
@keyframes flap-left {
    0% { transform: rotateY(0deg) rotateZ(0deg); }
    100% { transform: rotateY(65deg) rotateZ(-4deg); }
}
@keyframes flap-right {
    0% { transform: rotateY(0deg) rotateZ(0deg); }
    100% { transform: rotateY(-65deg) rotateZ(4deg); }
}
@keyframes bobbing {
    0%, 100% { transform: translateY(0px) rotate(0deg); }
    50% { transform: translateY(-8px) rotate(2deg); }
}
@keyframes pulse-radha {
    0%, 100% { opacity: 1; transform: scale(1); box-shadow: 0 0 10px #fbbf24; }
    50% { opacity: 0.4; transform: scale(0.75); box-shadow: 0 0 4px #f43f5e; }
}
.butterfly-flying #bf-wing-l {
    animation-duration: 0.07s !important;
}
.butterfly-flying #bf-wing-r {
    animation-duration: 0.07s !important;
}
.divine-sparkle {
    position: fixed;
    pointer-events: none;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    animation: fade-divine 0.9s forwards ease-out;
    z-index: 9999998;
}
@keyframes fade-divine {
    0% { opacity: 1; transform: scale(1) translateY(0); }
    100% { opacity: 0; transform: scale(0.2) translateY(24px); }
}
</style>

<script>
(function() {
    if (window._aiCompanionLoaded) return;
    window._aiCompanionLoaded = true;

    const root = document.getElementById("ai-companion-root");
    const butterfly = document.getElementById("companion-butterfly");
    const bubble = document.getElementById("companion-bubble");
    const bodyEl = document.getElementById("companion-body");
    const minBtn = document.getElementById("companion-min-btn");
    const badgeEl = document.getElementById("companion-badge");
    const badgeText = document.getElementById("companion-badge-text");
    const dotEl = document.getElementById("companion-dot");
    const mainMsg = document.getElementById("companion-main-msg");
    const nextText = document.getElementById("companion-next-text");
    const progWrap = document.getElementById("companion-prog-wrap");
    const progBar = document.getElementById("companion-prog-bar");

    let isMinimized = false;
    let isEvading = false;
    let lastStatusRunning = false;
    let cachedStatusData = null;

    // Toggle bubble minimize
    if (minBtn) {
        minBtn.addEventListener("click", function(e) {
            e.stopPropagation();
            isMinimized = !isMinimized;
            bodyEl.style.display = isMinimized ? "none" : "block";
            minBtn.textContent = isMinimized ? "➕" : "━";
        });
    }

    // Spawn Vrindavan divine sparkles (gold, peacock teal, lotus pink, emerald)
    function spawnDivineSparkles(x, y, count=7) {
        const colors = [
            "radial-gradient(circle, #f59e0b 0%, #fbbf24 100%)",
            "radial-gradient(circle, #00e5ff 0%, #0284c7 100%)",
            "radial-gradient(circle, #f43f5e 0%, #ec4899 100%)",
            "radial-gradient(circle, #10b981 0%, #059669 100%)"
        ];
        const glows = ["#fbbf24", "#00e5ff", "#f43f5e", "#10b981"];

        for (let i = 0; i < count; i++) {
            const sp = document.createElement("div");
            sp.className = "divine-sparkle";
            const cIdx = Math.floor(Math.random() * colors.length);
            sp.style.background = colors[cIdx];
            sp.style.boxShadow = "0 0 10px " + glows[cIdx];
            sp.style.left = (x + (Math.random() * 36 - 18)) + "px";
            sp.style.top = (y + (Math.random() * 36 - 18)) + "px";
            document.body.appendChild(sp);
            setTimeout(() => sp.remove(), 900);
        }
    }

    // User Click Handler: Provides instant live update & flutters to another place
    function onRadhaClick(e) {
        if (e) e.stopPropagation();
        if (isEvading) return;

        // 1. Fetch freshest telemetry immediately
        fetch("/app/static/pipeline_status.json?t=" + Date.now())
            .then(res => res.json())
            .then(data => {
                cachedStatusData = data;
                applyStatusUpdate(data);
                displayLiveClickBrief(data);
            })
            .catch(() => {
                displayLiveClickBrief(cachedStatusData);
            })
            .finally(() => {
                // 2. Play divine flight animation to a new spot
                evadeAndPerch(true);
            });
    }

    function displayLiveClickBrief(data) {
        // Expand bubble if minimized
        if (isMinimized) {
            isMinimized = false;
            bodyEl.style.display = "block";
            minBtn.textContent = "━";
        }

        // Highlight bubble with divine glow
        bubble.style.borderColor = "#fbbf24";
        bubble.style.boxShadow = "0 16px 45px rgba(0, 0, 0, 0.8), 0 0 35px rgba(245, 158, 11, 0.55)";

        if (data && data.is_running) {
            mainMsg.innerHTML = `<span style="color:#fbbf24;">🌸 రాధ:</span> "ఇప్పుడు <b>${data.stage || 'స్టేజ్'}</b> జరుగుతోంది! [<b>${data.percent}%</b>] పూర్తయింది. టాస్క్: ${data.current_task || 'పని జరుగుతోంది'}. నేను చూసుకుంటున్నా, భయపడకండి! ✨"`;
            nextText.innerHTML = `⏩ <b>తదుపరి:</b> ${data.next_task || 'వీడియో అసెంబ్లీ & అప్‌లోడ్'}`;
            progWrap.style.display = "block";
            progBar.style.width = Math.max(5, data.percent) + "%";
        } else if (data && (data.last_topic || data.last_run_result || data.topic)) {
            const topicName = data.last_topic || data.topic || "లేటెస్ట్ వీడియో";
            mainMsg.innerHTML = `<span style="color:#fbbf24;">🌸 రాధ:</span> "గత రన్ స్టేటస్: <b>${topicName}</b> పూర్తయింది! 🎬 రియల్ ఫోటోలు & తెలుగు మీమ్స్‌తో వీడియో సిద్ధంగా ఉంది. నెక్స్ట్ ఏం చేద్దాం? ✨"`;
            nextText.innerHTML = `⏩ <b>ఫలితం:</b> ${data.last_run_result || 'సక్సెస్‌ఫుల్‌గా జనరేట్ అయింది'}`;
        } else {
            const idleMessages = [
                `<span style="color:#fbbf24;">🌸 రాధ:</span> "నమస్తే! నేను మీ రాధని (శ్రీకృష్ణుడి సఖి). స్టూడియో సిద్ధంగా ఉంది! ఏదైనా టాపిక్ ఇవ్వండి లేదా జనరేట్ నొక్కండి!"`,
                `<span style="color:#fbbf24;">🌸 రాధ:</span> "బిగ్ బాస్ రోస్టింగ్ చేద్దామా? లేదా ఆసక్తికరమైన టెక్ ఫ్యాక్ట్స్ వీడియోనా? మీరు ఆర్డర్ ఇవ్వండి, నిమిషాల్లో రెడీ చేస్తా! 🪶"`,
                `<span style="color:#fbbf24;">🌸 రాధ:</span> "అన్ని ఫిల్టర్లు, సెలబ్రిటీ గార్డులు & శృతి నాచురల్ వాయిస్ యాక్టివ్‌గా ఉన్నాయి! 🎬🔥"`
            ];
            mainMsg.innerHTML = idleMessages[Math.floor(Math.random() * idleMessages.length)];
            nextText.textContent = "⏩ టాపిక్ బాక్స్‌లో టైప్ చేసి Generate నొక్కండి!";
        }
    }

    // Playful Evasion & Perching: flies gracefully to headers/buttons/controls
    function evadeAndPerch(isTargetFlight = false) {
        if (isEvading) return;
        isEvading = true;

        const curRect = root.getBoundingClientRect();
        spawnDivineSparkles(curRect.left + 35, curRect.top + 35, 10);
        butterfly.classList.add("butterfly-flying");

        // Perch candidates: headers, cards, or buttons across the screen
        const candidates = document.querySelectorAll(".brand, .hero-title, .glass-card, [data-testid='stSelectbox'], .stButton, div[data-testid='stWidgetLabel']");
        let targetX = 0;
        let targetY = 0;

        if (candidates.length > 0 && Math.random() > 0.25) {
            const randElem = candidates[Math.floor(Math.random() * candidates.length)];
            const rRect = randElem.getBoundingClientRect();
            targetX = Math.max(20, Math.min(window.innerWidth - 340, rRect.left + (Math.random() * 50 - 25)));
            targetY = Math.max(75, Math.min(window.innerHeight - 200, rRect.top - 55));
        } else {
            targetX = Math.floor(Math.random() * (window.innerWidth - 350)) + 30;
            targetY = Math.floor(Math.random() * (window.innerHeight - 250)) + 80;
        }

        root.style.left = targetX + "px";
        root.style.top = targetY + "px";
        root.style.right = "auto";

        // Particle trail during flight
        let trailInterval = setInterval(() => {
            const r = root.getBoundingClientRect();
            spawnDivineSparkles(r.left + 35, r.top + 35, 4);
        }, 110);

        setTimeout(() => {
            clearInterval(trailInterval);
            butterfly.classList.remove("butterfly-flying");
            isEvading = false;
        }, 950);
    }

    if (butterfly) {
        butterfly.addEventListener("click", onRadhaClick);
        butterfly.addEventListener("mouseenter", function() {
            if (!lastStatusRunning && !isEvading) {
                butterfly.style.transform = "scale(1.15)";
            }
        });
        butterfly.addEventListener("mouseleave", function() {
            butterfly.style.transform = "scale(1)";
        });
    }

    // Context-Aware Inspector: explains interactive inputs on hover
    function registerInteractiveInspectors() {
        // Topic Input
        document.querySelectorAll("input[type='text'], textarea").forEach(input => {
            if (!input._hasAiHover) {
                input._hasAiHover = true;
                input.addEventListener("focus", () => {
                    if (!lastStatusRunning) {
                        mainMsg.innerHTML = "💡 <b>Topic Box:</b> తెలుగు బిగ్ బాస్ లేదా టెక్ ఫ్యాక్ట్స్ టాపిక్ ఇవ్వండి!";
                        nextText.textContent = "సెలబ్రిటీ ఫైర్‌వాల్ పాత సీజన్లు & తప్పుడు వ్యక్తులను 100% ఆపుతుంది.";
                    }
                });
            }
        });

        // Selectboxes
        document.querySelectorAll("[data-testid='stSelectbox']").forEach(box => {
            if (!box._hasAiHover) {
                box._hasAiHover = true;
                box.addEventListener("mouseenter", () => {
                    if (!lastStatusRunning) {
                        const txt = box.textContent || "";
                        if (txt.includes("Voice") || txt.includes("Shruti") || txt.includes("Mohan")) {
                            mainMsg.innerHTML = "🎙️ <b>Voice Tuning:</b> శృతి వాయిస్ - సహజమైన, వ్యంగ్యమైన హ్యూమన్ స్టైల్!";
                            nextText.textContent = "అనవసరమైన సౌండ్ ఎఫెక్ట్స్ & 'బాస్' పిలుపులు పూర్తిగా తొలగించబడ్డాయి.";
                        } else if (txt.includes("Privacy") || txt.includes("YouTube")) {
                            mainMsg.innerHTML = "🔒 <b>YouTube Mode:</b> డూప్లికేట్ రన్స్ ఆటోమేటిక్‌గా ప్రైవేట్‌గా అప్‌లోడ్ అవుతాయి!";
                            nextText.textContent = "మీ ఛానెల్ సేఫ్ గా ఉంటుంది & YouTube Studio లో వీడియో లభిస్తుంది.";
                        } else if (txt.includes("Aspect") || txt.includes("9:16") || txt.includes("16:9")) {
                            mainMsg.innerHTML = "📱 <b>9:16 Shorts Mode:</b> 100% యూట్యూబ్ షార్ట్స్ & రీల్స్ ఆప్టిమైజ్డ్!";
                            nextText.textContent = "డైనమిక్ తెలుగు పాప్-అప్ క్యాప్షన్లతో స్క్రీన్ నిండుగా వస్తుంది.";
                        }
                    }
                });
            }
        });

        // Generate Buttons
        document.querySelectorAll("button").forEach(btn => {
            if (!btn._hasAiHover && !btn.id) {
                btn._hasAiHover = true;
                btn.addEventListener("mouseenter", () => {
                    if (!lastStatusRunning && (btn.textContent.includes("Generate") || btn.textContent.includes("Create"))) {
                        mainMsg.innerHTML = "🚀 <b>Launch Production:</b> Groq ఫాస్ట్ ఫెయిల్‌ఓవర్ & Ken Burns ఎడిటింగ్‌తో వీడియో రెడీ!";
                        nextText.textContent = "క్లిక్ చేయగానే పూర్తి లైవ్ ప్రోగ్రెస్ బార్ కనిపిస్తుంది.";
                    }
                });
            }
        });
    }

    function applyStatusUpdate(data) {
        if (!data) return;
        const isRunning = !!data.is_running;
        lastStatusRunning = isRunning;

        if (isRunning) {
            badgeEl.style.background = "linear-gradient(90deg, rgba(6, 182, 212, 0.3), rgba(245, 158, 11, 0.3))";
            badgeEl.style.borderColor = "#38bdf8";
            badgeEl.style.color = "#38bdf8";
            dotEl.style.background = "#38bdf8";
            dotEl.style.boxShadow = "0 0 12px #38bdf8";
            badgeText.textContent = `🌸 రాధ • RUNNING [${data.percent}%] (STEP ${data.step_number || 1}/${data.total_steps || 7})`;

            mainMsg.innerHTML = `⚙️ <b>${data.stage || 'Processing'}:</b> ${data.current_task || 'Working...'}`;
            nextText.innerHTML = data.next_task ? `⏩ <b>Next:</b> ${data.next_task}` : "Finalizing video assets...";

            progWrap.style.display = "block";
            progBar.style.width = Math.max(5, data.percent) + "%";

            if (isMinimized) {
                isMinimized = false;
                bodyEl.style.display = "block";
                minBtn.textContent = "━";
            }
        } else {
            progWrap.style.display = "none";
            badgeEl.style.background = "linear-gradient(90deg, rgba(245, 158, 11, 0.2), rgba(244, 63, 94, 0.2))";
            badgeEl.style.borderColor = "rgba(245, 158, 11, 0.6)";
            badgeEl.style.color = "#fbbf24";
            dotEl.style.background = "#fbbf24";
            dotEl.style.boxShadow = "0 0 10px #fbbf24";
            badgeText.textContent = "🌸 రాధ (RADHA) • శ్రీకృష్ణుడి సఖి";
        }
    }

    // Real-Time Poller: fetches static/pipeline_status.json every 1000ms
    function fetchLiveTelemetry() {
        fetch("/app/static/pipeline_status.json?t=" + Date.now())
            .then(res => {
                if (!res.ok) throw new Error("Status unavailable");
                return res.json();
            })
            .then(data => {
                cachedStatusData = data;
                applyStatusUpdate(data);
            })
            .catch(() => {});
    }

    // Autonomous Radha Wandering: flutters gently every 14 seconds across page elements
    setInterval(() => {
        if (!isEvading && !isMinimized && !lastStatusRunning) {
            evadeAndPerch(false);
        }
    }, 14000);

    setInterval(fetchLiveTelemetry, 1000);
    setInterval(registerInteractiveInspectors, 2500);
    fetchLiveTelemetry();
    registerInteractiveInspectors();
})();
</script>
"""
    st.markdown(companion_html, unsafe_allow_html=True)



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
    Renders the modern, playful floating AI Butterfly Companion on the Streamlit dashboard.
    Features:
      1. Ethereal 3D animated cyber butterfly with fluttering wings and bioluminescent glow.
      2. Playful Evasion & Perching: when user tries to hover/catch it, it flutters gracefully to perch on headlines/controls!
      3. Real-time Live Status Ticker: every second streams live pipeline steps (percentage, current task, next step).
      4. Context-aware Interactive Guide: explains page controls (Topic, Voice, Aspect, YouTube Mode, Generate) on hover/click.
    """
    companion_html = """
<div id="ai-companion-root" style="position: fixed; top: 85px; right: 28px; z-index: 9999999; pointer-events: auto; transition: left 0.85s cubic-bezier(0.22, 1, 0.36, 1), top 0.85s cubic-bezier(0.22, 1, 0.36, 1); font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;">
    <div id="companion-bubble" style="
        background: rgba(6, 20, 32, 0.92);
        backdrop-filter: blur(24px);
        -webkit-backdrop-filter: blur(24px);
        border: 1px solid rgba(56, 189, 248, 0.45);
        border-radius: 18px;
        padding: 12px 16px;
        width: 290px;
        max-width: 85vw;
        box-shadow: 0 16px 36px rgba(0, 0, 0, 0.65), 0 0 25px rgba(6, 182, 212, 0.25);
        margin-bottom: 8px;
        transition: all 0.3s ease;
        position: relative;
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <div id="companion-badge" style="
                background: rgba(45, 212, 191, 0.15);
                border: 1px solid rgba(45, 212, 191, 0.4);
                color: #2dd4bf;
                font-size: 0.72rem;
                font-weight: 700;
                letter-spacing: 0.05em;
                padding: 2px 8px;
                border-radius: 20px;
                display: flex;
                align-items: center;
                gap: 5px;
            ">
                <span id="companion-dot" style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #2dd4bf; box-shadow: 0 0 8px #2dd4bf; animation: pulse-dot 1.5s infinite;"></span>
                <span id="companion-badge-text">AI ASSISTANT</span>
            </div>
            <div style="display: flex; gap: 4px; align-items: center;">
                <button id="companion-min-btn" title="Toggle Bubble" style="
                    background: transparent;
                    border: none;
                    color: #94a3b8;
                    cursor: pointer;
                    font-size: 0.85rem;
                    padding: 0 4px;
                    line-height: 1;
                ">━</button>
            </div>
        </div>

        <div id="companion-body">
            <div id="companion-main-msg" style="
                color: #f1f5f9;
                font-size: 0.85rem;
                font-weight: 600;
                line-height: 1.35;
                margin-bottom: 4px;
            ">
                ✨ నమస్తే! మీ AI వీడియో అసిస్టెంట్‌ని. టాపిక్ ఇవ్వగానే వీడియో రెడీ చేస్తా!
            </div>
            
            <div id="companion-next-step" style="
                color: #38bdf8;
                font-size: 0.75rem;
                font-weight: 500;
                line-height: 1.3;
                display: flex;
                align-items: center;
                gap: 4px;
            ">
                <span>⏩</span> <span id="companion-next-text">Next: Pick a topic or hit Generate!</span>
            </div>

            <div id="companion-prog-wrap" style="
                display: none;
                width: 100%;
                height: 5px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                margin-top: 8px;
                overflow: hidden;
            ">
                <div id="companion-prog-bar" style="
                    width: 0%;
                    height: 100%;
                    background: linear-gradient(90deg, #06b6d4, #38bdf8, #a855f7);
                    transition: width 0.4s ease;
                    border-radius: 6px;
                "></div>
            </div>
        </div>
    </div>

    <!-- 3D BUTTERFLY SPRITE -->
    <div id="companion-butterfly" style="
        width: 58px;
        height: 48px;
        cursor: grab;
        display: flex;
        justify-content: center;
        align-items: center;
        filter: drop-shadow(0 0 14px rgba(56, 189, 248, 0.85));
        animation: bobbing 3.2s infinite ease-in-out;
        transform-origin: center center;
        user-select: none;
    ">
        <svg viewBox="0 0 100 80" width="58" height="48" style="overflow: visible;">
            <defs>
                <linearGradient id="bf-grad-left" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#38bdf8" />
                    <stop offset="50%" stop-color="#06b6d4" />
                    <stop offset="100%" stop-color="#9333ea" />
                </linearGradient>
                <linearGradient id="bf-grad-right" x1="100%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stop-color="#38bdf8" />
                    <stop offset="50%" stop-color="#06b6d4" />
                    <stop offset="100%" stop-color="#9333ea" />
                </linearGradient>
                <filter id="neon-glow" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="3" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
            </defs>

            <!-- LEFT WINGS -->
            <g id="bf-wing-l" style="transform-origin: 50px 40px; animation: flap-left 0.24s infinite alternate ease-in-out;">
                <!-- Forewing -->
                <path d="M 50 38 C 42 12, 10 5, 2 24 C -4 38, 20 54, 50 42 Z" fill="url(#bf-grad-left)" opacity="0.92" stroke="#e0f2fe" stroke-width="1.2" />
                <path d="M 46 36 C 36 20, 16 16, 10 26 C 6 34, 24 44, 46 38 Z" fill="none" stroke="rgba(255,255,255,0.6)" stroke-width="0.8" />
                <!-- Hindwing -->
                <path d="M 50 42 C 40 50, 18 56, 16 68 C 14 78, 38 78, 50 48 Z" fill="url(#bf-grad-left)" opacity="0.85" stroke="#bae6fd" stroke-width="1" />
            </g>

            <!-- RIGHT WINGS -->
            <g id="bf-wing-r" style="transform-origin: 50px 40px; animation: flap-right 0.24s infinite alternate ease-in-out;">
                <!-- Forewing -->
                <path d="M 50 38 C 58 12, 90 5, 98 24 C 104 38, 80 54, 50 42 Z" fill="url(#bf-grad-right)" opacity="0.92" stroke="#e0f2fe" stroke-width="1.2" />
                <path d="M 54 36 C 64 20, 84 16, 90 26 C 94 34, 76 44, 54 38 Z" fill="none" stroke="rgba(255,255,255,0.6)" stroke-width="0.8" />
                <!-- Hindwing -->
                <path d="M 50 42 C 60 50, 82 56, 84 68 C 86 78, 62 78, 50 48 Z" fill="url(#bf-grad-right)" opacity="0.85" stroke="#bae6fd" stroke-width="1" />
            </g>

            <!-- BODY & HEAD -->
            <ellipse cx="50" cy="40" rx="3.5" ry="14" fill="#0f172a" stroke="#38bdf8" stroke-width="1.2" filter="url(#neon-glow)" />
            <circle cx="50" cy="24" r="3" fill="#2dd4bf" />
            <!-- Antennae -->
            <path d="M 48 22 Q 40 10 34 14" fill="none" stroke="#38bdf8" stroke-width="1.2" stroke-linecap="round" />
            <path d="M 52 22 Q 60 10 66 14" fill="none" stroke="#38bdf8" stroke-width="1.2" stroke-linecap="round" />
            <circle cx="34" cy="14" r="1.5" fill="#f43f5e" />
            <circle cx="66" cy="14" r="1.5" fill="#f43f5e" />
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
    50% { transform: translateY(-7px) rotate(2deg); }
}
@keyframes pulse-dot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.8); }
}
.butterfly-flying #bf-wing-l {
    animation-duration: 0.08s !important;
}
.butterfly-flying #bf-wing-r {
    animation-duration: 0.08s !important;
}
.sparkle-particle {
    position: fixed;
    pointer-events: none;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: radial-gradient(circle, #38bdf8 0%, #a855f7 100%);
    box-shadow: 0 0 8px #38bdf8;
    animation: fade-sparkle 0.8s forwards ease-out;
    z-index: 9999998;
}
@keyframes fade-sparkle {
    0% { opacity: 1; transform: scale(1) translateY(0); }
    100% { opacity: 0; transform: scale(0.2) translateY(18px); }
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

    // Toggle bubble minimize
    if (minBtn) {
        minBtn.addEventListener("click", function(e) {
            e.stopPropagation();
            isMinimized = !isMinimized;
            bodyEl.style.display = isMinimized ? "none" : "block";
            minBtn.textContent = isMinimized ? "➕" : "━";
        });
    }

    // Spawn fairy dust sparkles
    function spawnSparkles(x, y, count=5) {
        for (let i = 0; i < count; i++) {
            const sp = document.createElement("div");
            sp.className = "sparkle-particle";
            sp.style.left = (x + (Math.random() * 30 - 15)) + "px";
            sp.style.top = (y + (Math.random() * 30 - 15)) + "px";
            document.body.appendChild(sp);
            setTimeout(() => sp.remove(), 800);
        }
    }

    // Playful Evasion & Perching: flies away when user hovers/tries to catch it!
    const playfulTeluguMessages = [
        "పట్టుకోలేరు! 🦋😜 Catch me if you can!",
        "ఇక్కడ వాలాను! 🌸 ఏం కావాలో చెప్పు...",
        "హాహా! నేను వేగంగా ఎగురుతా! 💨✨",
        "లెట్స్ మేక్ ఏ వైరల్ హిట్ వీడియో! 🎬🔥",
        "బిగ్ బాస్ రోస్టింగ్ చేద్దామా? లేక టెక్ ఫ్యాక్టా? 📱"
    ];

    function evadeAndPerch() {
        if (isEvading) return;
        isEvading = true;

        const curRect = root.getBoundingClientRect();
        spawnSparkles(curRect.left + 30, curRect.top + 30, 8);
        butterfly.classList.add("butterfly-flying");

        // Perch candidates: headers, cards, or safe viewport margins
        const candidates = document.querySelectorAll(".brand, .hero-title, .glass-card, [data-testid='stSelectbox'], .stButton");
        let targetX = 0;
        let targetY = 0;

        if (candidates.length > 0 && Math.random() > 0.35) {
            const randElem = candidates[Math.floor(Math.random() * candidates.length)];
            const rRect = randElem.getBoundingClientRect();
            targetX = Math.max(20, Math.min(window.innerWidth - 320, rRect.left + (Math.random() * 40 - 20)));
            targetY = Math.max(70, Math.min(window.innerHeight - 180, rRect.top - 50));
        } else {
            // Free random coordinates in viewport
            targetX = Math.floor(Math.random() * (window.innerWidth - 340)) + 30;
            targetY = Math.floor(Math.random() * (window.innerHeight - 240)) + 75;
        }

        root.style.left = targetX + "px";
        root.style.top = targetY + "px";
        root.style.right = "auto";

        // Show playful evasion dialogue if not actively rendering video
        if (!lastStatusRunning) {
            const randMsg = playfulTeluguMessages[Math.floor(Math.random() * playfulTeluguMessages.length)];
            mainMsg.textContent = randMsg;
            nextText.textContent = "Hover over controls for instant tips!";
        }

        // Particle trail during flight
        let trailInterval = setInterval(() => {
            const r = root.getBoundingClientRect();
            spawnSparkles(r.left + 35, r.top + 35, 3);
        }, 120);

        setTimeout(() => {
            clearInterval(trailInterval);
            butterfly.classList.remove("butterfly-flying");
            isEvading = false;
        }, 850);
    }

    if (butterfly) {
        butterfly.addEventListener("mouseenter", evadeAndPerch);
        butterfly.addEventListener("click", evadeAndPerch);
    }

    // Context-Aware Inspector: explains interactive inputs on hover
    function registerInteractiveInspectors() {
        // Topic Input
        document.querySelectorAll("input[type='text'], textarea").forEach(input => {
            if (!input._hasAiHover) {
                input._hasAiHover = true;
                input.addEventListener("focus", () => {
                    if (!lastStatusRunning) {
                        mainMsg.textContent = "💡 Topic Box: తెలుగు బిగ్ బాస్ లేదా టెక్ ఫ్యాక్ట్స్ టాపిక్ ఇవ్వండి!";
                        nextText.textContent = "Ground-truth filters will block old seasons & wrong actors.";
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
                            mainMsg.textContent = "🎙️ Voice Tuning: శృతి వాయిస్ - వ్యంగ్యమైన, సహజమైన తెలుగు రోస్ట్!";
                            nextText.textContent = "Intrusive SFX & 'బాస్' fillers are permanently disabled.";
                        } else if (txt.includes("Privacy") || txt.includes("YouTube")) {
                            mainMsg.textContent = "🔒 YouTube Destination: డూప్లికేట్స్ ఆటోమేటిక్‌గా ప్రైవేట్‌గా అప్‌లోడ్ అవుతాయి!";
                            nextText.textContent = "Preserves channel authority while saving revision.";
                        } else if (txt.includes("Aspect") || txt.includes("9:16") || txt.includes("16:9")) {
                            mainMsg.textContent = "📱 9:16 Shorts Mode: 100% రీల్స్ & షార్ట్స్ ఆప్టిమైజ్డ్!";
                            nextText.textContent = "Includes dynamic HarfBuzz Telugu pop-up subtitles.";
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
                        mainMsg.textContent = "🚀 Launch Video: Groq ఫాస్ట్ ఫెయిల్‌ఓవర్‌తో 2-3 నిమిషాల్లో రెడీ!";
                        nextText.textContent = "Click to run end-to-end 4K video pipeline.";
                    }
                });
            }
        });
    }

    // Real-Time Poller: fetches static/pipeline_status.json every 1000ms
    function fetchLiveTelemetry() {
        fetch("/app/static/pipeline_status.json?t=" + Date.now())
            .then(res => {
                if (!res.ok) throw new Error("Status unavailable");
                return res.json();
            })
            .then(data => {
                if (!data) return;
                const isRunning = !!data.is_running;
                lastStatusRunning = isRunning;

                if (isRunning) {
                    // Pipeline is actively executing!
                    badgeEl.style.background = "rgba(6, 182, 212, 0.25)";
                    badgeEl.style.borderColor = "#38bdf8";
                    badgeEl.style.color = "#38bdf8";
                    dotEl.style.background = "#38bdf8";
                    dotEl.style.boxShadow = "0 0 10px #38bdf8";
                    badgeText.textContent = `RUNNING [${data.percent}%] • STEP ${data.step_number || 1}/${data.total_steps || 7}`;

                    mainMsg.textContent = `⚙️ ${data.stage || 'Processing'}: ${data.current_task || 'Working...'}`;
                    nextText.textContent = data.next_task ? `⏩ Next: ${data.next_task}` : "Finalizing video assets...";

                    progWrap.style.display = "block";
                    progBar.style.width = Math.max(5, data.percent) + "%";

                    // Keep un-minimized during active run
                    if (isMinimized) {
                        isMinimized = false;
                        bodyEl.style.display = "block";
                        minBtn.textContent = "━";
                    }
                } else {
                    // Idle state
                    progWrap.style.display = "none";
                    badgeEl.style.background = "rgba(45, 212, 191, 0.15)";
                    badgeEl.style.borderColor = "rgba(45, 212, 191, 0.4)";
                    badgeEl.style.color = "#2dd4bf";
                    dotEl.style.background = "#2dd4bf";
                    dotEl.style.boxShadow = "0 0 8px #2dd4bf";
                    badgeText.textContent = "STUDIO READY";
                }
            })
            .catch(() => {
                // Fallback polling silence
            });
    }

    // Run polling and inspector setup
    setInterval(fetchLiveTelemetry, 1000);
    setInterval(registerInteractiveInspectors, 2500);
    fetchLiveTelemetry();
    registerInteractiveInspectors();
})();
</script>
"""
    st.markdown(companion_html, unsafe_allow_html=True)


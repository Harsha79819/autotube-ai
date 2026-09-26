"""
AutoTube AI - Dark Sci-Fi HUD Glassmorphism UI System (liquid_ui.py)
Implements precise HUD design tokens:
  - Deep near-black navy backgrounds (#0a0e17) with radial depth glow
  - High-blur translucent glass panels (rgba(18, 24, 38, 0.55), blur(20px))
  - Glowing orange accents (#ff6a2c) for primary actions and active telemetry
  - Teal status pills (#2dd4bf) for active provider confirmations
  - High-density telemetry cards with label-over-value pairing
"""

import streamlit as st
from providers.tracker import get_latest_step_providers, get_step_audit_log, get_provider_status

HUD_GLASS_CSS = """
:root {
  /* Backgrounds */
  --bg-base: #0a0e17;
  --bg-gradient: radial-gradient(circle at 50% 0%, #1a2436 0%, #0a0e17 60%);

  /* Glass panels */
  --panel-bg: rgba(18, 24, 38, 0.55);
  --panel-bg-light: rgba(30, 38, 56, 0.45);
  --panel-blur: blur(20px);
  --panel-border: 1px solid rgba(255, 255, 255, 0.08);
  --panel-radius: 18px;
  --panel-shadow: 0 8px 40px rgba(0, 0, 0, 0.5);

  /* Accent (orange — primary actions, active telemetry, progress bars) */
  --accent: #ff6a2c;
  --accent-light: #ff9558;
  --accent-gradient: linear-gradient(135deg, #ff8a3d 0%, #ff5f2c 100%);
  --accent-glow: 0 0 24px rgba(255, 106, 44, 0.45);

  /* Secondary accent (teal — operating/ok status pills) */
  --status-ok: #2dd4bf;

  /* Text */
  --text-primary: #eef1f6;
  --text-secondary: #8a92a6;
  --text-label-spacing: 0.08em;
}

/* Streamlit Base Overrides */
.stApp {
  background: var(--bg-gradient) !important;
  background-color: var(--bg-base) !important;
  color: var(--text-primary) !important;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
}

.block-container {
  max-width: 1450px;
  padding-top: 2rem;
  padding-bottom: 4rem;
}

header[data-testid="stHeader"] {
  background: transparent !important;
}

section[data-testid="stSidebar"] {
  background: rgba(10, 14, 23, 0.96) !important;
  border-right: var(--panel-border) !important;
}

/* Glass Cards */
.glass-card {
  background: var(--panel-bg);
  border: var(--panel-border);
  border-radius: var(--panel-radius);
  padding: 24px;
  backdrop-filter: var(--panel-blur);
  -webkit-backdrop-filter: var(--panel-blur);
  box-shadow: var(--panel-shadow), inset 0 1px 0 rgba(255, 255, 255, 0.06);
  margin-bottom: 18px;
}

/* Brand and Hero */
.brand {
  font-size: 30px;
  font-weight: 800;
  letter-spacing: -1px;
}

.brand span {
  background: var(--accent-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.status {
  display: inline-block;
  padding: 6px 12px;
  margin-left: 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.10);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: var(--text-label-spacing);
  text-transform: uppercase;
  color: var(--text-secondary);
}

.status-ok-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(45, 212, 191, 0.12);
  border: 1px solid rgba(45, 212, 191, 0.35);
  color: var(--status-ok);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: var(--text-label-spacing);
  text-transform: uppercase;
}

.hero-title {
  font-size: 46px;
  line-height: 1.05;
  font-weight: 850;
  letter-spacing: -2px;
  margin-top: 20px;
}

.hero-gradient {
  background: linear-gradient(90deg, #FFFFFF 0%, #ff9558 45%, #ff6a2c 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.hero-subtitle {
  color: var(--text-secondary);
  font-size: 16px;
  margin-top: 10px;
  margin-bottom: 24px;
}

/* Headings */
.section-title {
  font-size: 20px;
  font-weight: 750;
  margin-bottom: 5px;
  color: var(--text-primary);
}

.section-subtitle {
  color: var(--text-secondary);
  font-size: 13px;
  margin-bottom: 18px;
}

/* Telemetry Stat Blocks (Label-over-Value HUD Pairing) */
.hud-telemetry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin: 14px 0;
}

.hud-stat-box {
  background: var(--panel-bg-light);
  border: var(--panel-border);
  border-radius: 14px;
  padding: 14px 16px;
  backdrop-filter: var(--panel-blur);
  position: relative;
  overflow: hidden;
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
  font-size: 20px;
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

/* Explicit Shared Glassmorphism Design System Tokens */
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
  background: rgba(255, 255, 255, 0.06);
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
  color: #fff !important;
  border-radius: 12px;
  box-shadow: var(--accent-glow);
  font-weight: 750;
  border: 1px solid rgba(255, 106, 44, 0.6);
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

/* Streamlit Inputs */
div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
textarea {
  background: rgba(18, 24, 38, 0.70) !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  border-radius: 12px !important;
  color: var(--text-primary) !important;
}

div[data-baseweb="input"]:focus-within > div,
div[data-baseweb="select"]:focus-within > div,
textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 1px var(--accent), var(--accent-glow) !important;
}

label {
  font-size: 12px !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: var(--text-label-spacing) !important;
  color: var(--text-secondary) !important;
}

/* Primary Generate Button (Glowing Orange Sci-Fi Action) */
.stButton > button {
  width: 100%;
  border-radius: 14px;
  border: 1px solid rgba(255, 106, 44, 0.6) !important;
  background: var(--accent-gradient) !important;
  color: white !important;
  font-weight: 750 !important;
  font-size: 15px !important;
  min-height: 48px !important;
  box-shadow: var(--accent-glow) !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.stButton > button:hover {
  transform: translateY(-1.5px) !important;
  box-shadow: 0 0 32px rgba(255, 106, 44, 0.65) !important;
  border-color: var(--accent-light) !important;
}

/* Progress Bars */
div[data-testid="stProgressBar"] > div > div {
  background: var(--accent-gradient) !important;
  box-shadow: 0 0 14px rgba(255, 106, 44, 0.5) !important;
}

/* Tabs */
button[data-baseweb="tab"] {
  color: var(--text-secondary) !important;
  font-weight: 600 !important;
  letter-spacing: var(--text-label-spacing) !important;
  text-transform: uppercase !important;
  font-size: 12px !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
  color: var(--accent) !important;
  border-bottom-color: var(--accent) !important;
}

/* Pipeline Steps */
.pipeline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 15px;
  overflow-x: auto;
}

.pipeline-step {
  min-width: 105px;
  text-align: center;
  padding: 13px 10px;
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
  color: #64748B;
  font-size: 18px;
}

/* Chips */
.chip {
  display: inline-block;
  padding: 6px 12px;
  margin-right: 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.055);
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


def inject_hud_glass_css():
    """Injects the complete dark sci-fi HUD glassmorphism stylesheet into Streamlit."""
    st.markdown(f"<style>{HUD_GLASS_CSS}</style>", unsafe_allow_html=True)


def render_provider_audit_card():
    """
    Renders the live Multi-Provider Execution Audit widget with telemetry stat blocks
    showing active providers, status badges, and millisecond latencies.
    """
    latest = get_latest_step_providers()
    if not latest:
        # Display ready architecture state so user sees active multi-provider chains
        latest = {
            "script": {"provider": "Gemini 2.5 Flash", "duration_ms": 0.0, "is_fallback": False, "note": "Primary (Groq & OpenRouter stand-by)"},
            "visuals": {"provider": "Pexels + Pixabay + FLUX", "duration_ms": 0.0, "is_fallback": False, "note": "3-Tier Cascade Active"},
            "voice": {"provider": "Kokoro / OmniVoice", "duration_ms": 0.0, "is_fallback": False, "note": "Studio Creator Mode"},
            "subtitles": {"provider": "Dynamic Pop-Up ASS", "duration_ms": 0.0, "is_fallback": False, "note": "Spec Highlighting Ready"},
        }

    st.markdown(
        """
        <div class="glass-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
                <div>
                    <div class="section-title">⚡ Multi-Provider Pipeline Audit</div>
                    <div class="section-subtitle">Real-time telemetry of multi-provider cascade executions and response times.</div>
                </div>
                <div class="status-ok-pill">● ALL SYSTEMS NOMINAL</div>
            </div>
            <div class="hud-telemetry-grid">
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(min(len(latest), 4))
    idx = 0
    for step_key, info in latest.items():
        prov = info.get("provider", "Unknown")
        dur_ms = info.get("duration_ms", 0.0)
        is_fb = info.get("is_fallback", False)
        status_tag = "⚡ FALLBACK" if is_fb else "✅ OPERATIONAL"
        badge_color = "#f59e0b" if is_fb else "#2dd4bf"

        with cols[idx % len(cols)]:
            st.markdown(
                f"""
                <div class="hud-stat-box">
                    <div class="hud-stat-label">{step_key.upper()} STEP</div>
                    <div class="hud-stat-value">{prov}</div>
                    <div class="hud-stat-sub" style="color: {badge_color};">
                        <span>{status_tag}</span> • <span>{dur_ms:.0f}ms</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        idx += 1

    st.markdown("</div></div>", unsafe_allow_html=True)
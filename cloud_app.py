"""
AutoTube AI - 24/7 Cloud Mobile Control Center (cloud_app.py)
A lightweight, mobile-first Streamlit web dashboard designed to run 24/7 on
Streamlit Community Cloud (share.streamlit.io).

Allows user to:
- Browse live, real-time trending Telugu topics (Bigg Boss, Tollywood, Tech, News).
- Enter ANY custom video topic on demand.
- Select channel (Channel 1 or Channel 2) and format (Shorts 60-90s vs Long 3-8m).
- Dispatch production runs directly to GitHub Actions high-speed cloud runners.
- Monitor live production progress and view published YouTube & Instagram videos.
- 100% cloud-hosted: Works permanently from any smartphone with laptop completely off!
"""

from __future__ import annotations
import os
import json
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Tuple, List, Dict, Optional, Any
import streamlit as st

# ============================================================
# APP CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="AutoTube AI — Cloud Dashboard",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

def _safe_get_secret(key: str, default: str = "") -> str:
    """Safely retrieves a configuration key without raising StreamlitSecretNotFoundError."""
    try:
        val = st.secrets.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    except Exception:
        pass
    env_val = os.environ.get(key) or os.environ.get(f"APP_{key}") or os.environ.get(f"GITHUB_{key}")
    if env_val and str(env_val).strip():
        return str(env_val).strip()
    return default

DEFAULT_GITHUB_REPO = "Harsha79819/autotube-ai"
DEFAULT_PIN = "9989"

GH_REPO = _safe_get_secret("GH_REPO", DEFAULT_GITHUB_REPO)
APP_PIN = _safe_get_secret("APP_PIN", DEFAULT_PIN)

WORKFLOW_FILE = "daily_publisher.yml"

# ============================================================
# CUSTOM MOBILE CSS
# ============================================================

st.markdown(
    """
    <style>
    /* Dark Modern Streamlit UI */
    .stApp {
        background-color: #0b0f19;
        color: #f1f5f9;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    .header-card {
        background: linear-gradient(135deg, #1e1b4b 0%, #31104b 100%);
        border: 1px solid #4338ca;
        padding: 20px;
        border-radius: 16px;
        margin-bottom: 20px;
        text-align: center;
    }
    .topic-chip {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 12px 16px;
        margin-bottom: 10px;
        font-size: 0.95rem;
    }
    .status-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 8px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .badge-success { background-color: #065f46; color: #34d399; }
    .badge-progress { background-color: #1e3a8a; color: #60a5fa; }
    .badge-pending { background-color: #374151; color: #9ca3af; }
    .badge-failed { background-color: #7f1d1d; color: #f87171; }
    
    /* Touch target buttons (>= 48px) */
    .stButton > button {
        border-radius: 12px !important;
        min-height: 48px !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# AUTHENTICATION
# ============================================================

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown(
        """
        <div class="header-card">
            <h2>🎬 AutoTube AI Mobile</h2>
            <p style="color: #94a3b8;">24/7 Cloud Automation Dashboard</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pin_input = st.text_input("🔑 Enter Security PIN", type="password", max_chars=6)
        if st.button("Unlock Dashboard", use_container_width=True):
            if pin_input.strip() == APP_PIN:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Incorrect PIN. Please try again.")
    st.stop()

# ============================================================
# TOKEN RESOLUTION
# ============================================================

if "user_token" not in st.session_state:
    st.session_state.user_token = _safe_get_secret("GH_TOKEN", "") or _safe_get_secret("GITHUB_TOKEN", "")

active_token = st.session_state.user_token

if not active_token:
    st.warning("🔑 GitHub Access Token Required")
    with st.expander("Setup Token (One-time)", expanded=True):
        st.write("Please paste your GitHub Token below to connect to cloud runners:")
        token_input = st.text_input("GitHub Personal Access Token (starts with gho_ or ghp_)", type="password")
        if st.button("Save Token", use_container_width=True):
            if token_input.strip():
                st.session_state.user_token = token_input.strip()
                st.success("✅ Token saved!")
                st.rerun()
    st.stop()

# ============================================================
# GITHUB ACTIONS API HELPERS
# ============================================================

def get_headers():
    return {
        "Authorization": f"token {st.session_state.user_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AutoTube-Cloud-App",
    }

def trigger_workflow(custom_topic: str = "", custom_channel: str = "viral_talks_me&mine", custom_duration: str = "60-90s", slot_id: str = "RUN_ALL_PENDING") -> Tuple[bool, str]:
    url = f"https://api.github.com/repos/{GH_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    payload = {
        "ref": "main",
        "inputs": {
            "custom_topic": custom_topic.strip(),
            "custom_channel": custom_channel,
            "custom_duration": custom_duration,
            "slot_id": slot_id,
            "force": True,
        },
    }
    try:
        r = requests.post(url, json=payload, headers=get_headers(), timeout=12)
        if r.status_code in (200, 204):
            return True, "Workflow dispatched successfully!"
        return False, f"GitHub API error: {r.status_code} - {r.text}"
    except Exception as e:
        return False, str(e)

def get_recent_runs(limit: int = 5) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/repos/{GH_REPO}/actions/runs?per_page={limit}"
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        if r.status_code == 200:
            return r.json().get("workflow_runs", [])
    except Exception:
        pass
    return []

# ============================================================
# LIVE REAL-TIME TELUGU NEWS FETCHER
# ============================================================

NEWS_FEEDS = {
    "🔥 Bigg Boss Telugu 10": "https://news.google.com/rss/search?q=Bigg+Boss+Telugu+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
    "🎬 Tollywood & Cinema": "https://news.google.com/rss/search?q=Tollywood+Telugu+cinema+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
    "⚡ Tech & AI Innovations": "https://news.google.com/rss/search?q=AI+technology+breakthrough+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
    "📰 Breaking News (Telugu)": "https://news.google.com/rss/search?q=Telugu+news+when:1d&hl=te&gl=IN&ceid=IN:te",
}

@st.cache_data(ttl=900)
def fetch_live_news_topics(feed_url: str) -> list:
    items = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(feed_url, headers=headers, timeout=8)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:10]:
                title = item.find("title").text if item.find("title") is not None else ""
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0].strip()
                if len(title) > 15:
                    items.append(title)
    except Exception:
        pass
    return items

# ============================================================
# HEADER & SYSTEM STATUS
# ============================================================

st.markdown(
    """
    <div class="header-card">
        <h1 style="margin: 0; font-size: 1.8rem;">🎬 AutoTube AI Mobile Studio</h1>
        <p style="margin: 5px 0 0 0; color: #a5b4fc; font-size: 0.95rem;">
            ☁️ 24/7 Cloud Automated Video Production & Publisher
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_create, tab_live, tab_schedule, tab_quota = st.tabs([
    "🚀 Create Video",
    "📡 Live Production",
    "⏰ 10 Daily Slots",
    "📊 Quota & Usage"
])

# ============================================================
# TAB 1: CREATE VIDEO ON DEMAND
# ============================================================

with tab_create:
    st.subheader("🎯 On-Demand Video Creation")
    
    if "selected_topic" not in st.session_state:
        st.session_state.selected_topic = ""

    st.markdown("#### 🔥 Real-Time Trending News (Past 24h)")
    news_cat = st.selectbox("Category", list(NEWS_FEEDS.keys()))
    headlines = fetch_live_news_topics(NEWS_FEEDS[news_cat])

    if headlines:
        for idx, h in enumerate(headlines[:4]):
            col_t, col_b = st.columns([4, 1])
            with col_t:
                st.markdown(f"<div class='topic-chip'>📌 {h}</div>", unsafe_allow_html=True)
            with col_b:
                if st.button("Use Topic", key=f"btn_h_{idx}", use_container_width=True):
                    st.session_state.selected_topic = h
                    st.rerun()
    else:
        st.info("Searching live Google News feeds...")

    st.markdown("---")
    st.markdown("#### ✍️ Custom Topic Input")
    
    custom_topic = st.text_area(
        "Enter Video Topic / Headline",
        value=st.session_state.selected_topic,
        placeholder="e.g. Mukesh vs Thrigun Violent Clash in Bigg Boss 10 Over Dirty Mind Comment",
        help="Type any topic in English or Telugu",
        height=80,
    )

    col_ch, col_dur = st.columns(2)
    with col_ch:
        ch_display = st.selectbox(
            "Target YouTube Channel",
            options=[
                "Channel 2 — Viral Talks (Bigg Boss, Roast, Comedy)",
                "Channel 1 — Imaginary Facts (News, Tech, Mysteries)",
            ],
            help="Channel 2: Energetic Voice + Memes; Channel 1: Clean News Anchor Voice",
        )
        target_channel = "viral_talks_me&mine" if "Channel 2" in ch_display else "Imaginary_facts"

    with col_dur:
        dur_display = st.selectbox(
            "Video Format & Visual Engine",
            options=[
                "📱 Shorts (9:16) [60-90s] — Creator Canvas, Captions OFF (Clean Screen)",
                "📺 Long-form (16:9) [3-5m] — Cinematic Documentary, Chapter Slates, Captions ON (No Canva Cards)",
                "📺 Long-form (16:9) [5-8m] — Cinematic Documentary, Chapter Slates, Captions ON (No Canva Cards)",
            ],
            help="Shorts: Creator Canvas with clean screen; Long-form: 100% widescreen HD documentary footage with chapter slates and Telugu subtitles",
        )
        if "3-5m" in dur_display:
            target_duration = "3-5m"
        elif "5-8m" in dur_display:
            target_duration = "5-8m"
        else:
            target_duration = "60-90s"

    st.markdown("")
    if st.button("🚀 Generate & Publish Video Now", type="primary", use_container_width=True):
        if not custom_topic.strip():
            st.error("⚠️ Please select or type a video topic first.")
        else:
            with st.spinner("Dispatching video production to Cloud Runner..."):
                ok, msg = trigger_workflow(
                    custom_topic=custom_topic,
                    custom_channel=target_channel,
                    custom_duration=target_duration,
                )
                if ok:
                    st.success("🎉 Video Production Triggered in Cloud! Open 'Live Production' tab to monitor.")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error(f"❌ Failed to trigger: {msg}")

# ============================================================
# TAB 2: LIVE PRODUCTION MONITOR
# ============================================================

with tab_live:
    st.subheader("📡 Live Cloud Production Status")
    
    if st.button("🔄 Refresh Status", use_container_width=True):
        st.rerun()

    runs = get_recent_runs(limit=6)
    if not runs:
        st.info("No recent cloud runs found.")
    else:
        for r in runs:
            r_id = r["id"]
            status = r.get("status", "unknown")
            conclusion = r.get("conclusion")
            created_at = r.get("created_at", "")
            html_url = r.get("html_url", "#")
            
            badge_class = "badge-progress" if status == "in_progress" else (
                "badge-success" if conclusion == "success" else "badge-failed"
            )
            badge_text = status.upper() if status == "in_progress" else (conclusion or status).upper()

            with st.container():
                st.markdown(
                    f"""
                    <div style="background: #1e293b; padding: 15px; border-radius: 12px; margin-bottom: 12px; border: 1px solid #334155;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: bold; font-size: 1.05rem;">Run #{r_id}</span>
                            <span class="status-badge {badge_class}">{badge_text}</span>
                        </div>
                        <p style="margin: 6px 0; color: #94a3b8; font-size: 0.85rem;">Created: {created_at}</p>
                        <a href="{html_url}" target="_blank" style="color: #818cf8; text-decoration: none; font-size: 0.9rem;">
                            🔗 View GitHub Actions Live Runner Logs ↗
                        </a>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

# ============================================================
# TAB 3: 10 DAILY PEAK SLOTS SCHEDULE
# ============================================================

with tab_schedule:
    st.subheader("⏰ Today's 10 Peak Automated Publishing Slots")
    st.write("Videos automatically produce and publish daily during high-traffic Telugu viewing hours.")

    SLOTS_DATA = [
        {"id": "CH1-S1", "time": "08:00 AM", "channel": "Channel 1", "format": "Short (60-90s)", "category": "Morning Local News"},
        {"id": "CH2-S1", "time": "08:45 AM", "channel": "Channel 2", "format": "Short (60-90s)", "category": "Bigg Boss 10 House Drama"},
        {"id": "CH1-L1", "time": "12:30 PM", "channel": "Channel 1", "format": "Long (3-5m)", "category": "Tech Innovation Explainer"},
        {"id": "CH2-L1", "time": "01:30 PM", "channel": "Channel 2", "format": "Long (3-6m)", "category": "BB10 Midday Controversy"},
        {"id": "CH1-S2", "time": "04:00 PM", "channel": "Channel 1", "format": "Short (60-90s)", "category": "Viral Tech & AI Short"},
        {"id": "CH2-S2", "time": "05:00 PM", "channel": "Channel 2", "format": "Short (60-90s)", "category": "BB10 Voting Trends & Leaks"},
        {"id": "CH2-S3", "time": "07:00 PM", "channel": "Channel 2", "format": "Short (60-90s)", "category": "Tollywood Cinema Buzz"},
        {"id": "CH1-S3", "time": "07:45 PM", "channel": "Channel 1", "format": "Short (60-90s)", "category": "Mind-Blowing Mystery"},
        {"id": "CH2-L2", "time": "09:00 PM", "channel": "Channel 2", "format": "Long (4-8m)", "category": "Tollywood Deep Dive Review"},
        {"id": "CH1-L2", "time": "10:00 PM", "channel": "Channel 1", "format": "Long (5-8m)", "category": "Historical Mysteries"},
    ]

    for s in SLOTS_DATA:
        col_s1, col_s2 = st.columns([3, 1])
        with col_s1:
            st.markdown(
                f"**[{s['id']}] {s['time']} IST** — `{s['channel']}`  \n"
                f"<span style='color: #a5b4fc;'>{s['category']}</span> ({s['format']})",
                unsafe_allow_html=True,
            )
        with col_s2:
            if st.button(f"Run {s['id']}", key=f"run_slot_{s['id']}", use_container_width=True):
                with st.spinner(f"Triggering {s['id']}..."):
                    ok, msg = trigger_workflow(slot_id=s['id'])
                    if ok:
                        st.success(f"Slot {s['id']} launched in cloud!")
                        st.rerun()
                    else:
                        st.error(msg)
        st.markdown("<hr style='margin: 6px 0; border-color: #1e293b;'/>", unsafe_allow_html=True)

# ============================================================
# TAB 4: QUOTA & LIMITS
# ============================================================

with tab_quota:
    st.subheader("📊 Cloud & API Limits Tracker")
    st.markdown(
        """
        - **GitHub Actions Free Quota**: 2,000 minutes per month (Auto-resets on 1st of every month).
        - **Average Short Video Render**: ~4 to 6 minutes of cloud runner time.
        - **Average Long-Form Render**: ~7 to 10 minutes.
        - **Estimated Daily Usage for 10 Videos**: ~40-60 mins.
        - **Gemini Free Tier API**: 1,500 requests / day (Zero cost).
        - **Edge-TTS Telugu Speech**: 100% Free & Unlimited.
        - **Pexels & News Media**: 100% Free.
        """
    )

"""
AutoTube AI - 24/7 Multi-Channel Daily Automated Production & Scheduler Engine
(daily_scheduler.py)

Orchestrates 10 daily video publications distributed across peak Telugu viewing hours:
  - Channel 1 (Primary - Imaginary_facts): 3 Shorts + 2 Long-form (Local News, Tech, Mysteries)
  - Channel 2 (Secondary - viral_talks_me&mine): 3 Shorts + 2 Long-form (Bigg Boss 10, Tollywood Cinema)
  - Universal Female Telugu Voice: 👩 Shruti (te-IN-ShrutiNeural)
  - Universal Public Privacy: Direct public uploads
  - Strict Instagram Reels Gating: Only 9:16 Shorts (<= 90s) upload to Instagram Reels; 16:9 Long-form NEVER uploads to Instagram
  - Dynamic Long-Form Intensity Duration: Scales dynamically (3-5m standard, 5-8m high intensity)
  - Mutual Exclusion: PipelineLock prevents concurrency conflicts between manual and automated runs
"""

import os
import sys
import time
import json
import random
import argparse
import traceback
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

LOGS_DIR = ROOT / "logs"
OUTPUT_DIR = ROOT / "output"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DAILY_LOG_FILE = LOGS_DIR / "daily_runs.log"
DAILY_STATUS_FILE = LOGS_DIR / "daily_status.json"
DAILY_SLOT_STATUS_FILE = LOGS_DIR / "daily_slot_status.json"
DAILY_FAILURE_FILE = LOGS_DIR / "daily_failure_latest.json"

from run_lock import PipelineLock
from agents.youtube_agent import resolve_target_channel

# ============================================================
# UNIVERSAL CREATOR SETTINGS
# ============================================================

DEFAULT_TELUGU_VOICE = "👩 Shruti (Telugu Creator / Anchor) - Conversational"
DEFAULT_LANGUAGE_STYLE = "Telugu with English words (Casual / Trendy)"
DEFAULT_PRIVACY = "public"

# Master killswitch: All automatic background uploads are enabled when ENABLE_AUTO_UPLOAD=1 is set.
ENABLE_AUTO_UPLOAD = os.getenv("ENABLE_AUTO_UPLOAD", "0").strip().lower() in ("1", "true", "yes")

# Channel filter for automated background scheduler (default: 'Channel 1'):
# Allows dedicating automated scheduling strictly to Channel 1, while preserving Channel 2 for manual runs.
SCHEDULED_CHANNELS = os.getenv("SCHEDULED_CHANNELS", "Channel 1").strip()

# ============================================================
# 10 DAILY PEAK-HOURS SLOT SCHEDULE (IST)
# ============================================================

DAILY_SLOT_CONFIGS: List[Dict[str, Any]] = [
    {
        "slot_id": "CH1-S1",
        "slot_name": "Channel 1 — Morning Breaking Local News",
        "scheduled_time": "08:00",
        "channel": "Channel 1 (Primary)",
        "format_type": "short",
        "aspect_ratio": "9:16",
        "target_duration": "60-90s",
        "category": "Regional",
        "content_type": "Local News",
        "instagram_upload": True,
        "language_style": DEFAULT_LANGUAGE_STYLE,
        "voice": DEFAULT_TELUGU_VOICE,
        "tone": "informative",
    },
    {
        "slot_id": "CH2-S1",
        "slot_name": "Channel 2 — Bigg Boss 10 Morning House Drama",
        "scheduled_time": "08:45",
        "channel": "Channel 2 (Secondary)",
        "format_type": "short",
        "aspect_ratio": "9:16",
        "target_duration": "60-90s",
        "category": "Bigg Boss Telugu 10",
        "content_type": "Bigg Boss Telugu 10",
        "instagram_upload": True,
        "language_style": DEFAULT_LANGUAGE_STYLE,
        "voice": DEFAULT_TELUGU_VOICE,
        "tone": "roast",
    },
    {
        "slot_id": "CH1-L1",
        "slot_name": "Channel 1 — Tech Innovation / Fact Explainer Deep Dive",
        "scheduled_time": "12:30",
        "channel": "Channel 1 (Primary)",
        "format_type": "long-form",
        "aspect_ratio": "16:9",
        "target_duration": "dynamic",  # 3-5m or 5-8m based on topic intensity
        "category": "Technology",
        "content_type": "Tech News",
        "instagram_upload": False,
        "language_style": DEFAULT_LANGUAGE_STYLE,
        "voice": DEFAULT_TELUGU_VOICE,
        "tone": "informative",
    },
    {
        "slot_id": "CH2-L1",
        "slot_name": "Channel 2 — Bigg Boss 10 Midday Controversy Deep Dive",
        "scheduled_time": "13:30",
        "channel": "Channel 2 (Secondary)",
        "format_type": "long-form",
        "aspect_ratio": "16:9",
        "target_duration": "dynamic",  # 3-6m based on topic intensity
        "category": "Bigg Boss Telugu 10",
        "content_type": "Bigg Boss Telugu 10",
        "instagram_upload": False,
        "language_style": DEFAULT_LANGUAGE_STYLE,
        "voice": DEFAULT_TELUGU_VOICE,
        "tone": "roast",
    },
    {
        "slot_id": "CH1-S2",
        "slot_name": "Channel 1 — Viral Tech / AI Innovation Short",
        "scheduled_time": "16:00",
        "channel": "Channel 1 (Primary)",
        "format_type": "short",
        "aspect_ratio": "9:16",
        "target_duration": "60-90s",
        "category": "Technology",
        "content_type": "Tech News",
        "instagram_upload": True,
        "language_style": DEFAULT_LANGUAGE_STYLE,
        "voice": DEFAULT_TELUGU_VOICE,
        "tone": "informative",
    },
    {
        "slot_id": "CH2-S2",
        "slot_name": "Channel 2 — Bigg Boss 10 Live Voting Trends & Leaks",
        "scheduled_time": "17:00",
        "channel": "Channel 2 (Secondary)",
        "format_type": "short",
        "aspect_ratio": "9:16",
        "target_duration": "60-90s",
        "category": "Bigg Boss Telugu 10",
        "content_type": "Bigg Boss Telugu 10",
        "instagram_upload": True,
        "language_style": DEFAULT_LANGUAGE_STYLE,
        "voice": DEFAULT_TELUGU_VOICE,
        "tone": "roast",
    },
    {
        "slot_id": "CH2-S3",
        "slot_name": "Channel 2 — Tollywood Cinema Buzz & Quick Review",
        "scheduled_time": "19:00",
        "channel": "Channel 2 (Secondary)",
        "format_type": "short",
        "aspect_ratio": "9:16",
        "target_duration": "60-90s",
        "category": "Movie Reviews",
        "content_type": "Movie Reviews",
        "instagram_upload": True,
        "language_style": DEFAULT_LANGUAGE_STYLE,
        "voice": DEFAULT_TELUGU_VOICE,
        "tone": "conversational",
    },
    {
        "slot_id": "CH1-S3",
        "slot_name": "Channel 1 — Mind-Blowing Mystery & Bizarre Facts",
        "scheduled_time": "19:45",
        "channel": "Channel 1 (Primary)",
        "format_type": "short",
        "aspect_ratio": "9:16",
        "target_duration": "60-90s",
        "category": "Science",
        "content_type": "Interesting Facts",
        "instagram_upload": True,
        "language_style": DEFAULT_LANGUAGE_STYLE,
        "voice": DEFAULT_TELUGU_VOICE,
        "tone": "informative",
    },
    {
        "slot_id": "CH2-L2",
        "slot_name": "Channel 2 — Tollywood In-Depth Review / Pop Culture Breakdown",
        "scheduled_time": "21:00",
        "channel": "Channel 2 (Secondary)",
        "format_type": "long-form",
        "aspect_ratio": "16:9",
        "target_duration": "dynamic",  # 4-8m based on topic intensity
        "category": "Cinema & Entertainment",
        "content_type": "Movie Reviews",
        "instagram_upload": False,
        "language_style": DEFAULT_LANGUAGE_STYLE,
        "voice": DEFAULT_TELUGU_VOICE,
        "tone": "conversational",
    },
    {
        "slot_id": "CH1-L2",
        "slot_name": "Channel 1 — Historical Mysteries & Unsolved Phenomena",
        "scheduled_time": "22:00",
        "channel": "Channel 1 (Primary)",
        "format_type": "long-form",
        "aspect_ratio": "16:9",
        "target_duration": "dynamic",  # 5-8m based on topic intensity
        "category": "History",
        "content_type": "History",
        "instagram_upload": False,
        "language_style": DEFAULT_LANGUAGE_STYLE,
        "voice": DEFAULT_TELUGU_VOICE,
        "tone": "informative",
    },
]

# Evergreen Curated Topics (Fallbacks if live feeds are momentarily unreachable)
CURATED_HISTORY_TOPICS = [
    "The Library of Alexandria: The Tragic Loss of Ancient World Knowledge",
    "The Antikythera Mechanism: The Ancient Greek Analog Computer That Shocked Modern Science",
    "The Indus Valley Civilization: The Mysterious Bronze Age Metropolis That Vanished",
    "The Hidden Architecture of the Great Pyramid of Giza: Unsolved Engineering Feats",
    "The Silk Road: The Ancient Superhighway That Shaped Global Trade and Civilizations",
]

CURATED_FACTS_TOPICS = [
    "10 Unbelievable Deep Sea Phenomena Science Still Cannot Explain",
    "The Strangest Cosmic Anomalies Discovered by Space Telescopes",
    "Bizarre Survival Adaptations in Extreme Environments on Earth",
    "Quantum Entanglement and the Bizarre Paradoxes of Modern Physics",
    "How Optical Illusions Fool the Human Brain: Fascinating Neuroscience Facts",
]


def log_daily(message: str):
    """Appends a timestamped entry to logs/daily_runs.log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] [24/7_SCHEDULER] {message}\n"
    try:
        with open(DAILY_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass
    print(entry.strip(), flush=True)


# ============================================================
# SLOT STATE PERSISTENCE & RECOVERY
# ============================================================

def get_slot_config(slot_id: str) -> Optional[Dict[str, Any]]:
    """Returns configuration dictionary for a given slot_id."""
    for s in DAILY_SLOT_CONFIGS:
        if s["slot_id"].upper() == slot_id.upper():
            return s
    return None


def load_daily_slot_status() -> Dict[str, Any]:
    """
    Reads slot execution status for today. Initializes missing slots to 'pending'.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    default_payload = {
        "date": today_str,
        "slots": {},
    }

    raw = {}
    if DAILY_SLOT_STATUS_FILE.exists():
        try:
            raw = json.loads(DAILY_SLOT_STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            raw = {}

    # If the file belongs to an older date, roll over to today
    if raw.get("date") != today_str:
        raw = default_payload

    if "slots" not in raw:
        raw["slots"] = {}

    # Ensure all 10 slots are represented
    for conf in DAILY_SLOT_CONFIGS:
        s_id = conf["slot_id"]
        if s_id not in raw["slots"]:
            raw["slots"][s_id] = {
                "slot_id": s_id,
                "slot_name": conf["slot_name"],
                "scheduled_time": conf["scheduled_time"],
                "channel": conf["channel"],
                "format_type": conf["format_type"],
                "status": "pending",  # pending, in_progress, success, failed, skipped
                "executed_at": None,
                "topic": None,
                "youtube_video_id": None,
                "instagram_status": None,
                "error": None,
                "attempts": 0,
            }

    return raw


def save_daily_slot_status(status_dict: Dict[str, Any]):
    """Persists daily slot execution status."""
    try:
        DAILY_SLOT_STATUS_FILE.write_text(json.dumps(status_dict, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log_daily(f"Failed to save slot status: {e}")


# ============================================================
# LIVE TOPIC RESOLUTION & INTENSITY EVALUATION
# ============================================================

def evaluate_slot_duration(slot: Dict[str, Any], topic: str) -> str:
    """
    Dynamically computes target duration based on format type and topic intensity:
      - Short: strictly '60-90s' (Extended Shorts / Meta Reels Sweet Spot)
      - Long-form:
          - High Intensity (multi-chapter controversy, historical mystery, deep saga): '5-8m'
          - Standard (focused review, tech explainer, single-incident analysis): '3-5m'
    """
    if slot.get("format_type") == "short":
        return "60-90s"

    topic_lower = topic.lower()
    high_intensity_keywords = [
        "mystery", "unsolved", "ancient", "history", "civilization",
        "conspiracy", "scandal", "elimination", "danger zone",
        "truth behind", "full story", "investigation", "timeline",
        "dark secrets", "deep sea", "pyramid", "quantum", "universe",
        "shocking truth", "complete breakdown", "saga"
    ]
    if any(k in topic_lower for k in high_intensity_keywords):
        return "5-8m"
    return "3-5m"


def fetch_live_slot_topic(slot: Dict[str, Any]) -> str:
    """
    Discovers fresh, real-time live topics from Google News RSS and Telugu news feeds.
    Deduplicates against data/used_topics.json and past 7 days to guarantee novelty.
    """
    category = slot.get("category", "")
    content_type = slot.get("content_type", "")
    s_id = slot.get("slot_id", "")

    try:
        from agents.topic_suggester import fetch_ai_topic_suggestions, record_used_topic, load_used_topics
        used = load_used_topics()
    except Exception:
        used = set()
        def record_used_topic(t): pass

    # 1. Bigg Boss Telugu 10 / Post-Bigg Boss Pivot (Slots: CH2-S1, CH2-L1, CH2-S2)
    if "bigg boss" in category.lower() or "bigg boss" in content_type.lower():
        try:
            from agents.topic_suggester import fetch_ai_topic_suggestions, rank_topics_by_ovs
            suggestions = fetch_ai_topic_suggestions("Bigg Boss Telugu", count=5, use_ai=True)
            valid = [c for c in suggestions if c.strip().lower() not in used]
            
            # Post-Bigg Boss Self-Healing Pivot: If BB10 has ended or yields no fresh stories,
            # seamlessly transition to Tollywood Trolls, OTT Reviews, and Viral Roasts!
            if not valid:
                log_daily("ℹ️ Post-Bigg Boss Pivot: Seamlessly transitioning slot to Tollywood Trolls & Viral Drama...")
                pivot_suggestions = fetch_ai_topic_suggestions("Tollywood Trolls & Viral Drama", count=5, use_ai=True)
                valid = [c for c in pivot_suggestions if c.strip().lower() not in used]
            
            if valid:
                ranked = rank_topics_by_ovs(valid, "Bigg Boss Telugu")
                chosen = ranked[0]
                record_used_topic(chosen)
                return chosen
        except Exception as e:
            log_daily(f"Notice: topic_suggester for BB10 returned ({e}), falling back to live RSS query.")

        # Fallback to direct news query
        try:
            from agents.news_agent import get_trending_news
            bb_news = get_trending_news(category="Entertainment", limit=6)
            for item in bb_news:
                title = item.get("title", "")
                if title and title.strip().lower() not in used:
                    record_used_topic(title)
                    return title
        except Exception:
            pass

        # Evergreen dynamic fallback with today's date
        today_formatted = datetime.now().strftime("%d %B")
        fallback = f"Tollywood Viral Drama & Shocking Entertainment Twists ({today_formatted})"
        record_used_topic(fallback)
        return fallback

    # 2. Tollywood Movie Reviews & Cinema Buzz (Slots: CH2-S3, CH2-L2)
    elif "movie" in content_type.lower() or "cinema" in category.lower():
        try:
            from agents.topic_suggester import fetch_ai_topic_suggestions, rank_topics_by_ovs
            suggestions = fetch_ai_topic_suggestions("Movie Reviews", count=5, use_ai=True)
            valid = [c for c in suggestions if c.strip().lower() not in used]
            if valid:
                ranked = rank_topics_by_ovs(valid, "Movie Reviews")
                chosen = ranked[0]
                record_used_topic(chosen)
                return chosen
        except Exception as e:
            log_daily(f"Notice: topic_suggester for Cinema returned ({e})")

        try:
            from agents.news_agent import get_trending_news
            ent_news = get_trending_news(category="Entertainment", limit=8)
            for item in ent_news:
                t = item.get("title", "")
                if t and t.strip().lower() not in used:
                    record_used_topic(t)
                    return t
        except Exception:
            pass

        fallback = "Latest Tollywood Blockbuster Verdict and Box Office Sensation"
        record_used_topic(fallback)
        return fallback

    # 3. AP & Telangana Local Breaking News (Slot: CH1-S1)
    elif "local" in content_type.lower() or "regional" in category.lower():
        try:
            from agents.topic_suggester import fetch_ai_topic_suggestions, rank_topics_by_ovs
            suggestions = fetch_ai_topic_suggestions("Ground Reality AP/Telangana News", count=5, use_ai=True)
            valid = [c for c in suggestions if c.strip().lower() not in used]
            if valid:
                ranked = rank_topics_by_ovs(valid, "Ground Reality AP/Telangana News")
                chosen = ranked[0]
                record_used_topic(chosen)
                return chosen
        except Exception:
            pass

        try:
            from agents.news_agent import get_trending_news
            regional_news = get_trending_news(category="Regional", limit=8)
            for item in regional_news:
                t = item.get("title", "")
                if t and t.strip().lower() not in used:
                    record_used_topic(t)
                    return t
        except Exception as e:
            log_daily(f"Notice: news_agent for Regional returned ({e})")

        fallback = "Andhra Pradesh and Telangana Key Updates and Trending Highlights Today"
        record_used_topic(fallback)
        return fallback

    # 4. Tech News & AI Innovations (Slots: CH1-L1, CH1-S2)
    elif "tech" in content_type.lower() or "technology" in category.lower():
        try:
            from agents.topic_suggester import fetch_ai_topic_suggestions, rank_topics_by_ovs
            suggestions = fetch_ai_topic_suggestions("Tech News", count=5, use_ai=True)
            valid = [c for c in suggestions if c.strip().lower() not in used]
            if valid:
                ranked = rank_topics_by_ovs(valid, "Tech News")
                chosen = ranked[0]
                record_used_topic(chosen)
                return chosen
        except Exception:
            pass

        try:
            from agents.news_agent import get_trending_news
            tech_news = get_trending_news(category="Technology", limit=8)
            for item in tech_news:
                t = item.get("title", "")
                if t and t.strip().lower() not in used:
                    record_used_topic(t)
                    return t
        except Exception as e:
            log_daily(f"Notice: news_agent for Tech returned ({e})")

        fallback = "Next-Generation AI Innovations and Major Technological Breakthroughs"
        record_used_topic(fallback)
        return fallback

    # 5. History & Ancient Mysteries (Slot: CH1-L2)
    elif "history" in content_type.lower() or "history" in category.lower():
        try:
            from agents.topic_suggester import fetch_ai_topic_suggestions, rank_topics_by_ovs
            suggestions = fetch_ai_topic_suggestions("Indian Mysteries & Ancient Engineering", count=5, use_ai=True)
            valid = [c for c in suggestions if c.strip().lower() not in used]
            if valid:
                ranked = rank_topics_by_ovs(valid, "Indian Mysteries & Ancient Engineering")
                chosen = ranked[0]
                record_used_topic(chosen)
                return chosen
        except Exception:
            pass

        unused = [t for t in CURATED_HISTORY_TOPICS if t.strip().lower() not in used]
        chosen = random.choice(unused if unused else CURATED_HISTORY_TOPICS)
        record_used_topic(chosen)
        return chosen

    # 6. Interesting Facts & Strange Phenomena (Slot: CH1-S3)
    else:
        try:
            from agents.topic_suggester import fetch_ai_topic_suggestions, rank_topics_by_ovs
            suggestions = fetch_ai_topic_suggestions("Interesting Facts", count=5, use_ai=True)
            valid = [c for c in suggestions if c.strip().lower() not in used]
            if valid:
                ranked = rank_topics_by_ovs(valid, "Interesting Facts")
                chosen = ranked[0]
                record_used_topic(chosen)
                return chosen
        except Exception:
            pass

        unused = [t for t in CURATED_FACTS_TOPICS if t.strip().lower() not in used]
        chosen = random.choice(unused if unused else CURATED_FACTS_TOPICS)
        record_used_topic(chosen)
        return chosen


# ============================================================
# MULTI-SLOT EXECUTION ENGINE
# ============================================================

class MultiSlotDailyScheduler:
    """
    Manages 24/7 continuous monitoring, automated slot triggering,
    and robust error recovery across Channel 1 and Channel 2.
    """

    def __init__(self):
        self.enabled = os.getenv("DAILY_AUTO_GENERATE", "true").strip().lower() in ("true", "1", "yes")
        self.upload_privacy = os.getenv("DAILY_UPLOAD_PRIVACY", DEFAULT_PRIVACY).strip().lower()
        self.deferred_until: Optional[float] = None
        self._is_executing_slot: bool = False

    def is_slot_due(self, slot_conf: Dict[str, Any], current_time: datetime) -> bool:
        """
        Determines if a slot is due for execution.
        Triggers if current local time is at or after scheduled_time today.
        """
        sched_str = slot_conf.get("scheduled_time", "08:00")
        try:
            parts = sched_str.split(":")
            s_hour, s_minute = int(parts[0]), int(parts[1])
            slot_dt = current_time.replace(hour=s_hour, minute=s_minute, second=0, microsecond=0)
            return current_time >= slot_dt
        except Exception:
            return False

    def is_channel_automated(self, slot_conf: Dict[str, Any]) -> bool:
        """
        Filters which channels are included in automated scheduling sweeps.
        If SCHEDULED_CHANNELS='Channel 1', only Channel 1 slots will run automatically.
        Channel 2 is preserved strictly for manual/local runs by the user.
        """
        sched_ch = os.getenv("SCHEDULED_CHANNELS", "Channel 1").strip().lower()
        if not sched_ch or sched_ch in ("all", "both", "*"):
            return True
        ch_name = slot_conf.get("channel", "").lower()
        if "1" in sched_ch and ("channel 1" in ch_name or "primary" in ch_name or "ch1" in ch_name):
            return True
        if "2" in sched_ch and ("channel 2" in ch_name or "secondary" in ch_name or "ch2" in ch_name):
            return True
        return False

    def execute_slot(self, slot_id: str, force: bool = False) -> bool:
        """
        Executes a single scheduled slot end-to-end:
          1. Topic discovery & intensity duration evaluation.
          2. Pipeline lock acquisition.
          3. Pipeline generation with Shruti Telugu voice.
          4. YouTube public upload to correct channel.
          5. Instagram Reels upload (if short) or strict exclusion (if long-form).
          6. Status persistence in logs/daily_slot_status.json.
        """
        slot_conf = get_slot_config(slot_id)
        if not slot_conf:
            log_daily(f"❌ Error: Unknown slot_id '{slot_id}'")
            return False

        if self._is_executing_slot:
            log_daily(f"⚠️ A slot is already currently generating. Deferring '{slot_id}'...")
            return False

        status_data = load_daily_slot_status()
        slot_status = status_data["slots"].get(slot_id, {})
        current_state = slot_status.get("status")

        # Skip if already succeeded today (unless forced)
        if current_state == "success" and not force:
            log_daily(f"ℹ️ Slot '{slot_id}' already succeeded today. Skipping duplicate execution.")
            return True

        # Check maximum retry attempts per day
        attempts = slot_status.get("attempts", 0)
        if attempts >= 2 and not force:
            log_daily(f"⚠️ Slot '{slot_id}' reached maximum retry attempts (2) today. Skipping.")
            return False

        # Check Daily Channel Upload Cap (Max 3 Shorts, Max 1 Long-form per channel/day)
        if not force:
            shorts_today = 0
            long_today = 0
            is_ch1 = "channel 1" in slot_conf["channel"].lower()
            for sid, s_st in status_data.get("slots", {}).items():
                if s_st.get("status") == "success":
                    matching_c = next((c for c in DAILY_SLOT_CONFIGS if c["slot_id"] == sid), None)
                    if matching_c and (("channel 1" in matching_c["channel"].lower()) == is_ch1):
                        if matching_c["format_type"] == "short":
                            shorts_today += 1
                        elif matching_c["format_type"] == "long-form":
                            long_today += 1

            target_fmt = slot_conf.get("format_type", "short")
            ch_name = "Channel 1" if is_ch1 else "Channel 2"
            if target_fmt == "short" and shorts_today >= 3:
                log_daily(f"ℹ️ Daily upload cap reached for {ch_name}: {shorts_today} shorts already published today (Max 3). Skipping '{slot_id}' to protect YouTube algorithm velocity.")
                return True
            if target_fmt == "long-form" and long_today >= 1:
                log_daily(f"ℹ️ Daily upload cap reached for {ch_name}: {long_today} long-form video already published today (Max 1). Skipping '{slot_id}' to protect YouTube algorithm velocity.")
                return True

        # 1. Mutual Exclusion Check
        active_lock = PipelineLock.get_active_lock_info()
        if active_lock:
            holder = active_lock.get("source", "another process")
            pid = active_lock.get("pid", "?")
            log_daily(f"⚠️ Video generation currently in progress by {holder} (PID {pid}). Deferring slot '{slot_id}' by 5 minutes...")
            self.deferred_until = time.time() + 300
            return False

        self._is_executing_slot = True

        # Resolve Topic and Dynamic Duration
        topic = fetch_live_slot_topic(slot_conf)
        duration = evaluate_slot_duration(slot_conf, topic)
        channel = slot_conf["channel"]
        aspect = slot_conf["aspect_ratio"]
        fmt_type = slot_conf["format_type"]
        is_ig_eligible = slot_conf["instagram_upload"] and fmt_type == "short" and aspect == "9:16"

        log_daily("=" * 65)
        log_daily(f"🚀 EXECUTING SLOT: [{slot_id}] {slot_conf['slot_name']} {'(FORCED)' if force else ''}")
        log_daily(f"   Topic       : {topic}")
        log_daily(f"   Channel     : {channel}")
        log_daily(f"   Format      : {fmt_type.upper()} | Aspect: {aspect} | Target: {duration}")
        log_daily(f"   Voice       : {slot_conf['voice']}")
        log_daily(f"   Tone        : {slot_conf.get('tone', 'default')}")
        log_daily(f"   Privacy     : {self.upload_privacy}")
        log_daily(f"   Instagram   : {'ENABLED (Shorts)' if is_ig_eligible else 'BLOCKED (Long-form / Excluded)'}")
        log_daily("=" * 65)

        # Acquire Lock
        lock = PipelineLock(source=f"scheduler_slot_{slot_id}", topic=topic)
        lock_ok, lock_err = lock.acquire()
        if not lock_ok:
            log_daily(f"❌ Failed to acquire pipeline lock: {lock_err}")
            self._is_executing_slot = False
            self.deferred_until = time.time() + 300
            return False

        # Update slot state to in_progress
        slot_status["status"] = "in_progress"
        slot_status["topic"] = topic
        slot_status["attempts"] = attempts + 1
        save_daily_slot_status(status_data)

        start_time = time.time()
        try:
            from pipeline import generate_multi_media_video

            result = generate_multi_media_video(
                topic=topic,
                content_type=slot_conf["content_type"],
                language_style=slot_conf["language_style"],
                voice=slot_conf["voice"],
                tone=slot_conf.get("tone"),
                captions=(aspect == "16:9"),
                thumbnail=True,
                metadata=True,
                youtube_upload=ENABLE_AUTO_UPLOAD,
                youtube_privacy=self.upload_privacy,
                youtube_channel=channel,
                aspect_ratio=aspect,
                target_duration=duration,
                instagram_upload=bool(ENABLE_AUTO_UPLOAD and is_ig_eligible),
                generation_mode="stock",
            )

            # Check quality gates
            if (result or {}).get("upload_blocked") or (result or {}).get("status") == "SKIPPED_UNPUBLISHED":
                err_msg = (result or {}).get("youtube_error") or "Failed Phase 7 quality gates"
                log_daily(f"🛑 [Quality Gate Blocked] Slot '{slot_id}' was skipped and unpublished: {err_msg}")
                slot_status["status"] = "failed"
                slot_status["error"] = err_msg
                save_daily_slot_status(status_data)
                return False

            vid_id = (result or {}).get("youtube_video_id")
            title = (result or {}).get("title", topic)
            ig_res = (result or {}).get("instagram_status")

            elapsed = time.time() - start_time
            log_daily("=" * 65)
            log_daily(f"✅ SLOT COMPLETED SUCCESSFULLY: [{slot_id}] in {elapsed:.1f}s")
            log_daily(f"   Title        : {title}")
            log_daily(f"   YouTube ID   : {vid_id or 'Uploaded'}")
            log_daily(f"   YouTube Link : https://www.youtube.com/watch?v={vid_id}" if vid_id else "   YouTube Link : N/A")
            log_daily(f"   Channel      : {channel}")
            log_daily(f"   Instagram    : {ig_res.get('result', {}).get('media_id', 'Skipped') if ig_res else 'N/A'}")
            log_daily("=" * 65)

            slot_status["status"] = "success"
            slot_status["executed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            slot_status["youtube_video_id"] = vid_id
            slot_status["youtube_url"] = f"https://www.youtube.com/watch?v={vid_id}" if vid_id else None
            slot_status["instagram_status"] = ig_res
            slot_status["error"] = None
            save_daily_slot_status(status_data)

            try:
                from utils.github_quota import record_workflow_execution
                record_workflow_execution(slot_id, elapsed)
            except Exception:
                pass

            # Clean failure file if exists
            if DAILY_FAILURE_FILE.exists():
                try:
                    DAILY_FAILURE_FILE.unlink()
                except Exception:
                    pass

            return True

        except Exception as e:
            tb = traceback.format_exc()
            log_daily(f"🛑 Execution of slot '{slot_id}' failed: {e}")
            slot_status["status"] = "failed"
            slot_status["error"] = str(e)
            save_daily_slot_status(status_data)

            # Record failure JSON for debug
            failure_record = {
                "timestamp": datetime.now().isoformat(),
                "slot_id": slot_id,
                "topic": topic,
                "channel": channel,
                "error": str(e),
                "traceback": tb,
            }
            try:
                DAILY_FAILURE_FILE.write_text(json.dumps(failure_record, indent=2), encoding="utf-8")
            except Exception:
                pass

            return False

        finally:
            self._is_executing_slot = False
            lock.release()


    def execute_custom(self, topic: str, channel: str = "viral_talks_me&mine", duration: str = "60-90s", aspect_ratio: str = None) -> bool:
        """
        Executes a custom on-demand video production triggered from mobile web UI or GitHub Actions.
        """
        if not aspect_ratio:
            aspect_ratio = "9:16" if duration in ("30-60s", "60-90s") else "16:9"
        
        fmt_type = "short" if duration in ("30-60s", "60-90s") else "long"
        is_ig_eligible = (fmt_type == "short" and aspect_ratio == "9:16")
        content_type = "bigg_boss" if any(k in topic.lower() for k in ["bigg", "bb", "house", "nomination", "elimination"]) else "technology"
        style = "casual_telugu" if any(k in topic.lower() for k in ["bigg", "bb", "cinema", "tollywood"]) else "informative_telugu"

        log_daily("=" * 65)
        log_daily("🎯 EXECUTING CUSTOM ON-DEMAND PRODUCTION")
        log_daily(f"   Topic       : {topic}")
        log_daily(f"   Channel     : {channel}")
        log_daily(f"   Format      : {fmt_type.upper()} | Aspect: {aspect_ratio} | Duration: {duration}")
        log_daily(f"   Voice       : te-IN-ShrutiNeural")
        log_daily(f"   Instagram   : {'ENABLED (Shorts)' if is_ig_eligible else 'BLOCKED (Long-form / Excluded)'}")
        log_daily("=" * 65)

        lock = PipelineLock(source="custom_mobile_run", topic=topic)
        lock_ok, lock_err = lock.acquire()
        if not lock_ok:
            log_daily(f"❌ Failed to acquire lock for custom run: {lock_err}")
            return False

        start_time = time.time()
        try:
            from pipeline import generate_multi_media_video
            result = generate_multi_media_video(
                topic=topic,
                content_type=content_type,
                language_style=style,
                voice="te-IN-ShrutiNeural",
                captions=(aspect_ratio == "16:9"),
                thumbnail=True,
                metadata=True,
                youtube_upload=ENABLE_AUTO_UPLOAD,
                youtube_privacy=self.upload_privacy,
                youtube_channel=channel,
                aspect_ratio=aspect_ratio,
                target_duration=duration,
                instagram_upload=bool(ENABLE_AUTO_UPLOAD and is_ig_eligible),
                generation_mode="stock",
            )
            vid_id = (result or {}).get("youtube_video_id")
            elapsed = time.time() - start_time
            log_daily(f"✅ CUSTOM RUN COMPLETED: YouTube ID {vid_id or 'Uploaded'} in {elapsed:.1f}s")
            return bool(vid_id or (result and result.get("status") == "success"))
        except Exception as e:
            log_daily(f"🛑 Custom run failed: {e}")
            return False
        finally:
            lock.release()

    def run_pending_slots(self) -> int:
        """
        Scans all 10 slots for today. Executes any slot that is due, pending, and enabled for automation.
        Returns the count of successfully executed slots in this pass.
        """
        if not self.enabled:
            log_daily("ℹ️ Scheduler is disabled via DAILY_AUTO_GENERATE=false. Skipping automated sweep.")
            return 0

        now = datetime.now()
        status_data = load_daily_slot_status()
        success_count = 0

        for conf in DAILY_SLOT_CONFIGS:
            s_id = conf["slot_id"]
            if not self.is_channel_automated(conf):
                continue

            slot_st = status_data["slots"].get(s_id, {})
            current_status = slot_st.get("status", "pending")

            if current_status == "pending" and self.is_slot_due(conf, now):
                log_daily(f"⏰ Slot '{s_id}' scheduled for {conf['scheduled_time']} is DUE NOW. Launching...")
                ok = self.execute_slot(s_id, force=False)
                if ok:
                    success_count += 1
                # Small pause between consecutive slots if multiple were pending
                time.sleep(5)

        return success_count

    def run_current_slot(self) -> Optional[str]:
        """
        Executes strictly ONE single slot that matches the current time window.
        Prevents batch bursts and adheres to YouTube daily pacing limits.
        """
        if not self.enabled:
            log_daily("ℹ️ Scheduler is disabled via DAILY_AUTO_GENERATE=false. Skipping execution.")
            return None

        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
        except Exception:
            # Fallback: UTC + 5h 30m
            now = datetime.utcnow() + timedelta(hours=5, minutes=30)

        now_mins = now.hour * 60 + now.minute
        status_data = load_daily_slot_status()

        # Find the pending slot whose scheduled time is closest to now (within 90 mins)
        best_slot = None
        min_diff = 999999

        for conf in DAILY_SLOT_CONFIGS:
            s_id = conf["slot_id"]
            if not self.is_channel_automated(conf):
                continue

            slot_st = status_data.get("slots", {}).get(s_id, {})
            current_status = slot_st.get("status", "pending")
            if current_status == "success":
                continue

            sched_str = conf.get("scheduled_time", "08:00")
            parts = sched_str.split(":")
            s_mins = int(parts[0]) * 60 + int(parts[1])

            # Slot must be past its scheduled time, but within 90 mins
            diff = now_mins - s_mins
            if 0 <= diff <= 90:
                if diff < min_diff:
                    min_diff = diff
                    best_slot = s_id

        if not best_slot:
            # If no slot is within (0, 90] minutes, look for the earliest due pending slot
            for conf in DAILY_SLOT_CONFIGS:
                s_id = conf["slot_id"]
                if not self.is_channel_automated(conf):
                    continue

                slot_st = status_data.get("slots", {}).get(s_id, {})
                if slot_st.get("status") == "pending" and self.is_slot_due(conf, now):
                    best_slot = s_id
                    break

        if best_slot:
            log_daily(f"🎯 [Single Slot Pacing] Selected slot for current window ({now.strftime('%H:%M')} IST): '{best_slot}'. Launching...")
            ok = self.execute_slot(best_slot, force=False)
            return best_slot if ok else None
        else:
            log_daily(f"ℹ️ [Single Slot Pacing] No pending slot due for the current window ({now.strftime('%H:%M')} IST).")
            return None

    def start_daemon(self, poll_interval_seconds: int = 60):
        """
        Runs 24/7 background worker loop.
        Monitors peak slots continuously and triggers generations on schedule.
        """
        log_daily("=" * 65)
        log_daily("🌟 24/7 AUTO-TUBE AI MULTI-CHANNEL DAEMON STARTED")
        log_daily("   Monitoring 10 Daily Slots (IST Peak Hours)...")
        for s in DAILY_SLOT_CONFIGS:
            log_daily(f"   - [{s['slot_id']}] {s['scheduled_time']} | {s['channel']} | {s['format_type'].upper()} ({s['target_duration']}) | {s['slot_name']}")
        log_daily("=" * 65)

        try:
            while True:
                # Check deferral
                if self.deferred_until and time.time() < self.deferred_until:
                    time.sleep(10)
                    continue

                self.run_pending_slots()
                time.sleep(poll_interval_seconds)

        except KeyboardInterrupt:
            log_daily("🛑 24/7 Daemon received KeyboardInterrupt. Stopping gracefully...")
        except Exception as loop_err:
            log_daily(f"⚠️ Daemon error: {loop_err}")


# ============================================================
# CLI INTERFACE
# ============================================================

def print_slot_status():
    """Prints a clean ASCII table of today's 10 slot statuses."""
    status_data = load_daily_slot_status()
    today = status_data.get("date", date.today().isoformat())
    slots = status_data.get("slots", {})

    print()
    sched = MultiSlotDailyScheduler()
    sched_ch = os.getenv("SCHEDULED_CHANNELS", "Channel 1").strip()
    print("=" * 95)
    print(f"📊 AUTOTUBE AI — 10-SLOT DAILY PRODUCTION STATUS ({today}) | AUTOMATING: {sched_ch.upper()}")
    print("=" * 95)
    print(f"{'SLOT ID':<8} | {'TIME':<5} | {'CHANNEL':<18} | {'MODE':<8} | {'FORMAT':<9} | {'STATUS':<11} | {'TOPIC / URL'}")
    print("-" * 95)

    for conf in DAILY_SLOT_CONFIGS:
        s_id = conf["slot_id"]
        st = slots.get(s_id, {})
        status = st.get("status", "pending").upper()
        sched_time = conf["scheduled_time"]
        channel = conf["channel"]
        fmt = f"{conf['format_type']} ({conf['aspect_ratio']})"
        topic = st.get("topic") or conf["slot_name"]
        yt_id = st.get("youtube_video_id")
        extra = f" -> https://youtu.be/{yt_id}" if yt_id else ""
        mode = "AUTO" if sched.is_channel_automated(conf) else "MANUAL"
        print(f"{s_id:<8} | {sched_time:<5} | {channel[:18]:<18} | {mode:<8} | {fmt[:9]:<9} | {status:<11} | {topic[:30]}{extra}")

    print("=" * 95)
    print()


def main():
    parser = argparse.ArgumentParser(description="AutoTube AI 24/7 Multi-Channel Daily Scheduler")
    parser.add_argument("--daemon", action="store_true", help="Start continuous 24/7 background scheduler loop")
    parser.add_argument("--custom-topic", type=str, default=None, help="Execute a custom video topic immediately")
    parser.add_argument("--custom-channel", type=str, default="viral_talks_me&mine", help="Channel for custom topic (default: viral_talks_me&mine)")
    parser.add_argument("--custom-duration", type=str, default="60-90s", help="Duration for custom topic (default: 60-90s)")
    parser.add_argument("--custom-aspect", type=str, default=None, help="Aspect ratio for custom topic (9:16 or 16:9)")
    parser.add_argument("--slot", type=str, default=None, help="Execute a specific slot ID immediately (e.g. CH2-S1, CH1-L1)")
    parser.add_argument("--run-pending", action="store_true", help="Execute all currently due and pending slots")
    parser.add_argument("--run-current", action="store_true", help="Execute strictly ONE slot due for the current time window")
    parser.add_argument("--force", action="store_true", help="Force execution even if slot already succeeded today")
    parser.add_argument("--status", action="store_true", help="Print table of today's 10 slots and their statuses")
    args = parser.parse_args()

    scheduler = MultiSlotDailyScheduler()

    if args.status:
        print_slot_status()
        return

    if args.custom_topic:
        ok = scheduler.execute_custom(
            topic=args.custom_topic,
            channel=args.custom_channel,
            duration=args.custom_duration,
            aspect_ratio=args.custom_aspect
        )
        sys.exit(0 if ok else 1)

    if args.slot:
        ok = scheduler.execute_slot(args.slot, force=args.force)
        sys.exit(0 if ok else 1)

    if args.run_current:
        executed_slot = scheduler.run_current_slot()
        print(f"✅ Processed current window slot: {executed_slot or 'None due'}")
        return

    if args.run_pending:
        count = scheduler.run_pending_slots()
        print(f"✅ Processed pending slots: {count} succeeded.")
        return

    if args.daemon:
        scheduler.start_daemon(poll_interval_seconds=60)
        return

    # Default action if no args: print status and run any pending
    print_slot_status()
    scheduler.run_pending_slots()


if __name__ == "__main__":
    main()

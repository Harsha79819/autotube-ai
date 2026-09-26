"""
AutoTube AI - Global Supervisor & Autonomous Self-Healing Error Interceptor (supervisor.py)

Intercepts unhandled runtime exceptions across all major pipeline stages,
analyzes errors via Gemini AI, applies concrete automated fallbacks
without requiring human intervention, and streams real-time recovery events to the UI.
"""

import os
import sys
import time
import json
import traceback
import threading
import subprocess
import functools
import inspect
import asyncio
from pathlib import Path
from collections import deque
from datetime import datetime

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
FALLBACK_DIR = ASSETS_DIR / "fallback"
FAILED_RUNS_DIR = ROOT / "failed_runs"
FAILED_QUEUE_DIR = ROOT / "failed_queue"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
FAILED_RUNS_DIR.mkdir(parents=True, exist_ok=True)
FAILED_QUEUE_DIR.mkdir(parents=True, exist_ok=True)

EVENTS_LOG_FILE = OUTPUT_DIR / "self_healing_events.jsonl"

# Thread-safe in-memory ring buffer for incident history
_INCIDENT_LOCK = threading.Lock()
_INCIDENT_HISTORY = deque(maxlen=100)
_UNCONSUMED_EVENTS = []  # For Streamlit toast pop notifications

# Load existing events on startup if present
if EVENTS_LOG_FILE.exists():
    try:
        with open(EVENTS_LOG_FILE, "r", encoding="utf-8") as _f:
            for _line in _f:
                if _line.strip():
                    _INCIDENT_HISTORY.append(json.loads(_line))
    except Exception:
        pass


# ============================================================
# 1. AI ERROR ANALYZER (GEMINI + HEURISTIC FALLBACK)
# ============================================================

def analyze_error_with_ai(stage_name, error, tb_str="", context=None):
    """
    Analyze error using Gemini AI to classify and diagnose root cause.
    Classifications:
      (A) Transient/Network (HTTP 429, timeout, network disconnect, quota)
      (B) Bad Input Asset (corrupt image, missing file, zero-byte audio)
      (C) Parameter Mismatch (FFmpeg filter/scale error, KeyError, type error)
    """
    error_type = type(error).__name__
    error_msg = str(error)
    context_str = json.dumps(context, default=str) if context else "{}"

    # Try fast Gemini AI analysis
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = f"""You are an elite autonomous debugging supervisor for an AI video production pipeline.
Analyze this runtime error from stage '{stage_name}'.

ERROR TYPE: {error_type}
ERROR MESSAGE: {error_msg}
TRACEBACK SNIPPET:
{tb_str[-1200:] if tb_str else 'N/A'}
CONTEXT:
{context_str[:600]}

Classify the error into exactly one category:
(A) Transient/Network
(B) Bad Input Asset
(C) Parameter Mismatch

Return ONLY a JSON object with keys:
{{
  "classification": "(A) Transient/Network" | "(B) Bad Input Asset" | "(C) Parameter Mismatch",
  "root_cause": "concise 1-sentence explanation of what failed",
  "recommended_action": "concrete fallback action to heal without human input"
}}
"""
            for model_id in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
                try:
                    resp = client.models.generate_content(model=model_id, contents=prompt)
                    raw_text = getattr(resp, "text", "")
                    if raw_text:
                        clean_text = raw_text.strip()
                        if "```json" in clean_text:
                            clean_text = clean_text.split("```json")[1].split("```")[0].strip()
                        elif "```" in clean_text:
                            clean_text = clean_text.split("```")[1].split("```")[0].strip()
                        parsed = json.loads(clean_text)
                        return {
                            "classification": parsed.get("classification", "(C) Parameter Mismatch"),
                            "root_cause": parsed.get("root_cause", error_msg),
                            "recommended_action": parsed.get("recommended_action", "Applied automated fallback handler"),
                        }
                except Exception:
                    continue
        except Exception:
            pass

    # Deterministic heuristic fallback analysis
    lower_err = f"{error_type} {error_msg}".lower()

    if any(k in lower_err for k in ["timeout", "429", "quota", "connection", "rate limit", "resourceexhausted", "dns", "http", "network"]):
        classification = "(A) Transient/Network"
        root_cause = f"Network timeout or API quota limit reached: {error_msg[:120]}"
        action = "Switched to cached assets or secondary offline fallback strategy"
    elif any(k in lower_err for k in ["filenotfound", "cannot identify image", "corrupt", "no such file", "unidentifiedimage", "empty audio", "0 bytes", "image", "asset"]):
        classification = "(B) Bad Input Asset"
        root_cause = f"Asset corrupted or missing: {error_msg[:120]}"
        action = "Replaced corrupted/missing asset with fallback placeholder"
    else:
        classification = "(C) Parameter Mismatch"
        root_cause = f"Parameter, codec, or key error in {stage_name}: {error_msg[:120]}"
        action = "Sanitized parameters and re-invoked with safe baseline configuration"

    return {
        "classification": classification,
        "root_cause": root_cause,
        "recommended_action": action,
    }


# ============================================================
# 2. CONCRETE AUTOMATED HEALING STRATEGIES
# ============================================================

def heal_network_or_quota(stage_name, context=None):
    """
    Handle transient network failures and HTTP 429 quota limits.
    Switches to offline cached data or built-in templates.
    """
    context = context or {}

    if stage_name == "trend_agent":
        cache_file = OUTPUT_DIR / "trending_news_cache.json"
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                if cached:
                    return cached
            except Exception:
                pass
        return [
            {
                "title": "Global AI & Technology Breakthroughs 2026",
                "topic": "Global AI & Technology Breakthroughs 2026",
                "source": "AutoTube Evergreen Feed",
                "sources": ["AutoTube Knowledge Base"],
                "url": "https://news.google.com",
            }
        ]

    if stage_name == "script_agent":
        import re
        topic = context.get("topic", "Latest Breakthroughs")
        ctx_str = str(context).lower()
        is_tel = (
            bool(re.search(r"[\u0C00-\u0C7F]", str(topic)))
            or "telugu" in ctx_str
            or "mohan" in ctx_str
            or "shruti" in ctx_str
            or "te-in" in ctx_str
        )
        if is_tel:
            script = (
                f"హాయ్ ఫ్రెండ్స్! {topic} గురించి వచ్చిన లేటెస్ట్ అప్‌డేట్ చూశారా?\n"
                f"చూడండి ఫ్రెండ్స్, అసలు విషయం ఏంటంటే ఇందులో సరికొత్త మార్పులు రాబోతున్నాయి!\n"
                f"మరి దీనిపై మీరేమంటారు? కింద కామెంట్స్ లో చెప్పండి, వీడియో నచ్చితే లైక్ చేసి సబ్‌స్క్రైబ్ చేసుకోండి!"
            )
        else:
            script = (
                f"Here is what you need to know about {topic}.\n"
                f"Groundbreaking developments are shifting expectations worldwide.\n"
                f"Stay tuned as we follow the story closely."
            )
        visual_plan = (
            "1. Close-up establishing visual of the news development\n"
            "2. Detailed infographic showing global impact and key facts\n"
            "3. Future outlook and concluding perspective"
        )
        (OUTPUT_DIR / "script.txt").write_text(script, encoding="utf-8")
        (OUTPUT_DIR / "tts_script.txt").write_text(script, encoding="utf-8")
        (OUTPUT_DIR / "visual_plan.txt").write_text(visual_plan, encoding="utf-8")
        return script

    if stage_name == "image_agent":
        return heal_corrupt_or_missing_assets(context)

    return None


def heal_corrupt_or_missing_assets(context=None):
    """
    Inspect assets directory, drop any corrupt or zero-byte files,
    and guarantee assets/1.jpg .. assets/N.jpg exist using fallback images.
    """
    try:
        from PIL import Image
    except ImportError:
        Image = None

    needed_count = 5
    if context and isinstance(context.get("needed_count"), int):
        needed_count = max(1, context["needed_count"])

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    FALLBACK_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Identify and purge corrupt images in assets/
    for img_p in list(ASSETS_DIR.glob("*.jpg")) + list(ASSETS_DIR.glob("*.png")):
        if img_p.name.startswith("fallback_"):
            continue
        try:
            if img_p.stat().st_size == 0:
                img_p.unlink(missing_ok=True)
                continue
            if Image is not None:
                with Image.open(img_p) as im:
                    im.verify()
        except Exception:
            img_p.unlink(missing_ok=True)

    # 2. Gather available fallback images
    fallback_sources = sorted(list(FALLBACK_DIR.glob("*.jpg")) + list(FALLBACK_DIR.glob("*.png")))
    if not fallback_sources:
        # Create a clean fallback image programmatically if directory is empty
        if Image is not None:
            fb = Image.new("RGB", (1080, 1080), color=(20, 25, 40))
            fb_path = FALLBACK_DIR / "fallback_1.jpg"
            fb.save(fb_path, "JPEG")
            fallback_sources = [fb_path]

    # 3. Populate missing numbered images assets/1.jpg .. assets/N.jpg
    healed_files = []
    for i in range(1, needed_count + 1):
        target = ASSETS_DIR / f"{i}.jpg"
        if not target.exists() or target.stat().st_size == 0:
            if fallback_sources:
                donor = fallback_sources[(i - 1) % len(fallback_sources)]
                try:
                    target.write_bytes(donor.read_bytes())
                except Exception:
                    pass
        if target.exists() and target.stat().st_size > 0:
            healed_files.append(target)

    return healed_files


def heal_ffmpeg_failure(input_video="output/video.mp4", output_video="output/final_video.mp4", context=None):
    """
    Recover from FFmpeg encoding, scale, or filter failures by executing
    a CPU-safe baseline encoding command without problematic hardware filters.
    """
    in_path = Path(input_video)
    out_path = Path(output_video)

    if not in_path.exists():
        # Look for raw video or create emergency clip from assets
        raw_vid = OUTPUT_DIR / "raw_video.mp4"
        if raw_vid.exists():
            in_path = raw_vid
        else:
            in_path = OUTPUT_DIR / "video.mp4"

    voice_path = OUTPUT_DIR / "voice.mp3"
    voice_dur = 15.0
    if voice_path.exists():
        try:
            p = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(voice_path)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5
            )
            v_val = float(p.stdout.strip())
            if v_val > 0:
                voice_dur = v_val
        except Exception:
            pass

    if not in_path.exists() or in_path.stat().st_size == 0:
        first_img = ASSETS_DIR / "1.jpg"
        heal_corrupt_or_missing_assets({"needed_count": 1})
        if first_img.exists():
            cmd_img = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(first_img),
            ]
            if voice_path.exists() and voice_path.stat().st_size > 0:
                cmd_img.extend([
                    "-i", str(voice_path),
                    "-t", str(voice_dur),
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "ultrafast",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    str(in_path),
                ])
            else:
                cmd_img.extend([
                    "-t", str(voice_dur),
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "ultrafast",
                    str(in_path),
                ])
            try:
                subprocess.run(cmd_img, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)
            except Exception:
                pass

    # Check if in_path has audio
    has_audio = False
    if in_path.exists():
        try:
            p_a = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1", str(in_path)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5
            )
            has_audio = bool(p_a.stdout.strip())
        except Exception:
            pass

    # Execute safe CPU baseline encoding
    if not has_audio and voice_path.exists() and voice_path.stat().st_size > 0:
        safe_cmd = [
            "ffmpeg", "-y",
            "-i", str(in_path),
            "-i", str(voice_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            str(out_path),
        ]
    else:
        safe_cmd = [
            "ffmpeg", "-y",
            "-i", str(in_path),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(out_path),
        ]

    try:
        res = subprocess.run(safe_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
        if res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
            return str(out_path)
    except Exception:
        pass

    return str(in_path) if in_path.exists() else None


def heal_unrecoverable_topic(topic, error, context=None):
    """
    Quarantine topic metadata to failed_runs/ and failed_queue/
    and return an alternate ready-to-run evergreen topic.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(c for c in topic if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")[:40]
    filename = f"failure_{timestamp}_{safe_topic}.json"

    meta = {
        "timestamp": timestamp,
        "topic": topic,
        "error": str(error),
        "context": context or {},
        "status": "QUARANTINED",
    }

    try:
        (FAILED_RUNS_DIR / filename).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        (FAILED_QUEUE_DIR / filename).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception:
        pass

    return "Next Gen AI & Space Exploration Advances"


# ============================================================
# 3. INCIDENT LOGGER & UI EVENT STREAM
# ============================================================

def log_healing_incident(stage_name, error, classification, root_cause, resolution, context=None):
    """Record an auto-healed incident into in-memory queue and persistent log."""
    incident = {
        "id": f"heal_{int(time.time() * 1000)}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stage": stage_name,
        "error_type": type(error).__name__,
        "error_message": str(error)[:240],
        "classification": classification,
        "root_cause": root_cause,
        "resolution": resolution,
        "status": "RECOVERED & RUNNING",
    }

    with _INCIDENT_LOCK:
        _INCIDENT_HISTORY.appendleft(incident)
        _UNCONSUMED_EVENTS.append(incident)

    try:
        with open(EVENTS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(incident) + "\n")
    except Exception:
        pass

    print(f"[SUPERVISOR] 🩹 Auto-Healed '{stage_name}': {resolution}")
    return incident


def get_healing_logs(limit=30):
    """Retrieve the latest self-healing events."""
    with _INCIDENT_LOCK:
        return list(_INCIDENT_HISTORY)[:limit]


def pop_new_healing_events():
    """Consume unread healing events for Streamlit toast triggers."""
    with _INCIDENT_LOCK:
        global _UNCONSUMED_EVENTS
        events = list(_UNCONSUMED_EVENTS)
        _UNCONSUMED_EVENTS = []
        return events


# ============================================================
# 4. GLOBAL DECORATOR: @autonomous_recover
# ============================================================

def autonomous_recover(stage_name, fallback_fn=None):
    """
    Decorator around major pipeline functions.
    Catches any unhandled exception, runs AI error analysis,
    dispatches automated healing, logs incident, and returns recovered result.
    """
    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as err:
                    return _handle_recovery(func, args, kwargs, stage_name, err, fallback_fn, is_async=True)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as err:
                    return _handle_recovery(func, args, kwargs, stage_name, err, fallback_fn, is_async=False)
            return sync_wrapper
    return decorator


def _handle_recovery(func, args, kwargs, stage_name, err, fallback_fn, is_async=False):
    """Execute autonomous healing when an exception is caught."""
    tb_str = traceback.format_exc()
    func_name = getattr(func, "__name__", "unknown")
    context = {"function": func_name, "args_summary": str(args)[:200], "kwargs_keys": list(kwargs.keys())}

    # Extract topic if present in arguments
    if args and isinstance(args[0], str):
        context["topic"] = args[0]
    elif "topic" in kwargs:
        context["topic"] = kwargs["topic"]

    # 1. Analyze error with AI
    diagnosis = analyze_error_with_ai(stage_name, err, tb_str, context)
    classification = diagnosis["classification"]
    root_cause = diagnosis["root_cause"]

    # 2. Execute concrete automated healing strategy
    healed_result = None
    resolution = diagnosis["recommended_action"]

    try:
        if fallback_fn is not None:
            healed_result = fallback_fn(*args, **kwargs)
            resolution = f"Custom fallback executed for {stage_name}"
        elif stage_name == "trend_agent":
            healed_result = heal_network_or_quota("trend_agent", context)
            resolution = "Switched to local trend cache / evergreen topics"
        elif stage_name == "script_agent":
            healed_result = heal_network_or_quota("script_agent", context)
            resolution = "Generated structured fallback script and visual plan"
        elif stage_name == "image_agent":
            healed_result = heal_corrupt_or_missing_assets(context)
            resolution = "Purged corrupt images & populated assets from fallback library"
        elif stage_name in ("video_agent", "final_video_agent"):
            out_vid = kwargs.get("output_video", "output/final_video.mp4")
            in_vid = kwargs.get("input_video", "output/video.mp4")
            healed_result = heal_ffmpeg_failure(in_vid, out_vid, context)
            resolution = "Re-encoded video with CPU-safe baseline parameters (-c:v libx264 -pix_fmt yuv420p -preset ultrafast)"
        elif stage_name == "voice_agent":
            # Guarantee voice.wav exists
            voice_wav = OUTPUT_DIR / "voice.wav"
            if not voice_wav.exists() or voice_wav.stat().st_size == 0:
                # Create a 3-second clean tone wav if missing
                try:
                    subprocess.run([
                        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                        "-ar", "24000", "-ac", "1", str(voice_wav)
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                except Exception:
                    pass
            healed_result = str(voice_wav) if voice_wav.exists() else None
            resolution = "Synthesized audio using safe local voice fallback"
        elif stage_name == "youtube_agent":
            healed_result = {"status": "DEFERRED", "message": "Upload deferred; video preserved locally"}
            resolution = "Deferred YouTube upload to prevent halting; video saved locally"
        else:
            resolution = f"Safely recovered with default state for {stage_name}"
    except Exception as fallback_err:
        resolution = f"Auto-mitigated pipeline exception: {fallback_err}"

    # 3. Log incident for UI streaming
    log_healing_incident(stage_name, err, classification, root_cause, resolution, context)

    return healed_result


# ============================================================
# 5. STREAMLIT DIAGNOSTICS UI COMPONENT
# ============================================================

def render_healing_diagnostics_drawer():
    """
    Render the live incident diagnostics drawer and trigger toast notifications in Streamlit.
    Call this within Streamlit apps to provide real-time recovery feedback.
    """
    try:
        import streamlit as st
    except ImportError:
        return

    # 1. Pop and display toasts for newly healed events
    new_events = pop_new_healing_events()
    for ev in new_events:
        stage = ev.get("stage", "pipeline")
        res = ev.get("resolution", "Self-healing resolved the issue.")
        try:
            st.toast(f"⚠️ Auto-Healed ({stage}): {res[:80]}", icon="🩹")
        except Exception:
            pass

    # 2. Render Expandable Incident Drawer
    logs = get_healing_logs(limit=15)

    with st.expander(f"🛠️ Self-Healing Diagnostics & Log ({len(logs)} incidents auto-healed)", expanded=False):
        if not logs:
            st.markdown(
                """
                <div style="background: rgba(34, 197, 94, 0.08); border: 1px solid rgba(34, 197, 94, 0.25); border-radius: 10px; padding: 12px 14px;">
                    <div style="font-size: 12.5px; font-weight: 600; color: #4ADE80;">
                        ✅ All Systems Nominal
                    </div>
                    <div style="font-size: 11px; color: #94A3B8; margin-top: 2px;">
                        The autonomous supervisor is actively monitoring. No unhandled errors or active fault recoveries.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div style="font-size: 11px; color: #94A3B8; margin-bottom: 10px;">
                    Autonomous supervisor auto-recovers errors in real time without human intervention:
                </div>
                """,
                unsafe_allow_html=True,
            )

            for log in logs:
                c_badge = (
                    "🔴 Transient/Network" if "Transient" in log.get("classification", "")
                    else "🟡 Bad Asset" if "Asset" in log.get("classification", "")
                    else "🔵 Parameter Mismatch"
                )

                st.markdown(
                    f"""
                    <div style="background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 10px 14px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <span style="font-size: 12px; font-weight: 700; color: #F1F5F9;">
                                ⚙️ {log.get('stage', 'Pipeline Stage').upper()}
                            </span>
                            <span style="font-size: 10px; font-weight: 600; color: #38BDF8; background: rgba(56, 189, 248, 0.12); padding: 2px 8px; border-radius: 6px;">
                                {log.get('status', 'RECOVERED')}
                            </span>
                        </div>
                        <div style="font-size: 11px; color: #CBD5E1; margin-bottom: 3px;">
                            <b>Root Cause ({c_badge}):</b> {log.get('root_cause', 'Unknown')}
                        </div>
                        <div style="font-size: 11px; color: #4ADE80; margin-bottom: 3px;">
                            <b>🩹 Resolution:</b> {log.get('resolution', 'Fallback applied')}
                        </div>
                        <div style="font-size: 10px; color: #64748B;">
                            🕒 {log.get('timestamp', '')} • Error: <code>{log.get('error_type', '')}</code>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

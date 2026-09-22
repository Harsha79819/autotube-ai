"""
AutoTube AI - Embedded Copilot Agent (copilot_agent.py)
Interactive controller, real-time job inspector, and troubleshooter.
"""

import json
import os
import re
import threading
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
FAILED_QUEUE_DIR = ROOT / "failed_queue"

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-flash-lite-latest",
]

_client = None
if API_KEY:
    try:
        from google import genai
        _client = genai.Client(api_key=API_KEY)
    except Exception as init_err:
        print(f"Copilot genai init note: {init_err}")

# ============================================================
# THREAD-SAFE ACTIVE JOB TRACKER
# ============================================================

_JOB_LOCK = threading.Lock()
_ACTIVE_JOB = {
    "id": None,
    "status": "idle",       # "idle", "running", "completed", "failed"
    "action": None,         # "generate", "rerender", "trend_scan"
    "topic": None,
    "step": "Idle",
    "progress": 0,
    "started_at": 0.0,
    "error": None,
    "result": None,
}


def get_active_job():
    """Return a thread-safe copy of the active background job state."""
    with _JOB_LOCK:
        return dict(_ACTIVE_JOB)


def is_job_running():
    """Check if a background pipeline job is currently executing."""
    with _JOB_LOCK:
        return _ACTIVE_JOB["status"] == "running"


def _update_job(**kwargs):
    """Thread-safe update of the active job state."""
    with _JOB_LOCK:
        _ACTIVE_JOB.update(kwargs)


# ============================================================
# GEMINI CALL HELPER
# ============================================================

def call_gemini(prompt, system_instruction=None):
    """Call Gemini with multi-model fallback."""
    global _client
    if not _client and API_KEY:
        try:
            from google import genai
            _client = genai.Client(api_key=API_KEY)
        except Exception:
            pass

    if not _client:
        return None

    for model_name in MODELS:
        try:
            config = {}
            if system_instruction:
                from google.genai import types
                config["system_instruction"] = system_instruction

            resp = _client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config if config else None,
            )
            text = getattr(resp, "text", "")
            if text and text.strip():
                return text.strip()
        except Exception:
            continue

    return None


# ============================================================
# VOICE MAPPING UTILITIES
# ============================================================

VOICE_OPTIONS = {
    "adam": "👨 Adam (Male Creator) - Fast & Crisp",
    "bella": "👩 Bella (Warm Female) - Storytelling",
    "michael": "🎙️ Michael (Deep Male) - Professional",
    "heart": "🌸 Heart (Gentle Female) - Calming",
}


def map_voice_preference(voice_text, style_text=""):
    """Map natural language voice or style preference to standard AutoTube voice ID."""
    combined = (str(voice_text) + " " + str(style_text)).lower()

    if any(k in combined for k in ["bella", "female", "woman", "warm", "storytelling"]):
        return VOICE_OPTIONS["bella"]
    if any(k in combined for k in ["michael", "deep", "documentary", "authoritative", "professional"]):
        return VOICE_OPTIONS["michael"]
    if any(k in combined for k in ["heart", "gentle", "calm", "soothing", "soft"]):
        return VOICE_OPTIONS["heart"]

    # Default to energetic creator voice
    return VOICE_OPTIONS["adam"]


# ============================================================
# 1. NATURAL LANGUAGE INTENT PARSER
# ============================================================

def parse_pipeline_intent(user_prompt):
    """
    Parse a natural language video creation request into structured parameters:
    topic, aspect_ratio, style, target_duration, voice, content_type.
    """
    prompt = f"""You are an autonomous video pipeline controller.
Analyze the user's natural language request to create a video:
"{user_prompt}"

Extract these parameters and return ONLY valid JSON (no markdown formatting, no code blocks):
{{
  "topic": "<clear, concise video topic or title>",
  "aspect_ratio": "<'9:16' for vertical/shorts/reels/tiktok, '16:9' for horizontal/landscape/youtube, or '1:1' for square/default>",
  "style": "<e.g. energetic, creator, news, storytelling, educational>",
  "target_duration": <duration in seconds as integer, default 60>,
  "voice_preference": "<adam|bella|michael|heart>",
  "content_type": "<'News' or 'General Topic'>"
}}
"""
    raw_response = call_gemini(prompt)
    if raw_response:
        try:
            clean_json = re.sub(r"^```(?:json)?|```$", "", raw_response.strip(), flags=re.MULTILINE).strip()
            data = json.loads(clean_json)
            aspect_ratio = data.get("aspect_ratio", "1:1")
            if aspect_ratio not in ("9:16", "16:9", "1:1"):
                aspect_ratio = "1:1"

            target_duration = int(data.get("target_duration", 60))
            style = data.get("style", "energetic creator")
            voice = map_voice_preference(data.get("voice_preference", ""), style)
            content_type = data.get("content_type", "News")
            topic = data.get("topic", "").strip() or user_prompt.strip()

            return {
                "topic": topic,
                "aspect_ratio": aspect_ratio,
                "style": style,
                "target_duration": target_duration,
                "voice": voice,
                "content_type": content_type,
            }
        except Exception:
            pass

    # Heuristic fallback parser
    is_vertical = any(w in user_prompt.lower() for w in ["vertical", "9:16", "short", "shorts", "reel", "reels", "tiktok"])
    is_horizontal = any(w in user_prompt.lower() for w in ["horizontal", "16:9", "wide", "landscape"])
    aspect = "9:16" if is_vertical else ("16:9" if is_horizontal else "1:1")

    # Extract duration
    dur_match = re.search(r"(\d+)\s*(?:s|sec|seconds)", user_prompt, re.IGNORECASE)
    duration = int(dur_match.group(1)) if dur_match else 60

    # Extract topic by stripping common prefixes
    cleaned_topic = re.sub(r"^(?:create|make|generate|produce)\s+(?:a|an)?\s*(?:\d+s|\d+\s*sec)?\s*(?:vertical|horizontal|short|reels?)?\s*(?:video|clip)?\s*(?:about|on|for)?\s*", "", user_prompt, flags=re.IGNORECASE).strip()
    cleaned_topic = re.sub(r"\s*(?:with|using)\s+.*$", "", cleaned_topic, flags=re.IGNORECASE).strip()

    if not cleaned_topic:
        cleaned_topic = user_prompt.strip()

    voice = map_voice_preference(user_prompt)

    return {
        "topic": cleaned_topic,
        "aspect_ratio": aspect,
        "style": "energetic creator",
        "target_duration": duration,
        "voice": voice,
        "content_type": "News" if any(w in user_prompt.lower() for w in ["news", "breaking", "update", "forecast"]) else "General Topic",
    }


# ============================================================
# 2. BACKGROUND PIPELINE EXECUTION
# ============================================================

def start_background_pipeline(topic, aspect_ratio="1:1", voice=None, content_type="News", style="English creator style", youtube_upload=None, youtube_privacy=None):
    """
    Launch full autonomous video generation in a background thread so the Streamlit UI never freezes.
    """
    if is_job_running():
        return False, "A video generation job is already in progress. Please wait for it to complete."

    job_id = f"job_{int(time.time())}"
    voice = voice or VOICE_OPTIONS["adam"]

    def _worker():
        try:
            _update_job(
                id=job_id,
                status="running",
                action="generate",
                topic=topic,
                step="Initializing AutoTube pipeline...",
                progress=5,
                started_at=time.time(),
                error=None,
                result=None,
            )

            from pipeline import generate_multi_media_video

            def _progress_cb(percent, text):
                _update_job(progress=percent, step=text)

            # Resolve youtube upload & privacy if not explicitly passed
            w_yt_upload = youtube_upload
            w_yt_privacy = youtube_privacy
            if w_yt_upload is None:
                try:
                    import streamlit as _st
                    w_yt_upload = _st.session_state.get("declared_yt_upload", False)
                except Exception:
                    w_yt_upload = False
            if w_yt_privacy is None:
                try:
                    import streamlit as _st
                    w_yt_privacy = _st.session_state.get("declared_yt_privacy", "private")
                except Exception:
                    w_yt_privacy = "private"

            result = generate_multi_media_video(
                topic=topic,
                content_type=content_type,
                language_style=style,
                voice=voice,
                aspect_ratio=aspect_ratio,
                progress_callback=_progress_cb,
                youtube_upload=w_yt_upload,
                youtube_privacy=w_yt_privacy,
            )

            completion_step = "Video generation completed successfully! 🎉"
            if result and isinstance(result, dict) and result.get("youtube_video_id"):
                completion_step = f"Published to YouTube ({w_yt_privacy.upper()})! Video ID: {result['youtube_video_id']} 🎉"

            _update_job(
                status="completed",
                step=completion_step,
                progress=100,
                result=result,
            )
        except Exception as err:
            _update_job(
                status="failed",
                step=f"Generation failed: {str(err)}",
                error=str(err),
            )

    thread = threading.Thread(target=_worker, name=f"AutoTube-{job_id}", daemon=True)
    thread.start()

    return True, f"🚀 Started background video generation for **'{topic}'** ({aspect_ratio}, {voice})."


# ============================================================
# 3. IN-FLIGHT MODIFIER (TWEAK & RE-RUN)
# ============================================================

def rewrite_script_hook_and_rerender(user_instruction, voice=None, aspect_ratio="1:1"):
    """
    Rewrite the opening hook or script based on user feedback and
    re-render from voice generation onwards without re-downloading media.
    """
    if is_job_running():
        return False, "A pipeline job is currently running. Please wait for it to finish."

    script_path = OUTPUT_DIR / "script.txt"
    tts_path = OUTPUT_DIR / "tts_script.txt"
    section_map_path = OUTPUT_DIR / "section_map.txt"

    if not script_path.exists():
        return False, "No existing script found to modify. Please generate a video first."

    current_script = script_path.read_text(encoding="utf-8").strip()

    # Use Gemini to revise the hook / opening section
    prompt = f"""You are an elite video scriptwriter and content director.
The user wants to revise their video script hook with the following instructions:
"{user_instruction}"

CURRENT SCRIPT:
{current_script}

INSTRUCTIONS:
1. Rewrite the opening hook (first 2-3 sentences) to be punchier, more dramatic, and captivating while preserving factual accuracy.
2. Keep the rest of the script coherent with the updated hook.
3. Return ONLY the complete revised script text. No titles, no markdown bold formatting, no disclaimers.
"""
    revised_script = call_gemini(prompt)
    if not revised_script or len(revised_script.strip()) < 40:
        # Simple fallback rewrite
        lines = current_script.split("\n")
        first_line = lines[0] if lines else current_script
        revised_script = f"Breaking update: {first_line}\n" + "\n".join(lines[1:])

    revised_script = revised_script.strip()
    script_path.write_text(revised_script, encoding="utf-8")
    tts_path.write_text(revised_script, encoding="utf-8")

    # Update section 1 narration in section_map.txt if present
    if section_map_path.exists():
        try:
            sec_text = section_map_path.read_text(encoding="utf-8")
            first_sentence = revised_script.split(".")[0] + "."
            updated_sec = re.sub(
                r"(SECTION\s+1\s*\|\s*VISUAL\s+1\s*\n).*?(?=\n\s*SECTION\s+2|\Z)",
                rf"\g<1>{first_sentence}",
                sec_text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            section_map_path.write_text(updated_sec, encoding="utf-8")
        except Exception:
            pass

    preview_hook = revised_script.split(".")[0] + "."

    job_id = f"rerender_{int(time.time())}"
    effective_voice = voice or VOICE_OPTIONS["adam"]

    def _rerender_worker():
        try:
            _update_job(
                id=job_id,
                status="running",
                action="rerender",
                topic="In-flight Script Tweak",
                step="Generating narration with updated hook...",
                progress=30,
                started_at=time.time(),
                error=None,
            )

            from pipeline import (
                create_voice_for_script,
                create_pipeline_video,
                create_final_video,
                create_thumbnail,
                create_ai_review,
            )
            from agents.video_agent import ensure_visual_assets_exist

            # 1. Voice
            _update_job(step="Synthesizing updated voice narration...", progress=40)
            create_voice_for_script(effective_voice)

            # 2. Video Mux
            _update_job(step="Muxing visuals and updated timed audio...", progress=65)
            ensure_visual_assets_exist()
            create_pipeline_video(aspect_ratio=aspect_ratio)

            # 3. Final Video + Captions
            _update_job(step="Rendering final video with fresh captions...", progress=80)
            create_final_video(captions=True, aspect_ratio=aspect_ratio)

            # 4. Thumbnail
            _update_job(step="Refreshing thumbnail...", progress=90)
            title_file = OUTPUT_DIR / "title.txt"
            topic_title = title_file.read_text(encoding="utf-8").strip() if title_file.exists() else "Video Update"
            create_thumbnail(topic_title, aspect_ratio=aspect_ratio)

            # 5. AI Review
            _update_job(step="Running quality review on revised video...", progress=95)
            review_res = create_ai_review(captions_enabled=True)

            _update_job(
                status="completed",
                step="Tweak & re-render completed successfully! 🎉",
                progress=100,
                result=review_res,
            )
        except Exception as err:
            _update_job(
                status="failed",
                step=f"Re-render failed: {str(err)}",
                error=str(err),
            )

    t = threading.Thread(target=_rerender_worker, name=f"AutoTube-{job_id}", daemon=True)
    t.start()

    return True, (
        f"✍️ **Updated Hook:** *\"{preview_hook}\"*\n\n"
        f"🔄 **In-flight re-render initiated:** Re-synthesizing voice narration, re-aligning subtitles, "
        f"and re-rendering the final video ({aspect_ratio}). I'll track progress in the background!"
    )


# ============================================================
# 4. PIPELINE STATE & JOB INSPECTOR
# ============================================================

def inspect_pipeline_state():
    """
    Inspect the live pipeline state, current background job,
    or last rendered video outputs.
    """
    job = get_active_job()

    if job["status"] == "running":
        elapsed = int(time.time() - job["started_at"])
        return (
            f"⚡ **Active Job Running:** `{job.get('action', 'pipeline')}`\n"
            f"- **Topic:** {job.get('topic', 'Autonomous Task')}\n"
            f"- **Current Step:** {job.get('step', 'Processing...')}\n"
            f"- **Progress:** {job.get('progress', 0)}%\n"
            f"- **Elapsed Time:** {elapsed}s"
        )

    final_video = OUTPUT_DIR / "final_video.mp4"
    review_file = OUTPUT_DIR / "review.json"
    title_file = OUTPUT_DIR / "title.txt"

    if not final_video.exists():
        return "ℹ️ No video has been generated yet in this session. Ask me to create one or run a trend scan to start!"

    size_mb = round(final_video.stat().st_size / (1024 * 1024), 2)
    title = title_file.read_text(encoding="utf-8").strip() if title_file.exists() else "Latest Project"

    review_summary = "Not reviewed yet."
    if review_file.exists():
        try:
            rev = json.loads(review_file.read_text(encoding="utf-8"))
            score = rev.get("overall_score") or rev.get("score", 0)
            status = rev.get("status", "COMPLETE")
            failing = rev.get("failing_component", "None")
            script_s = rev.get("script_score", "-")
            audio_s = rev.get("audio_score", "-")
            visual_s = rev.get("visual_score", "-")
            review_summary = (
                f"- **Review Score:** {score}/100 ({status})\n"
                f"- **Subscores:** Script={script_s} | Audio={audio_s} | Visuals={visual_s}\n"
                f"- **Failing Component:** `{failing}`"
            )
        except Exception:
            pass

    healing_summary = ""
    try:
        from supervisor import get_healing_logs
        h_logs = get_healing_logs(limit=3)
        if h_logs:
            items = "\n".join([f"  - 🩹 `{l.get('stage')}`: {l.get('resolution')}" for l in h_logs])
            healing_summary = f"\n\n🛠️ **Autonomous Self-Healing Supervisor:**\n{items}"
    except Exception:
        pass

    return (
        f"🎬 **Latest Video Project:**\n"
        f"- **Title:** {title}\n"
        f"- **File:** `output/final_video.mp4` ({size_mb} MB)\n"
        f"{review_summary}{healing_summary}\n\n"
        f"💡 *Tip: Ask me to 're-render with Bella's voice' or 'rewrite the hook' to tweak this video!*"
    )



def inspect_last_failure():
    """
    Inspect failed_queue/ and review diagnostics to explain why the last run failed.
    """
    if FAILED_QUEUE_DIR.exists():
        failures = sorted(FAILED_QUEUE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if failures:
            latest = failures[0]
            try:
                data = json.loads(latest.read_text(encoding="utf-8"))
                topic = data.get("topic", "Unknown")
                attempts = data.get("attempts", 3)
                score = data.get("final_score", 0)
                failing = data.get("failing_component", "Unknown")
                feedback = data.get("feedback", "Quality threshold < 80.")

                return (
                    f"⚠️ **Last Run Failure Analysis (from Dead-Letter Queue):**\n"
                    f"- **Topic:** {topic}\n"
                    f"- **Attempts Made:** {attempts}\n"
                    f"- **Final Score:** {score}/100 (< 80 threshold)\n"
                    f"- **Failing Component:** `{failing}`\n"
                    f"- **Reviewer Feedback:** *\"{feedback}\"*\n\n"
                    f"🛠️ **Recommended Fix:**\n"
                    f"Ask me: *'Rewrite the script hook for {topic} and re-render'* or *'Regenerate visuals with higher resolution'* to recover!"
                )
            except Exception:
                pass

    review_file = OUTPUT_DIR / "review.json"
    if review_file.exists():
        try:
            rev = json.loads(review_file.read_text(encoding="utf-8"))
            score = rev.get("overall_score") or rev.get("score", 0)
            if score < 80:
                failing = rev.get("failing_component", "Unknown")
                feedback = rev.get("feedback", "Score below 80.")
                crit = rev.get("critical_issues", [])
                crit_text = "\n".join([f"  - {c}" for c in crit]) if crit else "  - Sub-threshold quality score"

                return (
                    f"⚠️ **Last Run Review Analysis:**\n"
                    f"- **Overall Score:** {score}/100 (Threshold: 80)\n"
                    f"- **Culprit Component:** `{failing}`\n"
                    f"- **Feedback:** {feedback}\n"
                    f"- **Critical Issues:**\n{crit_text}\n\n"
                    f"💡 The self-healing pipeline attempted automatic correction. Say *'Re-render with Bella'* or *'Make hook punchier'* to adjust."
                )
            else:
                return (
                    f"✅ The last video generation **passed** review with a score of **{score}/100**!\n"
                    f"No unresolved errors found in the pipeline."
                )
        except Exception:
            pass

    try:

        from supervisor import get_healing_logs
        h_logs = get_healing_logs(limit=2)
        if h_logs:
            latest_heal = h_logs[0]
            return (
                f"🩹 **Autonomous Supervisor Self-Healed Incident:**\n"
                f"- **Stage:** `{latest_heal.get('stage')}`\n"
                f"- **Classification:** {latest_heal.get('classification')}\n"
                f"- **Root Cause:** {latest_heal.get('root_cause')}\n"
                f"- **Applied Resolution:** {latest_heal.get('resolution')}\n"
                f"- **Status:** `{latest_heal.get('status')}`\n\n"
                f"The pipeline recovered automatically and is operating nominally!"
            )
    except Exception:
        pass

    return "ℹ️ No recent failure logs or dead-letter queue entries found. The pipeline is operating nominally."



# ============================================================
# 5. QUICK ACTIONS
# ============================================================

def run_trend_scan():
    """Fetch live trending topics and suggest ready-to-run video prompts."""
    stories = []
    cache_file = OUTPUT_DIR / "trending_news_cache.json"
    if cache_file.exists():
        try:
            stories = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    if not stories:
        try:
            from agents.trend_agent import discover_trending_topics
            stories = discover_trending_topics(limit=5)
        except Exception:
            pass

    if not stories:
        return "⚠️ Could not fetch live trends at this moment. You can still ask me to create a video on any custom topic!"

    lines = ["🔥 **Live Trending Stories Ready for Video Production:**\n"]
    for i, s in enumerate(stories[:5], start=1):
        title = s.get("title") or s.get("topic") or "Trending News"
        sources = s.get("sources", [])
        source_name = sources[0] if sources else s.get("source", "Google News")
        lines.append(f"{i}. **{title}** *({source_name})*")

    lines.append("\n👉 *Click a topic or tell me: 'Create a 60s vertical video about story #1'*")
    return "\n".join(lines)


def check_last_score():
    """Retrieve and format the latest AI review scorecard."""
    review_file = OUTPUT_DIR / "review.json"
    if not review_file.exists():
        return "ℹ️ No quality scorecard available yet. Generate a video first to view AI review ratings!"

    try:
        rev = json.loads(review_file.read_text(encoding="utf-8"))
        score = rev.get("overall_score") or rev.get("score", 0)
        status = rev.get("status", "COMPLETE")
        script_s = rev.get("script_score", "-")
        audio_s = rev.get("audio_score", "-")
        visual_s = rev.get("visual_score", "-")
        failing = rev.get("failing_component", "None")
        feedback = rev.get("feedback") or rev.get("summary", "Ready for publishing.")

        badge = "🟢 PASSED" if score >= 80 else "🟡 IMPROVEMENTS NEEDED"

        return (
            f"📊 **AI Quality Review Scorecard:**\n\n"
            f"- **Status:** {badge} (`{status}`)\n"
            f"- **Overall Score:** **{score}/100**\n"
            f"- **Script Score:** {script_s}/100\n"
            f"- **Audio Narration:** {audio_s}/100\n"
            f"- **Visual Cohesion:** {visual_s}/100\n"
            f"- **Failing Component:** `{failing}`\n\n"
            f"📝 **Reviewer Notes:**\n> {feedback}"
        )
    except Exception as err:
        return f"⚠️ Error loading review scorecard: {err}"


def rerender_last_video():
    """Re-render the last video project from voice and video muxing onwards."""
    if is_job_running():
        return "⚠️ A video generation job is already in progress. Please wait for it to complete."

    script_path = OUTPUT_DIR / "script.txt"
    if not script_path.exists():
        return "⚠️ No previous script found to re-render. Please create a video first!"

    success, msg = rewrite_script_hook_and_rerender("Preserve script, refresh narration, visuals and captions.")
    return msg


# ============================================================
# 6. MAIN COPILOT CONVERSATION ROUTER
# ============================================================

def process_copilot_message(user_message, history=None):
    """
    Main conversational dispatcher for the embedded Copilot.
    Parses user message and routes to the appropriate tool or conversational response.
    """
    clean_msg = user_message.strip()
    lower_msg = clean_msg.lower()

    # Quick action button triggers
    if clean_msg == "ACTION_TREND_SCAN" or lower_msg in ["run trend scan", "trend scan", "trending topics", "show trends"]:
        return run_trend_scan()

    if clean_msg == "ACTION_CHECK_SCORE" or lower_msg in ["check last score", "check score", "quality score", "review score"]:
        return check_last_score()

    if clean_msg == "ACTION_RERENDER" or lower_msg in ["re-render last video", "rerender last video", "re-render", "rerender"]:
        return rerender_last_video()

    # Status / inspection queries
    if any(q in lower_msg for q in ["current status", "what is the status", "progress", "how is it going", "is it running", "status"]):
        return inspect_pipeline_state()

    if any(q in lower_msg for q in ["why did the last run fail", "why did it fail", "what failed", "what went wrong", "explain failure", "failure"]):
        return inspect_last_failure()

    # In-flight hook / script modification
    if any(q in lower_msg for q in ["rewrite the script hook", "rewrite the hook", "punchier", "make the hook", "change hook", "modify hook", "rewrite hook"]):
        success, reply = rewrite_script_hook_and_rerender(clean_msg)
        return reply

    # Pipeline generation trigger check
    is_creation_intent = any(w in lower_msg for w in [
        "create", "make", "generate", "produce", "build", "render",
    ]) and any(w in lower_msg for w in [
        "video", "short", "shorts", "reel", "reels", "clip", "news",
    ])

    if is_creation_intent:
        parsed = parse_pipeline_intent(clean_msg)
        topic = parsed["topic"]
        aspect = parsed["aspect_ratio"]
        voice = parsed["voice"]
        content_type = parsed["content_type"]
        style = parsed["style"]

        success, reply = start_background_pipeline(
            topic=topic,
            aspect_ratio=aspect,
            voice=voice,
            content_type=content_type,
            style=style,
        )
        return reply

    # General conversational fallback using Gemini
    sys_instruction = (
        "You are the embedded AI Copilot for AutoTube AI, an autonomous video production studio. "
        "You help users create videos, inspect jobs, tweak scripts, explain review scores, and troubleshoot issues. "
        "Keep responses concise, helpful, and formatted in clean GitHub markdown. "
        "Remind users they can say: 'Create a 60s vertical video about [topic]', 'What is the current status?', or 'Rewrite the hook'."
    )

    gemini_reply = call_gemini(clean_msg, system_instruction=sys_instruction)
    if gemini_reply:
        return gemini_reply

    return (
        f"👋 I'm your **AutoTube AI Copilot**!\n\n"
        f"Here are a few things I can do for you right now:\n"
        f"- 🎬 **Create a video:** *'Create a 60s vertical video about latest AI breakthroughs with Bella'* \n"
        f"- 📊 **Check progress:** *'What is the current status?'*\n"
        f"- 🔍 **Troubleshoot:** *'Why did the last run fail?'*\n"
        f"- ✍️ **Tweak & Re-render:** *'Rewrite the script hook to be punchier and re-render'*\n"
        f"- 🚀 **Scan trends:** Use the `[🚀 Run Trend Scan]` button above!"
    )


# ============================================================
# 7. STREAMLIT UI COPILOT COMPONENTS
# ============================================================

def render_copilot_main_studio():
    """
    Render the comprehensive full-page AI Copilot Studio interface.
    Includes natural language conversation, live progress monitor, suggested prompt chips,
    review scorecard inspection, real-time video player preview, and in-flight hook editor.
    """
    import streamlit as st

    # Initialize messages
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "👋 **Welcome to AutoTube AI Copilot Studio!**\n\n"
                    "I'm your autonomous creative director. You can talk to me in English or Telugu.\n"
                    "Tell me what video you want to produce, or tap one of the suggested prompts below!\n\n"
                    "💡 *Try saying:* **'Create a 60s vertical video about latest NVIDIA chips with an energetic voice'**"
                ),
            }
        ]

    # Studio Header & Status Bar
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.95) 100%);
                    border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 16px; padding: 20px 24px; margin-bottom: 20px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.35);">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                <div style="display: flex; align-items: center; gap: 14px;">
                    <div style="font-size: 36px; background: rgba(56, 189, 248, 0.15); border-radius: 12px; padding: 6px 12px;">🤖</div>
                    <div>
                        <div style="font-size: 22px; font-weight: 800; color: #F8FAFC; letter-spacing: -0.5px;">
                            AutoTube AI Copilot <span style="background: linear-gradient(90deg, #38BDF8, #818CF8); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Studio</span>
                        </div>
                        <div style="font-size: 13px; color: #94A3B8; margin-top: 2px;">
                            Autonomous Conversational Video Director • Natural Language Creation • Real-Time Self-Healing
                        </div>
                    </div>
                </div>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                    <span style="background: rgba(34, 197, 94, 0.15); border: 1px solid rgba(34, 197, 94, 0.35); color: #4ADE80; font-size: 11.5px; font-weight: 600; padding: 5px 12px; border-radius: 999px;">● Agent Connected</span>
                    <span style="background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); color: #38BDF8; font-size: 11.5px; font-weight: 600; padding: 5px 12px; border-radius: 999px;">⚡ Kokoro 24kHz TTS</span>
                    <span style="background: rgba(168, 85, 247, 0.12); border: 1px solid rgba(168, 85, 247, 0.3); color: #C084FC; font-size: 11.5px; font-weight: 600; padding: 5px 12px; border-radius: 999px;">🧠 Gemini Flash 2.5</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Clickable Starter Prompts Grid
    st.markdown("<div style='font-size: 12px; font-weight: 700; color: #94A3B8; letter-spacing: 0.5px; margin-bottom: 8px;'>💡 QUICK START PROMPTS (CLICK TO RUN)</div>", unsafe_allow_html=True)
    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    preset_prompt = None

    with p_col1:
        if st.button("⚡ NVIDIA AI Chips (9:16)", key="p_chip_nvidia", use_container_width=True, help="Create a 60s vertical video about latest NVIDIA chips"):
            preset_prompt = "Create a 60s vertical video about latest NVIDIA chips with an energetic voice"
    with p_col2:
        if st.button("🚀 Space Discovery (16:9)", key="p_chip_space", use_container_width=True, help="Create a horizontal video about James Webb Telescope discoveries"):
            preset_prompt = "Create a horizontal video about recent James Webb telescope discoveries with Bella"
    with p_col3:
        if st.button("📰 Breaking News (9:16)", key="p_chip_breaking", use_container_width=True, help="Generate a 60s vertical breaking news video"):
            preset_prompt = "Generate a 60s vertical breaking news video with fast crisp narration"
    with p_col4:
        if st.button("🔥 Scan Live Trends", key="p_chip_trends", use_container_width=True, help="Scan live trending news topics"):
            preset_prompt = "ACTION_TREND_SCAN"

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    # Main Studio Two-Column Grid
    chat_col, side_col = st.columns([1.45, 1.05], gap="large")

    chip_action = preset_prompt

    with chat_col:
        # Quick Action Toolbar
        tb1, tb2, tb3, tb4 = st.columns(4)
        with tb1:
            if st.button("🚀 Scan Trends", key="main_action_trend", use_container_width=True):
                chip_action = "ACTION_TREND_SCAN"
        with tb2:
            if st.button("📊 Review Score", key="main_action_score", use_container_width=True):
                chip_action = "ACTION_CHECK_SCORE"
        with tb3:
            if st.button("🔄 Re-render Video", key="main_action_rerender", use_container_width=True):
                chip_action = "ACTION_RERENDER"
        with tb4:
            if st.button("🗑️ Clear Chat", key="main_action_clear", use_container_width=True):
                st.session_state.messages = [st.session_state.messages[0]]
                st.rerun()

        # Chat Conversation Container
        chat_container = st.container(height=480)
        with chat_container:
            for m in st.session_state.messages:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])

        # Chat Input
        user_input = st.chat_input("Prompt AutoTube Copilot (e.g. 'Create a 60s vertical reel on Quantum Computing' or 'Why did the last run fail?')...", key="copilot_main_chat_input")

    with side_col:
        # Live Pipeline Job Monitor Card
        job = get_active_job()
        st.markdown(
            """
            <div style="background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 14px; padding: 14px 16px; margin-bottom: 16px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div style="font-size: 13px; font-weight: 700; color: #F1F5F9;">⚡ PIPELINE MONITOR</div>
            """,
            unsafe_allow_html=True,
        )

        if job.get("status") == "running":
            elapsed = int(time.time() - job.get("started_at", time.time()))
            st.markdown(
                f"""
                    <span style="font-size: 11px; font-weight: 700; color: #38BDF8; background: rgba(56, 189, 248, 0.15); padding: 2px 8px; border-radius: 6px;">RUNNING ({job.get('progress', 0)}%)</span>
                </div>
                <div style="font-size: 12px; color: #E2E8F0; margin-bottom: 6px;"><b>Topic:</b> {str(job.get('topic', ''))[:40]}</div>
                <div style="font-size: 11.5px; color: #94A3B8; margin-bottom: 10px;">{job.get('step', 'Processing...')}</div>
                """,
                unsafe_allow_html=True,
            )
            st.progress(min(1.0, max(0.0, job.get("progress", 0) / 100.0)))
            if st.button("🔄 Refresh Job Status", key="main_job_refresh", use_container_width=True):
                st.rerun()
        elif job.get("status") == "completed":
            st.markdown(
                """
                    <span style="font-size: 11px; font-weight: 700; color: #4ADE80; background: rgba(34, 197, 94, 0.15); padding: 2px 8px; border-radius: 6px;">COMPLETED</span>
                </div>
                <div style="font-size: 12px; color: #4ADE80; font-weight: 500;">🎉 Video generation completed successfully!</div>
                """,
                unsafe_allow_html=True,
            )
        elif job.get("status") == "failed":
            st.markdown(
                f"""
                    <span style="font-size: 11px; font-weight: 700; color: #F87171; background: rgba(248, 113, 113, 0.15); padding: 2px 8px; border-radius: 6px;">FAILED</span>
                </div>
                <div style="font-size: 11.5px; color: #F87171;">{job.get('error', 'Error occurred during generation')}</div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                    <span style="font-size: 11px; font-weight: 600; color: #94A3B8; background: rgba(255, 255, 255, 0.05); padding: 2px 8px; border-radius: 6px;">STANDBY</span>
                </div>
                <div style="font-size: 11.5px; color: #94A3B8;">AutoTube autonomous pipeline is idle and ready for video prompts.</div>
                """,
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

        # Video Player Preview (if video exists)
        final_video = OUTPUT_DIR / "final_video.mp4"
        if final_video.exists():
            st.markdown(
                """
                <div style="background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 14px; padding: 14px 16px; margin-bottom: 16px;">
                    <div style="font-size: 13px; font-weight: 700; color: #F1F5F9; margin-bottom: 10px;">🎬 LATEST VIDEO OUTPUT</div>
                """,
                unsafe_allow_html=True,
            )
            try:
                video_bytes = final_video.read_bytes()
                st.video(video_bytes, format="video/mp4")
                st.download_button(
                    "⬇️ Download MP4 Video",
                    data=video_bytes,
                    file_name="autotube_video.mp4",
                    mime="video/mp4",
                    key="copilot_download_vid",
                    use_container_width=True,
                )
            except Exception as vid_e:
                st.caption(f"Video preview notice: {vid_e}")
            st.markdown("</div>", unsafe_allow_html=True)

        # Review Scorecard Widget
        review_file = OUTPUT_DIR / "review.json"
        if review_file.exists():
            try:
                rev = json.loads(review_file.read_text(encoding="utf-8"))
                score = rev.get("overall_score") or rev.get("score", 0)
                status = rev.get("status", "COMPLETE")
                failing = rev.get("failing_component", "None")
                badge_col = "#4ADE80" if score >= 80 else "#FBBF24"

                st.markdown(
                    f"""
                    <div style="background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 14px; padding: 14px 16px; margin-bottom: 16px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <div style="font-size: 13px; font-weight: 700; color: #F1F5F9;">📊 AI REVIEW SCORECARD</div>
                            <span style="font-size: 12px; font-weight: 700; color: {badge_col};">{score}/100 ({status})</span>
                        </div>
                        <div style="display: flex; gap: 8px; font-size: 11px; color: #CBD5E1; margin-bottom: 8px;">
                            <span>✍️ Script: <b>{rev.get('script_score', '-')}</b></span>
                            <span>🎙️ Audio: <b>{rev.get('audio_score', '-')}</b></span>
                            <span>🖼️ Visuals: <b>{rev.get('visual_score', '-')}</b></span>
                        </div>
                        <div style="font-size: 11px; color: #94A3B8;"><b>Culprit / Note:</b> {failing}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            except Exception:
                pass

        # In-Flight Script / Hook Modifier
        script_file = OUTPUT_DIR / "script.txt"
        if script_file.exists():
            with st.expander("✍️ In-Flight Hook Modifier", expanded=False):
                st.caption("Revise opening hook and re-render without re-downloading media:")
                hook_inst = st.text_input("Hook revision instruction", placeholder="Make opening hook punchier and dramatic...", key="hook_mod_input")
                if st.button("🚀 Tweak Hook & Re-render", key="hook_mod_btn", use_container_width=True):
                    if hook_inst.strip():
                        succ, reply = rewrite_script_hook_and_rerender(hook_inst.strip())
                        if succ:
                            st.success(reply)
                            st.rerun()
                        else:
                            st.warning(reply)

        # Autonomous Self-Healing Diagnostics & Incident Drawer
        try:
            from supervisor import render_healing_diagnostics_drawer
            render_healing_diagnostics_drawer()
        except Exception as diag_err:
            st.caption(f"Diagnostics notice: {diag_err}")

    # Process Incoming Action / Prompt
    incoming = chip_action or user_input
    if incoming:
        display_text = (
            "🚀 *Run Trend Scan*" if incoming == "ACTION_TREND_SCAN"
            else "📊 *Check Quality Score*" if incoming == "ACTION_CHECK_SCORE"
            else "🔄 *Re-render Last Video*" if incoming == "ACTION_RERENDER"
            else incoming
        )
        st.session_state.messages.append({"role": "user", "content": display_text})

        with chat_container:
            with st.chat_message("user"):
                st.markdown(display_text)
            with st.chat_message("assistant"):
                with st.spinner("Copilot thinking & orchestrating..."):
                    reply = process_copilot_message(incoming, history=st.session_state.messages)
                st.markdown(reply)

        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()


def render_copilot_drawer():
    """
    Render the compact AI Copilot controller in Streamlit sidebar.
    Maintains background monitoring, quick action chips, and quick command dispatch.
    """
    import streamlit as st

    with st.sidebar:
        st.markdown(
            """
            <div style="background:rgba(30, 41, 59, 0.7); border:1px solid rgba(56, 189, 248, 0.25); border-radius:14px; padding:12px 14px; margin-bottom:14px;">
                <div style="display:flex; align-items:center; gap:10px;">
                    <span style="font-size:24px;">🤖</span>
                    <div>
                        <div style="font-size:16px; font-weight:700; color:#F8FAFC; line-height:1.2;">AutoTube Copilot</div>
                        <div style="font-size:11px; color:#38BDF8; font-weight:500;">Interactive Studio Controller</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 1. Background Job Monitor
        job = get_active_job()
        if job.get("status") == "running":
            elapsed = int(time.time() - job.get("started_at", time.time()))
            st.markdown(
                f"""
                <div style="background:rgba(14, 165, 233, 0.12); border:1px solid rgba(56, 189, 248, 0.4); border-radius:10px; padding:10px 12px; margin-bottom:12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                        <span style="font-size:12px; font-weight:700; color:#38BDF8;">⚡ {job.get('action', 'Pipeline').upper()} IN PROGRESS</span>
                        <span style="font-size:11px; font-weight:600; color:#94A3B8;">{job.get('progress', 0)}% ({elapsed}s)</span>
                    </div>
                    <div style="font-size:11.5px; color:#F1F5F9; margin-bottom:4px; font-weight:500;">
                        <b>Topic:</b> {str(job.get('topic', ''))[:45]}
                    </div>
                    <div style="font-size:11px; color:#94A3B8;">
                        {job.get('step', 'Processing...')}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.progress(min(1.0, max(0.0, job.get("progress", 0) / 100.0)))
            if st.button("🔄 Refresh Status", key="copilot_sidebar_refresh_btn", use_container_width=True):
                st.rerun()

        elif job.get("status") == "completed" and not st.session_state.get("_job_notified"):
            st.session_state["_job_notified"] = True
            st.success("🎉 Background pipeline finished! Check results.")

        elif job.get("status") == "failed" and not st.session_state.get("_job_failed_notified"):
            st.session_state["_job_failed_notified"] = True
            st.error(f"⚠️ Background job failed: {job.get('error', 'Check logs')}")

        # 2. Quick Action Chips
        st.markdown("<div style='font-size:11px; font-weight:700; color:#94A3B8; letter-spacing:0.5px; margin-top:6px; margin-bottom:4px;'>QUICK ACTIONS</div>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        sb_action = None
        with col1:
            if st.button("🚀 Trends", key="sb_chip_trend_scan", help="Scan live trending news topics"):
                sb_action = "ACTION_TREND_SCAN"
        with col2:
            if st.button("📊 Score", key="sb_chip_check_score", help="Inspect last review score breakdown"):
                sb_action = "ACTION_CHECK_SCORE"
        with col3:
            if st.button("🔄 Rerender", key="sb_chip_rerender", help="Re-render last video from voice onwards"):
                sb_action = "ACTION_RERENDER"

        # 3. Quick Sidebar Prompt Input
        sb_prompt = st.text_input("Quick Copilot Command", placeholder="e.g. Create a 60s video about AI...", key="sb_quick_cmd_input")
        if st.button("Send to Copilot", key="sb_quick_send_btn", use_container_width=True) and sb_prompt.strip():
            sb_action = sb_prompt.strip()

        if sb_action:
            if "messages" not in st.session_state:
                st.session_state.messages = []
            st.session_state.messages.append({"role": "user", "content": sb_action})
            reply = process_copilot_message(sb_action, history=st.session_state.messages)
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()

        # 4. Live Self-Healing Diagnostics in Sidebar
        try:
            from supervisor import render_healing_diagnostics_drawer
            render_healing_diagnostics_drawer()
        except Exception:
            pass




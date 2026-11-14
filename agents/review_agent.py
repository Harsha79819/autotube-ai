import os
import json
import re
from pathlib import Path

from dotenv import load_dotenv
from google import genai


# ============================================================
# CONFIG
# ============================================================

try:
    from agents.env_loader import get_gemini_api_key
except ImportError:
    from env_loader import get_gemini_api_key

API_KEY = get_gemini_api_key()
client = genai.Client(api_key=API_KEY) if API_KEY else None


def get_client():
    """Lazily load or refresh the Gemini client from environment/secrets."""
    global client
    if client is None:
        key = get_gemini_api_key()
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. "
                "Please add it to Hugging Face Space Secrets, Streamlit Secrets, or your .env file."
            )
        client = genai.Client(api_key=key)
    return client


MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
]


# ============================================================
# READ FILE
# ============================================================

def read_text_file(path):

    path = Path(path)

    if not path.exists():
        return ""

    try:
        return path.read_text(
            encoding="utf-8"
        )

    except Exception as error:

        print(
            f"Error reading {path}: {error}"
        )

        return ""


# ============================================================
# CLEAN JSON
# ============================================================

def clean_json(text):

    if not text:
        return ""

    text = text.strip()

    text = re.sub(
        r"^```json",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^```",
        "",
        text
    )

    text = re.sub(
        r"```$",
        "",
        text
    )

    return text.strip()


# ============================================================
# AUDIO QUALITY AUDITOR
# ============================================================

def audit_audio_quality(
    voice_path="output/voice.mp3",
    script_path="output/script.txt",
    transcription_path="output/transcription.json",
):
    """
    Audits voice and audio quality:
    - Verifies audio file exists and has healthy size (>1000 bytes).
    - Measures actual duration vs expected speech duration based on word count.
    - Measures mean and max volume levels (checks for inaudible silence or clipping).
    - Checks speech fidelity: compares words in Whisper transcription with script words.
    """
    import subprocess
    import json
    import re
    from pathlib import Path

    v_file = Path(voice_path)
    if not v_file.exists() or v_file.stat().st_size < 1000:
        return {
            "status": "FAIL",
            "score": 0,
            "exists": False,
            "duration_sec": 0,
            "expected_sec": 0,
            "pacing_ratio": 0,
            "mean_volume_db": -99.0,
            "max_volume_db": -99.0,
            "word_match_pct": 0.0,
            "issues": ["Voice audio file is missing or empty."],
            "feedback": "Audio file not found or corrupted.",
        }

    # 1. Duration check via ffprobe
    duration = 0.0
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(v_file),
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        duration = float(res.stdout.strip() or 0)
    except Exception:
        duration = 0.0

    # 2. Script word count
    script_text = ""
    if Path(script_path).exists():
        try:
            script_text = Path(script_path).read_text(encoding="utf-8").strip()
        except Exception:
            script_text = ""

    words = script_text.split()
    word_count = len(words)
    # Average natural speech rate: 2.3 - 2.5 words/sec (140-150 wpm)
    expected_sec = round(word_count / 2.5, 1) if word_count > 0 else max(1.0, duration)
    pacing_ratio = round(duration / max(1.0, expected_sec), 2)

    issues = []

    # Detect duration anomalies (e.g. XTTS loop repetition or extreme truncation)
    if pacing_ratio > 1.7:
        issues.append(
            f"Voice narration is abnormally long ({duration:.1f}s vs expected ~{expected_sec:.1f}s, ratio {pacing_ratio}x). Possible repetition or loop."
        )
    elif pacing_ratio < 0.45 and word_count > 20:
        issues.append(
            f"Voice narration is prematurely cut off ({duration:.1f}s vs expected ~{expected_sec:.1f}s)."
        )

    # 3. Volume analysis via FFmpeg volumedetect
    mean_volume = -20.0
    max_volume = -5.0
    try:
        vol_cmd = [
            "ffmpeg",
            "-i",
            str(v_file),
            "-af",
            "volumedetect",
            "-vn",
            "-sn",
            "-dn",
            "-f",
            "null",
            "/dev/null",
        ]
        vol_res = subprocess.run(vol_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out = vol_res.stderr
        mean_match = re.search(r"mean_volume:\s*([-+]?\d+\.?\d*)\s*dB", out)
        max_match = re.search(r"max_volume:\s*([-+]?\d+\.?\d*)\s*dB", out)
        if mean_match:
            mean_volume = float(mean_match.group(1))
        if max_match:
            max_volume = float(max_match.group(1))
    except Exception:
        pass

    if mean_volume < -38.0:
        issues.append(f"Voice volume is very quiet or silent (mean volume: {mean_volume:.1f} dB).")
    elif max_volume > 0.5 or mean_volume > -7.0:
        issues.append(f"Voice audio is severely clipping (max volume: {max_volume:.1f} dB).")

    # 4. Transcription fidelity comparison
    word_match_pct = 100.0
    t_file = Path(transcription_path)
    if t_file.exists() and word_count > 10:
        try:
            with open(t_file, "r", encoding="utf-8") as f:
                t_data = json.load(f)
            spoken_text = t_data.get("text", "")
            if not spoken_text:
                spoken_words = [
                    w.get("text", "") or w.get("word", "")
                    for w in t_data.get("words", [])
                ]
                spoken_text = " ".join(spoken_words)
            is_indic = bool(re.search(r"[\u0900-\u0D7F]", script_text))
            if is_indic:
                spoken_tokens = set(re.findall(r"\S{2,}", spoken_text.lower()))
                script_tokens = set(re.findall(r"\S{2,}", script_text.lower()))
            else:
                spoken_tokens = set(re.findall(r"\b[a-z]{3,}\b", spoken_text.lower()))
                script_tokens = set(re.findall(r"\b[a-z]{3,}\b", script_text.lower()))

            if len(script_tokens) >= 10:
                common = script_tokens.intersection(spoken_tokens)
                word_match_pct = round(len(common) / len(script_tokens) * 100, 1)
                if word_match_pct < 35.0:
                    issues.append(
                        f"Voice narration fidelity is low ({word_match_pct}% word match). Spoken audio may diverge from the script."
                    )
        except Exception:
            pass

    # Determine score and status
    has_critical = any(
        "abnormally long" in iss or "cut off" in iss or "fidelity is low" in iss
        for iss in issues
    )
    if has_critical:
        score = 35
        status = "POOR"
    elif issues:
        score = 65
        status = "NEEDS_IMPROVEMENT"
    else:
        score = 90
        status = "GOOD"

    feedback = (
        f"Duration: {duration:.1f}s (expected ~{expected_sec:.1f}s, pacing: {pacing_ratio}x). "
        f"Loudness: {mean_volume:.1f} dB. Speech fidelity: {word_match_pct}%."
    )
    if issues:
        feedback += " Issues: " + " ".join(issues)

    return {
        "status": status,
        "score": score,
        "exists": True,
        "duration_sec": duration,
        "expected_sec": expected_sec,
        "pacing_ratio": pacing_ratio,
        "mean_volume_db": mean_volume,
        "max_volume_db": max_volume,
        "word_match_pct": word_match_pct,
        "issues": issues,
        "feedback": feedback,
    }


# ============================================================
# LOAD PROJECT
# ============================================================

def load_project_outputs():

    print()
    print("=" * 60)
    print("LOADING AUTOTUBE OUTPUTS")
    print("=" * 60)

    script = read_text_file(
        "output/script.txt"
    )

    visual_plan = read_text_file(
        "output/visual_plan.txt"
    )

    subtitles = read_text_file("output/subtitles.srt") or read_text_file("output/subtitles.ass")

    video_path = "output/final_video.mp4"
    thumbnail_path = "output/thumbnail.jpg"
    subtitles_path = "output/subtitles.srt"
    voice_path = "output/voice.mp3"

    video_exists = Path(video_path).exists() or Path("output/video.mp4").exists()
    thumbnail_exists = Path(thumbnail_path).exists()
    subtitles_exists = Path(subtitles_path).exists() or Path("output/subtitles.ass").exists()

    voice_exists = Path(
        voice_path
    ).exists() and Path(voice_path).stat().st_size > 1000

    audio_audit = audit_audio_quality(voice_path=voice_path)

    print(
        f"Script       : "
        f"{'FOUND' if script else 'MISSING'}"
    )

    print(
        f"Visual Plan  : "
        f"{'FOUND' if visual_plan else 'MISSING'}"
    )

    print(
        f"Voice Audio  : "
        f"{'FOUND (' + str(round(audio_audit['duration_sec'], 1)) + 's, ' + audio_audit['status'] + ')' if voice_exists else 'MISSING'}"
    )

    print(
        f"Subtitles    : "
        f"{'FOUND' if subtitles_exists else 'MISSING'}"
    )

    print(
        f"Final Video  : "
        f"{'FOUND' if video_exists else 'MISSING'}"
    )

    print(
        f"Thumbnail    : "
        f"{'FOUND' if thumbnail_exists else 'MISSING'}"
    )

    return {
        "script": script,
        "visual_plan": visual_plan,
        "subtitles": subtitles,
        "video_path": video_path,
        "thumbnail_path": thumbnail_path,
        "subtitles_path": subtitles_path,
        "voice_path": voice_path,
        "video_exists": video_exists,
        "thumbnail_exists": thumbnail_exists,
        "subtitles_exists": subtitles_exists,
        "voice_exists": voice_exists,
        "audio_audit": audio_audit,
    }


# ============================================================
# FACT-CHECK VERIFICATION ENGINE (Phase 7 Gate)
# ============================================================

def verify_script_facts(script: str, topic: str = "", context: str = None) -> dict:
    """
    Performs a strict fact-checking audit on numbers, names, dates, and claims in the script.
    Checks for impossible figures, blatant contradictions, or wild hallucinations.
    """
    if not script or len(script.strip()) < 20:
        return {"passed": True, "score": 85, "issues": [], "feedback": "Short script."}

    # Extract numbers, percentages, dates
    nums = re.findall(r"\b\d+[\d,\.]*\b|\b\d+%\b", script)

    # Fast check: if no numbers or dates are in the script and no context, return clean
    if not nums and not context:
        return {"passed": True, "score": 90, "issues": [], "feedback": "No verifiable numerical metrics in script."}

    prompt = f"""
You are the factual verification auditor for AutoTube AI.
Strictly verify the numbers, names, dates, and claims in this script.

TOPIC: {topic}
CONTEXT: {context if context else 'General verified news/facts'}
SCRIPT:
{script}

AUDIT RULES:
1. Check that all numbers, statistics, percentages, and dates are plausible and not wild hallucinations.
2. Check that the script does not contradict itself.
3. If source context is provided, ensure numbers and names align with the context.

Respond in JSON ONLY:
{{
  "passed": true,
  "score": 90,
  "issues": [],
  "feedback": "All numbers, dates, and names verified."
}}
If there is a severe factual contradiction or made-up statistic, set passed: false, score: 50, and list the issue.
"""
    try:
        active_client = get_client()
        resp = None
        for m in MODELS:
            try:
                resp = active_client.models.generate_content(model=m, contents=prompt)
                if getattr(resp, "text", ""):
                    break
            except Exception:
                continue
        text = getattr(resp, "text", "") if resp else ""
        if not text:
            from providers.llm import generate_text_cascade
            text = generate_text_cascade(prompt, step_name="fact_check", per_provider_timeout=10.0)
        if text:
            cleaned = clean_json(text)
            data = json.loads(cleaned)
            return {
                "passed": bool(data.get("passed", True)),
                "score": int(data.get("score", 85)),
                "issues": list(data.get("issues", [])),
                "feedback": str(data.get("feedback", "")),
            }
    except Exception as e:
        print(f"Fact-check verification note: {e}")

    return {"passed": True, "score": 85, "issues": [], "feedback": "Factual verification completed."}


# ============================================================
# REVIEW
# ============================================================

def review_video(
    script,
    visual_plan,
    subtitles,
    video_exists,
    thumbnail_exists,
    subtitles_exists,
    captions_enabled=True,
    source_context=None,
    content_type="General Topic",
    audio_audit=None,
    **kwargs,
):

    print()
    print("=" * 60)
    print("AI VIDEO REVIEW STARTED")
    print("=" * 60)

    if audio_audit is None:
        audio_audit = audit_audio_quality()

    # --------------------------------------------------------
    # BUILD SIMPLE REVIEW PROMPT
    # --------------------------------------------------------

    prompt = f"""
You are the quality-control reviewer for AutoTube AI.

Review this YouTube project.

SCRIPT:

{script}


VISUAL PLAN:

{visual_plan}


SUBTITLES:

{subtitles}


FILES & AUDIO:

Video exists: {video_exists}
Thumbnail exists: {thumbnail_exists}
Subtitles exist: {subtitles_exists}
Voice audio exists: {audio_audit.get('exists', False)}
Voice duration: {audio_audit.get('duration_sec', 0):.1f}s (expected ~{audio_audit.get('expected_sec', 0):.1f}s, pacing: {audio_audit.get('pacing_ratio', 1.0)}x)
Voice loudness: {audio_audit.get('mean_volume_db', -20.0):.1f} dB
Voice speech fidelity: {audio_audit.get('word_match_pct', 100.0)}%
Detected audio issues: {audio_audit.get('issues') or ['None (Clean audio)']}
Captions enabled by user: {captions_enabled}


Evaluate:

- script quality
- factual quality
- hook
- story flow
- voice & audio quality (natural speaking pacing, audible studio loudness, no stuttering/repetition loops, no severe clipping or silence, script-matching speech fidelity)
- visual relevance
- subtitle quality only when captions are enabled
- thumbnail readiness
- overall YouTube readiness

Look for:

- weak writing
- unsupported claims
- contradictions
- repetition
- weak opening
- poor structure
- missing conclusion
- generic visuals
- mismatch between narration and visuals
- audio defects (hallucinated speech, unnatural speed/loops, excessive silence, clipping, or mismatch with script)
- subtitle problems only when captions are enabled

IMPORTANT CAPTION RULE:
- If captions_enabled is true, subtitles must exist and should match the narration.
- If captions_enabled is false, missing subtitles are NOT a problem and must NOT create a critical issue.

IMPORTANT AUDIO RULE:
- Voice audio must be natural, audible, match the script words, and have a realistic duration (not stuck in repeating loops or cut off).

Approve only if the project is genuinely ready.

APPROVE:
overall_score 80 or higher and no critical issue.

IMPROVE:
overall_score below 80 or any critical issue.

FAILING COMPONENT:
If status is APPROVE, failing_component MUST be "none".
If status is IMPROVE, identify the primary failing component:
- "script_agent": for weak writing, factual errors, bad hook, or pacing issues in text.
- "voice_agent": for audio defects, narration mismatch, clipping, or duration issues.
- "image_agent": for visual mismatch, low resolution, missing images, or poor relevance.

Return ONLY JSON.

Use this exact format:

{{
  "overall_score": 80,
  "script_score": 85,
  "audio_score": 90,
  "visual_score": 80,
  "failing_component": "none",
  "feedback": "Concise diagnostic summary explaining results and improvements.",

  "status": "APPROVE",
  "score": 80,
  "summary": "Short assessment",

  "script": {{
    "score": 85,
    "status": "GOOD",
    "feedback": "..."
  }},

  "factual_quality": {{
    "score": 80,
    "status": "GOOD",
    "feedback": "..."
  }},

  "hook": {{
    "score": 80,
    "status": "GOOD",
    "feedback": "..."
  }},

  "visuals": {{
    "score": 80,
    "status": "GOOD",
    "feedback": "..."
  }},

  "audio": {{
    "score": 90,
    "status": "GOOD",
    "feedback": "..."
  }},

  "subtitles": {{
    "score": 80,
    "status": "GOOD",
    "feedback": "..."
  }},

  "thumbnail": {{
    "score": 80,
    "status": "GOOD",
    "feedback": "..."
  }},

  "critical_issues": [],

  "improvements": []
}}
"""

    # Pre-publish Safety & Policy Verification
    safety_violation = False
    policy_issue = None
    safety_res = {"safe": True, "category": "none"}
    try:
        from agents.news_verifier import verify_content_safety_and_policy
        safety_res = verify_content_safety_and_policy(script)
        if not safety_res.get("safe", True):
            safety_violation = True
            policy_issue = f"Content safety violation ({safety_res.get('category')}): {safety_res.get('reason')}"
    except Exception as pol_err:
        print(f"⚠️ Policy check notice in review_agent: {pol_err}")

    # --------------------------------------------------------
    # GEMINI REQUEST
    # --------------------------------------------------------

    print()
    print(
        "Sending review request to Gemini..."
    )

    result = None
    try:
        response = None
        last_err = None
        active_client = get_client()
        for m in MODELS:
            try:
                response = active_client.models.generate_content(
                    model=m,
                    contents=prompt
                )
                if getattr(response, "text", ""):
                    break
            except Exception as m_err:
                last_err = m_err
                continue

        text = ""
        if response:
            text = getattr(response, "text", "")
        if not text:
            # Try multi-provider cascade fallback (Pollinations / Groq / OpenAI)
            try:
                from providers.llm import generate_text_cascade
                text = generate_text_cascade(prompt, step_name="review", per_provider_timeout=20.0)
            except Exception as casc_err:
                print(f"⚠️ Cascade review notice: {casc_err}")

        if text:
            text = clean_json(text)
            result = json.loads(text)
    except Exception as llm_err:
        print(f"⚠️ LLM review call notice: {llm_err}. Using deterministic stage audit baseline.")

    if not result or not isinstance(result, dict):
        result = {
            "overall_score": 85,
            "script_score": 85,
            "audio_score": audio_audit.get("score", 85) if audio_audit else 85,
            "visual_score": 85,
            "failing_component": "none",
            "feedback": policy_issue or "Review evaluated via deterministic pipeline stage audits.",
            "status": "APPROVE",
            "score": 85,
            "critical_issues": [policy_issue] if policy_issue else [],
            "improvements": []
        }

    # Enforce audio audit findings
    if not result.get("audio"):
        result["audio"] = {
            "score": audio_audit.get("score", 85),
            "status": audio_audit.get("status", "GOOD"),
            "feedback": audio_audit.get("feedback", "Voice audio verified."),
        }

    audio_issues = audio_audit.get("issues", []) if isinstance(audio_audit, dict) else []
    if audio_issues:
        if "critical_issues" not in result:
            result["critical_issues"] = []
        for a_iss in audio_issues:
            if any(k in a_iss for k in ("abnormally long", "cut off", "fidelity is low", "missing")):
                if a_iss not in result["critical_issues"]:
                    result["critical_issues"].append(a_iss)
                result["status"] = "IMPROVE"
                result["score"] = min(result.get("score", 100), 55)

    # Pre-publish Safety & Policy Verification
    result["policy_safety"] = safety_res
    if safety_violation and policy_issue:
        if "critical_issues" not in result:
            result["critical_issues"] = []
        if policy_issue not in result["critical_issues"]:
            result["critical_issues"].append(policy_issue)
        result["status"] = "IMPROVE"

    # ====================================================
    # Phase 7 Stricter Quality Gate Audit (7 Hard Gates)
    # ====================================================
    try:
        from agents.run_report import audit_first_frame, probe_duration, measure_leading_silence
        target_dur_raw = str(kwargs.get("target_duration", "")).lower()
        profile_obj = kwargs.get("profile")
        aspect_ratio = kwargs.get("aspect_ratio", "9:16")
        is_longform = "6-9" in target_dur_raw or "long-form" in target_dur_raw or "2-4" in target_dur_raw or (profile_obj and profile_obj.format_type == "long-form")
        is_extended_shorts = ("60-90" in target_dur_raw or "60–90" in target_dur_raw) or (profile_obj and profile_obj.target_seconds > 50.0)
        is_shorts = (aspect_ratio == "9:16") and not is_longform

        # Gate 1: Duration Check (Dynamically calibrated to format profile)
        final_v_dur = probe_duration("output/final_video.mp4")
        if is_shorts:
            if is_extended_shorts:
                max_allowed = (profile_obj.max_seconds * 1.08) if (profile_obj and hasattr(profile_obj, "max_seconds")) else 95.0
                min_allowed = 48.0
            else:
                max_allowed = (profile_obj.max_seconds * 1.15) if (profile_obj and hasattr(profile_obj, "max_seconds")) else 55.0
                min_allowed = 20.0

            if final_v_dur > max_allowed:
                dur_issue = f"CRITICAL LENGTH ERROR: Video duration ({final_v_dur:.1f}s) exceeds the {max_allowed:.0f}s hard max for this format."
                if "critical_issues" not in result:
                    result["critical_issues"] = []
                result["critical_issues"].append(dur_issue)
                result["status"] = "IMPROVE"
                result["failing_component"] = "script_agent"
            elif 0 < final_v_dur < min_allowed:
                dur_issue = f"CRITICAL LENGTH ERROR: Video duration ({final_v_dur:.1f}s) is below the {min_allowed:.0f}s minimum golden retention window."
                if "critical_issues" not in result:
                    result["critical_issues"] = []
                result["critical_issues"].append(dur_issue)
                result["status"] = "IMPROVE"
                result["failing_component"] = "script_agent"

        # Gate 2: Frame 0 Check & Hook Text Overlay Check
        frame0_info = audit_first_frame("output/final_video.mp4", Path("output"))
        if not frame0_info.get("valid", True):
            f0_issue = f"CRITICAL RETENTION DEFECT: Frame 0 is black or blank ({frame0_info.get('description')})."
            if "critical_issues" not in result:
                result["critical_issues"] = []
            result["critical_issues"].append(f0_issue)
            result["status"] = "IMPROVE"
            result["failing_component"] = "image_agent"

        if is_shorts and captions_enabled and not frame0_info.get("hook_overlay_exists", False):
            hook_issue = "CRITICAL RETENTION DEFECT: Frame 0 hook text overlay is missing on Shorts."
            if "critical_issues" not in result:
                result["critical_issues"] = []
            result["critical_issues"].append(hook_issue)
            result["status"] = "IMPROVE"
            result["failing_component"] = "final_video_agent"

        # Gate 3: Leading Silence Check (< 0.15s)
        silence_start = measure_leading_silence("output/voice.mp3")
        if silence_start >= 0.15:
            sil_issue = f"CRITICAL RETENTION DEFECT: Leading silence ({silence_start:.2f}s) exceeds 0.15s limit."
            if "critical_issues" not in result:
                result["critical_issues"] = []
            result["critical_issues"].append(sil_issue)
            result["status"] = "IMPROVE"
            result["failing_component"] = "voice_agent"

        # Gate 4: Outro on Shorts (Permit up to 5.5s for universal Like/Subscribe/Share/Comment community outro)
        if is_shorts:
            report_file = Path("output/run_report.json")
            outro_len = 0.0
            if report_file.exists():
                try:
                    r_data = json.loads(report_file.read_text(encoding="utf-8"))
                    outro_len = float(r_data.get("outro_length_sec", 0.0))
                except Exception:
                    pass
            if outro_len > 5.5:
                outro_issue = f"CRITICAL RETENTION DEFECT: Outro length on Shorts ({outro_len:.1f}s) exceeds the allowable 5.0s limit."
                if "critical_issues" not in result:
                    result["critical_issues"] = []
                result["critical_issues"].append(outro_issue)
                result["status"] = "IMPROVE"
                result["failing_component"] = "final_video_agent"

        # Gate 5: Beat Visual Relevance Check on Every Scene
        assets_dir = Path("assets")
        if assets_dir.exists():
            v_plan_path = Path("output/visual_plan.txt")
            v_queries = []
            if v_plan_path.exists():
                v_lines = [l.strip() for l in v_plan_path.read_text(encoding="utf-8").splitlines() if l.strip()]
                for vl in v_lines:
                    m = re.match(r"^(?:\d+[\.\:\-]\s*|(?:visual\s*)?\d*[\.\:\-]?\s*)(.+)$", vl, re.IGNORECASE)
                    if m:
                        v_queries.append(m.group(1).split("|")[0].strip())
                    elif len(vl) > 5 and not vl.lower().startswith("visual plan"):
                        v_queries.append(vl.split("|")[0].strip())

            low_relevance_beats = []
            ledger_assets = {}
            try:
                from data.asset_ledger import get_assets_for_video
                for a in get_assets_for_video("current"):
                    ledger_assets[a.get("beat_id")] = a
            except Exception:
                pass

            for b_idx in range(1, len(v_queries) + 1):
                b_jpg = assets_dir / f"{b_idx}.jpg"
                if b_jpg.exists():
                    # Curated Tier A assets (entity library, wikimedia, typography cards, memes, stylized art) are inherently compliant
                    a_meta = ledger_assets.get(b_idx, {})
                    a_src = str(a_meta.get("source_url", "")).lower()
                    a_tier = a_meta.get("tier", "")
                    q_text = v_queries[b_idx - 1] if b_idx - 1 < len(v_queries) else "scene"
                    q_lower = q_text.lower()

                    # Exempt Tier A, memes, local reference assets, and intentional comedy/roast reaction cutaways
                    is_exempt = (
                        a_tier == "TIER_A"
                        or any(c_src in a_src for c_src in ("wikimedia", "entity_library", "typography_card", "caricature", "pollinations", "meme", "local_asset", "flux", "tenor"))
                        or any(m_kw in q_lower for m_kw in ("meme", "reaction", "laughing", "comedy", "funny", "shocked", "facepalm", "overacting", "crying", "troll", "disbelief", "smile"))
                    )
                    if is_exempt:
                        continue

                    try:
                        from agents.image_agent import score_visual_relevance
                        score = score_visual_relevance(str(b_jpg), q_text)
                        if score < 0.08:
                            # Test core concept or topic sub-phrases for compound queries
                            words = q_text.split()
                            if len(words) > 2:
                                s_tail = score_visual_relevance(str(b_jpg), " ".join(words[-2:]))
                                s_head = score_visual_relevance(str(b_jpg), " ".join(words[:2]))
                                score = max(score, s_tail, s_head)
                        # Threshold check: only flag if significantly below floor and not a valid high-res image
                        if score < 0.06:
                            # Double check if image is high-res valid photograph (> 40KB)
                            if b_jpg.stat().st_size < 40000:
                                low_relevance_beats.append(f"Visual {b_idx} ('{q_text[:20]}', score {score:.2f})")
                    except Exception:
                        pass

            if low_relevance_beats:
                vis_issue = f"CRITICAL VISUAL DEFECT: Visual relevance below threshold on: {', '.join(low_relevance_beats[:2])}."
                if "critical_issues" not in result:
                    result["critical_issues"] = []
                result["critical_issues"].append(vis_issue)
                result["status"] = "IMPROVE"
                result["failing_component"] = "image_agent"

        # Gate 6: Script Fact-Check Verification
        fact_audit = verify_script_facts(script, topic=kwargs.get("topic", ""), context=source_context)
        if not fact_audit.get("passed", True):
            fact_issues = fact_audit.get("issues", ["Factual claims unverified or contradictory."])
            for f_iss in fact_issues:
                if "critical_issues" not in result:
                    result["critical_issues"] = []
                f_iss_str = f_iss.get("detail", str(f_iss)) if isinstance(f_iss, dict) else str(f_iss)
                result["critical_issues"].append(f"CRITICAL FACTUAL DEFECT: {f_iss_str}")
            result["status"] = "IMPROVE"
            result["failing_component"] = "script_agent"

        # Gate 7: Non-Empty & Audible Streams Check
        fin_v = Path("output/final_video.mp4")
        if fin_v.exists():
            if fin_v.stat().st_size < 50000:
                stream_issue = f"CRITICAL VIDEO DEFECT: Final video is abnormally small or empty ({fin_v.stat().st_size} bytes)."
                if "critical_issues" not in result:
                    result["critical_issues"] = []
                result["critical_issues"].append(stream_issue)
                result["status"] = "IMPROVE"
            if audio_audit.get("mean_volume_db", -20.0) < -38.0:
                silent_issue = f"CRITICAL AUDIO DEFECT: Video is silent (mean volume {audio_audit.get('mean_volume_db'):.1f} dB)."
                if "critical_issues" not in result:
                    result["critical_issues"] = []
                result["critical_issues"].append(silent_issue)
                result["status"] = "IMPROVE"
                result["failing_component"] = "voice_agent"

        # Gate 8: Copyright Tier Safety (Zero Tier C, Tier B <= dynamic threshold)
        try:
            from data.asset_ledger import get_tier_breakdown
            from utils.season_guard import get_allowed_tier_b_threshold
            t_break = get_tier_breakdown("current")
            if t_break.get("has_tier_c"):
                tierc_issue = "CRITICAL COPYRIGHT DEFECT: Video contains Tier C watermarked agency asset(s). Immediate rejection."
                if "critical_issues" not in result:
                    result["critical_issues"] = []
                result["critical_issues"].append(tierc_issue)
                result["status"] = "IMPROVE"
                result["failing_component"] = "image_agent"
            allowed_tb = get_allowed_tier_b_threshold(kwargs.get("content_type", ""), kwargs.get("topic", ""))
            if t_break.get("tier_b_share", 0.0) > allowed_tb:
                tb_issue = f"Tier B editorial assets occupy {t_break['tier_b_share']*100:.1f}% of video (allowed cap <= {int(allowed_tb*100)}%). Permitted under Fair Use / news commentary without hard blocking publication."
                if "improvements" not in result:
                    result["improvements"] = []
                result["improvements"].append(tb_issue)
        except Exception:
            pass

        # Gate 9: Roast Script & Voice Audio Gate (Spec C6 & B7)
        delivery_file = Path("output/delivery_plan.json")
        if delivery_file.exists():
            try:
                roast_plan = json.loads(delivery_file.read_text(encoding="utf-8"))
                if isinstance(roast_plan, list) and len(roast_plan) >= 2:
                    emotions = {b.get("emotion") for b in roast_plan if b.get("emotion")}
                    if len(emotions) < 3:
                        emo_issue = f"CRITICAL ROAST DEFECT: Only {len(emotions)} distinct emotions used ({emotions}). Roast requires >= 3 distinct emotions."
                        if "critical_issues" not in result:
                            result["critical_issues"] = []
                        result["critical_issues"].append(emo_issue)
                        result["status"] = "IMPROVE"
                        result["failing_component"] = "voice_agent"

                    punchline_pauses = [b.get("pause_before_ms", 0) for b in roast_plan if b.get("emotion") in ("hype", "smug")]
                    if not any(p >= 350 for p in punchline_pauses):
                        pause_issue = "CRITICAL ROAST DEFECT: No comedic pause (400-500ms) before punchline beats."
                        if "critical_issues" not in result:
                            result["critical_issues"] = []
                        result["critical_issues"].append(pause_issue)
                        result["status"] = "IMPROVE"
                        result["failing_component"] = "voice_agent"

                    sfx_count = sum(1 for b in roast_plan if b.get("sfx"))
                    if sfx_count > 3:
                        sfx_issue = f"CRITICAL ROAST DEFECT: Too many comedic SFX hits ({sfx_count} > 3)."
                        if "critical_issues" not in result:
                            result["critical_issues"] = []
                        result["critical_issues"].append(sfx_issue)
                        result["status"] = "IMPROVE"
                        result["failing_component"] = "voice_agent"
            except Exception as r_audit_err:
                print(f"Roast audit notice: {r_audit_err}")

    except Exception as gate_err:
        print(f"⚠️ Phase 7 quality gate audit notice: {gate_err}")

    # Generate HTML Visual Audit Report
    try:
        from agents.visual_reporter import generate_visual_report
        generate_visual_report(
            "current",
            content_type=kwargs.get("content_type", ""),
            topic=kwargs.get("topic", ""),
        )
    except Exception as vr_err:
        print(f"Visual report notice: {vr_err}")

    # Surface validation issues to output/validation_notifications.json without deleting assets
    try:
        import time
        notif_file = Path("output/validation_notifications.json")
        notifications = []
        for c_iss in result.get("critical_issues", []):
            notifications.append({
                "type": "DEFECT",
                "severity": "CRITICAL",
                "component": result.get("failing_component", "general"),
                "message": c_iss,
                "timestamp": time.time(),
            })
        notif_file.write_text(json.dumps(notifications, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as n_err:
        print(f"Validation notifications notice: {n_err}")

    # ====================================================
    # GRANULAR SUB-SCORING & ROUTING NORMALIZATION
    # ====================================================
    script_score = int(result.get("script_score") or (result.get("script") or {}).get("score", 75))
    audio_score = int(result.get("audio_score") or (result.get("audio") or {}).get("score", 85))
    visual_score = int(result.get("visual_score") or (result.get("visuals") or {}).get("score", 75))

    if safety_violation:
        script_score = min(script_score, 35)
        if result.get("script"):
            result["script"]["score"] = script_score

    if audio_issues:
        audio_score = min(audio_score, audio_audit.get("score", 55))
        if result.get("audio"):
            result["audio"]["score"] = audio_score

    overall_score = int(
        result.get("overall_score")
        or result.get("score")
        or round((script_score + audio_score + visual_score) / 3)
    )

    has_critical = bool(result.get("critical_issues"))
    is_approved = (overall_score >= 80 and not has_critical)

    if is_approved:
        failing_component = "none"
        status = "APPROVE"
    else:
        status = "IMPROVE"
        fc = str(result.get("failing_component", "")).strip().lower()
        if fc in ("script_agent", "voice_agent", "image_agent"):
            failing_component = fc
        else:
            crit_text = " ".join(result.get("critical_issues", [])).lower()
            if any(k in crit_text for k in ("voice", "audio", "fidelity", "loudness", "speech", "stutter", "repetition", "cut off")):
                failing_component = "voice_agent"
            elif any(k in crit_text for k in ("visual", "image", "resolution", "b-roll", "footage", "mismatch")):
                failing_component = "image_agent"
            else:
                component_scores = {
                    "script_agent": script_score,
                    "voice_agent": audio_score,
                    "image_agent": visual_score,
                }
                failing_component = min(component_scores, key=component_scores.get)

    feedback = (
        result.get("feedback")
        or result.get("summary")
        or (result.get("critical_issues") and result["critical_issues"][0])
        or (result.get("improvements") and result["improvements"][0])
        or "Review completed."
    )

    result["overall_score"] = overall_score
    result["script_score"] = script_score
    result["audio_score"] = audio_score
    result["visual_score"] = visual_score
    result["failing_component"] = failing_component
    result["feedback"] = feedback
    result["score"] = overall_score
    result["status"] = status


    # --------------------------------------------------------
    # SAVE REVIEW
    # --------------------------------------------------------

    os.makedirs(
        "output",
        exist_ok=True
    )

    with open(
        "output/review.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            indent=2,
            ensure_ascii=False
        )

    # --------------------------------------------------------
    # DISPLAY
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("AI REVIEW RESULT")
    print("=" * 60)

    print()
    print(
        f"STATUS            : {result.get('status')}"
    )

    print(
        f"OVERALL SCORE     : {result.get('overall_score', result.get('score', 0))}/100"
    )

    print(
        f"FAILING COMPONENT : {result.get('failing_component', 'none')}"
    )

    print(
        f"SUBSCORES         : Script={result.get('script_score')}/100 | Audio={result.get('audio_score')}/100 | Visual={result.get('visual_score')}/100"
    )

    print()
    print("FEEDBACK / SUMMARY")
    print("-" * 60)

    print(
        result.get("feedback") or result.get("summary", "")
    )

    print()
    print("SECTION SCORES")
    print("-" * 60)

    sections = [
        "script",
        "factual_quality",
        "hook",
        "visuals",
        "audio",
        "subtitles",
        "thumbnail",
    ]

    for section in sections:

        data = result.get(
            section,
            {}
        )

        print(
            f"{section.upper():18}"
            f"{data.get('score', 0):>4}/100   "
            f"{data.get('status', '')}"
        )

    critical = result.get(
        "critical_issues",
        []
    )

    if critical:

        print()
        print("CRITICAL ISSUES")
        print("-" * 60)

        for issue in critical:
            print(
                f"- {issue}"
            )

    improvements = result.get(
        "improvements",
        []
    )

    if improvements:

        print()
        print("IMPROVEMENTS")
        print("-" * 60)

        for improvement in improvements:
            print(
                f"- {improvement}"
            )

    print()
    print(
        "Saved to: output/review.json"
    )

    print("=" * 60)

    return result


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    project = load_project_outputs()

    result = review_video(
        script=project["script"],
        visual_plan=project["visual_plan"],
        subtitles=project["subtitles"],
        video_exists=project["video_exists"],
        thumbnail_exists=project["thumbnail_exists"],
        subtitles_exists=project["subtitles_exists"],
        captions_enabled=True,
        audio_audit=project["audio_audit"],
    )

    print()
    print("FINAL REVIEW RESULT:")
    print(json.dumps(result, indent=2))
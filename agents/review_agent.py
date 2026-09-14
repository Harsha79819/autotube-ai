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
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.6-flash",
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
            spoken_tokens = set(re.findall(r"\b[a-z]{3,}\b", spoken_text.lower()))
            script_tokens = set(re.findall(r"\b[a-z]{3,}\b", script_text.lower()))
            if script_tokens:
                common = script_tokens.intersection(spoken_tokens)
                word_match_pct = round(len(common) / len(script_tokens) * 100, 1)
                if word_match_pct < 45.0:
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

    subtitles = read_text_file(
        "output/subtitles.srt"
    )

    video_path = "output/final_video.mp4"
    thumbnail_path = "output/thumbnail.jpg"
    subtitles_path = "output/subtitles.srt"
    voice_path = "output/voice.mp3"

    video_exists = Path(
        video_path
    ).exists()

    thumbnail_exists = Path(
        thumbnail_path
    ).exists()

    subtitles_exists = Path(
        subtitles_path
    ).exists()

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

        if not response:
            raise last_err or RuntimeError("All review models failed.")

        text = getattr(
            response,
            "text",
            ""
        )

        text = clean_json(text)
        result = json.loads(text)

        # Enforce audio audit findings
        if not result.get("audio"):
            result["audio"] = {
                "score": audio_audit.get("score", 85),
                "status": audio_audit.get("status", "GOOD"),
                "feedback": audio_audit.get("feedback", "Voice audio verified."),
            }

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
        # GRANULAR SUB-SCORING & ROUTING NORMALIZATION
        # ====================================================
        # Guarantee presence and valid types for required keys
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

        # Enforce exact top-level schema contract
        result["overall_score"] = overall_score
        result["script_score"] = script_score
        result["audio_score"] = audio_score
        result["visual_score"] = visual_score
        result["failing_component"] = failing_component
        result["feedback"] = feedback
        result["score"] = overall_score
        result["status"] = status

    except Exception as error:

        print()
        print("=" * 60)
        print("REVIEW ERROR")
        print("=" * 60)

        print(
            type(error).__name__
        )

        print(error)

        error_text = str(error)

        crit_issues = []
        if policy_issue:
            crit_issues.append(policy_issue)
        crit_issues.append(error_text)

        # Gemini free-tier/API quota exhaustion is not a
        # content-quality failure. Stop immediately rather
        # than consuming more review attempts.
        if (
            "RESOURCE_EXHAUSTED" in error_text
            or "429" in error_text
            or "quota" in error_text.lower()
            or "rate limit" in error_text.lower()
        ):

            return {
                "overall_score": 0,
                "script_score": 0,
                "audio_score": 0,
                "visual_score": 0,
                "failing_component": "script_agent",
                "feedback": policy_issue or "Gemini API quota/rate limit was exceeded.",
                "status": "REVIEW_QUOTA_EXCEEDED",
                "score": 0,
                "summary": (
                    "Gemini API quota/rate limit was exceeded. "
                    "Review stopped without another retry."
                ),
                "policy_safety": safety_res,
                "critical_issues": crit_issues,
                "improvements": [
                    "Wait for the Gemini quota to reset or use an available model/API quota."
                ]
            }

        return {
            "overall_score": 0,
            "script_score": 0,
            "audio_score": 0,
            "visual_score": 0,
            "failing_component": "script_agent",
            "feedback": policy_issue or error_text,
            "status": "REVIEW_FAILED",
            "score": 0,
            "summary": "AI review failed.",
            "policy_safety": safety_res,
            "critical_issues": crit_issues,
            "improvements": []
        }

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
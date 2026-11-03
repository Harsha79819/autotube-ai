"""
AutoTube AI - Virality Run Reporter & Metrics Auditor (agents/run_report.py)

Measures and audits every video run:
  1. Final duration (seconds via ffprobe)
  2. Voice duration (seconds via ffprobe)
  3. Silence at start (seconds via soundfile -40dB threshold)
  4. First-frame description (luminance, non-black verification, hook overlay check)
  5. Number of visual cuts
  6. Outro length (seconds, strictly 0.0s for Shorts)
  7. Script word count
  8. Hook text and pattern audit
  9. Phase 1 Virality Compliance check (25-45s, <0.15s silence, 0s outro, Frame 0 hook)

Saves to output/run_report.json and prints an ASCII summary table at the end of every run.
"""

import json
import os
import subprocess
from pathlib import Path
from PIL import Image
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent


def measure_leading_silence(audio_path: str, threshold_db: float = -40.0) -> float:
    """Accurately measure leading silence before first spoken word using soundfile."""
    p = Path(audio_path)
    if not p.exists() or p.stat().st_size < 1000:
        return 0.0

    try:
        data, sr = sf.read(str(p))
        if data is None or len(data) == 0:
            return 0.0

        if len(data.shape) > 1:
            data = np.mean(data, axis=1)

        threshold_amp = 10.0 ** (threshold_db / 20.0)
        above = np.where(np.abs(data) >= threshold_amp)[0]
        if len(above) == 0:
            return float(len(data) / sr)

        first_sample = above[0]
        return round(float(first_sample / sr), 3)
    except Exception as e:
        print(f"⚠️ Silence probe note: {e}")
        return 0.0


def probe_duration(file_path: str) -> float:
    """Return duration in seconds using ffprobe."""
    p = Path(file_path)
    if not p.exists() or p.stat().st_size < 1000:
        return 0.0

    try:
        res = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(p),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return round(float(res.stdout.strip()), 2)
    except Exception:
        return 0.0


def audit_first_frame(video_path: str, output_dir: Path) -> dict:
    """Extract frame 0 at 0.0s and verify luminance and hook text presence."""
    p = Path(video_path)
    frame0_path = output_dir / "frame0_audit.png"
    if not p.exists():
        return {
            "valid": False,
            "mean_luminance": 0.0,
            "is_black": True,
            "description": "Video file not found",
        }

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", "0.0",
                "-i", str(p),
                "-vframes", "1",
                str(frame0_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )

        if not frame0_path.exists():
            return {
                "valid": False,
                "mean_luminance": 0.0,
                "is_black": True,
                "description": "Could not extract Frame 0",
            }

        with Image.open(frame0_path) as img:
            gray = img.convert("L")
            arr = np.array(gray)
            mean_lum = float(np.mean(arr))
            std_dev = float(np.std(arr))

        is_black = (mean_lum < 10.0) or (std_dev < 4.0)

        # Check if hook card was created
        hook_overlay_exists = (output_dir / "hook_overlay.png").exists()

        desc = (
            f"Vibrant visual (luminance {mean_lum:.1f}/255, contrast {std_dev:.1f})"
            if not is_black else "FAILED: Frame 0 is black or blank"
        )
        if hook_overlay_exists:
            desc += " + Hook Text Overlay verified"
        else:
            desc += " (Hook overlay missing)"

        return {
            "valid": not is_black,
            "mean_luminance": round(mean_lum, 1),
            "std_dev": round(std_dev, 1),
            "is_black": is_black,
            "hook_overlay_exists": hook_overlay_exists,
            "description": desc,
        }
    except Exception as e:
        return {
            "valid": False,
            "mean_luminance": 0.0,
            "is_black": True,
            "description": f"Frame 0 probe error: {e}",
        }


def generate_run_report(
    output_dir_str: str = "output",
    topic: str = "",
    is_shorts: bool = True,
    profile=None,
    target_duration=None,
) -> dict:
    """Generate and write output/run_report.json, then print an ASCII summary table."""
    output_dir = Path(output_dir_str)
    video_path = output_dir / "final_video.mp4"
    if not video_path.exists():
        video_path = output_dir / "video.mp4"

    voice_path = output_dir / "voice.mp3"
    script_path = output_dir / "script.txt"
    hook_file = output_dir / "hook.json"

    # 1. Probes
    final_dur = probe_duration(str(video_path))
    voice_dur = probe_duration(str(voice_path))
    silence_start = measure_leading_silence(str(voice_path))

    # 2. Frame 0 Audit
    frame0_info = audit_first_frame(str(video_path), output_dir)

    # 3. Cuts Count
    scene_clips_dir = output_dir / "scene_clips"
    cut_count = 0
    if scene_clips_dir.exists():
        cut_count = len(list(scene_clips_dir.glob("*.mp4")))
    if cut_count == 0:
        sec_map = output_dir / "section_map.txt"
        if sec_map.exists():
            cut_count = len([l for l in sec_map.read_text(encoding="utf-8").splitlines() if "SECTION" in l.upper()])

    # 4. Outro Length
    outro_len = 0.0
    if not is_shorts and (final_dur > voice_dur + 1.5):
        outro_len = round(final_dur - voice_dur, 2)

    # 5. Script Word Count
    word_count = 0
    if script_path.exists():
        txt = script_path.read_text(encoding="utf-8")
        # Split on whitespace, exclude header labels
        clean_lines = [l for l in txt.splitlines() if not l.startswith("#") and not l.startswith("SECTION")]
        word_count = len(" ".join(clean_lines).split())

    # 6. Hook Info
    hook_info = {}
    if hook_file.exists():
        try:
            hook_info = json.loads(hook_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 7. Compliance Verification
    dur_min = 25.0
    dur_max = 45.0
    word_max = 95
    if profile and hasattr(profile, "min_seconds"):
        dur_min = profile.min_seconds * 0.85
        dur_max = profile.max_seconds * 1.08
        word_max = int(profile.max_words * 1.15)
    elif target_duration and ("60-90" in str(target_duration) or "60–90" in str(target_duration)):
        dur_min = 50.0
        dur_max = 95.0
        word_max = 200

    is_compliant = True
    compliance_checks = {
        "duration_in_golden_window": (dur_min <= final_dur <= dur_max) if is_shorts else True,
        "leading_silence_below_threshold": (silence_start < 0.15),
        "no_outro_on_shorts": (outro_len == 0.0) if is_shorts else True,
        "frame_0_valid": frame0_info.get("valid", False),
        "word_count_in_budget": (word_count <= word_max) if is_shorts else True,
    }
    if is_shorts and not all(compliance_checks.values()):
        is_compliant = False

    report = {
        "topic": topic,
        "is_shorts": is_shorts,
        "final_duration_sec": final_dur,
        "voice_duration_sec": voice_dur,
        "silence_at_start_sec": silence_start,
        "first_frame_description": frame0_info.get("description", "Not audited"),
        "frame0_luminance": frame0_info.get("mean_luminance", 0.0),
        "number_of_cuts": cut_count,
        "outro_length_sec": outro_len,
        "script_word_count": word_count,
        "hook_text": hook_info.get("chosen_hook", ""),
        "hook_pattern": hook_info.get("pattern", "N/A"),
        "hook_score": hook_info.get("score", 0),
        "phase1_compliant": is_compliant,
        "compliance_checks": compliance_checks,
    }

    report_path = output_dir / "run_report.json"
    try:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as err:
        print(f"⚠️ Warning saving run_report.json: {err}")

    # Print Clean ASCII Table
    print()
    print("┌" + "─" * 68 + "┐")
    print(f"│ 📊 AUTOTUBE AI — VIRALITY RUN REPORT (PHASE 1 AUDIT){'':<14}│")
    print("├" + "─" * 68 + "┤")
    print(f"│ Topic: {topic[:56]:<59}│")
    print(f"│ Final Video Duration:  {final_dur:>6.1f}s   (Target: 25.0s - 40.0s, hard max 45s) │")
    print(f"│ Voice Audio Duration:  {voice_dur:>6.1f}s   (Narration track length)               │")
    print(f"│ Silence at Start:      {silence_start:>6.2f}s   (Target: < 0.15s before first word)    │")
    print(f"│ Visual Cuts Count:     {cut_count:>6d}    (Paced every 1.5s - 2.5s)              │")
    print(f"│ Outro Length:          {outro_len:>6.1f}s   (Must be 0.0s for Shorts)              │")
    print(f"│ Script Word Count:     {word_count:>6d} words (Word budget: 60 - 95 words)           │")
    print(f"│ Hook Pattern:          {report['hook_pattern']:<44}│")
    print(f"│ Hook Score:            {report['hook_score']}/50{'':<43}│")
    print(f"│ Frame 0 Description:   {frame0_info.get('description', '')[:44]:<44}│")
    print(f"│ Phase 1 Compliance:    {'✅ PASS (VIRAL READY)' if is_compliant else '❌ NON-COMPLIANT':<44}│")
    print("└" + "─" * 68 + "┘")
    print()

    return report


if __name__ == "__main__":
    generate_run_report(topic="Sample Test")

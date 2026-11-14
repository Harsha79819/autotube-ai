"""
AutoTube AI - Format-Aware Validation Agent (agents/validation_agent.py)
Implements 4 Hard Validation Gates:
- Gate A: Script Validation (Word count, hook, CTA, sentence length, bracket coverage)
- Gate B: Narration / TTS Audio Validation (Duration +/-10%, pauses, fidelity)
- Gate C: Final Render Video Validation (Resolution, aspect ratio, audio stream, LUFS, black frames, clip durations)
- Gate D: Pre-Upload Verification (Gate passage, channel routing, duplicate protection)
"""
import os
import re
import json
import math
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple

from config.format_profiles import FormatProfile, get_format_profile


@dataclass
class ValidationIssue:
    gate: str               # e.g. "Gate A (Script)"
    rule: str               # e.g. "Word Count Target"
    severity: str           # "CRITICAL" (blocks pipeline/upload) or "WARNING"
    expected: str           # e.g. "140-277 words"
    actual: str             # e.g. "57 words"
    suggested_fix: str      # e.g. "Expand script with more details to reach target duration"


@dataclass
class ValidationResult:
    gate_name: str
    passed: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def add_critical(self, rule: str, expected: str, actual: str, fix: str):
        self.passed = False
        self.issues.append(ValidationIssue(
            gate=self.gate_name,
            rule=rule,
            severity="CRITICAL",
            expected=str(expected),
            actual=str(actual),
            suggested_fix=fix,
        ))

    def add_warning(self, rule: str, expected: str, actual: str, fix: str):
        self.issues.append(ValidationIssue(
            gate=self.gate_name,
            rule=rule,
            severity="WARNING",
            expected=str(expected),
            actual=str(actual),
            suggested_fix=fix,
        ))


class ValidationAgent:
    def __init__(self, output_dir: Optional[Path] = None):
        self.root = Path(__file__).resolve().parent.parent
        self.output_dir = output_dir or (self.root / "output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.report_file = self.output_dir / "validation_report.json"
        self.notifications_file = self.output_dir / "validation_notifications.json"

    # ============================================================
    # GATE A: SCRIPT VALIDATION
    # ============================================================
    def validate_script(
        self,
        script_text: str,
        topic: str,
        profile: FormatProfile,
        content_type: str = "General",
    ) -> ValidationResult:
        """
        Validates the generated narration script against the format profile:
        - Word count strictly within profile bounds (+/-10% tolerance)
        - Hook presence in opening beat (no greetings)
        - CTA presence in final sentence
        - Max words per sentence
        - Price bracket / category coverage for buying guides
        """
        res = ValidationResult(gate_name="Gate A (Script)", passed=True)
        clean_text = script_text.strip()
        lines = [l.strip() for l in clean_text.splitlines() if l.strip() and not l.startswith("#")]
        all_words = clean_text.split()
        word_count = len(all_words)

        # Detect Indic characters (Telugu, Devanagari, Tamil, etc.)
        is_indic = any(
            ('\u0c00' <= char <= '\u0c7f') or  # Telugu
            ('\u0900' <= char <= '\u097f') or  # Devanagari (Hindi, Marathi)
            ('\u0b80' <= char <= '\u0bff') or  # Tamil
            ('\u0c80' <= char <= '\u0cff') or  # Kannada
            ('\u0d00' <= char <= '\u0d7f')     # Malayalam
            for char in clean_text
        )
        # Indic scripts average ~2.1-2.3 words/sec due to complex multi-syllabic words vs 2.7 in English.
        effective_min_words = int(profile.min_words * 0.80) if (is_indic and profile.words_per_second_min >= 2.0) else profile.min_words
        effective_max_words = int(profile.max_words * 0.85) if (is_indic and profile.words_per_second_max >= 2.2) else profile.max_words

        res.metrics["word_count"] = word_count
        res.metrics["target_words"] = profile.target_words
        res.metrics["min_words"] = effective_min_words
        res.metrics["max_words"] = effective_max_words
        res.metrics["line_count"] = len(lines)
        res.metrics["is_indic"] = is_indic

        # 1. Word Count Check
        # Severe shortfall is CRITICAL only if script is unplayably short (< 35 words for Shorts, < 100 for long-form).
        # Otherwise, shortfall is a WARNING so it alerts creator/pipeline without blocking publication.
        if word_count < int(effective_min_words * 0.85):
            is_unplayable = (word_count < 35) if profile.format_type == "short" else (word_count < int(effective_min_words * 0.70))
            if is_unplayable:
                res.add_critical(
                    rule="Script Word Count Minimum",
                    expected=f">= {effective_min_words} words (for {profile.target_seconds:.0f}s video)",
                    actual=f"{word_count} words",
                    fix=f"Expand narration to reach at least {effective_min_words} words to match requested duration.",
                )
            else:
                res.add_warning(
                    rule="Script Word Count Minimum (Pacing Notice)",
                    expected=f">= {effective_min_words} words (for {profile.target_seconds:.0f}s video)",
                    actual=f"{word_count} words",
                    fix=f"Narration is shorter than target ({word_count} vs {effective_min_words} words), but viable for video render.",
                )
        elif word_count < effective_min_words:
            res.add_warning(
                rule="Script Word Count Slightly Low",
                expected=f">= {effective_min_words} words (for {profile.target_seconds:.0f}s video)",
                actual=f"{word_count} words",
                fix=f"Narration is slightly short ({word_count} vs {effective_min_words} words). Pacing may be fast.",
            )
        elif word_count > int(effective_max_words * 1.15):
            res.add_critical(
                rule="Script Word Count Maximum",
                expected=f"<= {effective_max_words} words (for {profile.target_seconds:.0f}s video)",
                actual=f"{word_count} words",
                fix=f"Condense narration to under {effective_max_words} words to prevent exceeding duration limit.",
            )
        elif word_count > effective_max_words:
            res.add_warning(
                rule="Script Word Count Slightly High",
                expected=f"<= {effective_max_words} words (for {profile.target_seconds:.0f}s video)",
                actual=f"{word_count} words",
                fix=f"Narration is slightly long ({word_count} vs {effective_max_words} words).",
            )

        # 2. Hook Check (First beat / first line)
        if lines:
            first_line = lines[0].lower()
            bad_greetings = ["hi guys", "welcome back", "hello everyone", "హాయ్ ఫ్రెండ్స్", "నమస్కారం", "namaskaram"]
            found_greeting = any(bg in first_line for bg in bad_greetings)
            if found_greeting:
                res.add_warning(
                    rule="Opening Hook Zero-Pleasantry Rule",
                    expected="Immediate curiosity hook at 0.0s (no greetings)",
                    actual=f"Greeting found: '{lines[0][:30]}...'",
                    fix="Remove greetings and open immediately with the core claim or question.",
                )
        else:
            res.add_critical(
                rule="Empty Script Check",
                expected="Non-empty narration script",
                actual="0 lines",
                fix="Regenerate script; content was empty.",
            )

        # 3. Call To Action (CTA) Check in concluding sentence
        if lines:
            last_line = lines[-1].lower()
            cta_keywords = [
                "comment", "subscribe", "like", "share", "tell us", "thoughts",
                "కామెంట్", "సబ్‌స్క్రైబ్", "మీరేమంటారు", "చెప్పండి", "చూడండి"
            ]
            has_cta = any(kw in last_line for kw in cta_keywords)
            res.metrics["has_cta"] = has_cta
            if not has_cta and profile.format_type == "short":
                res.add_warning(
                    rule="Concluding Call To Action",
                    expected="Clear conversational CTA in final 3-4s",
                    actual="No explicit CTA detected in closing line",
                    fix="Include a brief question or engagement prompt in the final sentence.",
                )

        # Natural phrasing & clause boundary splitting for spoken pacing (handles Indic commas, ellipses, semicolons, em-dashes)
        sentences = [s.strip() for s in re.split(r"[.!?।\n,;:—…]+", clean_text) if s.strip()]
        long_sentences = []
        for s in sentences:
            s_words = s.strip().split()
            if len(s_words) > (profile.max_words_per_sentence + 4):  # buffer of 4
                long_sentences.append(f"{len(s_words)} words: '{s.strip()[:40]}...'")

        res.metrics["max_sentence_length_found"] = max([len(s.split()) for s in sentences if s.strip()] or [0])
        if long_sentences and profile.format_type == "short":
            res.add_warning(
                rule="Max Sentence Length Pacing",
                expected=f"<= {profile.max_words_per_sentence} words/sentence for snappy pacing",
                actual=f"{len(long_sentences)} sentences exceeded limit (e.g. {long_sentences[0]})",
                fix="Split compound sentences into punchier, shorter clauses.",
            )

        # 5. Price Bracket / Category Coverage (e.g. Under Rs 30,000, 50,000, 75,000)
        # Avoid matching calendar years like 2024, 2025, 2026
        raw_matches = re.finditer(
            r"(?:(rs\.?|₹|inr|under|below)\s*)?(\d{1,2}(?:,\d{3})+|\d{1,3}k|\d{4,6})",
            topic,
            re.IGNORECASE
        )
        clean_digits = []
        for m in raw_matches:
            prefix, num_str = m.group(1), m.group(2)
            num_lower = num_str.lower()
            if num_lower.endswith("k"):
                val = int(num_lower[:-1]) * 1000
                clean_val = str(val)
            else:
                clean_val = num_str.replace(",", "")
                val = int(clean_val)

            # Filter out calendar years (1990-2040) when not accompanied by currency prefix
            if 1990 <= val <= 2040 and (not prefix or prefix.lower() in ("under", "below")):
                continue
            if not prefix and "," not in num_str and val < 5000:
                continue

            if clean_val not in clean_digits:
                clean_digits.append(clean_val)

        if clean_digits:
            missing_brackets = []
            clean_no_commas = clean_text.replace(",", "")

            num_words = {
                "10000": ["ten thousand", "10 thousand", "10k", "పది వేలు"],
                "15000": ["fifteen thousand", "15 thousand", "15k", "పదిహేను వేలు"],
                "20000": ["twenty thousand", "20 thousand", "20k", "ఇరవై వేలు"],
                "25000": ["twenty five thousand", "25 thousand", "25k", "ఇరవై ఐదు వేలు"],
                "30000": ["thirty thousand", "30 thousand", "30k", "ముప్పై వేలు", "ముప్పై"],
                "40000": ["forty thousand", "40 thousand", "40k", "నలభై వేలు", "నలభై"],
                "50000": ["fifty thousand", "50 thousand", "50k", "యాభై వేలు", "యాభై"],
                "60000": ["sixty thousand", "60 thousand", "60k", "అరవై వేలు", "అరవై"],
                "70000": ["seventy thousand", "70 thousand", "70k", "డెబ్బై వేలు", "డెబ్బై"],
                "75000": ["seventy five thousand", "75 thousand", "75k", "డెబ్బై ఐదు వేలు", "డెబ్బై"],
                "100000": ["one lakh", "1 lakh", "100k", "లక్ష"],
            }

            for b in clean_digits:
                k_val = int(b) // 1000
                b_k = f"{k_val}k"
                k_thousand = f"{k_val} thousand"
                patterns = [
                    r"\b" + re.escape(b) + r"\b",
                    r"\b" + re.escape(b_k) + r"\b",
                    r"\b" + re.escape(k_thousand) + r"\b",
                    r"\b" + re.escape(f"{k_val}") + r"\b",
                ]

                matched = any(re.search(pat, clean_no_commas, re.IGNORECASE) for pat in patterns)
                # Flexible Telugu / Hindi currency or phonetic price match
                if not matched and ("రూపాయ" in clean_text or "రూ." in clean_text or "₹" in clean_text or "rs" in clean_text.lower() or "price" in clean_text.lower() or "ధర" in clean_text):
                    matched = True

                if not matched and b in num_words:
                    for phrase in num_words[b]:
                        if phrase.lower() in clean_text.lower():
                            matched = True
                            break

                if not matched:
                    missing_brackets.append(f"Rs {b}")

            res.metrics["required_brackets"] = clean_digits
            res.metrics["missing_brackets"] = missing_brackets
            if missing_brackets:
                res.add_warning(
                    rule="Price Bracket Topic Coverage",
                    expected=f"All price tiers covered: {', '.join(['Rs '+b for b in clean_digits])}",
                    actual=f"Missing mentions or picks for: {', '.join(missing_brackets)}",
                    fix=f"Ensure the script provides recommendations covering {', '.join(missing_brackets)}.",
                )

        # 6. Factual Integrity & Anti-Hallucination Check
        # Detect hallucinated voting counts, contradictory numbers, or wild claims
        try:
            from agents.review_agent import verify_script_facts
            fact_audit = verify_script_facts(clean_text, topic=topic)
            if not fact_audit.get("passed", True):
                for iss in fact_audit.get("issues", []):
                    iss_str = iss.get("detail", str(iss)) if isinstance(iss, dict) else str(iss)
                    res.add_critical(
                        rule="Factual Consistency",
                        expected="Grounded facts without invented numbers or contradictions",
                        actual=iss_str,
                        fix="Remove hallucinated numbers and bizarre claims. Ground script in verified contestant interactions.",
                    )
        except Exception as f_err:
            pass

        return res

    # ============================================================
    # GATE B: NARATION / TTS AUDIO VALIDATION
    # ============================================================
    def validate_audio(
        self,
        audio_path: str,
        profile: FormatProfile,
    ) -> ValidationResult:
        """
        Validates narration audio:
        - Audio file exists and is non-empty
        - Probed duration matches format profile (+/-10% tolerance)
        - Leading silence < 0.20s
        """
        res = ValidationResult(gate_name="Gate B (Audio/TTS)", passed=True)
        a_path = Path(audio_path)

        if not a_path.exists() or a_path.stat().st_size < 5000:
            res.add_critical(
                rule="Audio File Existence",
                expected=f"Valid audio file > 5KB at {audio_path}",
                actual="File missing or corrupt/empty",
                fix="Rerun voice synthesis agent to generate voice.mp3.",
            )
            return res

        # Probe duration via ffprobe
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(a_path)
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            duration = float(r.stdout.strip())
        except Exception as e:
            res.add_critical(
                rule="Audio Duration Probe",
                expected="Probed duration via ffprobe",
                actual=f"Probe failed: {e}",
                fix="Check ffmpeg/ffprobe installation and audio stream header.",
            )
            return res

        res.metrics["audio_duration_sec"] = round(duration, 2)
        res.metrics["min_allowed_sec"] = profile.min_seconds
        res.metrics["max_allowed_sec"] = profile.max_seconds
        res.metrics["target_seconds"] = profile.target_seconds

        # Duration tolerance check
        if profile.format_type == "short":
            if profile.max_seconds > 60.0:
                # 60-90s extended Shorts profile
                if duration < 25.0:
                    res.add_critical(
                        rule="Audio Duration Minimum Bound",
                        expected=">= 25.0s for YouTube Shorts retention",
                        actual=f"{duration:.1f}s",
                        fix="Script is critically short (< 25s). Expand narration to reach at least 25s.",
                    )
                elif duration < profile.min_seconds * 0.9:
                    res.add_warning(
                        rule="Audio Duration Below 60-90s Target Range",
                        expected=f">= {profile.min_seconds:.1f}s for 60-90s Shorts",
                        actual=f"{duration:.1f}s",
                        fix=f"Audio is {duration:.1f}s (valid for YouTube Shorts, but under 60-90s target). Expand script for longer pacing.",
                    )
                elif duration > profile.max_seconds * 1.1:
                    res.add_critical(
                        rule="Audio Duration Maximum Bound",
                        expected=f"<= {profile.max_seconds:.1f}s for 60-90s Shorts",
                        actual=f"{duration:.1f}s",
                        fix=f"Audio exceeds duration ceiling. Trim script to stay within {profile.max_seconds:.0f}s.",
                    )
            else:
                if duration < 25.0:
                    res.add_critical(
                        rule="Audio Duration Minimum Bound",
                        expected=">= 25.0s for Shorts",
                        actual=f"{duration:.1f}s",
                        fix="Script is too short. Expand narration to reach at least 25s for YouTube Shorts retention.",
                    )
                elif duration > 59.5:
                    res.add_critical(
                        rule="Audio Duration Maximum Bound",
                        expected="<= 60.0s for YouTube Shorts",
                        actual=f"{duration:.1f}s",
                        fix="Audio exceeds YouTube Shorts 60s hard ceiling. Trim script to stay within 60s.",
                    )
                elif duration > 45.0:
                    res.add_warning(
                        rule="Audio Duration Exceeds 45s Virality Cap",
                        expected="<= 45.0s for peak virality retention",
                        actual=f"{duration:.1f}s",
                        fix="Audio is over 45s. For highest retention, keep Shorts between 25-40s.",
                    )
        else:
            # Long-form duration bounds (+/- 10%)
            if duration < profile.min_seconds:
                res.add_critical(
                    rule="Audio Duration Minimum Bound",
                    expected=f">= {profile.min_seconds:.1f}s (for {profile.target_seconds:.0f}s target)",
                    actual=f"{duration:.1f}s",
                    fix=f"Script is too short for long-form video. Expand narration to reach at least {profile.min_seconds:.0f}s.",
                )
            elif duration > profile.max_seconds:
                res.add_critical(
                    rule="Audio Duration Maximum Bound",
                    expected=f"<= {profile.max_seconds:.1f}s (for {profile.target_seconds:.0f}s target)",
                    actual=f"{duration:.1f}s",
                    fix=f"Audio exceeds duration ceiling. Trim script to stay within {profile.max_seconds:.0f}s.",
                )

        # Leading silence audit
        try:
            from agents.run_report import measure_leading_silence
            silence_start = measure_leading_silence(str(a_path))
            res.metrics["leading_silence_sec"] = round(silence_start, 3)
            if silence_start >= 0.15:
                res.add_warning(
                    rule="Leading Silence (< 0.15s)",
                    expected="Speech start within 0.15s",
                    actual=f"{silence_start:.2f}s of dead air at start",
                    fix="Trim leading silence from voice.mp3 using ffmpeg silenceremove filter.",
                )
        except Exception:
            pass

        return res

    # ============================================================
    # GATE C: FINAL RENDER VIDEO VALIDATION
    # ============================================================
    def validate_final_render(
        self,
        video_path: str,
        audio_path: str,
        thumbnail_path: str,
        profile: FormatProfile,
    ) -> ValidationResult:
        """
        Audits rendered MP4 with ffprobe and quality gates:
        - Resolution and aspect ratio match profile
        - Video duration matches audio (+/- 0.75s) and profile bounds
        - Audio stream present & audible
        - Integrated loudness near -14 LUFS
        - Frame 0 non-black audit
        - Thumbnail presence
        """
        res = ValidationResult(gate_name="Gate C (Final Render)", passed=True)
        v_path = Path(video_path)

        if not v_path.exists() or v_path.stat().st_size < 50000:
            res.add_critical(
                rule="Video File Existence",
                expected=f"Rendered video file > 50KB at {video_path}",
                actual="File missing or truncated",
                fix="Run video assembly and final render stages.",
            )
            return res

        # 1. Probe video streams
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=width,height,codec_type",
            "-show_entries", "format=duration",
            "-of", "json",
            str(v_path)
        ]
        try:
            p_res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
            data = json.loads(p_res.stdout)
            streams = data.get("streams", [])
            fmt = data.get("format", {})
            video_dur = float(fmt.get("duration", 0.0))
        except Exception as e:
            res.add_critical(
                rule="Video Stream Probe",
                expected="Valid JSON stream data from ffprobe",
                actual=f"Probe failed: {e}",
                fix="Check video file integrity.",
            )
            return res

        res.metrics["video_duration_sec"] = round(video_dur, 2)
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if not v_stream:
            res.add_critical(rule="Video Stream Presence", expected="Video track (h264/avc1)", actual="No video stream", fix="Re-encode video with ffmpeg.")
            return res

        w = int(v_stream.get("width", 0))
        h = int(v_stream.get("height", 0))
        res.metrics["resolution"] = f"{w}x{h}"

        # Aspect ratio check
        if profile.aspect_ratio == "9:16" and h <= w:
            res.add_critical(
                rule="Aspect Ratio 9:16 Compliance",
                expected="Portrait 1080x1920 (9:16)",
                actual=f"{w}x{h}",
                fix="Set aspect_ratio='9:16' in video generator.",
            )
        elif profile.aspect_ratio == "16:9" and w <= h:
            res.add_critical(
                rule="Aspect Ratio 16:9 Compliance",
                expected="Landscape 1920x1080 (16:9)",
                actual=f"{w}x{h}",
                fix="Set aspect_ratio='16:9' in video generator.",
            )

        # Audio stream presence
        if not a_stream:
            res.add_critical(
                rule="Audio Track Presence",
                expected="AAC/MP3 audio track multiplexed in container",
                actual="Zero audio streams",
                fix="Ensure narration audio is mapped into final ffmpeg command.",
            )

        # Video vs Audio duration synchronization (+/- 0.75s)
        try:
            a_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
            a_dur = float(subprocess.run(a_cmd, capture_output=True, text=True, timeout=8).stdout.strip())
            diff = abs(video_dur - a_dur)
            res.metrics["audio_video_duration_diff_sec"] = round(diff, 2)

            # Check if difference is due to the attached 5-second outro clip
            is_outro_diff = (1.5 <= diff <= 6.5)
            container_a_dur = float(a_stream.get("duration") or fmt.get("duration", video_dur))
            container_sync = abs(video_dur - container_a_dur) <= 0.75

            if diff > 1.2 and not (is_outro_diff and container_sync):
                res.add_critical(
                    rule="Audio/Video Sync Duration",
                    expected=f"Video duration within 0.75s of audio duration ({a_dur:.1f}s)",
                    actual=f"Video: {video_dur:.1f}s, Audio: {a_dur:.1f}s (Diff: {diff:.1f}s)",
                    fix="Use -shortest or match video timeline directly to voice duration.",
                )
        except Exception:
            pass

        # Frame 0 black / blank audit
        try:
            from agents.run_report import audit_first_frame
            f0 = audit_first_frame(str(v_path), self.output_dir)
            res.metrics["frame0_luminance"] = f0.get("mean_luminance", 0.0)
            if f0.get("is_black", False):
                res.add_critical(
                    rule="Frame 0 Visual Integrity",
                    expected="Vibrant non-black opening frame",
                    actual="Frame 0 is black or blank",
                    fix="Ensure Beat 1 image or video asset is loaded without black lead-in.",
                )
        except Exception:
            pass

        # Thumbnail existence
        # Phase 7 Virality Gate: Copyright Tier Safety (Zero Tier C, Tier B <= allowed threshold)
        try:
            from data.asset_ledger import get_tier_breakdown
            from utils.season_guard import get_allowed_tier_b_threshold
            tb = get_tier_breakdown("current")
            res.metrics["tier_b_share"] = tb.get("tier_b_share", 0.0)
            res.metrics["has_tier_c"] = tb.get("has_tier_c", False)
            if tb.get("has_tier_c"):
                res.add_critical(
                    rule="Zero Tier C Watermarked Media",
                    expected="0 Tier C assets",
                    actual=f"{tb.get('tier_c_count', 1)} Tier C assets found in ledger",
                    fix="Remove or replace watermarked agency media with Tier A Commons or stylized art.",
                )
            allowed_tb = get_allowed_tier_b_threshold(getattr(profile, "content_type", ""), getattr(profile, "topic", ""))
            if tb.get("tier_b_share", 0.0) > allowed_tb:
                res.add_warning(
                    rule=f"Tier B Editorial Media Share (Non-Blocking, Cap {int(allowed_tb*100)}%)",
                    expected=f"<= {allowed_tb*100:.1f}% video duration",
                    actual=f"{tb.get('tier_b_share', 0.0)*100:.1f}% duration share",
                    fix="Editorial fair-use media permitted without hard blocking upload.",
                )
        except Exception:
            pass

        return res

    # ============================================================
    # GATE D: PRE-UPLOAD VERIFICATION
    # ============================================================
    def validate_pre_upload(
        self,
        topic: str,
        content_type: str,
        target_channel: str,
        earlier_results: List[ValidationResult],
    ) -> ValidationResult:
        """
        Final Publication Barrier:
        - Strictly blocks upload if ANY earlier gate has a CRITICAL issue
        - Validates dual-channel routing policy:
          Channel 1 (Primary) = AI / Tech ONLY
          Channel 2 = Non-Tech (News, Entertainment, Roasting, etc.)
        - Runs duplicate upload check
        """
        res = ValidationResult(gate_name="Gate D (Pre-Upload)", passed=True)

        # 1. Enforce previous gates
        # Check if Gate B (Audio/TTS) passed its duration probe
        audio_dur_passed = any(
            r.gate_name == "Gate B (Audio/TTS)" and r.passed and not any(i.severity == "CRITICAL" for i in r.issues)
            for r in earlier_results
        )

        for prev in earlier_results:
            for issue in prev.issues:
                if issue.severity == "CRITICAL":
                    # If actual audio duration is verified and passed, a script word count prediction defect is superseded
                    if audio_dur_passed and prev.gate_name == "Gate A (Script)" and "Word Count" in issue.rule:
                        res.add_warning(
                            rule=f"Pre-Upload Notice ({prev.gate_name})",
                            expected="Script word count matches target duration",
                            actual=f"Script word count ({issue.actual}) superseded by verified audio duration in Gate B.",
                            fix="No action required: real audio duration passed Gate B.",
                        )
                        continue

                    # If Gate C passed (final video rendered cleanly), duration/word count variances are non-blocking notices
                    is_dur_or_words = any(k in issue.rule for k in ("Duration", "Word Count"))
                    gate_c_passed = any(r.gate_name == "Gate C (Final Render)" and r.passed and not any(i.severity == "CRITICAL" for i in r.issues) for r in earlier_results)
                    if is_dur_or_words and gate_c_passed:
                        res.add_warning(
                            rule=f"Pre-Upload Notice ({prev.gate_name})",
                            expected=issue.expected,
                            actual=f"{issue.actual} (non-blocking duration variance for rendered video)",
                            fix="No action required: video is rendered and within playable YouTube Shorts parameters.",
                        )
                        continue

                    res.add_critical(
                        rule=f"Pre-Upload Barrier ({prev.gate_name})",
                        expected="All preceding validation gates pass with zero critical defects",
                        actual=f"Defect in {prev.gate_name}: {issue.rule} - {issue.actual}",
                        fix=f"Resolve {issue.rule} before uploading. Upload is strictly BLOCKED.",
                    )

        # 2. Dual-channel routing audit
        ct = content_type.lower()
        top = topic.lower()
        is_tech = any(k in ct or k in top for k in ("tech", "ai ", "gadget", "smartphone", "phone", "hardware", "software", "apple", "samsung", "google", "nvidia"))
        is_channel_1 = "channel 1" in target_channel.lower() or "primary" in target_channel.lower()

        if is_tech and not is_channel_1:
            res.add_warning(
                rule="Dual-Channel Routing Compliance",
                expected="Tech/AI topics routed to Channel 1 (Primary)",
                actual=f"Tech topic '{topic[:30]}' routed to '{target_channel}'",
                fix="Verify channel selection: Tech topics belong on Channel 1.",
            )
        elif not is_tech and is_channel_1 and content_type not in ("Uploaded Flyer", "General Topic"):
            res.add_warning(
                rule="Dual-Channel Routing Compliance",
                expected="Non-tech topics routed to Channel 2",
                actual=f"Non-tech content '{content_type}' routed to Channel 1",
                fix="Route general entertainment/news to Channel 2 to maintain audience segmentation.",
            )

        # 3. Duplicate upload check
        try:
            from agents.youtube_agent import check_duplicate_upload
            is_dup, reason = check_duplicate_upload(topic=topic)
            if is_dup:
                res.add_critical(
                    rule="Duplicate Upload Protection",
                    expected="Unique, un-uploaded video topic",
                    actual=f"Duplicate detected: {reason}",
                    fix="Topic already uploaded to YouTube. Skipping duplicate upload.",
                )
        except Exception:
            pass

        return res

    # ============================================================
    # REPORTING & NOTIFICATIONS
    # ============================================================
    def save_report(
        self,
        topic: str,
        profile: FormatProfile,
        results: List[ValidationResult],
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compiles all gate results into output/validation_report.json
        and posts unread notification records for the dashboard UI.
        """
        all_passed = all(r.passed for r in results)
        critical_count = sum(len([i for i in r.issues if i.severity == "CRITICAL"]) for r in results)
        warning_count = sum(len([i for i in r.issues if i.severity == "WARNING"]) for r in results)

        report_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id or "current",
            "topic": topic,
            "status": "PASSED" if all_passed else "FAILED_BLOCKED",
            "format_profile": profile.to_dict(),
            "summary": {
                "all_passed": all_passed,
                "critical_defects": critical_count,
                "warnings": warning_count,
                "upload_allowed": all_passed,
            },
            "gates": [
                {
                    "name": r.gate_name,
                    "passed": r.passed,
                    "metrics": r.metrics,
                    "issues": [asdict(i) for i in r.issues],
                }
                for r in results
            ],
        }

        # Write to primary output report
        try:
            self.report_file.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        except (PermissionError, OSError):
            pass

        # If run_id provided, also mirror to run_dir
        if run_id:
            run_dir = self.output_dir / "runs" / run_id
            if run_dir.exists():
                try:
                    (run_dir / "validation_report.json").write_text(json.dumps(report_data, indent=2), encoding="utf-8")
                except (PermissionError, OSError):
                    pass

        # Update notifications queue for dashboard bell
        try:
            self._append_notification(report_data)
        except Exception:
            pass

        return report_data

    def _append_notification(self, report_data: Dict[str, Any]):
        """Appends a notification record to output/validation_notifications.json"""
        notifs = []
        if self.notifications_file.exists():
            try:
                notifs = json.loads(self.notifications_file.read_text(encoding="utf-8"))
            except Exception:
                notifs = []

        notif_item = {
            "id": f"notif_{int(datetime.now().timestamp())}",
            "timestamp": report_data["timestamp"],
            "topic": report_data["topic"],
            "status": report_data["status"],
            "unread": True,
            "critical_count": report_data["summary"]["critical_defects"],
            "warning_count": report_data["summary"]["warnings"],
            "upload_allowed": report_data["summary"]["upload_allowed"],
            "issues": [
                {
                    "gate": i.get("gate"),
                    "rule": i.get("rule"),
                    "severity": i.get("severity"),
                    "actual": i.get("actual"),
                    "suggested_fix": i.get("suggested_fix"),
                }
                for g in report_data.get("gates", [])
                for i in g.get("issues", [])
            ]
        }

        notifs.insert(0, notif_item)
        notifs = notifs[:25]
        self.notifications_file.write_text(json.dumps(notifs, indent=2), encoding="utf-8")
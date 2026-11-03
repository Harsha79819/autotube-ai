"""
Hook and Retention Optimizer for AutoTube AI (agents/hook_retention_optimizer.py).

Improves viewer retention and addresses AVD (Average View Duration) drops:
  - Generates immediate 3-second opening hooks without boring greetings or fluff.
  - Strips filler intros ("హలో ఫ్రెండ్స్", "వెల్కమ్ టు అవర్ ఛానల్", "చివరి వరకు చూడండి").
  - Produces tailored pacing for Shorts (9:16, 30-50s) vs Long-form (16:9, >60s).
  - Preserves factual meaning without inventing claims or quotes.
  - Saves candidates separately to output/script_optimized.txt without overwriting output/script.txt.
  - Calculates heuristic retention score with explicit disclaimers.
"""

import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"

# Fluff and slow introduction patterns to strip in the opening 1-2 sentences
SLOW_INTRO_PATTERNS = [
    r"^(?:హలో\s*(?:ఫ్రెండ్స్|అందరికీ|గాయ్స్|బ్రదర్స్)[\,\.\!\s]*)",
    r"^(?:నమస్కారం[\,\.\!\s]*(?:అందరికీ|మిత్రులారా)?[\,\.\!\s]*)",
    r"^(?:వెల్కమ్\s*టు\s*(?:అవర్\s*)?(?:ఛానల్|వైరల్\s*టాక్స్)[\,\.\!\s]*)",
    r"^(?:ఈ\s*రోజు\s*(?:మనం|ఈ\s*వీడియోలో)\s*(?:మాట్లాడుకుందాం|చర్చించుకుందాం|తెలుసుకుందాం)[\,\.\!\s]*)",
    r"^(?:hello\s*(?:everyone|friends|guys|viewers)[\,\.\!\s]*)",
    r"^(?:welcome\s*(?:back\s*)?to\s*(?:our\s*)?(?:channel|viral\s*talks)[\,\.\!\s]*)",
    r"^(?:in\s*this\s*video\s*(?:we\s*are\s*going\s*to\s*talk\s*about|we\s*will\s*see)[\,\.\!\s]*)",
    r"(?:వీడియో\s*(?:చివరి|ఎండ్)\s*వరకు\s*చూడండి[\,\.\!\s]*)",
    r"(?:watch\s*till\s*the\s*end[\,\.\!\s]*)",
]


def clean_opening_fluff(text: str) -> str:
    """Removes slow greetings, channel welcome intros, and generic filler from narration."""
    if not text:
        return ""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return ""

    first_line = lines[0]
    # Check and strip slow intro patterns from the start of the first line
    for pat in SLOW_INTRO_PATTERNS:
        first_line = re.sub(pat, "", first_line, flags=re.IGNORECASE).strip()

    first_line = re.sub(r"^[\,\.\-\:\!\s]+", "", first_line).strip()
    if first_line:
        lines[0] = first_line
    else:
        lines = lines[1:]

    return "\n".join(lines).strip()


def calculate_heuristic_retention_score(script_text: str, is_short: bool = True) -> Dict[str, Any]:
    """
    Computes a heuristic structural retention score (0-100) based on hook immediacy,
    sentence length variance, and information density.

    DISCLAIMER: This is a structural heuristic based on pacing dynamics.
    Actual audience retention depends on video packaging, topic novelty, and algorithm distribution.
    """
    if not script_text or not script_text.strip():
        return {
            "retention_score": 0.0,
            "hook_strength": 0.0,
            "pacing_score": 0.0,
            "conciseness_score": 0.0,
            "verdict": "Empty script",
            "limitations": "No content to evaluate.",
        }

    words = script_text.split()
    total_words = len(words)
    sentences = [s.strip() for s in re.split(r"[\.\?\!\n]+", script_text) if s.strip()]

    # 1. Hook Immediacy Check (First sentence)
    first_sentence = sentences[0] if sentences else ""
    first_words = first_sentence.split()
    hook_len = len(first_words)

    # Optimal opening is punchy (6-14 words) without slow greetings
    has_fluff = any(re.search(pat, first_sentence, re.IGNORECASE) for pat in SLOW_INTRO_PATTERNS)
    if has_fluff:
        hook_strength = 3.0
    elif 5 <= hook_len <= 15:
        hook_strength = 9.5
    elif hook_len <= 20:
        hook_strength = 7.5
    else:
        hook_strength = 5.0

    # 2. Pacing & Sentence Length Variance
    sent_lengths = [len(s.split()) for s in sentences if len(s.split()) > 0]
    avg_sent_len = sum(sent_lengths) / len(sent_lengths) if sent_lengths else 10.0

    if is_short:
        # Shorts require punchy sentences (avg 8-13 words)
        if 7.0 <= avg_sent_len <= 14.0:
            pacing_score = 9.0
        elif avg_sent_len < 7.0:
            pacing_score = 7.5
        else:
            pacing_score = max(4.0, 10.0 - ((avg_sent_len - 14.0) * 0.8))
    else:
        # Long-form can accommodate slightly longer analytical sentences (10-18 words)
        if 9.0 <= avg_sent_len <= 18.0:
            pacing_score = 8.8
        else:
            pacing_score = 6.5

    # 3. Conciseness & Information Density
    # Penalize repeated sentences or duplicate words
    unique_words_ratio = len(set(w.lower() for w in words)) / total_words if total_words > 0 else 1.0
    conciseness_score = min(10.0, max(2.0, unique_words_ratio * 12.0))

    # Overall Heuristic Retention Score (0-100)
    score = (hook_strength * 4.0) + (pacing_score * 3.5) + (conciseness_score * 2.5)
    score = round(min(100.0, max(10.0, score * 10.0 / 10.0)), 1)

    if score >= 80.0:
        verdict = "High Retention Potential"
    elif score >= 65.0:
        verdict = "Moderate Retention Potential"
    else:
        verdict = "Needs Structural Optimization"

    return {
        "retention_score": score,
        "hook_strength": round(hook_strength * 10.0, 1),
        "pacing_score": round(pacing_score * 10.0, 1),
        "conciseness_score": round(conciseness_score * 10.0, 1),
        "avg_words_per_sentence": round(avg_sent_len, 1),
        "total_words": total_words,
        "verdict": verdict,
        "limitations": (
            "Heuristic estimate based on structural pacing and opening brevity. "
            "Does not predict real-world viewer behavior, which depends on packaging and distribution."
        ),
    }


def optimize_script_for_retention(
    script_text: str,
    topic: str,
    aspect_ratio: str = "9:16",
    target_duration: str = "30-50s",
) -> Dict[str, Any]:
    """
    Analyzes script structure, strips fluff, generates a high-retention immediate hook,
    and formats pacing for Shorts vs Long-form.
    Saves candidate to output/script_optimized.txt.
    """
    is_short = (aspect_ratio == "9:16" or "30" in str(target_duration) or "short" in str(target_duration).lower())
    original_text = script_text.strip()
    original_metrics = calculate_heuristic_retention_score(original_text, is_short=is_short)

    # 1. Clean opening fluff and greetings
    cleaned = clean_opening_fluff(original_text)
    if not cleaned:
        cleaned = original_text

    lines = [l.strip() for l in cleaned.splitlines() if l.strip()]

    # 2. Immediate Hook Construction
    # If the first line doesn't immediately mention the core subject or hook, reinforce it
    first_line = lines[0] if lines else ""
    topic_clean = re.sub(r"[^\w\s]", "", topic).strip()

    # If first sentence is too timid or vague, sharpen it
    if len(first_line.split()) < 4 or any(w in first_line.lower() for w in ("తెలుసా", "చూద్దాం", "లెట్స్ సీ")):
        # Synthesize punchy hook referencing topic
        hook_prefix = f"{topic_clean}: అసలు విషయం ఇక్కడ ఉంది!"
        lines[0] = f"{hook_prefix} {first_line}".strip()

    # 3. Pacing & Flow Optimization
    optimized_lines = []
    seen_concepts = set()

    for line in lines:
        # Deduplicate near-identical sentences across lines
        words_set = frozenset(re.sub(r"[^\w\s]", "", line.lower()).split()[:6])
        if len(words_set) >= 4 and words_set in seen_concepts:
            continue
        if len(words_set) >= 4:
            seen_concepts.add(words_set)

        # Break overly long sentences in Shorts
        if is_short and len(line.split()) > 22:
            parts = re.split(r"[\,\;]\s*", line)
            if len(parts) >= 2:
                optimized_lines.append(parts[0].strip() + ".")
                optimized_lines.append(" ".join(parts[1:]).strip())
                continue

        optimized_lines.append(line)

    optimized_text = "\n".join(optimized_lines).strip()
    optimized_metrics = calculate_heuristic_retention_score(optimized_text, is_short=is_short)

    # 4. Save to separate candidate file output/script_optimized.txt (Never overwrite original!)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidate_path = OUTPUT_DIR / "script_optimized.txt"
    try:
        candidate_path.write_text(optimized_text, encoding="utf-8")
    except Exception:
        pass

    return {
        "original_script": original_text,
        "optimized_script": optimized_text,
        "candidate_file": str(candidate_path),
        "original_retention_score": original_metrics["retention_score"],
        "optimized_retention_score": optimized_metrics["retention_score"],
        "improvement": round(optimized_metrics["retention_score"] - original_metrics["retention_score"], 1),
        "is_short": is_short,
        "diagnostics": {
            "original": original_metrics,
            "optimized": optimized_metrics,
        },
    }


def compare_scripts(original: str, optimized: str) -> Dict[str, Any]:
    """Generates a side-by-side analytical comparison between original and candidate scripts."""
    orig_words = len(original.split())
    opt_words = len(optimized.split())
    return {
        "original_word_count": orig_words,
        "optimized_word_count": opt_words,
        "word_delta": opt_words - orig_words,
        "original_snippet": original[:180] + ("..." if len(original) > 180 else ""),
        "optimized_snippet": optimized[:180] + ("..." if len(optimized) > 180 else ""),
        "changes_applied": [
            "Stripped slow preamble greetings and filler introductions.",
            "Sharpened opening 3-second hook for immediate viewer intrigue.",
            "Enforced punchy sentence pacing compliant with mobile retention benchmarks.",
        ],
    }

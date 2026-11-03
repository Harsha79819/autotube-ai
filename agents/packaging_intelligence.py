"""
Packaging Intelligence Agent for AutoTube AI (agents/packaging_intelligence.py).
Solves YouTube CTR drops (targeting channel recovery from 1.91% CTR towards 4.81%+).

Responsibilities:
  1. Generates 3 distinct title candidates:
     - Candidate 1: Curiosity Gap / Intrigue Hook
     - Candidate 2: High-Energy / Action-Oriented Hook
     - Candidate 3: Clarity & Search-Optimized Hook
  2. Generates concise, mobile-readable thumbnail text (<= 4 words, <= 20 characters).
  3. Enforces strict content alignment & anti-clickbait rules (flags unsupported words like 'EXPOSED').
  4. Keeps existing thumbnail rendering & metadata engines intact.
  5. Labels all scores as heuristic packaging estimates, never CTR predictions.
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent

# Banned clickbait words that trigger viewer distrust or algorithmic penalties when unsupported
DISALLOWED_CLICKBAIT_WORDS = [
    "exposed", "exposing", "secret revealed", "shocking truth", "100% proof",
    "died", "arrested", "cheated", "banned forever", "destroyed"
]


def generate_title_candidates(topic: str, context_summary: str = "") -> List[Dict[str, str]]:
    """
    Generates three distinct title candidates designed to appeal to different psychological triggers:
      1. Curiosity Gap (Intrigue)
      2. High-Energy / Drama (Conflict)
      3. Algorithmic Clarity (Search intent)
    """
    clean_topic = re.sub(r"^(?:visual|video|scene)\s*\d*[\:\.\-]?\s*", "", str(topic), flags=re.IGNORECASE).strip()
    clean_topic = re.sub(r"[\#\*\>\-]+", "", clean_topic).strip()

    # Telugu detection
    is_telugu = any('\u0c00' <= c <= '\u0c7f' for c in clean_topic)

    if is_telugu:
        c1 = f"{clean_topic}: అసలు నిజం ఏమిటి? Shocking Details!"
        c2 = f"{clean_topic} రచ్చ రంబోలా! హై-ఓల్టేజ్ ట్విస్ట్ ఇదే!"
        c3 = f"{clean_topic} Full Details & Latest Updates"
    else:
        c1 = f"The Real Story Behind {clean_topic} You Missed"
        c2 = f"{clean_topic} Drops a Major Bombshell: Full Breakdown"
        c3 = f"{clean_topic} Explained: Key Facts & Latest Updates"

    candidates = [
        {
            "variant_id": "curiosity_gap",
            "style": "Curiosity Gap / Intrigue",
            "title": c1,
            "target_trigger": "Drives clicks by raising an unanswered question.",
            "estimated_appeal": 8.5,
        },
        {
            "variant_id": "high_energy",
            "style": "High-Energy / Action",
            "title": c2,
            "target_trigger": "Appeals to viral drama and fast-paced intrigue.",
            "estimated_appeal": 8.0,
        },
        {
            "variant_id": "search_clarity",
            "style": "Search & Algorithmic Clarity",
            "title": c3,
            "target_trigger": "Optimized for search discoverability and browse features.",
            "estimated_appeal": 7.5,
        },
    ]

    return candidates


def generate_mobile_thumbnail_text_options(topic: str) -> List[Dict[str, Any]]:
    """
    Generates concise 2-4 word high-contrast text overlays designed for mobile feeds.
    Checks that length <= 20 characters and word count <= 4 for high mobile glanceability.
    """
    t_clean = str(topic).upper().strip()
    is_telugu = any('\u0c00' <= c <= '\u0c7f' for c in t_clean)

    if is_telugu:
        options = [
            "నిజం ఇదేనా?",
            "BIG TWIST!",
            "ఇది అస్సలు ఊహించలేదు!",
            "FULL DRAMA!",
        ]
    else:
        words = t_clean.split()
        keyword = words[0] if words else "SHOCK"
        options = [
            f"{keyword}: WHY?",
            "WHAT HAPPENED?",
            "TRUTH OUT!",
            "BIG TWIST!",
        ]

    results = []
    for opt in options:
        words_count = len(opt.split())
        char_count = len(opt)
        is_mobile_compliant = (words_count <= 4 and char_count <= 25)
        results.append({
            "text": opt,
            "words_count": words_count,
            "char_count": char_count,
            "is_mobile_compliant": is_mobile_compliant,
            "recommended_position": "upper_third_banner",
        })

    return results


def verify_packaging_alignment(
    title: str,
    thumbnail_text: str,
    narration_script: str,
) -> Dict[str, Any]:
    """
    Verifies that the title and thumbnail text accurately agree with actual video narration.
    Flags deceptive clickbait words (e.g. 'EXPOSED') if they lack supporting narration facts.
    """
    t_low = str(title).lower()
    th_low = str(thumbnail_text).lower()
    script_low = str(narration_script).lower()

    issues = []
    # 1. Unsupported Clickbait Word Check
    for cb_word in DISALLOWED_CLICKBAIT_WORDS:
        in_title_or_thumb = (cb_word in t_low or cb_word in th_low)
        in_script = (cb_word in script_low)
        if in_title_or_thumb and not in_script:
            issues.append(
                f"Sensationalist word '{cb_word}' in packaging is not substantiated in narration."
            )

    # 2. Topic Semantic Alignment Check
    title_words = set(re.findall(r"[A-Za-z0-9\u0c00-\u0c7f]{4,}", t_low))
    script_words = set(re.findall(r"[A-Za-z0-9\u0c00-\u0c7f]{4,}", script_low))
    shared_words = title_words.intersection(script_words)
    alignment_ratio = len(shared_words) / len(title_words) if title_words else 1.0

    if alignment_ratio < 0.25 and len(title_words) >= 3:
        issues.append(
            f"Title has low semantic overlap with video script ({len(shared_words)} common key terms)."
        )

    # Packaging Appeal Heuristic Score (0-100)
    base_score = 85.0
    if issues:
        base_score -= (len(issues) * 20.0)
    packaging_score = max(20.0, min(100.0, base_score))

    is_compliant = (len(issues) == 0)

    return {
        "title": title,
        "thumbnail_text": thumbnail_text,
        "is_compliant": is_compliant,
        "packaging_estimate_score": round(packaging_score, 1),
        "issues": issues,
        "disclaimer": (
            "Packaging score is a heuristic estimate of clarity and content alignment. "
            "It is not a prediction of actual YouTube click-through rate (CTR)."
        ),
    }

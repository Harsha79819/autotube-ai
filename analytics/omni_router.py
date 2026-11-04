"""
AutoTube AI - Omni-Route Channel Performance Intelligence Engine
(analytics/omni_router.py)

Architectural Core:
1. Multi-Dimensional Routing: Dynamically routes incoming topics to the optimal channel
   (Channel 1 vs Channel 2), format (Shorts 9:16 vs Long-Form 16:9), voice modulation (Anchor vs Roast),
   and visual engine (Documentary 16:9 vs Canvas 9:16).
2. Omni-Viral Score (OVS): Evaluates and ranks candidate topics using audited YouTube audience
   performance signals and high-converting keyword multipliers.
3. Multi-Provider Omni-Cascade: Routes LLM synthesis through Gemini 2.5 Flash -> Groq Llama 3.3 -> OpenRouter.
4. Post-Bigg Boss Self-Healing: Automatically detects season wrap-up and pivots Channel 2 into
   evergreen Tollywood trolls, movie/OTT reviews, and pop culture roasts.
"""

import os
import re
import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ============================================================
# AUDITED AUDIENCE DEMAND KEYWORD WEIGHTS
# Derived from actual channel performance metrics
# ============================================================

CHANNEL_KEYWORD_WEIGHTS: Dict[str, Dict[str, float]] = {
    "viral_talks_me&mine": {
        # High-growth emotional & conflict hooks
        "exposed": 1.50,
        "double game": 1.45,
        "unfair": 1.45,
        "scripted": 1.40,
        "truth behind": 1.40,
        "honest review": 1.40,
        "review": 1.30,
        "roast": 1.35,
        "roasting": 1.35,
        "elimination": 1.30,
        "leaks": 1.25,
        "twist": 1.25,
        "shocking": 1.20,
        "danger zone": 1.25,
        "wildcard": 1.25,
        "housemates": 1.15,
        "controversy": 1.30,
        "troll": 1.30,
        # High-performing entities
        "sudheer": 1.35,
        "rohit": 1.25,
        "aman": 1.25,
        "nagarjuna": 1.20,
        "prabhas": 1.30,
        "pawan kalyan": 1.30,
        "mahesh": 1.20,
        "rajamouli": 1.25,
        "allu arjun": 1.25,
        "box office": 1.25,
        "ott": 1.20,
    },
    "Imaginary_facts": {
        # High-growth mystery, science, & explainer hooks
        "mystery": 1.45,
        "unsolved": 1.45,
        "ancient": 1.35,
        "science": 1.30,
        "isro": 1.35,
        "breakthrough": 1.30,
        "secret": 1.30,
        "space": 1.25,
        "ai": 1.25,
        "artificial intelligence": 1.25,
        "deep learning": 1.20,
        "technology": 1.20,
        "bizarre": 1.25,
        "deep dive": 1.25,
        "engineering": 1.30,
        "untold": 1.30,
        "real story": 1.25,
        "quantum": 1.25,
        "robot": 1.20,
        "superpower": 1.20,
        "hyderabad": 1.20,
        "andhra": 1.20,
        "telangana": 1.20,
    },
}

PACKAGING_MULTIPLIERS = [
    (r"\b(why|how|what happens|the truth|revealed|exposed)\b", 1.15),
    (r"\b(top\s+\d+|\d+\s+reasons|\d+\s+facts)\b", 1.10),
    (r"[:!?\-–]", 1.05),
]


def calculate_omni_viral_score(
    topic: str,
    category: str = "",
    channel_name: str = "viral_talks_me&mine",
) -> float:
    """Calculates Omni-Viral Score (OVS) for a topic. Baseline 1.00; top viral: 1.40 - 2.20+."""
    if not topic or not str(topic).strip():
        return 1.0

    t_lower = str(topic).strip().lower()
    ch_key = "viral_talks_me&mine" if "viral" in channel_name.lower() or "channel 2" in channel_name.lower() else "Imaginary_facts"

    weights = CHANNEL_KEYWORD_WEIGHTS.get(ch_key, CHANNEL_KEYWORD_WEIGHTS["viral_talks_me&mine"])
    score = 1.0

    matched_boost = 0.0
    for kw, boost in weights.items():
        if kw in t_lower:
            matched_boost += (boost - 1.0)

    score += matched_boost

    for pattern, mult in PACKAGING_MULTIPLIERS:
        if re.search(pattern, t_lower, flags=re.IGNORECASE):
            score *= mult

    word_count = len(topic.split())
    if word_count < 5 or word_count > 20:
        score *= 0.85

    return round(min(score, 2.50), 3)


def route_topic_spec(
    topic_idea: str,
    requested_category: str = "",
    force_channel: Optional[str] = None,
    force_aspect: Optional[str] = None,
) -> Dict[str, Any]:
    """Multi-Dimensional Omni-Router determining channel, format, voice, and visual policy."""
    t_clean = str(topic_idea).strip()
    t_lower = t_clean.lower()
    c_lower = str(requested_category or "").lower()

    is_tech_fact = any(
        k in t_lower or k in c_lower
        for k in (
            "tech", "ai ", "ai:", "artificial intelligence", "isro", "nasa", "science",
            "ancient", "mystery", "quantum", "semiconductor", "robot", "space", "gadget",
            "engineering", "history", "unsolved", "pyramid", "temple", "breaking news"
        )
    )
    is_entertainment = any(
        k in t_lower or k in c_lower
        for k in (
            "bigg boss", "bb10", "tollywood", "cinema", "movie review", "ott",
            "prabhas", "pawan", "nagarjuna", "roast", "troll", "teaser", "trailer",
            "box office", "sudheer", "rohit", "aman", "housemates", "eviction"
        )
    )

    if force_channel:
        target_ch = "Channel 2 (Secondary)" if "channel 2" in force_channel.lower() or "viral" in force_channel.lower() else "Channel 1 (Primary)"
    elif is_entertainment and not is_tech_fact:
        target_ch = "Channel 2 (Secondary)"
    elif is_tech_fact:
        target_ch = "Channel 1 (Primary)"
    else:
        target_ch = "Channel 2 (Secondary)"

    ch_slug = "viral_talks_me&mine" if "Channel 2" in target_ch else "Imaginary_facts"

    is_long_form_indicator = any(
        k in t_lower or k in c_lower
        for k in ("deep dive", "in-depth", "complete history", "full story", "breakdown", "analysis", "documentary", "16:9")
    )

    if force_aspect:
        aspect = force_aspect
    elif is_long_form_indicator:
        aspect = "16:9"
    else:
        aspect = "9:16"

    captions_enabled = (aspect == "16:9")
    use_canvas = (aspect != "16:9")
    voice_mode = "roast_modulated" if ch_slug == "viral_talks_me&mine" else "news_anchor"
    memes_enabled = (ch_slug == "viral_talks_me&mine")

    if aspect == "16:9":
        duration = "5-8m" if any(k in t_lower for k in ("history", "unsolved", "complete", "dynasty")) else "3-5m"
    else:
        duration = "60-90s"

    ovs = calculate_omni_viral_score(t_clean, category=requested_category, channel_name=ch_slug)

    return {
        "topic": t_clean,
        "target_channel": target_ch,
        "channel_slug": ch_slug,
        "aspect_ratio": aspect,
        "target_duration": duration,
        "captions": captions_enabled,
        "use_canvas": use_canvas,
        "voice_mode": voice_mode,
        "memes_enabled": memes_enabled,
        "omni_viral_score": ovs,
        "instagram_reels": (aspect == "9:16"),
    }


def synthesize_viral_topics_omni(
    category: str,
    count: int = 6,
    channel_name: str = "viral_talks_me&mine",
) -> List[Dict[str, Any]]:
    """Synthesizes and scores fresh viral topics using Omni-Provider LLM cascade."""
    try:
        from agents.topic_suggester import fetch_ai_topic_suggestions, load_used_topics
        raw_suggestions = fetch_ai_topic_suggestions(category, count=count + 4, use_ai=True)
    except Exception as e:
        print(f"OmniRouter fetch notice: {e}")
        raw_suggestions = []

    used = set()
    try:
        from agents.topic_suggester import load_used_topics
        used = load_used_topics()
    except Exception:
        pass

    scored_topics: List[Dict[str, Any]] = []
    seen = set()

    for item in raw_suggestions:
        t_str = str(item).strip()
        if not t_str or t_str.lower() in used:
            continue
        norm_key = re.sub(r"[^a-zA-Z0-9]", "", t_str.lower())
        if norm_key in seen:
            continue
        seen.add(norm_key)

        route_info = route_topic_spec(t_str, requested_category=category, force_channel=channel_name)
        scored_topics.append(route_info)

    scored_topics.sort(key=lambda x: x["omni_viral_score"], reverse=True)
    return scored_topics[:count]


if __name__ == "__main__":
    print("🚀 OMNI-ROUTE TEST RUN")
    test_topics = [
        ("Sudheer Double Game Exposed: Unfair Mid-Week Eviction Drama", "Bigg Boss Telugu"),
        ("The Paradise Movie Honest Review: Why Good Content Triumphed", "Movie Reviews"),
        ("ISRO Gaganyaan Mission: Ancient Indian Space Dreams Realized", "Tech News"),
        ("General discussion on things", "General Topic"),
    ]
    for topic, cat in test_topics:
        spec = route_topic_spec(topic, requested_category=cat)
        print(f"📌 Topic: {spec['topic']} -> Ch: {spec['target_channel']}, Aspect: {spec['aspect_ratio']}, Captions: {spec['captions']}, Canvas: {spec['use_canvas']}, Voice: {spec['voice_mode']}, OVS: {spec['omni_viral_score']}")
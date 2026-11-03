"""
Content Intelligence Agent for AutoTube AI.
Evaluates topic relevance, freshness, audience interest, and available evidence
tailored for the channel's established audience ('viral_talks_me&mine').

Supports three configurable content pillars:
  1. tollywood_celebrity: Star buzz, Telugu cinema updates, controversies, box office.
  2. behind_the_scenes: Production secrets, Bigg Boss Telugu house dynamics, industry insider facts.
  3. viral_entertainment_explainers: Pop-culture deep dives, why movies succeed/flop, trending controversies.

Preserves the existing topic selection workflow and never changes user topics automatically.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent

# Validated Content Pillars for viral_talks_me&mine
CONTENT_PILLARS = {
    "tollywood_celebrity": {
        "display_name": "Tollywood & Celebrity Buzz",
        "description": "Star updates, casting reveals, box-office debates, and celebrity news.",
        "keywords": [
            "prabhas", "allu arjun", "ram charan", "jr ntr", "chiranjeevi", "balakrishna",
            "mahesh babu", "pawan kalyan", "nani", "vijay deverakonda", "tollywood", "cinema",
            "box office", "movie release", "trailer", "teaser", "devara", "pushpa", "game changer",
            "kalki", "ss rajmouli", "sukumar", "trivikram", "og", "salaar", "director", "actor"
        ],
    },
    "behind_the_scenes": {
        "display_name": "Behind-The-Scenes & House Drama",
        "description": "Bigg Boss Telugu house insider dynamics, unseen production facts, shooting incidents.",
        "keywords": [
            "bigg boss", "bigg boss telugu", "housemate", "nomination", "eviction", "secret room",
            "unseen footage", "shooting floor", "bts", "behind the scenes", "set secrets",
            "nagarjuna", "thrigun", "vamsi", "shalini", "apoorva", "aman", "jhansi", "sudheer",
            "voting leak", "task controversy", "elimination shock", "anchor", "reality show"
        ],
    },
    "viral_entertainment_explainers": {
        "display_name": "Viral Entertainment Explainers",
        "description": "Deep-dives into viral social debates, why a movie failed/succeeded, pop-culture breakdowns.",
        "keywords": [
            "why it failed", "why it succeeded", "explained", "mystery behind", "controversy",
            "truth behind", "reality check", "analysis", "case study", "viral debate",
            "social media trend", "flop or hit", "breakdown", "dark side", "rise and fall",
            "what really happened", "public reaction", "audience verdict"
        ],
    },
}


def detect_content_pillar(topic: str) -> str:
    """Classifies a topic into one of the three established content pillars."""
    if not topic:
        return "viral_entertainment_explainers"
    
    t_lower = str(topic).lower()
    scores = {}
    for pillar_id, data in CONTENT_PILLARS.items():
        score = sum(1 for kw in data["keywords"] if kw in t_lower)
        scores[pillar_id] = score

    best_pillar = max(scores, key=scores.get)
    if scores[best_pillar] > 0:
        return best_pillar
    return "viral_entertainment_explainers"


def check_topic_novelty(topic: str, threshold: float = 0.65) -> Tuple[bool, float, Optional[str]]:
    """
    Checks whether a topic is a repetitive duplicate of past used topics in data/used_topics.json.
    Returns: (is_novel: bool, max_similarity: float, closest_matched_topic: Optional[str])
    """
    if not topic:
        return False, 1.0, None

    clean_topic = re.sub(r"[^\w\s]", "", str(topic).lower()).split()
    topic_set = set(clean_topic)
    if not topic_set:
        return True, 0.0, None

    used_file = ROOT / "data" / "used_topics.json"
    if not used_file.exists():
        return True, 0.0, None

    try:
        used_list = json.loads(used_file.read_text(encoding="utf-8"))
    except Exception:
        used_list = []

    max_sim = 0.0
    closest_topic = None

    for used in used_list:
        used_words = set(re.sub(r"[^\w\s]", "", str(used).lower()).split())
        if not used_words:
            continue
        intersection = len(topic_set.intersection(used_words))
        union = len(topic_set.union(used_words))
        sim = intersection / union if union > 0 else 0.0

        if sim > max_sim:
            max_sim = sim
            closest_topic = used

    is_novel = max_sim < threshold
    return is_novel, round(max_sim, 3), closest_topic if max_sim >= threshold else None


def evaluate_topic_intelligence(
    topic: str,
    channel_context: str = "viral_talks_me&mine",
    available_sources_count: int = 3,
) -> Dict[str, Any]:
    """
    Evaluates topic relevance, freshness, audience interest, and available evidence.
    Returns a comprehensive diagnostic score and recommendation rationale.
    """
    if not topic or not str(topic).strip():
        return {
            "topic": "",
            "pillar": "unknown",
            "overall_score": 0,
            "freshness_score": 0,
            "audience_interest_score": 0,
            "evidence_score": 0,
            "novelty_score": 0,
            "is_recommended": False,
            "rationale": "Topic is empty.",
            "diagnostics": {},
        }

    topic_str = str(topic).strip()
    pillar = detect_content_pillar(topic_str)
    pillar_info = CONTENT_PILLARS.get(pillar, {})

    # 1. Audience Interest Score (0-10) based on channel alignment
    t_low = topic_str.lower()
    interest_matches = sum(1 for kw in pillar_info.get("keywords", []) if kw in t_low)
    audience_interest_score = min(10.0, 5.0 + (interest_matches * 1.5))

    # 2. Freshness Score (0-10)
    freshness_signals = [
        "today", "latest", "update", "shock", "breaking", "leak", "controversy",
        "now", "2026", "review", "teaser", "first look", "nominations", "eviction"
    ]
    fresh_matches = sum(1 for s in freshness_signals if s in t_low)
    freshness_score = min(10.0, 6.0 + (fresh_matches * 1.2))

    # 3. Evidence / Verification Confidence Score (0-10)
    # Penalizes wild unverifiable buzzwords like 'illuminati', 'exposed alien', etc.
    wild_rumor_words = ["alien", "illuminati", "ghost confirmed", "100% fake"]
    has_wild_rumors = any(w in t_low for w in wild_rumor_words)
    if has_wild_rumors:
        evidence_score = 3.0
    else:
        evidence_score = min(10.0, 6.0 + min(available_sources_count, 4))

    # 4. Novelty Score (0-10)
    is_novel, max_sim, closest = check_topic_novelty(topic_str)
    if is_novel:
        novelty_score = max(5.0, 10.0 - (max_sim * 10.0))
    else:
        novelty_score = max(1.0, 10.0 - (max_sim * 12.0))

    # Overall Weighted Score (0-100)
    # Formula: Interest (35%) + Freshness (25%) + Novelty (25%) + Evidence (15%)
    overall = (
        (audience_interest_score * 3.5)
        + (freshness_score * 2.5)
        + (novelty_score * 2.5)
        + (evidence_score * 1.5)
    )
    overall_score = round(min(100.0, max(0.0, overall)), 1)
    is_recommended = bool(overall_score >= 68.0 and is_novel)

    # Rationale generation
    reasons = []
    if audience_interest_score >= 8.0:
        reasons.append(f"Strongly aligns with {pillar_info.get('display_name', 'entertainment')} audience.")
    if is_novel:
        reasons.append("High topic novelty with zero recent channel duplication.")
    else:
        reasons.append(f"Shares angle similarity with past topic: '{closest}'.")
    if evidence_score >= 7.0:
        reasons.append("Verifiable editorial news and entertainment background available.")

    rationale = " ".join(reasons) if reasons else "Sufficient candidate content score."

    return {
        "topic": topic_str,
        "pillar": pillar,
        "pillar_name": pillar_info.get("display_name", pillar),
        "overall_score": overall_score,
        "freshness_score": round(freshness_score, 1),
        "audience_interest_score": round(audience_interest_score, 1),
        "evidence_score": round(evidence_score, 1),
        "novelty_score": round(novelty_score, 1),
        "is_novel": is_novel,
        "closest_duplicate": closest,
        "is_recommended": is_recommended,
        "rationale": rationale,
        "channel_target": channel_context,
    }


def get_vetted_pillar_topics(pillar: str = "tollywood_celebrity") -> List[Dict[str, Any]]:
    """Returns curated vetted topic candidates for a specific content pillar."""
    candidates_pool = {
        "tollywood_celebrity": [
            "Devara 2 & Pushpa 2: High-Stakes Box Office Faceoff Analyzed",
            "Prabhas Kalki 2 Cinematic Universe: Key Story Leaks and Expectations",
            "SSMB29 Globe-Trotting Adventure: Rajamouli's International Casting Updates",
            "Ram Charan Game Changer Climax: Behind the Intense Action Choreography",
        ],
        "behind_the_scenes": [
            "Bigg Boss Telugu 10 House Politics: Secret Alliances That Broke Down",
            "Inside Tollywood VFX Studios: How High-Budget CGI Scenes Are Really Made",
            "Bigg Boss Telugu Weekend Shoot: What Happens During Nagarjuna's Elimination Pass",
            "Tollywood Set Security: How Big Movie Leaks Happen and How Teams Prevent Them",
        ],
        "viral_entertainment_explainers": [
            "Why Certain Big-Budget Pan-India Films Flop: The Script Density Problem Explained",
            "The Psychology of Bigg Boss Telugu Voting: How Social Media Fan Armies Influence Results",
            "Telugu Cinema Ticket Pricing Dynamics: How Single Screens vs Multiplexes React",
            "The Rise of Mid-Budget Concept Hits in Tollywood: What Audience Really Craves",
        ],
    }
    
    selected_pool = candidates_pool.get(pillar, candidates_pool["viral_entertainment_explainers"])
    evaluated = [evaluate_topic_intelligence(t) for t in selected_pool]
    return sorted(evaluated, key=lambda x: x["overall_score"], reverse=True)

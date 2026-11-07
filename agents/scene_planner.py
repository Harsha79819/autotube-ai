"""
Pacing engine: collapse 24-26 sentence-level sections into 8-10 real scenes.

Input  : `timed_sections` from video_agent.find_section_timestamps(), i.e. a list of
         {"section": int, "visual": int, "start": float, "end": float, "narration": str}
Output : list[Scene], each 6-9 s, cut at natural topic/sentence boundaries, with the
         entities, emotion, layout and punchline banner already decided.

The cut points come from a small dynamic program, not a fixed chunk size:

    cost(group) = ((duration - ideal) / ideal)^2        stay near the ideal scene length
                + hard penalty if outside [min_s, max_s]
                + CUT_WEIGHT * (1 - boundary_strength)   only cut where the script "turns"

boundary_strength rewards: sentence-ending punctuation, a change of who is being
talked about, a change of emotion, and a real pause in the voiceover.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from agents.entity_bank import Entity, EntityBank, get_bank

MIN_SCENE_S = 6.0
MAX_SCENE_S = 9.5
CUT_WEIGHT = 1.2

# --------------------------------------------------------------------------- #
# Emotion lexicon. Starter list - extend it with the words your scripts really
# use. Telugu entries are matched as substrings (agglutinative language), Latin
# entries as lowercase substrings too. Priority on ties: angry > shocked > smug > serious.
# --------------------------------------------------------------------------- #
EMOTION_LEXICON: Dict[str, Tuple[str, ...]] = {
    "angry": (
        "కోపం", "కోప", "అరిచ", "అరుస్త", "అరుపు", "అరవ", "గొడవ", "తిట్ట", "రెచ్చ", "మండిపడ",
        "angry", "furious", "scream", "shout", "yell", "fight", "argu", "slam", "blast", "kopam",
    ),
    "shocked": (
        "షాక్", "ఆశ్చర్య", "అనూహ్య", "నమ్మలేక", "ఊహించ",
        "shock", "unexpected", "twist", "unbelievable", "bombshell", "suddenly", "can't believe",
    ),
    "smug": (
        "సేఫ్ గేమ్", "సేఫ్‌గేమ్", "నటన", "నటిస్", "డ్రామా", "జిత్తు", "గేమ్ ప్లాన్",
        "safe game", "plays safe", "playing safe", "fake", "acting", "drama", "two-faced",
        "backstab", "cunning", "game plan", "strategy",
    ),
    "serious": (
        "నామినేషన్", "నామినేట్", "ఎలిమినేష", "ఎలిమినేట్", "వార్నింగ్", "హెచ్చరిక", "సీరియస్", "కెప్టెన్",
        "nomination", "nominated", "elimination", "eliminated", "warning", "serious",
        "captain", "verdict", "punishment", "decision",
    ),
}
_PRIORITY = ("angry", "shocked", "smug", "serious")

# Visual language per emotion (used by canvas_engine too)
EMOTION_COLORS = {
    "angry": "#E63946",
    "shocked": "#00B4D8",
    "smug": "#9B5DE5",
    "serious": "#F4A261",
    "neutral": "#FFC400",
}


def detect_emotion(text: str, default: str = "neutral") -> str:
    low = (text or "").lower()
    best, best_score = default, 0
    for emo in _PRIORITY:
        score = sum(low.count(tok.lower()) for tok in EMOTION_LEXICON[emo])
        if score > best_score:
            best, best_score = emo, score
    return best


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class SceneEntity:
    entity: Entity
    emotion: str
    expression_used: str = ""  # which cutout file actually matched (after fallback)


@dataclass
class Scene:
    index: int  # 1-based
    start: float
    end: float
    narration: str
    section_ids: List[int]
    visual_ids: List[int]
    emotion: str = "neutral"
    banner: str = ""
    layout: str = "broll"  # solo | split | name_card | broll
    entities: List[SceneEntity] = field(default_factory=list)
    mentioned_without_cutout: List[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.1, self.end - self.start)


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
_SENT_SPLIT = re.compile(r"(?<=[.!?।…])\s+|\n+")
_END_PUNCT = (".", "!", "?", "।", "…")


def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text or "") if s and s.strip()]


def extract_banner(text: str, bank: EntityBank, max_words: int = 8) -> str:
    """Pick the punchiest short clause of the scene's narration for the top banner."""
    candidates: List[str] = []
    for sent in split_sentences(text):
        candidates.append(sent)
        parts = [p.strip() for p in re.split(r"[,;:—–-]\s+", sent) if p.strip()]
        if len(parts) > 1:
            candidates.extend(parts)
    best, best_score = "", -1e9
    for cand in candidates:
        words = cand.split()
        n = len(words)
        if n < 2:
            continue
        low = cand.lower()
        emo_hits = sum(1 for emo in _PRIORITY for tok in EMOTION_LEXICON[emo] if tok.lower() in low)
        has_entity = 1 if bank.find_entities(cand) else 0
        score = 2.0 * min(emo_hits, 3) + 1.0 * has_entity
        score += 2.0 if 3 <= n <= max_words else 0.0
        score += 0.7 if cand.rstrip().endswith(("!", "?")) else 0.0
        score -= 0.35 * abs(n - 6)
        if score > best_score:
            best, best_score = cand, score
    if not best:
        best = " ".join((text or "").split()[:max_words])
    words = best.split()
    if len(words) > max_words + 2:
        best = " ".join(words[:max_words]) + "…"
    return best.strip(" ,;:-—–\"'“”")


# --------------------------------------------------------------------------- #
# Consolidation
# --------------------------------------------------------------------------- #
def _target_scene_count(total: float) -> int:
    n = round(total / 7.5)
    if total >= 56:
        n = max(8, min(10, n)) if total <= 95 else math.ceil(total / 8.5)
    return max(2, n)


def _boundary_strengths(sections: List[dict], bank: EntityBank) -> List[float]:
    """strength[i] in [0,1] for cutting AFTER section i (last one is irrelevant)."""
    n = len(sections)
    ents = [{e.slug for e, _ in bank.find_entities(s.get("narration", ""))} for s in sections]
    emos = [detect_emotion(s.get("narration", "")) for s in sections]
    out = [1.0] * n
    for i in range(n - 1):
        text = (sections[i].get("narration") or "").strip()
        s = 0.15
        if text.endswith(_END_PUNCT):
            s += 0.40
        if ents[i] and ents[i + 1] and ents[i] != ents[i + 1]:
            s += 0.30
        elif bool(ents[i]) != bool(ents[i + 1]):
            s += 0.15
        if emos[i] != emos[i + 1]:
            s += 0.15
        gap = float(sections[i + 1].get("start", 0)) - float(sections[i].get("end", 0))
        if gap >= 0.30:
            s += 0.20
        out[i] = min(1.0, s)
    return out


def consolidate(
    timed_sections: List[dict],
    bank: Optional[EntityBank] = None,
    min_s: float = MIN_SCENE_S,
    max_s: float = MAX_SCENE_S,
    target_scenes: Optional[int] = None,
) -> List[List[dict]]:
    """Group consecutive sections into scenes. Sections are never split or reordered."""
    bank = bank or get_bank()
    secs = [s for s in timed_sections if float(s["end"]) > float(s["start"])]
    n = len(secs)
    if n == 0:
        return []
    durs = [float(s["end"]) - float(s["start"]) for s in secs]
    total = float(secs[-1]["end"]) - float(secs[0]["start"])
    k = target_scenes or _target_scene_count(total)
    ideal = min(max(total / k, min_s + 0.5), max_s - 0.5)
    strength = _boundary_strengths(secs, bank)

    prefix = [0.0]
    for d in durs:
        prefix.append(prefix[-1] + d)

    INF = float("inf")
    dp = [INF] * (n + 1)
    back = [0] * (n + 1)
    dp[0] = 0.0
    for j in range(1, n + 1):
        for i in range(j):  # group = sections i..j-1
            if dp[i] == INF:
                continue
            d = prefix[j] - prefix[i]
            cost = ((d - ideal) / ideal) ** 2
            if d < min_s:
                cost += 4.0 * (min_s - d)
            elif d > max_s:
                # a single oversized section is unavoidable; merging more is not
                cost += (6.0 if j - i > 1 else 0.5) * (d - max_s)
            if j < n:
                cost += CUT_WEIGHT * (1.0 - strength[j - 1])
            if dp[i] + cost < dp[j]:
                dp[j], back[j] = dp[i] + cost, i

    groups: List[List[dict]] = []
    j = n
    while j > 0:
        i = back[j]
        groups.append(secs[i:j])
        j = i
    groups.reverse()

    # A trailing sliver (< 2.5 s) reads as a glitch: fold it into the previous scene.
    if len(groups) > 1 and sum(float(s["end"]) - float(s["start"]) for s in groups[-1]) < 2.5:
        groups[-2].extend(groups.pop())
    return groups


# --------------------------------------------------------------------------- #
# Scene construction
# --------------------------------------------------------------------------- #
def _load_overrides(path: Optional[Path]) -> Dict[int, dict]:
    if not path or not Path(path).exists():
        return {}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return {int(k): v for k, v in raw.items()}
    except Exception as exc:
        print(f"[ScenePlanner] ignoring bad overrides file {path}: {exc}")
        return {}


def plan_scenes(
    timed_sections: List[dict],
    bank: Optional[EntityBank] = None,
    overrides_path: Optional[Path | str] = None,
) -> List[Scene]:
    """
    overrides_path: optional JSON {"3": {"banner": "...", "emotion": "angry",
    "entities": ["aman", "thrigun"], "layout": "split"}} keyed by 1-based scene number.
    Lets you (or script_agent) pin anything the heuristics get wrong.
    """
    bank = bank or get_bank()
    overrides = _load_overrides(Path(overrides_path) if overrides_path else None)
    scenes: List[Scene] = []

    groups = consolidate(timed_sections, bank)
    max_canva_allowed = max(2, round(len(groups) * 0.35))
    canva_count = 0
    last_layout = None

    for idx, group in enumerate(groups, start=1):
        narration = " ".join((s.get("narration") or "").strip() for s in group).strip()
        ov = overrides.get(idx, {})
        scene_emotion = ov.get("emotion") or detect_emotion(narration)

        if ov.get("entities"):
            found = [(bank.get(slug), 0) for slug in ov["entities"] if bank.get(slug)]
        else:
            found = bank.find_entities(narration)

        sentences = split_sentences(narration)
        scene_entities: List[SceneEntity] = []
        no_cutout: List[str] = []
        for ent, _pos in found:
            # emotion for THIS person comes from the sentence that talks about them
            own = scene_emotion
            for sent in sentences:
                if any(e.slug == ent.slug for e, _ in bank.find_entities(sent)):
                    local = detect_emotion(sent, default="")
                    if local:
                        own = local
                    break
            if not ent.has_cutouts():
                no_cutout.append(ent.display_name)
                continue
            used = ent.cutout_for(own)
            scene_entities.append(SceneEntity(ent, own, used[0] if used else ""))

        if ov.get("layout"):
            layout = ov["layout"]
        elif len(scene_entities) >= 2:
            layout = "split"
        elif len(scene_entities) == 1:
            # Selective Canva Cadence:
            # Hook (scene 1) always gets Canva punch card.
            # Consecutive scenes must NEVER repeat Canva cards.
            # Limit Canva card budget to ~35% of total scenes.
            is_hook = (idx == 1)
            is_punchy = scene_emotion in ("angry", "shocked", "smug")
            allow_canva = is_hook or (last_layout not in ("solo", "split", "name_card") and canva_count < max_canva_allowed and is_punchy)
            if allow_canva:
                layout = "solo"
            else:
                layout = "broll"
        elif no_cutout:
            if idx == 1 or (last_layout not in ("solo", "split", "name_card") and canva_count < max_canva_allowed):
                layout = "name_card"
            else:
                layout = "broll"
        else:
            layout = "broll"

        if layout in ("solo", "split", "name_card"):
            canva_count += 1
        last_layout = layout

        scenes.append(
            Scene(
                index=idx,
                start=float(group[0]["start"]),
                end=float(group[-1]["end"]),
                narration=narration,
                section_ids=[int(s["section"]) for s in group],
                visual_ids=[int(s["visual"]) for s in group],
                emotion=scene_emotion,
                banner=ov.get("banner") or extract_banner(narration, bank),
                layout=layout,
                entities=scene_entities[:2],
                mentioned_without_cutout=no_cutout,
            )
        )
    return scenes


def describe(scenes: List[Scene]) -> str:
    lines = [f"Scene plan: {len(scenes)} scenes"]
    for s in scenes:
        who = ", ".join(f"{e.entity.display_name}[{e.expression_used or e.emotion}]" for e in s.entities) or "-"
        miss = f"  (no cutout: {', '.join(s.mentioned_without_cutout)})" if s.mentioned_without_cutout else ""
        lines.append(
            f"  #{s.index:<2} {s.start:6.2f}-{s.end:6.2f} ({s.duration:4.1f}s) "
            f"{s.layout:<9} {s.emotion:<8} {who}{miss} | {s.banner}"
        )
    return "\n".join(lines)

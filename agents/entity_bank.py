"""
Curated entity + emotion cutout bank.

Layout on disk (committed or local, your choice):

    data/entities/<slug>/
        meta.json          {"display_name": "Aman", "aliases": ["aman", "అమన్"],
                            "show": "bigg_boss_telugu", "season": 10,
                            "accent": "#E63946"}          (everything optional)
        angry.png          transparent PNG cutouts, one per expression
        shocked.png
        smug.png
        serious.png
        neutral.png        <- the only REQUIRED expression; used as last resort

Why this fixes the "wrong face / wrong season" problem: a cutout is hand-picked
once for the CURRENT season, so there is nothing for a web search to collide
with (Rohit Sharma vs Rohit Sahni, Jhansi Fort vs Jhansi the anchor, ...).
Matching is by explicit alias only, never by fuzzy search.

CLI:
    python -m agents.entity_bank --validate          # report missing / bad cutouts
    python -m agents.entity_bank --find "text ..."   # which entities does this text mention
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

EMOTIONS = ("angry", "shocked", "smug", "serious", "neutral")

# If the exact expression is missing, try these in order. "neutral" is the floor.
EMOTION_FALLBACKS: Dict[str, Tuple[str, ...]] = {
    "angry": ("angry", "serious", "shocked", "neutral"),
    "shocked": ("shocked", "angry", "neutral"),
    "smug": ("smug", "neutral", "serious"),
    "serious": ("serious", "neutral", "smug"),
    "neutral": ("neutral", "serious", "smug"),
}

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENTITY_DIR = Path(os.environ.get("AUTOTUBE_ENTITY_DIR", ROOT / "data" / "entities"))


def _slug(name: str) -> str:
    s = re.sub(r"[^\wఀ-౿]+", "_", name.strip().lower(), flags=re.UNICODE)
    return s.strip("_")


@dataclass
class Entity:
    slug: str
    display_name: str
    folder: Path
    aliases: List[str] = field(default_factory=list)
    show: str = ""
    season: Optional[int] = None
    accent: str = "#FFC400"
    # Phrases that CONTAIN one of this entity's aliases but mean someone/something else
    # ("ram charan", "rohit sharma", "jhansi fort"). A match inside a blocked phrase is ignored.
    block: List[str] = field(default_factory=list)
    cutouts: Dict[str, Path] = field(default_factory=dict)

    def has_cutouts(self) -> bool:
        return bool(self.cutouts)

    def cutout_for(self, emotion: str) -> Optional[Tuple[str, Path]]:
        """Return (expression_used, path) honouring the fallback chain."""
        for exp in EMOTION_FALLBACKS.get(emotion, EMOTION_FALLBACKS["neutral"]):
            if exp in self.cutouts:
                return exp, self.cutouts[exp]
        if self.cutouts:  # unknown emotion label or odd bank: take anything real
            exp = sorted(self.cutouts)[0]
            return exp, self.cutouts[exp]
        return None


class EntityBank:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else DEFAULT_ENTITY_DIR
        self.entities: Dict[str, Entity] = {}
        self._alias_index: List[Tuple[str, str]] = []  # (alias_lower, slug), longest first
        self.reload()

    # ---------------------------------------------------------------- loading
    def reload(self) -> None:
        self.entities.clear()
        if not self.root.exists():
            self._alias_index = []
            return
        for folder in sorted(p for p in self.root.iterdir() if p.is_dir()):
            meta = {}
            meta_path = folder / "meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception as exc:  # bad JSON must not kill the pipeline
                    print(f"[EntityBank] ignoring unreadable {meta_path}: {exc}")
            display = meta.get("display_name") or folder.name.replace("_", " ").title()
            ent = Entity(
                slug=folder.name,
                display_name=display,
                folder=folder,
                aliases=[a for a in meta.get("aliases", []) if a],
                show=meta.get("show", ""),
                season=meta.get("season"),
                accent=meta.get("accent", "#FFC400"),
                block=[b.strip().lower() for b in meta.get("block", []) if b and b.strip()],
            )
            for exp in EMOTIONS:
                p = folder / f"{exp}.png"
                if p.exists() and p.stat().st_size > 0:
                    ent.cutouts[exp] = p
            self.entities[ent.slug] = ent

        index: List[Tuple[str, str]] = []
        for ent in self.entities.values():
            names = {ent.display_name, ent.folder.name.replace("_", " ")} | set(ent.aliases)
            for n in names:
                n = n.strip().lower()
                if n:
                    index.append((n, ent.slug))
        # longest alias first so "rohit sahni" wins over "rohit"
        self._alias_index = sorted(index, key=lambda t: len(t[0]), reverse=True)

    # --------------------------------------------------------------- matching
    def find_entities(self, text: str) -> List[Tuple[Entity, int]]:
        """
        Entities mentioned in `text`, in order of first mention: [(entity, char_pos)].
        Latin aliases need word boundaries ("charan" must not match inside
        "charanamrutham"); Telugu aliases are matched as substrings because
        Telugu is agglutinative (అమన్ → అమన్‌కి / అమన్‌ని).
        """
        if not text or not self._alias_index:
            return []
        hay = text.lower()
        taken: List[Tuple[int, int]] = []
        found: Dict[str, int] = {}
        blocked: Dict[str, List[Tuple[int, int]]] = {}
        for slug, ent in self.entities.items():
            spans = [(m.start(), m.end()) for phrase in ent.block for m in re.finditer(re.escape(phrase), hay)]
            if spans:
                blocked[slug] = spans
        for alias, slug in self._alias_index:
            is_latin = alias.isascii()
            pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])" if is_latin else re.escape(alias)
            for m in re.finditer(pattern, hay):
                span = (m.start(), m.end())
                if any(span[0] < e and s < span[1] for s, e in taken):
                    continue  # already claimed by a longer alias
                if any(span[0] < e and s < span[1] for s, e in blocked.get(slug, ())):
                    continue  # inside a phrase this entity explicitly does NOT mean (e.g. "ram charan")
                taken.append(span)
                if slug not in found or m.start() < found[slug]:
                    found[slug] = m.start()
        ordered = sorted(found.items(), key=lambda kv: kv[1])
        return [(self.entities[slug], pos) for slug, pos in ordered]

    def get(self, slug: str) -> Optional[Entity]:
        return self.entities.get(slug)

    # ------------------------------------------------------------- validation
    def validate(self) -> List[str]:
        problems: List[str] = []
        if not self.entities:
            problems.append(f"No entities found under {self.root}")
        try:
            from PIL import Image
        except ImportError:
            Image = None
        for ent in self.entities.values():
            if "neutral" not in ent.cutouts:
                problems.append(f"{ent.slug}: missing neutral.png (required last-resort expression)")
            if not ent.aliases:
                problems.append(f"{ent.slug}: no aliases in meta.json (matches display name only)")
            for exp, path in ent.cutouts.items():
                if Image is None:
                    continue
                try:
                    with Image.open(path) as im:
                        if im.mode != "RGBA":
                            problems.append(f"{ent.slug}/{exp}.png: not RGBA - background is not transparent")
                        else:
                            lo, hi = im.getchannel("A").getextrema()
                            if lo == 255:
                                problems.append(f"{ent.slug}/{exp}.png: alpha is fully opaque - not a real cutout")
                        if min(im.size) < 600:
                            problems.append(f"{ent.slug}/{exp}.png: {im.size[0]}x{im.size[1]} is small; "
                                            "use >= 1000px tall or it will look soft on a 1080x1920 canvas")
                except Exception as exc:
                    problems.append(f"{ent.slug}/{exp}.png: unreadable ({exc})")
        return problems


_BANK: Optional[EntityBank] = None


def get_bank(refresh: bool = False) -> EntityBank:
    global _BANK
    if _BANK is None or refresh:
        _BANK = EntityBank()
    return _BANK


if __name__ == "__main__":
    bank = EntityBank()
    if "--find" in sys.argv:
        txt = sys.argv[sys.argv.index("--find") + 1]
        for ent, pos in bank.find_entities(txt):
            print(f"{pos:4d}  {ent.display_name}  ({', '.join(sorted(ent.cutouts)) or 'no cutouts'})")
    else:
        print(f"Bank: {bank.root}  ({len(bank.entities)} entities)")
        for ent in bank.entities.values():
            print(f"  {ent.display_name:<20} {', '.join(sorted(ent.cutouts)) or '-'}")
        issues = bank.validate()
        print("\nOK" if not issues else "\n" + "\n".join(f"  ! {i}" for i in issues))
        sys.exit(1 if issues else 0)

"""
agents/entity_harvester.py - Autonomous Entity Harvester & Visual Asset Seeder

Ensures zero cold-start entity errors in AutoTube AI:
1. Dynamically detects all celebrities, contestants, and people mentioned in the script/topic.
2. Checks whether a local verified reference portrait exists in reference_assets/ or assets/entities/.
3. If missing, automatically downloads, audits (via NegativeMemoryLedger), and stores an HD portrait.
4. Permanently registers the discovered entity in SQLite autotube.db (entity_registry table).
"""

import os
import re
import json
import sqlite3
import requests
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
from PIL import Image

from data.negative_ledger import get_negative_ledger
from providers.image import search_duckduckgo_images

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "autotube.db"
CONTESTANT_REF_DIR = ROOT / "reference_assets" / "contestants"
ENTITIES_REF_DIR = ROOT / "assets" / "entities"

CONTESTANT_REF_DIR.mkdir(parents=True, exist_ok=True)
ENTITIES_REF_DIR.mkdir(parents=True, exist_ok=True)


def _get_entity_db_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def init_entity_registry():
    conn = _get_entity_db_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entity_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT NOT NULL UNIQUE,
            aliases_json TEXT NOT NULL,
            category TEXT NOT NULL,
            context_tags TEXT DEFAULT "",
            reference_image_path TEXT DEFAULT "",
            negative_tokens_json TEXT DEFAULT "[]",
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entity_canonical ON entity_registry(canonical_name);")
    conn.commit()
    conn.close()


init_entity_registry()


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", s)


def find_existing_reference_portrait(entity_name: str) -> Optional[Path]:
    """Checks reference directories and entity registry for an existing portrait."""
    if not entity_name:
        return None
    slug = slugify(entity_name)
    
    # 1. Direct file matches
    candidates = [
        CONTESTANT_REF_DIR / f"{slug}.jpg",
        CONTESTANT_REF_DIR / f"{slug}.png",
        ENTITIES_REF_DIR / slug / f"{slug}.jpg",
        ENTITIES_REF_DIR / slug / f"{slug}.png",
        ENTITIES_REF_DIR / f"{slug}.jpg",
    ]
    for c in candidates:
        if c.exists() and c.stat().st_size > 1024:
            return c

    # 2. Check through image_agent find_local_contestant_image
    try:
        from agents.image_agent import find_local_contestant_image
        match = find_local_contestant_image(entity_name)
        if match and match[1].exists():
            return match[1]
    except Exception:
        pass

    # 3. Check SQLite entity_registry
    try:
        conn = _get_entity_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT reference_image_path FROM entity_registry WHERE canonical_name = ? OR aliases_json LIKE ?",
                       (entity_name, f'%"{entity_name}"%'))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            p = Path(row[0])
            if p.exists() and p.stat().st_size > 1024:
                return p
    except Exception:
        pass

    return None


def fetch_and_audit_portrait(
    entity_name: str,
    context: str = "",
    category: str = "entertainment",
) -> Optional[Path]:
    """
    Downloads an HD portrait of entity_name, audited against NegativeMemoryLedger,
    and verified for PIL readability, dimensions, and aspect ratio.
    """
    if not entity_name or len(entity_name.strip()) < 3:
        return None

    existing = find_existing_reference_portrait(entity_name)
    if existing:
        return existing

    slug = slugify(entity_name)
    ledger = get_negative_ledger()

    queries = [
        f"{entity_name} {context} official portrait photo HD",
        f"{entity_name} actor face photo",
        f"{entity_name} {context} photo",
    ]

    target_path = CONTESTANT_REF_DIR / f"{slug}.jpg"
    temp_path = CONTESTANT_REF_DIR / f"temp_{slug}.jpg"
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
    }

    for q in queries:
        try:
            results = search_duckduckgo_images(q, max_results=8)
            for res in results:
                img_url = res.get("image_url") or res.get("image")
                source_url = res.get("url", "")
                title = res.get("title", "")

                if not img_url:
                    continue

                clean, reason = ledger.audit_candidate(url=img_url, ocr_text=f"{title} {source_url}")
                if not clean:
                    continue

                try:
                    resp = requests.get(img_url, headers=headers, timeout=6)
                    if resp.status_code != 200 or len(resp.content) < 5000:
                        continue

                    temp_path.write_bytes(resp.content)

                    with Image.open(temp_path) as im:
                        im.verify()

                    with Image.open(temp_path) as im:
                        w, h = im.size
                        if w < 250 or h < 250:
                            temp_path.unlink(missing_ok=True)
                            continue
                        ratio = w / h
                        if ratio > 2.2 or ratio < 0.4:
                            temp_path.unlink(missing_ok=True)
                            continue

                        rgb = im.convert("RGB")
                        rgb.save(str(target_path), "JPEG", quality=92)
                        temp_path.unlink(missing_ok=True)

                    try:
                        conn = _get_entity_db_conn()
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT OR REPLACE INTO entity_registry
                            (canonical_name, aliases_json, category, context_tags, reference_image_path)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            entity_name,
                            json.dumps([entity_name, slug, entity_name.lower()]),
                            category,
                            context,
                            str(target_path)
                        ))
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass

                    print(f"🌱 [Entity Harvester] Auto-harvested and registered reference portrait for '{entity_name}' -> {target_path.name}")
                    return target_path

                except Exception:
                    temp_path.unlink(missing_ok=True)
                    continue

        except Exception:
            continue

    temp_path.unlink(missing_ok=True)
    return None


def harvest_entities_from_plan(delivery_plan: List[Dict[str, Any]], topic: str = "") -> List[str]:
    """
    Scans all beats in delivery_plan and ensures verified portraits exist for every mentioned entity.
    Returns list of verified entities.
    """
    discovered_entities = set()
    is_bb = any(k in topic.lower() for k in ["bigg boss", "biggboss", "bb10", "బిగ్ బాస్"])
    context = "Bigg Boss Telugu 10" if is_bb else "Telugu Cinema"

    for b in delivery_plan:
        ent = b.get("main_entity") or b.get("primary_entity")
        if ent and len(ent.strip()) >= 3:
            if ent.lower() not in {"news headline", "housemates", "scene", "highlight", "drama"}:
                discovered_entities.add(ent.strip())

    harvested = []
    for entity in discovered_entities:
        ref = find_existing_reference_portrait(entity)
        if not ref:
            ref = fetch_and_audit_portrait(entity, context=context)
        if ref:
            harvested.append(entity)

    return harvested

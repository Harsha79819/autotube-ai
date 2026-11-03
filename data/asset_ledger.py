"""SQLite Asset Ledger for AutoTube AI.
Tracks source, tier, license, and attribution for every asset used in a video.
Enforces auditability, copyright safety, and generates YouTube description credits.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent / "autotube.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target_path = db_path or DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize the asset_ledger table if it does not exist."""
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS asset_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                beat_id INTEGER NOT NULL,
                asset_path TEXT NOT NULL,
                source_url TEXT DEFAULT "",
                tier TEXT NOT NULL CHECK(tier IN ("TIER_A", "TIER_B", "TIER_C")),
                license TEXT DEFAULT "",
                credit_text TEXT DEFAULT "",
                duration_sec REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_asset_ledger_video
            ON asset_ledger(video_id);
            """
        )
        conn.commit()


def clear_ledger_for_video(video_id: str = "current", db_path: Optional[Path] = None) -> None:
    """Clear all records for a given video_id before a fresh pipeline run."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM asset_ledger WHERE video_id = ?", (str(video_id),))
        conn.commit()


def record_asset(
    video_id: str,
    beat_id: int,
    asset_path: str,
    source_url: str = "",
    tier: str = "TIER_A",
    license_name: str = "",
    credit_text: str = "",
    duration_sec: float = 0.0,
    db_path: Optional[Path] = None,
) -> int:
    """Record an asset in the ledger."""
    init_db(db_path)
    tier_clean = tier.upper()
    if not tier_clean.startswith("TIER_"):
        tier_clean = f"TIER_{tier_clean}"

    with get_connection(db_path) as conn:
        conn.execute(
            "DELETE FROM asset_ledger WHERE video_id = ? AND beat_id = ?",
            (str(video_id), int(beat_id)),
        )
        cursor = conn.execute(
            """
            INSERT INTO asset_ledger (
                video_id, beat_id, asset_path, source_url, tier, license, credit_text, duration_sec
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(video_id),
                int(beat_id),
                str(asset_path),
                str(source_url or ""),
                tier_clean,
                str(license_name or ""),
                str(credit_text or ""),
                float(duration_sec or 0.0),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def get_assets_for_video(video_id: str, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieve all recorded assets for a given video_id."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, video_id, beat_id, asset_path, source_url, tier, license, credit_text, duration_sec, created_at
            FROM asset_ledger
            WHERE video_id = ?
            ORDER BY beat_id ASC, id ASC
            """,
            (str(video_id),),
        ).fetchall()
        return [dict(row) for row in rows]


def get_tier_breakdown(video_id: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Return asset counts and duration shares by tier for a video."""
    assets = get_assets_for_video(video_id, db_path)
    if not assets:
        return {
            "total_assets": 0,
            "total_duration": 0.0,
            "tier_a_count": 0,
            "tier_b_count": 0,
            "tier_c_count": 0,
            "tier_b_share": 0.0,
            "has_tier_c": False,
        }

    total_count = len(assets)
    total_dur = sum(a.get("duration_sec", 0.0) for a in assets)
    tier_a = [a for a in assets if a["tier"] == "TIER_A"]
    tier_b = [a for a in assets if a["tier"] == "TIER_B"]
    tier_c = [a for a in assets if a["tier"] == "TIER_C"]

    tier_b_dur = sum(a.get("duration_sec", 0.0) for a in tier_b)
    tier_b_share = (tier_b_dur / total_dur) if total_dur > 0 else (len(tier_b) / total_count)

    return {
        "total_assets": total_count,
        "total_duration": total_dur,
        "tier_a_count": len(tier_a),
        "tier_b_count": len(tier_b),
        "tier_c_count": len(tier_c),
        "tier_b_share": round(tier_b_share, 4),
        "has_tier_c": len(tier_c) > 0,
    }


def generate_description_credits(video_id: str, db_path: Optional[Path] = None) -> str:
    """Generate formatted YouTube description credits from recorded assets."""
    assets = get_assets_for_video(video_id, db_path)
    if not assets:
        return ""

    credits_set = set()
    for a in assets:
        credit = a.get("credit_text", "").strip()
        lic = a.get("license", "").strip()
        src = a.get("source_url", "").strip()
        if credit:
            credits_set.add(credit)
        elif lic:
            credits_set.add(f"Licensed under {lic}")
        elif "wikimedia.org" in src or "wikipedia.org" in src:
            credits_set.add("Wikimedia Commons / CC-BY-SA")
        elif "pexels.com" in src:
            credits_set.add("Pexels (Free to use)")
        elif "pixabay.com" in src:
            credits_set.add("Pixabay (Free to use)")

    if not credits_set:
        return ""

    lines = ["Media Credits & Attribution:"]
    for c in sorted(credits_set):
        lines.append(f"- {c}")
    return "\n".join(lines)


def get_recent_used_asset_paths(limit_videos: int = 15, db_path: Optional[Path] = None) -> List[str]:
    """Return asset paths and source URLs used across recent video runs."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT asset_path, source_url
            FROM asset_ledger
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit_videos * 25,),
        ).fetchall()
        results = []
        for r in rows:
            if r["asset_path"]:
                results.append(str(r["asset_path"]))
            if r["source_url"]:
                results.append(str(r["source_url"]))
        return results


if __name__ == "__main__":
    init_db()
    print("Asset ledger initialized at:", DB_PATH)

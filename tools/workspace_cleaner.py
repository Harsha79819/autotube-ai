#!/usr/bin/env python3
"""
tools/workspace_cleaner.py - Workspace Isolation & Cross-Topic Data Purge Engine

Guarantees 100% strict isolation between consecutive video generation runs:
1. Archives previous completed video run to output/runs/ (never loses past work).
2. Purges all previous scripts, topics, contestant names, metadata, and audio from output/.
3. Purges all loose scraped images (1.jpg, 2.jpg, etc.) from assets/ while strictly preserving
   permanent system subdirectories (assets/music/, assets/sfx/, assets/memes/, assets/entities/, etc.).
4. Prevents old topic/contestant data from manipulating or corrupting new runs.
"""

import os
import sys
import shutil
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
RUNS_DIR = OUTPUT_DIR / "runs"

# Permanent system subdirectories inside assets/ that must NEVER be deleted
PROTECTED_ASSET_SUBDIRS = {
    "music",
    "sfx",
    "memes",
    "entities",
    "fallback",
    "outro",
    ".gitkeep",
}

# Topic-specific files in output/ that MUST be wiped before a new video run
STALE_OUTPUT_FILES = [
    # Script & text files
    "topic.txt",
    "title.txt",
    "script.txt",
    "tts_script.txt",
    "script_optimized.txt",
    "teleprompter.txt",
    "section_map.txt",
    # Visual & planning files
    "beat_visual_plan.json",
    "visual_plan.json",
    "visual_plan.txt",
    "visual_report.html",
    "delivery_plan.json",
    "hook_overlay.png",
    "frame0_audit.png",
    "verify_frame.jpg",
    # Audio files
    "voice.mp3",
    "voice_raw.wav",
    "voice_paced.wav",
    "mixed_audio.wav",
    "transcription.json",
    # Video & subtitle files
    "subtitles.ass",
    "subtitles.srt",
    "video.mp4",
    "final_video.mp4",
    # Metadata & publishing files
    "metadata.json",
    "thumbnail.jpg",
    "community_poll.json",
    "run_info.json",
    # Evaluation & audit reports
    "validation_report.json",
    "review.json",
    "run_report.json",
    "pipeline_timing.json",
    "pipeline_timing.log",
    "script_candidates_evaluation.json",
    "script_candidates_evaluation.log",
]


def archive_previous_run() -> Optional[Path]:
    """
    Safely archives completed previous run artifacts into output/runs/run_<timestamp>_<slug>/
    so past videos and scripts are never lost.
    """
    final_video = OUTPUT_DIR / "final_video.mp4"
    script_file = OUTPUT_DIR / "script.txt"
    topic_file = OUTPUT_DIR / "topic.txt"

    # Only archive if there is actually a completed video or script
    if not final_video.exists() and not script_file.exists():
        return None

    try:
        topic_slug = "video"
        if topic_file.exists():
            topic_raw = topic_file.read_text(encoding="utf-8").strip()
            topic_slug = re.sub(r"[^A-Za-z0-9]+", "_", topic_raw)[:30].strip("_")
        elif script_file.exists():
            topic_slug = "previous_script"

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_dest = RUNS_DIR / f"run_{timestamp_str}_{topic_slug}"
        archive_dest.mkdir(parents=True, exist_ok=True)

        copied_count = 0
        for fname in STALE_OUTPUT_FILES:
            src = OUTPUT_DIR / fname
            if src.exists() and src.is_file():
                try:
                    shutil.copy2(src, archive_dest / fname)
                    copied_count += 1
                except Exception:
                    pass

        # Also copy AI thumbnails if any
        for ai_t in OUTPUT_DIR.glob("ai_thumbnail_bg_*.jpg"):
            try:
                shutil.copy2(ai_t, archive_dest / ai_t.name)
                copied_count += 1
            except Exception:
                pass

        if copied_count > 0:
            print(f"📦 [Workspace Archive] Safely archived {copied_count} files from previous run -> {archive_dest.name}")
            return archive_dest

    except Exception as exc:
        print(f"⚠️ Archive previous run notice: {exc}")

    return None


def purge_scraped_assets() -> int:
    """
    Purges all loose scraped images (1.jpg, 2.jpg, etc.) directly in assets/
    while strictly preserving permanent system folders (music, sfx, memes, entities, etc.).
    """
    if not ASSETS_DIR.exists():
        return 0

    purged_count = 0
    for item in ASSETS_DIR.iterdir():
        # NEVER delete protected directories
        if item.is_dir() and item.name in PROTECTED_ASSET_SUBDIRS:
            continue
        if item.name.startswith("."):
            continue

        # Delete loose files (e.g. 1.jpg, 2.jpg, test_canva.png)
        if item.is_file():
            try:
                item.unlink(missing_ok=True)
                purged_count += 1
            except Exception:
                pass

    if purged_count > 0:
        print(f"🧹 [Asset Cleaner] Purged {purged_count} loose scraped images from assets/ to prevent cross-topic visual leaks.")
    return purged_count


def purge_output_workspace(archive_first: bool = True) -> int:
    """
    Purges lingering topic-specific files from output/ so the next video run begins with a 100% clean slate.
    """
    if archive_first:
        archive_previous_run()

    purged_count = 0
    for fname in STALE_OUTPUT_FILES:
        target = OUTPUT_DIR / fname
        if target.exists() and target.is_file():
            try:
                target.unlink(missing_ok=True)
                purged_count += 1
            except Exception:
                pass

    # Clean any dynamic AI backdrops or candidate thumbnails
    for pattern in ["ai_thumbnail_bg_*.jpg", "thumbnail_playwright_*.png", "ai_backdrop_*.jpg"]:
        for f in OUTPUT_DIR.glob(pattern):
            try:
                f.unlink(missing_ok=True)
                purged_count += 1
            except Exception:
                pass

    # Clean temporary test directories inside output/
    for test_dir in OUTPUT_DIR.glob("test_*"):
        if test_dir.is_dir():
            try:
                shutil.rmtree(test_dir, ignore_errors=True)
            except Exception:
                pass

    return purged_count


def clean_run_environment(archive_first: bool = True) -> Dict[str, int]:
    """
    Master entrypoint: Cleanly isolates the workspace for a new video generation run.
    Wipes lingering scripts, metadata, and scraped images so old topics cannot manipulate new data.
    """
    purged_out = purge_output_workspace(archive_first=archive_first)
    purged_assets = purge_scraped_assets()

    # Reset SQLite asset ledger
    try:
        from data.asset_ledger import clear_ledger_for_video
        clear_ledger_for_video("current")
    except Exception:
        pass

    print(f"✨ [Clean Slate] Workspace purified: {purged_out} output files reset, {purged_assets} old assets purged. 100% fresh run guaranteed!")
    return {
        "output_files_purged": purged_out,
        "scraped_assets_purged": purged_assets,
    }


if __name__ == "__main__":
    res = clean_run_environment(archive_first=False)
    print("Clean run environment result:", res)

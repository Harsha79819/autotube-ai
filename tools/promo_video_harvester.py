#!/usr/bin/env python3
"""
tools/promo_video_harvester.py - Automated Star Maa YouTube Promo Harvester

Fetches official HD promo thumbnails and keyframes from official Star Maa,
Disney+ Hotstar Telugu, and Bigg Boss Telugu YouTube uploads.
"""

import os
import re
import json
import time
import subprocess
from pathlib import Path
from typing import List, Optional
from io import BytesIO

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache" / "promo_frames"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}


def search_youtube_promo_videos(query: str, max_results: int = 3) -> List[dict]:
    """
    Queries YouTube using yt-dlp flat playlist extraction for Star Maa Bigg Boss promos.
    """
    clean_q = re.sub(r"[^\w\s]", " ", query).strip()
    if not clean_q:
        clean_q = "Star Maa Bigg Boss Telugu 10 promo"
    elif "star maa" not in clean_q.lower() and "bigg boss" not in clean_q.lower():
        clean_q = f"Star Maa Bigg Boss Telugu 10 {clean_q} promo"

    yt_query = f"ytsearch{max_results}:{clean_q}"
    yt_dlp_bin = ROOT / ".venv" / "bin" / "yt-dlp"
    if not yt_dlp_bin.exists():
        yt_dlp_bin = Path("yt-dlp")

    cmd = [
        str(yt_dlp_bin),
        yt_query,
        "--dump-json",
        "--no-warnings",
        "--flat-playlist",
        "--default-search", "ytsearch",
    ]

    results = []
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                vid = data.get("id")
                title = data.get("title", "")
                if vid:
                    results.append({
                        "video_id": vid,
                        "title": title,
                        "channel": data.get("channel", "") or data.get("uploader", ""),
                    })
                    if len(results) >= max_results:
                        break
            except Exception:
                continue
    except Exception as e:
        print(f"Notice during yt-dlp promo search ({query[:30]}): {e}")

    return results


def download_promo_thumbnail(video_id: str, prefix: str = "promo") -> Optional[Path]:
    """
    Downloads the highest-resolution available thumbnail for a YouTube video.
    """
    resolutions = [
        "maxresdefault.jpg",
        "hq720.jpg",
        "sddefault.jpg",
        "hqdefault.jpg",
    ]

    out_path = CACHE_DIR / f"{prefix}_{video_id}.jpg"
    if out_path.exists() and out_path.stat().st_size > 10000:
        return out_path

    for res in resolutions:
        url = f"https://i.ytimg.com/vi/{video_id}/{res}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=6)
            if r.status_code == 200 and len(r.content) > 10000:
                with Image.open(BytesIO(r.content)) as im:
                    w, h = im.size
                    if w >= 480 and h >= 360:
                        im.convert("RGB").save(out_path, "JPEG", quality=92)
                        return out_path
        except Exception:
            continue

    return None


def harvest_promo_visuals(query: str, max_results: int = 3) -> List[Path]:
    """
    Searches YouTube for Star Maa / Bigg Boss promos matching query and downloads HD thumbnails.
    Returns list of local Path objects.
    """
    videos = search_youtube_promo_videos(query, max_results=max_results)
    harvested = []
    for v in videos:
        vid = v["video_id"]
        p = download_promo_thumbnail(vid, prefix="starmaa")
        if p and p.exists() and p.stat().st_size > 5000:
            harvested.append(p)
            if len(harvested) >= max_results:
                break

    return harvested


if __name__ == "__main__":
    import sys
    test_q = sys.argv[1] if len(sys.argv) > 1 else "Bigg Boss Telugu 10 Day 48 promo"
    print(f"Testing Promo Video Harvester with: '{test_q}'...")
    res = harvest_promo_visuals(test_q, max_results=3)
    print(f"Harvested {len(res)} promo visuals:")
    for p in res:
        print(f"  • {p} ({p.stat().st_size // 1024} KB)")

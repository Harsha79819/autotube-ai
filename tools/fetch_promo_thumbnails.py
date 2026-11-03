#!/usr/bin/env python3
"""
tools/fetch_promo_thumbnails.py - Downloads official HD thumbnails directly from YouTube URLs into data/inbox/

Usage:
    python tools/fetch_promo_thumbnails.py <youtube_url_or_video_id> [optional_filename_prefix]
"""

import sys
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = ROOT / "data" / "inbox"
INBOX_DIR.mkdir(parents=True, exist_ok=True)

def extract_video_id(url_or_id: str) -> str:
    m = re.search(r'(?:v=|youtu\.be/|shorts/|embed/)([a-zA-Z0-9_-]{11})', url_or_id)
    if m:
        return m.group(1)
    if len(url_or_id) == 11:
        return url_or_id
    raise ValueError(f"Could not extract YouTube video ID from: {url_or_id}")

def fetch_thumbnail(url_or_id: str, prefix: str = "promo"):
    vid = extract_video_id(url_or_id)
    resolutions = ["maxresdefault.jpg", "sddefault.jpg", "hqdefault.jpg"]
    
    out_path = INBOX_DIR / f"{prefix}_{vid}.jpg"
    
    headers = {"User-Agent": "Mozilla/5.0"}
    downloaded = False
    for res in resolutions:
        thumb_url = f"https://img.youtube.com/vi/{vid}/{res}"
        try:
            req = urllib.request.Request(thumb_url, headers=headers)
            with urllib.request.urlopen(req) as resp, open(out_path, "wb") as out:
                out.write(resp.read())
            if out_path.stat().st_size > 5000:
                print(f"✓ Downloaded 1080p official promo thumbnail -> {out_path.relative_to(ROOT)}")
                downloaded = True
                break
        except Exception:
            continue
            
    if not downloaded:
        print(f"❌ Failed to fetch thumbnail for {vid}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/fetch_promo_thumbnails.py <youtube_url_or_id> [prefix]")
    else:
        url = sys.argv[1]
        pfx = sys.argv[2] if len(sys.argv) > 2 else "promo"
        fetch_thumbnail(url, pfx)

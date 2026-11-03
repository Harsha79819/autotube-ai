#!/usr/bin/env python3
"""
tools/auto_sort.py - Processes raw photos in data/inbox/ into clean transparent cutouts for data/entities/

Usage:
    python tools/auto_sort.py
"""

import sys
import os
import re
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.entity_bank import get_bank, EMOTIONS

INBOX_DIR = ROOT / "data" / "inbox"
ENTITIES_DIR = ROOT / "data" / "entities"

def detect_contestant_and_emotion(filename: str, bank) -> tuple:
    clean = filename.lower().replace("-", " ").replace("_", " ")
    detected_emo = "neutral"
    for emo in EMOTIONS:
        if emo in clean:
            detected_emo = emo
            break
            
    matched_ent = None
    for slug, ent in bank._by_slug.items():
        if slug in clean:
            matched_ent = ent
            break
        for alias in ent.aliases:
            if alias.lower() in clean:
                matched_ent = ent
                break
                
    return matched_ent, detected_emo

def remove_background_and_crop(input_path: Path, output_path: Path):
    try:
        from rembg import remove
        print(f"✂️  [rembg AI] Stripping background for {input_path.name}...")
        with Image.open(input_path) as im:
            im_rgba = im.convert("RGBA")
            result = remove(im_rgba)
    except Exception as e:
        print(f"⚠️ rembg fallback notice ({e}). Converting directly...")
        im = Image.open(input_path).convert("RGBA")
        result = im

    bbox = result.getchannel("A").getbbox()
    if bbox:
        result = result.crop(bbox)
        
    w, h = result.size
    if h < 800 and max(w, h) > 0:
        scale = 1000 / max(1, h)
        result = result.resize((round(w * scale), 1000), Image.LANCZOS)
        
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path, "PNG")
    print(f"  ✓ Saved clean transparent cutout: {output_path.relative_to(ROOT)}")
    return True

def process_inbox():
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    files = [f for f in INBOX_DIR.iterdir() if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    
    if not files:
        print(f"📂 [Inbox Empty] No photos found in {INBOX_DIR.relative_to(ROOT)}")
        print("💡 Drop contestant photos into data/inbox/ (e.g., 'varshini_1.jpg', 'thrigun_angry.png') and rerun!")
        return

    bank = get_bank(ENTITIES_DIR)
    processed = 0

    for f in files:
        ent, emo = detect_contestant_and_emotion(f.name, bank)
        if not ent:
            print(f"⚠️ Could not detect contestant for '{f.name}'. Name it like '<contestant_name>_<emotion>.jpg'. Skipping.")
            continue

        target_file = ENTITIES_DIR / ent.slug / f"{emo}.png"
        success = remove_background_and_crop(f, target_file)
        if success:
            processed += 1
            done_dir = INBOX_DIR / "archive"
            done_dir.mkdir(parents=True, exist_ok=True)
            f.rename(done_dir / f.name)

    print(f"\n🎉 Successfully sorted and generated {processed} cutouts into data/entities/!")

if __name__ == "__main__":
    process_inbox()

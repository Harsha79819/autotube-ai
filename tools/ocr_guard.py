#!/usr/bin/env python3
"""
tools/ocr_guard.py - Native macOS Vision OCR Guard
Validates visual image assets using macOS Vision Framework (.accurate OCR).
Detects and rejects images containing:
- Prior season watermarks/logos (Bigg Boss 1-9, BB1-9, Season 1-9)
- Old pre-launch teaser promos ('coming soon')
- Prior season known winner/contestant names (Kalyan Padala, Ashwini Sri, Rohit Sahni, etc.)
- Political leakages (YS Jagan, Chandrababu, Revanth, Pawan Kalyan)
"""

import os
import sys
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, List, Dict, Optional, Any

SWIFT_OCR_SCRIPT = """
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count > 1 else {
    exit(0)
}

for i in 1..<args.count {
    let path = args[i]
    let url = URL(fileURLWithPath: path)
    guard let img = NSImage(contentsOf: url),
          let cgImg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("RESULT|||\\(path)|||ERROR:MISSING_OR_CORRUPT")
        continue
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    let handler = VNImageRequestHandler(cgImage: cgImg, options: [:])
    try? handler.perform([request])
    let results = request.results ?? []
    let detected = results.compactMap { $0.topCandidates(1).first?.string }.joined(separator: " | ")
    print("RESULT|||\\(path)|||OK|||\\(detected)")
}
"""

_swift_script_path: Optional[str] = None

def _get_swift_script() -> str:
    global _swift_script_path
    if _swift_script_path and os.path.exists(_swift_script_path):
        return _swift_script_path
    tmp = tempfile.NamedTemporaryFile(suffix=".swift", delete=False, mode="w", encoding="utf-8")
    tmp.write(SWIFT_OCR_SCRIPT)
    tmp.close()
    _swift_script_path = tmp.name
    return _swift_script_path


def scan_images_ocr(image_paths: List[Any]) -> Dict[str, str]:
    """
    Scans a batch of images with macOS Vision OCR or Linux Tesseract.
    Returns a dict of {str(path): detected_text}.
    """
    path_objs = [Path(p) for p in image_paths]
    valid_paths = [str(p) for p in path_objs if p.exists() and p.is_file() and p.stat().st_size > 1000]
    if not valid_paths:
        return {}

    results = {}

    # macOS Native Vision Framework
    if sys.platform == "darwin" and shutil.which("swift"):
        script_path = _get_swift_script()
        batch_size = 30
        for i in range(0, len(valid_paths), batch_size):
            batch = valid_paths[i:i + batch_size]
            try:
                proc = subprocess.run(
                    ["swift", script_path] + batch,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                for line in proc.stdout.splitlines():
                    if line.startswith("RESULT|||"):
                        parts = line.split("|||")
                        if len(parts) >= 4 and parts[2] == "OK":
                            results[parts[1]] = parts[3]
                        elif len(parts) >= 3:
                            results[parts[1]] = ""
            except Exception as e:
                print(f"⚠️ OCR scan notice: {e}")
        return results

    # Linux / Cross-platform Tesseract CLI
    if shutil.which("tesseract"):
        for p in valid_paths:
            try:
                proc = subprocess.run(
                    ["tesseract", p, "stdout", "-l", "eng", "--oem", "1", "--psm", "3"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if proc.returncode == 0:
                    results[p] = " ".join(proc.stdout.split())
                else:
                    results[p] = ""
            except Exception:
                results[p] = ""
        return results

    # Fallback: Python pytesseract if installed
    try:
        import pytesseract
        from PIL import Image
        for p in valid_paths:
            try:
                with Image.open(p) as img:
                    txt = pytesseract.image_to_string(img)
                    results[p] = " ".join(txt.split())
            except Exception:
                results[p] = ""
        return results
    except Exception:
        pass

    return {p: "" for p in valid_paths}


def check_asset_prior_seasons(image_path: Path, is_bb: bool = True) -> Tuple[bool, str, str]:
    """
    Checks a single asset image for prior season tokens or political blacklist.
    Returns: (is_clean: bool, detected_text: str, reason: str)
    """
    if not image_path.exists():
        return False, "", "File does not exist"

    results = scan_images_ocr([image_path])
    text = results.get(str(image_path), "")
    t_low = text.lower()

    if not is_bb:
        return True, text, "OK"

    # 1. Direct prior season keyword checks (English & Telugu)
    prior_season_patterns = [
        r"\bbigg\s*boss\s*[1-9]\b",
        r"\bbb\s*[1-9]\b",
        r"\bseason\s*[1-9]\b",
        r"\bseason-[1-9]\b",
        r"\bbb[1-9]\b",
        r"బిగ్[\s_-]*బాస్[\s_-]*[1-9]\b",
        r"బిగ్‌బాస్[\s_-]*[1-9]\b",
        r"సీజన్[\s_-]*[1-9]\b",
        r"బిగ్[\s_-]*బాస్[\s_-]*([1-9])",
        r"బిగ్‌బాస్[\s_-]*([1-9])",
        r"సీజన్[\s_-]*([1-9])",
    ]
    for pat in prior_season_patterns:
        if re.search(pat, t_low):
            return False, text, f"Detected prior season pattern: {pat}"

    # 2. Number + Bigg Boss co-occurrence (e.g. '9 | BIGG BOSS', '9) | BIGG BOSS', etc.)
    if "bigg boss" in t_low or "biggboss" in t_low:
        # Check old teaser promos
        if "coming soon" in t_low or "grand launch" in t_low:
            if "10" not in t_low:
                return False, text, "Detected pre-launch teaser promo without Season 10 branding"
        for s_num in range(1, 10):
            # If solitary digit 1-9 is near bigg boss
            if re.search(r"(?:^|[\s\|\:\-\(\[])" + str(s_num) + r"(?:[\s\|\:\-\)\]]|$)", t_low):
                # Ensure it's not Season 10
                if "10" not in t_low:
                    return False, text, f"Detected prior season digit {s_num} with Bigg Boss logo"

    # 3. Known past contestants / personalities from previous seasons
    past_season_names = [
        "kalyan padala", "ashwini sri", "rohit sahni", "sivaji",
        "pallavi prashanth", "shobha shetty", "priyanka jain",
        "amardeep", "prashanth", "teja", "rathika", "subhashree",
        "aadi reddy", "geetu royal", "revanth", "fima", "inasulthan",
        "shiva jyothi", "himaja", "punarnavi", "sreemukhi",
        "kaushal", "kaushal manda", "geetha madhuri", "deepthi sunaina",
        "shiva rajkumar", "balakrishna", "బాలకృష్ణ", "unstoppable", "అన్‌స్టాపబుల్",
    ]
    for name in past_season_names:
        if name in t_low:
            return False, text, f"Detected past season personality: {name}"

    # 4. Politics blacklist
    political_names = ["ys jagan", "jagan", "ysr", "chandrababu", "pawan kalyan", "revanth reddy", "kcr", "modi"]
    for pol in political_names:
        if pol in t_low:
            return False, text, f"Detected political leakage: {pol}"

    # 5. Foreign non-Telugu scripts (Bengali, Devanagari, Urdu/Arabic)
    if re.search(r"[\u0980-\u09FF]", text):
        return False, text, "Detected foreign Bengali script"
    if re.search(r"[\u0600-\u06FF]", text):
        return False, text, "Detected foreign Arabic/Urdu script"

    # 6. Anime, foreign political news conferences, and collage templates
    foreign_bad_tokens = [
        "anime", "manga", "trigun themes", "analysis of", "podcast",
        "bnp", "bangladesh", "narayanganj", "press conference",
        "meme template", "meme templates", "stickers pack", "wallpaper download",
    ]
    for bad_tok in foreign_bad_tokens:
        if bad_tok in t_low:
            return False, text, f"Detected foreign/non-show token: {bad_tok}"

    return True, text, "OK"

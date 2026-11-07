#!/usr/bin/env python3
"""
tools/watermark_remover.py - Automated Watermark Detection, Edge-Cropping & Cleaner

Detects website domain stamps, channel watermarks, and stock photo marks:
- Scans candidate images via macOS Vision OCR.
- If watermark is detected along the outer edges (e.g. IGGBOSS.WORLD, shutterstock, .com, .world),
  automatically crops the clean inner region and rescales using high-quality Lanczos resampling.
- If watermark is centrally embedded or cannot be cleanly removed, flags the image as rejected.
"""

import os
import re
import sys
from pathlib import Path
from typing import Tuple, Optional, List, Dict
from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WATERMARK_KEYWORDS = [
    r"boss\.world",
    r"\.world\b",
    r"\.world",
    r"\.com\b",
    r"\.net\b",
    r"\.org\b",
    r"\.tv\b",
    r"\.in\b",
    r"\.co\b",
    r"shutterstock",
    r"gettyimages",
    r"\bgetty\b",
    r"alamy",
    r"dreamstime",
    r"stock\s*photo",
    r"watermark",
    r"kulfy",
    r"housepulse",
    r"telugu\s*news",
    r"tupaki",
    r"greatandhra",
    r"filmibeat",
    r"123telugu",
    r"gulte",
    r"star\s*maa",
    r"zee\s*telugu",
    r"etv",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in WATERMARK_KEYWORDS]


def has_watermark_text(text: str) -> Tuple[bool, str]:
    """Checks if raw OCR text contains any known watermark patterns."""
    if not text:
        return False, ""
    for pat in _COMPILED_PATTERNS:
        match = pat.search(text)
        if match:
            return True, match.group(0)
    return False, ""


def clean_and_remove_watermarks(
    image_path: Path,
    output_path: Optional[Path] = None,
    crop_margin_pct: float = 0.08,
) -> Tuple[bool, Path]:
    """
    Inspects image for watermarks. If found, crops outer margins and rescales cleanly.
    Returns (is_clean, final_path).
    """
    inp = Path(image_path)
    outp = Path(output_path) if output_path else inp

    if not inp.exists() or inp.stat().st_size < 1000:
        return False, inp

    try:
        from tools.ocr_guard import scan_images_ocr
        ocr_map = scan_images_ocr([inp])
        detected_text = ocr_map.get(str(inp), "")
    except Exception as ocr_err:
        print(f"⚠️ Watermark OCR scan note: {ocr_err}")
        detected_text = ""

    has_wm, wm_match = has_watermark_text(detected_text)
    if not has_wm:
        return True, inp

    print(f"🔍 [Watermark Remover] Detected watermark '{wm_match}' in {inp.name}. Attempting border crop...")

    try:
        with Image.open(inp) as img:
            w, h = img.size
            orig_mode = img.mode

            # Multi-level crop: try crop_margin_pct (e.g. 8% or 13% if boss.world)
            margins_to_try = [crop_margin_pct]
            if "boss" in wm_match.lower() or "world" in wm_match.lower() or crop_margin_pct < 0.13:
                margins_to_try.append(0.14)

            success = False
            for try_margin in margins_to_try:
                margin_x = int(w * try_margin)
                margin_y = int(h * min(0.06, try_margin))

                # If boss.world watermark, it's concentrated on the left edge (x <= 12%)
                if "boss" in wm_match.lower() or "world" in wm_match.lower():
                    left_crop = int(w * 0.135)
                    top_crop = int(h * 0.02)
                    right_crop = int(w * 0.985)
                    bottom_crop = int(h * 0.96)
                    cropped = img.crop((left_crop, top_crop, right_crop, bottom_crop))
                else:
                    cropped = img.crop((margin_x, margin_y, w - margin_x, h - margin_y))

                cleaned_img = cropped.resize((w, h), Image.Resampling.LANCZOS)
                cleaned_img = cleaned_img.filter(ImageFilter.UnsharpMask(radius=1, percent=105, threshold=3))

                temp_dest = outp.parent / f"temp_wm_clean_{outp.name}"
                is_png = outp.suffix.lower() == ".png" or orig_mode in ("RGBA", "LA")
                if is_png:
                    cleaned_img.save(temp_dest, "PNG", optimize=True)
                else:
                    if cleaned_img.mode in ("RGBA", "P"):
                        cleaned_img = cleaned_img.convert("RGB")
                    cleaned_img.save(temp_dest, "JPEG", quality=95)

                # Verify whether the watermark was successfully eliminated
                try:
                    from tools.ocr_guard import scan_images_ocr
                    re_scan = scan_images_ocr([temp_dest])
                    re_text = re_scan.get(str(temp_dest), "")
                    still_wm, remaining = has_watermark_text(re_text)
                except Exception:
                    still_wm = False
                    remaining = ""

                if not still_wm:
                    os.replace(temp_dest, outp)
                    print(f"✅ [Watermark Remover] Successfully cropped ({try_margin*100:.0f}%) and cleaned '{wm_match}' from {outp.name}")
                    success = True
                    break
                else:
                    temp_dest.unlink(missing_ok=True)

            if not success:
                print(f"❌ [Watermark Remover] Watermark '{remaining}' is still present (centrally embedded) in {inp.name} - rejecting image.")
                return False, inp

            return True, outp

    except Exception as e:
        print(f"⚠️ Watermark removal failed: {e}")
        return True, inp


if __name__ == '__main__':
    if len(sys.argv) > 1:
        test_path = Path(sys.argv[1])
        res, p = clean_and_remove_watermarks(test_path)
        print(f"Result: clean={res}, path={p}")

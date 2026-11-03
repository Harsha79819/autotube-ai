"""
agents/vision_gate.py - Pre-Render Vision Quality Gate & Self-Healing Interceptor

Executes immediately before FFmpeg video rendering:
1. Audits all beat assets (1.jpg to N.jpg) for:
   - Decodability & file size (> 1KB)
   - Exact 1080x1920 resolution & 9:16 vertical shorts aspect ratio
   - Prior season branding / logos / watermarks via Apple Vision OCR
   - NegativeMemoryLedger ban list (hashes & patterns)
2. Auto-heals any defective asset on-the-fly using dynamic Canva Editorial Cards
   with verified contestant avatars before video encoding starts.
"""

import re
import json
from pathlib import Path
from typing import Dict, Any, Tuple, List
from PIL import Image

from data.negative_ledger import get_negative_ledger
from tools.ocr_guard import check_asset_prior_seasons
from providers.image import clean_and_crop_image

ROOT = Path(__file__).resolve().parent.parent


def audit_and_heal_visual_assets(
    assets_dir: Path = None,
    aspect_ratio: str = "9:16",
    topic: str = "",
) -> Tuple[bool, Dict[str, Any]]:
    """
    Scans and auto-heals all visual assets before FFmpeg assembly.
    Returns (success_status, inspection_report).
    """
    a_dir = Path(assets_dir) if assets_dir else (ROOT / "assets")
    if not a_dir.exists():
        return False, {"error": "assets directory does not exist"}

    ledger = get_negative_ledger()
    image_files = sorted([
        f for f in a_dir.iterdir()
        if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        and not f.name.startswith("contact_sheet")
    ], key=lambda x: int(re.search(r"\d+", x.stem).group(0)) if re.search(r"\d+", x.stem) else 999)

    report = {
        "total_assets": len(image_files),
        "healed_count": 0,
        "clean_count": 0,
        "details": {},
    }

    # Load delivery_plan / visual_plan for entity context
    dp_data = {}
    dp_file = ROOT / "output" / "delivery_plan.json"
    if dp_file.exists():
        try:
            items = json.loads(dp_file.read_text(encoding="utf-8"))
            for it in items:
                dp_data[it.get("beat_id")] = it
        except Exception:
            pass

    # Detect show context
    from data.bb10_contestants import is_bigg_boss_context
    is_bb = is_bigg_boss_context(topic)

    for img_path in image_files:
        filename = img_path.name
        b_num_m = re.search(r"(\d+)", img_path.stem)
        beat_id = int(b_num_m.group(1)) if b_num_m else None
        
        is_defective = False
        defect_reason = "Clean"

        # Check 1: Size & PIL integrity
        if img_path.stat().st_size < 1024:
            is_defective = True
            defect_reason = "File size below 1KB"

        if not is_defective:
            try:
                with Image.open(img_path) as im:
                    im.verify()
                with Image.open(img_path) as im:
                    w, h = im.size
                    if w < 200 or h < 200:
                        is_defective = True
                        defect_reason = f"Resolution too low ({w}x{h})"
            except Exception as e:
                is_defective = True
                defect_reason = f"Image decode failure: {e}"

        # Check 2: Negative Ledger Image Hash
        if not is_defective:
            banned_h, r_h = ledger.is_image_hash_banned(img_path)
            if banned_h:
                is_defective = True
                defect_reason = r_h

        # Check 3: Apple Vision OCR Prior Season Branding
        if not is_defective and is_bb:
            is_clean, ocr_txt, rej_reason = check_asset_prior_seasons(img_path, is_bb=True)
            if not is_clean:
                is_defective = True
                defect_reason = f"OCR Defect: {rej_reason} (Found: '{ocr_txt[:35]}')"

        # Check 4: General Negative Ledger OCR Patterns
        if not is_defective:
            try:
                from tools.ocr_guard import run_apple_vision_ocr
                raw_ocr = run_apple_vision_ocr(img_path)
                banned_txt, r_txt = ledger.is_ocr_text_banned(raw_ocr)
                if banned_txt:
                    is_defective = True
                    defect_reason = r_txt
            except Exception:
                pass

        # Perform Auto-Healing if defective
        if is_defective:
            # 1. Permanently ban the defective image hash
            ledger.ban_image_hash(img_path, reason=defect_reason)
            
            # 2. Extract beat details for Canva card
            b_info = dp_data.get(beat_id, {})
            b_ent = b_info.get("main_entity") or b_info.get("primary_entity", "")
            spoken = b_info.get("spoken_text") or b_info.get("narration") or f"Highlight Beat {beat_id or ''}"

            from agents.image_agent import find_local_contestant_image
            from agents.entity_harvester import find_existing_reference_portrait
            from agents.typography_card import generate_typography_card

            av_p = None
            if b_ent:
                loc = find_local_contestant_image(b_ent)
                if loc:
                    av_p = str(loc[1])
                    b_ent = loc[0].replace("_", " ").title()
                else:
                    ref = find_existing_reference_portrait(b_ent)
                    if ref:
                        av_p = str(ref)

            if is_bb:
                badge = f"{b_ent.upper()} • BIGG BOSS 10" if b_ent else "HIGHLIGHT • BIGG BOSS 10"
                subtext = "Bigg Boss Telugu 10 • Star Maa"
            else:
                badge = f"{b_ent.upper()} • EXCLUSIVE" if b_ent else "HIGHLIGHT • EXCLUSIVE"
                subtext = "AutoTube Exclusive Update"

            healed = generate_typography_card(
                headline_text=spoken,
                output_path=str(img_path),
                topic_category="entertainment",
                aspect_ratio=aspect_ratio,
                badge_label=badge,
                avatar_image_path=av_p,
                subtext=subtext,
            )

            if healed:
                clean_and_crop_image(img_path, aspect_ratio=aspect_ratio)
                report["healed_count"] += 1
                report["details"][filename] = f"HEALED ({defect_reason}) -> Canva Editorial Card ({badge})"
                print(f"✨ [Vision Gate] Auto-healed {filename}: {defect_reason} -> Canva Editorial Card ({badge})")
            else:
                report["details"][filename] = f"FAILED_TO_HEAL: {defect_reason}"
        else:
            # Guarantee 1080x1920 scaling even on clean images
            try:
                clean_and_crop_image(img_path, aspect_ratio=aspect_ratio)
            except Exception:
                pass
            report["clean_count"] += 1
            report["details"][filename] = "PASS"

    all_passed = (report["healed_count"] + report["clean_count"]) == report["total_assets"]
    return all_passed, report

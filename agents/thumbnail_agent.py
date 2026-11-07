from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import re
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
OUTPUT_DIR = ROOT / "output"


def _find_best_background(aspect_ratio="16:9", assets_dir=None):
    """
    Select the best image from assets matching the desired aspect ratio.

    Avoids:
    - contact sheets
    - very small images

    Prefers:
    - aspect ratio closest to target
    - larger resolution
    """

    candidates = []
    scan_dir = Path(assets_dir) if assets_dir else ASSETS_DIR
    if not scan_dir.exists():
        scan_dir = ASSETS_DIR
    if not scan_dir.exists():
        return None

    target_ratio = (
        9 / 16 if aspect_ratio == "9:16"
        else (1.0 if aspect_ratio == "1:1" else 16 / 9)
    )

    # Pass 1: Pre-fetch ledger URLs in 1 query instead of looping on DB per image
    ledger_urls = {}
    if not assets_dir or Path(assets_dir).resolve() == ASSETS_DIR.resolve():
        db_p = ROOT / "data" / "autotube.db"
        if db_p.exists():
            try:
                import sqlite3
                with sqlite3.connect(str(db_p), timeout=5.0) as conn:
                    rows = conn.execute("SELECT asset_path, source_url FROM asset_ledger ORDER BY id DESC").fetchall()
                    for ap, su in rows:
                        if ap and su:
                            ledger_urls[Path(ap).name] = su
            except Exception:
                pass

    try:
        from utils.season_guard import is_conflicting_season_candidate, is_bigg_boss_topic
        title_file = OUTPUT_DIR / "title.txt"
        title_txt = title_file.read_text(encoding="utf-8").strip() if title_file.exists() else ""
        is_bb = is_bigg_boss_topic(title_txt)
    except Exception:
        is_bb = False

    raw_candidates = []

    for path in scan_dir.iterdir():
        if path.name.lower().startswith("contact_sheet"):
            continue

        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue

        # Fast meme name filter
        if any(m in path.name.lower() for m in ("meme", "brahmi", "sunil", "ali", "posani", "kota", "babu_mohan", "dharmavarapu", "venky", "venu_madhav", "jayaprakash")):
            continue

        try:
            with Image.open(path) as img:
                width, height = img.size

                if width < 300 or height < 300:
                    continue

                aspect = width / height
                ratio_difference = abs(aspect - target_ratio)
                ratio_score = max(0, 60 - (ratio_difference * 35))
                resolution_score = min((width * height) / 1_000_000, 20)

                source_url = ledger_urls.get(path.name, "")

                if source_url and is_conflicting_season_candidate(source_url, is_bb_context=is_bb):
                    continue

                if source_url and ("meme" in source_url.lower() or "reaction" in source_url.lower()):
                    continue

                # Primary subject bonus
                subject_bonus = 0
                if source_url and "contestant_gallery" in source_url:
                    subject_bonus += 20
                if path.name in ("1.jpg", "1.jpeg", "1.png"):
                    subject_bonus += 5
                elif path.name in ("2.jpg", "2.jpeg", "2.png"):
                    subject_bonus += 5

                score = ratio_score + resolution_score + subject_bonus
                raw_candidates.append((score, path, source_url))

        except Exception as exc:
            print(f"⚠️ Could not inspect {path.name}: {exc}")

    if not raw_candidates:
        candidates = []
    else:
        # Sort raw candidates by score descending
        raw_candidates.sort(key=lambda item: item[0], reverse=True)

        # Pass 2: Deep validation (meme hash & OCR) on top candidates ONLY (max 4)
        top_candidates = raw_candidates[:4]
        meme_hashes = []
        meme_dir = ROOT / "reference_assets" / "memes"
        if meme_dir.exists():
            try:
                from agents.image_agent import image_dhash
                for mf in meme_dir.glob("*.jpg"):
                    mdh = image_dhash(mf)
                    if mdh:
                        meme_hashes.append((mf.name, mdh))
            except Exception:
                pass

        # Filter out perceptual meme matches among top candidates
        filtered_top = []
        try:
            from agents.image_agent import image_dhash, is_perceptual_duplicate
            for score, p, s_url in top_candidates:
                p_dh = image_dhash(p)
                is_known_meme = False
                if p_dh and meme_hashes:
                    for m_name, mf_dh in meme_hashes:
                        if is_perceptual_duplicate(p_dh, [mf_dh], max_dist=5):
                            print(f"⚠️ [Thumbnail] Skipping {p.name}: perceptual match with known meme in library ({m_name})")
                            is_known_meme = True
                            break
                if not is_known_meme:
                    filtered_top.append((score, p, s_url))
        except Exception:
            filtered_top = top_candidates

        # Batch OCR scanning on remaining top candidates (at most 3)
        to_ocr_paths = [p for _, p, _ in filtered_top[:3]]
        ocr_results = {}
        if to_ocr_paths:
            try:
                from tools.ocr_guard import scan_images_ocr
                ocr_results = scan_images_ocr(to_ocr_paths)
            except Exception:
                pass

        candidates = []
        for score, p, s_url in filtered_top:
            ocr_txt = ocr_results.get(str(p), "").lower()
            try:
                from tools.watermark_remover import clean_and_remove_watermarks, has_watermark_text
                has_wm, _ = has_watermark_text(ocr_txt)
                if has_wm:
                    ok, cleaned_p = clean_and_remove_watermarks(p)
                    if not ok:
                        print(f"⚠️ [Thumbnail] Skipping {p.name}: embedded watermark could not be cropped ({ocr_txt[:30]})")
                        continue
                    p = cleaned_p
            except Exception:
                if any(b in ocr_txt for b in ("kulfy", "housepulse", "biggboss.world", "boss.world", "shutterstock", "getty")):
                    print(f"⚠️ [Thumbnail] Skipping {p.name}: contains watermark/disqualified text ({ocr_txt[:30]})")
                    continue
            candidates.append((score, p))
            if len(candidates) >= 2:
                break

    if not candidates:
        fallback_pool = list((ROOT / "assets" / "fallback").glob("*.jpg")) + list((ROOT / "assets" / "entities").glob("**/*.jpg"))
        for fb_path in fallback_pool:
            try:
                with Image.open(fb_path) as img:
                    w, h = img.size
                    if w >= 300 and h >= 300:
                        candidates.append((10, fb_path))
            except Exception:
                pass

    if not candidates:
        # Guarantee background is NEVER None: Generate branded high-contrast slate image
        slate_path = (ASSETS_DIR / "thumbnail_slate.jpg")
        try:
            ASSETS_DIR.mkdir(parents=True, exist_ok=True)
            slate_w, slate_h = (1080, 1920) if aspect_ratio == "9:16" else (1280, 720)
            slate_img = Image.new("RGB", (slate_w, slate_h), color=(15, 23, 42))
            draw = ImageDraw.Draw(slate_img)
            draw.rectangle((0, int(slate_h * 0.35), slate_w, int(slate_h * 0.65)), fill=(30, 41, 59))
            slate_img.save(slate_path, "JPEG", quality=90)
            print(f"🖼️ Thumbnail background: Generated branded high-contrast slate ({aspect_ratio})")
            return slate_path
        except Exception:
            return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    selected = candidates[0][1]
    try:
        from tools.watermark_remover import clean_and_remove_watermarks
        is_clean, cleaned_selected = clean_and_remove_watermarks(selected)
        if is_clean:
            selected = cleaned_selected
    except Exception as wm_clean_err:
        print(f"⚠️ Thumbnail watermark cleaner notice: {wm_clean_err}")

    print(
        f"🖼️ Thumbnail background selected ({aspect_ratio}): "
        f"{selected.name}"
    )

    return selected


def _load_font(size, is_telugu=False):
    """
    Find a usable bold font on macOS/Linux/Windows, with full Telugu Unicode support.
    """
    project_fonts = [
        str(ROOT / "fonts" / "NotoSansTelugu-Bold.ttf"),
        str(ROOT / "fonts" / "KohinoorTelugu.ttc"),
        str(ROOT / "fonts" / "Telugu MN.ttc"),
    ]
    if is_telugu:
        font_paths = project_fonts + [
            "/System/Library/Fonts/Supplemental/KohinoorTelugu.ttc",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ]
    else:
        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf",
        ] + project_fonts + [
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass

    return ImageFont.load_default()


def _clean_title(title, is_telugu=False):
    """
    Converts a video title into a high-CTR, 2-4 word curiosity-gap phrase.
    For Telugu / Bigg Boss topics, prioritizes high-voltage, bold Telugu curiosity badges.
    """
    if not title:
        return "బిగ్ బాస్ బిగ్ ట్విస్ట్?!" if is_telugu else "SHOCKING TWIST?!"

    t = str(title).strip()

    # Strip common channel prefixes or suffixes
    t = re.sub(r"^(roasting the drama|roasting|breaking|honest review|review):\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*-\s*(reuters|youtube|shorts|viral).*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[#@][\w]+", "", t).strip()

    t_low = t.lower()

    # If Telugu context or Bigg Boss topic: Generate bold, curiosity-triggering Telugu badges
    if is_telugu or any(k in t_low for k in ("bigg boss", "biggboss", "బిగ్ బాస్", "aman", "అమన్", "trigun", "త్రిగుణ్", "jhansi", "ఝాన్సీ", "rohit", "రోహిత్", "sudheer", "సుధీర్")):
        if any(k in t_low for k in ["overaction", "ఓవరాక్షన్", "over action", "drama", "డ్రామా"]):
            return "ఓవరాక్షన్ పీక్స్!"
        elif any(k in t_low for k in ["elimination", "eviction", "ఎలిమినేషన్", "ఎలిమినేట్"]):
            return "ఎలిమినేషన్ షాక్?!"
        elif any(k in t_low for k in ["nomination", "నామినేషన్", "నామినేట్"]):
            return "నామినేషన్ ట్విస్ట్?!"
        elif any(k in t_low for k in ["fight", "రచ్చ", "గొడవ", "clash", "war"]):
            return "హౌస్‌లో రచ్చ రంబోలా!"
        elif any(k in t_low for k in ["family", "ఫ్యామిలీ", "visit"]):
            return "ఫ్యామిలీ విజిట్ ట్విస్ట్?!"
        elif any(k in t_low for k in ["secret", "నిజం", "లీక్", "truth"]):
            return "అసలు నిజం లీక్?!"
        elif any(k in t_low for k in ["nagarjuna", "నాగార్జున", "warning", "వార్నింగ్"]):
            return "నాగార్జున ఫైర్!"
        elif any(k in t_low for k in ["wild card", "wildcard", "వైల్డ్ కార్డ్"]):
            return "వైల్డ్ కార్డ్ ఎంట్రీ?!"
        elif any(k in t_low for k in ["shock", "twist", "షాక్", "ట్విస్ట్"]):
            return "షాకింగ్ ట్విస్ట్?!"
        telugu_words = re.findall(r"[\u0C00-\u0C7F]+", t)
        if len(telugu_words) >= 2:
            return " ".join(telugu_words[:3]) + "!"
        return "బిగ్ బాస్ బిగ్ ట్విస్ట్?!"

    # Check for direct curiosity question in the title
    if "?" in t:
        q_part = [p.strip() for p in t.split("?") if p.strip()]
        if q_part:
            words = q_part[0].split()
            if len(words) <= 4:
                return (q_part[0] + "?").upper()
            else:
                return (" ".join(words[-4:]) + "?").upper()

    # If colon, pipe, or hyphen separates a punchy statement, take the punchiest part
    parts = [p.strip() for p in re.split(r"[:|!-]", t) if p.strip()]
    if len(parts) > 1:
        cand = parts[1] if 2 <= len(parts[1].split()) <= 4 else parts[0]
        words = cand.split()
        if 2 <= len(words) <= 4:
            return " ".join(words[:4]).upper()

    # Topic-specific curiosity trigger mappings for English
    if any(k in t_low for k in ["elimination", "eviction"]):
        return "SHOCKING ELIMINATION?!"
    elif any(k in t_low for k in ["nomination"]):
        return "NOMINATION TWIST?!"
    elif any(k in t_low for k in ["wild card", "wildcard"]):
        return "WILDCARD ENTRY BOMBSHELL!"
    elif any(k in t_low for k in ["nagarjuna"]):
        return "NAGARJUNA SHOCKING VERDICT!"
    elif any(k in t_low for k in ["secret room"]):
        return "SECRET ROOM DRAMA!"

    words = re.findall(r"[\w\u0C00-\u0C7F]+", t)
    stop_words = {"the", "a", "an", "is", "in", "and", "or", "of", "to", "for", "with", "this", "that", "telugu", "full", "story", "analysis"}
    punchy_words = [w for w in words if w.lower() not in stop_words]

    if len(punchy_words) >= 3:
        return " ".join(punchy_words[:4]).upper()
    elif len(words) >= 3:
        return " ".join(words[:4]).upper()
    elif words:
        return " ".join(words).upper()

    return "SHOCKING TWIST?!"


def _fit_to_aspect_ratio(image, aspect_ratio="16:9"):
    """
    Fits and sizes the image to the specified aspect ratio with smart canvas:
    - 16:9 -> 1280x720
    - 9:16 -> 1080x1920
    - 1:1 -> 1080x1080
    If aspect ratio differs substantially (e.g. landscape image on 9:16 vertical),
    uses blurred background canvas padding rather than cropping away all context.
    """
    from PIL import ImageEnhance

    if aspect_ratio == "9:16":
        target_w, target_h = 1080, 1920
    elif aspect_ratio == "1:1":
        target_w, target_h = 1080, 1080
    else:
        target_w, target_h = 1280, 720

    target_ratio = target_w / target_h
    width, height = image.size
    current_ratio = width / height

    # If aspect ratio is close (within 25%), clean center-crop
    if abs(current_ratio - target_ratio) / target_ratio < 0.25:
        if current_ratio > target_ratio:
            new_w = int(height * target_ratio)
            left = (width - new_w) // 2
            cropped = image.crop((left, 0, left + new_w, height))
        else:
            new_h = int(width / target_ratio)
            top = (height - new_h) // 2
            cropped = image.crop((0, top, width, top + new_h))
        return cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
    else:
        # Smart canvas:
        # 1. Background: scale to fill canvas and apply heavy blur + darkening
        bg_scale = max(target_w / width, target_h / height)
        bg_w, bg_h = int(width * bg_scale), int(height * bg_scale)
        bg = image.resize((bg_w, bg_h), Image.Resampling.BILINEAR)
        left = (bg_w - target_w) // 2
        top = (bg_h - target_h) // 2
        bg = bg.crop((left, top, left + target_w, top + target_h))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=28))
        bg = ImageEnhance.Brightness(bg).enhance(0.45)

        # 2. Foreground: scale to fit within canvas cleanly
        fg_scale = min(target_w / width, target_h / height)
        fg_w, fg_h = int(width * fg_scale), int(height * fg_scale)
        fg = image.resize((fg_w, fg_h), Image.Resampling.LANCZOS)

        # 3. Paste centered
        fg_x = (target_w - fg_w) // 2
        fg_y = (target_h - fg_h) // 2
        bg.paste(fg, (fg_x, fg_y))
        return bg


def create_thumbnail(title, aspect_ratio="16:9", assets_dir=None, output_dir=None):

    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("=" * 60)
    print(f"THUMBNAIL GENERATION ({aspect_ratio})")
    print("=" * 60)

    background_path = _find_best_background(aspect_ratio=aspect_ratio, assets_dir=assets_dir)

    image = None
    if background_path and Path(background_path).exists():
        try:
            image = Image.open(background_path).convert("RGB")
            background_name = Path(background_path).name
        except Exception as exc:
            print(f"⚠️ Failed to open background: {exc}")

    if image is None:
        print("ℹ️ Synthesizing branded high-contrast slate background for thumbnail...")
        canvas_w = 1080 if aspect_ratio == "9:16" else 1280
        canvas_h = 1920 if aspect_ratio == "9:16" else 720
        image = Image.new("RGB", (canvas_w, canvas_h), color=(15, 23, 42))
        slate_draw = ImageDraw.Draw(image)
        slate_draw.rectangle((0, int(canvas_h * 0.35), canvas_w, int(canvas_h * 0.65)), fill=(30, 41, 59))
        background_name = "branded_slate.jpg"

    # --------------------------------------------------------
    # FIT / RESIZE ACCORDING TO ASPECT RATIO
    # --------------------------------------------------------

    image = _fit_to_aspect_ratio(
        image,
        aspect_ratio=aspect_ratio,
    )

    canvas_w, canvas_h = image.size

    # --------------------------------------------------------
    # SLIGHT CONTRAST / SHARPNESS
    # --------------------------------------------------------

    image = image.filter(
        ImageFilter.UnsharpMask(
            radius=1,
            percent=120,
            threshold=3,
        )
    )

    # --------------------------------------------------------
    # DARK GRADIENT / SAFE ZONE OVERLAY
    # --------------------------------------------------------

    image = image.convert("RGBA")

    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    overlay_draw = ImageDraw.Draw(
        overlay
    )

    if aspect_ratio == "9:16":
        # Subtle gradient/soft darkening banner for vertical shorts
        overlay_draw.rectangle(
            (0, 920, canvas_w, 1380),
            fill=(0, 0, 0, 95),
        )
        overlay_draw.rectangle(
            (0, 0, canvas_w, 120),
            fill=(0, 0, 0, 30),
        )
        font_size = 78
        line_height = 92
        target_center_y = 1140
        max_text_width = canvas_w - 140
    elif aspect_ratio == "1:1":
        overlay_draw.rectangle(
            (0, 720, canvas_w, canvas_h),
            fill=(0, 0, 0, 95),
        )
        overlay_draw.rectangle(
            (0, 0, canvas_w, 90),
            fill=(0, 0, 0, 30),
        )
        font_size = 66
        line_height = 80
        target_center_y = 880
        max_text_width = canvas_w - 120
    else:  # 16:9
        overlay_draw.rectangle(
            (0, 420, canvas_w, canvas_h),
            fill=(0, 0, 0, 95),
        )
        overlay_draw.rectangle(
            (0, 0, canvas_w, 90),
            fill=(0, 0, 0, 30),
        )
        font_size = 68
        line_height = 80
        target_center_y = 560
        max_text_width = canvas_w - 160

    image = Image.alpha_composite(
        image,
        overlay,
    )

    draw = ImageDraw.Draw(image)

    # --------------------------------------------------------
    # TITLE (High-CTR Curiosity Badge)
    # --------------------------------------------------------

    is_telugu_topic = bool(
        re.search(r"[\u0C00-\u0C7F]", str(title))
        or ((OUTPUT_DIR / "topic.txt").exists() and re.search(r"[\u0C00-\u0C7F]|bigg boss|biggboss", (OUTPUT_DIR / "topic.txt").read_text(encoding="utf-8").lower()))
        or re.search(r"bigg\s*boss|aman|trigun|jhansi|rohit|sudheer", str(title).lower())
    )

    thumbnail_title = _clean_title(
        title,
        is_telugu=is_telugu_topic,
    )

    is_telugu_title = bool(re.search(r"[\u0C00-\u0C7F]", thumbnail_title))
    font = _load_font(font_size, is_telugu=is_telugu_title)

    # Wrap based on pixel width rather than blindly using a fixed word count.
    words = thumbnail_title.split()

    lines = []
    current = ""

    for word in words:
        test = (
            f"{current} {word}"
            if current
            else word
        )

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font,
            stroke_width=0,
        )

        text_width = (
            bbox[2] - bbox[0]
        )

        if (
            text_width <= max_text_width
            and len(lines) < 2
        ):
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    lines = lines[:2]  # Keep strictly 1-2 lines for maximum impact

    # --------------------------------------------------------
    # CENTER TITLE VERTICALLY IN TARGET ZONE WITH HIGH-CONTRAST PILL BADGES
    # --------------------------------------------------------

    total_height = (
        len(lines) * line_height
    )

    y = target_center_y - (
        total_height // 2
    )

    for idx, line in enumerate(lines):
        bbox = draw.textbbox(
            (0, 0),
            line,
            font=font,
            stroke_width=4,
        )

        text_width = (
            bbox[2] - bbox[0]
        )

        x = (
            canvas_w - text_width
        ) // 2

        # Draw High-CTR Pill Badge behind the line
        pad_x, pad_y = 26, 8
        pill_left = max(10, x - pad_x)
        pill_top = max(10, y - pad_y)
        pill_right = min(canvas_w - 10, x + text_width + pad_x)
        pill_bottom = min(canvas_h - 10, y + line_height - 6)

        # Drop shadow for pill
        draw.rounded_rectangle(
            (pill_left + 4, pill_top + 6, pill_right + 4, pill_bottom + 6),
            radius=16,
            fill=(0, 0, 0, 180),
        )

        # Pill background with contrasting border
        pill_border = "#FFCC00" if idx == 0 else "#E63946"
        draw.rounded_rectangle(
            (pill_left, pill_top, pill_right, pill_bottom),
            radius=16,
            fill=(12, 14, 24, 230),
            outline=pill_border,
            width=3,
        )

        # Vibrant high-CTR color: Golden yellow for first line, crisp white for second
        text_color = "#FFE600" if idx == 0 else "#FFFFFF"

        # High-contrast text with deep outline
        draw.text(
            (x, y),
            line,
            font=font,
            fill=text_color,
            stroke_width=4,
            stroke_fill="black",
        )

        y += line_height

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    output = (
        out_dir /
        "thumbnail.jpg"
    )
    global_output = (
        OUTPUT_DIR /
        "thumbnail.jpg"
    )

    image_rgb = image.convert("RGB")
    image_rgb.save(
        output,
        "JPEG",
        quality=95,
        optimize=True,
    )

    if output.resolve() != global_output.resolve():
        try:
            image_rgb.save(
                global_output,
                "JPEG",
                quality=95,
                optimize=True,
            )
        except Exception:
            try:
                import shutil
                shutil.copyfile(output, global_output)
            except Exception:
                pass

    print(
        f"✅ Thumbnail created ({canvas_w}x{canvas_h}): {output} (and {global_output})"
    )

    print(
        f"📝 Thumbnail title: "
        f"{thumbnail_title}"
    )

    print(
        f"🖼️ Background: "
        f"{background_name}"
    )

    print("=" * 60)

    return output


# ============================================================
# CTR A/B THUMBNAIL VARIANT GENERATION & RANKING
# ============================================================

def generate_thumbnail_prompts(topic_data: dict, gemini_call_fn=None) -> list[str]:
    """Generate 3 distinct, high-CTR visual thumbnail concepts for AI image generation."""
    topic_str = topic_data.get("topic") if isinstance(topic_data, dict) else str(topic_data)
    default_prompts = [
        f"{topic_str}, dramatic high-contrast studio lighting, bold close-up, vivid colors, photorealistic 8k, cinematic YouTube thumbnail style",
        f"{topic_str}, shocking revelation split comparison, intense neon rim lighting, sharp focal subject, ultra-detailed 8k",
        f"{topic_str}, sleek futuristic tech showcase, dramatic dark background, glowing highlights, clean commercial photography 8k",
    ]

    if gemini_call_fn is None:
        try:
            from agents.script_agent import get_client
            client = get_client()
            def _call_gem(prompt):
                for m in ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-3.5-flash-lite", "gemini-3.8-flash"]:
                    try:
                        resp = client.models.generate_content(
                            model=m,
                            contents=prompt,
                        )
                        if getattr(resp, "text", ""):
                            return resp.text
                    except Exception:
                        continue
                return ""
            gemini_call_fn = _call_gem
        except Exception:
            return default_prompts

    prompt = f"""
    You are an expert YouTube thumbnail designer specializing in high-CTR tech thumbnails.
    Given this topic/script context: "{topic_str}"
    
    Generate EXACTLY 3 distinct visual image prompts designed for text-to-image AI (FLUX / Pollinations).
    1. Concept 1: Bold, curiosity-inducing close-up (single dominant subject, high contrast).
    2. Concept 2: Shocking spec / comparison / dramatic angle.
    3. Concept 3: Futuristic tech showcase / sleek cinematic lighting.

    RULES:
    - Describe pure visual imagery ONLY. Do NOT include text on the image.
    - Keep each prompt under 35 words.
    - Return a valid JSON array of 3 strings only.
    """
    try:
        import json
        res = gemini_call_fn(prompt).strip().strip("`")
        if res.lower().startswith("json"):
            res = res[4:].strip()
        parsed = json.loads(res)
        if isinstance(parsed, list) and len(parsed) == 3:
            return parsed
    except Exception as e:
        print(f"⚠️ Thumbnail prompt generation notice: {e}")

    return default_prompts


def rank_thumbnails_by_gemini(candidates, topic_data, gemini_call_fn=None):
    """Rank thumbnail candidate filepaths for CTR potential on Telugu tech YouTube channel."""
    if not candidates:
        return []
    if len(candidates) == 1:
        return candidates

    topic_str = topic_data.get("topic") if isinstance(topic_data, dict) else str(topic_data)

    if gemini_call_fn is None:
        try:
            from agents.script_agent import get_client
            client = get_client()
            def _call_gem(prompt):
                for m in ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-3.5-flash-lite", "gemini-3.8-flash"]:
                    try:
                        resp = client.models.generate_content(
                            model=m,
                            contents=prompt,
                        )
                        if getattr(resp, "text", ""):
                            return resp.text
                    except Exception:
                        continue
                return ""
            gemini_call_fn = _call_gem
        except Exception:
            return candidates

    prompt = f"""
    Rank these {len(candidates)} thumbnail concepts for click-through-rate (CTR) potential
    on a Telugu tech YouTube Shorts/Reels channel.
    Prioritize:
    1. Instant curiosity / curiosity-gap
    2. High contrast & visual punch on a small smartphone screen
    3. Crystal-clear focal subject (no clutter)
    
    Topic: {topic_str}
    
    Candidates:
    {[c if isinstance(c, str) else str(c) for c in candidates]}
    
    Return the ranked candidate 0-indexed indices as a JSON array of integers (best first, e.g. [1, 0, 2]).
    """
    try:
        import json
        res = gemini_call_fn(prompt).strip().strip("`")
        if res.lower().startswith("json"):
            res = res[4:].strip()
        ranked_indices = json.loads(res)
        if isinstance(ranked_indices, list):
            valid_ranked = [candidates[i] for i in ranked_indices if isinstance(i, int) and 0 <= i < len(candidates)]
            for c in candidates:
                if c not in valid_ranked:
                    valid_ranked.append(c)
            return valid_ranked
    except Exception as e:
        print(f"⚠️ Thumbnail ranking notice: {e}")

    return candidates


def generate_thumbnail_variants(topic_data: dict, gemini_call_fn=None, flux_generate_fn=None) -> list[str]:
    """Generate 3 thumbnail concepts, render them, and rank them for click-worthiness."""
    prompts = generate_thumbnail_prompts(topic_data, gemini_call_fn)
    print(f"🎨 Generated {len(prompts)} thumbnail concept prompts for A/B testing")

    candidates = []
    if flux_generate_fn:
        for idx, p in enumerate(prompts):
            out_candidate = OUTPUT_DIR / f"thumbnail_candidate_{idx+1}.jpg"
            try:
                res = flux_generate_fn(p, str(out_candidate))
                if res and os.path.exists(res):
                    candidates.append(str(res))
            except Exception as err:
                print(f"⚠️ Candidate {idx+1} generation warning: {err}")

    if not candidates:
        best_thumb = create_thumbnail(topic_data.get("title") if isinstance(topic_data, dict) else str(topic_data))
        if best_thumb:
            candidates.append(str(best_thumb))

    ranked = rank_thumbnails_by_gemini(candidates, topic_data, gemini_call_fn)

    # Copy top-ranked thumbnail to output/thumbnail.jpg
    if ranked and os.path.exists(ranked[0]):
        import shutil
        shutil.copyfile(ranked[0], OUTPUT_DIR / "thumbnail.jpg")
        print(f"🏆 Best-ranked thumbnail selected: {ranked[0]} -> output/thumbnail.jpg")

    return ranked


if __name__ == "__main__":

    create_thumbnail(
        "Tata Motors Latest News"
    )


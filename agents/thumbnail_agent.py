from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import os
import re
import textwrap
from pathlib import Path
import json
import shutil
from typing import Optional, List, Dict, Tuple


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
        # Before returning a flat slate, attempt to generate an AI backdrop (Pollinations Sana 8k)
        ai_thumb_path = (ASSETS_DIR / f"ai_thumb_bg_{aspect_ratio.replace(':', '_')}.jpg")
        try:
            topic_str = ""
            if (OUTPUT_DIR / "topic.txt").exists():
                topic_str = (OUTPUT_DIR / "topic.txt").read_text(encoding="utf-8").strip()
            topic_clean = re.sub(r"[\u0C00-\u0C7F]", " ", topic_str).strip()
            if not topic_clean:
                topic_clean = "dramatic television studio glowing stage neon lights cinematic 8k"
            else:
                topic_clean = f"{topic_clean} dramatic stage neon lights cinematic 8k studio"

            from providers.image import generate_pollinations_image
            success = generate_pollinations_image(topic_clean, ai_thumb_path, aspect_ratio=aspect_ratio, force=True)
            if success and ai_thumb_path.exists() and ai_thumb_path.stat().st_size > 5000:
                candidates.append((90, ai_thumb_path))
                print(f"✨ [AI Generative Backdrop] Created photorealistic AI background: {ai_thumb_path.name}")
        except Exception as ai_bg_err:
            print(f"⚠️ AI backdrop generation notice: {ai_bg_err}")

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
    Converts a video title into a high-CTR, strictly 2-4 word curiosity-gap phrase.
    Guarantees:
    1. Simple & Clean: strictly 2 to 4 words in large font.
    2. Curiosity Gap: Never repeats the full video title; triggers intense viewer mystery.
    3. High-Contrast viral hooks in authentic Telugu or punchy English.
    """
    if not title:
        return "షాకింగ్ ట్విస్ట్?!" if is_telugu else "SHOCKING TWIST?!"

    t = str(title).strip()
    t_low = t.lower()

    # Topic-driven high-CTR Telugu curiosity badges (strictly 2-4 words)
    if is_telugu or any(k in t_low for k in ("bigg boss", "biggboss", "బిగ్ బాస్", "aman", "అమన్", "trigun", "త్రిగుణ్", "jhansi", "ఝాన్సీ", "rohit", "రోహిత్", "sudheer", "సుధీర్", "vamsi", "వంశీ")):
        if any(k in t_low for k in ["overaction", "ఓవరాక్షన్", "over action", "drama", "డ్రామా", "యాక్టింగ్"]):
            return "ఓవరాక్షన్ పీక్స్!"
        elif any(k in t_low for k in ["elimination", "eviction", "ఎలిమినేషన్", "ఎలిమినేట్", "వీడ్కోలు", "బయటకు"]):
            return "ఎలిమినేషన్ షాక్?!"
        elif any(k in t_low for k in ["nomination", "నామినేషన్", "నామినేట్"]):
            return "నామినేషన్ ట్విస్ట్?!"
        elif any(k in t_low for k in ["fight", "రచ్చ", "గొడవ", "clash", "war", "ఘర్షణ", "వార్"]):
            return "హౌస్‌లో రచ్చ రంబోలా!"
        elif any(k in t_low for k in ["secret", "నిజం", "లీక్", "truth", "సీక్రెట్", "బట్టబయలు", "ఎక్స్‌పోజ్"]):
            return "అసలు నిజం లీక్?!"
        elif any(k in t_low for k in ["nagarjuna", "నాగార్జున", "warning", "వార్నింగ్", "క్లాస్", "ఫైర్"]):
            return "నాగార్జున ఫైర్!"
        elif any(k in t_low for k in ["winner", "విన్నర్", "కప్పు", "ట్రోఫీ", "గెలుపు"]):
            return "విన్నర్ ఎవరో లీక్?!"
        elif any(k in t_low for k in ["wild card", "wildcard", "వైల్డ్ కార్డ్", "ఎంట్రీ"]):
            return "వైల్డ్ కార్డ్ ఎంట్రీ?!"
        elif any(k in t_low for k in ["fake", "ఫేక్", "మోసం", "చీటింగ్"]):
            return "ఫేక్ డ్రామా బయటపడింది!"
        elif any(k in t_low for k in ["shock", "twist", "షాక్", "ట్విస్ట్", "ట్విస్టు"]):
            return "షాకింగ్ ట్విస్ట్?!"

        # If title has custom Telugu words, extract punchiest 2-3 words (NEVER full sentence)
        telugu_words = re.findall(r"[\u0C00-\u0C7F]+", t)
        stop_words = {"బిగ్", "బాస్", "తెలుగు", "ఈ", "మరియు", "ఆ", "ఒక", "గురించి", "తో", "లో"}
        punchy = [w for w in telugu_words if w not in stop_words]
        if len(punchy) >= 2:
            return " ".join(punchy[:3]) + "?!"
        return "షాకింగ్ ట్విస్ట్?!"

    # English high-CTR curiosity triggers (strictly 2-4 words)
    if any(k in t_low for k in ["elimination", "eviction"]):
        return "SHOCKING ELIMINATION?!"
    elif any(k in t_low for k in ["nomination"]):
        return "NOMINATION TWIST?!"
    elif any(k in t_low for k in ["secret", "truth", "leak"]):
        return "THE TRUTH LEAKED?!"
    elif any(k in t_low for k in ["fight", "clash", "drama"]):
        return "UNEXPECTED DRAMA?!"
    elif any(k in t_low for k in ["fake", "cheat", "scam"]):
        return "EXPOSED ON STAGE!"
    elif any(k in t_low for k in ["shock", "twist"]):
        return "SHOCKING TWIST?!"

    words = [w for w in re.findall(r"[A-Za-z0-9]+", t) if w.lower() not in {"the", "a", "an", "is", "in", "and", "or", "of", "to", "for", "with", "this", "that", "review", "full", "video"}]
    if len(words) >= 2:
        return (" ".join(words[:3]) + "?!").upper()

    return "SHOCKING TWIST?!"


def _find_contestant_slug(text: str) -> Optional[str]:
    """Finds a matching contestant slug from text using contestants.json and entity library."""
    t_low = str(text or "").lower()
    c_json = ROOT / "contestants.json"
    if c_json.exists():
        try:
            data = json.loads(c_json.read_text(encoding="utf-8"))
            for slug, c_info in data.items():
                if slug in ("bigg_boss_telugu", "host"):
                    continue
                aliases = c_info.get("aliases", []) + [slug.replace("_", " "), c_info.get("nickname", "")]
                for a in aliases:
                    if a and len(str(a).strip()) >= 3 and str(a).lower() in t_low:
                        return slug
        except Exception:
            pass

    try:
        from tools.build_entity_library import match_entities_in_text
        ents = match_entities_in_text(text)
        for e in ents:
            eid = e.get("id") or e.get("slug")
            if eid and eid not in ("bigg_boss_telugu", "host_nagarjuna"):
                return eid
    except Exception:
        pass
    return None


def _fit_to_aspect_ratio(image, aspect_ratio="16:9"):
    """
    Fits and sizes the image to the specified aspect ratio using full-bleed cinema framing.
    Guarantees 100% full-screen coverage with zero blurred Canva borders or boxed card artifacts.
    - 16:9 -> 1280x720
    - 9:16 -> 1080x1920 (dramatic vertical cinema zoom centered on faces)
    - 1:1 -> 1080x1080
    """
    from PIL import ImageEnhance

    if aspect_ratio == "9:16":
        target_w, target_h = 1080, 1920
    elif aspect_ratio == "1:1":
        target_w, target_h = 1080, 1080
    else:
        target_w, target_h = 1280, 720

    width, height = image.size

    # Full-Bleed Cinema Framing: Scale to completely fill target canvas
    scale = max(target_w / width, target_h / height)
    scaled_w = int(width * scale)
    scaled_h = int(height * scale)
    scaled = image.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    # Center horizontally
    left = max(0, (scaled_w - target_w) // 2)

    # For vertical 9:16, human faces/expressions are typically in the upper 25-40% of the frame
    if aspect_ratio == "9:16" and scaled_h > target_h:
        top = max(0, min(scaled_h - target_h, int((scaled_h - target_h) * 0.30)))
    else:
        top = max(0, (scaled_h - target_h) // 2)

    cropped = scaled.crop((left, top, left + target_w, top + target_h))
    return cropped


def create_thumbnail(title, aspect_ratio="16:9", assets_dir=None, output_dir=None, use_playwright=True):

    if use_playwright:
        try:
            return create_playwright_canva_thumbnail(
                title=title,
                aspect_ratio=aspect_ratio,
                assets_dir=assets_dir,
                output_dir=output_dir,
            )
        except Exception as pw_err:
            print(f"⚠️ Playwright thumbnail generation notice: {pw_err}. Falling back to native canvas.")

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

    # If background is missing or is just a flat slate, generate photorealistic AI backdrop (Pollinations Sana 8k)
    if image is None or getattr(background_path, "name", "") in ("thumbnail_slate.jpg", "branded_slate.jpg"):
        try:
            ai_dest = out_dir / f"ai_backdrop_{aspect_ratio.replace(':', '_')}.jpg"
            clean_title_prompt = re.sub(r"[\u0C00-\u0C7F]", " ", str(title)).strip()
            t_file = OUTPUT_DIR / "topic.txt"
            if t_file.exists():
                topic_raw = t_file.read_text(encoding="utf-8").strip()
                clean_topic = re.sub(r"[\u0C00-\u0C7F]", " ", topic_raw).strip()
                if clean_topic:
                    clean_title_prompt = f"{clean_topic} {clean_title_prompt}"
            if not clean_title_prompt or len(clean_title_prompt) < 4:
                clean_title_prompt = "reality show stage dramatic glowing lights dark cinematic 8k studio"
            else:
                clean_title_prompt = f"{clean_title_prompt} dramatic stage neon studio lighting cinematic 8k"

            from providers.image import generate_pollinations_image
            if generate_pollinations_image(clean_title_prompt, ai_dest, aspect_ratio=aspect_ratio, force=True):
                image = Image.open(ai_dest).convert("RGB")
                background_name = ai_dest.name
                print(f"🎨 [AI Backdrop] Loaded photorealistic AI backdrop: {ai_dest.name}")
        except Exception as ai_e:
            print(f"⚠️ AI backdrop generation fallback notice: {ai_e}")

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
    # PRASAD TECH IN TELUGU STYLE: REAL CUTOUT COMPOSITING (IF ENTITY DETECTED)
    # --------------------------------------------------------
    is_telugu_topic = bool(
        re.search(r"[\u0C00-\u0C7F]", str(title))
        or ((OUTPUT_DIR / "topic.txt").exists() and re.search(r"[\u0C00-\u0C7F]|bigg boss|biggboss", (OUTPUT_DIR / "topic.txt").read_text(encoding="utf-8").lower()))
        or re.search(r"bigg\s*boss|aman|trigun|jhansi|rohit|sudheer", str(title).lower())
    )

    ent_slug = _find_contestant_slug(title)
    if not ent_slug:
        t_file = (out_dir / "topic.txt") if (out_dir / "topic.txt").exists() else (OUTPUT_DIR / "topic.txt")
        if t_file.exists():
            ent_slug = _find_contestant_slug(t_file.read_text(encoding="utf-8"))
    if not ent_slug:
        m_file = (out_dir / "metadata.json") if (out_dir / "metadata.json").exists() else (OUTPUT_DIR / "metadata.json")
        if m_file.exists():
            ent_slug = _find_contestant_slug(m_file.read_text(encoding="utf-8"))

    cutout_applied = False
    if ent_slug:
        try:
            from tools.person_cutout import extract_person_cutout
            # Prioritize high-emotion close-up facial expressions (shock, anger, laughter)
            cand_paths = []
            slug_variants = [ent_slug, f"{ent_slug}_naidu", f"{ent_slug}_reddy", f"{ent_slug}_sounderajan", f"{ent_slug}_contestant", f"{ent_slug}_bb"]
            emotion_stems = ["shocked", "angry", "laughing", "smug", "reaction", "surprised", "crying", "neutral", "image"]
            for em in emotion_stems:
                for sv in slug_variants:
                    cand_paths.append(ROOT / "data" / "entities" / sv / f"{em}.jpg")
                    cand_paths.append(ROOT / "data" / "entities" / sv / f"{em}.png")
                    cand_paths.append(ROOT / "assets" / "entities" / sv / f"{em}.jpg")
                    cand_paths.append(ROOT / "assets" / "entities" / sv / "image.jpg")

            person_img_path = next((p for p in cand_paths if p.exists() and p.stat().st_size > 1000), None)
            if person_img_path:
                cutout_path = extract_person_cutout(person_img_path)
                if cutout_path and Path(cutout_path).exists():
                    cutout_img = Image.open(cutout_path).convert("RGBA")
                    cw, ch = cutout_img.size

                    # Close-up face crop: focus on head and shoulders for high-emotion YouTuber reaction impact
                    if ch > 350:
                        cutout_img = cutout_img.crop((0, 0, cw, int(ch * 0.72)))
                        cw, ch = cutout_img.size

                    # Scale cutout to dominate canvas
                    if aspect_ratio == "9:16":
                        target_ch = int(canvas_h * 0.65)
                        target_cw = int(cw * (target_ch / ch))
                        cutout_img = cutout_img.resize((target_cw, target_ch), Image.Resampling.LANCZOS)
                        cx = (canvas_w - target_cw) // 2
                        cy = int(canvas_h * 0.10)
                    elif aspect_ratio == "1:1":
                        target_ch = int(canvas_h * 0.75)
                        target_cw = int(cw * (target_ch / ch))
                        cutout_img = cutout_img.resize((target_cw, target_ch), Image.Resampling.LANCZOS)
                        cx = (canvas_w - target_cw) // 2
                        cy = int(canvas_h * 0.08)
                    else:  # 16:9 (Prasad Tech layout: Subject stands on the right)
                        target_ch = int(canvas_h * 0.95)
                        target_cw = int(cw * (target_ch / ch))
                        cutout_img = cutout_img.resize((target_cw, target_ch), Image.Resampling.LANCZOS)
                        cx = canvas_w - target_cw - 40
                        cy = canvas_h - target_ch

                    # Golden outer rim glow (Prasad Tech signature pop)
                    r, g, b, a = cutout_img.split()
                    glow_color = Image.new("RGBA", cutout_img.size, (255, 185, 0, 230))
                    glow_color.putalpha(a)
                    glow_expanded = glow_color.filter(ImageFilter.GaussianBlur(radius=22))

                    # Blend background and cutout
                    base_rgba = image.convert("RGBA")
                    # Dim background so cutout and high-contrast text pop
                    enhancer = ImageEnhance.Brightness(base_rgba)
                    base_rgba = enhancer.enhance(0.78)

                    base_rgba.paste(glow_expanded, (cx, cy), glow_expanded)
                    base_rgba.paste(cutout_img, (cx, cy), cutout_img)
                    image = base_rgba
                    cutout_applied = True
                    print(f"🌟 [Prasad Tech Style] Blended high-emotion person cutout for {ent_slug} with vibrant rim glow!")
        except Exception as cutout_err:
            print(f"⚠️ Person cutout blend notice: {cutout_err}")

    # --------------------------------------------------------
    # LOWER-THIRD / SPLIT-SCREEN VIGNETTE OVERLAY
    # --------------------------------------------------------

    image = image.convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    if aspect_ratio == "16:9" and cutout_applied:
        # Subtle dark gradient on left 50% for split-screen text readability
        overlay_draw.rectangle(
            (0, 0, int(canvas_w * 0.52), canvas_h),
            fill=(0, 0, 0, 120),
        )
    else:
        # Soft dark gradient at bottom 24% for bottom badge readability
        vignette_y = int(canvas_h * 0.72)
        overlay_draw.rectangle(
            (0, vignette_y, canvas_w, canvas_h),
            fill=(0, 0, 0, 160),
        )

    image = Image.alpha_composite(image, overlay)

    # --------------------------------------------------------
    # TITLE (High-CTR Curiosity Badge: Strictly 2-4 Words)
    # --------------------------------------------------------

    thumbnail_title = _clean_title(
        title,
        is_telugu=is_telugu_topic,
    )

    badge_drawn = False
    # Attempt native CoreText Telugu badge rendering (Flawless Apple typography)
    if is_telugu_topic:
        try:
            from tools.native_typography import render_native_telugu_badge
            # High-CTR color scheme: Yellow, Red, White on Obsidian Black
            badge_border = "#E63946" if any(w in thumbnail_title for w in ["షాక్", "ఎలిమినేషన్", "ఫైర్", "రచ్చ", "ELIMINATION", "DRAMA", "SHOCK"]) else "#FFD700"
            badge_font_size = 82 if aspect_ratio == "9:16" else (64 if aspect_ratio == "16:9" else 70)
            native_badge_path = render_native_telugu_badge(thumbnail_title, font_size=badge_font_size, border_color=badge_border)
            if native_badge_path and Path(native_badge_path).exists():
                badge_img = Image.open(native_badge_path).convert("RGBA")
                bw, bh = badge_img.size

                # Auto-scale if badge width exceeds max allowed width
                if aspect_ratio == "16:9" and cutout_applied:
                    max_bw = int(canvas_w * 0.52)
                else:
                    max_bw = int(canvas_w * 0.92)

                if bw > max_bw:
                    scale_factor = max_bw / float(bw)
                    badge_img = badge_img.resize((max_bw, int(bh * scale_factor)), Image.Resampling.LANCZOS)
                    bw, bh = badge_img.size

                # Position strictly at the BOTTOM (lower third) or LEFT split-screen (Safe from YouTube bottom-right timer!)
                if aspect_ratio == "9:16":
                    bx = (canvas_w - bw) // 2
                    by = canvas_h - bh - 230  # Safely above YouTube Shorts bottom UI, leaving face 100% free!
                elif aspect_ratio == "1:1":
                    bx = (canvas_w - bw) // 2
                    by = canvas_h - bh - 80
                else:  # 16:9 Landscape
                    if cutout_applied:
                        # Prasad Tech split-screen: Subject on RIGHT, Badge on LEFT (Bottom-right corner 100% free)
                        bx = 60
                        by = (canvas_h - bh) // 2
                    else:
                        bx = 60
                        by = canvas_h - bh - 80

                image.paste(badge_img, (bx, by), badge_img)
                badge_drawn = True
                print(f"✍️ [Native Typography] Rendered native CoreText Telugu badge at ({bx}, {by}): '{thumbnail_title}'")
        except Exception as nat_err:
            print(f"⚠️ Native typography notice: {nat_err}")

    # Fallback to standard Pillow text rendering if native renderer was not used
    if not badge_drawn:
        draw = ImageDraw.Draw(image)
        font_size = 82 if aspect_ratio == "9:16" else (64 if aspect_ratio == "16:9" else 70)
        line_height = int(font_size * 1.18)
        font = _load_font(font_size, is_telugu=is_telugu_topic)

        words = thumbnail_title.split()
        lines = []
        current = ""
        max_text_width = int(canvas_w * 0.50) if (aspect_ratio == "16:9" and cutout_applied) else (canvas_w - 140)

        for word in words:
            test = f"{current} {word}" if current else word
            bbox = draw.textbbox((0, 0), test, font=font, stroke_width=0)
            if (bbox[2] - bbox[0]) <= max_text_width and len(lines) < 2:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        lines = lines[:2]

        total_height = len(lines) * line_height
        if aspect_ratio == "16:9" and cutout_applied:
            # Left split-screen
            y = (canvas_h - total_height) // 2
            base_x = 50
        else:
            # Bottom anchor
            bottom_anchor_y = canvas_h - total_height - (160 if aspect_ratio == "9:16" else 60)
            y = bottom_anchor_y
            base_x = None

        for idx, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font, stroke_width=4)
            text_width = bbox[2] - bbox[0]
            x = (canvas_w - text_width) // 2 if base_x is None else base_x

            pad_x, pad_y = 26, 8
            pill_left = max(10, x - pad_x)
            pill_top = max(10, y - pad_y)
            pill_right = min(canvas_w - 10, x + text_width + pad_x)
            pill_bottom = min(canvas_h - 10, y + line_height - 6)

            # Drop shadow
            draw.rounded_rectangle((pill_left + 4, pill_top + 6, pill_right + 4, pill_bottom + 6), radius=16, fill=(0, 0, 0, 180))
            # Pill background
            pill_border = "#FFCC00" if idx == 0 else "#E63946"
            draw.rounded_rectangle((pill_left, pill_top, pill_right, pill_bottom), radius=16, fill=(12, 14, 24, 230), outline=pill_border, width=3)
            # Text
            text_color = "#FFE600" if idx == 0 else "#FFFFFF"
            draw.text((x, y), line, font=font, fill=text_color, stroke_width=4, stroke_fill="black")
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


def create_playwright_canva_thumbnail(title, aspect_ratio="16:9", assets_dir=None, output_dir=None, channel="Channel 1 (Primary)") -> Path:
    """
    Renders the signature 'Prasad Tech in Telugu' high-CTR YouTube thumbnail using Playwright Chromium.
    Features:
    - Dual top banner black pills with high-contrast Yellow & White Telugu text and emojis.
    - Expressive cutout with golden/cyan glowing rim light.
    - Lower split evidence panels with cyan neon glow.
    - Floating brand logos and episode pill badge.
    - Standard 16:9 (1280x720) canvas for YouTube Data API (no side pillarbox bars).
    - If aspect_ratio == "9:16", also renders a 9:16 poster frame for video burn-in!
    """
    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from tools.playwright_renderer import render_prasad_tech_thumbnail, build_prasad_tech_thumbnail_params
        from tools.person_cutout import extract_person_cutout

        t_file = (out_dir / "topic.txt")
        topic_text = t_file.read_text(encoding="utf-8").strip() if t_file.exists() else str(title)

        # Build Prasad Tech style parameters
        params = build_prasad_tech_thumbnail_params(title=str(title), channel=str(channel), topic=topic_text)

        is_bb_run = any(bb_w in f"{title} {topic_text}".lower() for bb_w in ("bigg boss", "bb10", "బిగ్ బాస్"))

        # Cutout candidate: strictly search ONLY current title, current topic, and current run script
        cutout_path = None
        search_corpus = f"{title} {topic_text}"
        s_file = out_dir / "script.txt"
        if s_file.exists():
            try:
                search_corpus += f" {s_file.read_text(encoding='utf-8')[:300]}"
            except Exception:
                pass

        ent_slug = _find_contestant_slug(search_corpus)

        # Strict cross-topic firewall: If Bigg Boss, strictly REJECT non-Bigg Boss entities (Prabhas, movie stars, etc.)
        if is_bb_run and ent_slug in ("prabhas", "kalki_2898_ad_movie", "devara_movie", "dil_raju"):
            ent_slug = None

        if not ent_slug and is_bb_run:
            ent_slug = "nagarjuna"

        if ent_slug:
            cand_paths = []
            for ent_dir in [ROOT / "data" / "entities", ROOT / "assets" / "entities"]:
                if ent_dir.exists():
                    for sub in ent_dir.iterdir():
                        if sub.is_dir() and ent_slug.lower() in sub.name.lower():
                            for em in ["portrait_clean", "portrait", "clean", "shocked", "angry", "reaction", "image", "surprised", "laughing", "smug", "crying", "neutral"]:
                                cand_paths.append(sub / f"{em}.jpg")
                                cand_paths.append(sub / f"{em}.png")
            person_img_path = next((p for p in cand_paths if p.exists() and p.stat().st_size > 1000), None)
            if person_img_path:
                raw_cutout = extract_person_cutout(person_img_path)
                if raw_cutout and Path(raw_cutout).exists():
                    cutout_path = Path(raw_cutout)

        # Evidence images from generated run images if available
        ev_left_img = None
        ev_right_img = None
        run_images = list((out_dir / "images").glob("*.jpg")) + list((out_dir / "images").glob("*.png"))
        if not run_images:
            run_images = list((OUTPUT_DIR / "images").glob("*.jpg")) + list((OUTPUT_DIR / "images").glob("*.png"))
        if len(run_images) >= 1:
            ev_left_img = run_images[0]
        if len(run_images) >= 2:
            ev_right_img = run_images[1]

        out_png = out_dir / "thumbnail_prasad_16_9.png"
        res = render_prasad_tech_thumbnail(
            header_left_yellow=params["header_left_yellow"],
            header_left_white=params["header_left_white"],
            header_left_emoji=params["header_left_emoji"],
            header_right_white=params["header_right_white"],
            header_right_yellow=params["header_right_yellow"],
            header_right_emoji=params["header_right_emoji"],
            hero_cutout_path=cutout_path,
            evidence_left_img=ev_left_img,
            evidence_left_text=params["evidence_left_text"],
            evidence_left_badge=params["evidence_left_badge"],
            evidence_right_img=ev_right_img,
            evidence_right_text=params["evidence_right_text"],
            evidence_right_badge=params["evidence_right_badge"],
            episode_pill_text=params["episode_pill_text"],
            brand_logos=params.get("brand_logos"),
            aspect_ratio="16:9",  # Always 16:9 (1280x720) for YouTube API upload
            bg_theme=params.get("bg_theme", "tech_purple"),
            output_path=str(out_png),
        )

        if res and Path(res).exists():
            final_jpg = out_dir / "thumbnail.jpg"
            global_jpg = OUTPUT_DIR / "thumbnail.jpg"
            with Image.open(res) as img:
                img.convert("RGB").save(final_jpg, "JPEG", quality=95, optimize=True)
                if final_jpg.resolve() != global_jpg.resolve():
                    img.convert("RGB").save(global_jpg, "JPEG", quality=95, optimize=True)
            print(f"✅ [Prasad Tech Thumbnail Engine] High-CTR thumbnail created: {final_jpg}")

            # Also render 9:16 vertical poster if needed for video burn-in
            if aspect_ratio == "9:16":
                poster_916_path = out_dir / "thumbnail_916_poster.png"
                render_prasad_tech_thumbnail(
                    header_left_yellow=params["header_left_yellow"],
                    header_left_white=params["header_left_white"],
                    header_left_emoji=params["header_left_emoji"],
                    header_right_white=params["header_right_white"],
                    header_right_yellow=params["header_right_yellow"],
                    header_right_emoji=params["header_right_emoji"],
                    hero_cutout_path=cutout_path,
                    evidence_left_img=ev_left_img,
                    evidence_left_text=params["evidence_left_text"],
                    evidence_left_badge=params["evidence_left_badge"],
                    evidence_right_img=ev_right_img,
                    evidence_right_text=params["evidence_right_text"],
                    evidence_right_badge=params["evidence_right_badge"],
                    episode_pill_text=params["episode_pill_text"],
                    brand_logos=params.get("brand_logos"),
                    aspect_ratio="9:16",
                    bg_theme=params.get("bg_theme", "tech_purple"),
                    output_path=str(poster_916_path),
                )
                if poster_916_path.exists():
                    global_poster = OUTPUT_DIR / "thumbnail_916_poster.png"
                    if poster_916_path.resolve() != global_poster.resolve():
                        shutil.copyfile(poster_916_path, global_poster)

            return final_jpg

    except Exception as exc:
        print(f"⚠️ Prasad Tech thumbnail rendering notice: {exc}. Falling back to standard canvas.")

    return create_thumbnail(title=title, aspect_ratio=aspect_ratio, assets_dir=assets_dir, output_dir=output_dir, use_playwright=False)


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
                for m in ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]:
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
                for m in ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]:
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


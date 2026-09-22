from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import re
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
OUTPUT_DIR = ROOT / "output"


def _find_best_background(aspect_ratio="16:9"):
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

    if not ASSETS_DIR.exists():
        return None

    target_ratio = (
        9 / 16 if aspect_ratio == "9:16"
        else (1.0 if aspect_ratio == "1:1" else 16 / 9)
    )

    for path in ASSETS_DIR.iterdir():

        if path.name.lower() in {
            "contact_sheet.jpg",
            "contact_sheet.jpeg",
            "contact_sheet.png",
        }:
            continue

        if path.suffix.lower() not in {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }:
            continue

        try:
            with Image.open(path) as img:

                width, height = img.size

                if width < 300 or height < 300:
                    continue

                aspect = width / height

                # Prefer images close to requested aspect ratio
                ratio_difference = abs(aspect - target_ratio)
                ratio_score = max(0, 60 - (ratio_difference * 35))

                resolution_score = min(
                    (width * height) / 1_000_000,
                    20,
                )

                score = ratio_score + resolution_score

                candidates.append(
                    (score, path)
                )

        except Exception as exc:
            print(
                f"⚠️ Could not inspect {path.name}: {exc}"
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    selected = candidates[0][1]

    print(
        f"🖼️ Thumbnail background selected ({aspect_ratio}): "
        f"{selected.name}"
    )

    return selected


def _load_font(size):
    """
    Find a usable bold font on macOS/Linux/Windows.
    """

    font_paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]

    for path in font_paths:

        if os.path.exists(path):

            try:
                return ImageFont.truetype(
                    path,
                    size,
                )
            except OSError:
                pass

    return ImageFont.load_default()


def _clean_title(title):
    """
    Convert a long video title into a short
    thumbnail-friendly phrase.
    """

    if not title:
        return "LATEST NEWS"

    title = str(title).strip()

    # Remove common punctuation noise.
    title = re.sub(
        r"\s+",
        " ",
        title,
    )

    title = title.strip(
        " .,!?:;-_"
    )

    # Keep the strongest first part.
    words = title.split()

    # Thumbnail text should stay short.
    if len(words) > 8:
        words = words[:8]

    result = " ".join(words)

    return result.upper()


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


def create_thumbnail(title, aspect_ratio="16:9"):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("=" * 60)
    print(f"THUMBNAIL GENERATION ({aspect_ratio})")
    print("=" * 60)

    background_path = _find_best_background(aspect_ratio=aspect_ratio)

    if background_path is None:

        print(
            "❌ No suitable background image found"
        )

        return None

    try:

        image = Image.open(
            background_path
        ).convert("RGB")

    except Exception as exc:

        print(
            f"❌ Failed to open background: {exc}"
        )

        return None

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
        # Centered safe-zone banner for vertical shorts (avoiding top & bottom UI)
        overlay_draw.rectangle(
            (0, 860, canvas_w, 1420),
            fill=(0, 0, 0, 185),
        )
        overlay_draw.rectangle(
            (0, 0, canvas_w, 120),
            fill=(0, 0, 0, 40),
        )
        font_size = 66
        line_height = 80
        target_center_y = 1140
        max_text_width = canvas_w - 140
    elif aspect_ratio == "1:1":
        # Lower-third dark band for square
        overlay_draw.rectangle(
            (0, 680, canvas_w, canvas_h),
            fill=(0, 0, 0, 175),
        )
        overlay_draw.rectangle(
            (0, 0, canvas_w, 90),
            fill=(0, 0, 0, 40),
        )
        font_size = 60
        line_height = 74
        target_center_y = 880
        max_text_width = canvas_w - 120
    else:  # 16:9
        # Bottom dark area
        overlay_draw.rectangle(
            (0, 390, canvas_w, canvas_h),
            fill=(0, 0, 0, 165),
        )
        overlay_draw.rectangle(
            (0, 0, canvas_w, 90),
            fill=(0, 0, 0, 45),
        )
        font_size = 58
        line_height = 68
        target_center_y = 555
        max_text_width = canvas_w - 160

    image = Image.alpha_composite(
        image,
        overlay,
    )

    draw = ImageDraw.Draw(image)

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    thumbnail_title = _clean_title(
        title
    )

    font = _load_font(font_size)

    # Wrap based on pixel width rather than
    # blindly using a fixed word count.
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
            and len(lines) < 3
        ):
            current = test
        else:

            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    lines = lines[:3]

    # --------------------------------------------------------
    # CENTER TITLE VERTICALLY IN TARGET ZONE
    # --------------------------------------------------------

    total_height = (
        len(lines) * line_height
    )

    y = target_center_y - (
        total_height // 2
    )

    for line in lines:

        bbox = draw.textbbox(
            (0, 0),
            line,
            font=font,
            stroke_width=2,
        )

        text_width = (
            bbox[2] - bbox[0]
        )

        x = (
            canvas_w - text_width
        ) // 2

        # Strong shadow
        draw.text(
            (x + 5, y + 5),
            line,
            font=font,
            fill=(0, 0, 0, 220),
            stroke_width=3,
            stroke_fill=(0, 0, 0, 220),
        )

        # Main white text
        draw.text(
            (x, y),
            line,
            font=font,
            fill="white",
            stroke_width=2,
            stroke_fill="black",
        )

        y += line_height

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    output = (
        OUTPUT_DIR /
        "thumbnail.jpg"
    )

    image.convert("RGB").save(
        output,
        "JPEG",
        quality=95,
        optimize=True,
    )

    print(
        f"✅ Thumbnail created ({canvas_w}x{canvas_h}): {output}"
    )

    print(
        f"📝 Thumbnail title: "
        f"{thumbnail_title}"
    )

    print(
        f"🖼️ Background: "
        f"{background_path.name}"
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
                resp = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                return resp.text
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
                resp = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                return resp.text
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


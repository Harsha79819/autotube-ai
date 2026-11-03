"""
AutoTube AI - Full-Frame Typography & Stat Card Generator (agents/typography_card.py)

Generates professional, high-contrast full-frame visual graphic cards:
  - 1080x1920 (9:16 Shorts) or 1920x1080 (16:9 Landscape)
  - Topic-themed aesthetic gradients (Tech, Cinema/Entertainment, Facts/History, Finance)
  - Clean typographic hierarchy with accent badges, quotation styling, and glowing borders
  - Serves as the ultimate Phase 5 fallback rung: 100% relevant, 0% copyright risk,
    and proven to outperform bad/random stock footage on retention.
"""

import os
import re
import math
import textwrap
from pathlib import Path
from typing import Tuple, List, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "fonts"


def _load_font(is_telugu: bool, size: int) -> ImageFont.FreeTypeFont:
    """Loads the highest quality bold font available for Telugu or English."""
    candidates = []
    if is_telugu:
        candidates = [
            FONTS_DIR / "NotoSansTelugu-Bold.ttf",
            FONTS_DIR / "KohinoorTelugu.ttc",
            Path("/System/Library/Fonts/KohinoorTelugu.ttc"),
            FONTS_DIR / "Telugu MN.ttc",
        ]
    else:
        candidates = [
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/System/Library/Fonts/Helvetica.ttc"),
            FONTS_DIR / "NotoSansTelugu-Bold.ttf",
        ]

    for cand in candidates:
        if cand.exists():
            try:
                return ImageFont.truetype(str(cand), size=size)
            except Exception:
                continue

    return ImageFont.load_default()


# Topic theme palettes: (bg_top, bg_bottom, glow, accent, highlight, badge_bg, badge_border, badge_text)
THEMES = {
    "tech": {
        "bg_top": (10, 16, 32),
        "bg_bottom": (18, 30, 58),
        "glow": (0, 180, 255, 60),
        "accent": (0, 229, 255),       # Neon Cyan
        "highlight": (255, 215, 0),    # Gold
        "badge_bg": (0, 80, 140, 200),
        "badge_border": (0, 200, 255),
        "badge_text": "TECH INSIGHT",
    },
    "entertainment": {
        "bg_top": (28, 8, 16),
        "bg_bottom": (50, 15, 28),
        "glow": (255, 45, 85, 55),
        "accent": (255, 215, 0),       # Gold
        "highlight": (255, 59, 48),    # Crimson Red
        "badge_bg": (120, 20, 40, 200),
        "badge_border": (255, 90, 95),
        "badge_text": "CINEMA BUZZ",
    },
    "facts": {
        "bg_top": (12, 22, 24),
        "bg_bottom": (20, 44, 46),
        "glow": (52, 199, 89, 50),
        "accent": (48, 209, 88),       # Neon Green
        "highlight": (255, 214, 10),   # Yellow
        "badge_bg": (20, 80, 50, 200),
        "badge_border": (52, 199, 89),
        "badge_text": "KEY FACT",
    },
    "history": {
        "bg_top": (22, 18, 14),
        "bg_bottom": (42, 34, 26),
        "glow": (212, 160, 23, 50),
        "accent": (230, 180, 80),      # Amber/Parchment
        "highlight": (255, 230, 150),
        "badge_bg": (90, 70, 40, 200),
        "badge_border": (212, 160, 23),
        "badge_text": "HISTORICAL ARCHIVE",
    },
    "finance": {
        "bg_top": (8, 24, 20),
        "bg_bottom": (16, 48, 38),
        "glow": (0, 204, 153, 55),
        "accent": (0, 230, 153),
        "highlight": (255, 215, 0),
        "badge_bg": (15, 90, 60, 200),
        "badge_border": (0, 204, 153),
        "badge_text": "MARKET DATA",
    },
    "general": {
        "bg_top": (16, 18, 28),
        "bg_bottom": (32, 28, 48),
        "glow": (147, 51, 234, 50),
        "accent": (255, 215, 0),       # Gold
        "highlight": (56, 189, 248),   # Sky Blue
        "badge_bg": (60, 30, 90, 200),
        "badge_border": (192, 132, 252),
        "badge_text": "TOPIC HIGHLIGHT",
    },
}


def _matches_any_keyword(text: str, keywords: tuple) -> bool:
    """Checks if any keyword matches the text using regex word boundaries for ASCII tokens."""
    for kw in keywords:
        if " " in kw:
            if kw in text:
                return True
        elif kw.isascii() and kw.isalnum():
            if re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE):
                return True
        else:
            if kw in text:
                return True
    return False


def detect_card_category(topic_category: Optional[str], text: str) -> str:
    """Intelligently detects topic category from metadata and text content."""
    cat_clean = (topic_category or "").strip().lower()
    if cat_clean in THEMES:
        return cat_clean
    if cat_clean in ("cinema", "film", "movie", "roast", "bigg_boss", "bigg boss", "drama"):
        return "entertainment"
    if cat_clean in ("fact", "curiosity", "trivia"):
        return "facts"
    if cat_clean in ("historical", "war", "ancient"):
        return "history"
    if cat_clean in ("crypto", "stocks", "business", "money"):
        return "finance"
    if cat_clean in ("technology", "it", "coding", "software"):
        return "tech"

    combined = f"{cat_clean} {text}".lower()

    ent_keywords = (
        "cinema", "movie", "film", "entertainment", "roast", "bigg boss", "bigg_boss",
        "nagarjuna", "thrigun", "shalini", "temper vamsi", "vamsi", "sanjana", "bharani",
        "housemate", "contestant", "nomination", "elimination", "captaincy", "eviction",
        "బిగ్ బాస్", "నామినేషన్", "ఎలిమినేషన్", "సినిమా", "నటుడు", "హౌస్‌మేట్", "ట్రోల్", "మీమ్"
    )
    if _matches_any_keyword(combined, ent_keywords):
        return "entertainment"

    fact_keywords = ("fact", "curiosity", "weird", "unbelievable", "mystery", "నిజం", "ఆశ్చర్యం")
    if _matches_any_keyword(combined, fact_keywords):
        return "facts"

    hist_keywords = ("history", "ancient", "war", "era", "empire", "king", "చరిత్ర", "పురాతన")
    if _matches_any_keyword(combined, hist_keywords):
        return "history"

    fin_keywords = ("finance", "money", "crypto", "market", "economy", "stock", "డబ్బు", "మార్కెట్")
    if _matches_any_keyword(combined, fin_keywords):
        return "finance"

    tech_keywords = ("tech", "technology", "ai", "software", "hardware", "gadget", "chip", "robot", "సైన్స్", "టెక్")
    if _matches_any_keyword(combined, tech_keywords):
        return "tech"

    return "general"


def get_contextual_badge(category: str, text: str, user_badge: Optional[str] = None) -> str:
    """Generates an engaging, topic-aware headline badge."""
    if user_badge:
        return user_badge.strip().upper()
    t_lower = text.lower()
    if category == "entertainment":
        if _matches_any_keyword(t_lower, ("nomination", "నామినేషన్", "nominate")):
            return "NOMINATION BUZZ"
        if _matches_any_keyword(t_lower, ("elimination", "ఎలిమినేషన్", "eviction")):
            return "ELIMINATION ALERT"
        if _matches_any_keyword(t_lower, ("bigg boss", "బిగ్ బాస్", "housemate")):
            return "BIGG BOSS SPOTLIGHT"
        if _matches_any_keyword(t_lower, ("roast", "troll", "ట్రోల్", "meme")):
            return "VIRAL ROAST"
        if _matches_any_keyword(t_lower, ("fight", "clash", "వార్", "గొడవ")):
            return "DRAMA CLASH"
        return "HOT TOPIC"
    elif category == "facts":
        return "KEY FACT"
    elif category == "history":
        return "HISTORICAL ARCHIVE"
    elif category == "finance":
        return "MARKET INTEL"
    elif category == "tech":
        return "TECH INSIGHT"
    return "TOPIC HIGHLIGHT"



def _create_gradient_background(width: int, height: int, theme: dict) -> Image.Image:
    """Renders a smooth vertical gradient background with a subtle central ambient glow."""
    base = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(base)

    c1 = theme["bg_top"]
    c2 = theme["bg_bottom"]

    # Vertical linear gradient
    for y in range(height):
        ratio = y / max(1, height - 1)
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # Add radial ambient glow in center
    glow_color = theme.get("glow", (0, 180, 255, 50))
    glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)

    cx, cy = width // 2, height // 2
    max_radius = min(width, height) // 2

    # Draw expanding soft circles for radial glow
    for radius in range(max_radius, 0, -25):
        alpha = int(glow_color[3] * (1.0 - (radius / max_radius)) ** 1.5)
        if alpha > 0:
            glow_draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=(glow_color[0], glow_color[1], glow_color[2], alpha),
            )

    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=30))
    base = Image.alpha_composite(base, glow_layer)
    return base


def generate_typography_card(
    headline_text: str,
    output_path: str,
    topic_category: str = "general",
    aspect_ratio: str = "9:16",
    subtext: Optional[str] = None,
    badge_label: Optional[str] = None,
    bg_image_path: Optional[str] = None,
    avatar_image_path: Optional[str] = None,
) -> bool:
    """
    Renders a high-contrast full-frame visual graphic card with active photographic
    backgrounds (e.g. Bigg Boss House interior, living room, cinematic staging) and
    kinetic typography overlay. Never renders an empty plain blue/solid screen.
    """
    try:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        if aspect_ratio == "9:16":
            width, height = 1080, 1920
        elif aspect_ratio == "1:1":
            width, height = 1080, 1080
        else:
            width, height = 1920, 1080

        # Clean text
        clean_headline = headline_text.strip().replace("\n", " ")
        clean_headline = re.sub(r"^[\*\#\>\-\s]+", "", clean_headline)
        clean_headline = re.sub(r'^[“"\'\s]+|[”"\'\s]+$', "", clean_headline)

        if not clean_headline:
            clean_headline = "Key Takeaway"

        is_telugu = bool(re.search(r"[\u0C00-\u0C7F]", clean_headline))

        # Intelligently resolve category theme and contextual badge
        cat = detect_card_category(topic_category, clean_headline)
        theme = THEMES.get(cat, THEMES["general"])

        # ZERO BLANK / PLAIN SCREENS: Always use an active photographic background
        # (e.g. Bigg Boss house interior / living room / studio or fallback photography)
        active_bg_found = False
        cand_bgs = []
        if bg_image_path and Path(bg_image_path).exists():
            cand_bgs.append(Path(bg_image_path))

        # Check for Bigg Boss / show house interior stills
        if cat == "entertainment":
            bb_img = ROOT / "assets" / "entities" / "bigg_boss_telugu" / "image.jpg"
            if bb_img.exists():
                cand_bgs.append(bb_img)


        # Standard fallback photography assets
        fb_dir = ROOT / "assets" / "fallback"
        if fb_dir.exists():
            cand_bgs.extend(sorted(fb_dir.glob("*.jpg")))

        bg = None
        for b_cand in cand_bgs:
            try:
                with Image.open(b_cand) as b_im:
                    b_rgb = b_im.convert("RGB")
                    bw, bh = b_rgb.size
                    scale = max(width / float(bw), height / float(bh))
                    rw, rh = int(bw * scale), int(bh * scale)
                    resized = b_rgb.resize((rw, rh), Image.Resampling.LANCZOS)
                    cx = (rw - width) // 2
                    cy = (rh - height) // 2
                    cropped = resized.crop((cx, cy, cx + width, cy + height))
                    blurred = cropped.filter(ImageFilter.GaussianBlur(radius=18)).convert("RGBA")
                    scrim = Image.new("RGBA", (width, height), (12, 18, 30, 160))
                    bg = Image.alpha_composite(blurred, scrim)
                    active_bg_found = True
                    break
            except Exception:
                continue

        if not active_bg_found or bg is None:
            bg = _create_gradient_background(width, height, theme)

        card_draw = ImageDraw.Draw(bg)

        # --------------------------------------------------------
        # 1. Subtle Framing & Accent Lines
        # --------------------------------------------------------
        margin_x = int(width * 0.08)
        margin_y = int(height * 0.12)
        frame_box = [margin_x, margin_y, width - margin_x, height - margin_y]

        # Subtle card boundary
        card_draw.rounded_rectangle(
            frame_box,
            radius=24,
            outline=(255, 255, 255, 25),
            width=2,
        )

        # Corner accents
        accent_len = 36
        acc = theme["accent"]
        card_draw.line([(margin_x, margin_y), (margin_x + accent_len, margin_y)], fill=acc, width=4)
        card_draw.line([(margin_x, margin_y), (margin_x, margin_y + accent_len)], fill=acc, width=4)
        card_draw.line([(width - margin_x, margin_y), (width - margin_x - accent_len, margin_y)], fill=acc, width=4)
        card_draw.line([(width - margin_x, margin_y), (width - margin_x, margin_y + accent_len)], fill=acc, width=4)
        card_draw.line([(margin_x, height - margin_y), (margin_x + accent_len, height - margin_y)], fill=acc, width=4)
        card_draw.line([(margin_x, height - margin_y), (margin_x, height - margin_y - accent_len)], fill=acc, width=4)
        card_draw.line([(width - margin_x, height - margin_y), (width - margin_x - accent_len, height - margin_y)], fill=acc, width=4)
        card_draw.line([(width - margin_x, height - margin_y), (width - margin_x, height - margin_y - accent_len)], fill=acc, width=4)

        # --------------------------------------------------------
        # 1B. Optional Real Contestant Photo / Avatar (Canva-Style Editorial Frame)
        # --------------------------------------------------------
        avatar_rendered = False
        av_y_bottom = 0
        if avatar_image_path and Path(avatar_image_path).exists() and height > width:
            try:
                av_p = Path(avatar_image_path)
                with Image.open(av_p) as av_raw:
                    av_rgb = av_raw.convert("RGB")
                    av_dim = 460
                    # Center-crop square
                    min_edge = min(av_rgb.size)
                    left = (av_rgb.width - min_edge) // 2
                    top = (av_rgb.height - min_edge) // 2
                    av_sq = av_rgb.crop((left, top, left + min_edge, top + min_edge)).resize((av_dim, av_dim), Image.Resampling.LANCZOS)

                    # Rounded mask
                    mask = Image.new("L", (av_dim, av_dim), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.rounded_rectangle([0, 0, av_dim, av_dim], radius=36, fill=255)

                    av_rgba = av_sq.convert("RGBA")
                    av_rgba.putalpha(mask)

                    av_x = (width - av_dim) // 2
                    av_y = margin_y + int(height * 0.04)
                    av_y_bottom = av_y + av_dim

                    # Outer glow / accent border
                    card_draw.rounded_rectangle(
                        [av_x - 5, av_y - 5, av_x + av_dim + 5, av_y + av_dim + 5],
                        radius=40,
                        outline=theme["accent"],
                        width=5,
                    )
                    bg.paste(av_rgba, (av_x, av_y), av_rgba)
                    avatar_rendered = True
            except Exception as av_err:
                print(f"Notice: avatar compositing error: {av_err}")

        # --------------------------------------------------------
        # 2. Category Pill Badge (Top of Card or Below Avatar)
        # --------------------------------------------------------
        tag = get_contextual_badge(cat, clean_headline, badge_label)
        tag_font = _load_font(is_telugu=False, size=int(height * 0.016))
        try:
            t_bbox = card_draw.textbbox((0, 0), tag, font=tag_font)
            t_w = t_bbox[2] - t_bbox[0]
            t_h = t_bbox[3] - t_bbox[1]
        except Exception:
            t_w, t_h = len(tag) * 12, 24

        badge_pad_x = 24
        badge_pad_y = 10
        if avatar_rendered:
            badge_y = av_y_bottom + 22
        else:
            badge_y = margin_y + int(height * 0.05)
        badge_x0 = (width - t_w - (badge_pad_x * 2)) // 2
        badge_x1 = badge_x0 + t_w + (badge_pad_x * 2)
        badge_y0 = badge_y
        badge_y1 = badge_y + t_h + (badge_pad_y * 2)

        card_draw.rounded_rectangle(
            [badge_x0, badge_y0, badge_x1, badge_y1],
            radius=16,
            fill=theme["badge_bg"],
            outline=theme["badge_border"],
            width=2,
        )
        card_draw.text(
            (badge_x0 + badge_pad_x, badge_y0 + badge_pad_y),
            tag,
            font=tag_font,
            fill=(255, 255, 255, 245),
        )

        # --------------------------------------------------------
        # 3. Main Headline / Stat Typography (Center or Lower Half)
        # --------------------------------------------------------
        # Dynamic font sizing based on length
        char_len = len(clean_headline)
        if aspect_ratio == "9:16":
            base_size = int(height * 0.034) if char_len < 40 else (int(height * 0.028) if char_len < 80 else int(height * 0.024))
            wrap_chars = 18 if is_telugu else 22
            max_lines = 4 if avatar_rendered else 5
        else:
            base_size = int(height * 0.065) if char_len < 40 else (int(height * 0.052) if char_len < 80 else int(height * 0.042))
            wrap_chars = 30 if is_telugu else 36
            max_lines = 4

        main_font = _load_font(is_telugu=is_telugu, size=base_size)
        wrapped_lines = textwrap.wrap(clean_headline, width=wrap_chars)
        if len(wrapped_lines) > max_lines:
            wrapped_lines = wrapped_lines[:max_lines]
            wrapped_lines[-1] = wrapped_lines[-1].rstrip("., ") + "..."

        if avatar_rendered:
            y_text_expr = f"{badge_y1 + 45}"
            y_text_shadow = f"{badge_y1 + 48}"
        else:
            y_text_expr = "(h-text_h)/2"
            y_text_shadow = "(h-text_h)/2+3"

        # HarfBuzz OpenType complex shaping via FFmpeg for Telugu text
        if is_telugu and (FONTS_DIR / "NotoSansTelugu-Bold.ttf").exists():
            import subprocess, tempfile
            final_rgb = Image.new("RGB", (width, height), (0, 0, 0))
            final_rgb.paste(bg, (0, 0), bg)
            tmp_base = out_file.with_name(f"tmp_card_base_{out_file.stem}.png")
            final_rgb.save(str(tmp_base), "PNG")
            try:
                t_font = str((FONTS_DIR / "NotoSansTelugu-Bold.ttf").resolve()).replace(":", "\\:").replace("'", "\\'")
                text_content = "\n".join(wrapped_lines)
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as tf:
                    tf.write(text_content)
                    txt_path = tf.name

                esc_txt = txt_path.replace(":", "\\:").replace("'", "\\'")
                vf = (
                    f"drawtext=fontfile='{t_font}':textfile='{esc_txt}':fontsize={base_size}:fontcolor=black@0.9:"
                    f"line_spacing=22:x=(w-text_w)/2+3:y={y_text_shadow},"
                    f"drawtext=fontfile='{t_font}':textfile='{esc_txt}':fontsize={base_size}:fontcolor=white:"
                    f"line_spacing=22:x=(w-text_w)/2:y={y_text_expr}"
                )
                if subtext:
                    clean_sub = subtext.strip()[:60]
                    sub_y = height - margin_y - int(height * 0.04) if avatar_rendered else margin_y + int(height * 0.72)
                    vf += (
                        f",drawtext=fontfile='{t_font}':text='{clean_sub}':fontsize={int(height * 0.018)}:"
                        f"fontcolor=0xB4C8DC:x=(w-text_w)/2:y={sub_y}"
                    )

                cmd = ["ffmpeg", "-y", "-i", str(tmp_base), "-vf", vf, "-frames:v", "1", "-q:v", "2", str(out_file)]
                r = subprocess.run(cmd, capture_output=True, text=True)
                if r.returncode == 0 and out_file.exists():
                    tmp_base.unlink(missing_ok=True)
                    if os.path.exists(txt_path):
                        os.unlink(txt_path)
                    print(f"✅ Generated Phase 5 Typography Card (HarfBuzz Telugu): {output_path}")
                    return True
            except Exception as hb_card_err:
                print(f"Typography card HarfBuzz note: {hb_card_err}")
            finally:
                tmp_base.unlink(missing_ok=True)
                if "txt_path" in locals() and os.path.exists(txt_path):
                    os.unlink(txt_path)

        line_bboxes = []
        total_text_h = 0
        for line in wrapped_lines:
            try:
                bb = card_draw.textbbox((0, 0), line, font=main_font)
                lw = bb[2] - bb[0]
                lh = bb[3] - bb[1]
            except Exception:
                lw = len(line) * (base_size // 2)
                lh = base_size + 10
            line_bboxes.append((lw, lh))
            total_text_h += lh + 14

        # Center text block vertically or under avatar
        start_y = badge_y1 + 45 if avatar_rendered else (height - total_text_h) // 2

        # Draw each line with drop shadow & color hierarchy
        curr_y = start_y
        for idx, (line, (lw, lh)) in enumerate(zip(wrapped_lines, line_bboxes)):
            line_x = (width - lw) // 2

            # Drop shadow
            card_draw.text(
                (line_x + 3, curr_y + 3),
                line,
                font=main_font,
                fill=(0, 0, 0, 180),
            )

            # Highlight first or last line with accent color
            if idx == 0 and len(wrapped_lines) > 1:
                fill_color = theme["highlight"]
            elif idx == len(wrapped_lines) - 1:
                fill_color = theme["accent"]
            else:
                fill_color = (255, 255, 255, 250)

            card_draw.text(
                (line_x, curr_y),
                line,
                font=main_font,
                fill=fill_color,
            )
            curr_y += lh + 14

        # --------------------------------------------------------
        # 4. Optional Subtext / Source Attribution (Bottom of Card)
        # --------------------------------------------------------
        if subtext:
            clean_sub = subtext.strip()[:60]
            sub_font = _load_font(is_telugu=is_telugu, size=int(height * 0.018))
            try:
                s_bb = card_draw.textbbox((0, 0), clean_sub, font=sub_font)
                sw = s_bb[2] - s_bb[0]
                sh = s_bb[3] - s_bb[1]
            except Exception:
                sw, sh = len(clean_sub) * 10, 20

            sub_y = margin_y + int(height * 0.72)
            sub_x = (width - sw) // 2
            card_draw.text((sub_x, sub_y), clean_sub, font=sub_font, fill=(180, 200, 220, 220))

        # Convert RGBA to high-quality RGB JPEG
        final_rgb = Image.new("RGB", (width, height), (0, 0, 0))
        final_rgb.paste(bg, (0, 0), bg)
        final_rgb.save(out_file, "JPEG", quality=95)

        print(f"✅ Generated Phase 5 Typography Card ({aspect_ratio}, {topic_category}): {output_path}")
        return True

    except Exception as e:
        print(f"⚠️ Error generating typography card: {e}")
        return False

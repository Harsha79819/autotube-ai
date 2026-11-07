"""
AutoTube AI - Frame 0 Hook Text Overlay Card Generator (agents/hook_card.py)

Creates high-contrast, modern graphic overlay cards with large bold typography
and rounded glassmorphic background pills. Rendered to transparent RGBA PNG
and burned onto Frame 0 for the first ~2 seconds of YouTube Shorts.

Positioned in the upper third (y ~ 18-22%) to ensure zero collision with:
  - YouTube Shorts right-side interactive buttons (like/share/comments)
  - Bottom-third subtitles / captions
  - Channel name / sound title bar at very bottom
"""

import os
import re
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "fonts"


def _load_font(is_telugu: bool, size: int) -> ImageFont.FreeTypeFont:
    """Load the best available bold font for Telugu or English."""
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


def generate_hook_card(
    hook_text: str,
    output_path: str = "output/hook_overlay.png",
    width: int = 1080,
    height: int = 1920,
    tag_label: str = "",
) -> str:
    """
    Renders an eye-catching hook overlay card on a transparent RGBA canvas.
    Designed for 9:16 Shorts frame-0 hook impact.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    clean_hook = hook_text.strip().replace("\n", " ")
    # Clean any accidental quotes
    clean_hook = re.sub(r'^["\'\s]+|["\'\s]+$', '', clean_hook)

    is_telugu = bool(re.search(r"[\u0C00-\u0C7F]", clean_hook))

    # Base RGBA canvas (100% transparent)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Determine font size and text wrap based on length
    font_size = 54 if len(clean_hook) < 45 else (46 if len(clean_hook) < 75 else 40)
    hook_font = _load_font(is_telugu=is_telugu, size=font_size)
    tag_font = _load_font(is_telugu=False, size=24)

    # Wrap text cleanly across 2-3 lines max
    wrap_width = 24 if is_telugu else 28
    wrapped_lines = textwrap.wrap(clean_hook, width=wrap_width)
    if len(wrapped_lines) > 3:
        # Condense into 3 lines max
        wrapped_lines = wrapped_lines[:3]
        wrapped_lines[2] = wrapped_lines[2].rstrip(".") + "..."

    # Badge tag dimensions (only if tag_label is explicitly passed)
    clean_tag = tag_label.replace("⚡", "").strip() if tag_label else ""
    if clean_tag:
        try:
            tag_bbox = draw.textbbox((0, 0), clean_tag, font=tag_font)
            tag_w = tag_bbox[2] - tag_bbox[0] + 32
            tag_h = tag_bbox[3] - tag_bbox[1] + 16
        except Exception:
            tag_w = 200
            tag_h = 36
    else:
        tag_w = 0
        tag_h = 0

    # Calculate text bounding boxes
    line_heights = []
    line_widths = []
    for line in wrapped_lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=hook_font)
            line_widths.append(bbox[2] - bbox[0])
            lh = int(font_size * 1.4) if is_telugu else (bbox[3] - bbox[1])
            line_heights.append(lh)
        except Exception:
            line_widths.append(len(line) * (font_size // 2))
            line_heights.append(int(font_size * 1.4))

    max_line_w = max(line_widths) if line_widths else 400
    line_spacing = 16 if is_telugu else 14
    total_text_h = sum(line_heights) + (line_spacing * (len(wrapped_lines) - 1))

    # Card dimensions with generous padding
    pad_x = 50
    pad_y = 36 if is_telugu else 30
    extra_tag_h = (tag_h + 16) if clean_tag else 0
    card_w = min(width - 120, max(max_line_w + (pad_x * 2), tag_w + 60))
    card_h = total_text_h + extra_tag_h + (pad_y * 2) + (10 if is_telugu else 0)

    # Upper third positioning (centered horizontally, y at ~19% of height)
    card_x = (width - card_w) // 2
    card_y = int(height * 0.18)

    # 1. Outer subtle glow / shadow
    shadow_card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_card)
    s_draw.rounded_rectangle(
        [card_x - 4, card_y - 4, card_x + card_w + 4, card_y + card_h + 4],
        radius=32,
        fill=(0, 0, 0, 160),
    )
    canvas = Image.alpha_composite(canvas, shadow_card)
    draw = ImageDraw.Draw(canvas)

    # 2. Main pill card background (deep rich obsidian with subtle transparency)
    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=28,
        fill=(12, 14, 20, 235),
        outline=(255, 215, 0, 220),  # Radiant gold viral accent border
        width=4,
    )

    # 3. Pill Tag Badge (top-left inside card - ONLY if clean_tag is present)
    if clean_tag:
        tag_x = card_x + pad_x
        tag_y = card_y + 20
        draw.rounded_rectangle(
            [tag_x, tag_y, tag_x + tag_w, tag_y + tag_h],
            radius=14,
            fill=(255, 215, 0, 255),  # Vibrant gold
        )
        draw.text(
            (tag_x + 16, tag_y + 8),
            clean_tag,
            font=tag_font,
            fill=(10, 10, 10, 255),
        )
        start_text_y = tag_y + tag_h + 16
    else:
        start_text_y = card_y + pad_y

    # 4. Spoken Hook Text (HarfBuzz OpenType shaping for Telugu, PIL for Latin)
    if is_telugu and (FONTS_DIR / "NotoSansTelugu-Bold.ttf").exists():
        import subprocess, tempfile
        tmp_base = out_file.with_name(f"tmp_base_{out_file.stem}.png")
        canvas.save(str(tmp_base), "PNG")
        try:
            t_font = str((FONTS_DIR / "NotoSansTelugu-Bold.ttf").resolve()).replace(":", "\\:").replace("'", "\\'")
            text_content = "\n".join(wrapped_lines)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as tf:
                tf.write(text_content)
                txt_path = tf.name

            esc_txt = txt_path.replace(":", "\\:").replace("'", "\\'")
            text_y = start_text_y
            vf = (
                f"drawtext=fontfile='{t_font}':textfile='{esc_txt}':fontsize={font_size}:fontcolor=black@0.9:"
                f"line_spacing={line_spacing}:x=(w-text_w)/2+2:y={text_y}+2,"
                f"drawtext=fontfile='{t_font}':textfile='{esc_txt}':fontsize={font_size}:fontcolor=white:"
                f"line_spacing={line_spacing}:x=(w-text_w)/2:y={text_y}"
            )
            cmd = ["ffmpeg", "-y", "-i", str(tmp_base), "-vf", vf, "-frames:v", "1", str(out_file)]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0 and out_file.exists():
                tmp_base.unlink(missing_ok=True)
                if os.path.exists(txt_path):
                    os.unlink(txt_path)
                print(f"✅ Generated Frame-0 Hook Overlay (Telugu): {out_file} ({card_w}x{card_h}px)")
                return str(out_file)
        except Exception as hb_err:
            print(f"Hook card HarfBuzz note: {hb_err}")
        finally:
            tmp_base.unlink(missing_ok=True)
            if "txt_path" in locals() and os.path.exists(txt_path):
                os.unlink(txt_path)

    curr_y = start_text_y
    for idx, (line, l_w, l_h) in enumerate(zip(wrapped_lines, line_widths, line_heights)):
        # Center each line horizontally within the card
        text_x = card_x + ((card_w - l_w) // 2)

        # Draw crisp dark drop shadow behind text
        draw.text((text_x + 2, curr_y + 2), line, font=hook_font, fill=(0, 0, 0, 220))

        # First line is bright white; subsequent lines or key punch lines can use warm highlight
        text_color = (255, 255, 255, 255) if idx == 0 else (255, 245, 180, 255)
        draw.text((text_x, curr_y), line, font=hook_font, fill=text_color)
        curr_y += l_h + line_spacing

    canvas.save(str(out_file), "PNG")
    print(f"✅ Generated Frame-0 Viral Hook Overlay: {out_file} ({card_w}x{card_h}px)")
    return str(out_file)


if __name__ == "__main__":
    generate_hook_card(
        "శాంసంగ్ గెలాక్సీ ఎస్ 27 లో ఈ బిగ్గెస్ట్ ప్రాబ్లమ్ నిజంగా ఫిక్స్ చేశారా?",
        output_path="output/test_hook_overlay.png",
    )

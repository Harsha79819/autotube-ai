"""
AutoTube AI — Outro Asset Generator
Generates a 5-second 1080x1920 30FPS Sci-Fi HUD glassmorphic 'Like/Subscribe/Share/Comment'
outro clip with synchronized stereo audio chime.
Outputs:
  - assets/outro/like_subscribe_share_comment.mp4
  - assets/outro/like_share_subscribe.mp4 (symlinked/copied for backward compatibility)
"""

import os
import math
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION_SEC = 5.0
TOTAL_FRAMES = int(FPS * DURATION_SEC)

OUTPUT_DIR = Path("assets/outro")
OUTPUT_PATH = OUTPUT_DIR / "like_subscribe_share_comment.mp4"
LEGACY_PATH = OUTPUT_DIR / "like_share_subscribe.mp4"


def get_font(size: int, bold: bool = True):
    font_paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "fonts/NotoSansTelugu-Bold.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_base_background():
    """Generates the dark sci-fi HUD gradient background."""
    bg = Image.new("RGBA", (WIDTH, HEIGHT), (10, 14, 23, 255))
    draw = ImageDraw.Draw(bg)

    # Subtle radial center glow
    cx, cy = WIDTH // 2, HEIGHT // 2
    for r in range(500, 50, -50):
        alpha = int(18 * (1.0 - r / 500))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(26, 36, 54, alpha))

    # Subtle grid accent lines
    for y in range(200, HEIGHT, 160):
        draw.line([(60, y), (WIDTH - 60, y)], fill=(255, 255, 255, 6), width=1)
    for x in range(120, WIDTH, 160):
        draw.line([(x, 300), (x, HEIGHT - 300)], fill=(255, 255, 255, 6), width=1)

    return bg


def render_frame(frame_idx: int, base_bg: Image.Image) -> Image.Image:
    """Render a single frame of the 5-second outro animation with 4 actions: Like, Comment, Share, Subscribe."""
    frame = base_bg.copy()
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Glass Card Dimensions
    card_x1, card_y1 = 80, 500
    card_x2, card_y2 = WIDTH - 80, 1420
    card_w = card_x2 - card_x1

    # Outer Glass Card Fill
    draw.rounded_rectangle(
        [card_x1, card_y1, card_x2, card_y2],
        radius=44,
        fill=(18, 24, 38, 225),
        outline=(255, 255, 255, 32),
        width=2,
    )

    # Top Glowing Pill Badge: "✦ THANKS FOR WATCHING ✦"
    badge_w, badge_h = 440, 54
    badge_x = card_x1 + (card_w - badge_w) // 2
    badge_y = card_y1 + 45
    draw.rounded_rectangle(
        [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
        radius=27,
        fill=(255, 106, 44, 35),
        outline=(255, 106, 44, 190),
        width=2,
    )
    font_badge = get_font(22, bold=True)
    draw.text(
        (badge_x + 40, badge_y + 14),
        "✦ THANKS FOR WATCHING ✦",
        fill=(255, 149, 88, 255),
        font=font_badge,
    )

    # Main Headline
    font_title = get_font(46, bold=True)
    title_text = "ENJOYED THIS BREAKDOWN?"
    title_bbox = font_title.getbbox(title_text)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(
        (card_x1 + (card_w - title_w) // 2, card_y1 + 130),
        title_text,
        fill=(255, 255, 255, 255),
        font=font_title,
    )

    # Sub-text (Bilingual Telugu / English community prompt)
    font_sub = get_font(26, bold=False)
    sub_text = "మీ అభిప్రాయాన్ని క్రింద కామెంట్ చేయండి!"
    sub_bbox = font_sub.getbbox(sub_text)
    sub_w = sub_bbox[2] - sub_bbox[0]
    draw.text(
        (card_x1 + (card_w - sub_w) // 2, card_y1 + 205),
        sub_text,
        fill=(148, 163, 184, 240),
        font=font_sub,
    )

    # Pulse calculation for animated elements across the 5 seconds (150 frames)
    pulse = 0.5 + 0.5 * math.sin((frame_idx / TOTAL_FRAMES) * 4 * math.pi)

    # ----------------------------------------------------
    # 2x2 Grid of Actions: LIKE, COMMENT, SHARE, SUBSCRIBE
    # ----------------------------------------------------
    grid_y = card_y1 + 280
    pill_w = 410
    pill_h = 95
    col_gap = 40
    row_gap = 30
    total_grid_w = pill_w * 2 + col_gap
    start_grid_x = card_x1 + (card_w - total_grid_w) // 2

    font_btn = get_font(28, bold=True)
    font_tel = get_font(20, bold=False)

    # 1. LIKE Button (Col 0, Row 0)
    b1_x = start_grid_x
    b1_y = grid_y
    draw.rounded_rectangle(
        [b1_x, b1_y, b1_x + pill_w, b1_y + pill_h],
        radius=26,
        fill=(26, 36, 56, 200),
        outline=(45, 212, 191, 160),
        width=2,
    )
    draw.text((b1_x + 35, b1_y + 18), "👍  LIKE", fill=(45, 212, 191, 255), font=font_btn)
    draw.text((b1_x + 40, b1_y + 56), "లైక్ కొట్టండి", fill=(148, 163, 184, 220), font=font_tel)

    # 2. COMMENT Button (Col 1, Row 0)
    b2_x = start_grid_x + pill_w + col_gap
    b2_y = grid_y
    draw.rounded_rectangle(
        [b2_x, b2_y, b2_x + pill_w, b2_y + pill_h],
        radius=26,
        fill=(26, 36, 56, 200),
        outline=(168, 85, 247, 160),
        width=2,
    )
    draw.text((b2_x + 30, b2_y + 18), "💬  COMMENT", fill=(192, 132, 252, 255), font=font_btn)
    draw.text((b2_x + 35, b2_y + 56), "కామెంట్ చేయండి", fill=(148, 163, 184, 220), font=font_tel)

    # 3. SHARE Button (Col 0, Row 1)
    b3_x = start_grid_x
    b3_y = grid_y + pill_h + row_gap
    draw.rounded_rectangle(
        [b3_x, b3_y, b3_x + pill_w, b3_y + pill_h],
        radius=26,
        fill=(26, 36, 56, 200),
        outline=(56, 189, 248, 160),
        width=2,
    )
    draw.text((b3_x + 35, b3_y + 18), "🔁  SHARE", fill=(56, 189, 248, 255), font=font_btn)
    draw.text((b3_x + 40, b3_y + 56), "షేర్ చేయండి", fill=(148, 163, 184, 220), font=font_tel)

    # 4. SUBSCRIBE Button (Col 1, Row 1) — Animated Pulsing Glow
    b4_x = start_grid_x + pill_w + col_gap
    b4_y = grid_y + pill_h + row_gap
    sub_glow_pad = int(4 + 6 * pulse)
    draw.rounded_rectangle(
        [b4_x - sub_glow_pad, b4_y - sub_glow_pad, b4_x + pill_w + sub_glow_pad, b4_y + pill_h + sub_glow_pad],
        radius=26 + sub_glow_pad // 2,
        fill=(255, 106, 44, int(45 * pulse)),
    )
    draw.rounded_rectangle(
        [b4_x, b4_y, b4_x + pill_w, b4_y + pill_h],
        radius=26,
        fill=(255, 106, 44, 255),
        outline=(255, 175, 120, int(160 + 90 * pulse)),
        width=2,
    )
    draw.text((b4_x + 30, b4_y + 18), "🔔  SUBSCRIBE", fill=(255, 255, 255, 255), font=font_btn)
    draw.text((b4_x + 35, b4_y + 56), "సబ్‌స్క్రైబ్ చేసుకోండి", fill=(255, 237, 213, 240), font=font_tel)

    # Big Banner Callout below 2x2 grid
    sub_banner_y = b3_y + pill_h + 40
    sub_banner_w = total_grid_w
    sub_banner_h = 90
    draw.rounded_rectangle(
        [start_grid_x, sub_banner_y, start_grid_x + sub_banner_w, sub_banner_y + sub_banner_h],
        radius=24,
        fill=(30, 41, 59, 160),
        outline=(255, 255, 255, 25),
        width=1,
    )
    font_callout = get_font(26, bold=True)
    callout_txt = "❤️ LIKE • SHARE • COMMENT • SUBSCRIBE ❤️"
    c_bbox = font_callout.getbbox(callout_txt)
    c_w = c_bbox[2] - c_bbox[0]
    draw.text(
        (start_grid_x + (sub_banner_w - c_w) // 2, sub_banner_y + 30),
        callout_txt,
        fill=(255, 215, 0, 255),
        font=font_callout,
    )

    # Bottom Bell Hint
    font_hint = get_font(22, bold=False)
    hint_text = "Tap the bell icon so you never miss an upload!"
    hint_bbox = font_hint.getbbox(hint_text)
    hint_w = hint_bbox[2] - hint_bbox[0]
    draw.text(
        (card_x1 + (card_w - hint_w) // 2, card_y2 - 65),
        hint_text,
        fill=(148, 163, 184, 210),
        font=font_hint,
    )

    # Composite overlay onto base
    frame = Image.alpha_composite(frame, overlay)
    return frame.convert("RGB")


def generate_outro_clip():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"🎬 Generating 5.0-second 1080x1920 Outro clip ({TOTAL_FRAMES} frames @ {FPS}fps) with LIKE, SUBSCRIBE, SHARE, COMMENT...")

    base_bg = render_base_background()

    # 5-second stereo chime chord with smooth harmonic decay
    audio_expr = (
        "0.18*sin(2*PI*523.25*t)*exp(-0.8*t) + "
        "0.14*sin(2*PI*659.25*t)*exp(-0.7*t) + "
        "0.12*sin(2*PI*783.99*t)*exp(-0.6*t) + "
        "0.10*sin(2*PI*1046.50*t)*exp(-0.5*t)"
    )

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "-",  # Video input from stdin (input 0)
        "-f", "lavfi",
        "-i", f"aevalsrc=exprs={audio_expr}|{audio_expr}:s=48000:c=stereo:d=5.0",  # Audio synth (input 1, stereo)
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(DURATION_SEC),
        str(OUTPUT_PATH),
    ]

    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    try:
        for i in range(TOTAL_FRAMES):
            frame = render_frame(i, base_bg)
            proc.stdin.write(frame.tobytes())
        stdout, stderr = proc.communicate()
    except Exception as e:
        stdout, stderr = proc.communicate()
        print(f"Subprocess communication exception: {e}")

    if proc.returncode == 0 and OUTPUT_PATH.exists() and OUTPUT_PATH.stat().st_size > 1000:
        print(f"✅ Outro clip generated successfully: {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)")
        # Copy to legacy path for seamless backward compatibility
        try:
            shutil.copyfile(OUTPUT_PATH, LEGACY_PATH)
            print(f"✅ Mirrored to legacy path: {LEGACY_PATH}")
        except Exception as ce:
            print(f"Notice mirroring outro: {ce}")
        return str(OUTPUT_PATH)
    else:
        print(f"❌ Failed to generate outro clip:\n{stderr.decode('utf-8', errors='ignore')}")
        return None


if __name__ == "__main__":
    generate_outro_clip()


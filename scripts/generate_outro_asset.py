"""
AutoTube AI — Outro Asset Generator
Generates a 2-second 1080x1920 30FPS Sci-Fi HUD glassmorphic 'Like/Share/Subscribe'
outro clip with synchronized stereo audio chime for Section 11 of the upgrade spec.
Output: assets/outro/like_share_subscribe.mp4
"""

import os
import math
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION_SEC = 2.0
TOTAL_FRAMES = int(FPS * DURATION_SEC)

OUTPUT_DIR = Path("assets/outro")
OUTPUT_PATH = OUTPUT_DIR / "like_share_subscribe.mp4"


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
        alpha = int(14 * (1.0 - r / 500))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(26, 36, 54, alpha))

    # Subtle grid accent lines
    for y in range(200, HEIGHT, 160):
        draw.line([(60, y), (WIDTH - 60, y)], fill=(255, 255, 255, 6), width=1)
    for x in range(120, WIDTH, 160):
        draw.line([(x, 300), (x, HEIGHT - 300)], fill=(255, 255, 255, 6), width=1)

    return bg


def render_frame(frame_idx: int, base_bg: Image.Image) -> Image.Image:
    """Render a single frame of the 2-second outro animation."""
    frame = base_bg.copy()
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Glass Card Dimensions
    card_x1, card_y1 = 100, 580
    card_x2, card_y2 = WIDTH - 100, 1340
    card_w = card_x2 - card_x1

    # Outer Glass Card Fill
    draw.rounded_rectangle(
        [card_x1, card_y1, card_x2, card_y2],
        radius=40,
        fill=(18, 24, 38, 220),
        outline=(255, 255, 255, 28),
        width=2,
    )

    # Top Glowing Pill Badge: "✦ THANKS FOR WATCHING ✦"
    badge_w, badge_h = 420, 52
    badge_x = card_x1 + (card_w - badge_w) // 2
    badge_y = card_y1 + 55
    draw.rounded_rectangle(
        [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
        radius=26,
        fill=(255, 106, 44, 35),
        outline=(255, 106, 44, 180),
        width=2,
    )
    font_badge = get_font(22, bold=True)
    draw.text(
        (badge_x + 36, badge_y + 14),
        "✦ THANKS FOR WATCHING ✦",
        fill=(255, 149, 88, 255),
        font=font_badge,
    )

    # Main Headline: "LIKE • SHARE • SUBSCRIBE"
    font_title = get_font(52, bold=True)
    title_text = "ENJOYED THIS VIDEO?"
    title_bbox = font_title.getbbox(title_text)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(
        (card_x1 + (card_w - title_w) // 2, card_y1 + 145),
        title_text,
        fill=(255, 255, 255, 255),
        font=font_title,
    )

    # Sub-text
    font_sub = get_font(28, bold=False)
    sub_text = "Support the channel for more daily updates!"
    sub_bbox = font_sub.getbbox(sub_text)
    sub_w = sub_bbox[2] - sub_bbox[0]
    draw.text(
        (card_x1 + (card_w - sub_w) // 2, card_y1 + 225),
        sub_text,
        fill=(148, 163, 184, 240),
        font=font_sub,
    )

    # Action Pills: LIKE and SHARE
    pill_w = 340
    pill_h = 80
    gap = 40
    total_pills_w = pill_w * 2 + gap
    start_pills_x = card_x1 + (card_w - total_pills_w) // 2
    pills_y = card_y1 + 310

    # LIKE Pill
    draw.rounded_rectangle(
        [start_pills_x, pills_y, start_pills_x + pill_w, pills_y + pill_h],
        radius=24,
        fill=(30, 38, 56, 180),
        outline=(45, 212, 191, 140),
        width=2,
    )
    font_btn = get_font(30, bold=True)
    draw.text(
        (start_pills_x + 95, pills_y + 22),
        "👍  LIKE",
        fill=(45, 212, 191, 255),
        font=font_btn,
    )

    # SHARE Pill
    share_x = start_pills_x + pill_w + gap
    draw.rounded_rectangle(
        [share_x, pills_y, share_x + pill_w, pills_y + pill_h],
        radius=24,
        fill=(30, 38, 56, 180),
        outline=(255, 255, 255, 45),
        width=2,
    )
    draw.text(
        (share_x + 85, pills_y + 22),
        "🔁  SHARE",
        fill=(226, 232, 240, 240),
        font=font_btn,
    )

    # SUBSCRIBE Glow Button (Pulse animation across frames)
    pulse = 0.5 + 0.5 * math.sin((frame_idx / TOTAL_FRAMES) * 2 * math.pi)
    glow_alpha = int(140 + 100 * pulse)

    sub_btn_w = 720
    sub_btn_h = 105
    sub_btn_x = card_x1 + (card_w - sub_btn_w) // 2
    sub_btn_y = card_y1 + 440

    # Outer glow layer for Subscribe button
    glow_pad = int(6 + 8 * pulse)
    draw.rounded_rectangle(
        [
            sub_btn_x - glow_pad,
            sub_btn_y - glow_pad,
            sub_btn_x + sub_btn_w + glow_pad,
            sub_btn_y + sub_btn_h + glow_pad,
        ],
        radius=30 + glow_pad // 2,
        fill=(255, 106, 44, int(45 * pulse)),
    )

    # Main Subscribe Button (Neon Orange Fill)
    draw.rounded_rectangle(
        [sub_btn_x, sub_btn_y, sub_btn_x + sub_btn_w, sub_btn_y + sub_btn_h],
        radius=28,
        fill=(255, 106, 44, 255),
        outline=(255, 165, 110, glow_alpha),
        width=3,
    )

    font_sub_btn = get_font(38, bold=True)
    sub_btn_label = "🔔  SUBSCRIBE NOW"
    sub_lbl_bbox = font_sub_btn.getbbox(sub_btn_label)
    sub_lbl_w = sub_lbl_bbox[2] - sub_lbl_bbox[0]
    draw.text(
        (sub_btn_x + (sub_btn_w - sub_lbl_w) // 2, sub_btn_y + 28),
        sub_btn_label,
        fill=(255, 255, 255, 255),
        font=font_sub_btn,
    )

    # Bottom Bell Hint
    font_hint = get_font(24, bold=False)
    hint_text = "Tap the bell icon so you never miss an upload!"
    hint_bbox = font_hint.getbbox(hint_text)
    hint_w = hint_bbox[2] - hint_bbox[0]
    draw.text(
        (card_x1 + (card_w - hint_w) // 2, card_y1 + 610),
        hint_text,
        fill=(148, 163, 184, 200),
        font=font_hint,
    )

    # Composite overlay onto base
    frame = Image.alpha_composite(frame, overlay)
    return frame.convert("RGB")


def generate_outro_clip():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"🎬 Generating 2-second Glassmorphic Outro clip ({TOTAL_FRAMES} frames, 1080x1920 @ 30fps)...")

    base_bg = render_base_background()

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "-",  # Video input from stdin
        "-f", "lavfi",
        # 2-second stereo chime with gentle harmonic decay (C5 523Hz + E5 659Hz + G5 784Hz)
        "-i", "aevalsrc=exprs='(0.18*sin(2*PI*523.25*t)*exp(-2.2*t) + 0.14*sin(2*PI*659.25*t)*exp(-1.8*t) + 0.12*sin(2*PI*783.99*t)*exp(-1.5*t))':s=48000:d=2.0",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(DURATION_SEC),
        str(OUTPUT_PATH),
    ]

    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    for i in range(TOTAL_FRAMES):
        frame = render_frame(i, base_bg)
        proc.stdin.write(frame.tobytes())

    stdout, stderr = proc.communicate()

    if proc.returncode == 0 and OUTPUT_PATH.exists() and OUTPUT_PATH.stat().st_size > 1000:
        print(f"✅ Outro clip generated successfully: {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)")
        return str(OUTPUT_PATH)
    else:
        print(f"❌ Failed to generate outro clip:\n{stderr.decode('utf-8', errors='ignore')}")
        return None


if __name__ == "__main__":
    generate_outro_clip()

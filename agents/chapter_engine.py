"""
AutoTube AI - Chapter Engine (agents/chapter_engine.py)

Dedicated engine for Long-Format (16:9 / 3 to 8+ minutes) video production:
1. Renders high-production 1920x1080 Chapter Bumper Cards / Title Slates (Pillow + HarfBuzz Telugu shaping).
2. Converts bumper slates into smooth 2.5s-3.0s MP4 clips with cinematic fade-in/fade-out transitions.
3. Parses 3-Act documentary structures and section markers into compliant chapter schedules.
4. Generates YouTube-compliant SEO clickable timestamp blocks.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import textwrap
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from PIL import Image, ImageDraw, ImageFont, ImageFilter, features

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "fonts"
OUTPUT_DIR = ROOT / "output"

HAS_RAQM = features.check("raqm") and os.environ.get("AUTOTUBE_FORCE_LIBASS") != "1"

TELUGU_FONTS = [
    FONTS_DIR / "NotoSansTelugu-Bold.ttf",
    FONTS_DIR / "KohinoorTelugu.ttc",
    Path("/System/Library/Fonts/Supplemental/KohinoorTelugu.ttc"),
    FONTS_DIR / "Telugu MN.ttc",
]

ENGLISH_FONTS = [
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/System/Library/Fonts/Helvetica.ttc"),
    FONTS_DIR / "NotoSansTelugu-Bold.ttf",
]


def _load_font(is_telugu: bool, size: int) -> ImageFont.FreeTypeFont:
    """Loads appropriate bold font with HarfBuzz shaping if Raqm is present."""
    candidates = TELUGU_FONTS if is_telugu else ENGLISH_FONTS
    engine = ImageFont.Layout.RAQM if HAS_RAQM else ImageFont.Layout.BASIC

    for cand in candidates:
        if cand.exists():
            try:
                return ImageFont.truetype(str(cand), size=size, layout_engine=engine)
            except Exception:
                continue
    return ImageFont.load_default()


def _is_telugu_text(text: str) -> bool:
    return bool(re.search(r"[ఀ-౿]", str(text or "")))


def _format_time_hhmmss(seconds: float) -> str:
    """Formats seconds into MM:SS or HH:MM:SS format."""
    total_sec = max(0, int(round(seconds)))
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def render_chapter_bumper(
    chapter_num: int,
    title: str,
    subtitle: str = "",
    category: str = "general",
    width: int = 1920,
    height: int = 1080,
    output_path: Optional[str] = None,
) -> str:
    """
    Renders a 1920x1080 studio-grade Chapter Bumper Card (Title Slate).
    """
    if output_path is None:
        bumpers_dir = OUTPUT_DIR / "chapter_bumpers"
        bumpers_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(bumpers_dir / f"chapter_{chapter_num:02d}.png")

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    is_telugu = _is_telugu_text(f"{title} {subtitle}")

    cat_lower = str(category or "").lower()
    if any(k in cat_lower for k in ("tech", "gadget", "cyber", "ai")):
        bg_top, bg_bottom = (8, 14, 28), (14, 26, 48)
        accent = (0, 229, 255)
        badge_bg = (0, 80, 140, 220)
        badge_border = (0, 210, 255)
    elif any(k in cat_lower for k in ("cinema", "movie", "entertainment", "roast", "bigg boss")):
        bg_top, bg_bottom = (26, 8, 14), (45, 12, 22)
        accent = (255, 215, 0)
        badge_bg = (110, 20, 36, 220)
        badge_border = (255, 190, 40)
    elif any(k in cat_lower for k in ("facts", "science", "space", "nature")):
        bg_top, bg_bottom = (10, 20, 24), (16, 38, 42)
        accent = (52, 211, 153)
        badge_bg = (18, 70, 52, 220)
        badge_border = (52, 211, 153)
    else:
        bg_top, bg_bottom = (12, 16, 24), (22, 28, 40)
        accent = (255, 193, 7)
        badge_bg = (90, 65, 15, 220)
        badge_border = (255, 215, 64)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    for y in range(height):
        factor = y / height
        r = int(bg_top[0] * (1 - factor) + bg_bottom[0] * factor)
        g = int(bg_top[1] * (1 - factor) + bg_bottom[1] * factor)
        b = int(bg_top[2] * (1 - factor) + bg_bottom[2] * factor)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    mask = Image.radial_gradient("L").resize((width, height), Image.BICUBIC)
    mask = mask.point(lambda v: int(max(0, v - 80) * 0.75))
    vignette = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    img.paste(vignette, (0, 0), mask)

    draw = ImageDraw.Draw(img)

    badge_text = f"అధ్యాయం {chapter_num:02d}" if is_telugu else f"CHAPTER {chapter_num:02d}"
    badge_font = _load_font(is_telugu, size=int(height * 0.038))

    bbox = badge_font.getbbox(badge_text)
    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]

    pad_x, pad_y = int(width * 0.022), int(height * 0.012)
    pill_w = bw + pad_x * 2
    pill_h = bh + pad_y * 2
    pill_x = (width - pill_w) // 2
    pill_y = int(height * 0.28)

    draw.rounded_rectangle(
        [(pill_x, pill_y), (pill_x + pill_w, pill_y + pill_h)],
        radius=int(pill_h / 2),
        fill=badge_bg,
        outline=badge_border,
        width=2,
    )
    draw.text(
        (pill_x + pad_x - bbox[0], pill_y + pad_y - bbox[1]),
        badge_text,
        font=badge_font,
        fill=accent,
    )

    clean_title = title.strip().strip('"').strip("'")
    clean_title = re.sub(r"^(?:CHAPTER|ACT|SCENE)\s*\d+[:\-]\s*", "", clean_title, flags=re.IGNORECASE)

    title_size = int(height * 0.065)
    title_font = _load_font(is_telugu, size=title_size)

    max_chars_per_line = 32 if is_telugu else 38
    title_lines = textwrap.wrap(clean_title, width=max_chars_per_line)
    if not title_lines:
        title_lines = [clean_title]

    line_height = int(title_size * 1.35)
    total_title_h = len(title_lines) * line_height
    start_y = pill_y + pill_h + int(height * 0.05)

    for i, line in enumerate(title_lines):
        line_bbox = title_font.getbbox(line)
        lw = line_bbox[2] - line_bbox[0]
        lx = (width - lw) // 2 - line_bbox[0]
        ly = start_y + i * line_height

        draw.text((lx + 3, ly + 3), line, font=title_font, fill=(0, 0, 0, 180))
        draw.text((lx, ly), line, font=title_font, fill=(255, 255, 255, 255))

    rule_y = start_y + total_title_h + int(height * 0.04)
    rule_w = int(width * 0.28)
    rule_x1 = (width - rule_w) // 2
    rule_x2 = rule_x1 + rule_w
    draw.line([(rule_x1, rule_y), (rule_x2, rule_y)], fill=accent, width=3)

    if subtitle:
        sub_size = int(height * 0.032)
        sub_font = _load_font(is_telugu, size=sub_size)
        sub_bbox = sub_font.getbbox(subtitle)
        sw = sub_bbox[2] - sub_bbox[0]
        sx = (width - sw) // 2 - sub_bbox[0]
        sy = rule_y + int(height * 0.035)

        draw.text((sx + 2, sy + 2), subtitle, font=sub_font, fill=(0, 0, 0, 160))
        draw.text((sx, sy), subtitle, font=sub_font, fill=(203, 213, 225, 240))

    final_img = img.convert("RGB")
    final_img.save(str(out_file), quality=95)
    print(f"🎬 [Chapter Engine] Rendered 16:9 Chapter Bumper {chapter_num}: {out_file.name}")
    return str(out_file)


def create_chapter_bumper_clip(
    bumper_image_path: str,
    output_clip_path: str,
    duration: float = 3.0,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> str:
    inp = Path(bumper_image_path)
    outp = Path(output_clip_path)
    outp.parent.mkdir(parents=True, exist_ok=True)

    if not inp.exists():
        raise FileNotFoundError(f"Chapter bumper image not found: {bumper_image_path}")

    fade_in_dur = 0.35
    fade_out_st = max(0.5, duration - 0.35)

    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fade=t=in:st=0:d={fade_in_dur},fade=t=out:st={fade_out_st:.2f}:d=0.35"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(inp),
        "-t", f"{duration:.2f}",
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-movflags", "+faststart",
        str(outp),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not outp.exists() or outp.stat().st_size < 1024:
        raise RuntimeError(f"FFmpeg failed to create chapter bumper clip: {res.stderr}")

    return str(outp)


def parse_chapters_from_script(
    sections: List[Dict[str, Any]],
    total_duration: float = 0.0,
    script_text: str = "",
    min_chapter_duration: float = 10.0,
) -> List[Dict[str, Any]]:
    chapters: List[Dict[str, Any]] = []

    chapter_regex = re.compile(
        r"(?:\[|\()?(?:CHAPTER|ACT|అధ్యాయం|భాగం)\s*(\d+)[:\s\-]+([^\]\)\r\n]+)(?:\]|\))?",
        re.IGNORECASE,
    )
    detected_markers: List[Tuple[int, str, int]] = []

    for idx, sec in enumerate(sections):
        narr = sec.get("narration", "")
        vis = sec.get("visual_concept", "")
        text_block = f"{vis} {narr}"
        m = chapter_regex.search(text_block)
        if m:
            c_num = int(m.group(1))
            c_title = m.group(2).strip().strip("*:_#")
            detected_markers.append((c_num, c_title, idx))

    if not detected_markers and script_text:
        for m in chapter_regex.finditer(script_text):
            c_num = int(m.group(1))
            c_title = m.group(2).strip().strip("*:_#")
            pos = m.start()
            sec_idx = max(0, min(len(sections) - 1, int((pos / max(1, len(script_text))) * len(sections))))
            detected_markers.append((c_num, c_title, sec_idx))

    sec_count = max(1, len(sections))
    avg_sec_dur = (total_duration / sec_count) if total_duration > 0 else 5.0

    if detected_markers and len(detected_markers) >= 3:
        last_time = -1.0
        c_idx = 1
        for num, title, s_idx in detected_markers:
            if s_idx < len(sections) and "start" in sections[s_idx]:
                st = float(sections[s_idx]["start"])
            else:
                st = s_idx * avg_sec_dur

            if c_idx == 1:
                st = 0.0

            if c_idx == 1 or (st - last_time >= min_chapter_duration):
                chapters.append({
                    "chapter": c_idx,
                    "title": title[:65].strip(),
                    "start_time": round(st, 2),
                    "timestamp": _format_time_hhmmss(st),
                    "section_index": s_idx,
                })
                last_time = st
                c_idx += 1

    if len(chapters) < 3:
        is_tel = _is_telugu_text(script_text) or any(_is_telugu_text(s.get("narration", "")) for s in sections)
        effective_dur = total_duration if total_duration > 15.0 else (sec_count * 5.0)

        if effective_dur >= 360.0:
            target_chapters = 5
        elif effective_dur >= 180.0:
            target_chapters = 4
        else:
            target_chapters = 3

        default_titles_en = [
            "Introduction & The Mystery",
            "The Hidden Truth Unfolds",
            "The Critical Breakthrough",
            "Deep Dive & Turning Point",
            "Conclusion & Final Verdict",
        ]

        default_titles_te = [
            "పరిచయం మరియు అసలు వివాదం",
            "తెలియని నిజాలు మరియు నేపథ్యం",
            "కీలక మలుపు మరియు వాస్తవాలు",
            "లోతైన విశ్లేషణ మరియు ప్రభావం",
            "తీర్పు మరియు ముగింపు సమాధానం",
        ]

        titles = default_titles_te if is_tel else default_titles_en
        chapters = []
        step_secs = effective_dur / target_chapters

        for i in range(target_chapters):
            st = round(i * step_secs, 1)
            if i == 0:
                st = 0.0
            sec_idx = min(sec_count - 1, int(round((st / max(1.0, effective_dur)) * (sec_count - 1))))
            chapters.append({
                "chapter": i + 1,
                "title": titles[i % len(titles)],
                "start_time": st,
                "timestamp": _format_time_hhmmss(st),
                "section_index": sec_idx,
            })

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        chapters_file = OUTPUT_DIR / "chapters.json"
        chapters_file.write_text(json.dumps(chapters, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"✅ [Chapter Engine] Structured {len(chapters)} YouTube-compliant chapters saved to output/chapters.json")
    except Exception as save_err:
        print(f"⚠️ Error saving chapters.json: {save_err}")

    return chapters


def format_youtube_chapters_description(chapters: List[Dict[str, Any]]) -> str:
    if not chapters or len(chapters) < 3:
        return ""

    header = "\n\n📌 TIMESTAMPS / CHAPTERS:"
    lines = [header]
    for ch in chapters:
        ts = ch.get("timestamp", "00:00")
        title = ch.get("title", "")
        lines.append(f"{ts} - {title}")
    lines.append("")
    return "\n".join(lines)
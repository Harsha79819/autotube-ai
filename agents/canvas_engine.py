"""
Creator Canvas Engine - builds 9:16 layered scenes the way Shorts creators do,
instead of dropping one raw web photo full-bleed.

Layers (back to front), each saved as its own PNG so ffmpeg can animate them:

    bg      Blurred / tinted stage frame, or procedural bokeh (never AI-generated)
    cutout  Transparent PNG of the contestant: drop shadow + emotion-coloured rim glow
            + name chip. Solo (centre / lower-left / lower-right) or split-screen.
    vs      "VS" badge on the diagonal seam when two people clash
    banner  Telugu punchline panel in the top safe zone

Nothing here ever generates a human face. If there is no cutout, scenes degrade to
photo-card / typography-card / name-card layouts (see canvas_ladder.py for the policy).

Safe zones (Shorts/Reels UI covers the top ~10% and bottom ~20%):
    banner top  = 11% of height
    cutouts end = 80% of height  (leaves room for burned-in subtitles)
"""

from __future__ import annotations

import json
import math
import os
import random
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, features

from agents.scene_planner import EMOTION_COLORS, Scene

ROOT = Path(__file__).resolve().parent.parent
FONT_PATHS = [
    ROOT / "fonts" / "NotoSansTelugu-Bold.ttf",
    ROOT / "fonts" / "KohinoorTelugu.ttc",
    Path("/System/Library/Fonts/Supplemental/KohinoorTelugu.ttc"),
]
STAGE_DIR = Path(os.environ.get("AUTOTUBE_STAGE_DIR", ROOT / "data" / "stage"))
BRAND_FILE = ROOT / "data" / "brand.json"  # optional {"channel_name": "...", "accent": "#FFC400"}

W_DEFAULT, H_DEFAULT = 1080, 1920
SOLO_PLACEMENTS = ("center", "left", "center", "right")

HAS_RAQM = features.check("raqm") and os.environ.get("AUTOTUBE_FORCE_LIBASS") != "1"
_warned_shaping = False


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _hex(c: str) -> Tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _darken(rgb, f):
    return tuple(max(0, min(255, int(v * f))) for v in rgb)


def _font(size: int) -> ImageFont.FreeTypeFont:
    engine = ImageFont.Layout.RAQM if HAS_RAQM else ImageFont.Layout.BASIC
    for p in FONT_PATHS:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size, layout_engine=engine)
            except Exception:
                continue
    return ImageFont.load_default()


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    img = img.convert("RGB")
    s = max(w / img.width, h / img.height)
    img = img.resize((max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS)
    l, t = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((l, t, l + w, t + h))


def _load_brand() -> dict:
    try:
        return json.loads(BRAND_FILE.read_text(encoding="utf-8")) if BRAND_FILE.exists() else {}
    except Exception:
        return {}


def _vignette(img: Image.Image, strength: float = 0.62) -> Image.Image:
    mask = Image.radial_gradient("L").resize(img.size, Image.BICUBIC)
    mask = mask.point(lambda v: int(max(0, v - 90) * strength * 1.6))
    return Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, mask)


# --------------------------------------------------------------------------- #
# Backgrounds (Layer 1) - real stage frames or procedural. Never generated people.
# --------------------------------------------------------------------------- #
def _stage_frames() -> List[Path]:
    if not STAGE_DIR.exists():
        return []
    return sorted(p for p in STAGE_DIR.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))


def _is_bigg_boss_context() -> bool:
    try:
        for t_p in [ROOT / "output" / "topic.txt", ROOT / "output" / "topic.json"]:
            if t_p.exists():
                txt = t_p.read_text(encoding="utf-8").lower()
                if "bigg boss" in txt or "bb10" in txt or "star maa" in txt:
                    return True
    except Exception:
        pass
    return False


def make_background(w: int, h: int, emotion: str, seed: int, tint: Optional[str] = None, allow_stage_frames: Optional[bool] = None) -> Image.Image:
    accent = _hex(tint or EMOTION_COLORS.get(emotion, EMOTION_COLORS["neutral"]))
    if allow_stage_frames is None:
        allow_stage_frames = _is_bigg_boss_context()
    frames = _stage_frames() if allow_stage_frames else []
    if frames:
        base = _cover(Image.open(frames[seed % len(frames)]), w, h)
        base = base.filter(ImageFilter.GaussianBlur(26))
        base = Image.eval(base, lambda v: int(v * 0.48))
        base = Image.blend(base, Image.new("RGB", (w, h), _darken(accent, 0.55)), 0.28)
    else:
        rnd = random.Random(seed * 7919 + 13)
        top, bottom = (12, 12, 24), _darken(accent, 0.34)
        grad = Image.linear_gradient("L").resize((w, h))
        base = Image.composite(Image.new("RGB", (w, h), bottom), Image.new("RGB", (w, h), top), grad)
        bokeh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(bokeh)
        palette = [accent, (255, 196, 0), (255, 255, 255), _darken(accent, 1.4)]
        for _ in range(22):
            r = rnd.randint(40, 190)
            x, y = rnd.randint(-60, w + 60), rnd.randint(0, h)
            col = rnd.choice(palette)
            d.ellipse((x - r, y - r, x + r, y + r), fill=(*col, rnd.randint(22, 62)))
        bokeh = bokeh.filter(ImageFilter.GaussianBlur(22))
        base = Image.alpha_composite(base.convert("RGBA"), bokeh).convert("RGB")
    return _vignette(base)


# --------------------------------------------------------------------------- #
# Telugu text (Layer 4 content)
# --------------------------------------------------------------------------- #
def _warn_shaping_once():
    global _warned_shaping
    if not HAS_RAQM and not _warned_shaping:
        _warned_shaping = True
        print("[Canvas] Pillow has no libraqm: Telugu text is rendered through libass (ffmpeg) "
              "so conjuncts shape correctly. `pip install -U Pillow` + libfribidi gives the faster path.")


def _wrap(draw_font, text: str, max_w: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = f"{cur} {wd}".strip()
        if draw_font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def _text_pil(text, box_w, max_lines, start, min_size, fill, accent, stroke, highlight_last) -> Image.Image:
    size = start
    while True:
        font = _font(size)
        lines = _wrap(font, text, box_w)
        if len(lines) <= max_lines or size <= min_size:
            break
        size -= 4
    line_h = int(size * 1.32)
    img = Image.new("RGBA", (box_w, line_h * len(lines) + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for li, line in enumerate(lines):
        total = font.getlength(line)
        x = (box_w - total) / 2
        y = li * line_h
        words = line.split(" ")
        for wi, wd in enumerate(words):
            is_hl = highlight_last and li == len(lines) - 1 and wi == len(words) - 1
            d.text((x, y), wd, font=font, fill=accent if is_hl else fill,
                   stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
            x += font.getlength(wd + " ")
    return img


def _ass_color(rgb) -> str:  # ASS is &HBBGGRR&
    return f"&H{rgb[2]:02X}{rgb[1]:02X}{rgb[0]:02X}&"


# libass "Fontsize" is the font's full line height, not the em. Measured against Pillow for
# fonts/NotoSansTelugu-Bold.ttf: libass ink width is linear in Fontsize at 4.55 px/unit vs 6.70 px per
# Pillow size unit, i.e. Fontsize = 1.47 x Pillow size. Re-measure if you swap the font.
_ASS_SIZE_FACTOR = 1.47
_AVG_ADVANCE_EM = 0.47  # average Telugu advance per code point, in em (measured ~0.45, padded)


def _text_libass(text, box_w, max_lines, start, min_size, fill, accent, stroke, highlight_last) -> Image.Image:
    """Shape Telugu with libass (already a hard dependency via the subtitle pipeline)."""
    n = len(text)
    size = start  # Pillow-equivalent size; shrink until the estimated line count fits
    while size > min_size and math.ceil(n * _AVG_ADVANCE_EM * size / box_w) > max_lines:
        size -= 4
    fs = int(size * _ASS_SIZE_FACTOR)
    box_h = int(fs * 1.4 * (max_lines + 1)) + 20  # slack: libass wraps on its own, never clip
    words = text.split()
    if highlight_last and len(words) > 1:
        body = " ".join(words[:-1]) + " {\\1c" + _ass_color(accent) + "}" + words[-1]
    else:
        body = text
    ass = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\n"
        f"PlayResX: {box_w}\nPlayResY: {box_h}\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: T,Noto Sans Telugu,{fs},{_ass_color(fill)},&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,{stroke},0,5,8,8,0,1\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:05.00,T,,0,0,0,,{body}\n"
    )
    import numpy as np  # already a transitive dependency of moviepy

    # libass does not write alpha onto a transparent canvas, so render the same text over opaque
    # black and opaque white and recover alpha + colour from the difference (two-background matting).
    # Exact for anti-aliased edges and independent of the ffmpeg build.
    with tempfile.TemporaryDirectory() as td:
        ass_path = Path(td) / "t.ass"
        ass_path.write_text(ass, encoding="utf-8")
        ass_arg = ass_path.as_posix().replace(":", r"\:")
        fonts_arg = (ROOT / "fonts").as_posix().replace(":", r"\:")
        ass_f = f"ass={ass_arg}:fontsdir={fonts_arg}"
        blk, wht = Path(td) / "on_black.png", Path(td) / "on_white.png"
        graph = (f"color=c=black:s={box_w}x{box_h}:d=1,format=rgb24,{ass_f}[ob];"
                 f"color=c=white:s={box_w}x{box_h}:d=1,format=rgb24,{ass_f}[ow]")
        cmd = ["ffmpeg", "-y", "-filter_complex", graph,
               "-map", "[ob]", "-frames:v", "1", str(blk),
               "-map", "[ow]", "-frames:v", "1", str(wht)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not blk.exists() or not wht.exists():
            raise RuntimeError(f"libass text render failed: {r.stderr[-400:]}")
        c1 = np.asarray(Image.open(blk).convert("RGB"), dtype=np.float32)
        c2 = np.asarray(Image.open(wht).convert("RGB"), dtype=np.float32)
    alpha = np.clip(1.0 - (c2 - c1).mean(axis=2) / 255.0, 0.0, 1.0)
    rgb = np.clip(c1 / np.maximum(alpha[..., None], 1e-3), 0, 255)
    rgb[alpha < 1e-3] = 0
    rgba = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)
    img = Image.fromarray(rgba, "RGBA")
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        raise RuntimeError("libass rendered no glyphs (is the 'Noto Sans Telugu' font reachable?)")
    ink = img.crop(bbox)
    # Match the PIL path's contract: a box_w-wide strip with the text centred in it.
    strip = Image.new("RGBA", (box_w, ink.height), (0, 0, 0, 0))
    strip.alpha_composite(ink, (max(0, (box_w - ink.width) // 2), 0))
    return strip


def render_text(text, box_w, max_lines=3, start=84, min_size=52, fill=(255, 255, 255, 255),
                accent=(255, 196, 0, 255), stroke=6, highlight_last=True) -> Image.Image:
    text = " ".join((text or "").split())
    if not text:
        return Image.new("RGBA", (box_w, 4), (0, 0, 0, 0))
    _warn_shaping_once()
    if HAS_RAQM:
        return _text_pil(text, box_w, max_lines, start, min_size, fill, accent, stroke, highlight_last)
    return _text_libass(text, box_w, max_lines, start, min_size, fill[:3], accent[:3], stroke, highlight_last)


# --------------------------------------------------------------------------- #
# Layer builders
# --------------------------------------------------------------------------- #
def _blank(w, h) -> Image.Image:
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def _comp(layer: Image.Image, img: Image.Image, x: int, y: int) -> None:
    """alpha_composite that tolerates negative / overflowing offsets (clips instead of raising)."""
    sx, sy = max(0, -x), max(0, -y)
    dx, dy = max(0, x), max(0, y)
    cw = min(img.width - sx, layer.width - dx)
    ch = min(img.height - sy, layer.height - dy)
    if cw <= 0 or ch <= 0:
        return
    layer.alpha_composite(img.crop((sx, sy, sx + cw, sy + ch)), (dx, dy))


def make_banner_layer(text: str, accent_hex: str, w: int, h: int, tag: str = "") -> Image.Image:
    """Layer 4: dark rounded panel + accent bar + punchline, parked in the top safe zone."""
    accent = _hex(accent_hex)
    layer = _blank(w, h)
    margin, pad = 54, 34
    inner_w = w - 2 * margin - 2 * pad - 14
    txt = render_text(text, inner_w, max_lines=3, start=84, min_size=54, accent=(*accent, 255))
    tag_img = render_text(tag, inner_w, max_lines=1, start=40, min_size=30, fill=(255, 255, 255, 220),
                          stroke=0, highlight_last=False) if tag else None
    panel_h = txt.height + 2 * pad + (tag_img.height + 8 if tag_img else 0)
    top = int(h * 0.11)
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((margin, top + 10, w - margin, top + panel_h + 10), 34, fill=(0, 0, 0, 90))  # soft shadow
    d.rounded_rectangle((margin, top, w - margin, top + panel_h), 34, fill=(10, 10, 18, 236))
    d.rounded_rectangle((margin, top, margin + 14, top + panel_h), 7, fill=(*accent, 255))
    y = top + pad
    if tag_img:
        layer.alpha_composite(tag_img, (margin + pad + 14 + (inner_w - tag_img.width) // 2, y))
        y += tag_img.height + 8
    layer.alpha_composite(txt, (margin + pad + 14, y))
    return layer


def _trim(cut: Image.Image) -> Image.Image:
    cut = cut.convert("RGBA")
    bbox = cut.getchannel("A").getbbox()
    return cut.crop(bbox) if bbox else cut


def make_cutout_layer(cut_path: Path, name: str, accent_hex: str, w: int, h: int,
                      cx: float, bottom: float, box_w: int, box_h: int) -> Image.Image:
    """Layer 2: cutout with spotlight, rim glow, drop shadow and a name chip."""
    accent = _hex(accent_hex)
    cut = _trim(Image.open(cut_path))
    s = min(box_w / cut.width, box_h / cut.height)
    cut = cut.resize((max(1, round(cut.width * s)), max(1, round(cut.height * s))), Image.LANCZOS)
    # Busts end in a flat cut that reads as "floating". Dissolve the last 16% into the background
    # so the figure sits in the frame, and the bottom 20% stays clear for burned-in subtitles.
    fade_h = max(2, int(cut.height * 0.16))
    ramp = Image.new("L", cut.size, 255)
    ramp.paste(ImageOps.invert(Image.linear_gradient("L")).resize((cut.width, fade_h)), (0, cut.height - fade_h))
    cut.putalpha(ImageChops.multiply(cut.getchannel("A"), ramp))
    x, y = round(cx - cut.width / 2), round(bottom - cut.height)

    layer = _blank(w, h)
    # spotlight behind the head/shoulders
    spot = ImageOps.invert(Image.radial_gradient("L")).resize((int(box_w * 1.5), int(box_w * 1.5)), Image.BICUBIC)
    # radial_gradient is ~180/255 (not 0) at the edge midpoints, so subtract that floor or the
    # square's border shows up as a faint hard-edged band behind the cutout.
    spot_a = spot.point(lambda v: int(max(0, v - 75) * 1.42 * 0.26))
    spot_rgba = Image.new("RGBA", spot.size, (255, 255, 255, 0))
    spot_rgba.putalpha(spot_a)
    _comp(layer, spot_rgba, round(cx - spot.width / 2), round(bottom - cut.height * 0.62 - spot.height / 2))

    alpha = Image.new("L", (w, h), 0)
    alpha.paste(cut.getchannel("A"), (x, y))
    glow_a = alpha.filter(ImageFilter.GaussianBlur(30)).point(lambda v: min(255, int(v * 2.6)))
    glow = Image.new("RGBA", (w, h), (*accent, 0))
    glow.putalpha(glow_a.point(lambda v: int(v * 0.62)))
    layer.alpha_composite(glow)
    shadow_a = ImageChops.offset(alpha, 0, 26).filter(ImageFilter.GaussianBlur(24)).point(lambda v: int(v * 0.6))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow.putalpha(shadow_a)
    layer.alpha_composite(shadow)
    _comp(layer, cut, x, y)

    if name:
        chip_txt = render_text(name, box_w, max_lines=1, start=58, min_size=36, stroke=0,
                               highlight_last=False, fill=(255, 255, 255, 255))
        ink = chip_txt.getchannel("A").getbbox()  # render_text returns a box_w-wide strip; hug the ink
        if ink:
            chip_txt = chip_txt.crop(ink)
        pw, ph = chip_txt.width + 56, chip_txt.height + 26
        chip = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        ImageDraw.Draw(chip).rounded_rectangle((0, 0, pw - 1, ph - 1), ph // 2, fill=(*accent, 245))
        chip.alpha_composite(chip_txt, (28, 13))
        _comp(layer, chip, round(cx - pw / 2), min(h - ph - 4, round(bottom - ph / 2)))
    return layer


def make_vs_layer(w: int, h: int, cy: float) -> Image.Image:
    """Layer 3 element: VS badge on the seam."""
    size = 250
    badge = _blank(size + 40, size + 40)
    d = ImageDraw.Draw(badge)
    d.ellipse((24, 30, size + 14, size + 20), fill=(0, 0, 0, 120))
    d.ellipse((20, 20, size + 10, size + 10), fill=(255, 196, 0, 255), outline=(0, 0, 0, 255), width=12)
    font = _font(140)
    tw = font.getlength("VS")
    d.text(((size + 30 - tw) / 2, 28), "VS", font=font, fill=(0, 0, 0, 255))
    badge = badge.rotate(-9, resample=Image.BICUBIC, expand=True)
    layer = _blank(w, h)
    layer.alpha_composite(badge, (round(w / 2 - badge.width / 2), round(cy - badge.height / 2)))
    return layer


def _burst(size: int, rnd: random.Random, points: int = 22) -> List[Tuple[float, float]]:
    pts = []
    for i in range(points * 2):
        ang = math.pi * i / points
        r = size * (0.5 if i % 2 == 0 else 0.4) * rnd.uniform(0.94, 1.04)
        pts.append((r * math.cos(ang), r * math.sin(ang)))
    return pts


def make_burst_layer(w: int, h: int, accent_hex: str, cy: float, seed: int) -> Image.Image:
    """Animated-reaction stand-in: comic burst in the emotion colour (no faces)."""
    accent, rnd = _hex(accent_hex), random.Random(seed)
    layer = _blank(w, h)
    d = ImageDraw.Draw(layer)
    pts = _burst(int(w * 1.0), rnd)
    d.polygon([(w / 2 + x + 14, cy + y + 18) for x, y in pts], fill=(0, 0, 0, 110))
    d.polygon([(w / 2 + x, cy + y) for x, y in pts], fill=(*_darken(accent, 0.8), 255))
    inner = [(w / 2 + x * 0.88, cy + y * 0.88) for x, y in pts]
    d.polygon(inner, fill=(*accent, 255), outline=(255, 255, 255, 255), width=8)
    return layer


# --------------------------------------------------------------------------- #
# Scene composition
# --------------------------------------------------------------------------- #
@dataclass
class LayerSpec:
    path: str
    enter: str  # up | left | right | drop | fade
    t0: float
    bob: bool = False
    ox: int = 0  # where the cropped PNG sits on the canvas
    oy: int = 0
    empty: bool = False

    def __post_init__(self):
        # Layers are full-canvas RGBA but mostly transparent. Overlaying 1080x1920 per frame per layer
        # dominated render time (~1s of CPU per second of video, per layer), so crop to the visible
        # bounds once and overlay at an offset instead.
        im = Image.open(self.path).convert("RGBA")
        bbox = im.getchannel("A").getbbox()
        if bbox is None:
            self.empty = True
            return
        if bbox != (0, 0, im.width, im.height):
            im.crop(bbox).save(self.path, "PNG")
        self.ox, self.oy = bbox[0], bbox[1]


@dataclass
class SceneLayers:
    bg: str
    layers: List[LayerSpec] = field(default_factory=list)
    kind: str = ""


def _save(img: Image.Image, path: Path, mode: Optional[str] = None) -> str:
    (img.convert(mode) if mode else img).save(path, "PNG")
    return str(path)


def _split_bg(w, h, left_hex, right_hex, seed) -> Image.Image:
    """Diagonal split panels + seam."""
    lbg = make_background(w, h, "neutral", seed, tint=left_hex)
    rbg = make_background(w, h, "neutral", seed + 1, tint=right_hex)
    mask = Image.new("L", (w, h), 0)
    top_x, bot_x = int(w * 0.58), int(w * 0.42)
    ImageDraw.Draw(mask).polygon([(0, 0), (top_x, 0), (bot_x, h), (0, h)], fill=255)
    out = Image.composite(lbg, rbg, mask)
    ImageDraw.Draw(out).line([(top_x, 0), (bot_x, h)], fill=(255, 255, 255), width=10)
    return out


def compose_scene(scene: Scene, out_dir: Path, w: int = W_DEFAULT, h: int = H_DEFAULT,
                  photo_path: Optional[Path] = None, force: Optional[str] = None) -> SceneLayers:
    """
    Turn a planned Scene into layer PNGs. `photo_path` is an optional REAL photo
    (never AI-generated) used only for no-entity scenes (photo-card layout).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"s{scene.index:02d}"
    brand = _load_brand()
    brand_tag = brand.get("channel_name", "")
    emo_hex = EMOTION_COLORS.get(scene.emotion, EMOTION_COLORS["neutral"])
    layout = force or scene.layout

    if layout == "split" and len(scene.entities) >= 2:
        a, b = scene.entities[0], scene.entities[1]
        bg = _split_bg(w, h, a.entity.accent, b.entity.accent, scene.index)
        res = SceneLayers(bg=_save(bg, out_dir / f"{tag}_bg.png", "RGB"), kind="split")
        box_w, box_h, bottom = int(w * 0.50), int(h * 0.48), h * 0.80  # 0.50w each: never overlap each other
        la = make_cutout_layer(a.entity.cutout_for(a.emotion)[1], a.entity.display_name, a.entity.accent,
                               w, h, w * 0.25, bottom, box_w, box_h)
        lb = make_cutout_layer(b.entity.cutout_for(b.emotion)[1], b.entity.display_name, b.entity.accent,
                               w, h, w * 0.75, bottom, box_w, box_h)
        res.layers += [
            LayerSpec(_save(la, out_dir / f"{tag}_l.png"), "left", 0.10, True),
            LayerSpec(_save(lb, out_dir / f"{tag}_r.png"), "right", 0.10, True),
            LayerSpec(_save(make_vs_layer(w, h, h * 0.46), out_dir / f"{tag}_vs.png"), "up", 0.40),
        ]
    elif layout == "solo" and scene.entities:
        se = scene.entities[0]
        accent = EMOTION_COLORS.get(se.emotion, se.entity.accent) if se.entity.accent in ("", "#FFC400") else se.entity.accent
        bg = make_background(w, h, se.emotion, scene.index, tint=EMOTION_COLORS.get(se.emotion))
        res = SceneLayers(bg=_save(bg, out_dir / f"{tag}_bg.png", "RGB"), kind="solo")
        placement = SOLO_PLACEMENTS[(scene.index - 1) % len(SOLO_PLACEMENTS)]
        cx = {"center": 0.5, "left": 0.40, "right": 0.60}[placement] * w
        lc = make_cutout_layer(se.entity.cutout_for(se.emotion)[1], se.entity.display_name, accent,
                               w, h, cx, h * 0.80, int(w * 0.92), int(h * 0.52))
        res.layers.append(LayerSpec(_save(lc, out_dir / f"{tag}_c.png"), "up", 0.10, True))
    elif layout == "name_card":
        # Person is named but we have no cutout: big name + burst. No face, no guess.
        name = scene.mentioned_without_cutout[0] if scene.mentioned_without_cutout else ""
        res = SceneLayers(bg=_save(make_background(w, h, scene.emotion, scene.index), out_dir / f"{tag}_bg.png", "RGB"),
                          kind="name_card")
        res.layers.append(LayerSpec(_save(make_burst_layer(w, h, emo_hex, h * 0.50, scene.index),
                                          out_dir / f"{tag}_burst.png"), "fade", 0.05))
        nm = render_text(name, int(w * 0.70), max_lines=2, start=150, min_size=80, highlight_last=False, stroke=9)
        lay = _blank(w, h)
        lay.alpha_composite(nm, ((w - nm.width) // 2, int(h * 0.50 - nm.height / 2)))
        res.layers.append(LayerSpec(_save(lay, out_dir / f"{tag}_name.png"), "up", 0.20, True))
    elif layout == "broll" and photo_path and Path(photo_path).exists():
        # Full-Bleed 9:16 Cinema Motion & Full-Screen Reaction Meme
        photo = Image.open(photo_path).convert("RGB")
        bg = _cover(photo, w, h)
        bg = _vignette(bg, strength=0.32)
        res = SceneLayers(bg=_save(bg, out_dir / f"{tag}_bg.png", "RGB"), kind="cinema_motion")
        # Full-screen cinema motion: no boxed card, clean view with room for burned-in subtitles
        return res
    elif layout == "photo_card" and photo_path and Path(photo_path).exists():
        # Framed Canva photo card with blurred backdrop & punchline
        photo = Image.open(photo_path).convert("RGB")
        bg = _vignette(Image.eval(_cover(photo, w, h).filter(ImageFilter.GaussianBlur(34)), lambda v: int(v * 0.5)))
        res = SceneLayers(bg=_save(bg, out_dir / f"{tag}_bg.png", "RGB"), kind="photo_card")
        card_w = int(w * 0.88)
        s = min(card_w / photo.width, (h * 0.46) / photo.height)
        card = photo.resize((round(photo.width * s), round(photo.height * s)), Image.LANCZOS)
        lay = _blank(w, h)
        x0, y0 = (w - card.width) // 2, int(h * 0.30) + 0
        d = ImageDraw.Draw(lay)
        d.rounded_rectangle((x0 - 14, y0 - 14 + 16, x0 + card.width + 14, y0 + card.height + 14 + 16), 30, fill=(0, 0, 0, 120))
        d.rounded_rectangle((x0 - 14, y0 - 14, x0 + card.width + 14, y0 + card.height + 14), 30, fill=(*_hex(emo_hex), 255))
        m = Image.new("L", card.size, 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, card.width - 1, card.height - 1), 22, fill=255)
        lay.paste(card, (x0, y0), m)
        res.layers.append(LayerSpec(_save(lay, out_dir / f"{tag}_photo.png"), "up", 0.10))
    else:
        # Typography card: the punchline IS the visual.
        res = SceneLayers(bg=_save(make_background(w, h, scene.emotion, scene.index), out_dir / f"{tag}_bg.png", "RGB"),
                          kind="typography_card")
        res.layers.append(LayerSpec(_save(make_burst_layer(w, h, emo_hex, h * 0.47, scene.index),
                                          out_dir / f"{tag}_burst.png"), "fade", 0.05))
        big = render_text(scene.banner, int(w * 0.66), max_lines=5, start=112, min_size=64,
                          accent=(255, 255, 255, 255), stroke=8, highlight_last=False)
        lay = _blank(w, h)
        lay.alpha_composite(big, ((w - big.width) // 2, int(h * 0.47 - big.height / 2)))
        res.layers.append(LayerSpec(_save(lay, out_dir / f"{tag}_type.png"), "up", 0.20, True))
        if brand_tag:
            tg = render_text(brand_tag, int(w * 0.7), 1, 48, 30, stroke=0, highlight_last=False)
            lt = _blank(w, h)
            lt.alpha_composite(tg, ((w - tg.width) // 2, int(h * 0.11)))
            res.layers.append(LayerSpec(_save(lt, out_dir / f"{tag}_brand.png"), "drop", 0.05))
        return res  # banner would repeat the headline

    banner = make_banner_layer(scene.banner, emo_hex, w, h, tag=brand_tag)
    res.layers.append(LayerSpec(_save(banner, out_dir / f"{tag}_banner.png"), "drop", 0.05))
    return res


# --------------------------------------------------------------------------- #
# ffmpeg: animate the layers over a Ken-Burns background
# --------------------------------------------------------------------------- #
def _enter_expr(spec: LayerSpec) -> Tuple[str, str]:
    p = f"min(max((t-{spec.t0:.3f})/0.38,0),1)"
    inv = f"pow(1-{p},3)"
    bob = "+sin(2*PI*t*0.45)*H*0.004" if spec.bob else ""
    if spec.enter == "left":
        return f"-{inv}*W*0.14", f"0{bob}"
    if spec.enter == "right":
        return f"{inv}*W*0.14", f"0{bob}"
    if spec.enter == "drop":
        return "0", f"-{inv}*H*0.05{bob}"
    if spec.enter == "fade":
        return "0", f"0{bob}"
    return "0", f"{inv}*H*0.06{bob}"  # up


def _zoom_expr(motion: str, duration: float) -> str:
    """Background zoom factor as a function of time t (the bg is blurred, so cheap scaling is enough)."""
    d = max(0.5, duration)
    if motion == "hook":  # punch-in over 0.8s, then a slow drift
        return f"if(lt(t,0.8),1+0.25*t/0.8,1.25+0.05*(t-0.8)/{d:.3f})"
    if motion == "pull":
        return f"(1.12-0.12*t/{d:.3f})"
    return f"(1+0.12*t/{d:.3f})"  # push


def render_scene_clip(layers: SceneLayers, out_path: Path, duration: float, motion: str = "push",
                      fps: int = 30, width: int = W_DEFAULT, height: int = H_DEFAULT, is_hook: bool = False) -> str:
    """
    One ffmpeg pass: background drifts (push / pull / hook punch-in), then every layer slides or
    fades in on top. The result is an ordinary scene clip for ken_burns.assemble_with_transitions.
    Motion applies to the BACKGROUND only, so banner text and cutouts stay sharp and readable.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    motion = "hook" if is_hook else (motion if motion in ("push", "pull") else "push")

    inputs = ["-loop", "1", "-framerate", str(fps), "-t", f"{duration:.3f}", "-i", layers.bg]
    z = _zoom_expr(motion, duration)
    bg_chain = (f"[0:v]scale=w='trunc({width}*({z})/2)*2':h='trunc({height}*({z})/2)*2':eval=frame,"
                f"crop={width}:{height},setsar=1")
    if is_hook:  # short exposure flash on impact, same idea as the legacy hook
        bg_chain += ",eq=brightness='if(lt(t,0.23),0.22*(1-t/0.23),0)':eval=frame"
    chains, prev = [bg_chain + "[bg]"], "bg"
    for i, spec in enumerate([s for s in layers.layers if not s.empty], start=1):
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{duration:.3f}", "-i", spec.path]
        chains.append(f"[{i}:v]format=rgba,fade=t=in:st={spec.t0:.3f}:d=0.22:alpha=1[L{i}]")
        x, y = _enter_expr(spec)
        chains.append(f"[{prev}][L{i}]overlay=x='{spec.ox}+({x})':y='{spec.oy}+({y})':eval=frame:format=auto[v{i}]")
        prev = f"v{i}"
    chains.append(f"[{prev}]format=yuv420p[vout]")
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(chains), "-map", "[vout]",
           "-t", f"{duration:.3f}", "-r", str(fps), "-c:v", "libx264", "-preset", "ultrafast",
           "-crf", "18", "-pix_fmt", "yuv420p", str(out_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError(f"Canvas clip render failed: {r.stderr[-600:]}")
    return str(out_path)

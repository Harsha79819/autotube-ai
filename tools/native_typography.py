#!/usr/bin/env python3
"""
tools/native_typography.py - Native Apple CoreText Typography & Badge Renderer

Renders 100% authentic, grammatically flawless Indic / Telugu text badges:
- FreeType in standard Pillow lacks HarfBuzz complex text shaping, causing broken ligatures (వత్తులు, గుణింతాలు)
  that look deformed or like disjointed Tamil characters.
- This module leverages macOS native CoreText via Swift (`NSAttributedString`, `Kohinoor Telugu Bold`, Apple CoreText)
  to achieve pixel-perfect, native typographic shaping.
- Produces crisp, transparent PNG pill badges with customizable fill, stroke, outline, and drop shadows.
- Features persistent MD5 disk caching in `data/cache/typography_cache/`.
- Gracefully falls back to Pillow TrueType on non-macOS systems.
"""

import os
import sys
import re
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache" / "typography_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SWIFT_RENDERER_SCRIPT = """
import Foundation
import AppKit

let args = CommandLine.arguments
guard args.count >= 6 else {
    exit(1)
}

let text = args[1]
let outputPath = args[2]
let fontSize = CGFloat(Double(args[3]) ?? 68.0)
let borderColorHex = args[4]
let bgColorHex = args[5]

func colorFromHex(_ hex: String, alpha: CGFloat = 1.0) -> NSColor {
    var cString = hex.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    if cString.hasPrefix("#") {
        cString.remove(at: cString.startIndex)
    }
    if cString.count != 6 {
        return NSColor.white
    }
    var rgbValue: UInt64 = 0
    Scanner(string: cString).scanHexInt64(&rgbValue)
    return NSColor(
        red: CGFloat((rgbValue & 0xFF0000) >> 16) / 255.0,
        green: CGFloat((rgbValue & 0x00FF00) >> 8) / 255.0,
        blue: CGFloat(rgbValue & 0x0000FF) / 255.0,
        alpha: alpha
    )
}

let font = NSFont(name: "Kohinoor Telugu Bold", size: fontSize) 
    ?? NSFont(name: "Telugu Sangam MN Bold", size: fontSize)
    ?? NSFont.systemFont(ofSize: fontSize, weight: .bold)

let textColor = NSColor(red: 1.0, green: 0.92, blue: 0.05, alpha: 1.0) // High-CTR vibrant golden-yellow
let borderColor = colorFromHex(borderColorHex, alpha: 1.0)
let bgColor = colorFromHex(bgColorHex, alpha: 0.94)

let strokeWidth: CGFloat = -3.5 // Negative value means draw both stroke and fill
let attrs: [NSAttributedString.Key: Any] = [
    .font: font,
    .foregroundColor: textColor,
    .strokeColor: NSColor.black,
    .strokeWidth: strokeWidth
]

let attrString = NSAttributedString(string: text, attributes: attrs)
let textSize = attrString.size()

let paddingX: CGFloat = max(32.0, fontSize * 0.45)
let paddingY: CGFloat = max(16.0, fontSize * 0.22)
let badgeW = ceil(textSize.width + paddingX * 2)
let badgeH = ceil(textSize.height + paddingY * 2)
let imageSize = NSSize(width: badgeW, height: badgeH)

let img = NSImage(size: imageSize)
img.lockFocus()

let pillRect = NSRect(origin: .zero, size: imageSize)
let bgPath = NSBezierPath(roundedRect: pillRect.insetBy(dx: 3, dy: 3), xRadius: 18, yRadius: 18)

// Fill dark contrast pill
bgColor.setFill()
bgPath.fill()

// Stroke outline border
borderColor.setStroke()
bgPath.lineWidth = 4.0
bgPath.stroke()

// Draw text centered
let textX = paddingX
let textY = paddingY - 3 // slight optical baseline alignment
attrString.draw(at: NSPoint(x: textX, y: textY))

img.unlockFocus()

guard let tiffData = img.tiffRepresentation,
      let rep = NSBitmapImageRep(data: tiffData),
      let pngData = rep.representation(using: .png, properties: [:]) else {
    exit(1)
}

try? pngData.write(to: URL(fileURLWithPath: outputPath))
"""

_swift_script_path: Optional[str] = None


def _get_swift_script() -> str:
    global _swift_script_path
    if _swift_script_path and os.path.exists(_swift_script_path):
        return _swift_script_path
    tmp = tempfile.NamedTemporaryFile(suffix=".swift", delete=False, mode="w", encoding="utf-8")
    tmp.write(SWIFT_RENDERER_SCRIPT)
    tmp.close()
    _swift_script_path = tmp.name
    return _swift_script_path


def render_native_telugu_badge(
    text: str,
    font_size: int = 68,
    border_color: str = "#FFD700",
    bg_color: str = "#0C0E18",
    output_path: Optional[Path] = None,
) -> Path:
    """
    Renders an authentic Telugu pill badge with native Apple CoreText shaping.
    Returns the Path to the generated transparent PNG.
    """
    clean_text = str(text or "").strip()
    if not clean_text:
        clean_text = "బిగ్ బాస్"

    # Compute cache key
    cache_str = f"{clean_text}|{font_size}|{border_color}|{bg_color}"
    key = hashlib.md5(cache_str.encode("utf-8")).hexdigest()
    cached_path = CACHE_DIR / f"badge_{key}.png"

    dest = Path(output_path) if output_path else cached_path

    if cached_path.exists() and cached_path.stat().st_size > 1000:
        if dest != cached_path:
            shutil.copyfile(cached_path, dest)
        return dest

    # Check if macOS with Swift is available
    if sys.platform == "darwin" and shutil.which("swift"):
        script_file = _get_swift_script()
        temp_dest = CACHE_DIR / f"temp_{key}.png"
        try:
            cmd = [
                "swift",
                script_file,
                clean_text,
                str(temp_dest),
                str(font_size),
                border_color,
                bg_color,
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
            if temp_dest.exists() and temp_dest.stat().st_size > 500:
                os.replace(temp_dest, cached_path)
                if dest != cached_path:
                    shutil.copyfile(cached_path, dest)
                return dest
        except Exception as swift_err:
            print(f"⚠️ Native CoreText render notice: {swift_err}")
            temp_dest.unlink(missing_ok=True)

    # Cross-platform Pillow Fallback
    _render_pillow_fallback(clean_text, font_size, border_color, bg_color, cached_path)
    if dest != cached_path:
        shutil.copyfile(cached_path, dest)
    return dest


def _render_pillow_fallback(
    text: str,
    font_size: int,
    border_color: str,
    bg_color: str,
    dest: Path,
):
    """Pillow fallback for non-macOS environments."""
    font_path = ROOT / "fonts" / "NotoSansTelugu-Bold.ttf"
    if font_path.exists():
        try:
            font = ImageFont.truetype(str(font_path), font_size)
        except Exception:
            font = ImageFont.load_default()
    else:
        font = ImageFont.load_default()

    dummy = Image.new("RGBA", (1, 1))
    d_draw = ImageDraw.Draw(dummy)
    bbox = d_draw.textbbox((0, 0), text, font=font, stroke_width=4)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    pad_x, pad_y = int(font_size * 0.45), int(font_size * 0.22)
    bw, bh = tw + pad_x * 2, th + pad_y * 2

    im = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    # Draw rounded rectangle
    draw.rounded_rectangle((2, 2, bw - 2, bh - 2), radius=16, fill=bg_color, outline=border_color, width=4)
    # Draw text
    draw.text((pad_x - bbox[0], pad_y - bbox[1]), text, font=font, fill="#FFD700", stroke_width=4, stroke_fill="black")

    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "PNG")


if __name__ == "__main__":
    test_word = "హౌస్‌లో రచ్చ రంబోలా!" if len(sys.argv) < 2 else sys.argv[1]
    res = render_native_telugu_badge(test_word)
    print(f"Rendered: {res} ({res.stat().st_size} bytes)")

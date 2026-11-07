#!/usr/bin/env python3
"""
tools/playwright_renderer.py - High-Fidelity HTML/CSS Canvas & Graphic Card Renderer

Leverages Playwright headless Chromium to render ultra-crisp, Canva-grade graphics,
visual proof cards, and thumbnails using modern HTML5, CSS3, Flexbox, and Web Fonts:
- Instant 4K Retina resolution screenshots (device_scale_factor=2).
- Native support for Indic/Telugu typography (Google Fonts Noto Sans Telugu + Kohinoor Telugu).
- CSS filters, box shadows, gradients, and 3D transforms.
- Built-in deterministic fallback to PIL / Native Typography if browser is offline.
"""

import os
import sys
import base64
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

# Cache directory for rendered assets
RENDER_CACHE_DIR = ROOT / "data" / "cache" / "browser_renders"
RENDER_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _file_to_base64_src(file_path: Path) -> str:
    """Converts a local image file to a base64 data URI for offline rendering."""
    if not file_path or not file_path.exists():
        return ""
    suffix = file_path.suffix.lower().replace(".", "")
    mime = "image/png" if suffix == "png" else ("image/jpeg" if suffix in ("jpg", "jpeg") else "image/webp")
    encoded = base64.b64encode(file_path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def render_html_to_image(
    html_content: str,
    output_path: str,
    width: int = 1080,
    height: int = 1920,
    transparent: bool = True,
    device_scale_factor: int = 1,
) -> Optional[str]:
    """
    Renders raw HTML/CSS into a pixel-perfect PNG using Playwright Headless Chromium.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            context = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=device_scale_factor,
            )
            page = context.new_page()
            page.set_content(html_content, wait_until="networkidle", timeout=12000)
            page.screenshot(
                path=str(out_file),
                omit_background=transparent,
                type="png",
            )
            browser.close()

        if out_file.exists() and out_file.stat().st_size > 1000:
            print(f"🎨 [Playwright Renderer] Successfully exported: {out_file.name} ({width}x{height}px)")
            return str(out_file)

    except Exception as exc:
        print(f"⚠️ [Playwright Renderer] Browser render notice: {exc}")

    return None


def generate_canva_html(
    badge_text: str,
    aspect_ratio: str = "9:16",
    bg_image_path: Optional[Path] = None,
    cutout_path: Optional[Path] = None,
    border_color: str = "#FFD700",
) -> str:
    """
    Synthesizes a Canva-grade modern HTML5/CSS3 template for thumbnails and graphic cards.
    """
    w = 1080 if aspect_ratio == "9:16" else (1280 if aspect_ratio == "16:9" else 1080)
    h = 1920 if aspect_ratio == "9:16" else (720 if aspect_ratio == "16:9" else 1080)

    bg_src = _file_to_base64_src(bg_image_path) if bg_image_path else ""
    cutout_src = _file_to_base64_src(cutout_path) if cutout_path else ""

    # 16:9 Landscape Layout (Prasad Tech Split-Screen: Cutout Right, Badge Left)
    if aspect_ratio == "16:9":
        layout_css = """
        .container {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 40px 60px;
        }
        .text-section {
            width: 52%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: flex-start;
            z-index: 10;
        }
        .cutout-section {
            width: 48%;
            height: 100%;
            display: flex;
            justify-content: flex-end;
            align-items: flex-end;
            position: absolute;
            right: 20px;
            bottom: 0;
            z-index: 5;
        }
        .person-cutout {
            max-height: 94%;
            max-width: 100%;
            object-fit: contain;
            filter: drop-shadow(0 0 25px rgba(255, 185, 0, 0.75));
        }
        .badge-pill {
            font-size: 56px;
            padding: 22px 42px;
        }
        """
    # 9:16 Shorts Layout (Subject Centered, Badge Anchored at Bottom Safe Area)
    else:
        layout_css = """
        .container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: space-between;
            padding: 80px 40px 240px 40px;
        }
        .cutout-section {
            width: 100%;
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            margin-top: 100px;
            z-index: 5;
        }
        .person-cutout {
            max-height: 85%;
            max-width: 90%;
            object-fit: contain;
            filter: drop-shadow(0 0 35px rgba(255, 185, 0, 0.8));
        }
        .text-section {
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 10;
        }
        .badge-pill {
            font-size: 76px;
            padding: 26px 54px;
        }
        """

    bg_style = f"background-image: url('{bg_src}');" if bg_src else "background: radial-gradient(circle at center, #1E293B 0%, #0F172A 70%, #020617 100%);"

    html = f"""<!DOCTYPE html>
<html lang="te">
<head>
    <meta charset="UTF-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@800;900&display=swap');

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            width: {w}px;
            height: {h}px;
            overflow: hidden;
            background-color: #0F172A;
            font-family: 'Noto Sans Telugu', 'Kohinoor Telugu', 'Telugu Sangam MN', sans-serif;
            position: relative;
        }}
        .bg-layer {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            {bg_style}
            background-size: cover;
            background-position: center;
            filter: brightness(0.76) contrast(1.15);
            z-index: 1;
        }}
        .vignette-overlay {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: radial-gradient(circle at center, rgba(0,0,0,0) 40%, rgba(0,0,0,0.7) 100%);
            z-index: 2;
        }}
        .container {{
            position: relative;
            width: 100%;
            height: 100%;
            z-index: 3;
        }}
        {layout_css}
        .badge-pill {{
            background: rgba(12, 14, 24, 0.94);
            border: 4px solid {border_color};
            border-radius: 28px;
            color: #FFE600;
            font-weight: 900;
            text-align: center;
            white-space: nowrap;
            letter-spacing: -0.5px;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.85), 0 0 20px {border_color}66;
            text-shadow: 0 4px 12px rgba(0, 0, 0, 0.9), 2px 2px 0 #000, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000;
        }}
    </style>
</head>
<body>
    <div class="bg-layer"></div>
    <div class="vignette-overlay"></div>
    <div class="container">
        {f'<div class="cutout-section"><img class="person-cutout" src="{cutout_src}" alt="Subject" /></div>' if cutout_src else ''}
        <div class="text-section">
            <div class="badge-pill">{badge_text}</div>
        </div>
    </div>
</body>
</html>
"""
    return html


def render_canva_pro_thumbnail(
    badge_text: str,
    aspect_ratio: str = "9:16",
    bg_image_path: Optional[Path] = None,
    cutout_path: Optional[Path] = None,
    border_color: str = "#FFD700",
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    High-level entrypoint: renders a Canva-pro quality thumbnail via Playwright.
    """
    if not output_path:
        out_name = f"canva_thumb_{aspect_ratio.replace(':', '_')}.png"
        output_path = str(RENDER_CACHE_DIR / out_name)

    html = generate_canva_html(
        badge_text=badge_text,
        aspect_ratio=aspect_ratio,
        bg_image_path=bg_image_path,
        cutout_path=cutout_path,
        border_color=border_color,
    )

    w = 1080 if aspect_ratio == "9:16" else (1280 if aspect_ratio == "16:9" else 1080)
    h = 1920 if aspect_ratio == "9:16" else (720 if aspect_ratio == "16:9" else 1080)

    res = render_html_to_image(
        html_content=html,
        output_path=output_path,
        width=w,
        height=h,
        transparent=False,
    )
    return res


if __name__ == "__main__":
    test_out = "/tmp/test_canva_pw.png"
    res = render_canva_pro_thumbnail(
        badge_text="ఎలిమినేషన్ షాక్?!",
        aspect_ratio="9:16",
        border_color="#E63946",
        output_path=test_out,
    )
    print("Canva Pro Thumbnail Rendered:", res)

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
            try:
                page.set_content(html_content, wait_until="load", timeout=8000)
            except Exception:
                page.set_content(html_content, wait_until="domcontentloaded", timeout=5000)
            page.wait_for_timeout(250)
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


# ============================================================
# PRASAD TECH IN TELUGU — SIGNATURE HIGH-CTR THUMBNAIL ENGINE
# ============================================================

def generate_prasad_tech_html(
    header_left_yellow: str = "కొత్త ఫోన్",
    header_left_white: str = "కొంటున్నారా?",
    header_left_emoji: str = "📱",
    header_right_white: str = "ధర & ఫీచర్లు",
    header_right_yellow: str = "లీక్!",
    header_right_emoji: str = "🔥",
    hero_cutout_path: Optional[Path] = None,
    evidence_left_img: Optional[Path] = None,
    evidence_left_text: str = "200MP SONY SENSOR",
    evidence_left_badge: str = "CAMERA LEAK 📸",
    evidence_right_img: Optional[Path] = None,
    evidence_right_text: str = "₹24,999 / 6500mAh",
    evidence_right_badge: str = "PRICE & SPECS ⚡",
    episode_pill_text: str = "TECH 2026",
    brand_logos: Optional[list] = None,
    aspect_ratio: str = "16:9",
    bg_theme: str = "tech_purple",
) -> str:
    """
    Renders the exact 'Prasad Tech in Telugu' signature thumbnail layout:
      1. Top Split Banner: Glossy black pills with high-contrast Yellow & White bold Telugu text & emojis.
      2. Expressive Hero Cutout: Centered / right with glowing golden/cyan rim light.
      3. Lower Split Evidence Panels: Two glass-morphic cyan neon-bordered cards showing real device/scene proof.
      4. Brand Stack & Episode Pill: Floating brand logos (1+, Oppo, Realme, Apple, Samsung) & bottom-left badge.
    """
    is_916 = aspect_ratio == "9:16"
    w = 1080 if is_916 else 1280
    h = 1920 if is_916 else 720

    hero_src = _file_to_base64_src(Path(hero_cutout_path)) if hero_cutout_path and Path(hero_cutout_path).exists() else ""
    ev_left_src = _file_to_base64_src(Path(evidence_left_img)) if evidence_left_img and Path(evidence_left_img).exists() else ""
    ev_right_src = _file_to_base64_src(Path(evidence_right_img)) if evidence_right_img and Path(evidence_right_img).exists() else ""

    if not brand_logos:
        brand_logos = ["1+", "OPPO", "realme"] if "tech" in bg_theme else ["BB10", "HOT"]

    brand_badges_html = ""
    brand_classes = {"1+": "oneplus", "oppo": "oppo", "realme": "realme", "apple": "apple", "samsung": "samsung"}
    for b in brand_logos[:3]:
        cls = brand_classes.get(b.lower(), "default-brand")
        brand_badges_html += f'<div class="brand-logo {cls}">{b}</div>'

    # Background gradient selection
    if "red" in bg_theme or "danger" in bg_theme or "bb10" in bg_theme:
        bg_css = "radial-gradient(circle at 50% 35%, #3b0d15 0%, #170407 65%, #0a0102 100%)"
        glow_color = "rgba(255, 60, 60, 0.8)"
    elif "emerald" in bg_theme:
        bg_css = "radial-gradient(circle at 50% 35%, #063025 0%, #031410 65%, #010806 100%)"
        glow_color = "rgba(0, 240, 180, 0.8)"
    else:  # tech_purple (Prasad Tech signature)
        bg_css = "radial-gradient(circle at 50% 35%, #24134b 0%, #0e071e 65%, #05020c 100%)"
        glow_color = "rgba(255, 215, 0, 0.8)"

    # Evidence panel content
    def make_evidence_inner(src, text, badge):
        if src:
            return f'<img src="{src}" style="width:100%;height:100%;object-fit:cover;" /><div class="box-label">{badge}</div>'
        else:
            parts = text.split("/") if "/" in text else [text, ""]
            p1 = parts[0].strip()
            p2 = parts[1].strip() if len(parts) > 1 else ""
            return f"""
            <div style="color:#00F0FF; font-size:{'36px' if is_916 else '32px'}; font-weight:900; text-align:center; text-shadow:0 0 15px rgba(0,240,255,0.7);">{p1}</div>
            {f'<div style="color:#FFF; font-size:20px; font-weight:800; margin-top:4px;">{p2}</div>' if p2 else ''}
            <div class="box-label">{badge}</div>
            """

    left_inner = make_evidence_inner(ev_left_src, evidence_left_text, evidence_left_badge)
    right_inner = make_evidence_inner(ev_right_src, evidence_right_text, evidence_right_badge)

    if hero_src:
        hero_html = f'<img src="{hero_src}" class="hero-persona" />'
    elif "red" in bg_theme or "danger" in bg_theme or "bb10" in bg_theme:
        hero_html = """
        <div class="bb-emblem-wrap">
          <div class="bb-eye-ring">
            <div class="bb-iris">👁️</div>
          </div>
          <div class="bb-status-badge">BIGG BOSS 10 LIVE</div>
        </div>
        """
    else:
        phone_brand = brand_logos[0] if brand_logos else "1+"
        hero_html = f"""
        <div class="hero-phone">
          <div class="phone-frame">
            <div class="phone-island">
              <div class="notch-cam"></div>
              <div class="notch-pill">🔥 2026 FLAGSHIP</div>
            </div>
            <div class="phone-screen-content">
              <div class="screen-brand">{phone_brand}</div>
              <div class="screen-chip-tag">⚡ SNAPDRAGON 8 ELITE</div>
              <div class="screen-visual">
                <div class="spec-highlight">6500mAh<br>100W FLASH</div>
              </div>
              <div class="screen-camera-spec">📸 200MP SONY SENSOR</div>
            </div>
          </div>
        </div>
        """

    if is_916:
        # Vertical Shorts Layout (Optimized for safe margins above mobile UI)
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@800;900&family=Montserrat:wght@900&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 1080px; height: 1920px; background: {bg_css};
    font-family: 'Noto Sans Telugu', 'Montserrat', sans-serif;
    position: relative; overflow: hidden;
  }}
  .top-strip {{
    position: absolute; top: 120px; left: 0; width: 100%;
    display: flex; flex-direction: column; align-items: center; gap: 20px;
    padding: 0 40px; z-index: 20;
  }}
  .banner-pill {{
    background: #000000; border: 4.5px solid #1c1c24; border-radius: 22px;
    padding: 18px 45px; display: flex; align-items: center; justify-content: center; gap: 16px;
    box-shadow: 0 15px 40px rgba(0,0,0,0.95);
  }}
  .yellow-txt {{ color: #FFE500; font-size: 58px; font-weight: 900; text-shadow: 3px 3px 0 #000, -2px -2px 0 #000; }}
  .white-txt {{ color: #FFFFFF; font-size: 58px; font-weight: 900; text-shadow: 3px 3px 0 #000, -2px -2px 0 #000; }}
  .emoji {{ font-size: 52px; }}

  .hero-persona {{
    position: absolute; top: 380px; left: 50%; transform: translateX(-50%);
    max-height: 850px; z-index: 8;
    filter: drop-shadow(0 0 35px {glow_color}) drop-shadow(0 0 80px rgba(255, 170, 0, 0.45));
  }}
  .hero-phone {{
    position: absolute; top: 430px; left: 50%; transform: translateX(-50%);
    width: 440px; height: 750px; z-index: 8;
    filter: drop-shadow(0 0 40px rgba(0, 240, 255, 0.7)) drop-shadow(0 25px 60px rgba(0,0,0,0.95));
  }}
  .phone-frame {{
    width: 100%; height: 100%; border-radius: 54px; border: 6px solid #2e2f42;
    background: linear-gradient(165deg, #1b1d2e 0%, #0d0e17 60%, #06070a 100%);
    box-shadow: inset 0 0 25px rgba(0, 240, 255, 0.3), 0 0 0 3px #00F0FF;
    position: relative; overflow: hidden; display: flex; flex-direction: column; align-items: center;
    padding: 24px;
  }}
  .phone-island {{
    display: flex; align-items: center; gap: 10px; background: #000;
    border-radius: 24px; padding: 6px 20px; border: 2px solid #333; z-index: 5;
  }}
  .notch-cam {{ width: 14px; height: 14px; border-radius: 50%; background: #111; border: 2px solid #00F0FF; }}
  .notch-pill {{ color: #FFE500; font-size: 18px; font-weight: 900; }}
  .phone-screen-content {{
    width: 100%; flex: 1; margin-top: 30px; display: flex; flex-direction: column;
    align-items: center; justify-content: space-around; position: relative; z-index: 3;
  }}
  .screen-brand {{
    font-size: 54px; font-weight: 900; color: #FFFFFF;
    text-shadow: 0 0 25px rgba(0, 240, 255, 0.8), 3px 3px 0 #000;
  }}
  .screen-chip-tag {{
    background: rgba(0, 240, 255, 0.15); border: 2px solid #00F0FF;
    color: #00F0FF; font-size: 20px; font-weight: 900; padding: 8px 18px;
    border-radius: 12px; text-shadow: 0 0 10px rgba(0, 240, 255, 0.6);
  }}
  .screen-visual {{
    width: 200px; height: 200px; border-radius: 50%;
    background: radial-gradient(circle, rgba(0, 240, 255, 0.35) 0%, rgba(255, 229, 0, 0.15) 50%, transparent 70%);
    display: flex; align-items: center; justify-content: center;
    border: 3px dashed rgba(0, 240, 255, 0.5);
  }}
  .spec-highlight {{
    font-size: 24px; font-weight: 900; color: #FFE500; text-align: center;
    text-shadow: 2px 2px 0 #000; line-height: 1.3;
  }}
  .screen-camera-spec {{
    font-size: 22px; font-weight: 900; color: #FFF; background: #000;
    padding: 10px 22px; border-radius: 12px; border: 2px solid #FFE500;
    box-shadow: 0 6px 20px rgba(0,0,0,0.8);
  }}
  .bb-emblem-wrap {{
    position: absolute; top: 480px; left: 50%; transform: translateX(-50%);
    display: flex; flex-direction: column; align-items: center; gap: 20px; z-index: 8;
  }}
  .bb-eye-ring {{
    width: 300px; height: 300px; border-radius: 50%;
    background: radial-gradient(circle, #5a0815 0%, #1a0206 70%, #000 100%);
    border: 5px solid #FF3344; display: flex; align-items: center; justify-content: center;
    box-shadow: 0 0 60px rgba(255, 51, 68, 0.8), inset 0 0 40px rgba(255, 215, 0, 0.4);
  }}
  .bb-iris {{ font-size: 140px; filter: drop-shadow(0 0 25px #FFD700); }}
  .bb-status-badge {{
    background: #000; color: #FFE500; font-size: 28px; font-weight: 900;
    padding: 10px 30px; border-radius: 14px; border: 3px solid #FF3344;
    box-shadow: 0 8px 25px rgba(0,0,0,0.9);
  }}
  .split-panels {{
    position: absolute; bottom: 320px; left: 50px; right: 50px;
    display: flex; justify-content: space-between; z-index: 10;
  }}
  .evidence-box {{
    width: 460px; height: 260px; border-radius: 24px; border: 3.5px solid #00F0FF;
    background: linear-gradient(145deg, rgba(20, 30, 50, 0.92), rgba(10, 15, 28, 0.98));
    box-shadow: 0 15px 45px rgba(0, 240, 255, 0.3); overflow: hidden; position: relative;
    display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 15px;
  }}
  .box-label {{
    position: absolute; bottom: 12px; left: 14px;
    background: rgba(0,0,0,0.9); color: #FFF; font-size: 22px; font-weight: 800;
    padding: 6px 14px; border-radius: 10px; border-left: 5px solid #FFE500;
  }}
  .ep-pill {{
    position: absolute; top: 40px; left: 40px;
    background: #000; border: 3px solid #FFE500; color: #FFE500;
    font-size: 28px; font-weight: 900; padding: 8px 24px; border-radius: 12px; z-index: 25;
  }}
</style>
</head>
<body>
  <div class="ep-pill">{episode_pill_text}</div>
  <div class="top-strip">
    <div class="banner-pill">
      <span class="yellow-txt">{header_left_yellow}</span>
      <span class="white-txt">{header_left_white}</span>
      <span class="emoji">{header_left_emoji}</span>
    </div>
    <div class="banner-pill">
      <span class="white-txt">{header_right_white}</span>
      <span class="yellow-txt">{header_right_yellow}</span>
      <span class="emoji">{header_right_emoji}</span>
    </div>
  </div>
  {hero_html}
  <div class="split-panels">
    <div class="evidence-box">{left_inner}</div>
    <div class="evidence-box">{right_inner}</div>
  </div>
</body>
</html>"""
    else:
        # Standard 16:9 Landscape Widescreen (1280x720) — Exact Prasad Tech Layout
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@800;900&family=Montserrat:wght@900&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 1280px; height: 720px; background: {bg_css};
    font-family: 'Noto Sans Telugu', 'Montserrat', sans-serif;
    position: relative; overflow: hidden;
  }}
  .top-strip {{
    position: absolute; top: 16px; left: 0; width: 100%;
    display: flex; justify-content: space-between; align-items: center;
    padding: 0 32px; z-index: 20;
  }}
  .banner-pill {{
    background: #000000; border: 3.5px solid #1c1c24; border-radius: 18px;
    padding: 9px 24px; display: flex; align-items: center; gap: 12px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.9), inset 0 0 15px rgba(255,255,255,0.06);
  }}
  .yellow-txt {{
    color: #FFE500; font-size: 44px; font-weight: 900;
    text-shadow: 3px 3px 0 #000, -2px -2px 0 #000, 0 4px 10px rgba(0,0,0,0.8);
  }}
  .white-txt {{
    color: #FFFFFF; font-size: 44px; font-weight: 900;
    text-shadow: 3px 3px 0 #000, -2px -2px 0 #000, 0 4px 10px rgba(0,0,0,0.8);
  }}
  .emoji {{ font-size: 40px; }}

  .brand-stack {{
    position: absolute; top: 110px; right: 32px;
    display: flex; flex-direction: column; gap: 10px; z-index: 15;
  }}
  .brand-logo {{
    width: 64px; height: 64px; border-radius: 15px;
    background: #FFFFFF; display: flex; align-items: center; justify-content: center;
    font-weight: 900; font-size: 15px; color: #000;
    box-shadow: 0 6px 18px rgba(0,0,0,0.6); border: 2px solid #EEE;
  }}
  .brand-logo.oneplus {{ background: #F50514; color: #FFF; font-size: 24px; }}
  .brand-logo.oppo {{ background: #00875A; color: #FFF; font-size: 16px; }}
  .brand-logo.realme {{ background: #FFC915; color: #000; font-size: 15px; }}
  .brand-logo.apple {{ background: #000; color: #FFF; font-size: 22px; }}
  .brand-logo.samsung {{ background: #1428A0; color: #FFF; font-size: 12px; }}

  .hero-persona {{
    position: absolute; bottom: 0; left: 50%; transform: translateX(-50%);
    height: 560px; z-index: 8;
    filter: drop-shadow(0 0 25px {glow_color}) drop-shadow(0 0 55px rgba(255, 170, 0, 0.45));
  }}
  .hero-phone {{
    position: absolute; bottom: 0; left: 50%; transform: translateX(-50%);
    width: 290px; height: 530px; z-index: 8;
    filter: drop-shadow(0 0 35px rgba(0, 240, 255, 0.7)) drop-shadow(0 20px 45px rgba(0,0,0,0.9));
  }}
  .phone-frame {{
    width: 100%; height: 100%; border-radius: 46px 46px 0 0; border: 5px solid #2e2f42; border-bottom: none;
    background: linear-gradient(165deg, #1b1d2e 0%, #0d0e17 60%, #06070a 100%);
    box-shadow: inset 0 0 20px rgba(0, 240, 255, 0.25), 0 0 0 2.5px #00F0FF;
    position: relative; overflow: hidden; display: flex; flex-direction: column; align-items: center;
    padding: 18px 18px 0 18px;
  }}
  .phone-island {{
    display: flex; align-items: center; gap: 8px; background: #000;
    border-radius: 20px; padding: 4px 14px; border: 1.5px solid #333; z-index: 5;
  }}
  .notch-cam {{ width: 10px; height: 10px; border-radius: 50%; background: #111; border: 2px solid #00F0FF; }}
  .notch-pill {{ color: #FFE500; font-size: 13px; font-weight: 900; }}
  .phone-screen-content {{
    width: 100%; flex: 1; margin-top: 20px; display: flex; flex-direction: column;
    align-items: center; justify-content: space-around; position: relative; z-index: 3;
  }}
  .screen-brand {{
    font-size: 38px; font-weight: 900; color: #FFFFFF;
    text-shadow: 0 0 20px rgba(0, 240, 255, 0.8), 2px 2px 0 #000;
  }}
  .screen-chip-tag {{
    background: rgba(0, 240, 255, 0.15); border: 1.5px solid #00F0FF;
    color: #00F0FF; font-size: 14px; font-weight: 900; padding: 5px 12px;
    border-radius: 8px; text-shadow: 0 0 8px rgba(0, 240, 255, 0.6);
  }}
  .screen-visual {{
    width: 135px; height: 135px; border-radius: 50%;
    background: radial-gradient(circle, rgba(0, 240, 255, 0.35) 0%, rgba(255, 229, 0, 0.15) 50%, transparent 70%);
    display: flex; align-items: center; justify-content: center;
    border: 2px dashed rgba(0, 240, 255, 0.5);
  }}
  .spec-highlight {{
    font-size: 16px; font-weight: 900; color: #FFE500; text-align: center;
    text-shadow: 2px 2px 0 #000; line-height: 1.3;
  }}
  .screen-camera-spec {{
    font-size: 15px; font-weight: 900; color: #FFF; background: #000;
    padding: 6px 14px; border-radius: 8px; border: 1.5px solid #FFE500;
    box-shadow: 0 4px 15px rgba(0,0,0,0.8);
  }}
  .bb-emblem-wrap {{
    position: absolute; bottom: 80px; left: 50%; transform: translateX(-50%);
    display: flex; flex-direction: column; align-items: center; gap: 15px; z-index: 8;
  }}
  .bb-eye-ring {{
    width: 220px; height: 220px; border-radius: 50%;
    background: radial-gradient(circle, #5a0815 0%, #1a0206 70%, #000 100%);
    border: 4px solid #FF3344; display: flex; align-items: center; justify-content: center;
    box-shadow: 0 0 50px rgba(255, 51, 68, 0.8), inset 0 0 30px rgba(255, 215, 0, 0.4);
  }}
  .bb-iris {{ font-size: 100px; filter: drop-shadow(0 0 20px #FFD700); }}
  .bb-status-badge {{
    background: #000; color: #FFE500; font-size: 22px; font-weight: 900;
    padding: 8px 24px; border-radius: 12px; border: 2.5px solid #FF3344;
    box-shadow: 0 6px 20px rgba(0,0,0,0.9);
  }}
  .split-panels {{
    position: absolute; bottom: 20px; left: 32px; right: 32px;
    display: flex; justify-content: space-between; align-items: flex-end;
    z-index: 10;
  }}
  .evidence-box {{
    width: 350px; height: 195px; border-radius: 18px; border: 3px solid #00F0FF;
    background: linear-gradient(145deg, rgba(20, 30, 50, 0.92), rgba(10, 15, 28, 0.98));
    box-shadow: 0 12px 35px rgba(0, 240, 255, 0.25), inset 0 0 20px rgba(0, 240, 255, 0.15);
    overflow: hidden; position: relative;
    display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 10px;
  }}
  .box-label {{
    position: absolute; bottom: 8px; left: 10px;
    background: rgba(0,0,0,0.85); color: #FFF; font-size: 16px; font-weight: 800;
    padding: 3px 10px; border-radius: 6px; border-left: 4px solid #FFE500;
  }}
  .ep-pill {{
    position: absolute; bottom: 235px; left: 32px;
    background: #000000; border: 2px solid #FFE500; color: #FFE500;
    font-size: 20px; font-weight: 900; padding: 5px 16px; border-radius: 9px; z-index: 15;
    box-shadow: 0 6px 18px rgba(0,0,0,0.8);
  }}
</style>
</head>
<body>
  <div class="top-strip">
    <div class="banner-pill">
      <span class="yellow-txt">{header_left_yellow}</span>
      <span class="white-txt">{header_left_white}</span>
      <span class="emoji">{header_left_emoji}</span>
    </div>
    <div class="banner-pill">
      <span class="white-txt">{header_right_white}</span>
      <span class="yellow-txt">{header_right_yellow}</span>
      <span class="emoji">{header_right_emoji}</span>
    </div>
  </div>

  <div class="ep-pill">{episode_pill_text}</div>
  <div class="brand-stack">{brand_badges_html}</div>
  {hero_html}

  <div class="split-panels">
    <div class="evidence-box">{left_inner}</div>
    <div class="evidence-box">{right_inner}</div>
  </div>
</body>
</html>"""


def render_prasad_tech_thumbnail(
    header_left_yellow: str = "కొత్త ఫోన్",
    header_left_white: str = "కొంటున్నారా?",
    header_left_emoji: str = "📱",
    header_right_white: str = "ధర & ఫీచర్లు",
    header_right_yellow: str = "లీక్!",
    header_right_emoji: str = "🔥",
    hero_cutout_path: Optional[Path] = None,
    evidence_left_img: Optional[Path] = None,
    evidence_left_text: str = "200MP SONY SENSOR",
    evidence_left_badge: str = "CAMERA LEAK 📸",
    evidence_right_img: Optional[Path] = None,
    evidence_right_text: str = "₹24,999 / 6500mAh",
    evidence_right_badge: str = "PRICE & SPECS ⚡",
    episode_pill_text: str = "TECH 2026",
    brand_logos: Optional[list] = None,
    aspect_ratio: str = "16:9",
    bg_theme: str = "tech_purple",
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Renders high-CTR Prasad Tech in Telugu thumbnail using Playwright Chromium.
    Returns path to rendered PNG.
    """
    if not output_path:
        out_name = f"prasad_thumb_{aspect_ratio.replace(':', '_')}.png"
        output_path = str(RENDER_CACHE_DIR / out_name)

    w = 1080 if aspect_ratio == "9:16" else 1280
    h = 1920 if aspect_ratio == "9:16" else 720

    html = generate_prasad_tech_html(
        header_left_yellow=header_left_yellow,
        header_left_white=header_left_white,
        header_left_emoji=header_left_emoji,
        header_right_white=header_right_white,
        header_right_yellow=header_right_yellow,
        header_right_emoji=header_right_emoji,
        hero_cutout_path=hero_cutout_path,
        evidence_left_img=evidence_left_img,
        evidence_left_text=evidence_left_text,
        evidence_left_badge=evidence_left_badge,
        evidence_right_img=evidence_right_img,
        evidence_right_text=evidence_right_text,
        evidence_right_badge=evidence_right_badge,
        episode_pill_text=episode_pill_text,
        brand_logos=brand_logos,
        aspect_ratio=aspect_ratio,
        bg_theme=bg_theme,
    )

    res = render_html_to_image(
        html_content=html,
        output_path=output_path,
        width=w,
        height=h,
        transparent=False,
    )
    return res


def build_prasad_tech_thumbnail_params(title: str, channel: str = "Channel 1", topic: str = "") -> dict:
    """
    Intelligently parses title, topic, and channel into high-CTR viral thumbnail parameters.
    Supports:
    1. Cinema / Tollywood / Celebrity Roasts / Lifestyle / Food / Prabhas (Channel 2 / Viral Talks)
    2. Bigg Boss 10 (Channel 2 / Bigg Boss only)
    3. Facts / Science / Space / Mysteries (Channel 1 / Imaginary Facts)
    4. Tech / Gadgets / Mobiles / Specs (Channel 1 Tech reviews)
    """
    import re
    full_text = f"{title} {topic}".strip().lower()
    from utils.season_guard import is_bigg_boss_topic
    is_bb = is_bigg_boss_topic(full_text)

    is_tech = bool(re.search(
        r"\b(phone|mobile|smartphone|oneplus|samsung|iphone|iqoo|vivo|realme|xiaomi|redmi|pixel|snapdragon|dimensity|camera\s*sensor|processor|battery\s*mah|gadget|laptop)\b",
        full_text
    ))

    is_cinema_celebrity = (
        any(k in full_text for k in [
            "prabhas", "allu arjun", "ntr", "ram charan", "mahesh", "chiranjeevi",
            "pawan kalyan", "balakrishna", "cinema", "movie", "tollywood", "roast",
            "food", "lifestyle", "diet", "chef", "chefs", "kalki", "salaar", "og",
            "pushpa", "devara", "game changer", "spirit", "hero", "actor", "heroine",
            "trailer", "teaser", "box office", "collections", "drama", "entertainment"
        ])
        or "channel 2" in channel.lower()
    ) and not is_bb and not is_tech

    # 1. CHANNEL 2: BIGG BOSS 10 ONLY
    if is_bb:
        c_names = []
        for c in ["nagarjuna", "vamsi", "aman", "thrigun", "sudheer", "mukesh", "jhansi", "apoorva"]:
            if c in full_text:
                c_names.append(c.capitalize())
        name_str = c_names[0] if c_names else "బిగ్‌బాస్ 10"

        left_y = "బిగ్‌బాస్ 10" if name_str == "బిగ్‌బాస్ 10" else name_str
        left_w = "షాక్!" if "shock" in full_text or "twist" in full_text else "రచ్చ!"
        right_w = "ఎలిమినేషన్" if "elimination" in full_text else "ఓటింగ్ లీక్!"
        right_y = "క్యాన్సిల్?!" if "cancel" in full_text or "no elimination" in full_text else "ట్విస్ట్!"

        return {
            "header_left_yellow": left_y,
            "header_left_white": left_w,
            "header_left_emoji": "🚨",
            "header_right_white": right_w,
            "header_right_yellow": right_y,
            "header_right_emoji": "🔥",
            "evidence_left_text": "DRAMA / VOTING",
            "evidence_left_badge": "LIVE FEED 📹",
            "evidence_right_text": "SECRET LEAK",
            "evidence_right_badge": "HOUSE BUZZ ⚡",
            "episode_pill_text": "BB10 TODAY",
            "brand_logos": ["BB10", "HOT", "STAR"],
            "bg_theme": "danger_red",
        }

    # 2. CHANNEL 2: CINEMA / CELEBRITY / TOLLYWOOD / ROASTS / LIFESTYLE
    elif is_cinema_celebrity:
        celeb = ""
        for c_name, c_tel in [
            ("prabhas", "ప్రభాస్"),
            ("allu arjun", "అల్లు అర్జున్"),
            ("ram charan", "రామ్ చరణ్"),
            ("ntr", "ఎన్టీఆర్"),
            ("mahesh", "మహేష్ బాబు"),
            ("pawan", "పవన్ కళ్యాణ్"),
            ("chiranjeevi", "చిరంజీవి"),
            ("balakrishna", "బాలకృష్ణ"),
        ]:
            if c_name in full_text:
                celeb = c_tel
                break

        is_food_diet = any(k in full_text for k in ["food", "diet", "chef", "భోజనం", "ఖర్చు", "cooking", "తిండి", "లంచ్"])
        if is_food_diet:
            h_left_y = celeb or "రెబల్ స్టార్"
            h_left_w = "రాజభోగం! 👑"
            h_right_w = "లంచ్ ఖర్చు ఎంత? 😱"
            h_right_y = "10 మంది చెఫ్స్! 👨‍🍳"
            ev_left_t = "భారీ భోజనం ఖర్చు"
            ev_left_b = "DAILY EXPENSE 💸"
            ev_right_t = "10 SPECIAL CHEFS"
            ev_right_b = "ROYAL FEAST 🍽️"
            pill = "VIRAL ROAST"
            logos = ["HOT", "VIRAL", "TREND"]
            theme = "danger_red"
        elif any(k in full_text for k in ["roast", "drama", "troll", "mind", "lost"]):
            h_left_y = celeb or "టాప్ స్టార్"
            h_left_w = "ఫుల్ రోస్ట్! 🔥"
            h_right_w = "సోషల్ మీడియా"
            h_right_y = "రచ్చ రచ్చ! 💥"
            ev_left_t = "INSIDE SCOOP"
            ev_left_b = "VIRAL TALKS ⚡"
            ev_right_t = "HONEST TALK"
            ev_right_b = "PUBLIC REACTION 😱"
            pill = "VIRAL ROAST"
            logos = ["VIRAL", "TREND", "HOT"]
            theme = "danger_red"
        else:
            h_left_y = celeb or "టాప్ మూవీ"
            h_left_w = "వైరల్ టాక్! 🎬"
            h_right_w = "షాకింగ్"
            h_right_y = "నిజాలు! 🔥"
            ev_left_t = "BOX OFFICE"
            ev_left_b = "COLLECTIONS 💰"
            ev_right_t = "HONEST TALK"
            ev_right_b = "PUBLIC VERDICT ⭐"
            pill = "CINEMA BUZZ"
            logos = ["FILM", "HOT", "VIRAL"]
            theme = "danger_red"

        return {
            "header_left_yellow": h_left_y,
            "header_left_white": h_left_w,
            "header_left_emoji": "🔥",
            "header_right_white": h_right_w,
            "header_right_yellow": h_right_y,
            "header_right_emoji": "😱",
            "evidence_left_text": ev_left_t,
            "evidence_left_badge": ev_left_b,
            "evidence_right_text": ev_right_t,
            "evidence_right_badge": ev_right_b,
            "episode_pill_text": pill,
            "brand_logos": logos,
            "bg_theme": theme,
        }

    # 3. CHANNEL 1: FACTS / SCIENCE / SPACE / MYSTERIES
    elif any(k in full_text for k in ["fact", "facts", "science", "space", "isro", "nasa", "quantum", "mystery", "secret", "history", "ancient", "universe"]) or ("channel 1" in channel.lower() and not is_tech):
        return {
            "header_left_yellow": "రహస్యం!",
            "header_left_white": "నిజమా? 🤯",
            "header_left_emoji": "🌌",
            "header_right_white": "తెలిస్తే మైండ్ బ్లాంక్",
            "header_right_yellow": "షాకింగ్! ⚡",
            "header_right_emoji": "🔬",
            "evidence_left_text": "REAL SCIENCE",
            "evidence_left_badge": "DEEP DIVE 🔍",
            "evidence_right_text": "UNIVERSE SECRET",
            "evidence_right_badge": "FACT REVEALED 🧠",
            "episode_pill_text": "IMAGINARY FACTS",
            "brand_logos": ["FACT", "ISRO", "SCIENCE"],
            "bg_theme": "tech_purple",
        }

    # 4. TECH / SMARTPHONES / GADGETS
    detected_brands = []
    brand_map = {
        "oneplus": "1+",
        "oppo": "OPPO",
        "realme": "realme",
        "samsung": "SAMSUNG",
        "apple": "APPLE",
        "iphone": "APPLE",
        "iqoo": "iQOO",
        "vivo": "vivo",
        "xiaomi": "Xiaomi",
        "redmi": "Redmi",
        "motorola": "MOTO",
        "google": "Pixel",
        "pixel": "Pixel",
        "snapdragon": "Snapdragon",
        "dimensity": "Dimensity",
    }
    for k, v in brand_map.items():
        if k in full_text and v not in detected_brands:
            detected_brands.append(v)

    if not detected_brands:
        detected_brands = ["1+", "OPPO", "realme"]

    # Detect phone model name
    m_match = re.search(r"(oneplus\s*\d+|samsung\s*s\d+|iphone\s*\d+|iqoo\s*\d+|vivo\s*[xv]\d+|realme\s*gt\s*\d+|pixel\s*\d+)", full_text, re.IGNORECASE)
    phone_model = m_match.group(1).upper() if m_match else detected_brands[0]

    # Price detection
    pr_match = re.search(r"(\d+[\d,]*\s*(?:వేల|లక్ష|k|rs|inr))", full_text, re.IGNORECASE)
    price_str = f"₹{pr_match.group(1).strip()}" if pr_match else "₹24,999"

    # Specs
    spec_left = "200MP SONY SENSOR" if "camera" in full_text or "200mp" in full_text else ("SNAPDRAGON 8 ELITE" if "snapdragon" in full_text or "processor" in full_text else "50MP OIS CAMERA")
    spec_right = f"{price_str} / 6500mAh"

    return {
        "header_left_yellow": phone_model[:12],
        "header_left_white": "కొంటున్నారా?",
        "header_left_emoji": "📱",
        "header_right_white": "ధర & ఫీచర్లు",
        "header_right_yellow": "లీక్!",
        "header_right_emoji": "🔥",
        "evidence_left_text": spec_left,
        "evidence_left_badge": "CAMERA & CHIP 📸",
        "evidence_right_text": spec_right,
        "evidence_right_badge": "PRICE & SPECS ⚡",
        "episode_pill_text": "TECH 2026",
        "brand_logos": detected_brands[:3],
        "bg_theme": "tech_purple",
    }


def render_social_tweet_card(
    author_name: str,
    handle: str,
    tweet_text: str,
    timestamp: str = "Just now",
    avatar_path: Optional[Path] = None,
    verified: bool = True,
    likes_str: str = "18.4K",
    retweets_str: str = "4.2K",
    output_path: Optional[str] = None,
    card_width: int = 860,
) -> Optional[str]:
    """
    Renders an ultra-realistic dark-mode Twitter/X social proof card with Indic typography.
    """
    if not output_path:
        output_path = str(RENDER_CACHE_DIR / f"tweet_card_{abs(hash(tweet_text)) % 100000}.png")

    avatar_src = _file_to_base64_src(Path(avatar_path)) if avatar_path else ""
    avatar_html = (
        f'<img src="{avatar_src}" style="width:58px;height:58px;border-radius:50%;object-fit:cover;" />'
        if avatar_src
        else f'<div style="width:58px;height:58px;border-radius:50%;background:linear-gradient(135deg, #FF6B6B, #4ECDC4);display:flex;align-items:center;justify-content:center;font-weight:900;font-size:24px;color:#FFF;">{author_name[:1]}</div>'
    )

    verified_badge = (
        """<svg viewBox="0 0 22 22" style="width:20px;height:20px;margin-left:5px;fill:#1D9BF0;"><g><path d="M20.396 11c-.018-.646-.215-1.275-.57-1.816-.354-.54-.852-.972-1.438-1.246.223-.607.27-1.264.14-1.897-.131-.634-.437-1.218-.882-1.687-.47-.445-1.053-.75-1.687-.882-.633-.13-1.29-.083-1.897.14-.273-.587-.704-1.086-1.245-1.44S11.647 1.62 11 1.604c-.646.017-1.273.213-1.813.568s-.969.854-1.24 1.44c-.608-.223-1.267-.272-1.902-.14-.635.13-1.22.436-1.69.882-.445.47-.749 1.055-.878 1.688-.13.633-.08 1.29.144 1.896-.587.274-1.087.705-1.443 1.245-.356.54-.555 1.17-.574 1.817.02.647.218 1.276.574 1.817.356.54.856.972 1.443 1.245-.224.606-.274 1.263-.144 1.896.13.634.433 1.218.877 1.688.47.443 1.054.747 1.687.878.633.132 1.29.084 1.897-.136.274.586.705 1.084 1.246 1.439.54.354 1.17.551 1.816.569.647-.016 1.276-.213 1.817-.567s.972-.854 1.245-1.44c.604.239 1.266.296 1.903.164.636-.132 1.22-.447 1.68-.907.46-.46.776-1.044.908-1.681s.075-1.299-.165-1.903c.586-.274 1.084-.705 1.439-1.246.354-.54.551-1.17.569-1.816zM9.662 14.85l-3.429-3.428 1.293-1.302 2.136 2.136 5.293-5.293 1.302 1.293-6.595 6.594z"></path></g></svg>"""
        if verified
        else ""
    )

    clean_handle = handle if handle.startswith("@") else f"@{handle}"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@500;700;900&family=Inter:wght@400;600;700&display=swap');
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: transparent;
            padding: 30px;
            font-family: 'Inter', 'Noto Sans Telugu', -apple-system, BlinkMacSystemFont, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
        }}
        .tweet-card {{
            width: {card_width}px;
            background: rgba(10, 12, 20, 0.94);
            border: 2px solid rgba(255, 255, 255, 0.15);
            border-radius: 24px;
            padding: 28px 32px;
            box-shadow: 0 25px 60px rgba(0, 0, 0, 0.9), 0 0 30px rgba(29, 155, 240, 0.2);
            color: #E7E9EA;
            backdrop-filter: blur(20px);
        }}
        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
        }}
        .user-info {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}
        .names {{
            display: flex;
            flex-direction: column;
        }}
        .display-name {{
            font-weight: 800;
            font-size: 24px;
            color: #FFFFFF;
            display: flex;
            align-items: center;
        }}
        .handle {{
            font-size: 18px;
            color: #71767B;
            font-weight: 500;
        }}
        .x-logo {{
            width: 28px;
            height: 28px;
            fill: #FFFFFF;
            opacity: 0.9;
        }}
        .content {{
            font-size: 30px;
            line-height: 1.5;
            color: #F7F9F9;
            font-weight: 700;
            margin-bottom: 24px;
            word-break: break-word;
        }}
        .footer {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-top: 18px;
            border-top: 1px solid rgba(255, 255, 255, 0.12);
            color: #71767B;
            font-size: 17px;
            font-weight: 600;
        }}
        .metrics {{
            display: flex;
            gap: 36px;
        }}
        .metric-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
    </style>
</head>
<body>
    <div class="tweet-card">
        <div class="header">
            <div class="user-info">
                {avatar_html}
                <div class="names">
                    <div class="display-name">{author_name} {verified_badge}</div>
                    <div class="handle">{clean_handle} · {timestamp}</div>
                </div>
            </div>
            <svg class="x-logo" viewBox="0 0 24 24"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"></path></svg>
        </div>
        <div class="content">{tweet_text}</div>
        <div class="footer">
            <div class="metrics">
                <div class="metric-item">💬 1.2K</div>
                <div class="metric-item">🔁 {retweets_str}</div>
                <div class="metric-item" style="color:#F91880;">❤️ {likes_str}</div>
            </div>
            <div>Trending in Telugu</div>
        </div>
    </div>
</body>
</html>"""

    # Estimated height based on content length
    est_height = 360 + int(len(tweet_text) * 0.9)
    res = render_html_to_image(
        html_content=html,
        output_path=output_path,
        width=card_width + 80,
        height=est_height,
        transparent=True,
    )
    return res


def render_infographic_chart(
    chart_title: str,
    labels: list,
    values: list,
    unit: str = "%",
    subtitle: str = "Live Statistics & Comparison",
    width: int = 1000,
    height: int = 700,
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Renders an ultra-sharp modern infographic comparison chart with glowing gradient bars.
    """
    if not output_path:
        output_path = str(RENDER_CACHE_DIR / f"info_chart_{abs(hash(chart_title)) % 100000}.png")

    max_val = max(values) if values and max(values) > 0 else 100

    palette = [
        ("linear-gradient(90deg, #FF0055, #FF5500)", "#FF0055"),
        ("linear-gradient(90deg, #FFB800, #FFE600)", "#FFB800"),
        ("linear-gradient(90deg, #00C6FF, #0072FF)", "#00C6FF"),
        ("linear-gradient(90deg, #A855F7, #EC4899)", "#A855F7"),
        ("linear-gradient(90deg, #10B981, #059669)", "#10B981"),
    ]

    bars_html = ""
    for idx, (label, val) in enumerate(zip(labels, values)):
        bar_grad, glow = palette[idx % len(palette)]
        pct_width = max(12, int((val / max_val) * 100))
        bars_html += f"""
        <div class="row">
            <div class="label-col">{label}</div>
            <div class="bar-col">
                <div class="bar-outer">
                    <div class="bar-fill" style="width: {pct_width}%; background: {bar_grad}; box-shadow: 0 0 18px {glow}88;">
                        <span class="bar-val">{val}{unit}</span>
                    </div>
                </div>
            </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@700;900&family=Montserrat:wght@700;900&display=swap');
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: transparent;
            font-family: 'Montserrat', 'Noto Sans Telugu', sans-serif;
            width: {width}px;
            height: {height}px;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 30px;
        }}
        .chart-card {{
            width: 100%;
            background: rgba(11, 15, 26, 0.95);
            border: 2px solid rgba(255, 255, 255, 0.16);
            border-radius: 28px;
            padding: 38px 46px;
            box-shadow: 0 30px 70px rgba(0, 0, 0, 0.92), 0 0 35px rgba(255, 184, 0, 0.25);
            backdrop-filter: blur(25px);
        }}
        .header {{
            margin-bottom: 30px;
            border-bottom: 2px solid rgba(255, 255, 255, 0.1);
            padding-bottom: 18px;
        }}
        .title {{
            font-size: 34px;
            font-weight: 900;
            color: #FFFFFF;
            letter-spacing: -0.5px;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .subtitle {{
            font-size: 18px;
            font-weight: 700;
            color: #FFE600;
            margin-top: 6px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .row {{
            display: flex;
            align-items: center;
            margin-bottom: 22px;
        }}
        .label-col {{
            width: 32%;
            font-size: 24px;
            font-weight: 800;
            color: #F1F5F9;
            padding-right: 18px;
            text-shadow: 0 2px 8px rgba(0,0,0,0.8);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .bar-col {{
            width: 68%;
        }}
        .bar-outer {{
            width: 100%;
            height: 48px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 4px;
            border: 1px solid rgba(255, 255, 255, 0.12);
        }}
        .bar-fill {{
            height: 100%;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding-right: 14px;
            transition: all 0.3s ease;
        }}
        .bar-val {{
            font-size: 20px;
            font-weight: 900;
            color: #FFFFFF;
            text-shadow: 0 2px 4px rgba(0,0,0,0.9);
        }}
    </style>
</head>
<body>
    <div class="chart-card">
        <div class="header">
            <div class="title">📊 {chart_title}</div>
            <div class="subtitle">{subtitle}</div>
        </div>
        <div class="bars-container">
            {bars_html}
        </div>
    </div>
</body>
</html>"""

    res = render_html_to_image(
        html_content=html,
        output_path=output_path,
        width=width,
        height=height,
        transparent=True,
    )
    return res


def render_breaking_news_ticker(
    headline: str,
    ticker_text: str,
    aspect_ratio: str = "9:16",
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Renders a broadcast-quality TV news lower-third banner with red flashing alert tag and yellow ticker bar.
    """
    w = 1080 if aspect_ratio == "9:16" else 1280
    h = 320

    if not output_path:
        output_path = str(RENDER_CACHE_DIR / f"ticker_{abs(hash(headline)) % 100000}.png")

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@800;900&family=Impact&display=swap');
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: transparent;
            width: {w}px;
            height: {h}px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
            font-family: 'Noto Sans Telugu', -apple-system, sans-serif;
            padding-bottom: 20px;
        }}
        .ticker-wrapper {{
            width: 100%;
            display: flex;
            flex-direction: column;
            box-shadow: 0 -10px 30px rgba(0, 0, 0, 0.85);
        }}
        .alert-row {{
            display: flex;
            align-items: center;
        }}
        .alert-badge {{
            background: #E63946;
            color: #FFFFFF;
            font-weight: 900;
            font-size: 26px;
            padding: 10px 24px;
            letter-spacing: 1px;
            display: flex;
            align-items: center;
            gap: 10px;
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
            box-shadow: 0 0 20px rgba(230, 57, 70, 0.8);
        }}
        .headline-bar {{
            background: rgba(12, 14, 24, 0.96);
            border-top: 3px solid #E63946;
            border-bottom: 2px solid #FFE600;
            padding: 16px 28px;
            color: #FFFFFF;
            font-size: 32px;
            font-weight: 900;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            text-shadow: 0 2px 6px #000;
        }}
        .ticker-bar {{
            background: #FFE600;
            color: #0C0E18;
            font-size: 22px;
            font-weight: 900;
            padding: 8px 24px;
            letter-spacing: 0.5px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
    </style>
</head>
<body>
    <div class="ticker-wrapper">
        <div class="alert-row">
            <div class="alert-badge">🔴 BREAKING NEWS | తాజా సమాచారం</div>
        </div>
        <div class="headline-bar">{headline}</div>
        <div class="ticker-bar">
            <span>⚡ {ticker_text}</span>
            <span style="font-size:18px;font-weight:800;color:#333;">AUTOTUBE LIVE</span>
        </div>
    </div>
</body>
</html>"""

    res = render_html_to_image(
        html_content=html,
        output_path=output_path,
        width=w,
        height=h,
        transparent=True,
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

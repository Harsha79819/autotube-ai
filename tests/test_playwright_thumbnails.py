"""
Unit tests for Playwright Canva-Pro thumbnail renderer and browser harvester.
"""

import unittest
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

from agents.thumbnail_agent import create_playwright_canva_thumbnail
from tools.playwright_renderer import render_canva_pro_thumbnail, render_html_to_image


class TestPlaywrightThumbnails(unittest.TestCase):

    def setUp(self):
        self.test_dir = ROOT / "output" / "test_pw_thumbs"
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def test_render_html_to_image_basic(self):
        html = "<div style='width:400px;height:200px;background:#E63946;color:#FFFFFF;font-size:24px;display:flex;align-items:center;justify-content:center;'>Playwright Test</div>"
        out_p = self.test_dir / "basic.png"
        res = render_html_to_image(html, str(out_p), width=400, height=200)
        self.assertIsNotNone(res)
        self.assertTrue(out_p.exists())
        self.assertGreater(out_p.stat().st_size, 500)

    def test_render_canva_pro_thumbnail_16_9(self):
        out_p = self.test_dir / "canva_16_9.png"
        res = render_canva_pro_thumbnail(
            badge_text="ఎలిమినేషన్ షాక్?!",
            aspect_ratio="16:9",
            border_color="#E63946",
            output_path=str(out_p),
        )
        self.assertIsNotNone(res)
        self.assertTrue(out_p.exists())
        with Image.open(out_p) as img:
            self.assertEqual(img.size, (1280, 720))

    def test_create_playwright_canva_thumbnail_agent(self):
        res = create_playwright_canva_thumbnail(
            title="BIGG BOSS 10 ROHIT ELIMINATION DRAMA",
            aspect_ratio="16:9",
            output_dir=self.test_dir,
        )
        self.assertTrue(Path(res).exists())
        with Image.open(res) as img:
            self.assertEqual(img.size, (1280, 720))


if __name__ == "__main__":
    unittest.main()

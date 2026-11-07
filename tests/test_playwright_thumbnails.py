"""
Unit tests for Playwright Canva-Pro thumbnail renderer, Social Proof cards, Charts, News Tickers, and Community Polls.
"""

import unittest
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

from agents.thumbnail_agent import create_playwright_canva_thumbnail
from tools.playwright_renderer import (
    render_canva_pro_thumbnail,
    render_html_to_image,
    render_social_tweet_card,
    render_infographic_chart,
    render_breaking_news_ticker,
)
from tools.browser_harvester import harvest_live_poll_or_tweet_proof
from tools.community_post_generator import generate_community_poll


class TestPlaywrightSuite(unittest.TestCase):

    def setUp(self):
        self.test_dir = ROOT / "output" / "test_pw_suite"
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

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

    def test_render_social_tweet_card(self):
        out_p = self.test_dir / "tweet_card.png"
        res = render_social_tweet_card(
            author_name="BB Insider Telugu",
            handle="bb_insider",
            tweet_text="బ్రేకింగ్: ఈ వారం అమన్ వర్సెస్ రోహిత్ మధ్య భయంకరమైన గొడవ!",
            output_path=str(out_p),
        )
        self.assertIsNotNone(res)
        self.assertTrue(out_p.exists())
        with Image.open(out_p) as img:
            self.assertGreater(img.size[0], 800)

    def test_render_infographic_chart(self):
        out_p = self.test_dir / "info_chart.png"
        res = render_infographic_chart(
            chart_title="ఈ వారం లైవ్ ఓటింగ్ శాతం",
            labels=["రోహిత్", "వంశీ", "అమన్", "సుధీర్"],
            values=[38, 29, 21, 12],
            output_path=str(out_p),
        )
        self.assertIsNotNone(res)
        self.assertTrue(out_p.exists())
        with Image.open(out_p) as img:
            self.assertEqual(img.size, (1000, 700))

    def test_render_breaking_news_ticker(self):
        out_p = self.test_dir / "news_ticker.png"
        res = render_breaking_news_ticker(
            headline="రోహిత్ పట్నం ఎలిమినేషన్ షాక్?!",
            ticker_text="తాజా సమాచారం: బిగ్ బాస్ హౌస్ లో రచ్చ మొదలైంది..",
            output_path=str(out_p),
        )
        self.assertIsNotNone(res)
        self.assertTrue(out_p.exists())
        with Image.open(out_p) as img:
            self.assertEqual(img.size[1], 320)

    def test_harvest_live_poll_or_tweet_proof(self):
        out_p = self.test_dir / "proof_card.png"
        res = harvest_live_poll_or_tweet_proof(
            topic="Bigg Boss Telugu 10 Voting",
            output_path=str(out_p),
        )
        self.assertIsNotNone(res)
        self.assertTrue(out_p.exists())

    def test_generate_community_poll(self):
        poll = generate_community_poll(
            topic="Bigg Boss 10 Today Elimination",
            output_dir=self.test_dir,
        )
        self.assertIn("poll_question", poll)
        self.assertIn("options", poll)
        self.assertEqual(len(poll["options"]), 4)
        poll_file = self.test_dir / "community_poll.json"
        self.assertTrue(poll_file.exists())


if __name__ == "__main__":
    unittest.main()

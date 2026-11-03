import unittest
from pathlib import Path
from PIL import Image

from data.bb10_contestants import (
    validate_candidate_metadata,
    is_bigg_boss_context,
    check_political_blacklist,
    check_prior_seasons,
)
from tools.news_media_harvester import search_news_article_urls
from providers.image import clean_and_crop_image


class TestEntityDisambiguationAndCanvasGuard(unittest.TestCase):

    def test_political_and_jagan_rejection(self):
        """Ensures YS Jagan, Chandrababu, and political URLs are strictly rejected."""
        ok, reason = validate_candidate_metadata(
            "https://sakshi.com/politics/ys-jagan-press-meet.jpg",
            title="YS Jagan Slams Opposition",
            is_bb=True,
        )
        self.assertFalse(ok)
        self.assertTrue("jagan" in reason.lower() or "politics" in reason.lower())

        ok_url, _ = validate_candidate_metadata(
            "https://www.andhrajyothy.com/telangana/brs-mla-speech.html",
            is_bb=True,
        )
        self.assertFalse(ok_url)

    def test_rohit_disambiguation(self):
        """Ensures Season 6 Rohit Sahni & Marina articles are rejected when querying Rohit."""
        ok_sahni, reason = validate_candidate_metadata(
            "https://tv9telugu.com/entertainment/bigg-boss-season-6-rohit-marina-interview.html",
            title="Rohit Sahni evicted from Bigg Boss",
            entity_hint="Rohit",
            is_bb=True,
        )
        self.assertFalse(ok_sahni)
        self.assertTrue("season-6" in reason.lower() or "sahni" in reason.lower())

        # Valid Season 10 Rohit Patnam should pass
        ok_patnam, _ = validate_candidate_metadata(
            "https://10tv.in/telugu-news/movies/bigg-boss-telugu-10-rohit-patnam-danger.html",
            title="Rohit Patnam in Bigg Boss Telugu 10",
            entity_hint="Rohit",
            is_bb=True,
        )
        self.assertTrue(ok_patnam)

    def test_shalini_disambiguation(self):
        """Ensures Malayalam Season 4 Shalini Nair is rejected."""
        ok_nair, reason = validate_candidate_metadata(
            "https://malayalam.samayam.com/tv/bigg-boss-malayalam/shalini-nair.cms",
            title="Bigg Boss Malayalam Shalini talks about eviction",
            entity_hint="Shalini",
            is_bb=True,
        )
        self.assertFalse(ok_nair)

    def test_prior_seasons_rejection_and_bb10_retention(self):
        """Ensures seasons 1-9 are rejected but season 10 is preserved."""
        for s in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
            ok, _ = validate_candidate_metadata(f"https://example.com/bigg-boss-{s}-finale.jpg", is_bb=True)
            self.assertFalse(ok, f"Season {s} should be rejected")

        # Season 10 should pass
        ok_10, _ = validate_candidate_metadata("https://example.com/bigg-boss-10-grand-launch.jpg", is_bb=True)
        self.assertTrue(ok_10, "Season 10 should pass")

    def test_dynamic_non_bb_topic(self):
        """Ensures non-BB topic is processed without BB injection."""
        self.assertFalse(is_bigg_boss_context("Apple iPhone 18 Pro review specs"))
        self.assertFalse(is_bigg_boss_context("Sensex crashes 800 points as inflation rises"))
        self.assertTrue(is_bigg_boss_context("Bigg Boss Telugu 10 nominations fight"))
        self.assertTrue(is_bigg_boss_context("బిగ్ బాస్ హౌస్ లో రచ్చ"))

    def test_exact_1080x1920_vertical_canvas_guarantee(self):
        """Verifies that non-standard aspect ratios (650x788, square, landscape) are converted to exact 1080x1920."""
        test_dir = Path("data/cache/test_canvas")
        test_dir.mkdir(parents=True, exist_ok=True)

        shapes = [
            (650, 788),   # The exact anomaly from the audit (Asset 11)
            (1280, 720),  # Horizontal 16:9
            (800, 800),   # Square 1:1
            (1080, 1920), # Already exact
        ]

        for idx, (w, h) in enumerate(shapes):
            p = test_dir / f"test_{idx}.jpg"
            Image.new("RGB", (w, h), color=(100 + idx * 20, 80, 150)).save(p)
            clean_and_crop_image(p, aspect_ratio="9:16")
            with Image.open(p) as out_im:
                self.assertEqual(out_im.size, (1080, 1920), f"Shape ({w}, {h}) did not convert to (1080, 1920)")
            p.unlink(missing_ok=True)

        if test_dir.exists():
            test_dir.rmdir()


if __name__ == "__main__":
    unittest.main()

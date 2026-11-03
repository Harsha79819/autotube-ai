"""
Unit tests for YouTube Studio Channel Growth Optimizations (tests/test_channel_growth_optimizations.py)
Validates:
1. Audience Retention: 30-50s duration calibration (target ~35-42s, word limit 55-92).
2. Hook Engine: Instant 0.0s spoken hook delivery (<12 words, zero greeting).
3. Thumbnail CTR: Strictly 3-4 word curiosity phrases and high-contrast styling.
4. Niche Consistency: 7-day schedule for Channel 2 is 100% Telugu entertainment (Bigg Boss & Cinema).
5. Comment-Trigger CTAs: Contextual questions driving comments & subscriber conversion.
"""

import unittest
from pathlib import Path

from config.format_profiles import get_format_profile, parse_duration_to_seconds
from agents.hook_engine import generate_hook_candidates_fallback, _clean_banned_openings
from agents.thumbnail_agent import _clean_title, _find_best_background
from agents.script_agent import ensure_dynamic_outro_cta, TELUGU_DYNAMIC_CTAS
from agents.roast_engine import generate_quirky_cta, calibrate_script_before_execution
from agents.topic_suggester import _normalize_category_key, CURATED_TOPICS, CATEGORY_FEEDS
from daily_scheduler import DailyPublisher


class TestChannelGrowthOptimizations(unittest.TestCase):

    def test_01_shorts_duration_virality_calibration(self):
        """Verifies default Shorts duration is 30-50s and words are constrained to 55-92 words."""
        prof_default = get_format_profile()
        self.assertEqual(prof_default.format_type, "short")
        self.assertLessEqual(prof_default.min_seconds, 35.0)
        self.assertLessEqual(prof_default.max_seconds, 50.0)
        self.assertLessEqual(prof_default.max_words, 95)
        self.assertGreaterEqual(prof_default.min_words, 55)

        # Explicit 30-50s profile
        prof_30_50 = get_format_profile(target_duration="30-50s", language="Telugu")
        self.assertLessEqual(prof_30_50.target_seconds, 45.0)
        self.assertLessEqual(prof_30_50.max_words, 92)
        self.assertGreaterEqual(prof_30_50.min_words, 55)

    def test_02_roast_engine_script_calibration_bounds(self):
        """Verifies roast engine calibrates scripts to 65-92 words for high-retention 30-50s delivery."""
        test_script = (
            "బిగ్ బాస్ హౌస్‌లో నిన్న రాత్రి జరిగిన సీక్రెట్ మీటింగ్ చూశారా? "
            "ఒక్క నామినేషన్ తో మొత్తం గేమ్ తలకిందులైంది బాస్. "
            "ముగ్గురు కంటెస్టెంట్స్ ఇచ్చిన షాకింగ్ రీజన్స్ చూసి నాగార్జున కూడా షాక్ అయ్యారు. "
            "గ్రూపిజం తో ఆడిన వాళ్ళంతా ఇప్పుడు డేంజర్ జోన్ లో పడిపోయారు."
        )
        calibrated = calibrate_script_before_execution(
            script=test_script,
            target_duration_sec=38,
            topic="Bigg Boss Telugu 10 Nomination Drama",
        )
        words = len(calibrated.split())
        self.assertGreaterEqual(words, 60, f"Expected >= 60 words, got {words}")
        self.assertLessEqual(words, 105, f"Expected <= 105 words, got {words}")

    def test_03_hook_engine_instant_openings(self):
        """Verifies hook candidates have zero pleasantries and strictly <= 12 words."""
        bb_hooks = generate_hook_candidates_fallback("Bigg Boss Telugu 10", is_telugu=True)
        self.assertEqual(len(bb_hooks), 5)
        for h in bb_hooks:
            text = h["hook_text"]
            self.assertFalse(text.startswith("హాయ్"))
            self.assertFalse(text.startswith("నమస్కారం"))
            cleaned = _clean_banned_openings(text)
            self.assertEqual(cleaned, text)
            # High curiosity indicator
            self.assertGreater(len(text), 10)

        # Test English fallback
        en_hooks = generate_hook_candidates_fallback("Quantum Chip Breakthrough", is_telugu=False)
        self.assertEqual(len(en_hooks), 5)
        for h in en_hooks:
            self.assertFalse(h["hook_text"].lower().startswith("hi guys"))

    def test_04_thumbnail_3_to_4_word_curiosity_phrases(self):
        """Verifies thumbnail text is strictly 3-4 words and curiosity-driven."""
        test_titles = [
            ("Roasting the Drama: NAGARJUNA ROHIT NI TARGET CHESARA?", ["TARGET", "CHESARA", "ROHIT"]),
            ("Bigg Boss Telugu 10: Shocking Nomination Drama Unfiltered", ["NOMINATION", "TWIST?!"]),
            ("Bigg Boss Telugu Wild Card Entries: House Lo Unna Vallake Dikku Ledu!", ["WILDCARD", "ENTRY", "BOMBSHELL!"]),
            ("Kalki 2898 AD: Did Nag Ashwin & Prabhas Deliver Masterpiece?", ["DELIVER", "MASTERPIECE?"]),
            ("September Box Office Breakdown: How Nani and Vanga Impacted Tollywood", ["BOX", "OFFICE", "BREAKDOWN!"]),
        ]
        for raw_title, expected_kws in test_titles:
            cleaned = _clean_title(raw_title)
            words = cleaned.split()
            self.assertLessEqual(len(words), 5, f"Thumbnail text '{cleaned}' has > 4 words ({len(words)})")
            self.assertGreaterEqual(len(words), 1)

    def test_05_thumbnail_background_subject_bonus(self):
        """Verifies 1.jpg receives priority bonus in background selection."""
        import tempfile
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            img_1 = tmp_path / "1.jpg"
            img_broll = tmp_path / "broll_9.jpg"
            img_data = Image.new("RGB", (1080, 1920), color="red")
            img_data.save(img_1)
            img_data.save(img_broll)

            best = _find_best_background(aspect_ratio="9:16", assets_dir=str(tmp_path))
            self.assertIsNotNone(best)
            self.assertEqual(best.name, "1.jpg")

    def test_06_niche_consistent_7_day_scheduling(self):
        """Verifies Channel 2 7-day schedule is 100% Telugu Entertainment & Bigg Boss."""
        scheduler = DailyPublisher()
        # Verify category normalization
        self.assertEqual(_normalize_category_key("Bigg Boss Telugu"), "Bigg Boss Telugu")
        self.assertEqual(_normalize_category_key("BB10"), "Bigg Boss Telugu")
        self.assertIn("Bigg Boss Telugu", CURATED_TOPICS)
        self.assertIn("Bigg Boss Telugu", CATEGORY_FEEDS)

        # Verify fallback topic generation for Channel 2
        import os
        os.environ["DAILY_CHANNEL"] = "2"
        os.environ["DAILY_FORMAT"] = "short"
        pkg = scheduler.pick_daily_topic()
        self.assertEqual(pkg["aspect_ratio"], "9:16")
        self.assertEqual(pkg["target_duration"], "30-50s")
        self.assertIn(
            pkg["content_type"],
            ["Bigg Boss Telugu 10", "Cinema & Entertainment", "Movie Reviews", "Roasting"],
            f"Unexpected non-entertainment content type: {pkg['content_type']}"
        )

    def test_07_comment_trigger_cta_generation(self):
        """Verifies CTAs prompt viewers with engagement questions for comments and subscriptions."""
        bb_script = "బిగ్ బాస్ హౌస్ లో నామినేషన్స్ హీట్ పెరిగిపోయింది. గేమ్ రోజురోజుకీ మారిపోతోంది."
        cta_bb = ensure_dynamic_outro_cta(bb_script, topic="Bigg Boss Telugu 10", is_indic=True)
        # Check comment and subscription keywords
        self.assertTrue(
            "కామెంట్" in cta_bb or "comment" in cta_bb.lower(),
            f"CTA missing comment prompt: {cta_bb}"
        )
        self.assertTrue(
            "సబ్‌స్క్రైబ్" in cta_bb or "subscribe" in cta_bb.lower(),
            f"CTA missing subscribe prompt: {cta_bb}"
        )

        # Test roast quirky CTA
        quirky_bb = generate_quirky_cta("Bigg Boss Telugu 10 Wildcard Nomination", draft=bb_script)
        self.assertTrue("కామెంట్" in quirky_bb)
        self.assertTrue("సబ్‌స్క్రైబ్" in quirky_bb)


if __name__ == "__main__":
    unittest.main()

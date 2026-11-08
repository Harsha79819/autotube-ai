#!/usr/bin/env python3
"""
tests/test_audit_flaw_fixes_and_interactions.py

Comprehensive Unit & Interaction Test Suite verifying:
1. Elimination status and exclusion of Charan Mahadev in contestant registries & visual matcher.
2. Shruti as default Telugu voice in dashboard.
3. Fallback script expansion in roast_engine without raw English topic dumping.
4. News website image quota expanded and Star Maa promo screengrabs hard-capped to 3 beats.
5. Hook cleanup in pipeline clean_previous_generation().
6. Metadata title typo sanitizer (DUBBLE -> DOUBLE).
7. End-to-end interaction testing across script, visual plan, and metadata generation.
"""

import os
import sys
import json
import unittest
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class TestCharanEliminationGuard(unittest.TestCase):
    """Test Case 1: Verify Charan Mahadev is properly marked as eliminated and excluded."""

    def test_bb10_contestants_status(self):
        from data.bb10_contestants import CONTESTANTS_BB10, is_eliminated_contestant, get_active_contestants
        self.assertIn("charan", CONTESTANTS_BB10)
        charan_data = CONTESTANTS_BB10["charan"]
        self.assertEqual(charan_data.get("status"), "eliminated")
        self.assertFalse(charan_data.get("is_active"))
        self.assertTrue(is_eliminated_contestant("Charan Mahadev"))
        self.assertTrue(is_eliminated_contestant("charan"))
        self.assertTrue(is_eliminated_contestant("చరణ్"))

        active_list = get_active_contestants()
        self.assertNotIn("Charan Mahadev", active_list)
        self.assertNotIn("Rohit Patnam", active_list)
        self.assertNotIn("Shalini Patel", active_list)
        self.assertIn("Temper Vamsi", active_list)
        self.assertTrue(is_eliminated_contestant("Rohit Patnam"))
        self.assertTrue(is_eliminated_contestant("Shalini Patel"))

    def test_season_guard_elimination(self):
        from utils.season_guard import is_contestant_eliminated
        self.assertTrue(is_contestant_eliminated("Charan Mahadev"))
        self.assertTrue(is_contestant_eliminated("Charan"))
        self.assertTrue(is_contestant_eliminated("చరణ్"))
        self.assertTrue(is_contestant_eliminated("Rohit Patnam"))
        self.assertTrue(is_contestant_eliminated("రోహిత్"))
        self.assertTrue(is_contestant_eliminated("Shalini Patel"))
        self.assertTrue(is_contestant_eliminated("శాలిని"))
        self.assertTrue(is_contestant_eliminated("Gundeboina Jhansi"))
        self.assertFalse(is_contestant_eliminated("Temper Vamsi"))
        self.assertFalse(is_contestant_eliminated("Thrigun Eswaran"))

    def test_image_agent_skips_eliminated_contestant_for_general_scenes(self):
        from agents.image_agent import find_local_contestant_image
        # General scene mentioning Charan should be skipped because he is eliminated
        res = find_local_contestant_image("చరణ్ నామినేషన్ గొడవ మరియు రచ్చ")
        self.assertIsNone(res, "Eliminated contestant should not be matched for general nomination scenes")

        # But if the scene is explicitly about elimination/eviction, it can be allowed
        res_evict = find_local_contestant_image("చరణ్ ఎలిమినేషన్ మరియు బిగ్ బాస్ హౌస్ నుండి బయటకు")
        if res_evict is not None:
            slug, path = res_evict
            self.assertEqual(slug, "charan")


class TestAudioVoiceAndRoastExpansion(unittest.TestCase):
    """Test Case 2: Verify Shruti is default Telugu voice and fallback expansion has no raw English."""

    def test_dashboard_telugu_voice_default(self):
        # Inspect dashboard.py source code for Telugu voice ordering
        dash_file = ROOT / "dashboard.py"
        content = dash_file.read_text(encoding="utf-8")
        self.assertIn('"👩 Shruti (Telugu Creator / Anchor) - Conversational",\n                "👨 Mohan (Telugu Creator / Anchor) - Natural Spoken Delivery"', content)

    def test_roast_engine_fallback_expansion_sanitization(self):
        from agents.roast_engine import calibrate_script_before_execution
        raw_topic = "Nagarjuna Bigg Boss controversy explodes as trolls dig up old videos just to roast the host"
        short_script = "అసలు ఈ వీకెండ్ క్లాస్ చూశారా బాస్!"  # Very short script (6 words)

        # Force expansion for 60-90s (target 130 words)
        calibrated = calibrate_script_before_execution(
            script=short_script,
            target_duration_sec=75,
            topic=raw_topic,
            facts=[]
        )

        # Verify that the raw English string was NOT dumped into the Telugu script
        self.assertNotIn("controversy explodes as trolls dig up old videos just to roast the host", calibrated)
        self.assertNotIn("Nagarjuna బిగ్ బాస్ controversy", calibrated)
        # Verify it expanded with Telugu commentary
        self.assertIn("బాస్", calibrated)
        self.assertGreater(len(calibrated.split()), 20)

    def test_roast_engine_prompt_no_charan(self):
        from agents.roast_engine import extract_topic_facts
        # Verify fallback facts do not contain Charan
        facts = extract_topic_facts("Bigg Boss Telugu 10 Test Topic")
        for f in facts:
            self.assertNotIn("Charan", f, f"Charan found in fallback fact: {f}")


class TestWebImageQuotaAndPromoCapping(unittest.TestCase):
    """Test Case 3: Verify news website image harvesting quota and Star Maa promo capping."""

    def test_image_agent_source_limits(self):
        img_agent_file = ROOT / "agents" / "image_agent.py"
        code = img_agent_file.read_text(encoding="utf-8")

        # Verify news harvesting quota is expanded to 8
        self.assertIn("max_news_allowed = 8 if aspect_ratio == \"9:16\" else 10", code)
        self.assertIn("len(used_news_images) < max_news_allowed", code)

        # Verify Star Maa promo is hard-capped at 3 beats
        self.assertIn("max_promo_allowed = 3", code)
        self.assertIn("len(used_promo_images) < max_promo_allowed", code)
        self.assertIn("used_promo_images.add(ps_str)", code)


class TestPipelineCleanupAndMetadataTypo(unittest.TestCase):
    """Test Case 4: Verify hook.json cleanup and title typo corrections."""

    def test_pipeline_clean_previous_generation_removes_hook(self):
        from pipeline import clean_previous_generation, OUTPUT_DIR
        test_hook = OUTPUT_DIR / "hook.json"
        test_hook.write_text('{"topic": "stale test"}', encoding="utf-8")
        self.assertTrue(test_hook.exists())

        clean_previous_generation()
        self.assertFalse(test_hook.exists(), "hook.json should be removed by clean_previous_generation()")

    def test_metadata_agent_title_spellcheck(self):
        from agents.metadata_agent import sanitize_metadata_title
        bad_title_1 = "NAGARJUNA DUBBLE STANDARDS EXPOSED? Trolls Dig Up Old Videos!"
        fixed_1 = sanitize_metadata_title(bad_title_1)
        self.assertEqual(fixed_1, "NAGARJUNA DOUBLE STANDARDS EXPOSED? Trolls Dig Up Old Videos!")

        bad_title_2 = "Bigg Boss elemination shocker! dubble eviction today"
        fixed_2 = sanitize_metadata_title(bad_title_2)
        self.assertEqual(fixed_2, "Bigg Boss elimination shocker! double eviction today")

        bad_title_3 = "Host STANDAS questioned in weekend episode"
        fixed_3 = sanitize_metadata_title(bad_title_3)
        self.assertEqual(fixed_3, "Host STANDARDS questioned in weekend episode")


class TestEndToEndInteraction(unittest.TestCase):
    """Test Case 5: End-to-end interaction testing across modules."""

    def test_script_visual_voice_integration(self):
        from pipeline import VOICE_IDS, VOICE_TUNING
        # 1. Voice mapping interaction
        shruti_name = "👩 Shruti (Telugu Creator / Anchor) - Conversational"
        self.assertIn(shruti_name, VOICE_IDS)
        voice_id = VOICE_IDS[shruti_name]
        self.assertEqual(voice_id, "te-IN-ShrutiNeural")
        rate, pitch = VOICE_TUNING.get(shruti_name, ("+0%", "+0Hz"))
        self.assertEqual(rate, "+4%")

        # 2. Season guard + entity disambiguation interaction
        from utils.season_guard import is_bigg_boss_topic, is_conflicting_season_candidate
        is_bb = is_bigg_boss_topic("Bigg Boss Telugu 10 Weekend Class")
        self.assertTrue(is_bb)

        # 3. Disallowed Ram Charan collision when searching for contestant
        self.assertTrue(is_conflicting_season_candidate("Ram Charan Game Changer teaser launch", target_person="Charan"))


if __name__ == "__main__":
    unittest.main()

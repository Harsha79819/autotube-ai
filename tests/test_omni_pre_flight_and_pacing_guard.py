import unittest
import json
from pathlib import Path

from agents.roast_engine import validate_and_heal_script, _sanitize_awkward_loanwords
from agents.social_visual_selector import split_script_into_scenes
from agents.image_agent import is_blacklisted_candidate
from analytics.omni_router import OmniPreFlightGuard
from config.format_profiles import get_format_profile, parse_duration_to_seconds


class TestOmniPreFlightAndPacingGuard(unittest.TestCase):
    """
    Verification tests for Omni AI Pre-Flight Guard:
    1. Broken Telugu word sanitization
    2. Dynamic cuts guarantee (8-14 scenes, preventing frozen visuals)
    3. Wedding and off-topic interview image rejection
    4. 45-70s duration calibration
    """

    def test_01_broken_telugu_loanwords_sanitized(self):
        """Verifies that alien machine-translation words are purged and healed into natural Telugu."""
        broken_snippet = (
            "ముకేష్ వాళ్లను నాన్‌ఆఫ్ చేశాడు. వర్షిణి, దేబ్జాని జాతి గుండెలు మరుస్తున్నాక... "
            "శ్వేత సటోర్ రూమ్‌లో గుంజీలు చేస్తున్నాక... అతని ఈ అసహాయకారపూర్వకతకు వార్నింగ్ తప్పేలా లేదు."
        )
        healed = validate_and_heal_script(broken_snippet, topic="Bigg Boss Telugu 10")

        self.assertNotIn("నాన్‌ఆఫ్", healed)
        self.assertNotIn("జాతి గుండెలు", healed)
        self.assertNotIn("సటోర్ రూమ్", healed)
        self.assertNotIn("అసహాయకారపూర్వకతకు", healed)

        self.assertIn("డిస్క్వాలిఫై", healed)
        self.assertIn("గుండెల్లో రైళ్లు", healed)
        self.assertIn("స్టోర్ రూమ్", healed)
        self.assertIn("పక్షపాతానికి", healed)

    def test_02_three_paragraphs_split_into_8_to_14_scenes(self):
        """Verifies that a 3-paragraph 130-word script is segmented into 8 to 14 dynamic scenes."""
        three_para_script = (
            "బిగ్ బాస్ 10 హౌస్‌లో సంచాలక్ ముకేష్ గౌడ చేసిన రచ్చతో వాతావరణం భగ్గుమంది బాస్! "
            "టికెట్ టు ఫైనల్ టాస్క్‌లో త్రిగుణ్ టీమ్ దూకుడు చూపిస్తే, అమన్ మసూద్ ఒక్కరుగా రచ్చ రంబోలా చేశాడు. "
            "కానీ ముకేష్ వాళ్లను డిస్క్వాలిఫై చేశాడు. అసలు ట్విస్ట్ ఏంటంటే... తన పొరపాటును గుర్తించకుండా, "
            "త్రిగుణ్, అమన్ మధ్య వాగ్వాదాన్ని ఆయనే పుట్టిపెట్టాడు! ఇక దీన్ని కవర్ అప్ చేయడానికి హౌస్ యూనిటీ "
            "దెబ్బతీసినట్లు ఆరోపిస్తూ డ్రామా చేశాడు బాస్. చూశారా! సంచాలక్ అయిపోయాక ఎంత పచ్చి అబద్ధాలు చెప్తారో ఇక్కడ సాక్షాత్తూ చూశారు!\n"
            "ఇక వర్షిణి, దేబ్జాని గుండెల్లో రైళ్లు పరిగెడుతుంటే, కెప్టెన్ పొట్టి నరేష్ గట్టి వార్నింగ్స్ హౌస్‌లో వైరల్ అవుతున్నాయి. "
            "శ్వేత స్టోర్ రూమ్‌లో గుంజీలు తీస్తుంటే, ముకేష్ ఎలాంటి స్పందన ఇస్తారో చూడాలి. "
            "మరి ఈ వీకెండ్ ఎపిసోడ్‌లో నాగ్‌గారు ముకేష్‌కు ఎలాంటి క్లాస్ పీకబోతున్నారో చూడాలి. అతని ఈ పక్షపాతానికి వార్నింగ్ తప్పేలా లేదు.\n"
            "మరి మీ తరఫున ముకేష్ సంచాలక్‌గా ఫెయిల్ అయ్యాడా? లేక త్రిగుణ్ టీమ్ అధికంగా ఆడిందా? కింద కామెంట్ చేయండి! "
            "మరిన్ని కిర్రాక్ రోస్ట్‌ల కోసం ఇప్పుడే లైక్, షేర్, సబ్‌స్క్రైబ్ చేసుకోండి!"
        )
        scenes = split_script_into_scenes(three_para_script)
        self.assertGreaterEqual(len(scenes), 8, f"Expected at least 8 cuts, got {len(scenes)}")
        self.assertLessEqual(len(scenes), 14, f"Expected at most 14 cuts, got {len(scenes)}")

        # Verify no scene is longer than 22 words
        for idx, sc in enumerate(scenes, 1):
            w = len(sc.split())
            self.assertLessEqual(w, 22, f"Scene {idx} has {w} words: '{sc}'")

    def test_03_wedding_and_interview_images_blacklisted(self):
        """Verifies candidate rejection for wedding, marriage, reception, and interview noise."""
        wedding_candidate = {
            "title": "Actor Thrigun wedding reception with wife at temple",
            "image_url": "https://example.com/assets/thrigun-wedding.jpg",
            "source_url": "https://gulte.com/news/12345",
        }
        self.assertTrue(
            is_blacklisted_candidate(wedding_candidate, target_entity="Thrigun", topic_context="Bigg Boss Telugu 10")
        )

        interview_candidate = {
            "title": "Exclusive actress interview and personal photoshoot on Gulte",
            "image_url": "https://gulte.com/interviews/actress.jpg",
            "source_url": "https://gulte.com",
        }
        self.assertTrue(
            is_blacklisted_candidate(interview_candidate, target_entity="Varshini", topic_context="Bigg Boss Telugu 10")
        )

        valid_promo = {
            "title": "Bigg Boss Telugu 10 episode promo Mukesh Gowda heated clash",
            "image_url": "https://starmaa.com/bb10/mukesh-promo.jpg",
            "source_url": "https://hotstar.com",
        }
        self.assertFalse(
            is_blacklisted_candidate(valid_promo, target_entity="Mukesh Gowda", topic_context="Bigg Boss Telugu 10")
        )

    def test_04_omni_pre_flight_guard_gates(self):
        """Verifies OmniPreFlightGuard deterministic gating methods."""
        # Test 1: Language gate
        broken_text = "ముకేష్ నాన్‌ఆఫ్ చేశాడు మరియు సటోర్ రూమ్ లో దాక్కున్నాడు"
        healed, issues = OmniPreFlightGuard.audit_and_heal_script(broken_text)
        self.assertEqual(len(issues), 2)
        self.assertIn("డిస్క్వాలిఫై", healed)
        self.assertIn("స్టోర్ రూమ్", healed)

        # Test 2: Pacing gate rejects 3 cuts on 65s video
        passed_3, reason_3 = OmniPreFlightGuard.audit_scene_cuts(3, 65.0)
        self.assertFalse(passed_3)
        self.assertIn("Static slide defect", reason_3)

        # Test 3: Pacing gate accepts 11 cuts on 60s video
        passed_11, reason_11 = OmniPreFlightGuard.audit_scene_cuts(11, 60.0)
        self.assertTrue(passed_11)
        self.assertIsNone(reason_11)

    def test_05_duration_profile_45_70s(self):
        """Verifies 45-70s target duration bounds and word count envelope."""
        prof = get_format_profile("45-70s", language="telugu")
        self.assertEqual(prof.min_seconds, 45.0)
        self.assertEqual(prof.target_seconds, 60.0)
        self.assertEqual(prof.max_seconds, 70.0)
        self.assertEqual(prof.min_words, 115)
        self.assertEqual(prof.max_words, 145)


if __name__ == "__main__":
    unittest.main()

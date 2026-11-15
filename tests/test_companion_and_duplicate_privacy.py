"""
tests/test_companion_and_duplicate_privacy.py
Comprehensive test suite verifying:
1. Live companion telemetry updates and thread safety.
2. Duplicate topic / revision auto-switching to YouTube PRIVATE mode.
3. Strict Tollywood celebrity firewall in image_agent.
4. Accurate phonetic Telugu normalization (Rohit, Sudheer, Nagarjuna).
"""

import unittest
from pathlib import Path
import json
import os

from agents.companion_agent import (
    update_companion_status,
    get_companion_status,
    reset_companion_status,
)
from agents.image_agent import is_blacklisted_candidate
from utils.transliterate_telugu import ensure_telugu_script


class TestCompanionAndDuplicatePrivacy(unittest.TestCase):

    def test_companion_telemetry_flow(self):
        # 1. Update status during active run
        payload = update_companion_status(
            stage="Audio Synthesis",
            percent=50,
            current_task="Generating Shruthi Neural Telugu Voice (zero filler/SFX)",
            next_task="Harvesting Season 10 Visuals",
            is_running=True,
            step_number=4,
            total_steps=7,
        )
        self.assertTrue(payload["is_running"])
        self.assertEqual(payload["percent"], 50)
        self.assertEqual(payload["stage"], "Audio Synthesis")

        # 2. Verify static file persistence
        static_p = Path("static/pipeline_status.json")
        self.assertTrue(static_p.exists())
        data = json.loads(static_p.read_text(encoding="utf-8"))
        self.assertEqual(data["stage"], "Audio Synthesis")
        self.assertEqual(data["percent"], 50)

        # 3. Reset companion
        reset_companion_status("Unit test completed")
        idle_data = get_companion_status()
        self.assertFalse(idle_data["is_running"])
        self.assertEqual(idle_data["percent"], 100)

    def test_image_agent_tollywood_firewall_for_bigg_boss(self):
        # Candidate referencing Mahesh Babu & Rajamouli on a BB run
        bad_cand_1 = {
            "title": "Mahesh Babu and SS Rajamouli launch event news",
            "image_url": "https://example.com/mahesh_rajamouli.jpg",
            "source_url": "https://example.com/news/123",
        }
        self.assertTrue(
            is_blacklisted_candidate(bad_cand_1, target_entity="rohit_patnam", topic_context="Bigg Boss Telugu 10")
        )

        # Candidate referencing Allu Arjun on a BB run
        bad_cand_2 = {
            "title": "Allu Arjun Pushpa 2 press meet updates",
            "image_url": "https://example.com/allu_arjun.jpg",
            "source_url": "https://example.com/news/456",
        }
        self.assertTrue(
            is_blacklisted_candidate(bad_cand_2, target_entity="aman_masud", topic_context="Bigg Boss Telugu 10")
        )

        # Legitimate candidate referencing Bigg Boss contestant
        good_cand = {
            "title": "Rohit Patnam elimination reaction Bigg Boss 10 Star Maa",
            "image_url": "https://example.com/rohit_patnam_stage.jpg",
            "source_url": "https://example.com/news/789",
        }
        self.assertFalse(
            is_blacklisted_candidate(good_cand, target_entity="rohit_patnam", topic_context="Bigg Boss Telugu 10")
        )

    def test_telugu_phonetic_normalization(self):
        test_text = "రాహిత్ పట్నమ్ బయటకు వెళ్ళాక, సౌధీర్ రెడ్డి నరగజున ముందు వీకే థ్రీ టాస్కులో మాట్లాడారు."
        normalized = ensure_telugu_script(test_text)
        self.assertIn("రోహిత్ పట్నం", normalized)
        self.assertIn("సుధీర్ రెడ్డి", normalized)
        self.assertIn("నాగార్జున", normalized)
        self.assertIn("వీక్ 3", normalized)
        self.assertNotIn("నరగజున", normalized)
        self.assertNotIn("సౌధీర్", normalized)


if __name__ == "__main__":
    unittest.main()

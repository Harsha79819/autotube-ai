"""
Unit tests for Ground Truth Contestant Reference Directory and
Anti-Collision Overhaul in agents/image_agent.py.
"""

import unittest
from pathlib import Path

from agents.image_agent import (
    find_local_contestant_image,
    is_blacklisted_candidate,
    search_wikimedia,
    search_bing,
    STRICT_ANTI_COLLISION_BLACKLIST,
    CONTESTANT_REF_DIRS,
)


class TestGroundTruthContestantReference(unittest.TestCase):

    def test_01_reference_directories_exist_and_populated(self):
        """Verifies reference_assets/contestants and assets/contestants exist with official photos."""
        ref_dir = Path("reference_assets/contestants")
        self.assertTrue(ref_dir.exists(), "reference_assets/contestants must exist")
        
        expected_files = [
            "anchor_jhansi.jpg",
            "jhansi.jpg",
            "rohit_sahni.jpg",
            "rohit.jpg",
            "charan_mahadev.jpg",
            "charan.jpg",
            "varshini_sounderajan.jpg",
            "varshini.jpg",
            "mukesh_gowda.jpg",
            "mukesh.jpg",
            "thrigun.jpg",
            "debjani.jpg",
            "sudheer_reddy.jpg",
            "aman.jpg",
            "chaithra.jpg",
            "ram_prasad.jpg",
            "shalini.jpg",
            "temper_vamsi.jpg",
            "srishti.jpg",
            "potti_naresh.jpg",
            "krishnudu.jpg",
        ]
        for ef in expected_files:
            target = ref_dir / ef
            self.assertTrue(target.exists(), f"Missing ground truth photo: {ef}")
            self.assertGreater(target.stat().st_size, 1000, f"File too small: {ef}")

    def test_02_find_local_contestant_image_matches_contestants(self):
        """Verifies Priority 1 matcher identifies scenes featuring contestants."""
        # 1. Jhansi
        res_jhansi = find_local_contestant_image("Jhansi becomes captain of the house")
        self.assertIsNotNone(res_jhansi)
        self.assertEqual(res_jhansi[0], "jhansi")
        self.assertTrue(res_jhansi[1].exists())

        # 2. Rohit
        res_rohit = find_local_contestant_image("Rohit gets into heated argument in kitchen")
        self.assertIsNotNone(res_rohit)
        self.assertIn(res_rohit[0], ("rohit", "rohit_naidu"))
        self.assertTrue(res_rohit[1].exists())

        # 3. Charan
        res_charan = find_local_contestant_image("Charan evicted in week 1 shock")
        self.assertIsNotNone(res_charan)
        self.assertEqual(res_charan[0], "charan")
        self.assertTrue(res_charan[1].exists())

        # 4. Varshini
        res_varshini = find_local_contestant_image("Varshini Sounderajan emotional confession")
        self.assertIsNotNone(res_varshini)
        self.assertEqual(res_varshini[0], "varshini")
        self.assertTrue(res_varshini[1].exists())

        # 5. Mukesh
        res_mukesh = find_local_contestant_image("Mukesh Gowda wins star player badge")
        self.assertIsNotNone(res_mukesh)
        self.assertEqual(res_mukesh[0], "mukesh")
        self.assertTrue(res_mukesh[1].exists())

    def test_03_find_local_contestant_image_rejects_celebrity_and_monument_collisions(self):
        """Verifies Priority 1 matcher rejects Ram Charan, Rohit Sharma, and Jhansi Fort."""
        # 1. Ram Charan (must NOT match contestant Charan)
        self.assertIsNone(find_local_contestant_image("Ram Charan arrives at Game Changer event"))
        self.assertIsNone(find_local_contestant_image("Mega Power Star Ram Charan RRR oscar win"))

        # 2. Rohit Sharma (must NOT match contestant Rohit)
        self.assertIsNone(find_local_contestant_image("Rohit Sharma hits 100 in World Cup match"))
        self.assertIsNone(find_local_contestant_image("Cricketer Rohit Sharma BCCI press meet"))

        # 3. Jhansi Fort (must NOT match contestant Jhansi)
        self.assertIsNone(find_local_contestant_image("Jhansi Fort historical monument in Uttar Pradesh"))
        self.assertIsNone(find_local_contestant_image("Rani Lakshmibai Jhansi Fort tourism"))

        # 4. Generic action / b-roll scene (must NOT match any contestant -> goes to Priority 2)
        self.assertIsNone(find_local_contestant_image("Dramatic stage lighting with camera sweep"))
        self.assertIsNone(find_local_contestant_image("Living room couch tension and clock ticking"))

    def test_04_wikimedia_scraper_restricted_for_celebrities(self):
        """Verifies Wikimedia search returns [] immediately for Indian celebrity queries."""
        self.assertEqual(search_wikimedia("Rohit Sahni Bigg Boss"), [])
        self.assertEqual(search_wikimedia("Charan Bigg Boss Telugu 10"), [])
        self.assertEqual(search_wikimedia("Anchor Jhansi Bigg Boss"), [])
        self.assertEqual(search_wikimedia("Varshini Sounderajan television"), [])
        self.assertEqual(search_wikimedia("Mukesh Gowda serial actor"), [])
        self.assertEqual(search_wikimedia("Bigg Boss Telugu nominations"), [])

    def test_05_anti_collision_blacklist_filtering(self):
        """Verifies candidate rejection using STRICT_ANTI_COLLISION_BLACKLIST."""
        bad_cand_1 = {
            "title": "Rohit Sharma holding cricket bat during IPL",
            "image_url": "https://example.com/rohit_sharma_cricket.jpg",
            "source_url": "https://cricket.com",
        }
        self.assertTrue(is_blacklisted_candidate(bad_cand_1))

        bad_cand_2 = {
            "title": "Ram Charan at Dhruva pre-release",
            "image_url": "https://example.com/ram_charan_konidela.jpg",
            "source_url": "https://tollywood.com",
        }
        self.assertTrue(is_blacklisted_candidate(bad_cand_2))

        bad_cand_3 = {
            "title": "Historical Jhansi Fort monument tourism in India",
            "image_url": "https://example.com/jhansi_fort_monument.jpg",
            "source_url": "https://tourism.com",
        }
        self.assertTrue(is_blacklisted_candidate(bad_cand_3))

        clean_cand = {
            "title": "Stage lighting setup in production studio",
            "image_url": "https://example.com/studio_lights.jpg",
            "source_url": "https://pexels.com",
        }
        self.assertFalse(is_blacklisted_candidate(clean_cand))


if __name__ == "__main__":
    unittest.main()
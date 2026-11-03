"""
Test Person Visual Sourcing & Season Guard Engine
Verifies that:
1. Contestants (Apoorva, Jhansi, Thrigun, Aman, etc.) are accurately identified in scenes.
2. Season guard disqualifies other regional show languages (Kannada, Tamil, Hindi)
   while exempting authentic contestant portraits.
3. detect_named_entity prioritizes contestants over generic show rules.
"""

import unittest
from utils.season_guard import (
    extract_person_from_scene,
    extract_all_persons_from_scene,
    is_conflicting_season_candidate,
    verify_candidate_person,
)
from agents.image_agent import detect_named_entity


class TestPersonVisualSourcing(unittest.TestCase):

    def test_extract_person_from_scenes(self):
        # Telugu line mentioning Apoorva and Jhansi
        line1 = "Bigg Boss Season 10 లో అపూర్వ, ఝాన్సి ఎలిమినేషన్ అంట... అసలు షో ఇంకా అక్కడిదాకా వెళ్ళనే లేదు బాస్!"
        self.assertEqual(extract_person_from_scene(line1), "Apoorva")
        all_persons = extract_all_persons_from_scene(line1)
        self.assertIn("Apoorva", all_persons)
        self.assertTrue(any("Jhansi" in p for p in all_persons))

        # Telugu line mentioning Thrigun
        line2 = "త్రిగుణ్ ఎంట్రీతో హౌస్‌లో గేమ్ మొత్తం మారిపోయింది!"
        self.assertEqual(extract_person_from_scene(line2), "Thrigun")

        # English/Telugu mixed line mentioning Aman
        line3 = "ఎప్పుడూ సైలెంట్‌గా ఉండే Aman సడన్‌గా నిద్రలేచి immunity కొట్టేశాడు!"
        self.assertEqual(extract_person_from_scene(line3), "Aman Masud")

        # Line mentioning Nagarjuna
        line4 = "వీకెండ్ వస్తే నాగార్జున ఎంట్రీ... పీకుతారు నలభై నిమిషాల... క్లాస్!"
        self.assertEqual(extract_person_from_scene(line4), "Nagarjuna")

    def test_detect_named_entity_precedence(self):
        # Apoorva mentioned in Bigg Boss context should identify Apoorva, NOT generic Bigg Boss Telugu
        line = "Bigg Boss 10 లో అపూర్వ ఎలిమినేషన్"
        is_ent, ent_name, cat = detect_named_entity(line)
        self.assertTrue(is_ent)
        self.assertEqual(ent_name, "Apoorva")

        # Thrigun mentioned
        line2 = "Bigg Boss Telugu 10 లో త్రిగుణ్ ఎంట్రీ"
        is_ent2, ent_name2, _ = detect_named_entity(line2)
        self.assertTrue(is_ent2)
        self.assertEqual(ent_name2, "Thrigun")

    def test_season_guard_language_rejection(self):
        # Kannada Bigg Boss must be strictly rejected in Telugu context
        kannada_cand = "https://images.tv9kannada.com/wp-content/uploads/2025/10/bigg-boss-kannada.jpg"
        self.assertTrue(is_conflicting_season_candidate(kannada_cand, current_season=10, is_bb_context=True))

        # Tamil Bigg Boss must be strictly rejected
        tamil_cand = "https://vijaytv.com/bigg-boss-tamil-season-8-promo.jpg"
        self.assertTrue(is_conflicting_season_candidate(tamil_cand, current_season=10, is_bb_context=True))

        # Hindi Bigg Boss must be strictly rejected
        hindi_cand = "https://colorstv.com/bigg-boss-10-hindi-salman-khan.jpg"
        self.assertTrue(is_conflicting_season_candidate(hindi_cand, current_season=10, is_bb_context=True))

    def test_season_guard_person_portrait_exemption(self):
        # Real photo of Apoorva with 2024 or 2025 in path should NOT be rejected when target_person is Apoorva
        apoorva_cand = "https://admin.tellychakkar.com/sites/www.tellychakkar.com/files/s3fs-public/images/digital/2024/11/Apoorva.jpg"
        self.assertFalse(is_conflicting_season_candidate(
            apoorva_cand,
            current_season=10,
            is_bb_context=True,
            target_person="Apoorva"
        ))

        # But a generic show still from 2024 season 8 MUST be rejected
        old_bb_cand = "https://static.10tv.in/wp-content/uploads/2024/09/Bigg-Boss-8-Telugu-launch.jpg"
        self.assertTrue(is_conflicting_season_candidate(
            old_bb_cand,
            current_season=10,
            is_bb_context=True,
            target_person=None
        ))

    def test_verify_candidate_person(self):
        # Target person is Thrigun
        is_match, is_conflict = verify_candidate_person("Thrigun actor photo", "Thrigun")
        self.assertTrue(is_match)
        self.assertFalse(is_conflict)

        # Candidate refers to a competing person (e.g. Sudheer)
        is_match2, is_conflict2 = verify_candidate_person("Sudheer comedy stills", "Thrigun")
        self.assertFalse(is_match2)
        self.assertTrue(is_conflict2)


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path
from agents.entity_harvester import (
    slugify,
    find_existing_reference_portrait,
    harvest_entities_from_plan,
)

class TestEntityHarvester(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Thrigun Eswaran"), "thrigun_eswaran")
        self.assertEqual(slugify("S. S. Rajamouli"), "s_s_rajamouli")
        self.assertEqual(slugify("Anchor Shiva (Shiv)"), "anchor_shiva_shiv")

    def test_find_existing_reference_portrait(self):
        # Known existing reference portraits
        p_thrigun = find_existing_reference_portrait("Thrigun")
        self.assertIsNotNone(p_thrigun)
        self.assertTrue(p_thrigun.exists())

        p_shiv = find_existing_reference_portrait("Shiv")
        self.assertIsNotNone(p_shiv)
        self.assertTrue(p_shiv.exists())

    def test_harvest_entities_from_plan(self):
        mock_plan = [
            {"beat_id": 1, "main_entity": "Thrigun Eswaran", "spoken_text": "త్రిగుణ్ జైల్లో ఉన్నాడు"},
            {"beat_id": 2, "main_entity": "Shiv", "spoken_text": "శివ్ గేమ్‌ప్లే చూసి మైండ్ బ్లాంక్"},
            {"beat_id": 3, "main_entity": "News Headline", "spoken_text": "జనరల్ న్యూస్"}, # Should be skipped
        ]
        harvested = harvest_entities_from_plan(mock_plan, topic="Bigg Boss Telugu 10 Review")
        self.assertIn("Thrigun Eswaran", harvested)
        self.assertIn("Shiv", harvested)
        self.assertNotIn("News Headline", harvested)


if __name__ == "__main__":
    unittest.main()

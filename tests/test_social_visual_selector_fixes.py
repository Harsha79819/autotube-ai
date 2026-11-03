import json
import unittest
from pathlib import Path

from config.settings import get_setting, load_settings
from providers.apify_social import _normalize_candidate
from agents.script_agent import build_structured_visual_plan


class TestSocialVisualSelectorFixes(unittest.TestCase):
    def test_use_social_visuals_default_is_false(self):
        """Verifies that USE_SOCIAL_VISUALS is set to False to prioritize Universal Visual Engine."""
        self.assertFalse(get_setting("USE_SOCIAL_VISUALS", True))
        cfg_json = json.loads(Path("config/settings.json").read_text(encoding="utf-8"))
        self.assertFalse(cfg_json.get("USE_SOCIAL_VISUALS"))

    def test_ecommerce_domains_blacklisted_in_apify_social(self):
        """Verifies that e-commerce domains (Amazon, Flipkart, etc.) are filtered from candidates."""
        amazon_url = "https://m.media-amazon.com/images/I/71Rg4oj6aVL._AC_SL1500_.jpg"
        cand = _normalize_candidate(
            image_url=amazon_url,
            caption="Bigg Boss Telugu 10 product",
            post_url="https://amazon.com",
            username="seller",
            platform="web_social",
            query="Aman",
        )
        self.assertIsNone(cand)

        normal_url = "https://static.10tv.in/wp-content/uploads/2026/06/stills.jpg"
        valid_cand = _normalize_candidate(
            image_url=normal_url,
            caption="Bigg Boss Telugu 10 news still",
            post_url="https://twitter.com",
            username="news",
            platform="web_social",
            query="Aman",
        )
        self.assertIsNotNone(valid_cand)

    def test_hook_beats_inherit_topic_contestant(self):
        """Verifies that Beat 1 & Beat 2 inherit the contestant mentioned in the topic."""
        topic = "Shalini's Wild Secret Room Twist Proves Housemates Clueless"
        sections = [
            {"narration": "అసలు ఈ వారం హౌస్‌లో ఏం జరిగిందో చూస్తే మైండ్ బ్లాంక్ అవ్వాల్సిందే."},
            {"narration": "ట్విస్ట్ చూసి అంతా షాక్ అయిపోయారు."},
            {"narration": "రోహిత్ త్రిగుణ్ వెన్నుపోటు పొడిచారు."},
        ]
        visual_plan = ["Visual 1", "Visual 2", "Visual 3"]

        plan = build_structured_visual_plan(sections, visual_plan, topic=topic)
        self.assertGreaterEqual(len(plan), 3)
        self.assertEqual(plan[0]["main_entity"], "Shalini Patel")
        self.assertIn("Shalini Patel", plan[0]["search_query"])
        self.assertEqual(plan[1]["main_entity"], "Shalini Patel")


if __name__ == "__main__":
    unittest.main()

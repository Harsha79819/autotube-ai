import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import tempfile
import shutil

class TestImageDeadlockAndProgress(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.assets_dir = self.tmp_dir / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_progress_callback_and_no_deadlock(self):
        """Verify that download_images_from_visual_plan calls progress_callback and does not deadlock."""
        from agents.image_agent import download_images_from_visual_plan

        visual_plan = [
            "1. Aman winning moment celebration",
            "2. Naresh shock reaction in house",
            "3. Audience screaming excitement",
            "4. Winner trophy presentation stage",
        ]

        progress_calls = []
        def dummy_progress(val, text=""):
            progress_calls.append((val, text))

        with patch("agents.image_agent.ASSETS_DIR", self.assets_dir), \
             patch("agents.image_agent.OUTPUT_DIR", self.tmp_dir), \
             patch("providers.image.search_bing_images", return_value=[]), \
             patch("providers.image.search_entertainment_posters", return_value=[]), \
             patch("providers.image.search_twitter_media_images", return_value=[]), \
             patch("tools.build_entity_library.match_entities_in_text", return_value=[]):

            result = download_images_from_visual_plan(
                visual_plan,
                aspect_ratio="9:16",
                topic="Bigg Boss Telugu 10 Aman Winner Aithe Naresh Twist",
                progress_callback=dummy_progress,
            )

            self.assertEqual(len(result), 4)
            self.assertTrue(len(progress_calls) >= 4, f"Expected at least 4 progress calls, got {len(progress_calls)}")
            for val, text in progress_calls:
                self.assertGreaterEqual(val, 35)
                self.assertLessEqual(val, 55)
                self.assertIn("Sourcing visuals", text)

    def test_entity_library_lock_reentrancy_no_deadlock(self):
        """Verify entity library match does not self-deadlock when acquiring hash_lock."""
        from agents.image_agent import download_images_from_visual_plan

        visual_plan = [
            "1. Sudigali Sudheer celebration",
            "2. Sudigali Sudheer speech",
            "3. Housemates applauding",
            "4. Stage curtain falls",
        ]

        dummy_img = self.tmp_dir / "dummy_sudheer.jpg"
        Image.new("RGB", (720, 1280), color=(100, 50, 20)).save(dummy_img, "JPEG")

        fake_entity_match = [
            {"id": "sudigali_sudheer", "canonical_name": "Sudigali Sudheer", "score": 95}
        ]
        fake_asset = {
            "path": str(dummy_img),
            "source_url": "local_library",
            "license": "CC-BY",
            "credit": "Test",
        }

        with patch("agents.image_agent.ASSETS_DIR", self.assets_dir), \
             patch("agents.image_agent.OUTPUT_DIR", self.tmp_dir), \
             patch("tools.build_entity_library.match_entities_in_text", return_value=fake_entity_match), \
             patch("tools.build_entity_library.get_entity_asset", return_value=fake_asset), \
             patch("providers.image.search_bing_images", return_value=[]), \
             patch("providers.image.search_entertainment_posters", return_value=[]), \
             patch("providers.image.search_twitter_media_images", return_value=[]):

            result = download_images_from_visual_plan(
                visual_plan,
                aspect_ratio="9:16",
                topic="Bigg Boss Telugu 10 Sudheer",
            )
            self.assertEqual(len(result), 4)
            self.assertTrue(self.assets_dir.joinpath("1.jpg").exists())
            self.assertTrue(self.assets_dir.joinpath("2.jpg").exists())

if __name__ == "__main__":
    unittest.main()

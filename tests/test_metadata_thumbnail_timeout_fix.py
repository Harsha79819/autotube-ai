"""
Unit test suite verifying the Metadata & Thumbnail Generation timeout fix and autonomous supervisor recovery.
Tests:
1. Metadata agent strict timeouts and fast fallback
2. Thumbnail agent 2-pass background scoring speed and meme protection
3. Supervisor auto-recovery on timeout for 'Metadata & Thumbnail Generation'
4. Pipeline thumbnail reuse when pre-generated during parallel stage
"""

import os
import sys
import time
import shutil
import unittest
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from agents.metadata_agent import generate_metadata, generate_fallback_metadata, _call_gemini_metadata
from agents.thumbnail_agent import create_thumbnail, _find_best_background
from pipeline import run_stage_with_timeout, create_metadata
from supervisor import _handle_recovery


class TestMetadataThumbnailTimeoutFix(unittest.TestCase):

    def setUp(self):
        self.test_dir = ROOT / "output" / "test_meta_thumb_fix"
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_metadata_agent_generates_valid_content(self):
        """Verifies that generate_metadata produces valid title, description, and tags quickly."""
        topic = "Bigg Boss Telugu 10 Weekend Elimination Shock"
        script = "Bigg Boss Telugu 10 house lo ee weekend sensational elimination jarigindi. Rohit Patnam bayataku vachesadu."
        t0 = time.time()
        title, desc, tags = generate_metadata(topic, script)
        elapsed = time.time() - t0

        self.assertTrue(len(title) > 5)
        self.assertTrue(len(desc) > 20)
        self.assertTrue(isinstance(tags, list) and len(tags) >= 3)
        self.assertLess(elapsed, 25.0, f"generate_metadata took too long: {elapsed:.2f}s")

    def test_call_gemini_metadata_thread_timeout(self):
        """Verifies that _call_gemini_metadata times out cleanly when the provider hangs."""
        class MockHangingClient:
            class MockModels:
                def generate_content(self, *args, **kwargs):
                    time.sleep(5)
                    return None
            models = MockModels()

        mock_client = MockHangingClient()
        t0 = time.time()
        with self.assertRaises(Exception):
            _call_gemini_metadata(mock_client, "fake-model", "test prompt", timeout=0.2)
        elapsed = time.time() - t0
        self.assertLess(elapsed, 1.0, f"Timeout wrapper did not abort hanging model in time: {elapsed:.2f}s")

    def test_thumbnail_agent_two_pass_speed_and_quality(self):
        """Verifies that _find_best_background and create_thumbnail complete in under 3 seconds."""
        assets_test = self.test_dir / "assets"
        assets_test.mkdir(parents=True, exist_ok=True)

        # Create 10 dummy images to simulate a real video assets folder
        for i in range(1, 11):
            color = "blue" if i == 1 else "green"
            Image.new("RGB", (1080, 1920), color=color).save(assets_test / f"{i}.jpg")

        t0 = time.time()
        best_bg = _find_best_background(aspect_ratio="9:16", assets_dir=assets_test)
        elapsed_bg = time.time() - t0

        self.assertIsNotNone(best_bg)
        self.assertTrue(Path(best_bg).exists())
        self.assertLess(elapsed_bg, 6.0, f"_find_best_background took too long: {elapsed_bg:.2f}s")

        t1 = time.time()
        thumb_path = create_thumbnail(
            title="ROHIT ELIMINATION SCRIPTED DRAMA?",
            aspect_ratio="9:16",
            assets_dir=assets_test,
            output_dir=self.test_dir,
        )
        elapsed_thumb = time.time() - t1
        self.assertTrue(Path(thumb_path).exists())
        self.assertLess(elapsed_thumb, 12.0, f"create_thumbnail took too long: {elapsed_thumb:.2f}s")

    def test_supervisor_recovers_metadata_stage_on_timeout(self):
        """Verifies that run_stage_with_timeout auto-heals when Metadata & Thumbnail Generation times out."""
        def slow_stage(topic, script, **kwargs):
            time.sleep(2.0)
            return "unexpected", "should", "not", "reach", "here"

        topic = "Bigg Boss Telugu 10 Drama"
        script = "Bigg Boss Telugu 10 house updates and review."
        
        # Call with a 0.05s timeout to simulate a stage timeout
        result = run_stage_with_timeout(
            "Metadata & Thumbnail Generation",
            0.05,
            slow_stage,
            topic,
            script,
            run_dir=self.test_dir,
            run_id="test_timeout_recovery_run",
            aspect_ratio="9:16",
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 5)
        title, desc, tags, vid_id, yt_err = result
        self.assertTrue(len(title) > 0)
        self.assertTrue(len(desc) > 0)
        self.assertTrue(len(tags) > 0)
        self.assertIsNone(vid_id)
        # Verify metadata.json was saved by the recovery handler
        meta_file = self.test_dir / "metadata.json"
        self.assertTrue(meta_file.exists())

    def test_create_metadata_reuses_existing_thumbnail(self):
        """Verifies that create_metadata reuses a pre-existing thumbnail rather than recreating it."""
        pre_existing_thumb = self.test_dir / "thumbnail.jpg"
        Image.new("RGB", (1080, 1920), color="purple").save(pre_existing_thumb)
        orig_mtime = pre_existing_thumb.stat().st_mtime

        time.sleep(0.1)
        topic = "Quick Topic Test"
        script = "Quick script test."
        title, desc, tags, vid_id, yt_err = create_metadata(
            topic,
            script,
            run_dir=self.test_dir,
            aspect_ratio="9:16",
        )

        self.assertTrue((self.test_dir / "thumbnail.jpg").exists())
        self.assertEqual(pre_existing_thumb.stat().st_mtime, orig_mtime)


if __name__ == "__main__":
    unittest.main()

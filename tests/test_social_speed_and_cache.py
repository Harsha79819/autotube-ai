import unittest
import os
import sys
import time
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from agents.social_visual_selector import split_script_into_scenes, batch_analyze_scenes_with_llm
from providers.apify_social import _load_metadata_cache, _save_metadata_cache, _query_cache_key


class TestSocialSpeedAndCache(unittest.TestCase):
    """Verifies social visual selection caching, batching, and speed optimizations."""

    def test_01_scene_splitting(self):
        """Verifies script splitting produces discrete scene units."""
        sample_script = (
            "60 కెమెరాలు తిరుగుతున్నా ఒక్క ఫ్రేమ్ కూడా దొరకలేదంటే నమ్ముతారా?\n"
            "అసలు మనం సీజన్ ఎయిట్ లో ఉన్నామా లేక 2030 లో ఉన్నామా బాస్?\n"
            "అసలు హౌస్‌లోనే లేని ముకేష్-వర్షిణి లవ్ స్టోరీ ఒకటి వైరల్ అవుతోంది.\n"
            "వీళ్లు కెమెరాలకి తెలియకుండా ఎక్కడో రహస్యంగా ప్రేమించుకుంటున్నారా ఏంటి?"
        )
        scenes = split_script_into_scenes(sample_script)
        self.assertEqual(len(scenes), 4)
        for s in scenes:
            self.assertGreater(len(s), 10)

    def test_02_social_cache_empty_query_retention(self):
        """Verifies empty or 0-result candidate queries are retained in cache to prevent repeated waits."""
        cache = _load_metadata_cache()
        test_key = _query_cache_key("twitter", "test_nonexistent_hashtag_xyz_99")

        # Simulate caching an empty result
        cache[test_key] = {"candidates": [], "cached_at": time.time()}
        _save_metadata_cache(cache)

        # Reload cache and verify retention
        reloaded = _load_metadata_cache()
        self.assertIn(test_key, reloaded)
        self.assertEqual(reloaded[test_key]["candidates"], [])

        # Clean up test key
        if test_key in reloaded:
            del reloaded[test_key]
            _save_metadata_cache(reloaded)

    def test_03_batch_scene_fallback_resilience(self):
        """Verifies batch scene analyzer falls back gracefully without crashing when offline."""
        scenes = [
            "Scene 1: Introduction to the biggest reality drama",
            "Scene 2: Contestants clash during the heated nomination task",
            "Scene 3: The shocking elimination verdict is finally revealed",
        ]
        metas = batch_analyze_scenes_with_llm(scenes, overall_context="Bigg Boss Telugu 8")
        self.assertEqual(len(metas), len(scenes))
        for m in metas:
            self.assertIn("main_entity", m)
            self.assertIn("event_type", m)
            self.assertIn("hashtags", m)
            self.assertIn("clip_text", m)


if __name__ == "__main__":
    unittest.main()

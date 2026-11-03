"""
Tests for visual pacing segmentation, video aspect ratio enforcement,
and non-repeating topic suggestions.
"""

import os
import unittest
import shutil
from pathlib import Path

from agents.social_visual_selector import split_script_into_scenes
from agents.topic_suggester import (
    load_used_topics,
    record_used_topic,
    fetch_ai_topic_suggestions,
    USED_TOPICS_FILE,
)


from unittest.mock import patch

class TestPacingAspectAndTopicNovelty(unittest.TestCase):

    def test_sentence_level_scene_splitting(self):
        """Verify that multi-sentence paragraphs produce 1 scene per sentence instead of only 3 paragraphs."""
        test_script = (
            "బిగ్ బాస్ వైల్డ్ కార్డ్ ఎంట్రీ అంటే బాంబు పేలాలి. కానీ ఇక్కడ జరుగుతున్నది చూస్తుంటే క్రింజ్ కూడా సిగ్గుపడి పారిపోతుంది బాస్! "
            "సీజన్ సెవెన్‌లో ఒకరు వైల్డ్ కార్డ్‌గా వచ్చి విన్నర్ అయ్యాడు. అసలే రేటింగ్స్ పడిపోతుంటే ఒకేసారి ఐదుగురిని లోపలికి పంపారు. "
            "ఇది రియాలిటీ షోనా లేక బస్ స్టాండ్ దగ్గర రష్ అవరా? మరికొందరు అసలు కంటెస్టెంట్లే కాదు. "
            "స్క్రిప్ట్ చదివే ఆర్టిస్టుల రేంజ్ లో ఎంట్రీ ఇస్తారు! కళ్ల ముందు పాతవాళ్లు గేమ్ ఆడుతుంటే వీళ్లు బిల్డప్ ఇస్తారు. "
            "అసలు వైల్డ్ కార్డ్స్ అంటే ఎంటర్టైన్మెంట్ కోసం అనుకుంటే రియాలిటీని భ్రష్టు పట్టిస్తున్నారు. "
            "సీజన్ ఎయిట్‌లో మళ్ళీ క్లాన్ సిస్టమ్ అని కొత్త గొడవలు. అసలు వీళ్లు గేమ్ సేవ్ చేస్తున్నారో లేదో కానీ మనకి బీపీ గ్యారెంటీ! "
            "ఇలాంటి క్రేజీ అనాలిసిస్ మిస్ అవ్వకూడదంటే సబ్స్క్రైబ్ బటన్ కొట్టేయండి. సో లైక్, షేర్, సబ్‌స్క్రైబ్ కొట్టేయండి!"
        )

        with patch("agents.social_visual_selector.OUTPUT_DIR", Path("/tmp/non_existent_dir_for_test")):
            scenes = split_script_into_scenes(test_script)
            # Should be at least 10 scenes, NOT 1 or 3!
            self.assertGreaterEqual(len(scenes), 10, f"Expected >= 10 scenes for fast pacing, got {len(scenes)}")

    def test_alignment_with_existing_section_map(self):
        """Verify that when section_map has 13 sections, split_script_into_scenes returns exactly 13 scenes."""
        fake_sections = [
            {"section": i, "visual": i, "narration": f"Narration beat {i} about Bigg Boss."}
            for i in range(1, 14)
        ]
        fake_script = " ".join(s["narration"] for s in fake_sections)
        with patch("agents.video_agent.get_section_map", return_value=fake_sections):
            with patch("pathlib.Path.exists", return_value=True):
                scenes = split_script_into_scenes(fake_script)
                self.assertEqual(len(scenes), 13, f"Expected exactly 13 scenes matching section_map, got {len(scenes)}")

    def test_topic_ledger_deduplication(self):
        """Verify that record_used_topic prevents returning previously used topics."""
        test_topic = "Unique Test Mystery Topic That Should Never Repeat"
        record_used_topic(test_topic)

        used = load_used_topics()
        self.assertIn(test_topic.lower(), used)

        suggestions = fetch_ai_topic_suggestions("History", count=6, use_ai=False)
        self.assertNotIn(test_topic, suggestions)

    def test_history_and_facts_diversity(self):
        """Verify History and Facts return rich, relevant topics."""
        hist_topics = fetch_ai_topic_suggestions("History", count=5, use_ai=False)
        self.assertGreaterEqual(len(hist_topics), 5)
        # Check presence of key themes (Kohinoor, Ramappa, Dwarka, Alexandria, Golconda, etc.)
        hist_combined = " ".join(hist_topics).lower()
        self.assertTrue(
            any(k in hist_combined for k in [
                "kohinoor", "ramappa", "dwarka", "alexandria", "pyramid", "indus", "bobbili",
                "nizam", "golconda", "pillar", "delhi", "pirate", "heracleion", "lepakshi",
                "vijayanagara", "chernobyl", "antikythera", "padmanabhaswamy"
            ]),
            f"Expected rich Indian/world history topics, got: {hist_topics}"
        )


    def test_validate_mapping_auto_expansion(self):
        """Verify that validate_mapping auto-expands visual_plan when sections has more items."""
        from agents.video_agent import validate_mapping

        # 5 mock images with stems '1', '2', '3', '4', '5'
        class MockPath:
            def __init__(self, name):
                self.name = name
                self.stem = Path(name).stem

        images = [MockPath(f"{i}.jpg") for i in range(1, 6)]
        # visual_plan only has 2 items
        visual_plan = ["Scene 1", "Scene 2"]
        # sections has 5 items
        sections = [
            {"section": i, "visual": i, "narration": f"Narration for section {i}"}
            for i in range(1, 6)
        ]

        # Should auto-expand visual_plan from 2 to 5 and succeed without crashing
        validate_mapping(images, visual_plan, sections)
        self.assertEqual(len(visual_plan), 5)
        self.assertEqual(len(sections), 5)

    def test_supervisor_scale_filter_present(self):
        """Verify supervisor.py defines portrait 1080:1920 scale/pad filter in heal_ffmpeg_failure."""
        import inspect
        from supervisor import heal_ffmpeg_failure
        source = inspect.getsource(heal_ffmpeg_failure)
        self.assertIn("scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}", source)
        self.assertIn("-vf", source)


if __name__ == "__main__":
    unittest.main()

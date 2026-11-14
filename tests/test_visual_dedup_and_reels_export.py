"""
Unit tests for AutoTube AI:
1. Visual Deduplication & Dynamic AI Image Fallback (agents/visual_agent.py)
2. Instagram Reels 9:16 FFmpeg Export Specifications (agents/final_video_agent.py)
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agents.visual_agent import (
    get_asset_identity,
    is_same_asset_or_entity,
    detect_repeated_assets,
    deduplicate_consecutive_assets,
    build_scene_flux_prompt,
)
from agents.final_video_agent import create_final_video
from data.asset_ledger import (
    clear_ledger_for_video,
    record_asset,
    get_assets_for_video,
    get_tier_breakdown,
)


class TestVisualDedupAndReelsExport(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.assets_dir = Path(self.test_dir) / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        clear_ledger_for_video("test_video")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        clear_ledger_for_video("test_video")

    def test_01_is_same_asset_or_entity_detection(self):
        """Verifies identity comparison across hashes, entities, URLs, and credit text."""
        # 1. Same entity
        a1 = {"entity": "thrigun", "file_hash": "aaa", "source_url": "http://1", "credit_text": "Photo of Thrigun"}
        a2 = {"entity": "thrigun", "file_hash": "bbb", "source_url": "http://2", "credit_text": "Photo of Thrigun"}
        same, reason = is_same_asset_or_entity(a1, a2)
        self.assertTrue(same)
        self.assertIn("thrigun", reason)

        # 2. Different entity
        a3 = {"entity": "sanjana", "file_hash": "ccc", "source_url": "http://3", "credit_text": "Photo of Sanjana"}
        same_diff, _ = is_same_asset_or_entity(a1, a3)
        self.assertFalse(same_diff)

        # 3. Identical image hash without entity
        a4 = {"entity": "", "file_hash": "hash_xyz", "source_url": "", "credit_text": "Stock image"}
        a5 = {"entity": "", "file_hash": "hash_xyz", "source_url": "", "credit_text": "Another still"}
        same_hash, reason_hash = is_same_asset_or_entity(a4, a5)
        self.assertTrue(same_hash)
        self.assertIn("hash", reason_hash)

        # 4. Identical source URL
        a6 = {"entity": "", "file_hash": "h6", "source_url": "http://cdn.example.com/photo.jpg", "credit_text": ""}
        a7 = {"entity": "", "file_hash": "h7", "source_url": "http://cdn.example.com/photo.jpg", "credit_text": ""}
        same_url, reason_url = is_same_asset_or_entity(a6, a7)
        self.assertTrue(same_url)
        self.assertIn("url", reason_url)

    def test_02_detect_repeated_assets_consecutive_threshold(self):
        """
        Verifies that repeating 'Photo of Thrigun' across Beats 7-13 triggers
        subsequent repeat flags only for beats 9, 10, 11, 12, 13 (streak > 2).
        Beats 7 and 8 must remain untouched (streak <= 2).
        """
        # Create dummy assets 1..13
        for i in range(1, 14):
            img_file = self.assets_dir / f"{i}.jpg"
            img_file.write_bytes(f"dummy_image_data_beat_{i}".encode("utf-8"))

        # Setup ledger: beats 1..6 are diverse, beats 7..13 repeat Thrigun
        record_asset("test_video", 1, str(self.assets_dir / "1.jpg"), "http://s1", "TIER_A", "CC0", "House Interior", 3.0)
        record_asset("test_video", 2, str(self.assets_dir / "2.jpg"), "http://s2", "TIER_B", "Editorial", "Photo of Nagarjuna", 3.0)
        record_asset("test_video", 3, str(self.assets_dir / "3.jpg"), "http://s3", "TIER_A", "CC0", "Nomination Room", 3.0)
        record_asset("test_video", 4, str(self.assets_dir / "4.jpg"), "http://s4", "TIER_B", "Editorial", "Photo of Sanjana", 3.0)
        record_asset("test_video", 5, str(self.assets_dir / "5.jpg"), "http://s5", "TIER_B", "Editorial", "Photo of Sanjana", 3.0)
        record_asset("test_video", 6, str(self.assets_dir / "6.jpg"), "http://s6", "TIER_A", "CC0", "Living Area Stage", 3.0)

        # Beats 7 to 13: 7 consecutive beats repeating 'Photo of Thrigun'
        for i in range(7, 14):
            record_asset(
                video_id="test_video",
                beat_id=i,
                asset_path=str(self.assets_dir / f"{i}.jpg"),
                source_url=f"http://web/thrigun_{i}.jpg",
                tier="TIER_B",
                license_name="Web Editorial",
                credit_text="Photo of Thrigun",
                duration_sec=3.0,
            )

        section_narrations = {
            7: "Thrigun gets nominated by Sanjana.",
            8: "Thrigun questions the nomination reason.",
            9: "Intense argument erupts in the living room.",
            10: "Contestants take sides in the dispute.",
            11: "Emotional breakdown during the heated confrontation.",
            12: "The buzzer rings signaling end of round.",
            13: "Final vote tally is announced on screen.",
        }

        repeated = detect_repeated_assets(
            assets_dir=self.assets_dir,
            max_consecutive=2,
            video_id="test_video",
            section_narrations=section_narrations,
            target_count=13,
        )

        repeated_beat_ids = [r["beat_id"] for r in repeated]
        # Beats 7 and 8 should NOT be flagged (first 2 consecutive beats)
        self.assertNotIn(7, repeated_beat_ids)
        self.assertNotIn(8, repeated_beat_ids)
        # Beats 9..13 MUST be flagged as repeated subsequent beats
        self.assertEqual(repeated_beat_ids, [9, 10, 11, 12, 13])

        # Verify streak counters
        self.assertEqual(repeated[0]["streak"], 3)  # Beat 9 is 3rd consecutive
        self.assertEqual(repeated[1]["streak"], 4)  # Beat 10 is 4th
        self.assertEqual(repeated[4]["streak"], 7)  # Beat 13 is 7th

    @patch("agents.visual_agent.rewrite_query_for_flux", return_value="cinematic dramatic reality scene, 9:16 vertical ratio, photorealistic, 8k")
    @patch("agents.visual_agent.generate_ai_visual")
    def test_03_deduplicate_consecutive_assets_flux_fallback_and_tier_b_cap(self, mock_generate, mock_rewrite):
        """
        Verifies that deduplicate_consecutive_assets:
        1. Calls FLUX AI visual generation for subsequent beats (Beats 9-13).
        2. Re-records replaced beats as TIER_A in asset ledger.
        3. Enforces overall Tier B share <= 30%.
        """
        mock_generate.return_value = True

        for i in range(1, 14):
            p = self.assets_dir / f"{i}.jpg"
            p.write_bytes(f"image_data_{i}".encode("utf-8"))

        # Setup ledger
        record_asset("test_video", 1, str(self.assets_dir / "1.jpg"), "http://1", "TIER_A", "CC0", "House", 3.0)
        record_asset("test_video", 2, str(self.assets_dir / "2.jpg"), "http://2", "TIER_A", "CC0", "Nomination", 3.0)
        record_asset("test_video", 3, str(self.assets_dir / "3.jpg"), "http://3", "TIER_A", "CC0", "Stage", 3.0)
        record_asset("test_video", 4, str(self.assets_dir / "4.jpg"), "http://4", "TIER_A", "CC0", "Kitchen", 3.0)
        record_asset("test_video", 5, str(self.assets_dir / "5.jpg"), "http://5", "TIER_A", "CC0", "Garden", 3.0)
        record_asset("test_video", 6, str(self.assets_dir / "6.jpg"), "http://6", "TIER_A", "CC0", "Store room", 3.0)

        # Beats 7..13 repeating Quantum Drone (Tier B)
        for i in range(7, 14):
            record_asset("test_video", i, str(self.assets_dir / f"{i}.jpg"), f"http://drone/{i}", "TIER_B", "Web", "Photo of Quantum Drone", 3.0)

        # Before dedup, Tier B share is 7/13 = 53.8%
        pre_tb = get_tier_breakdown("test_video")
        self.assertGreater(pre_tb["tier_b_share"], 0.50)

        section_narrations = {i: f"Narration context for scene {i}" for i in range(1, 14)}

        results = deduplicate_consecutive_assets(
            assets_dir=self.assets_dir,
            section_narrations=section_narrations,
            aspect_ratio="9:16",
            topic_category="general",
            max_consecutive=2,
            target_count=13,
            video_id="test_video",
            show_context="",
        )

        self.assertEqual(len(results), 13)
        # FLUX should have been invoked for beats 9, 10, 11, 12, 13 (at least 5 times)
        self.assertGreaterEqual(mock_generate.call_count, 5)

        # Verify ledger after deduplication
        post_assets = {a["beat_id"]: a for a in get_assets_for_video("test_video")}
        # Beats 7 & 8 should still be TIER_B (the 2 allowed consecutive beats)
        self.assertEqual(post_assets[7]["tier"], "TIER_B")
        self.assertEqual(post_assets[8]["tier"], "TIER_B")

        # Beats 9..13 should now be TIER_A (FLUX dedup)
        for b_id in [9, 10, 11, 12, 13]:
            self.assertEqual(post_assets[b_id]["tier"], "TIER_A")
            self.assertEqual(post_assets[b_id]["source_url"], "pollinations_flux_dedup")

        # Check final Tier B share: 2 Tier B out of 13 total = 15.38% <= 30%
        post_tb = get_tier_breakdown("test_video")
        self.assertLessEqual(post_tb["tier_b_share"], 0.30)

    @patch("agents.final_video_agent.subprocess.run")
    def test_04_final_video_agent_9_16_reels_ffmpeg_arguments(self, mock_subproc):
        """
        Verifies that create_final_video for 9:16 vertical exports strictly includes:
        -c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 192k -ar 44100 -movflags +faststart
        to satisfy Meta Instagram Reels ingestion compliance.
        """
        dummy_input = Path(self.test_dir) / "input.mp4"
        dummy_input.write_bytes(b"dummy_mp4_bytes")
        dummy_output = Path(self.test_dir) / "output.mp4"

        def fake_subproc(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            if isinstance(cmd, list) and len(cmd) > 0:
                if cmd[0] == "ffprobe":
                    res.stdout = "audio\n"
                elif cmd[0] == "ffmpeg":
                    dummy_output.write_bytes(b"rendered_output")
                    res.stdout = ""
            return res

        mock_subproc.side_effect = fake_subproc

        create_final_video(
            add_captions=False,
            aspect_ratio="9:16",
            input_video=str(dummy_input),
            output_video=str(dummy_output),
        )

        ffmpeg_calls = [c for c in mock_subproc.call_args_list if c[0][0][0] == "ffmpeg"]
        self.assertTrue(len(ffmpeg_calls) > 0)
        cmd = ffmpeg_calls[-1][0][0]
        cmd_str = " ".join(cmd)

        # Assert mandatory Meta Reels parameters
        self.assertIn("-c:v libx264", cmd_str)
        self.assertIn("-pix_fmt yuv420p", cmd_str)
        self.assertIn("-c:a aac", cmd_str)
        self.assertIn("-b:a 192k", cmd_str)
        self.assertIn("-ar 44100", cmd_str)
        self.assertIn("-movflags +faststart", cmd_str)

    @patch("agents.final_video_agent.subprocess.run")
    @patch("agents.final_video_agent.subprocess.Popen")
    def test_05_final_video_agent_16_9_horizontal_arguments(self, mock_popen, mock_subproc):
        """
        Verifies horizontal (16:9) long-form videos retain 48000 Hz audio rate.
        """
        dummy_input = Path(self.test_dir) / "input_16_9.mp4"
        dummy_input.write_bytes(b"dummy_mp4_bytes")
        dummy_output = Path(self.test_dir) / "output_16_9.mp4"

        # Create dummy subtitles.srt so that filter complex assembly is triggered
        sub_srt = Path("output/subtitles.srt")
        sub_srt.parent.mkdir(parents=True, exist_ok=True)
        sub_srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello world\n", encoding="utf-8")

        def fake_subproc(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            if isinstance(cmd, list) and len(cmd) > 0:
                if cmd[0] == "ffprobe":
                    res.stdout = "audio\n"
                elif cmd[0] == "ffmpeg":
                    dummy_output.write_bytes(b"rendered_output")
                    res.stdout = ""
            return res

        mock_subproc.side_effect = fake_subproc

        mock_proc_obj = MagicMock()
        mock_proc_obj.returncode = 0
        mock_proc_obj.stdout = ["frame=100\n", "progress=end\n"]
        mock_proc_obj.wait.return_value = 0

        def fake_popen(cmd, *args, **kwargs):
            dummy_output.write_bytes(b"rendered_output_bytes_123456")
            return mock_proc_obj

        mock_popen.side_effect = fake_popen

        create_final_video(
            add_captions=True,
            aspect_ratio="16:9",
            input_video=str(dummy_input),
            output_video=str(dummy_output),
        )

        ffmpeg_calls = [c for c in mock_popen.call_args_list if c[0][0][0] == "ffmpeg"]
        self.assertTrue(len(ffmpeg_calls) > 0)
        cmd = ffmpeg_calls[-1][0][0]
        cmd_str = " ".join(cmd)

        # Assert horizontal assembly retains 48000
        self.assertIn("-ar 48000", cmd_str)

    @patch("agents.visual_agent.rewrite_query_for_flux", side_effect=lambda q, **kwargs: q)
    def test_06_build_scene_flux_prompt_cleaning_and_formatting(self, mock_rewrite):
        """Verifies stripping of leading numbers/labels and appending explicit visual keywords."""
        test_cases = [
            ("1. Contestant enters the confession room", "Contestant enters the confession room"),
            ("Beat 3: High tension living room argument", "High tension living room argument"),
            ("Visual 5 - Dramatic buzzer rings across stage", "Dramatic buzzer rings across stage"),
            ("Shot 12: Final elimination announcement", "Final elimination announcement"),
        ]
        for raw_text, expected_core in test_cases:
            prompt = build_scene_flux_prompt(raw_text, aspect_ratio="9:16", topic_category="entertainment")
            self.assertTrue(prompt.startswith("Gritty cinematic"))
            self.assertIn("9:16 vertical ratio", prompt)
            self.assertIn("photorealistic, 8k photography, dramatic atmospheric lighting", prompt)
            self.assertIn(expected_core, prompt)
            self.assertNotIn("Beat 3:", prompt)
            self.assertNotIn("Visual 5 -", prompt)
            self.assertNotIn("1.", prompt)

    @patch("agents.visual_agent.generate_ai_visual", return_value=True)
    def test_07_deduplicate_consecutive_assets_target_count_fallback(self, mock_generate):
        """Verifies target_count automatically falls back to len(section_narrations) if None or 0."""
        for i in range(1, 5):
            p = self.assets_dir / f"{i}.jpg"
            p.write_bytes(f"image_data_{i}".encode("utf-8"))
            record_asset("test_video", i, str(p), f"http://cand/{i}", "TIER_B", "Web", "Photo of Thrigun", 3.0)

        section_narrations = {
            1: "Thrigun arrives",
            2: "Thrigun speaks",
            3: "Thrigun disputes",
            4: "Thrigun leaves",
        }

        # target_count=None
        results_none = deduplicate_consecutive_assets(
            assets_dir=self.assets_dir,
            section_narrations=section_narrations,
            target_count=None,
            video_id="test_video",
        )
        self.assertEqual(len(results_none), 4)

        # target_count=0
        results_zero = deduplicate_consecutive_assets(
            assets_dir=self.assets_dir,
            section_narrations=section_narrations,
            target_count=0,
            video_id="test_video",
        )
        self.assertEqual(len(results_zero), 4)

    def test_08_thumbnail_agent_dual_output_and_slate_fallback(self):
        """
        Verifies that create_thumbnail writes to BOTH output_dir and global OUTPUT_DIR,
        and generates a branded slate when no background candidates exist.
        """
        from agents.thumbnail_agent import create_thumbnail
        custom_out_dir = Path(self.test_dir) / "custom_run_out"
        global_out_dir = Path(self.test_dir) / "global_out"
        empty_assets_dir = Path(self.test_dir) / "empty_assets"
        empty_assets_dir.mkdir(parents=True, exist_ok=True)

        with patch("agents.thumbnail_agent.OUTPUT_DIR", global_out_dir):
            result_path = create_thumbnail(
                title="Bigg Boss 10 Nominations Twist",
                aspect_ratio="9:16",
                assets_dir=empty_assets_dir,
                output_dir=custom_out_dir,
            )

            self.assertIsNotNone(result_path)
            custom_thumb = custom_out_dir / "thumbnail.jpg"
            global_thumb = global_out_dir / "thumbnail.jpg"

            # Must exist in run-specific directory
            self.assertTrue(custom_thumb.exists())
            self.assertGreater(custom_thumb.stat().st_size, 1000)

            # Must exist in global OUTPUT_DIR for UI and sanity checks
            self.assertTrue(global_thumb.exists())
            self.assertGreater(global_thumb.stat().st_size, 1000)

    def test_09_video_agent_ensure_visual_assets_exist(self):
        """
        Verifies ensure_visual_assets_exist:
        1. Clones from assets/1.jpg or creates fallback slates when assets are missing.
        2. Successfully extracts frame 0 when only .mp4 exists.
        """
        from agents.video_agent import ensure_visual_assets_exist
        from PIL import Image

        # Create assets/1.jpg
        p1 = self.assets_dir / "1.jpg"
        img = Image.new("RGB", (1080, 1920), color=(200, 50, 50))
        img.save(p1, "JPEG")

        # Create dummy assets/2.mp4
        p2_mp4 = self.assets_dir / "2.mp4"
        p2_mp4.write_bytes(b"dummy mp4 file bytes for simulation" * 200)

        with patch("agents.video_agent.ASSETS_DIR", self.assets_dir), \
             patch("agents.video_agent.subprocess.run") as mock_subproc:

            def fake_ffmpeg(cmd, *args, **kwargs):
                if "-vframes" in cmd and "2.jpg" in str(cmd[-1]):
                    # Simulate extracted jpg frame
                    Path(cmd[-1]).write_bytes(b"extracted_jpg_frame_bytes" * 100)
                res = MagicMock()
                res.returncode = 0
                return res

            mock_subproc.side_effect = fake_ffmpeg

            # Run ensure_visual_assets_exist for 3 assets
            ensure_visual_assets_exist(needed_count=3)

            # 1.jpg must exist
            self.assertTrue((self.assets_dir / "1.jpg").exists())

            # 2.jpg should have been extracted or populated
            self.assertTrue((self.assets_dir / "2.jpg").exists())
            self.assertGreater((self.assets_dir / "2.jpg").stat().st_size, 1000)

            # 3.jpg was missing, should have been cloned from 1.jpg
            self.assertTrue((self.assets_dir / "3.jpg").exists())
            self.assertGreater((self.assets_dir / "3.jpg").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()

"""
Unit Tests for Long-Format Video Engine (Chapter Engine, Multi-Track Audio Mixing, YouTube SEO Timestamps)
"""
import os
import json
import unittest
from pathlib import Path

from agents.chapter_engine import (
    render_chapter_bumper,
    parse_chapters_from_script,
    format_youtube_chapters_description,
)
from agents.metadata_agent import _attach_youtube_chapters
import audio_mixer as am


class TestChapterEngineAndLongForm(unittest.TestCase):
    def test_render_chapter_bumper_16_9(self):
        output_p = 'output/test_unit_bumper.png'
        res = render_chapter_bumper(
            chapter_num=1,
            title='Tollywood Box Office Pulse',
            subtitle='PART 1: THE BIG OPENINGS',
            category='cinema',
            width=1920,
            height=1080,
            output_path=output_p,
        )
        self.assertTrue(os.path.exists(output_p))
        from PIL import Image
        with Image.open(output_p) as im:
            self.assertEqual(im.size, (1920, 1080))
        if os.path.exists(output_p):
            os.remove(output_p)

    def test_parse_chapters_from_script_explicit(self):
        sections = [
            {'section': 1, 'start': 0.0, 'end': 20.0, 'narration': '[CHAPTER 1: The Untold Beginning] First beat.'},
            {'section': 2, 'start': 20.0, 'end': 40.0, 'narration': 'Second beat.'},
            {'section': 3, 'start': 40.0, 'end': 70.0, 'narration': '[CHAPTER 2: Deep Dive Evidence] Third beat.'},
            {'section': 4, 'start': 70.0, 'end': 95.0, 'narration': 'Fourth beat.'},
            {'section': 5, 'start': 95.0, 'end': 130.0, 'narration': '[CHAPTER 3: The Verdict] Final beat.'},
        ]
        chapters = parse_chapters_from_script(sections, total_duration=130.0)
        self.assertEqual(len(chapters), 3)
        self.assertEqual(chapters[0]['chapter'], 1)
        self.assertEqual(chapters[0]['start_time'], 0.0)
        self.assertEqual(chapters[0]['timestamp'], '00:00')
        self.assertEqual(chapters[0]['title'], 'The Untold Beginning')

        self.assertEqual(chapters[1]['chapter'], 2)
        self.assertEqual(chapters[1]['title'], 'Deep Dive Evidence')

        self.assertEqual(chapters[2]['chapter'], 3)
        self.assertEqual(chapters[2]['title'], 'The Verdict')

    def test_format_youtube_chapters_description(self):
        chapters = [
            {'chapter': 1, 'title': 'Introduction', 'timestamp': '00:00'},
            {'chapter': 2, 'title': 'The Turning Point', 'timestamp': '01:15'},
            {'chapter': 3, 'title': 'Final Analysis', 'timestamp': '02:45'},
        ]
        block = format_youtube_chapters_description(chapters)
        self.assertIn('00:00 - Introduction', block)
        self.assertIn('01:15 - The Turning Point', block)
        self.assertIn('02:45 - Final Analysis', block)

    def test_metadata_attach_youtube_chapters(self):
        desc = 'Official documentary.'
        augmented = _attach_youtube_chapters(desc)
        self.assertTrue(augmented.startswith(desc))

    def test_audio_mixer_has_longform_function(self):
        self.assertTrue(hasattr(am, 'mix_longform_background_music'))

    def test_assemble_with_transitions_concat_fallback(self):
        from unittest.mock import patch
        import subprocess
        from ken_burns import assemble_with_transitions

        # Create two 1-second synthetic color video clips
        test_dir = Path("output/test_fallback")
        test_dir.mkdir(parents=True, exist_ok=True)
        clip1 = test_dir / "clip1.mp4"
        clip2 = test_dir / "clip2.mp4"
        out_clip = test_dir / "out_assembled.mp4"

        cmd1 = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip1)]
        cmd2 = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip2)]
        subprocess.run(cmd1, capture_output=True, check=True)
        subprocess.run(cmd2, capture_output=True, check=True)

        orig_run = subprocess.run
        call_count = [0]

        def mocked_run(cmd, *args, **kwargs):
            call_count[0] += 1
            # Simulate failure on xfade command (which has -filter_complex)
            if "-filter_complex" in cmd:
                class FailedRes:
                    returncode = 1
                    stderr = "Simulated xfade filter complex error"
                    stdout = ""
                return FailedRes()
            return orig_run(cmd, *args, **kwargs)

        with patch("subprocess.run", side_effect=mocked_run):
            res_path = assemble_with_transitions([str(clip1), str(clip2)], str(out_clip))

        self.assertTrue(os.path.exists(res_path))
        self.assertGreater(os.path.getsize(res_path), 1000)

        # Cleanup
        for p in (clip1, clip2, out_clip):
            if p.exists():
                p.unlink(missing_ok=True)
        test_dir.rmdir()


if __name__ == '__main__':
    unittest.main()
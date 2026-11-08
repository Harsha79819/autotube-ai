import unittest
import os
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

class TestImageAspectAndRealism(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = ROOT / "output" / "test_aspect_suite"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def test_landscape_to_vertical_smart_fit(self):
        from providers.image import clean_and_crop_image
        test_img = self.tmp_dir / "landscape_test.jpg"
        # 16:9 landscape image
        Image.new("RGB", (1280, 720), (200, 100, 50)).save(test_img)

        clean_and_crop_image(test_img, aspect_ratio="9:16")
        im = Image.open(test_img)
        self.assertEqual(im.size, (1080, 1920), "Must format to exact 1080x1920 canvas")

    def test_portrait_native_clean_crop(self):
        from providers.image import clean_and_crop_image
        test_img = self.tmp_dir / "portrait_test.jpg"
        # 9:16 portrait image
        Image.new("RGB", (720, 1280), (50, 120, 200)).save(test_img)

        clean_and_crop_image(test_img, aspect_ratio="9:16")
        im = Image.open(test_img)
        self.assertEqual(im.size, (1080, 1920), "Portrait must scale to exact 1080x1920")

    def test_ken_burns_clamped_motion(self):
        from ken_burns import build_ken_burns_clip, get_clip_duration
        test_img = self.tmp_dir / "kb_test.jpg"
        Image.new("RGB", (1080, 1920), (30, 40, 50)).save(test_img)
        out_clip = self.tmp_dir / "kb_clip.mp4"

        build_ken_burns_clip(test_img, out_clip, duration_seconds=1.5, direction="zoom_in")
        self.assertTrue(out_clip.exists())
        self.assertGreater(out_clip.stat().st_size, 5000)
        dur = get_clip_duration(out_clip)
        self.assertAlmostEqual(dur, 1.5, delta=0.3)

    def test_typography_card_badge_clamping(self):
        from agents.typography_card import generate_typography_card
        card_out = self.tmp_dir / "long_badge_card.jpg"
        long_badge = "HYDERABAD TRAFFIC POLICE SPECIAL DRIVE AGAINST MOBILE PHONES 2026 HIGHLIGHT"
        ok = generate_typography_card(
            headline_text="నాలుగు వేల మందిపై ట్రాఫిక్ పోలీసులు కేసులు నమోదు చేశారు",
            output_path=str(card_out),
            topic_category="general",
            aspect_ratio="9:16",
            badge_label=long_badge,
        )
        self.assertTrue(ok)
        self.assertTrue(card_out.exists())
        im = Image.open(card_out)
        self.assertEqual(im.size, (1080, 1920))

    def tearDown(self):
        import shutil
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()

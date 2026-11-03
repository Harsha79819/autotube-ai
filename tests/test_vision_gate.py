import unittest
import tempfile
import shutil
from pathlib import Path
from PIL import Image

from agents.vision_gate import audit_and_heal_visual_assets
from data.negative_ledger import get_negative_ledger


class TestVisionGate(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.ledger = get_negative_ledger()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_clean_assets_pass_and_scale(self):
        # Create 2 valid 1080x1920 images
        img1_p = self.temp_dir / "1.jpg"
        img2_p = self.temp_dir / "2.jpg"

        Image.new("RGB", (1080, 1920), color=(30, 30, 30)).save(img1_p)
        Image.new("RGB", (1080, 1920), color=(50, 50, 50)).save(img2_p)

        all_ok, rep = audit_and_heal_visual_assets(
            assets_dir=self.temp_dir,
            aspect_ratio="9:16",
            topic="Bigg Boss Telugu 10 Episode Review"
        )
        self.assertTrue(all_ok)
        self.assertEqual(rep["total_assets"], 2)
        self.assertEqual(rep["clean_count"], 2)
        self.assertEqual(rep["healed_count"], 0)

    def test_corrupt_asset_auto_healed(self):
        # Create 1 corrupt 0-byte file
        img1_p = self.temp_dir / "1.jpg"
        img1_p.write_bytes(b"corrupt non-image data")

        all_ok, rep = audit_and_heal_visual_assets(
            assets_dir=self.temp_dir,
            aspect_ratio="9:16",
            topic="Bigg Boss Telugu 10 Episode Review"
        )
        self.assertTrue(all_ok)
        self.assertEqual(rep["total_assets"], 1)
        self.assertEqual(rep["healed_count"], 1)

        # Confirm the file is now a valid PIL image
        with Image.open(img1_p) as im:
            self.assertEqual(im.size, (1080, 1920))


if __name__ == "__main__":
    unittest.main()

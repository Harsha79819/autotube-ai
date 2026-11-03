import unittest
import tempfile
import shutil
import json
from pathlib import Path
from PIL import Image

from agents.news_verifier import validate_visual_assets


class TestDynamicFallbacks(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.output_dir = Path("output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dp_file = self.output_dir / "delivery_plan.json"
        self.meta_file = self.output_dir / "metadata.json"

        # Backup existing output files if any
        self.dp_backup = self.dp_file.read_text(encoding="utf-8") if self.dp_file.exists() else None
        self.meta_backup = self.meta_file.read_text(encoding="utf-8") if self.meta_file.exists() else None

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if self.dp_backup:
            self.dp_file.write_text(self.dp_backup, encoding="utf-8")
        elif self.dp_file.exists():
            self.dp_file.unlink()

        if self.meta_backup:
            self.meta_file.write_text(self.meta_backup, encoding="utf-8")
        elif self.meta_file.exists():
            self.meta_file.unlink()

    def test_non_bb_topic_generates_cinema_card_without_bb_labels(self):
        # Configure delivery plan for a Tollywood movie topic (e.g., Kalki / Prabhas)
        self.meta_file.write_text(json.dumps({
            "title": "Kalki 2898 AD Box Office Records Prabhas Starrer Movie",
        }), encoding="utf-8")
        self.dp_file.write_text(json.dumps([
            {
                "beat_id": 1,
                "main_entity": "Prabhas",
                "spoken_text": "కల్కి మూవీ బాక్సాఫీస్ వద్ద రికార్డుల సునామీ సృష్టించింది"
            }
        ]), encoding="utf-8")

        # Put a corrupt 0-byte file as 1.jpg
        img_path = self.temp_dir / "1.jpg"
        img_path.write_bytes(b"corrupt")

        rep = validate_visual_assets(assets_dir=self.temp_dir)
        self.assertEqual(rep["corrupt_count"], 1)
        self.assertIn("1.jpg", rep["replaced"])

        # Confirm 1.jpg was generated as a valid image
        self.assertTrue(img_path.exists())
        with Image.open(img_path) as im:
            self.assertEqual(im.size, (1080, 1920))

    def test_bb_topic_with_rohit_generates_rohit_card(self):
        # Configure delivery plan for Rohit in Bigg Boss 10
        self.meta_file.write_text(json.dumps({
            "title": "Rohit Patnam Shocking Nomination Drama in Bigg Boss Telugu 10",
        }), encoding="utf-8")
        self.dp_file.write_text(json.dumps([
            {
                "beat_id": 1,
                "main_entity": "Rohit Patnam",
                "spoken_text": "రోహిత్ పట్నం నామినేషన్ లో వేసిన ప్లాన్ అదిరిపోయింది"
            }
        ]), encoding="utf-8")

        # Put a corrupt file as 1.jpg
        img_path = self.temp_dir / "1.jpg"
        img_path.write_bytes(b"corrupt")

        rep = validate_visual_assets(assets_dir=self.temp_dir)
        self.assertEqual(rep["corrupt_count"], 1)
        self.assertIn("1.jpg", rep["replaced"])
        self.assertIn("ROHIT", rep["details"]["1.jpg"]["reason"])
        self.assertIn("BIGG BOSS 10", rep["details"]["1.jpg"]["reason"])


if __name__ == "__main__":
    unittest.main()

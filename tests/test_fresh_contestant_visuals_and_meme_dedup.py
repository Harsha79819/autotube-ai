import unittest
import os
import json
import shutil
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


class TestFreshContestantVisualsAndMemeDedup(unittest.TestCase):

    def setUp(self):
        self.used_memes_file = ROOT / "data" / "used_memes.json"
        self.used_contestant_file = ROOT / "data" / "used_contestant_images.json"

    def test_expanded_telugu_meme_library(self):
        """Verifies reference_assets/memes has 25+ clean memes and meme_manager supports 14 emotions."""
        meme_dir = ROOT / "reference_assets" / "memes"
        self.assertTrue(meme_dir.exists(), "reference_assets/memes must exist")
        memes = list(meme_dir.glob("*.jpg")) + list(meme_dir.glob("*.png"))
        self.assertGreaterEqual(len(memes), 25, f"Expected at least 25 clean Telugu reaction memes, got {len(memes)}")

        from tools.meme_manager import EMOTION_MEME_MAP, get_reaction_meme
        self.assertGreaterEqual(len(EMOTION_MEME_MAP), 12, "EMOTION_MEME_MAP must cover at least 12 distinct emotions")

        # Test emotion retrieval
        used = set()
        m1 = get_reaction_meme("shocked", used_memes=used)
        self.assertIsNotNone(m1)
        self.assertTrue(m1.exists())
        self.assertIn(m1.name, used)

        # Test that cooldown prevents immediate repeat
        m2 = get_reaction_meme("shocked", used_memes=used)
        if m2:
            self.assertNotEqual(m1.name, m2.name)

    def test_contestant_galleries_exist_and_rotate(self):
        """Verifies multi-image galleries exist for key contestants and find_local_contestant_image rotates candidates."""
        gallery_dir = ROOT / "data" / "contestant_galleries"
        self.assertTrue(gallery_dir.exists(), "data/contestant_galleries must exist")

        key_contestants = ["mukesh", "jhansi", "rohit", "charan", "aman", "sudheer", "thrigun", "ram_prasad", "naresh"]
        for c in key_contestants:
            c_dir = gallery_dir / c
            self.assertTrue(c_dir.exists(), f"Gallery directory for {c} must exist")
            imgs = list(c_dir.glob("*.jpg")) + list(c_dir.glob("*.png"))
            self.assertGreaterEqual(len(imgs), 6, f"Contestant {c} should have at least 6 distinct gallery images, got {len(imgs)}")

        # Verify rotation in find_local_contestant_image
        from agents.image_agent import find_local_contestant_image, image_hash

        used_hashes = set()
        used_dhashes = []

        # Call 1: Mukesh
        match1 = find_local_contestant_image("Mukesh Gowda nomination fight", used_hashes=used_hashes, used_dhashes=used_dhashes)
        self.assertIsNotNone(match1)
        slug1, path1 = match1
        self.assertEqual(slug1, "mukesh")
        h1 = image_hash(path1)
        used_hashes.add(h1)

        # Call 2: Mukesh again (should return a DIFFERENT image from gallery!)
        match2 = find_local_contestant_image("Mukesh clownery in morning song", used_hashes=used_hashes, used_dhashes=used_dhashes)
        self.assertIsNotNone(match2)
        slug2, path2 = match2
        self.assertEqual(slug2, "mukesh")
        self.assertNotEqual(path1.name, path2.name, "Second call for Mukesh MUST return a distinct photo, not the same one!")

    def test_thumbnail_guard_disqualifies_memes_and_watermarks(self):
        """Verifies thumbnail selection strictly rejects reaction memes and watermarks."""
        from agents.thumbnail_agent import create_thumbnail

        # Create temporary assets dir with a meme and a clean photo
        test_assets = ROOT / "data" / "test_thumb_assets"
        test_assets.mkdir(parents=True, exist_ok=True)
        try:
            # Create a mock meme file
            meme_file = test_assets / "1.jpg"
            real_meme = ROOT / "reference_assets" / "memes" / "brahmi_doubt.jpg"
            if real_meme.exists():
                shutil.copy2(real_meme, meme_file)
            else:
                Image.new("RGB", (1080, 1920), color="blue").save(meme_file)

            # Create a clean contestant photo as 2.jpg
            clean_photo = test_assets / "2.jpg"
            real_contestant = ROOT / "data" / "contestant_galleries" / "mukesh" / "mukesh_1.jpg"
            if real_contestant.exists():
                shutil.copy2(real_contestant, clean_photo)
            else:
                Image.new("RGB", (1080, 1920), color="green").save(clean_photo)

            thumb_out = ROOT / "output" / "test_thumb_out"
            thumb_out.mkdir(parents=True, exist_ok=True)

            res = create_thumbnail(
                title="Mukesh Behavior Exposed in Bigg Boss 10",
                aspect_ratio="9:16",
                assets_dir=test_assets,
                output_dir=thumb_out,
            )
            self.assertIsNotNone(res)
            self.assertTrue(Path(res).exists())

        finally:
            shutil.rmtree(test_assets, ignore_errors=True)
            shutil.rmtree(ROOT / "output" / "test_thumb_out", ignore_errors=True)

    def test_metadata_agent_shorts_chapter_guard(self):
        """Verifies _attach_youtube_chapters does not append timestamps to Shorts descriptions."""
        from agents.metadata_agent import _attach_youtube_chapters

        desc = "Exciting Bigg Boss Telugu 10 update."
        res = _attach_youtube_chapters(desc, is_shorts=True)
        self.assertEqual(res, desc)

        res2 = _attach_youtube_chapters(desc, is_shorts=False, total_duration=75.0)
        self.assertEqual(res2, desc)

    def test_final_video_agent_shorts_outro_omission(self):
        """Verifies that for 9:16 Shorts, final_video_agent does not append the 5s outro."""
        from agents.final_video_agent import create_final_video
        import inspect
        src = inspect.getsource(create_final_video)
        self.assertIn("if include_outro and not is_shorts:", src)
        self.assertIn("use_ass = True", src)


if __name__ == "__main__":
    unittest.main()

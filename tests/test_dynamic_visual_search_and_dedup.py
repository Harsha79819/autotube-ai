import os
import shutil
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from agents.image_agent import (
    build_contextual_search_query,
    get_contextual_negative_filters,
    is_blacklisted_candidate,
    image_dhash,
    hamming_distance,
    is_perceptual_duplicate,
    find_local_contestant_image,
    image_hash,
)
from providers.image import generate_pollinations_image


class TestDynamicVisualSearchAndDedup(unittest.TestCase):

    def test_single_names_are_never_searched_alone(self):
        """Verify that single bare names are never returned without contextual anchors."""
        # Bare name Rohit in Bigg Boss context
        core_q1, full_q1 = build_contextual_search_query("Rohit", "Bigg Boss Telugu 10 Nominations", "Rohit argument with Jhansi", "reality show")
        self.assertNotIn('^"Rohit"$', core_q1)
        self.assertTrue("Bigg Boss" in core_q1 or "Telugu" in core_q1 or "contestant" in core_q1)
        self.assertTrue("Rohit" in core_q1)

        # Bare name Ram in movie roast context
        core_q2, full_q2 = build_contextual_search_query("Ram", "Double iSmart Movie Roast", "Ram Pothineni punch dialogue", "movie roast")
        self.assertTrue("Double iSmart" in core_q2 or "movie" in core_q2 or "Ram" in core_q2)

        # Bare name Charan in reality show context
        core_q3, full_q3 = build_contextual_search_query("Charan", "Bigg Boss Telugu Season 10", "Charan voting controversy", "reality tv")
        self.assertTrue("Bigg Boss" in core_q3 or "contestant" in core_q3)
        # Verify negative filter prevents Ram Charan collision
        neg = get_contextual_negative_filters("Charan", "Bigg Boss Telugu Season 10")
        self.assertIn("ram charan", neg.lower())

    def test_contextual_negative_filters(self):
        """Verify negative filters block sports, cricket, stamps, and off-target celebrities."""
        # For reality TV Rohit
        neg_rohit = get_contextual_negative_filters("Rohit", "Bigg Boss Telugu 10").lower()
        self.assertIn("cricket", neg_rohit)
        self.assertIn("rohit sharma", neg_rohit)
        self.assertIn("stamp", neg_rohit)

        # For historical Jhansi collision in entertainment
        neg_jhansi = get_contextual_negative_filters("Jhansi", "Bigg Boss Telugu 10 Roast").lower()
        self.assertIn("fort", neg_jhansi)
        self.assertIn("lakshmibai", neg_jhansi)

        # For cricketer when topic is actually cricket, should NOT negative filter cricket
        neg_cricket = get_contextual_negative_filters("Rohit Sharma", "IPL 2026 Mumbai Indians Match Review").lower()
        self.assertNotIn("-cricket", neg_cricket)

    def test_is_blacklisted_candidate_collision_protection(self):
        """Test candidate blacklist detection for URL and title tokens."""
        # Reality Rohit should reject Rohit Sharma cricket images
        cand_cricket = {
            "image_url": "https://sports.ndtv.com/cricket/rohit-sharma-fifty.jpg",
            "title": "Rohit Sharma scores century in test match",
        }
        self.assertTrue(is_blacklisted_candidate(
            cand_cricket,
            target_entity="Rohit",
            topic_context="Bigg Boss Telugu 10"
        ))

        # Reality Charan should reject Ram Charan movie images
        cand_ram_charan = {
            "image_url": "https://filmfare.com/photos/ram-charan-game-changer.jpg",
            "title": "Ram Charan poses at Game Changer teaser launch",
        }
        self.assertTrue(is_blacklisted_candidate(
            cand_ram_charan,
            target_entity="Charan",
            topic_context="Bigg Boss Telugu 10"
        ))

        # Reality Jhansi should reject Jhansi Fort historical monuments
        cand_jhansi_fort = {
            "image_url": "https://monuments.gov.in/jhansi-fort-architecture.jpg",
            "title": "Rani Jhansi Fort Uttar Pradesh Tourism",
        }
        self.assertTrue(is_blacklisted_candidate(
            cand_jhansi_fort,
            target_entity="Jhansi",
            topic_context="Bigg Boss Telugu 10"
        ))

        # Legitimate candidate should pass
        cand_valid = {
            "image_url": "https://starmaa.hotstar.com/biggboss/rohit-patnam-interview.jpg",
            "title": "Rohit Patnam nominated in Bigg Boss Telugu house",
        }
        self.assertFalse(is_blacklisted_candidate(
            cand_valid,
            target_entity="Rohit",
            topic_context="Bigg Boss Telugu 10"
        ))

    def test_perceptual_dhash_and_hamming_deduplication(self):
        """Test perceptual difference hash (dHash) and Hamming distance deduplication."""
        with tempfile.TemporaryDirectory() as tmpdir:
            img1_path = Path(tmpdir) / "img1.png"
            img2_path = Path(tmpdir) / "img2.png"
            img3_path = Path(tmpdir) / "img3.png"

            # Create an image with a horizontal gradient / pattern
            im1 = Image.new("RGB", (200, 200), color=(50, 100, 150))
            for x in range(200):
                for y in range(100):
                    im1.putpixel((x, y), (x, y, 100))
            im1.save(img1_path)

            # img2 is a resized version of img1 (should have nearly identical dHash)
            im2 = im1.resize((100, 100))
            im2.save(img2_path)

            # img3 is completely different (vertical bright stripe)
            im3 = Image.new("RGB", (200, 200), color=(250, 250, 250))
            for x in range(50):
                for y in range(200):
                    im3.putpixel((x, y), (10, 10, 10))
            im3.save(img3_path)

            h1 = image_dhash(img1_path)
            h2 = image_dhash(img2_path)
            h3 = image_dhash(img3_path)

            self.assertIsNotNone(h1)
            self.assertIsNotNone(h2)
            self.assertIsNotNone(h3)

            # Distance between identical / resized images should be 0 or near 0
            dist_1_2 = hamming_distance(h1, h2)
            self.assertLessEqual(dist_1_2, 2)
            self.assertTrue(is_perceptual_duplicate(h2, [h1], max_dist=6))

            # Distance between completely different images should be large (> 10)
            dist_1_3 = hamming_distance(h1, h3)
            self.assertGreater(dist_1_3, 10)
            self.assertFalse(is_perceptual_duplicate(h3, [h1], max_dist=6))

    def test_local_contestant_single_use_deduplication(self):
        """Verify local contestant images are strictly single-use and deduplicated."""
        used_hashes = set()
        used_dhashes = []

        # First match for Rohit should find local file in reference_assets/contestants
        res1 = find_local_contestant_image("Rohit Patnam", used_hashes=used_hashes, used_dhashes=used_dhashes)
        self.assertIsNotNone(res1)
        slug1, path1 = res1
        self.assertEqual(slug1, "rohit")
        self.assertTrue(path1.exists())

        # Register as used in scene 1
        used_hashes.add(image_hash(path1))
        used_dhashes.append(image_dhash(path1))

        # Second call for scene 2 MUST return a different candidate (or None if exhausted), never repeating path1!
        res2 = find_local_contestant_image("Rohit Patnam", used_hashes=used_hashes, used_dhashes=used_dhashes)
        if res2:
            slug2, path2 = res2
            self.assertEqual(slug2, "rohit")
            self.assertNotEqual(path1, path2, "Second call for Rohit must not repeat the first photo")


if __name__ == "__main__":
    unittest.main()

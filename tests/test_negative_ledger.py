import unittest
import tempfile
from pathlib import Path
from PIL import Image

from data.negative_ledger import NegativeMemoryLedger, get_negative_ledger, compute_image_hash


class TestNegativeMemoryLedger(unittest.TestCase):
    def setUp(self):
        self.ledger = get_negative_ledger()

    def test_baseline_exclusions_seeded(self):
        # Season 7 / 8 / 9 OCR patterns should be caught
        clean, reason = self.ledger.is_ocr_text_banned("Exclusive Bigg Boss 7 Promo")
        self.assertTrue(clean)
        self.assertIn("Prior season Bigg Boss 7", reason)

        clean8, reason8 = self.ledger.is_ocr_text_banned("Contestant Bigg Boss 8 Eye Logo")
        self.assertTrue(clean8)
        self.assertIn("Prior season Bigg Boss 8", reason8)

    def test_ban_url_and_domain(self):
        test_url = "https://spamsite.xyz/fake_news/article_123.jpg"
        self.ledger.ban_url(test_url, "Verified clickbait source")

        banned, reason = self.ledger.is_url_banned(test_url)
        self.assertTrue(banned)
        self.assertIn("Verified clickbait source", reason)

        test_domain = "https://badpublisher.org/stills/photo.jpg"
        self.ledger.ban_domain("badpublisher.org", "Low-resolution aggregator")
        banned_dom, r_dom = self.ledger.is_domain_banned(test_domain)
        self.assertTrue(banned_dom)
        self.assertIn("Low-resolution aggregator", r_dom)

    def test_ban_image_hash(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            temp_path = Path(f.name)

        try:
            # Create a simple red test image
            img = Image.new("RGB", (300, 300), color=(255, 0, 0))
            img.save(temp_path)

            h = compute_image_hash(temp_path)
            self.assertTrue(len(h) > 0)

            # Ban it
            self.ledger.ban_image_hash(temp_path, "Corrupt or wrong contestant image")

            # Check audit
            banned_h, r_h = self.ledger.is_image_hash_banned(temp_path)
            self.assertTrue(banned_h)
            self.assertIn("Corrupt or wrong contestant image", r_h)

            # Audit candidate one-stop check
            clean, audit_reason = self.ledger.audit_candidate(image_path=temp_path)
            self.assertFalse(clean)
            self.assertIn("Corrupt or wrong contestant image", audit_reason)
        finally:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

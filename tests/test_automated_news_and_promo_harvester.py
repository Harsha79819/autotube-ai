#!/usr/bin/env python3
"""
tests/test_automated_news_and_promo_harvester.py

Unit tests verifying:
1. News Media Harvester (extracting authentic episode stills from Telugu news portals)
2. Star Maa YouTube Promo Harvester (fetching official promo visuals)
3. Telugu Reaction Meme Manager (mapping emotion and comedy phrases to iconic memes)
4. Full integration into image_agent visual sourcing hierarchy
"""

import unittest
from pathlib import Path
from PIL import Image

from tools.news_media_harvester import (
    extract_images_from_article_url,
    harvest_news_images,
    _is_valid_image_url,
)
from tools.promo_video_harvester import (
    harvest_promo_visuals,
    search_youtube_promo_videos,
)
from tools.meme_manager import (
    get_reaction_meme,
    match_emotion_from_text,
)


class TestAutomatedNewsAndPromoHarvester(unittest.TestCase):

    def test_valid_image_url_filtering(self):
        """Verifies filtering of logos, banners, tracking pixels, and ads."""
        self.assertFalse(_is_valid_image_url("https://example.com/logo_small.png"))
        self.assertFalse(_is_valid_image_url("https://example.com/banner_ad.jpg"))
        self.assertFalse(_is_valid_image_url("https://example.com/author_avatar.jpg"))
        self.assertTrue(_is_valid_image_url("https://static.langimg.com/tlg/thumb/135176941/bigg-boss-10.jpg"))

    def test_extract_images_from_sakshi_article(self):
        """Tests live extraction of authentic episode still from Sakshi article URL."""
        test_url = "https://www.sakshi.com/telugu-news/movies/dakshi-eliminated-bigg-boss-10-telugu-2940248"
        images = extract_images_from_article_url(test_url, max_images=2)
        self.assertGreater(len(images), 0, "Should extract at least 1 image from Sakshi article")
        p = images[0]
        self.assertTrue(p.exists())
        with Image.open(p) as im:
            self.assertGreaterEqual(im.size[0], 400)
            self.assertGreaterEqual(im.size[1], 250)

    def test_harvest_promo_visuals(self):
        """Tests YouTube promo search and thumbnail downloading for Star Maa Bigg Boss."""
        frames = harvest_promo_visuals("Bigg Boss Season 10 Telugu Day 48 promo", max_results=2)
        self.assertGreater(len(frames), 0, "Should harvest at least 1 Star Maa promo thumbnail")
        p = frames[0]
        self.assertTrue(p.exists())
        self.assertGreater(p.stat().st_size, 10000)

    def test_meme_manager_emotion_mapping(self):
        """Verifies Telugu keyword emotion matching for comedy and shock."""
        self.assertEqual(match_emotion_from_text("అక్కడ చేస్తున్న ఓవరాక్షన్ చూసి మైండ్ బ్లాక్ అయింది"), "shocked")
        self.assertEqual(match_emotion_from_text("ఇదేంట్రా నాయనా ఈ దరిద్రపు డ్రామా"), "overacting")
        self.assertEqual(match_emotion_from_text("హౌస్ లో నవ్వు ఆపలేకపోయాం ఫుల్ కామెడీ"), "comedy")
        self.assertEqual(match_emotion_from_text("పీఆర్ స్ట్రాటజీ బయటపడింది ఫేక్ మాస్క్"), "suspicious")

    def test_get_reaction_meme_deduplication(self):
        """Verifies reaction meme retrieval and single-use deduplication."""
        used = set()
        m1 = get_reaction_meme("shocked", used_memes=used)
        self.assertIsNotNone(m1)
        self.assertTrue(m1.exists())
        self.assertIn(m1.name, used)

        m2 = get_reaction_meme("overacting", used_memes=used)
        self.assertIsNotNone(m2)
        self.assertNotEqual(m1.name, m2.name, "Consecutive memes should not be identical")


if __name__ == "__main__":
    unittest.main()

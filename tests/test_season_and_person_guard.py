"""
tests/test_season_and_person_guard.py - Regression test for Season 10 Context Locking & Person Verification
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.season_guard import (
    get_current_season_number,
    is_conflicting_season_candidate,
    extract_person_from_scene,
    verify_candidate_person,
)


class TestSeasonAndPersonGuard(unittest.TestCase):

    def test_season_number_extraction(self):
        self.assertEqual(get_current_season_number("Bigg Boss Telugu 10"), 10)
        self.assertEqual(get_current_season_number("Bigboss 10"), 10)
        self.assertEqual(get_current_season_number("BB10"), 10)
        self.assertEqual(get_current_season_number("Bigg Boss Telugu 8"), 8)

    def test_past_season_rejection(self):
        cur_season = 10
        # Check URLs from previous contaminated run
        failed_run_urls = [
            "https://www.indiaherald.com/ImageStore/images/movies/movies-general/bigg-boss-telugu-season-3-day-14-hot-stills-set-25.jpg",
            "https://www.siasat.com/wp-content/uploads/2024/09/Bigg-Boss-Telugu-8-2.jpg",
            "https://images.indianexpress.com/2025/12/Kalyan-Padala-Bigg-Boss-Telugu-9-winner.jpg",
            "https://www.bizzbuzz.news/h-upload/2025/12/04/1983277-bigg-boss-9-telugu-day-87-.jpg",
            "https://pbs.twimg.com/media/bb8-nomination-drama.jpg",
        ]
        for url in failed_run_urls:
            self.assertTrue(
                is_conflicting_season_candidate(url, current_season=cur_season),
                f"Failed to reject past season URL: {url}"
            )

        # Valid Season 10 URLs must pass
        valid_s10_urls = [
            "https://pbs.twimg.com/media/Bigg-Boss-Telugu-10-launch.jpg",
            "https://example.com/bb10-telugu-promo.jpg",
            "https://example.com/candid-telugu-housemate.jpg",
        ]
        for url in valid_s10_urls:
            self.assertFalse(
                is_conflicting_season_candidate(url, current_season=cur_season),
                f"Incorrectly rejected valid S10 URL: {url}"
            )

    def test_person_extraction_from_scene(self):
        self.assertEqual(
            extract_person_from_scene("నాగార్జున గారి తీర్పులు చూస్తుంటే, కొందరికి వార్నింగ్..."),
            "Nagarjuna"
        )
        self.assertEqual(
            extract_person_from_scene("సుధీర్ కామెడీ టైమింగ్‌తో అందర్నీ ఎంటర్‌టైన్ చేస్తున్నాడు."),
            "Sudheer Reddy"
        )
        self.assertEqual(
            extract_person_from_scene("రోహిత్ నామినేషన్ ప్రాసెస్ చూస్తుంటే..."),
            "Rohit Patnam"
        )
        self.assertIsNone(
            extract_person_from_scene("బిగ్ బాస్ చూస్తుంటే ఇప్పుడు రియాలిటీ షో లా లేదు బాస్...")
        )

    def test_person_verification_and_conflict(self):
        target = "Nagarjuna"

        # Matching candidate
        match_cand = "Nagarjuna Akkineni hosting Bigg Boss Telugu 10 weekend episode"
        is_m, is_c = verify_candidate_person(match_cand, target_person=target)
        self.assertTrue(is_m)
        self.assertFalse(is_c)

        # Conflicting candidates (mention other contestants)
        conflict_cand1 = "Rohit Patnam celebrates Bigg Boss Telugu victory with family"
        is_m, is_c = verify_candidate_person(conflict_cand1, target_person=target)
        self.assertFalse(is_m)
        self.assertTrue(is_c)

        conflict_cand2 = "Varshini eviction interview after Bigg Boss Telugu"
        is_m, is_c = verify_candidate_person(conflict_cand2, target_person=target)
        self.assertFalse(is_m)
        self.assertTrue(is_c)

    def test_thrigun_and_aman_person_extraction(self):
        # Telugu and English scene texts
        self.assertEqual(
            extract_person_from_scene("త్రిగుణ్ ఎంట్రీతో హౌస్‌లో గేమ్ మొత్తం మారిపోయింది!"),
            "Thrigun"
        )
        self.assertEqual(
            extract_person_from_scene("Trigun and Aman won the immunity task!"),
            "Thrigun"  # First match
        )
        self.assertEqual(
            extract_person_from_scene("ఎప్పుడూ సైలెంట్‌గా ఉండే Aman సడన్‌గా నిద్రలేచి immunity కొట్టేశాడు!"),
            "Aman Masud"
        )

    def test_unwanted_anime_and_wrestling_candidate_rejection(self):
        from utils.season_guard import is_unwanted_visual_candidate, get_person_disallowed_terms

        # Trigun anime wallpapers must be strictly rejected
        thrigun_disallow = get_person_disallowed_terms("Thrigun")
        anime_urls = [
            "https://wallpapercrafter.com/th8005/1376245-trigun-1080P.jpg",
            "https://a-static.besthdwallpaper.com/trigun-vash-the-stampede-wallpaper-2048x115",
            "https://wallpapers.com/images/hd/blonde-hair-blue-eyes-vash-trigun-oixzmyaj67aod",
            "https://animotaku.fr/wp-content/uploads/2025/10/anime-trigun-stargaze-janvier-20",
            "https://images8.alphacoders.com/849/849732.jpg",
        ]
        for url in anime_urls:
            self.assertTrue(
                is_unwanted_visual_candidate(url, disallow_terms=thrigun_disallow, is_bb_context=True),
                f"Failed to reject anime url: {url}"
            )

        # Aman wrestling photos must be strictly rejected (via disallow terms or past year 2024 date)
        aman_disallow = get_person_disallowed_terms("Aman")
        wrestler_urls = [
            "https://images.bhaskarassets.com/web2images/521/2024/08/10/aman_1723235206.jpeg",
            "https://staticimg.amarujala.com/assets/images/2024/08/10/amana-saharavata_278c30",
            "https://img.republicworld.com/all_images/aman-sehrawat-1723226833991-16_9.webp",
            "Aman Sehrawat wins bronze medal at Olympics in wrestling",
        ]
        for item in wrestler_urls:
            self.assertTrue(
                is_conflicting_season_candidate(item, current_season=10, is_bb_context=True, disallow_terms=aman_disallow),
                f"Failed to reject wrestling item: {item}"
            )

        # Authentic Bigg Boss 10 still must PASS
        valid_still = "https://static.10tv.in/wp-content/uploads/2026/06/Bigg-Boss-Telugu-10-Aman-stills.jpg"
        self.assertFalse(
            is_conflicting_season_candidate(valid_still, current_season=10, is_bb_context=True, disallow_terms=aman_disallow)
        )

    def test_pan_india_and_common_nouns_not_person(self):
        # Common English adjectives/nouns must NEVER be extracted as people
        self.assertIsNone(extract_person_from_scene("ఆ హైప్ చూస్తే 'Pan-India' రేంజ్..."))
        self.assertIsNone(extract_person_from_scene("గ్రాండ్ వెల్కమ్ అని బిల్డప్ ఇచ్చారు..."))
        self.assertIsNone(extract_person_from_scene("గ్రౌండ్ రియాల్టీ చూస్తే 'లోకల్' కామెడీ!"))
        self.assertIsNone(extract_person_from_scene("Double elimination twist shocked everyone."))
        self.assertIsNone(extract_person_from_scene("Super fast task execution in house."))

    def test_kabali_and_rajinikanth_person_extraction(self):
        self.assertEqual(
            extract_person_from_scene('"నేను మళ్ళీ వస్తా" అని కబాలి గెటప్‌లో వచ్చినట్టు ఉంది.'),
            "Rajinikanth"
        )
        self.assertEqual(
            extract_person_from_scene("సూపర్‌స్టార్ రజినీకాంత్ స్టైల్‌లో ఎంట్రీ ఇచ్చాడు."),
            "Rajinikanth"
        )

    def test_global_offtopic_noise_rejection(self):
        # International noise from previous run must be strictly rejected
        bad_urls = [
            "https://esctoday.com/wp-content/uploads/2026/06/bulgaria-eurovision-winner-dara-to-headline-sofia-pride-2026.jpg",
            "https://assets.ejecentral.com.mx/dims4/default/40fa61b/2147483647/strip/true/cro",
            "https://eloutput.com/wp-content/uploads/2025/05/GTA-6-retrasado-2025-1.png",
            "https://wallpapersko.com/wp-content/uploads/2023/01/india-flag-map-hd-wallpaper.jpg",
        ]
        for u in bad_urls:
            self.assertTrue(
                is_conflicting_season_candidate(u, current_season=10, is_bb_context=True),
                f"Failed to reject off-topic noise: {u}"
            )

    def test_apify_persistent_quota_failover(self):
        from providers.apify_social import is_apify_disabled, mark_apify_disabled, APIFY_QUOTA_FLAG_FILE
        mark_apify_disabled()
        self.assertTrue(is_apify_disabled())
        self.assertTrue(APIFY_QUOTA_FLAG_FILE.exists())
        # Clean up test flag
        APIFY_QUOTA_FLAG_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

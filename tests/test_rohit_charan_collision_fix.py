import unittest
from pathlib import Path
from agents.visual_ladder import is_irrelevant_stock_asset, search_all_sources_parallel
from utils.season_guard import (
    is_entertainment_or_roast_topic,
    is_conflicting_season_candidate,
    is_bigg_boss_topic,
)


class TestRohitCharanCollisionFix(unittest.TestCase):
    def test_entertainment_and_bigg_boss_detection(self):
        """Verify that reality show queries and Bigg Boss topics are recognized as entertainment."""
        self.assertTrue(is_bigg_boss_topic("Bigg Boss Telugu 10"))
        self.assertTrue(is_entertainment_or_roast_topic("Bigg Boss Telugu 10"))
        self.assertTrue(is_entertainment_or_roast_topic("Rohit Sahni fight promo"))
        self.assertTrue(is_entertainment_or_roast_topic("Anchor Jhansi elimination"))
        self.assertTrue(is_entertainment_or_roast_topic("Charan nomination debate"))

    def test_rohit_sharma_disqualification(self):
        """Verify cricketer Rohit Sharma is blocked when searching for Rohit / Rohit Sahni."""
        cand_title = "File:Rohit Sharma November 2016 (cropped).jpg"
        cand_url = "https://upload.wikimedia.org/wikipedia/commons/4/4b/Rohit_Sharma.jpg"

        # Disqualified via target_entity
        self.assertTrue(is_irrelevant_stock_asset(cand_title, cand_url, "Rohit Sahni Bigg Boss", target_entity="Rohit Sahni"))
        self.assertTrue(is_irrelevant_stock_asset(cand_title, cand_url, "Rohit Bigg Boss", target_entity="Rohit"))

        # Disqualified via direct season guard candidate check
        self.assertTrue(is_conflicting_season_candidate(f"{cand_title} {cand_url}", target_person="Rohit Sahni"))
        self.assertTrue(is_conflicting_season_candidate(f"{cand_title} {cand_url}", target_person="Rohit"))

    def test_jhansi_fort_disqualification(self):
        """Verify historical Jhansi Fort / Nahargarh Fort is blocked when searching for Anchor Jhansi."""
        cand_title = "File:Nahargarh Fort Jaipur / Jhansi Fort"
        cand_url = "https://upload.wikimedia.org/wikipedia/commons/8/88/Jhansi_Fort.jpg"

        self.assertTrue(is_irrelevant_stock_asset(cand_title, cand_url, "Anchor Jhansi Bigg Boss", target_entity="Jhansi"))
        self.assertTrue(is_conflicting_season_candidate(f"{cand_title} {cand_url}", target_person="Jhansi"))

    def test_ram_charan_disqualification(self):
        """Verify Mega Power Star Ram Charan is blocked when searching for contestant Charan."""
        cand_title = "File:Ram Charan at Dhruva pre-release event.jpg"
        cand_url = "https://upload.wikimedia.org/wikipedia/commons/7/77/Ram_Charan.jpg"

        self.assertTrue(is_irrelevant_stock_asset(cand_title, cand_url, "Charan Bigg Boss Telugu", target_entity="Charan"))
        self.assertTrue(is_conflicting_season_candidate(f"{cand_title} {cand_url}", target_person="Charan"))

    def test_wikimedia_skipped_for_entertainment(self):
        """Verify Wikimedia Commons is skipped completely during parallel retrieval for entertainment topics."""
        cands = search_all_sources_parallel(
            queries=["Rohit Sahni Bigg Boss Telugu 10 nomination"],
            raw_query="Rohit Sahni Bigg Boss Telugu 10 nomination",
            topic_category="entertainment",
            max_candidates=10,
        )
        sources = [c.get("source") for c in cands]
        self.assertNotIn("wikimedia_commons", sources)


if __name__ == "__main__":
    unittest.main()

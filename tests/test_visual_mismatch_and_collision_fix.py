"""
Unit tests for Visual Mismatch Bug Fix in agents/social_visual_selector.py,
utils/season_guard.py, agents/image_agent.py, and agents/visual_ladder.py.
"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from utils.season_guard import (
    is_conflicting_season_candidate,
    get_celebrity_collision_negative_keywords,
    get_celebrity_collision_negative_string,
)
from agents.social_visual_selector import fetch_candidates_for_selection_step
from agents.image_agent import collect_candidates, verify_visual_with_gemini


class TestVisualMismatchAndCollisionFix(unittest.TestCase):

    def test_past_season_regex_rejection_when_target_season_10(self):
        """Test is_conflicting_season_candidate catches Season 9, BB9, S9, and older URLs."""
        # Season 9 variations
        self.assertTrue(is_conflicting_season_candidate("Season 9", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("season 9", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("season-9", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("season9", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("BB9", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("bb9", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("bb-9", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("S9", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("s9", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("s-9", target_season=10))

        # Season 8 variations
        self.assertTrue(is_conflicting_season_candidate("Season 8", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("BB8", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("S8", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("s8", target_season=10))

        # URL path variations
        self.assertTrue(is_conflicting_season_candidate("https://deccanchronicle.com/entertainment/season-9/nagarjuna.jpg", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("https://example.com/images/s9/rohit.jpg", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("https://example.com/images/bb9/charan.jpg", target_season=10))
        self.assertTrue(is_conflicting_season_candidate("https://example.com/photos/s8/stage.jpg", target_season=10))

        # Current season (Season 10) must NOT be rejected
        self.assertFalse(is_conflicting_season_candidate("https://example.com/season-10/rohit.jpg", target_season=10))
        self.assertFalse(is_conflicting_season_candidate("Season 10 contestants live", target_season=10))
        self.assertFalse(is_conflicting_season_candidate("BB10 nominations drama", target_season=10))
        self.assertFalse(is_conflicting_season_candidate("S10 housemates", target_season=10))
        self.assertFalse(is_conflicting_season_candidate("Bigg Boss Telugu 10 promo 2026", target_season=10))

    def test_celebrity_collision_negative_keywords(self):
        """Test dynamic negative keywords for Indian celebrity collisions."""
        rohit_negs = get_celebrity_collision_negative_keywords("Rohit")
        self.assertIn("-cricket", rohit_negs)
        self.assertIn("-sharma", rohit_negs)
        self.assertIn("-hitman", rohit_negs)
        self.assertIn("-ipl", rohit_negs)

        charan_negs = get_celebrity_collision_negative_keywords("Charan")
        self.assertIn("-ram", charan_negs)
        self.assertIn("-konidela", charan_negs)
        self.assertIn("-rrr", charan_negs)
        self.assertIn("-chiranjeevi", charan_negs)

        arjun_negs = get_celebrity_collision_negative_keywords("Arjun")
        self.assertIn("-allu", arjun_negs)
        self.assertIn("-pushpa", arjun_negs)

        # String helper formatting
        rohit_str = get_celebrity_collision_negative_string("Rohit")
        self.assertIn("-cricket", rohit_str)
        self.assertIn("-sharma", rohit_str)

    @patch("agents.social_visual_selector.fetch_social_candidates_for_scene")
    def test_fetch_candidates_enforces_strict_quotes_and_negatives(self, mock_fetch):
        """Test fetch_candidates_for_selection_step enforces strict quoting and collision negatives."""
        mock_fetch.return_value = []

        fetch_candidates_for_selection_step(
            entity_name="Charan",
            person_search_name="Charan Bigg Boss Telugu",
            event_keyword="nominations",
            hashtags=["#BiggBossTelugu10"],
            is_bb=True,
            cur_season=10,
            person_disallow=[],
            person_name="Charan",
        )

        calls = mock_fetch.call_args_list
        self.assertTrue(len(calls) > 0)
        
        found_strict_query = False
        for c in calls:
            kwargs = c.kwargs
            ent = kwargs.get("entity", "")
            if '"Charan" "Bigg Boss Telugu 10"' in ent:
                found_strict_query = True
                self.assertIn("-ram", ent)
                self.assertIn("-konidela", ent)
        self.assertTrue(found_strict_query, "Strict quoted format '\"Charan\" \"Bigg Boss Telugu 10\"' not found in calls")

    @patch("agents.social_visual_selector.fetch_social_candidates_for_scene")
    def test_fetch_candidates_rohit_collision_negatives(self, mock_fetch):
        """Test fetch_candidates for Rohit includes cricket / sharma negatives."""
        mock_fetch.return_value = []

        fetch_candidates_for_selection_step(
            entity_name="Rohit",
            person_search_name="Rohit Sahni Bigg Boss Telugu",
            event_keyword="kitchen argument",
            hashtags=["#BiggBossTelugu10"],
            is_bb=True,
            cur_season=10,
            person_disallow=[],
            person_name="Rohit",
        )

        calls = mock_fetch.call_args_list
        self.assertTrue(len(calls) > 0)
        found_rohit_strict = False
        for c in calls:
            ent = c.kwargs.get("entity", "")
            if '"Rohit" "Bigg Boss Telugu 10"' in ent:
                found_rohit_strict = True
                self.assertIn("-cricket", ent)
                self.assertIn("-sharma", ent)
        self.assertTrue(found_rohit_strict, "Strict quoted format '\"Rohit\" \"Bigg Boss Telugu 10\"' not found")

    @patch("agents.image_agent.search_pexels")
    @patch("agents.image_agent.search_bing")
    def test_collect_candidates_skips_pexels_for_reality_show_topics(self, mock_bing, mock_pexels):
        """Test collect_candidates skips Pexels for reality show / entertainment topics."""
        mock_bing.return_value = []
        mock_pexels.return_value = [{"image_url": "https://example.com/concert.jpg", "title": "Concert Stage"}]

        # Reality show topic
        cands = collect_candidates(
            queries=['"Charan" "Bigg Boss Telugu 10"'],
            topic_category="entertainment",
        )
        mock_pexels.assert_not_called()

        # Non-reality tech topic should call search_pexels
        collect_candidates(
            queries=["iPhone 16 pro max titanium finish"],
            topic_category="tech",
        )
        mock_pexels.assert_called()

    def test_jhansi_and_charan_collision_rejections(self):
        """Test is_conflicting_season_candidate rejects Jhansi Fort and Sree Vishnu for reality contestants."""
        from utils.season_guard import get_person_disallowed_terms

        # 1. Jhansi Fort / monument rejection
        jhansi_disallow = get_person_disallowed_terms("Jhansi")
        self.assertIn("fort", jhansi_disallow)
        fort_cand = "Jhansi Fort historic monument in Uttar Pradesh tourism"
        self.assertTrue(is_conflicting_season_candidate(fort_cand, is_bb_context=True, disallow_terms=jhansi_disallow))

        # 2. Charan / Sree Vishnu / Ram Charan collision rejection
        charan_disallow = get_person_disallowed_terms("Charan")
        self.assertTrue(any("sree vishnu" in d for d in charan_disallow))
        self.assertTrue(any("ram charan" in d for d in charan_disallow))
        sree_vishnu_cand = "Actor Sree Vishnu at movie pre-release event"
        self.assertTrue(is_conflicting_season_candidate(sree_vishnu_cand, is_bb_context=True, disallow_terms=charan_disallow))

        # 3. Season 9 throne / trophy rejection on Season 10
        s9_throne = "Bigg Boss Telugu Season 9 Grand Finale throne celebration"
        self.assertTrue(is_conflicting_season_candidate(s9_throne, target_season=10, is_bb_context=True))


if __name__ == "__main__":
    unittest.main()

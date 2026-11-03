import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from utils.season_guard import (
    resolve_effective_show_context,
    is_entertainment_or_roast_topic,
    is_bigg_boss_topic,
    COMMON_CELEBRITY_COLLISION_NEGATIVES,
    KNOWN_TELUGU_SHOW_PERSONS,
)
from tools.build_entity_library import match_entities_in_text
from agents.visual_ladder import is_irrelevant_stock_asset, search_all_sources_parallel
from agents.visual_agent import source_dual_tier_visual, build_scene_flux_prompt

class TestEntityCollisionAndContextIsolation(unittest.TestCase):

    def test_telugu_entity_no_devara_collision(self):
        """'విజయ్ దేవరకొండ' must NOT trigger 'Devara: Part 1'."""
        text_vd = "విజయ్ దేవరకొండ లేటెస్ట్ రోస్ట్ మరియు డైలాగ్స్"
        matched_vd = match_entities_in_text(text_vd)
        matched_names = [m.get("canonical_name") for m in matched_vd]
        self.assertIn("Vijay Deverakonda", matched_names)
        self.assertNotIn("Devara: Part 1", matched_names)

        # Genuine Devara movie text should match Devara and NOT Vijay Deverakonda
        text_devara = "దేవర సినిమా బాక్సాఫీస్ కలెక్షన్స్ ఎన్టీఆర్"
        matched_devara = match_entities_in_text(text_devara)
        matched_devara_names = [m.get("canonical_name") for m in matched_devara]
        self.assertIn("Devara: Part 1", matched_devara_names)
        self.assertNotIn("Vijay Deverakonda", matched_devara_names)

    def test_resolve_effective_show_context_isolation(self):
        """Stale SHOW_CONTEXT ('bigboss 10 telugu') must be cleared for non-show cinema topics."""
        stale_show_context = "bigboss 10 telugu"

        # 1. Cinema / actor roast topic -> must be empty string
        cinema_topic = "Vijay Deverakonda Rashmika Marriage Rumors and Trolls"
        resolved = resolve_effective_show_context(cinema_topic, "Some script about Tollywood", stale_show_context)
        self.assertEqual(resolved, "")

        # 2. Telugu cinema roast topic -> must be empty string
        telugu_cinema_topic = "విజయ్ దేవరకొండ రోస్ట్ వీడియో"
        resolved_telugu = resolve_effective_show_context(telugu_cinema_topic, "", stale_show_context)
        self.assertEqual(resolved_telugu, "")

        # 3. Legitimate Bigg Boss topic -> must retain show context
        bb_topic = "Bigg Boss 10 Telugu Monday Nominations Fire"
        resolved_bb = resolve_effective_show_context(bb_topic, "బిగ్ బాస్ నామినేషన్స్", stale_show_context)
        self.assertEqual(resolved_bb, stale_show_context)

    def test_is_entertainment_or_roast_topic(self):
        """Verifies detection of entertainment / cinema / roast topics."""
        self.assertTrue(is_entertainment_or_roast_topic("Vijay Deverakonda cinema troll"))
        self.assertTrue(is_entertainment_or_roast_topic("విజయ్ దేవరకొండ రోస్ట్"))
        self.assertTrue(is_entertainment_or_roast_topic("Tollywood hero movie gossip"))
        self.assertFalse(is_entertainment_or_roast_topic("Quantum physics lab experiments"))

    def test_irrelevant_stock_asset_blacklist(self):
        """Laboratory equipment, matchsticks, 19th century art, foreign posters must be flagged irrelevant."""
        # Irrelevant assets
        self.assertTrue(is_irrelevant_stock_asset(
            cand_title="Antique Laboratory glassware and chemical beakers in science lab",
            cand_url="https://commons.wikimedia.org/wiki/File:Chemistry_apparatus.jpg",
            query_text="Vijay Deverakonda speaking",
            target_entity="Vijay Deverakonda"
        ))
        self.assertTrue(is_irrelevant_stock_asset(
            cand_title="Burning matchstick with sulfur flame",
            cand_url="https://commons.wikimedia.org/wiki/File:Matchstick.jpg",
            query_text="Vijay Deverakonda hot looks",
            target_entity="Vijay Deverakonda"
        ))
        self.assertTrue(is_irrelevant_stock_asset(
            cand_title="19th-century oil painting of French countryside landscape",
            cand_url="https://commons.wikimedia.org/wiki/File:Landscape_oil_painting.jpg",
            query_text="Vijay Deverakonda scenic background",
            target_entity="Vijay Deverakonda"
        ))
        self.assertTrue(is_irrelevant_stock_asset(
            cand_title="Vintage Russian circus foreign poster 1920",
            cand_url="https://commons.wikimedia.org/wiki/File:Circus_poster.jpg",
            query_text="Tollywood movie poster",
            target_entity=""
        ))

        # Relevant celebrity assets should NOT be flagged
        self.assertFalse(is_irrelevant_stock_asset(
            cand_title="Vijay Deverakonda at trailer launch event in Hyderabad",
            cand_url="https://example.com/vijay_deverakonda.jpg",
            query_text="Vijay Deverakonda trailer launch",
            target_entity="Vijay Deverakonda"
        ))

    @patch("agents.visual_ladder.search_wikimedia")
    def test_wikimedia_disabled_for_entertainment_roasts(self, mock_search_wm):
        """search_all_sources_parallel must NOT query Wikimedia for entertainment/roast topics."""
        search_all_sources_parallel(
            queries=["Vijay Deverakonda cinema troll"],
            raw_query="Vijay Deverakonda trolling funny scene",
            topic_category="entertainment",
        )
        mock_search_wm.assert_not_called()

    @patch("agents.visual_agent.generate_ai_visual")
    @patch("agents.visual_agent.source_beat_visual")
    def test_flux_fallback_when_editorial_fails(self, mock_source_beat, mock_generate_ai):
        """When real photos are unavailable for cinema roast, source_dual_tier_visual falls back to FLUX AI."""
        mock_source_beat.return_value = {"success": False, "asset_path": ""}
        
        def fake_generate_ai(prompt, dest_path, aspect_ratio="9:16"):
            Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
            Path(dest_path).write_bytes(b"dummy_image_data_at_least_1000_bytes_" * 50)
            return True

        mock_generate_ai.side_effect = fake_generate_ai

        dest_test_jpg = Path("/tmp/test_dual_tier_beat_1.jpg")
        if dest_test_jpg.exists():
            dest_test_jpg.unlink()

        res = source_dual_tier_visual(
            beat_number=1,
            raw_query="Vijay Deverakonda punchline roast",
            narration="విజయ్ దేవరకొండ డైలాగ్స్ మీద అదిరిపోయే రోస్ట్",
            destination_jpg=dest_test_jpg,
            aspect_ratio="9:16",
            topic_category="entertainment",
        )

        mock_generate_ai.assert_called_once()
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("tier"), "TIER_A")
        self.assertEqual(res.get("source"), "pollinations_flux_fallback")
        if dest_test_jpg.exists():
            dest_test_jpg.unlink()

    def test_build_scene_flux_prompt_isolation(self):
        """build_scene_flux_prompt cleans text and respects topic isolation without show context contamination."""
        prompt = build_scene_flux_prompt(
            scene_text="Beat 1: విజయ్ దేవరకొండ స్పీచ్ పై కామెడీ రివ్యూ",
            aspect_ratio="9:16",
            topic_category="entertainment",
            show_context="bigboss 10 telugu"  # Should be neutralized by resolve_effective_show_context
        )
        self.assertNotIn("Bigg Boss Telugu 10", prompt)
        self.assertNotIn("Beat 1:", prompt)
        self.assertIn("9:16 vertical ratio", prompt)

if __name__ == "__main__":
    unittest.main()

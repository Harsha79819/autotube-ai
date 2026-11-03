import unittest
from pathlib import Path
import json

from utils.season_guard import (
    format_strict_visual_query,
    is_generic_visual_query,
    is_conflicting_season_candidate,
    is_bigg_boss_topic,
    get_current_season_number,
    extract_person_from_scene,
)
from agents.script_agent import (
    build_structured_visual_plan,
    synthesize_beat_visual_plan,
)
from agents.image_agent import build_queries
from agents.visual_ladder import rewrite_beat_queries
from agents.social_visual_selector import analyze_scene_with_llm


class TestStrictVisualRetrievalAndSeasonLock(unittest.TestCase):
    def test_format_strict_visual_query(self):
        # Format 1: [Contestant Name] [Season Name] [Year]
        q1 = format_strict_visual_query("Charan Kumar", "Bigg Boss Telugu 10", 2026)
        self.assertEqual(q1, '"Charan Kumar" "Bigg Boss Telugu 10" 2026')

        # Format 2: [Contestant Name] [Specific Task/Promo]
        q2 = format_strict_visual_query("Sudheer", "Bigg Boss Telugu", 2026, task_or_promo="Nominations Confrontation")
        self.assertEqual(q2, '"Sudheer" "Bigg Boss Telugu" "Nominations Confrontation"')

    def test_is_generic_visual_query(self):
        # Generic terms must be rejected
        self.assertTrue(is_generic_visual_query("Bigg Boss Telugu drama"))
        self.assertTrue(is_generic_visual_query("Bigg Boss emotional scene"))
        self.assertTrue(is_generic_visual_query("Bigg Boss Telugu stage"))
        self.assertTrue(is_generic_visual_query("reality show drama"))
        self.assertTrue(is_generic_visual_query("bigg boss housemates"))

        # Specific strict queries must NOT be flagged as generic
        self.assertFalse(is_generic_visual_query('"Charan Kumar" "Bigg Boss Telugu 10" 2026'))
        self.assertFalse(is_generic_visual_query('"Sudheer" "Bigg Boss Telugu" "Nominations Confrontation"'))
        self.assertFalse(is_generic_visual_query("Nagarjuna Akkineni weekend episode hosting stage"))

    def test_past_season_rejection_in_season_guard(self):
        # Deccan Chronicle Season 9 July 2025 Nagarjuna photo with Season 9 logo
        deccan_url = "https://www.deccanchronicle.com/h-upload/2025/07/12/1937320-nagarjuna.webp"
        self.assertTrue(
            is_conflicting_season_candidate(
                deccan_url,
                target_person="Nagarjuna Akkineni",
                current_season=10,
                is_bb_context=True,
            )
        )

        # Candidate mentioning Season 9 or BB9
        self.assertTrue(
            is_conflicting_season_candidate(
                "Bigg Boss Telugu 9 grand finale winner celebration",
                current_season=10,
                is_bb_context=True,
            )
        )
        self.assertTrue(
            is_conflicting_season_candidate(
                "Nagarjuna launching 9 Bigg Boss promo video 2025",
                current_season=10,
                is_bb_context=True,
            )
        )

        # Valid Season 10 candidate from 2026
        self.assertFalse(
            is_conflicting_season_candidate(
                "Bigg Boss Telugu 10 Charan nominations heated confrontation 2026 promo",
                target_person="Charan",
                current_season=10,
                is_bb_context=True,
            )
        )

    def test_build_structured_visual_plan_dynamic_metadata(self):
        sections = [
            {"narration": "బిగ్ బాస్ హౌస్‌లో చరణ్ కుమార్ నామినేషన్స్ హీటెడ్ ఆర్గ్యుమెంట్ జరిగింది."},
            {"narration": "సుధీర్ కెప్టెన్సీ టాస్క్‌లో అద్భుతమైన స్ట్రాటజీ చూపించాడు."},
            {"narration": "నాగార్జున గారు వీకెండ్ ఎపిసోడ్‌లో అందరి క్లాస్ తీసుకున్నారు."},
        ]
        raw_vp = [
            "Bigg Boss Telugu drama",  # generic, should be filtered out
            "Sudheer dynamic action | Captaincy Task",
            "Nagarjuna weekend stage | host discussion",
        ]
        topic = "Bigg Boss Telugu Season 10 Nominations"

        plan = build_structured_visual_plan(sections, raw_vp, topic=topic)
        self.assertEqual(len(plan), 3)

        # Beat 1: Charan Mahadev, Season 10, 2026, Nominations
        b1 = plan[0]
        self.assertTrue(any("Charan" in c for c in b1["contestant_names"]))
        self.assertEqual(b1["season_name"], "Bigg Boss Telugu 10")
        self.assertEqual(b1["event_year"], 2026)
        self.assertEqual(b1["incident_context"], "Nominations Confrontation")
        self.assertIn('"Bigg Boss Telugu 10" 2026', b1["strict_query"])
        # Check negative exclusions
        self.assertTrue(any("-Season 9" in neg for neg in b1["negative_exclusions"]))
        self.assertTrue(any("-BB9" in neg for neg in b1["negative_exclusions"]))
        self.assertTrue(any("-2025" in neg for neg in b1["negative_exclusions"]))
        # Verify generic query was rejected
        self.assertNotIn("Bigg Boss Telugu drama", b1["cleaned_queries"])

        # Beat 2: Sudheer, Captaincy Task
        b2 = plan[1]
        self.assertTrue(any("Sudheer" in c for c in b2["contestant_names"]))
        self.assertEqual(b2["incident_context"], "Captaincy Task")
        self.assertIn('"Bigg Boss Telugu 10" 2026', b2["strict_query"])

        # Beat 3: Host Nagarjuna
        b3 = plan[2]
        self.assertIn("Nagarjuna Akkineni", b3["contestant_names"])

    def test_image_agent_build_queries_strict_formatting(self):
        # When querying for a Bigg Boss contestant, strict format and negative exclusions are enforced
        queries = build_queries(
            visual_description="Charan confrontation in Bigg Boss Telugu 10",
            narration="చరణ్ నామినేషన్ గొడవ",
            topic_category="entertainment",
        )
        self.assertTrue(len(queries) > 0)
        # First query should be the strict quoted format with negative exclusions
        self.assertTrue(any('"Bigg Boss Telugu 10" 2026' in q for q in queries))
        self.assertTrue(any("-Season 9" in q for q in queries))

    def test_visual_ladder_rewrite_beat_queries_strict(self):
        queries = rewrite_beat_queries(
            raw_query="Charan intense confrontation scene",
            narration="Bigg Boss Telugu 10 housemates arguing",
            topic_category="entertainment",
        )
        self.assertTrue(len(queries) > 0)
        self.assertTrue(any('"Bigg Boss Telugu 10" 2026' in q for q in queries))

    def test_analyze_scene_with_llm_metadata(self):
        # Test scene analysis fallback produces structured metadata
        meta = analyze_scene_with_llm(
            scene_text="చరణ్ నామినేషన్స్ గొడవలో బిగ్ బాస్ హౌస్ దద్దరిల్లింది",
            overall_context="Bigg Boss Telugu 10",
        )
        self.assertIn("Charan", meta.get("person_name", ""))
        self.assertEqual(meta.get("season_name"), "Bigg Boss Telugu 10")
        self.assertEqual(meta.get("year"), 2026)
        self.assertIn('"Bigg Boss Telugu 10" 2026', meta.get("strict_query", ""))

    def test_non_bigg_boss_backward_compatibility(self):
        # A tech topic should NOT have Bigg Boss or season restrictions injected
        tech_queries = build_queries(
            visual_description="India Mobile Congress 6G telecom tower showcase",
            narration="భారతదేశంలో 6G నెట్‌వర్క్ ట్రయల్స్ ప్రారంభం అయ్యాయి",
            topic_category="tech",
        )
        for q in tech_queries:
            self.assertNotIn("Bigg Boss", q)
            self.assertNotIn("-Season 9", q)


if __name__ == "__main__":
    unittest.main()

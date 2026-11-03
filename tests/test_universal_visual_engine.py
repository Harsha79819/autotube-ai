import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from agents.script_agent import build_structured_visual_plan
from agents.visual_agent import build_universal_search_query, source_dual_tier_visual, build_scene_flux_prompt
from agents.visual_ladder import is_irrelevant_stock_asset

class TestUniversalVisualEngine(unittest.TestCase):

    def test_dynamic_category_and_entity_extraction_cinema(self):
        """Verifies structured metadata extraction for Cinema (e.g. Dil Raju)."""
        topic = "Dil Raju Shocking Press Meet on Tollywood Cinema Collections"
        sections = [
            {"narration": "దిల్ రాజు ప్రెస్ మీట్ లో షాకింగ్ కామెంట్స్ చేశారు."},
            {"narration": "ఈ సినిమా కలెక్షన్స్ పై ఆయన చాలా కోపంగా మాట్లాడారు."},
            {"narration": "టాలీవుడ్ భవిష్యత్తు కోసం పెద్ద ప్లాన్ సిద్ధం చేస్తున్నారు."},
            {"narration": "లైక్ చేయండి మరియు సబ్స్క్రైబ్ చేసుకోండి."}
        ]
        visual_plan = ["Dil Raju speech", "Angry discussion", "Tollywood future", "Outro subscribe"]

        plan = build_structured_visual_plan(sections, visual_plan, topic=topic)
        self.assertEqual(len(plan), 4)

        for beat in plan:
            # Check all 4 mandatory keys exist in every beat
            self.assertIn("content_type", beat)
            self.assertIn("primary_entity", beat)
            self.assertIn("emotion_or_action", beat)
            self.assertIn("visual_fallback_prompt", beat)
            self.assertEqual(beat["content_type"], "cinema")
            self.assertEqual(beat["primary_entity"], "Dil Raju")

        # First beat had "shocking" -> emotion_or_action should be shocked
        self.assertEqual(plan[0]["emotion_or_action"], "shocked")
        self.assertIn("Dil Raju", plan[0]["visual_fallback_prompt"])
        self.assertIn("shocked", plan[0]["visual_fallback_prompt"])

        # Second beat had "angry" -> emotion_or_action should be angry
        self.assertEqual(plan[1]["emotion_or_action"], "angry")

    def test_dynamic_category_and_entity_extraction_business(self):
        """Verifies structured metadata extraction for Business (e.g. Foxconn / Haier)."""
        topic = "Foxconn Signs Signature Factory Deal in Telangana"
        sections = [
            {"narration": "ఫాక్స్‌కాన్ భారీ ఎలక్ట్రానిక్స్ తయారీ ప్లాంట్ ఏర్పాటు చేస్తోంది."},
            {"narration": "తెలంగాణ ప్రభుత్వంతో చారిత్రాత్మక ఒప్పందం సంతకం చేశారు."},
            {"narration": "వేల మంది యువతకు ఉపాధి అవకాశాలు లభించనున్నాయి."},
            {"narration": "మరిన్ని అప్‌డేట్స్ కోసం ఫాలో అవ్వండి."}
        ]
        visual_plan = ["Foxconn factory", "Signature deal", "Employment", "Outro"]

        plan = build_structured_visual_plan(sections, visual_plan, topic=topic)
        self.assertEqual(len(plan), 4)

        self.assertEqual(plan[0]["content_type"], "business")
        self.assertEqual(plan[0]["primary_entity"], "Foxconn")
        self.assertEqual(plan[0]["emotion_or_action"], "modern factory floor")

        self.assertEqual(plan[1]["content_type"], "business")
        self.assertEqual(plan[1]["primary_entity"], "Foxconn")
        self.assertEqual(plan[1]["emotion_or_action"], "signature deal")

    def test_dynamic_category_and_entity_extraction_tech(self):
        """Verifies structured metadata extraction for Tech (e.g. Tesla)."""
        topic = "Tesla Unveils Autonomous Robotaxi and AI Supercomputer"
        sections = [
            {"narration": "టెస్లా సరికొత్త ఆర్టిఫిషియల్ ఇంటెలిజెన్స్ చిప్ లాంచ్ చేసింది."},
            {"narration": "ఈ టెక్నాలజీతో కార్ల ధరలు భారీగా తగ్గే అవకాశం ఉంది."},
            {"narration": "భారత్ లో కూడా టెస్లా తయారీ ప్లాంట్ రాబోతోంది."},
            {"narration": "మీ అభిప్రాయాన్ని కామెంట్ చేయండి."}
        ]
        visual_plan = ["Tesla AI launch", "Electric cars", "Tesla factory", "Outro"]

        plan = build_structured_visual_plan(sections, visual_plan, topic=topic)
        self.assertEqual(plan[0]["content_type"], "tech")
        self.assertEqual(plan[0]["primary_entity"], "Tesla")

    def test_dynamic_category_and_entity_extraction_politics(self):
        """Verifies structured metadata extraction for Politics (e.g. Revanth Reddy)."""
        topic = "CM Revanth Reddy Fiery Speech in Telangana Assembly"
        sections = [
            {"narration": "రేవంత్ రెడ్డి అసెంబ్లీలో ప్రతిపక్షాలపై తీవ్రంగా విరుచుకుపడ్డారు."},
            {"narration": "రైతుల రుణమాఫీపై కీలక ప్రకటన చేశారు."},
            {"narration": "కాంగ్రెస్ ప్రభుత్వం ఇచ్చిన హామీలను నెరవేరుస్తుందని స్పష్టం చేశారు."},
            {"narration": "సబ్‌స్క్రైబ్ చేయడం మర్చిపోకండి."}
        ]
        visual_plan = ["Revanth Reddy speech", "Farmers loan waiver", "Assembly debate", "Outro"]

        plan = build_structured_visual_plan(sections, visual_plan, topic=topic)
        self.assertEqual(plan[0]["content_type"], "politics")
        self.assertEqual(plan[0]["primary_entity"], "Revanth Reddy")

    def test_dynamic_category_and_entity_extraction_reality_tv(self):
        """Verifies structured metadata extraction for Reality TV (Bigg Boss)."""
        topic = "Bigg Boss 10 Telugu Monday Nominations Fire"
        sections = [
            {"narration": "బిగ్ బాస్ హౌస్ లో సోమవారం నామినేషన్స్ మంటలు చెలరేగాయి."},
            {"narration": "త్రిగుణ్ మరియు శాలిని మధ్య తీవ్ర వాగ్వాదం జరిగింది."},
            {"narration": "నాగార్జున వీకెండ్ ఎపిసోడ్ లో క్లాస్ పీకనున్నారు."},
            {"narration": "ఎవరు ఎలిమినేట్ అవుతారో కామెంట్ చేయండి."}
        ]
        visual_plan = ["Nominations fire", "Thrigun fight", "Host Nagarjuna", "Outro"]

        plan = build_structured_visual_plan(sections, visual_plan, topic=topic)
        self.assertEqual(plan[0]["content_type"], "reality_tv")
        self.assertEqual(plan[1]["primary_entity"], "Thrigun")

    def test_build_universal_search_query_context_isolation(self):
        """Validates format of search queries and strict show context isolation."""
        # 1. Person/Celebrity: "{primary_entity}" {emotion_or_action} face photo OR interview
        q_person = build_universal_search_query(
            primary_entity="Dil Raju",
            emotion_or_action="shocked",
            content_type="cinema",
            show_context="bigboss 10 telugu",  # Stale context must be IGNORED
        )
        self.assertEqual(q_person, '"Dil Raju" shocked face photo OR interview')
        self.assertNotIn("bigboss", q_person.lower())

        # 2. Company/Business: "{primary_entity}" {emotion_or_action} modern high quality
        q_company = build_universal_search_query(
            primary_entity="Foxconn",
            emotion_or_action="modern factory floor",
            content_type="business",
            show_context="bigboss 10 telugu",
        )
        self.assertEqual(q_company, '"Foxconn" modern factory floor modern high quality')
        self.assertNotIn("bigboss", q_company.lower())

        # 3. Reality TV with genuine show context: includes show context
        q_reality = build_universal_search_query(
            primary_entity="Thrigun",
            emotion_or_action="angry",
            content_type="reality_tv",
            show_context="Bigg Boss Telugu 10",
        )
        self.assertIn("Bigg Boss Telugu 10", q_reality)
        self.assertIn("Thrigun", q_reality)

    def test_vintage_stock_and_roulette_blacklist(self):
        """Validates that vintage projectors, roulette wheels, and lab beakers are strictly rejected."""
        # Vintage film projector -> rejected
        self.assertTrue(is_irrelevant_stock_asset(
            cand_title="Vintage antique film projector running 35mm film reel",
            cand_url="https://example.com/projector.jpg",
            query_text="Dil Raju press meet",
            target_entity="Dil Raju"
        ))

        # Roulette wheel / casino -> rejected
        self.assertTrue(is_irrelevant_stock_asset(
            cand_title="Spinning roulette wheel on casino table with chips",
            cand_url="https://example.com/roulette.jpg",
            query_text="Foxconn business investment",
            target_entity="Foxconn"
        ))

        # Laboratory beakers / glassware -> rejected
        self.assertTrue(is_irrelevant_stock_asset(
            cand_title="Laboratory chemistry glassware apparatus and beakers",
            cand_url="https://example.com/beaker.jpg",
            query_text="Tesla AI release",
            target_entity="Tesla"
        ))

        # Legitimate entity photo -> accepted
        self.assertFalse(is_irrelevant_stock_asset(
            cand_title="Dil Raju speaking at movie launch event",
            cand_url="https://example.com/dil_raju_press.jpg",
            query_text="Dil Raju press meet",
            target_entity="Dil Raju"
        ))

    @patch("agents.visual_agent.generate_ai_visual")
    @patch("agents.visual_agent.source_beat_visual")
    def test_instant_flux_fallback_with_fallback_prompt(self, mock_source_beat, mock_generate_ai):
        """Verifies instant FLUX AI fallback uses visual_fallback_prompt."""
        mock_source_beat.return_value = {"success": False, "asset_path": ""}

        captured_prompt = []
        def fake_generate_ai(prompt, dest_path, aspect_ratio="9:16"):
            captured_prompt.append(prompt)
            Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
            Path(dest_path).write_bytes(b"dummy_image_data_at_least_1000_bytes_" * 50)
            return True

        mock_generate_ai.side_effect = fake_generate_ai

        # Mock visual_plan.json
        mock_plan = [{
            "beat_id": 1,
            "content_type": "cinema",
            "primary_entity": "Dil Raju",
            "emotion_or_action": "shocked",
            "visual_fallback_prompt": "Dil Raju in shocked reaction, dramatic cinema stage lighting"
        }]
        
        test_out_json = Path("output/visual_plan.json")
        test_out_json.parent.mkdir(parents=True, exist_ok=True)
        import json
        test_out_json.write_text(json.dumps(mock_plan), encoding="utf-8")

        dest_test_jpg = Path("/tmp/test_universal_beat_1.jpg")
        if dest_test_jpg.exists():
            dest_test_jpg.unlink()

        res = source_dual_tier_visual(
            beat_number=1,
            raw_query="Dil Raju shocking speech",
            narration="దిల్ రాజు షాకింగ్ కామెంట్స్",
            destination_jpg=dest_test_jpg,
            aspect_ratio="9:16",
            topic_category="cinema",
        )

        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("tier"), "TIER_A")
        self.assertEqual(res.get("source"), "pollinations_flux_fallback")
        self.assertTrue(len(captured_prompt) > 0)
        self.assertIn("Cinematic Dil Raju in shocked reaction", captured_prompt[0])
        self.assertIn("9:16 vertical ratio", captured_prompt[0])

        if dest_test_jpg.exists():
            dest_test_jpg.unlink()

if __name__ == "__main__":
    unittest.main()

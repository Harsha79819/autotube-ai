import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image

from agents.script_agent import build_structured_visual_plan, synthesize_beat_visual_plan
from agents.visual_agent import source_dual_tier_visual
from agents.visual_ladder import search_all_sources_parallel, source_beat_visual
from providers.image import clean_and_crop_image


class TestScriptLevelVisualPlanning(unittest.TestCase):

    def setUp(self):
        Path("output").mkdir(parents=True, exist_ok=True)

    def test_structured_visual_plan_json_schema(self):
        """Verifies every beat has beat_id, narration, main_entity, emotion, search_query."""
        topic = "Bigg Boss 10 Telugu Monday Fire: Shalini Damera and Temper Vamsi Fight"
        sections = [
            {"narration": "బిగ్ బాస్ హౌస్‌లో శాలిని డామెర ఒక్కసారిగా షాకింగ్ కామెంట్స్ చేశారు."},
            {"narration": "టెంపర్ వంశీ కోపంగా స్టేజ్ పై నామినేషన్ గొడవ మొదలుపెట్టారు."},
            {"narration": "దిల్ రాజు కూడా ఈ ఎపిసోడ్ పై సరదాగా మాట్లాడారు."},
        ]
        raw_vp = [
            "Shalini Patel reaction",
            "Temper Vamsi fight",
            "Dil Raju discussion",
        ]

        plan = build_structured_visual_plan(sections, raw_vp, topic=topic)
        self.assertEqual(len(plan), 3)

        # Check beat 1: Shalini Patel
        b1 = plan[0]
        self.assertEqual(b1["beat_id"], 1)
        self.assertIn("శాలిని", b1["narration"])
        self.assertEqual(b1["main_entity"], "Shalini Patel")
        self.assertEqual(b1["emotion"], "shocked")
        self.assertIn("Shalini Patel", b1["search_query"])
        # Must NOT be full narration sentence
        self.assertNotEqual(b1["search_query"], b1["narration"])
        self.assertLessEqual(len(b1["search_query"].split()), 6)

        # Check beat 2: Temper Vamsi
        b2 = plan[1]
        self.assertEqual(b2["beat_id"], 2)
        self.assertIn("టెంపర్ వంశీ", b2["narration"])
        self.assertEqual(b2["main_entity"], "Temper Vamsi")
        self.assertEqual(b2["emotion"], "angry")
        self.assertIn("Temper Vamsi", b2["search_query"])
        self.assertNotEqual(b2["search_query"], b2["narration"])
        self.assertLessEqual(len(b2["search_query"].split()), 6)

        # Check beat 3: Dil Raju
        b3 = plan[2]
        self.assertEqual(b3["beat_id"], 3)
        self.assertEqual(b3["main_entity"], "Dil Raju")
        self.assertIn("Dil Raju", b3["search_query"])
        self.assertNotEqual(b3["search_query"], b3["narration"])

        # Check output/visual_plan.json exists and is valid JSON
        vp_path = Path("output/visual_plan.json")
        self.assertTrue(vp_path.exists())
        saved_data = json.loads(vp_path.read_text(encoding="utf-8"))
        self.assertEqual(len(saved_data), 3)
        for beat in saved_data:
            self.assertIn("beat_id", beat)
            self.assertIn("narration", beat)
            self.assertIn("main_entity", beat)
            self.assertIn("emotion", beat)
            self.assertIn("search_query", beat)

    def test_synthesize_beat_visual_plan_deterministic_and_json(self):
        """Verifies synthesize_beat_visual_plan populates delivery_plan and exports beat_visual_plan.json."""
        topic = "Dil Raju Tollywood Cinema Roast"
        delivery_plan = [
            {"beat_id": 1, "spoken_text": "దిల్ రాజు ప్రెస్ మీట్ లో షాకింగ్ కామెంట్స్ చేశారు.", "emotion": "shocked"},
            {"beat_id": 2, "spoken_text": "ఈ సినిమా కలెక్షన్స్ పై ఆయన చాలా కోపంగా మాట్లాడారు.", "emotion": "angry"},
        ]

        with patch("providers.llm.generate_text_cascade", side_effect=RuntimeError("offline")):
            visual_lines = synthesize_beat_visual_plan(delivery_plan, topic=topic)
        self.assertEqual(len(visual_lines), 2)

        # Verify delivery_plan enriched
        self.assertEqual(delivery_plan[0]["main_entity"], "Dil Raju")
        self.assertEqual(delivery_plan[0]["emotion"], "shocked")
        self.assertIn("Dil Raju", delivery_plan[0]["search_query"])
        # Negative rule: search_query must never equal full narration sentence
        self.assertNotEqual(delivery_plan[0]["search_query"], delivery_plan[0]["spoken_text"])
        self.assertLessEqual(len(delivery_plan[0]["search_query"].split()), 6)

        # Verify beat_visual_plan.json
        bvp_file = Path("output/beat_visual_plan.json")
        self.assertTrue(bvp_file.exists())
        bvp_data = json.loads(bvp_file.read_text(encoding="utf-8"))
        self.assertEqual(len(bvp_data), 2)
        self.assertEqual(bvp_data[0]["main_entity"], "Dil Raju")
        self.assertNotEqual(bvp_data[0]["search_query"], bvp_data[0]["narration"])

    def test_synthesize_beat_visual_plan_llm_json_parsing(self):
        """Verifies that LLM structured JSON array is accurately parsed and populated."""
        topic = "Bigg Boss 10 Nominations"
        delivery_plan = [
            {"beat_id": 1, "spoken_text": "శాలిని డామెర నామినేషన్స్ లో అరిచారు.", "emotion": "angry"},
            {"beat_id": 2, "spoken_text": "టెంపర్ వంశీ కూడా సీరియస్ గా బదులిచ్చారు.", "emotion": "aggressive"},
        ]
        mock_llm_json = """
        [
          {
            "beat_id": 1,
            "narration": "శాలిని డామెర నామినేషన్స్ లో అరిచారు.",
            "main_entity": "Shalini Damera",
            "emotion": "angry",
            "search_query": "Shalini Damera bigg boss"
          },
          {
            "beat_id": 2,
            "narration": "టెంపర్ వంశీ కూడా సీరియస్ గా బదులిచ్చారు.",
            "main_entity": "Temper Vamsi",
            "emotion": "aggressive",
            "search_query": "Temper Vamsi actor"
          }
        ]
        """
        with patch("providers.llm.generate_text_cascade", return_value=mock_llm_json):
            visual_lines = synthesize_beat_visual_plan(delivery_plan, topic=topic)

        self.assertEqual(len(visual_lines), 2)
        self.assertEqual(delivery_plan[0]["main_entity"], "Shalini Damera")
        self.assertEqual(delivery_plan[0]["search_query"], "Shalini Damera bigg boss")
        self.assertEqual(delivery_plan[1]["main_entity"], "Temper Vamsi")
        self.assertEqual(delivery_plan[1]["search_query"], "Temper Vamsi actor")

    def test_search_query_negative_rule_sanitization(self):
        """Verifies that if LLM returns the entire narration sentence, the sanitizer cleans it."""
        topic = "Dil Raju Press Meet"
        delivery_plan = [
            {"beat_id": 1, "spoken_text": "దిల్ రాజు ప్రెస్ మీట్ లో షాకింగ్ కామెంట్స్ చేశారు.", "emotion": "shocked"}
        ]
        # LLM violated negative rule by echoing full narration
        violating_json = """
        [
          {
            "beat_id": 1,
            "narration": "దిల్ రాజు ప్రెస్ మీట్ లో షాకింగ్ కామెంట్స్ చేశారు.",
            "main_entity": "Dil Raju",
            "emotion": "shocked",
            "search_query": "దిల్ రాజు ప్రెస్ మీట్ లో షాకింగ్ కామెంట్స్ చేశారు."
          }
        ]
        """
        with patch("providers.llm.generate_text_cascade", return_value=violating_json):
            synthesize_beat_visual_plan(delivery_plan, topic=topic)

        # Sanitizer must have replaced full narration with clean 2-3 word keyword query
        self.assertNotEqual(delivery_plan[0]["search_query"], "దిల్ రాజు ప్రెస్ మీట్ లో షాకింగ్ కామెంట్స్ చేశారు.")
        self.assertIn("Dil Raju", delivery_plan[0]["search_query"])

    def test_pexels_stock_filtered_when_main_entity_present(self):
        """Verifies that generic stock videos (Pexels) are skipped when a main_entity is present."""
        queries = ['"Temper Vamsi" actor', 'Temper Vamsi interview']
        with patch("agents.visual_ladder.get_pexels_api_key", return_value="fake_pexels_key"), \
             patch("agents.visual_ladder.search_pexels_videos") as mock_pexels_v, \
             patch("agents.visual_ladder.search_pexels_photos") as mock_pexels_p:
            cands = search_all_sources_parallel(
                queries=queries,
                raw_query="Temper Vamsi angry scene",
                topic_category="entertainment",
            )
            # Pexels video & photos must NOT be called for an entity beat
            mock_pexels_v.assert_not_called()
            mock_pexels_p.assert_not_called()
            for c in cands:
                self.assertNotIn("pexels", c.get("source", ""))

    def test_flux_fallback_prompt_formatting(self):
        """Verifies that FLUX fallback prompt uses Cinematic {main_entity} in {emotion} expression."""
        # Setup visual_plan.json with structured beat
        vp_data = [
            {
                "beat_id": 1,
                "narration": "శాలిని డామెర తీవ్రంగా స్పందించారు.",
                "main_entity": "Shalini Damera",
                "emotion": "shocked",
                "search_query": "Shalini Damera bigg boss",
                "content_type": "reality_tv",
            }
        ]
        Path("output/visual_plan.json").write_text(json.dumps(vp_data), encoding="utf-8")

        captured_prompts = []
        def fake_generate_ai_visual(prompt, dest, aspect_ratio="9:16"):
            captured_prompts.append(prompt)
            # create small valid dummy image
            img = Image.new("RGB", (1080, 1920), color=(10, 20, 30))
            img.save(dest)
            return True

        with patch("agents.visual_agent.source_beat_visual", return_value={"success": False}), \
             patch("agents.visual_agent.generate_ai_visual", side_effect=fake_generate_ai_visual):
            res = source_dual_tier_visual(
                beat_number=1,
                raw_query="Shalini Damera bigg boss",
                narration="శాలిని డామెర తీవ్రంగా స్పందించారు.",
                destination_jpg=Path("output/test_fallback.jpg"),
                topic_category="reality_tv",
            )
            self.assertTrue(res.get("success"))
            self.assertTrue(len(captured_prompts) > 0)
            flux_prompt = captured_prompts[0]
            self.assertIn("Cinematic Shalini Damera in shocked expression", flux_prompt)
            self.assertIn("9:16 vertical ratio", flux_prompt)
            self.assertIn("photorealistic", flux_prompt)

    def test_clean_and_crop_image(self):
        """Verifies clean_and_crop_image trims borders and formats to 9:16."""
        test_img_path = Path("output/test_crop.jpg")
        # Create a 16:9 landscape image with black letterboxing
        im = Image.new("RGB", (1920, 1080), color=(200, 50, 50))
        im.save(test_img_path)

        res_path = clean_and_crop_image(test_img_path, aspect_ratio="9:16")
        self.assertTrue(res_path.exists())
        with Image.open(res_path) as cropped_im:
            self.assertEqual(cropped_im.size, (1080, 1920))


if __name__ == "__main__":
    unittest.main()

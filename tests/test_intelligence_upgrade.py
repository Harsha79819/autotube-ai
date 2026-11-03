"""
Unit Test Suite for AutoTube AI Non-Breaking Intelligence Upgrade.
Tests:
  1. Content Intelligence Agent
  2. Hook and Retention Optimizer
  3. Packaging Intelligence Agent
  4. Fact-Checking & Originality Reviewer
  5. YouTube Performance Feedback Module
  6. Experiment and Learning Logger
  7. Configuration Defaults & Non-Breaking Safety
"""

import unittest
import os
import sys
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

class TestContentIntelligenceAgent(unittest.TestCase):
    def setUp(self):
        from agents.content_intelligence_agent import (
            detect_content_pillar,
            check_topic_novelty,
            evaluate_topic_intelligence,
            get_vetted_pillar_topics,
        )
        self.detect_pillar = detect_content_pillar
        self.check_novelty = check_topic_novelty
        self.evaluate_topic = evaluate_topic_intelligence
        self.get_vetted = get_vetted_pillar_topics

    def test_pillar_detection(self):
        # 1. Tollywood Celebrity
        p1 = self.detect_pillar("Prabhas Kalki 2 Box Office Collection Record")
        self.assertEqual(p1, "tollywood_celebrity")

        # 2. Behind The Scenes
        p2 = self.detect_pillar("Bigg Boss Telugu 10 Secret Room Unseen Footage")
        self.assertEqual(p2, "behind_the_scenes")

        # 3. Viral Entertainment Explainers
        p3 = self.detect_pillar("Why Certain Big-Budget Pan-India Films Flop: Script Breakdown")
        self.assertEqual(p3, "viral_entertainment_explainers")

    def test_novelty_and_evaluation(self):
        # Test topic evaluation
        res = self.evaluate_topic("SS Rajamouli Globe-Trotting Adventure Movie Update")
        self.assertIn("overall_score", res)
        self.assertIn("pillar", res)
        self.assertIn("freshness_score", res)
        self.assertIn("novelty_score", res)
        self.assertIn("rationale", res)
        self.assertGreaterEqual(res["overall_score"], 0)
        self.assertLessEqual(res["overall_score"], 100)

    def test_vetted_topics_pool(self):
        vetted = self.get_vetted("tollywood_celebrity")
        self.assertGreater(len(vetted), 0)
        self.assertTrue(any("Prabhas" in v["topic"] or "Devara" in v["topic"] or "Rajamouli" in v["topic"] for v in vetted))


class TestHookRetentionOptimizer(unittest.TestCase):
    def setUp(self):
        from agents.hook_retention_optimizer import (
            clean_opening_fluff,
            calculate_heuristic_retention_score,
            optimize_script_for_retention,
            compare_scripts,
        )
        self.clean_fluff = clean_opening_fluff
        self.calc_score = calculate_heuristic_retention_score
        self.optimize = optimize_script_for_retention
        self.compare = compare_scripts

    def test_clean_opening_fluff(self):
        dirty = "హలో ఫ్రెండ్స్ వెల్కమ్ టు అవర్ ఛానల్. ఈ రోజు బిగ్ బాస్ హౌస్‌లో పెద్ద గొడవ జరిగింది."
        cleaned = self.clean_fluff(dirty)
        self.assertNotIn("హలో ఫ్రెండ్స్", cleaned)
        self.assertNotIn("వెల్కమ్ టు అవర్ ఛానల్", cleaned)
        self.assertIn("బిగ్ బాస్ హౌస్‌లో", cleaned)

        english_dirty = "Hello guys welcome to our channel! In this video we will talk about Kalki 2."
        eng_cleaned = self.clean_fluff(english_dirty)
        self.assertNotIn("Hello guys", eng_cleaned)
        self.assertNotIn("welcome to our channel", eng_cleaned)

    def test_heuristic_retention_scoring(self):
        sample = "ఈ రోజు బిగ్ బాస్ హౌస్‌లో హై-ఓల్టేజ్ డ్రామా. నామినేషన్లలో త్రిగుణ్ సాక్షిని టార్గెట్ చేశాడు. అసలు ఏం జరిగింది?"
        score_res = self.calc_score(sample, is_short=True)
        self.assertIn("retention_score", score_res)
        self.assertIn("limitations", score_res)
        self.assertIn("Heuristic estimate", score_res["limitations"])
        self.assertGreater(score_res["retention_score"], 0)

    def test_optimization_creates_separate_candidate(self):
        sample = "నమస్కారం అందరికీ. ఈ రోజు మనం ఒక ముఖ్యమైన విషయం గురించి మాట్లాడుకుందాం. బిగ్ బాస్ నామినేషన్లలో షాకింగ్ ట్విస్ట్ వచ్చింది."
        opt_res = self.optimize(sample, topic="Bigg Boss Telugu 10 Nominations", aspect_ratio="9:16")
        self.assertIn("optimized_script", opt_res)
        self.assertIn("candidate_file", opt_res)
        self.assertTrue(Path(opt_res["candidate_file"]).exists())
        self.assertNotIn("నమస్కారం అందరికీ", opt_res["optimized_script"])

        # Check compare function
        comp = self.compare(opt_res["original_script"], opt_res["optimized_script"])
        self.assertIn("original_word_count", comp)
        self.assertIn("optimized_word_count", comp)


class TestPackagingIntelligence(unittest.TestCase):
    def setUp(self):
        from agents.packaging_intelligence import (
            generate_title_candidates,
            generate_mobile_thumbnail_text_options,
            verify_packaging_alignment,
        )
        self.gen_titles = generate_title_candidates
        self.gen_thumbs = generate_mobile_thumbnail_text_options
        self.verify_pack = verify_packaging_alignment

    def test_title_candidates_generation(self):
        candidates = self.gen_titles("Devara 2 Box Office Records")
        self.assertEqual(len(candidates), 3)
        variants = [c["variant_id"] for c in candidates]
        self.assertIn("curiosity_gap", variants)
        self.assertIn("high_energy", variants)
        self.assertIn("search_clarity", variants)

    def test_mobile_thumbnail_text(self):
        options = self.gen_thumbs("Devara Climax")
        self.assertGreater(len(options), 0)
        for opt in options:
            self.assertLessEqual(opt["words_count"], 4)
            self.assertTrue(opt["is_mobile_compliant"])

    def test_anti_clickbait_and_alignment(self):
        # Unsupported 'EXPOSED'
        res = self.verify_pack(
            title="Tollywood Star EXPOSED in Scam",
            thumbnail_text="SECRET EXPOSED",
            narration_script="ఈ రోజు జరిగిన ప్రెస్ మీట్‌లో కొత్త ప్రాజెక్ట్ వివరాలు వెల్లడించారు.",
        )
        self.assertFalse(res["is_compliant"])
        self.assertTrue(any("exposed" in str(iss).lower() for iss in res["issues"]))
        self.assertIn("disclaimer", res)


class TestFactOriginalityReviewer(unittest.TestCase):
    def setUp(self):
        from agents.fact_originality_reviewer import review_fact_and_originality
        self.review_fact = review_fact_and_originality

    def test_advisory_review(self):
        script = (
            "ఈ సినిమా మొదటి రోజు 100 కోట్ల గ్రాస్ వసూలు చేసింది. "
            "ఇందులో అపూర్వ మోసం చేసింది అని ప్రచారం జరుగుతోంది. "
            "అసలు దీని వెనుక ఉన్న కారణం విశ్లేషిస్తే సినిమా మేకింగ్ చాలా బాగుంది."
        )
        res = self.review_fact(script, topic="Cinema Review", strict_enforcement=False)
        self.assertIn("status", res)
        self.assertIn("findings", res)
        self.assertTrue(res["passed"])  # Advisory mode passes without blocking
        self.assertTrue(res["is_advisory"])

    def test_strict_enforcement_mode(self):
        # Script with ungrounded controversial claims in strict mode
        script = "అతను పెద్ద క్రైమ్ చేశాడు. మోసం చేశాడు."
        res = self.review_fact(script, topic="Controversy", strict_enforcement=True)
        self.assertFalse(res["passed"])
        self.assertEqual(res["status"], "CHANGES_REQUESTED")


class TestYouTubeFeedback(unittest.TestCase):
    def setUp(self):
        from analytics.youtube_feedback import (
            diagnose_channel_performance,
            USER_CHANNEL_28D_ANALYTICS,
        )
        self.diagnose = diagnose_channel_performance
        self.sample_data = USER_CHANNEL_28D_ANALYTICS

    def test_diagnosis_on_user_channel_metrics(self):
        res = self.diagnose(self.sample_data)
        self.assertEqual(res["status"], "ANALYSIS_COMPLETE")
        self.assertEqual(res["channel_name"], "viral_talks_me&mine")
        
        # Verify CTR drop diagnosis (1.91% from 4.81%)
        recs = res["recommendations"]
        has_packaging_rec = any("Packaging" in r["area"] for r in recs)
        self.assertTrue(has_packaging_rec, "Failed to flag CTR packaging recommendation")

        # Verify AVD drop diagnosis (19s from 27s)
        has_hook_rec = any("Hook" in r["area"] for r in recs)
        self.assertTrue(has_hook_rec, "Failed to flag AVD retention hook recommendation")

        # Verify next experiment
        self.assertIn("next_experiment", res)
        self.assertIn("disclaimer", res)

    def test_unavailable_state_without_fabrication(self):
        res = self.diagnose(analytics_data=None, use_sample_fallback=False)
        self.assertEqual(res["status"], "UNAVAILABLE")
        self.assertIn("were not fabricated", res["disclaimer"])


class TestExperimentLogger(unittest.TestCase):
    def setUp(self):
        from analytics.experiment_logger import (
            log_experiment_run,
            load_experiment_log,
            update_experiment_metrics,
            compare_experiments_by_pillar,
        )
        self.log_run = log_experiment_run
        self.load_log = load_experiment_log
        self.update_metrics = update_experiment_metrics
        self.compare_pillar = compare_experiments_by_pillar

    def test_logging_and_retrieval(self):
        entry = self.log_run(
            topic="Test Topic Intelligence Run",
            content_pillar="tollywood_celebrity",
            aspect_ratio="9:16",
            target_duration="30-50s",
            actual_duration_sec=42.5,
            hook_variant="immediate_hook",
            title_variant="Test Title Curiosity",
            thumbnail_text="TEST SHOCK",
            heuristic_scores={"retention_score": 88.0, "packaging_score": 90.0},
        )
        self.assertIsNotNone(entry.get("experiment_id"))
        self.assertEqual(entry["format"], "Shorts")

        # Test updating metrics
        up = self.update_metrics(entry["experiment_id"], {"views": 1500, "impressions_ctr_percent": 3.8})
        self.assertTrue(up)

        # Test comparing by pillar
        matches = self.compare_pillar("tollywood_celebrity")
        self.assertGreater(len(matches), 0)


class TestConfigSettingsDefaults(unittest.TestCase):
    def test_all_upgrade_flags_disabled_by_default(self):
        from config.settings import DEFAULT_SETTINGS
        self.assertFalse(DEFAULT_SETTINGS["ENABLE_CONTENT_INTELLIGENCE"])
        self.assertFalse(DEFAULT_SETTINGS["ENABLE_HOOK_OPTIMIZER"])
        self.assertFalse(DEFAULT_SETTINGS["ENABLE_PACKAGING_INTELLIGENCE"])
        self.assertFalse(DEFAULT_SETTINGS["ENABLE_FACT_CHECK_REVIEW"])
        self.assertFalse(DEFAULT_SETTINGS["ENABLE_EXPERIMENT_LOGGING"])
        self.assertFalse(DEFAULT_SETTINGS["STRICT_FACT_CHECK_ENFORCEMENT"])
        self.assertIn("tollywood_celebrity", DEFAULT_SETTINGS["CONTENT_PILLARS"])


if __name__ == "__main__":
    unittest.main()

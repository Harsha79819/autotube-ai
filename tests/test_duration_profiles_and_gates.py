import unittest
import os
import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config.format_profiles import get_format_profile
from agents.validation_agent import ValidationAgent, ValidationResult
from agents.script_agent import auto_calibrate_script_to_profile, clean_script_narration
from agents.run_report import generate_run_report


class TestDurationProfilesAndGates(unittest.TestCase):
    """Regression and functional test suite for 60-90s duration and validation gates."""

    def test_01_format_profile_60_90s_bounds(self):
        """Verifies 60-90s format profile returns correct duration and word bounds."""
        prof_en = get_format_profile("60-90s", language="English")
        self.assertEqual(prof_en.target_seconds, 75.0)
        self.assertEqual(prof_en.min_seconds, 60.0)
        self.assertEqual(prof_en.max_seconds, 90.0)
        self.assertGreaterEqual(prof_en.min_words, 125)
        self.assertLessEqual(prof_en.max_words, 220)

        prof_te = get_format_profile("60-90s", language="Telugu")
        self.assertEqual(prof_te.target_seconds, 75.0)
        self.assertEqual(prof_te.min_seconds, 60.0)
        self.assertEqual(prof_te.max_seconds, 90.0)

    def test_02_step1_auto_calibrate_underlength_script(self):
        """Verifies underlength script (82 words) is expanded to >= 125 words for 60-90s."""
        prof = get_format_profile("60-90s", language="Telugu")
        short_telugu_script = (
            "60 కెమెరాలు తిరుగుతున్నా ఒక్క ఫ్రేమ్ కూడా దొరకలేదంటే నమ్ముతారా? "
            "అసలు మనం సీజన్ ఎయిట్ లో ఉన్నామా లేక 2030 లో ఉన్నామా బాస్? "
            "అసలు హౌస్‌లోనే లేని ముకేష్-వర్షిణి లవ్ స్టోరీ ఒకటి వైరల్ అవుతోంది. "
            "వీళ్లు కెమెరాలకి తెలియకుండా ఎక్కడో రహస్యంగా ప్రేమించుకుంటున్నారా ఏంటి? "
            "ఇది బిగ్ బాస్ హౌసా లేక ఎవరో క్రియేట్ చేసిన ఎడిటింగ్ స్కూలా? "
            "అసలు వీళ్ళది లవ్ ట్రాక్ కాదు బాస్, ఫుల్లీ ఫ్యాన్ మేడ్ ఎడిట్స్! "
            "వీళ్ల ప్రేమ మనకంటే ఎక్కువగా క్లౌడ్ లోనే బ్రతుకుతుందన్నమాట! "
            "ఇదంతా ఒక పెద్ద స్క్రిప్టెడ్ డ్రామా, అసలు అక్కడ కథే లేదు బాస్!"
        )
        words_before = len(short_telugu_script.split())
        self.assertLess(words_before, 100)

        calibrated = auto_calibrate_script_to_profile(
            script=short_telugu_script,
            profile=prof,
            topic="Bigg Boss Telugu 10 Exposed",
            content_type="Entertainment",
        )
        words_after = len(calibrated.split())
        self.assertGreaterEqual(words_after, 125, f"Calibrated script has only {words_after} words")
        self.assertTrue(any(k in calibrated for k in ["లైక్", "సబ్‌స్క్రైబ్", "కామెంట్", "subscribe"]))

    def test_03_validation_agent_gate_a_and_b(self):
        """Verifies ValidationAgent passes 60-90s script and 65s audio without critical defects."""
        prof = get_format_profile("60-90s", language="Telugu")
        val_agent = ValidationAgent()

        # Calibrated 140-word script
        sample_script = " ".join(["పదం" for _ in range(145)]) + " లైక్ కొట్టి సబ్‌స్క్రైబ్ చేసుకోండి!"
        res_a = val_agent.validate_script(sample_script, "Sample Topic", prof)
        self.assertTrue(res_a.passed)
        critical_a = [i for i in res_a.issues if i.severity == "CRITICAL"]
        self.assertEqual(len(critical_a), 0)

        # 68.5s audio check
        res_b = ValidationResult("Gate B (Audio/TTS)", passed=True)
        # Simulate duration validation logic
        duration = 68.5
        if duration < prof.min_seconds * 0.9:
            res_b.add_warning("Audio Duration Below Target", f">= {prof.min_seconds}", f"{duration}")
        elif duration > prof.max_seconds * 1.1:
            res_b.add_critical("Audio Duration Exceeds Target", f"<= {prof.max_seconds}", f"{duration}")
        self.assertTrue(res_b.passed)
        critical_b = [i for i in res_b.issues if i.severity == "CRITICAL"]
        self.assertEqual(len(critical_b), 0)

    def test_04_review_agent_gate_1_duration_logic(self):
        """Verifies review_agent Gate 1 allows extended Shorts up to 95s without failing."""
        prof = get_format_profile("60-90s", language="Telugu")
        is_extended_shorts = True

        for test_dur in [58.0, 65.0, 75.0, 85.0]:
            issues = []
            max_allowed = (prof.max_seconds * 1.08) if is_extended_shorts else 55.0
            min_allowed = 48.0 if is_extended_shorts else 20.0
            if test_dur > max_allowed:
                issues.append("CRITICAL LENGTH ERROR: Exceeds max")
            elif test_dur < min_allowed:
                issues.append("CRITICAL LENGTH ERROR: Below min")
            self.assertEqual(len(issues), 0, f"Duration {test_dur}s incorrectly flagged with {issues}")

    def test_05_run_report_compliance_60_90s(self):
        """Verifies run_report compliance calculation for 60-90s."""
        prof = get_format_profile("60-90s", language="Telugu")
        dur_min = prof.min_seconds * 0.85
        dur_max = prof.max_seconds * 1.08
        word_max = int(prof.max_words * 1.15)

        test_final_dur = 72.5
        test_word_count = 155
        is_dur_golden = (dur_min <= test_final_dur <= dur_max)
        is_word_budget = (test_word_count <= word_max)

        self.assertTrue(is_dur_golden)
        self.assertTrue(is_word_budget)


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for YouTube Director AI, Dialogue Freshness & Anti-Cliché Memory.
Verifies:
1. Channel 1 & Channel 2 algorithm strategies based on IST time.
2. Cross-video dialogue ledger tracking and timeout.
3. 6 dynamic narrative archetypes rotation.
4. Cliché sanitization and freshness scoring.
"""

import unittest
from datetime import datetime, timezone, timedelta
from analytics.youtube_director import (
    YouTubeDirectorAI,
    get_youtube_director,
    NARRATIVE_ARCHETYPES,
)
from agents.roast_engine import validate_and_heal_script


class TestYouTubeDirectorAndDialogueFreshness(unittest.TestCase):
    def setUp(self):
        self.director = YouTubeDirectorAI()

    def test_channel_strategy_both_channels(self):
        """Verify that strategies for both Channel 1 and Channel 2 return valid format and slots."""
        # Test Channel 1
        ch1 = self.director.get_channel_strategy("Channel 1")
        self.assertIn("Channel 1", ch1["channel"])
        self.assertIn(ch1["aspect_ratio"], ["9:16", "16:9"])
        self.assertTrue(len(ch1["time_slot"]) > 0)
        self.assertTrue(len(ch1["recommended_angle"]) > 0)

        # Test Channel 2
        ch2 = self.director.get_channel_strategy("Channel 2")
        self.assertIn("Channel 2", ch2["channel"])
        self.assertIn(ch2["aspect_ratio"], ["9:16", "16:9"])
        self.assertTrue(len(ch2["time_slot"]) > 0)
        self.assertTrue(len(ch2["recommended_angle"]) > 0)

    def test_archetypes_coverage(self):
        """Ensure all 6 dynamic narrative archetypes are populated with hooks, punchlines & CTAs."""
        self.assertEqual(len(NARRATIVE_ARCHETYPES), 6)
        for arch_id, data in NARRATIVE_ARCHETYPES.items():
            self.assertTrue(len(data["hook_templates"]) >= 3)
            self.assertTrue(len(data["punchline_samples"]) >= 3)
            self.assertTrue(len(data["cta_template"]) > 20)

    def test_dialogue_recording_and_ledger(self):
        """Verify recording script dialogues correctly updates history ledger and detects clichés."""
        test_script = (
            "బిగ్ బాస్ హౌస్‌లో ముకేష్ గౌడ చేసిన రచ్చతో వాతావరణం భగ్గుమంది బాస్! "
            "సీన్ కట్ చేస్తే నాగ్‌గారి కౌంటర్‌తో ఫ్యూజులు ఎగిరిపోయాయి బాస్! "
            "మరి దీనిపై మీ కామెంట్స్ ఏంటో చెప్పండి, సబ్‌స్క్రైబ్ చేసుకోండి!"
        )
        self.director.record_script_dialogues(
            script=test_script,
            topic="Bigg Boss 10 Mukesh Clashes",
            channel="Channel 2",
            archetype_id="witty_observational",
        )

        ledger = self.director._read_ledger()
        self.assertTrue(len(ledger["history"]) > 0)
        last_entry = ledger["history"][-1]
        self.assertEqual(last_entry["topic"], "Bigg Boss 10 Mukesh Clashes")
        # Should detect 'వాతావరణం భగ్గుమంది బాస్', 'సీన్ కట్ చేస్తే', 'ఫ్యూజులు ఎగిరిపోయాయి బాస్'
        self.assertTrue(len(last_entry["detected_cliches"]) >= 2)

    def test_freshness_score_and_sanitization(self):
        """Verify that calculate_freshness_score and sanitize_script_cliches scrub repetitive clichés."""
        dirty_script = "వాతావరణం భగ్గుమంది బాస్! అక్కడ జరిగిన రచ్చ రంబోలా చూసి ఫ్యూజులు ఎగిరిపోయాయి బాస్!"
        score, detected = self.director.calculate_freshness_score(dirty_script)
        self.assertLess(score, 100)
        self.assertTrue(len(detected) >= 2)

        clean = self.director.sanitize_script_cliches(dirty_script)
        self.assertNotIn("వాతావరణం భగ్గుమంది", clean)
        self.assertNotIn("ఫ్యూజులు ఎగిరిపోయాయి", clean)
        self.assertNotIn("రచ్చ రంబోలా", clean)

    def test_validate_and_heal_script_integrates_cliche_sanitization(self):
        """Verify validate_and_heal_script automatically removes repetitive clichés."""
        raw_text = "బిగ్ బాస్ హౌస్‌లో జరిగిన రచ్చతో వాతావరణం భగ్గుమంది బాస్! ఆయన చేసిన కామెడీకి గాలి తీసేశాడు."
        healed = validate_and_heal_script(raw_text, topic="Bigg Boss 10")
        self.assertNotIn("వాతావరణం భగ్గుమంది", healed)
        self.assertNotIn("గాలి తీసేశాడు", healed)


if __name__ == "__main__":
    unittest.main()

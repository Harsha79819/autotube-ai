"""
Unit tests for script deduplication, dynamic 2-3s outro CTA, and fallback beat uniqueness.
"""

import unittest
from agents.script_agent import (
    deduplicate_script_narration,
    ensure_dynamic_outro_cta,
    clean_script_narration,
    auto_calibrate_script_to_profile,
    TELUGU_DYNAMIC_CTAS,
)
from agents.validation_agent import get_format_profile
from supervisor import heal_network_or_quota


class TestScriptDeduplicationAndCTA(unittest.TestCase):
    def test_exact_duplicate_blocks_removal(self):
        """Simulate the exact failure case where paragraphs were duplicated word-for-word."""
        failing_script = (
            "హాయ్ ఫ్రెండ్స్! ఈరోజు మనం ఎంతో ఆసక్తికరమైన Xbox Rejects GTA 6 గురించి సమగ్రంగా తెలుసుకుందాం.\n"
            "అసలు దీని వెనుక ఉన్న ముఖ్యమైన విశేషాలు మరియు ప్రస్తుత పరిస్థితులు చాలా మందికి తెలియదు.\n"
            "ఇందులోని ప్రతి ఒక్క అంశం కూడా భవిష్యత్తులో తీసుకురాబోయే ప్రభావం ఎంతో విశేషమైనది.\n"
            "వివిధ వర్గాల నుండి వస్తున్న స్పందనలను బట్టి చూస్తే, ఇది ప్రస్తుతం సెంటర్ ఆఫ్ అట్రాక్షన్ గా నిలిచింది.\n"
            "ప్రధానంగా ఇందులో గుర్తించాల్సిన మరో ముఖ్యమైన పాయింట్ ఏమిటంటే దీని ప్రాముఖ్యత రోజురోజుకూ పెరుగుతోంది.\n"
            "మరిన్ని తాజా పరిణామాలు త్వరలోనే ప్రజల్లోకి మరింత వేగంగా చేరనున్నాయి.\n"
            "సమగ్ర విశ్లేషణలో ఇది ఒక కీలకమైన మలుపుగా పరిశీలకులు భావిస్తున్నారు.\n"
            "మరి దీనిపై మీ అభిప్రాయం మరియు అనుభవాలు ఏమిటి బాస్?\n"
            "అసలు దీని వెనుక ఉన్న ముఖ్యమైన విశేషాలు మరియు ప్రస్తుత పరిస్థితులు చాలా మందికి తెలియదు.\n"
            "ఇందులోని ప్రతి ఒక్క అంశం కూడా భవిష్యత్తులో తీసుకురాబోయే ప్రభావం ఎంతో విశేషమైనది.\n"
            "వివిధ వర్గాల నుండి వస్తున్న స్పందనలను బట్టి చూస్తే, ఇది ప్రస్తుతం సెంటర్ ఆఫ్ అట్రాక్షన్ గా నిలిచింది.\n"
            "ప్రధానంగా ఇందులో గుర్తించాల్సిన మరో ముఖ్యమైన పాయింట్ ఏమిటంటే దీని ప్రాముఖ్యత రోజురోజుకూ పెరుగుతోంది.\n"
            "కింద కామెంట్స్ లో తెలియజేయండి, ఇన్ఫర్మేటివ్ వీడియోల కోసం లైక్ కొట్టి సబ్‌స్క్రైబ్ చేసుకోండి!"
        )

        cleaned = deduplicate_script_narration(failing_script)
        lines = [l.strip() for l in cleaned.splitlines() if l.strip()]

        # Verify that duplicate sentences were pruned
        count_visheshalu = sum(1 for l in lines if "అసలు దీని వెనుక ఉన్న ముఖ్యమైన విశేషాలు" in l)
        count_prabhavam = sum(1 for l in lines if "భవిష్యత్తులో తీసుకురాబోయే ప్రభావం" in l)
        self.assertEqual(count_visheshalu, 1, "Duplicate sentence must appear exactly once")
        self.assertEqual(count_prabhavam, 1, "Duplicate sentence must appear exactly once")

    def test_fuzzy_duplicate_sentences_removal(self):
        """Verify that near-identical sentences (>80% overlap) are detected and removed."""
        text = (
            "ఈ విషయంపై సోషల్ మీడియాలో భారీ చర్చ నడుస్తోంది.\n"
            "ఈ విషయంపై సోషల్ మీడియాలో భారీ చర్చ అయితే నడుస్తోంది బాస్.\n"
            "ఆడియన్స్ రియాక్షన్స్ చూస్తే అసలు ఏం జరుగుతుందో అర్థమవుతుంది."
        )
        cleaned = deduplicate_script_narration(text)
        lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
        self.assertEqual(len(lines), 2, "Near-identical sentence must be filtered out")

    def test_ensure_dynamic_outro_cta_telugu(self):
        """Verify that every Telugu script ends with a 2-3s like, share, and subscribe CTA."""
        draft = "ఈ కొత్త అప్‌డేట్ అందరినీ ఆశ్చర్యపరిచింది. రాబోయే రోజుల్లో మరిన్ని మార్పులు చూడొచ్చు."
        with_cta = ensure_dynamic_outro_cta(draft, topic="Gaming Update", is_indic=True)

        last_line = with_cta.splitlines()[-1]
        self.assertTrue("లైక్" in last_line, "Outro CTA must contain లైక్ (like)")
        self.assertTrue("షేర్" in last_line, "Outro CTA must contain షేర్ (share)")
        self.assertTrue("సబ్‌స్క్రైబ్" in last_line, "Outro CTA must contain సబ్‌స్క్రైబ్ (subscribe)")

        # Pacing check: 2-3s spoken duration is ~8-15 words
        word_count = len(last_line.split())
        self.assertLessEqual(word_count, 18, f"Outro CTA should be punchy (<= 18 words), got {word_count}")

    def test_ensure_dynamic_outro_cta_replaces_incomplete_cta(self):
        """Verify that an incomplete CTA (e.g. only subscribe) is updated to include all three."""
        draft = (
            "ముఖ్యమైన విషయాలు ఇవే బాస్.\n"
            "మరిన్ని వీడియోల కోసం సబ్‌స్క్రైబ్ చేసుకోండి!"
        )
        with_cta = ensure_dynamic_outro_cta(draft, topic="Phone News", is_indic=True)
        lines = with_cta.splitlines()
        last_line = lines[-1]
        self.assertTrue("లైక్" in last_line and "షేర్" in last_line and "సబ్‌స్క్రైబ్" in last_line)
        # Should not have stacked multiple CTAs
        self.assertEqual(len(lines), 2, "Should replace the incomplete CTA instead of stacking")

    def test_supervisor_fallback_zero_duplicates(self):
        """Verify that supervisor fallback generation produces 0 duplicates for 60-90s medium profile."""
        context = {
            "topic": "Xbox Rejects GTA 6 PC Streaming",
            "content_type": "News",
            "language_style": "Telugu - తెలుగు (Creator / Casual)",
            "voice": "Shruti",
            "target_duration": "60-90s",
        }
        fallback_script = heal_network_or_quota("script_agent", context=context)
        self.assertIsNotNone(fallback_script)

        lines = [l.strip() for l in fallback_script.splitlines() if l.strip()]
        unique_lines = set(lines)
        self.assertEqual(len(lines), len(unique_lines), f"Supervisor fallback had duplicates: {lines}")

        # Must end with Like, Share, Subscribe CTA
        last_line = lines[-1]
        self.assertTrue("లైక్" in last_line and "షేర్" in last_line and "సబ్‌స్క్రైబ్" in last_line)

    def test_auto_calibrate_zero_duplicates_large_expansion(self):
        """Verify that auto_calibrate_script_to_profile does not duplicate lines during large expansion."""
        profile = get_format_profile("extended_short", "9:16")
        short_script = "గేమింగ్ రంగంలో కొత్త సంచలనం మొదలైంది. జీటీఏ 6 గురించి క్రేజీ న్యూస్ బయటకు వచ్చింది."

        calibrated = auto_calibrate_script_to_profile(
            short_script, profile, topic="GTA 6 Gaming", content_type="Gaming"
        )
        lines = [l.strip() for l in calibrated.splitlines() if l.strip()]
        unique_lines = set(lines)
        self.assertEqual(len(lines), len(unique_lines), f"Calibrated script had duplicate lines: {lines}")
        self.assertGreaterEqual(len(calibrated.split()), 120, "Must reach target word count for 60-90s")


if __name__ == "__main__":
    unittest.main()

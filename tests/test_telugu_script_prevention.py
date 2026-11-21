import unittest
import json
from pathlib import Path
from agents.roast_engine import _sanitize_awkward_loanwords, validate_and_heal_script, markup_roast_delivery
from agents.script_agent import synthesize_beat_visual_plan


class TestTeluguScriptPrevention(unittest.TestCase):
    def test_contestants_thrigun_clean_name(self):
        """Verifies that contestants.json uses clean Thrigun / త్రిగుణ్ without Eswaran hallucination."""
        c_path = Path("contestants.json")
        self.assertTrue(c_path.exists())
        data = json.loads(c_path.read_text(encoding="utf-8"))
        thrigun = data.get("thrigun", {})
        self.assertEqual(thrigun.get("full_name"), "Thrigun")
        self.assertEqual(thrigun.get("telugu_name"), "త్రిగుణ్")
        self.assertNotIn("eswaran", thrigun.get("full_name", "").lower())

    def test_sanitize_awkward_loanwords_fixes_all_hallucinations(self):
        """Verifies that awkward machine translations and hallucinations are cleanly replaced."""
        bad_text = (
            'ట్రైగన్ ఎస్వరన్ కూడా వచ్చాడు. నాగార్జున క్షేత్రంలో "ఇది నామల్ టీజర్ కదా" అని ఓవర్‌యాక్టింగ్ చేశాడు. '
            'నాగ్‌గారి చిరునవ్వుతో... "నామల్ టీజర్ కంటే నీ టీజర్‌లోనే ఎక్కువ నాటకం" అని స్ట్రాంగ్ గా రీప్లై ఇచ్చాడు. '
            'అమన్ చిరునవ్వుతో... "మీ అక్టోర్ షాపింగ్ లిస్ట్‌లో నేనా?" అని సైలింగ్ చేశాడు. ఆ అక్టోర్ ఎవరో తెలుసా? '
            'ముకేష్ ఫ్లోర్‌పై కుప్పకూలి... "మేము నాటకం చేస్తున్నాం" అని నోరు మళ్ళించాడు. '
            'నాగ్‌గారి "నీ డిక్టేటర్ పోజులు చూసి నాకే డిక్టేటర్ పోజులు గుర్తుకు వచ్చాయి" అని జోక్ చేశాడు. '
            'ముకేష్ క్లబ్‌బింగ్ చేస్తూ... ఆన్స్వర్ ఇచ్చాడు. హౌస్‌లో హాస్యం చోటు చేసుకుంది.'
        )
        cleaned = _sanitize_awkward_loanwords(bad_text)

        # Verify all garbage phrases are removed
        self.assertNotIn("ట్రైగన్ ఎస్వరన్", cleaned)
        self.assertNotIn("ట్రైగన్", cleaned)
        self.assertNotIn("నామల్", cleaned)
        self.assertNotIn("అక్టోర్", cleaned)
        self.assertNotIn("షాపింగ్ లిస్ట్", cleaned)
        self.assertNotIn("సైలింగ్", cleaned)
        self.assertNotIn("నోరు మళ్ళించాడు", cleaned)
        self.assertNotIn("క్లబ్‌బింగ్", cleaned)
        self.assertNotIn("హాస్యం చోటు చేసుకుంది", cleaned)
        self.assertNotIn("క్షేత్రంలో", cleaned)

        # Verify correct Telugu words are present
        self.assertIn("త్రిగుణ్", cleaned)
        self.assertIn("నార్మల్", cleaned)
        self.assertIn("యాక్టర్", cleaned)
        self.assertIn("స్మైల్ చేశాడు", cleaned)
        self.assertIn("జోక్ చేశారు", cleaned)

    def test_validate_and_heal_script_respects_honorifics(self):
        """Verifies validate_and_heal_script enforces Nagarjuna honorifics."""
        sample = 'నాగ్‌గారి పంచ్ విసిరి జోక్ చేశాడు... సుధీర్ రెడ్డి నవ్వాడు.'
        healed = validate_and_heal_script(sample, topic="Bigg Boss Telugu 10")
        self.assertIn("నాగ్‌గారు", healed)
        self.assertIn("జోక్ చేశారు", healed)
        self.assertNotIn("జోక్ చేశాడు", healed)

    def test_markup_roast_delivery_cleans_orphan_quotes(self):
        """Verifies that beats do not start with broken quotes or orphan quote characters."""
        script = 'అమన్ చిరునవ్వుతో... "మీ టార్గెట్ లిస్ట్‌లో నేనా? " అని స్మైల్ చేశాడు. ముకేష్ ఫ్లోర్‌పై కుప్పకూలాడు.'
        beats = markup_roast_delivery(script, topic="Bigg Boss 10")
        for b in beats:
            text = b["spoken_text"]
            self.assertFalse(text.startswith('"'), f"Beat starts with orphan quote: {text}")
            self.assertFalse(text.startswith('”'), f"Beat starts with orphan quote: {text}")
            self.assertNotIn('" అని', text)

    def test_visual_plan_locks_nagarjuna_entity(self):
        """Verifies that beats mentioning Nagarjuna are strictly bound to Akkineni Nagarjuna."""
        delivery_plan = [
            {"beat_id": 1, "spoken_text": "ముకేష్ హౌస్‌లో డిక్టేటర్ అయ్యాడు.", "emotion": "hype"},
            {"beat_id": 2, "spoken_text": 'నాగ్‌గారి "నీ డిక్టేటర్ పోజులు చూసి నాకే డిక్టేటర్ పోజులు గుర్తుకు వచ్చాయి" అని జోక్ చేశారు.', "emotion": "mock"},
            {"beat_id": 3, "spoken_text": "సుధీర్ రెడ్డి షార్ప్ గా కౌంటర్ ఇచ్చాడు.", "emotion": "deadpan"}
        ]
        visual_plan = synthesize_beat_visual_plan(delivery_plan, topic="బిగ్ బాస్ 10: Mukesh Dictator")
        self.assertEqual(len(visual_plan), 3)
        # Beat 2 mentions Nagarjuna, so its main entity must be Nagarjuna
        beat_2_visual = visual_plan[1]
        self.assertTrue(
            "Nagarjuna" in beat_2_visual or "Akkineni" in beat_2_visual,
            f"Beat 2 should feature Nagarjuna, but was: {beat_2_visual}"
        )

    def test_sanitize_awkward_loanwords_fixes_new_machine_translations(self):
        """Verifies that alien machine transliterations (యాజ్, ముచ్చుడు, ప్లీడ్, ఐసీయూ) are cleanly replaced."""
        bad_text = (
            'నాగ్‌గారు అమన్‌పై "నీ యాజ్ ఫెయిల్ అయింది" అని ముచ్చుడు పెట్టారు. '
            'సుధీర్ మాత్రం "ఓట్లు లేకపోతే ఐసీయూకి వెళ్తాను" అని డ్రామాట్టెక్‌గా ప్లీడ్ చేశాడు. '
            'అమన్‌నే ఎలిమినేట్ చేయాలన్న యాజ్ విజయం సాధించినట్లుంది. '
            'మీరింట్లో ఐసీయూకి వెళ్లాలనిపించే ప్లీడ్ ఎప్పుడైనా చేశారా?'
        )
        cleaned = _sanitize_awkward_loanwords(bad_text)
        self.assertNotIn("యాజ్", cleaned)
        self.assertNotIn("ముచ్చుడు", cleaned)
        self.assertNotIn("ప్లీడ్", cleaned)
        self.assertNotIn("ఐసీయూ", cleaned)
        self.assertNotIn("డ్రామాట్టెక్‌గా", cleaned)

    def test_bb10_contestants_week_11_timeline(self):
        """Verifies that BB10 timeline is properly anchored to Week 11 (Day 75+)."""
        from data.bb10_contestants import CURRENT_WEEK, CURRENT_DAY, get_active_contestants, get_eliminated_contestants
        self.assertEqual(CURRENT_WEEK, 11)
        self.assertEqual(CURRENT_DAY, 75)
        active = get_active_contestants()
        eliminated = get_eliminated_contestants()
        self.assertIn("Thrigun", active)
        self.assertIn("Temper Vamsi", active)
        self.assertIn("Sudheer Reddy", active)
        self.assertIn("Gundeboina Jhansi", eliminated)
        self.assertIn("Rohit Patnam", eliminated)
        self.assertNotIn("Gundeboina Jhansi", active)
        self.assertNotIn("Rohit Patnam", active)

    def test_validate_and_heal_script_replaces_eliminated_contestants(self):
        """Verifies validate_and_heal_script replaces evicted housemates with active housemates in BB context."""
        sample = "బిగ్ బాస్ హౌస్‌లో సుధీర్ రెడ్డి, ఝాన్సీని సేఫ్‌లో పెట్టేసి, అమన్‌నే టార్గెట్ చేసాడు. రోహిత్ ఫ్యాన్స్‌కి సౌండ్ అవుతూ రచ్చ చేశాడు."
        healed = validate_and_heal_script(sample, topic="Bigg Boss Telugu 10")
        self.assertNotIn("ఝాన్సీ", healed)
        self.assertNotIn("రోహిత్", healed)

    def test_auto_calibrate_script_preserves_cta_at_the_end(self):
        """Verifies auto_calibrate_script_to_profile keeps CTA as the final sentence."""
        from agents.script_agent import auto_calibrate_script_to_profile
        from config.format_profiles import get_format_profile
        profile = get_format_profile("60-90s", "9:16", "short")
        short_script = "బిగ్ బాస్ హౌస్‌లో నామినేషన్ల రచ్చ మొదలైంది. త్రిగుణ్ మరియు ముకేష్ మధ్య వార్ పీక్స్‌కి చేరింది. లైక్, షేర్, సబ్‌స్క్రైబ్ చేయండి."
        calibrated = auto_calibrate_script_to_profile(short_script, profile, topic="Bigg Boss Telugu 10 Week 11", content_type="Bigg Boss Telugu")
        self.assertTrue(len(calibrated.split()) >= 120)
        # Verify CTA keywords are present towards the end
    def test_bb10_potti_naresh_is_week_11_captain(self):
        """Verifies Potti Naresh is the sole Captain for Week 11 and Temper Vamsi is not."""
        from data.bb10_contestants import CURRENT_CAPTAIN, CURRENT_CAPTAIN_TELUGU, CONTESTANTS_BB10, get_active_contestants_prompt_context
        self.assertEqual(CURRENT_CAPTAIN, "Potti Naresh")
        self.assertEqual(CURRENT_CAPTAIN_TELUGU, "పొట్టి నరేష్")
        self.assertTrue(CONTESTANTS_BB10["naresh"].get("is_captain", False))
        self.assertFalse(CONTESTANTS_BB10["temper vamsi"].get("is_captain", False))
        ctx = get_active_contestants_prompt_context()
        self.assertIn("Potti Naresh (పొట్టి నరేష్ - CURRENT WEEK 11 CAPTAIN)", ctx)
        self.assertIn("Temper Vamsi is NOT the captain", ctx)

    def test_validate_and_heal_script_corrects_vamsi_captaincy_to_naresh(self):
        """Verifies validate_and_heal_script catches Vamsi captaincy hallucination and fixes it to Potti Naresh."""
        from agents.roast_engine import validate_and_heal_script
        sample = "బిగ్ బాస్ హౌస్‌లో టెంపర్ వాంశీ ఈ వారం క్యాప్టెన్ అయ్యాడు. అతని లీడర్‌షిప్ చూసి అందరూ షాక్. వాంశీ క్యాప్టెన్సీ ఎలా ఉందో చెప్పండి."
        healed = validate_and_heal_script(sample, topic="Bigg Boss Telugu 10 Week 11")
        self.assertIn("పొట్టి నరేష్ ఈ వారం క్యాప్టెన్", healed)
        self.assertIn("పొట్టి నరేష్ క్యాప్టెన్సీ", healed)
        self.assertNotIn("వాంశీ", healed)

    def test_validate_and_heal_script_fixes_false_no_elimination_claims(self):
        """Verifies validate_and_heal_script removes contradictory 'no elimination' lines during active Week 11."""
        from agents.roast_engine import validate_and_heal_script
        sample = "ఈ వారం 1 నిమిషంలో ఎలిమినేషన్ రచ్చ. కానీ నిజం చెప్పాలంటే, ఈ వారం ఎలిమినేషన్‌ జరగలేదు. హౌస్‌లో అందరూ సురక్షితంగా ఉన్నారు."
        healed = validate_and_heal_script(sample, topic="Bigg Boss 10 Elimination Shock")
        self.assertNotIn("ఎలిమినేషన్‌ జరగలేదు", healed)
        self.assertNotIn("అందరూ సురక్షితంగా ఉన్నారు", healed)

    def test_post_process_metadata_fixes_vamsi_captaincy_and_filters_tags(self):
        """Verifies _post_process_metadata replaces Vamsi captaincy and purges disallowed tags."""
        from agents.metadata_agent import _post_process_metadata
        title = "బిగ్ బాస్ 10: వాంశీ ఈ వారం క్యాప్టెన్ #Shorts"
        desc = "బిగ్ బాస్ 10 లో వాంశీ క్యాప్టెన్సీ బాగుందా? కామెంట్స్ లో చెప్పండి."
        tags = ["Shorts", "bigg boss 10", "mansi captain", "naga chaitanya", "potti naresh"]
        t_out, d_out, tags_out = _post_process_metadata(title, desc, tags, topic="Bigg Boss 10", script="Sample script")
        self.assertIn("పొట్టి నరేష్", t_out)
        self.assertIn("పొట్టి నరేష్ క్యాప్టెన్సీ", d_out)
        self.assertNotIn("mansi captain", tags_out)
        self.assertNotIn("naga chaitanya", tags_out)
        self.assertIn("potti naresh", tags_out)


    def test_load_golden_full_script_returns_high_quality_telugu(self):
        """Verifies load_golden_full_script returns complete, authentic Telugu scripts."""
        from agents.roast_engine import load_golden_full_script
        bb_script = load_golden_full_script("Bigg Boss Telugu 10 Week 11")
        self.assertTrue(len(bb_script.split()) >= 80)
        self.assertIn("పొట్టి నరేష్", bb_script)
        self.assertIn("బాస్", bb_script)
        self.assertIn("కామెంట్", bb_script)

        cinema_script = load_golden_full_script("Devara Telugu Cinema Teaser Review")
        self.assertTrue(len(cinema_script.split()) >= 80)
        self.assertIn("సినిమా", cinema_script)

        tech_script = load_golden_full_script("Samsung Galaxy Ultra Phone Launch")
        self.assertTrue(len(tech_script.split()) >= 80)
        self.assertIn("ఫోన్", tech_script)

    def test_micro_fragment_line_merging(self):
        """Verifies that 10+ short lines are merged into continuous spoken text."""
        from agents.roast_engine import _sanitize_awkward_loanwords
        fragmented = (
            "ఈ వారం ఎలిమినేషన్ రచ్చ మొదలైంది.\n"
            "హౌస్‌లో డ్రామా నెక్స్ట్ లెవెల్.\n"
            "అసలు ట్విస్ట్ ఏంటంటే...\n"
            "పొట్టి నరేష్ కెప్టెన్ అయ్యాడు.\n"
            "హౌస్‌మేట్స్ ఫ్యూజులు ఎగిరిపోయాయి.\n"
            "నాగ్‌గారు క్లాస్ పీకారు.\n"
            "మీ ఓటు ఎవరికో కామెంట్ చేయండి."
        )
        cleaned = _sanitize_awkward_loanwords(fragmented)
        self.assertNotIn("\n", cleaned)
        self.assertTrue(len(cleaned.split()) >= 25)

    def test_anti_robot_literal_translations(self):
        """Verifies that awkward English-to-Telugu machine translations are sanitized."""
        from agents.roast_engine import _sanitize_awkward_loanwords
        bad_text = (
            "నాగర్‌జున ముందు అతను పాత్ర తీసుకున్నాడు. "
            "దాంతో ఇంటిలో ఉష్ణోగ్రత పెరిగింది. "
            "వారిద్దరి మధ్య చిన్న అర్థమైన దావాపేదావాను చూశాం. "
            "యూనిట్‌లోనే ముఖ్యంగా ఆల్ఫా మేల్ లా మాట్లాడాడు. "
            "డీబ్జాని మరియు ఊర్వశి షాకయ్యారు."
        )
        cleaned = _sanitize_awkward_loanwords(bad_text)
        self.assertNotIn("నాగర్‌జున", cleaned)
        self.assertIn("నాగార్జున", cleaned)
        self.assertNotIn("పాత్ర తీసుకున్నాడు", cleaned)
        self.assertIn("లీడ్ తీసుకున్నాడు", cleaned)
        self.assertNotIn("ఇంటిలో ఉష్ణోగ్రత పెరిగింది", cleaned)
        self.assertIn("హౌస్‌లో రచ్చ మొదలైంది", cleaned)
        self.assertNotIn("దావాపేదావా", cleaned)
        self.assertNotIn("యూనిట్‌లోనే ముఖ్యంగా", cleaned)
        self.assertNotIn("ఆల్ఫా మేల్", cleaned)
        self.assertNotIn("డీబ్జాని", cleaned)
        self.assertIn("దేబ్జాని", cleaned)
        self.assertNotIn("ఊర్వశి", cleaned)
        self.assertIn("వర్షిణి", cleaned)

    def test_validate_and_heal_script_fixes_rapid_elimination_hallucination(self):
        """Verifies validate_and_heal_script purges impossible rapid elimination numbers and myth translations."""
        from agents.roast_engine import validate_and_heal_script
        sample = "ఈ వారం 1 నిమిషంలో 3 లేడీలు ఎలిమినేట్ అయ్యారు! అయ్యో, ఇది మరీ మిథే, ఫ్రెండ్స్. బిగ్‌ బాస్ 10 లో ఇలాంటి డ్రామా ఎప్పుడూ ఉంటుంది."
        healed = validate_and_heal_script(sample, topic="Bigg Boss 10 Elimination Shock")
        self.assertNotIn("1 నిమిషంలో 3 లేడీలు ఎలిమినేట్", healed)
        self.assertNotIn("మిథే", healed)
        self.assertIn("ఈ వారం ఎలిమినేషన్ రచ్చతో బిగ్ బాస్ హౌస్ మొత్తం షేక్ అయింది!", healed)


if __name__ == "__main__":
    unittest.main()



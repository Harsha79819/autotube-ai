"""
AutoTube AI - YouTube Strategy & Algorithm Director AI (analytics/youtube_director.py)
Inspired by modern Multi-Agent Control Planes (Paperclip AI architecture):
1. Executive Strategy & Scheduling: Directs Channel 1 & Channel 2 content cadences,
   formats (Shorts vs Long-form), duration bounds, and viral retention angles based on IST viewing peaks.
2. Cross-Video Dialogue Memory & Cliché Ban: Maintains persistent dialogue ledger (data/dialogue_ledger.json).
   Temporarily locks out previously used catchphrases and clichés for 48 hours / 10 videos.
3. 6 Dynamic Telugu Creator Archetypes: Rotates narrative styles so scripts never sound predictable or repetitive.
"""

import os
import re
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DIALOGUE_LEDGER_PATH = DATA_DIR / "dialogue_ledger.json"

# ==============================================================================
# COMMON REPETITIVE CLICHÉS & PATTERNS TO GUARD ACROSS RUNS
# ==============================================================================
KNOWN_CLICHE_PATTERNS = [
    r"వాతావరణం\s*భగ్గుమంది(?:\s*బాస్)?",
    r"ఫ్యూజులు\s*ఎగిరిపోయాయి(?:\s*బాస్)?",
    r"చూశారా\s*బాస్",
    r"గాలి\s*(?:మొత్తం\s*)?తీసేశాడు",
    r"రచ్చ\s*రంబోలా",
    r"సీన్\s*కట్\s*చేస్తే",
    r"ముసుగులు\s*తీస్తుంటే",
    r"కాలర్\s*ఎగరేశారు",
    r"కిర్రాక్\s*రోస్ట్‌ల\s*కోసం",
    r"సాలిడ్\s*రోస్ట్‌ల\s*కోసం",
    r"ఆస్కార్\s*రేంజ్\s*ఓవర్\s*యాక్షన్",
    r"పరువు\s*మొత్తం\s*పోయింది",
    r"హైప్\s*ఒక\s*రేంజ్\s*లో\s*ఉంటే",
    r"అసలు\s*ట్విస్ట్\s*ఏంటంటే",
]

# Clean display names for the clichés
KNOWN_CLICHES_DISPLAY = [
    "వాతావరణం భగ్గుమంది బాస్",
    "ఫ్యూజులు ఎగిరిపోయాయి బాస్",
    "చూశారా బాస్",
    "గాలి తీసేశాడు",
    "రచ్చ రంబోలా",
    "సీన్ కట్ చేస్తే",
    "ముసుగులు తీస్తుంటే",
    "కాలర్ ఎగరేశారు",
    "కిర్రాక్ రోస్ట్‌ల కోసం",
    "సాలిడ్ రోస్ట్‌ల కోసం",
    "ఆస్కార్ రేంజ్ ఓవర్ యాక్షన్",
    "పరువు మొత్తం పోయింది",
    "హైప్ ఒక రేంజ్ లో ఉంటే",
    "అసలు ట్విస్ట్ ఏంటంటే",
]

# Clean organic replacements if a banned cliché accidentally slips into generated text
CLICHE_AUTO_REPLACEMENTS = [
    (r"వాతావరణం\s*భగ్గుమంది(?:\s*బాస్)?", "పరిస్థితి ఒక్కసారిగా వేడెక్కింది"),
    (r"ఫ్యూజులు\s*ఎగిరిపోయాయి(?:\s*బాస్)?", "మైండ్ బ్లాంక్ అయిపోయింది"),
    (r"చూశారా\s*బాస్[!?]?", "గమనించారా!"),
    (r"గాలి\s*(?:మొత్తం\s*)?తీసేశాడు", "దిమ్మతిరిగే కౌంటర్ ఇచ్చాడు"),
    (r"రచ్చ\s*రంబోలా", "తీవ్ర దుమారం"),
    (r"సీన్\s*కట్\s*చేస్తే", "కానీ తీరా చూస్తే"),
    (r"ముసుగులు\s*తీస్తుంటే", "అసలు రంగులు బయటపడుతుంటే"),
    (r"కాలర్\s*ఎగరేశారు", "బిల్డప్ ఇచ్చారు"),
    (r"కిర్రాక్\s*రోస్ట్‌ల\s*కోసం", "నిజాయితీ గల రివ్యూల కోసం"),
    (r"సాలిడ్\s*రోస్ట్‌ల\s*కోసం", "మరిన్ని ఇంట్రెస్టింగ్ అప్‌డేట్స్ కోసం"),
    (r"ఆస్కార్\s*రేంజ్\s*ఓవర్\s*యాక్షన్", "అంత పెద్ద డ్రామా"),
    (r"పరువు\s*మొత్తం\s*పోయింది", "ఆట మొత్తం తేలిపోయింది"),
    (r"హైప్\s*ఒక\s*రేంజ్\s*లో\s*ఉంటే", "ప్రచారం భారీగా ఉన్నా"),
    (r"అసలు\s*ట్విస్ట్\s*ఏంటంటే(?:\.\.\.)?", "ఇక్కడ అందరూ గుర్తించాల్సిన పాయింట్ ఏంటంటే"),
]

# ==============================================================================
# 6 DYNAMIC NARRATIVE ARCHETYPES (ROTATING CREATOR STYLES)
# ==============================================================================
NARRATIVE_ARCHETYPES = {
    "skeptical_truth_teller": {
        "id": "skeptical_truth_teller",
        "name": "Skeptical Truth-Teller (నిజాలు నిలదీసే శైలి)",
        "tone_desc": "Sharp, insightful, realistic breakdown questioning outward appearances.",
        "hook_templates": [
            "పైకి కనిపించే డ్రామా ఒకటైతే... లోపల తెరవెనుక నడిచిన అసలు కథ వేరే లెవల్!",
            "జనాలు నిజమే అనుకుంటున్నారు కానీ, దీని వెనుక ఉన్న అసలైన స్ట్రాటజీ తెలిస్తే మైండ్ బ్లాక్ అవ్వాల్సిందే!",
            "నిజం చెప్పాలంటే... ఇక్కడ జరుగుతున్న సీన్ చూశాక ఎవరికైనా క్లియర్ గా అర్థమైపోతుంది!",
        ],
        "punchline_samples": [
            "చెప్పే మాటలకి చేసే పనులకి అస్సలు సంబంధమే లేదు!",
            "ప్లాన్ అదిరింది కానీ... కాలిక్యులేషన్ మొత్తం రివర్స్ అయింది!",
            "ముందు నవ్వుతూ కనిపించినా... వెనుక మాత్రం పక్కా ఎత్తుగడలు నడుస్తున్నాయి!",
        ],
        "cta_template": "మరి ఇందులో ఎవరు నిజాయితీగా ఉన్నారు, ఎవరు నటిస్తున్నారు? మీ ఆలోచనలను కింద కామెంట్స్ లో చెప్పండి! జెన్యూన్ అనాలిసిస్ కోసం లైక్ చేసి సబ్‌స్క్రైబ్ చేసుకోండి!",
    },
    "high_voltage_alert": {
        "id": "high_voltage_alert",
        "name": "High-Voltage Breaking Alert (షాకింగ్ బ్రేకింగ్ శైలి)",
        "tone_desc": "Fast-paced, urgent, gripping creator energy emphasizing immediate stakes.",
        "hook_templates": [
            "ఇప్పుడే అందిన మైండ్ బ్లోయింగ్ ట్విస్ట్... ఈ ఒక్క పరిణామంతో మొత్తం ఈక్వేషన్స్ మారిపోయాయి!",
            "అసలు ఎవరూ ఊహించని షాకింగ్ డెవలప్‌మెంట్... నిన్నటి దాకా ఒక లెక్క, ఇప్పటినుంచి ఇంకో లెక్క!",
            "హౌస్‌లో ఎవరూ ఎక్స్‌పెక్ట్ చేయని ఊహించని షాక్... ఈ నిర్ణయం తర్వాత అంతా తలకిందులైపోయింది!",
        ],
        "punchline_samples": [
            "డేంజర్ జోన్ లోకి ఎవరు వెళ్తారో తెలిశాక అందరి ముఖాల్లో రంగులు మారాయి!",
            "ఒక్క దెబ్బతో మొత్తం గేమ్ పైచేయి మారిపోయింది!",
            "ఇంత వేగంగా సీన్ తిరుగుతుందని ఎవరూ కలల్లో కూడా అనుకోలేదు!",
        ],
        "cta_template": "మరి ఈ ట్విస్ట్ తో ఆట ఎవరి వైపు తిరుగుతుంది అనుకుంటున్నారు? మీ ప్రెడిక్షన్ వెంటనే కామెంట్ చేయండి! లేటెస్ట్ అప్‌డేట్స్ కోసం లైక్, షేర్, సబ్‌స్క్రైబ్ చేసుకోండి!",
    },
    "witty_observational": {
        "id": "witty_observational",
        "name": "Witty Observational Comedy (వ్యంగ్య హాస్య శైలి)",
        "tone_desc": "Hilarious, sarcastic friend tone laughing at funny contradictions and overaction.",
        "hook_templates": [
            "ఇదెక్కడి విచిత్రం రా బాబు... అక్కడ జరుగుతున్న కామెడీ చూస్తుంటే నవ్వాలో ఏడ్వాలో అర్థం కావట్లేదు!",
            "కాన్ఫిడెన్స్ ఏమో ఆకాశమంత... చేసిన పనేమో గోరంత... వీళ్ల బిల్డప్ చూస్తే ఎవరికైనా దిమ్మతిరగాల్సిందే!",
            "హౌస్ లో వీళ్లు ఇచ్చే ఎక్స్‌ప్రెషన్స్ చూస్తే, వీళ్లు గేమ్ ఆడుతున్నారా లేక కామెడీ క్లాస్ తీసుకుంటున్నారా అని డౌట్ వస్తుంది!",
        ],
        "punchline_samples": [
            "వాల్యూమ్ మాత్రం ఫుల్... కంటెంట్ చూస్తే నిల్!",
            "ఓవర్ కాన్ఫిడెన్స్ తో వెళ్లి గోతిలో పడడం అంటే ఇదేనేమో!",
            "పది మందికి లెక్చర్లు ఇచ్చి... చివర్లో తానే బలైపోయాడు!",
        ],
        "cta_template": "ఈ కామెడీ డ్రామాలో అసలైన కవరింగ్ మాస్టర్ ఎవరో కనిపెట్టారా? కింద కామెంట్స్ లో ఓటేయండి! ఫన్ రివ్యూల కోసం లైక్ కొట్టి సబ్‌స్క్రైబ్ చేసుకోండి!",
    },
    "dramatic_suspense": {
        "id": "dramatic_suspense",
        "name": "Dramatic Suspense & Irony (డ్రామా & ట్విస్ట్ శైలి)",
        "tone_desc": "Cinematic pacing, deliberate pauses, revealing ironic turnarounds.",
        "hook_templates": [
            "అందరి దృష్టి ఒకరి మీదే ఉంది... కానీ సైలెంట్ గా వెనుక నుంచి ఇంకొకరు వేసిన స్కెచ్ ఎవరికీ అర్థం కాలేదు!",
            "ఒక్క మాటతో మొదలైన చిన్న వివాదం... చివరకు ఇంత పెద్ద తుఫానులా మారుతుందని ఎవరూ అనుకోలేదు!",
            "ప్రతి ఒక్కరూ తమదే గెలుపు అని ధీమాగా ఉన్నారు... కానీ స్క్రిప్ట్ రివర్స్ అయ్యే సమయం వచ్చేసింది!",
        ],
        "punchline_samples": [
            "నమ్మిన వాళ్లే వెన్నుపోటు పొడిస్తే ఆ బాధ ఎలా ఉంటుందో ఇప్పుడు తెలిసొచ్చింది!",
            "అధికారం చేతికి రాగానే అహంకారం తలకెక్కినట్లు ప్రవర్తించారు!",
            "ఆటలో గెలవడం ముఖ్యం కాదు... పరువు కాపాడుకోవడం ముఖ్యం అని ఇప్పటికైనా గుర్తిస్తారా!",
        ],
        "cta_template": "మరి ఈ మైండ్ గేమ్‌లో చివరకు నిలిచేది ఎవరు? మీ అభిప్రాయాన్ని కింద కామెంట్ చేయండి! మరిన్ని ఆసక్తికరమైన డీకోడింగ్స్ కోసం సబ్‌స్క్రైబ్ చేసుకోండి!",
    },
    "tech_science_wonder": {
        "id": "tech_science_wonder",
        "name": "Tech & Science Wonder (లాజికల్ మిస్టరీ శైలి - Channel 1)",
        "tone_desc": "High curiosity, scientific facts, unraveling mysteries that blow people's minds.",
        "hook_templates": [
            "మనం రోజూ సాధారణంగా చూసే ఈ ఒక్క విషయం వెనుక... ఎంత పెద్ద సైన్స్ దాగుందో తెలిస్తే కళ్ళు తేలేస్తారు!",
            "శాస్త్రవేత్తలకే దిమ్మతిరిగేలా చేసిన ఈ షాకింగ్ రహస్యం గురించి ప్రపంచంలో 99 శాతం మందికి తెలియదు!",
            "స్మార్ట్‌ఫోన్లలో అందరూ చేసే ఈ చిన్న తప్పు వల్ల బ్యాటరీ మాత్రమే కాదు, మీ పర్సనల్ డేటా కూడా డేంజర్ లో పడుతోంది!",
        ],
        "punchline_samples": [
            "మనం ఆలోచించే విధానానికి... రియాలిటీలో సైన్స్ కి ఉన్నంత వ్యత్యాసం ఇదే!",
            "కంటికి కనిపించని ఈ చిన్న మెకానిజం వెనుక బిలియన్ డాలర్ల టెక్నాలజీ నడుస్తోంది!",
            "ఒక్కసారి ఈ ఫ్యాక్ట్ అర్థమయ్యాక... మీరు ప్రపంచాన్ని చూసే కోణమే మారిపోతుంది!",
        ],
        "cta_template": "ఈ ఇంట్రెస్టింగ్ సైన్స్ ఫ్యాక్ట్ మీకు ముందే తెలుసా లేక ఇప్పుడే ఫస్ట్ టైమ్ విన్నారా? కామెంట్స్ లో చెప్పండి! ఇలాంటి క్రేజీ ఫ్యాక్ట్స్ కోసం లైక్ చేసి సబ్‌స్క్రైబ్ చేసుకోండి!",
    },
    "direct_provocative": {
        "id": "direct_provocative",
        "name": "Direct Provocative Debate (ఆడియన్స్‌ను కదిలించే శైలి)",
        "tone_desc": "Challenging the audience directly, sparking viral debate and comments.",
        "hook_templates": [
            "ఇంత ఓపెన్ గా తప్పు జరుగుతుంటే ప్రేక్షకులు చూస్తూ ఊరుకుంటారని ఎలా అనుకున్నారు?",
            "ఒకరి తప్పుని కప్పిపుచ్చడానికి మిగతా అందరినీ టార్గెట్ చేయడం ఎంతవరకు న్యాయం?",
            "నిజంగా ఇది తెలివైన గేమా... లేక ఆడియన్స్‌ని ఫూల్స్ చేయాలనుకుంటున్నారా?",
        ],
        "punchline_samples": [
            "రూల్స్ అందరికీ ఒకేలా ఉండాలి కానీ... కొందరికి ప్రత్యేకం అయితే కుదరదు కదా!",
            "ఆడియన్స్ అంతా గమనిస్తున్నారు అన్న సంగతి మర్చిపోయి ప్రవర్తిస్తున్నారు!",
            "ఓట్లతో ఇచ్చే తీర్పు ముందు ఏ పీఆర్ స్ట్రాటజీ కూడా పనిచేయదు!",
        ],
        "cta_template": "మరి ఇందులో ఎవరి వైపు న్యాయం ఉంది? మీ సూటి సమాధానాన్ని కింద కామెంట్ చేయండి! నిక్కచ్చిగా మాట్లాడే వీడియోల కోసం లైక్, షేర్, సబ్‌స్క్రైబ్ చేసుకోండి!",
    },
}

class YouTubeDirectorAI:
    """
    Paperclip-inspired Central Control Plane & Strategy Director for AutoTube AI.
    Governs channel strategies, dialogue freshness, and cross-run memory.
    """
    def __init__(self, ledger_file: Path = DIALOGUE_LEDGER_PATH):
        self.ledger_file = Path(ledger_file)
        self._ensure_ledger_file()

    def _ensure_ledger_file(self):
        if not self.ledger_file.exists():
            initial_data = {
                "version": "2.0.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "history": [],
                "active_banned_cliches": [],
                "archetype_usage_counts": {k: 0 for k in NARRATIVE_ARCHETYPES.keys()},
            }
            self.ledger_file.write_text(json.dumps(initial_data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _read_ledger(self) -> Dict[str, Any]:
        try:
            return json.loads(self.ledger_file.read_text(encoding="utf-8"))
        except Exception:
            self._ensure_ledger_file()
            return json.loads(self.ledger_file.read_text(encoding="utf-8"))

    def _write_ledger(self, data: Dict[str, Any]):
        try:
            data["last_updated"] = datetime.now(timezone.utc).isoformat()
            self.ledger_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"⚠️ [YouTube Director] Failed to write dialogue ledger: {e}")

    # ==========================================================================
    # 1. CHANNEL STRATEGY & SCHEDULING (REAL YOUTUBE ALGORITHM CADENCE)
    # ==========================================================================
    def get_channel_strategy(self, channel_id: str, current_dt: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Determines the optimal format, target duration, category, and viral angle
        for Channel 1 vs Channel 2 based on current Indian Standard Time (IST).
        """
        if current_dt is None:
            # Current time in IST (UTC+5:30)
            utc_now = datetime.now(timezone.utc)
            ist_now = utc_now + timedelta(hours=5, minutes=30)
        else:
            ist_now = current_dt

        hour = ist_now.hour
        is_ch1 = "1" in str(channel_id) or "primary" in str(channel_id).lower() or "lazy" in str(channel_id).lower()

        if is_ch1:
            # Channel 1: Lazy Line (Facts, Tech, Science, Deep Dive)
            if 8 <= hour < 12:
                time_slot = "Morning Tech & Smartphone Secrets"
                fmt = "9:16 Short"
                duration = "45-60s"
                category = "Technology"
                angle = "Hidden mobile tricks, battery saver hacks, or crazy software secrets."
                archetype = "tech_science_wonder"
            elif 12 <= hour < 16:
                time_slot = "Lunchtime In-Depth Explainer"
                fmt = "16:9 Long-form"
                duration = "3-5m"
                category = "Technology"
                angle = "Deep dive tech teardown, Indian flagship buyer guide, or tech history."
                archetype = "skeptical_truth_teller"
            elif 16 <= hour < 20:
                time_slot = "Evening Mind-Blowing Science & Curiosities"
                fmt = "9:16 Short"
                duration = "45-60s"
                category = "Interesting Facts"
                angle = "Ancient engineering marvels, cosmic discoveries, or bizarre human psychology."
                archetype = "tech_science_wonder"
            else:
                time_slot = "Primetime Flagship & AI Tools Deep Dive"
                fmt = "9:16 Short"
                duration = "45-70s"
                category = "Technology"
                angle = "New AI apps, scam alerts, and future technology breakthroughs."
                archetype = "high_voltage_alert"

            return {
                "channel": "Channel 1 (Lazy Line - Facts & Tech)",
                "channel_id": "Channel 1",
                "ist_time": ist_now.strftime("%H:%M IST"),
                "time_slot": time_slot,
                "recommended_format": fmt,
                "aspect_ratio": "9:16" if "Short" in fmt else "16:9",
                "target_duration": duration,
                "category": category,
                "recommended_angle": angle,
                "recommended_archetype": archetype,
                "algorithm_rationale": "Channel 1 audiences engage with curiosity-driven tech hacks during morning/evening commutes and long-form explainers during lunch/night.",
            }
        else:
            # Channel 2: Viral Talks Me & Mine (Bigg Boss 10, Cinema, Roasts)
            if 8 <= hour < 12:
                time_slot = "Morning House Drama & Nomination Buzz"
                fmt = "9:16 Short"
                duration = "45-70s"
                category = "Bigg Boss Telugu 10"
                angle = "Midnight fights, breakfast kitchen drama, and nomination reaction roasts."
                archetype = "witty_observational"
            elif 12 <= hour < 16:
                time_slot = "Afternoon Midday Controversy Breakdown"
                fmt = "16:9 Long-form"
                duration = "3-5m"
                category = "Bigg Boss Telugu 10"
                angle = "Complete analysis of captaincy tasks, groupism, and voting trend shifts."
                archetype = "dramatic_suspense"
            elif 16 <= hour < 20:
                time_slot = "Evening Danger Zone Voting Trends & Tollywood Buzz"
                fmt = "9:16 Short"
                duration = "45-70s"
                category = "Bigg Boss Telugu 10"
                angle = "Unofficial voting leaks, danger zone bottom 2, or savage trailer roasts."
                archetype = "high_voltage_alert"
            else:
                time_slot = "Primetime Post-Episode Grilling & Weekend Preview"
                fmt = "9:16 Short"
                duration = "45-70s"
                category = "Bigg Boss Telugu 10"
                angle = "Host Nagarjuna's weekend grilling expectations or savage reality checks on fake house drama."
                archetype = "direct_provocative"

            return {
                "channel": "Channel 2 (Viral Talks - Entertainment & Roast)",
                "channel_id": "Channel 2",
                "ist_time": ist_now.strftime("%H:%M IST"),
                "time_slot": time_slot,
                "recommended_format": fmt,
                "aspect_ratio": "9:16" if "Short" in fmt else "16:9",
                "target_duration": duration,
                "category": category,
                "recommended_angle": angle,
                "recommended_archetype": archetype,
                "algorithm_rationale": "Channel 2 peaks around live episode airing (21:00-23:00) and morning afterbuzz (08:30-10:00). High emotional tension and witty punchlines drive maximum comment section debates.",
            }

    # ==========================================================================
    # 2. CROSS-VIDEO DIALOGUE MEMORY & CLICHÉ TIMEOUT
    # ==========================================================================
    def get_fresh_dialogue_directive(self, channel: str = "Channel 2", topic: str = "") -> Dict[str, Any]:
        """
        Inspects the dialogue ledger, selects the freshest narrative archetype,
        builds a list of currently banned clichés, and constructs prompt directives.
        """
        ledger = self._read_ledger()
        history = ledger.get("history", [])

        # 1. Identify actively banned clichés from recent history (last 10 videos or 48h)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        banned_phrases = set()

        # Always ban the most overused base phrases
        for item in history[-10:]:
            # Check timestamps
            ts_str = item.get("timestamp")
            if ts_str:
                try:
                    dt = datetime.fromisoformat(ts_str)
                    if dt < recent_cutoff and len(history) > 15:
                        continue
                except Exception:
                    pass

            for c in item.get("detected_cliches", []):
                banned_phrases.add(c)
            # Add opening hook keywords to prevent exact hook repeats
            hook_lead = item.get("hook_lead", "")
            if hook_lead and len(hook_lead) > 6:
                banned_phrases.add(hook_lead)

        # Baseline safeguards: if no history yet, seed baseline overused phrases into ban list
        if not banned_phrases:
            banned_phrases = {"వాతావరణం భగ్గుమంది బాస్", "ఫ్యూజులు ఎగిరిపోయాయి బాస్", "చూశారా బాస్", "గాలి తీసేశాడు", "రచ్చ రంబోలా"}

        # 2. Pick least recently used archetype
        usage_counts = ledger.get("archetype_usage_counts", {})
        recent_archetypes = [h.get("archetype_id") for h in history[-5:] if h.get("archetype_id")]

        candidates = []
        is_ch1 = "1" in str(channel) or "primary" in str(channel).lower()

        for arch_id, arch_data in NARRATIVE_ARCHETYPES.items():
            if is_ch1 and arch_id in ("witty_observational", "direct_provocative") and "tech" not in topic.lower():
                # Prefer tech/wonder or skeptical for Channel 1
                weight = 1
            elif not is_ch1 and arch_id == "tech_science_wonder":
                # Don't use science wonder for entertainment
                continue
            else:
                weight = 5

            # Penalize recently used archetypes
            if recent_archetypes and arch_id == recent_archetypes[-1]:
                weight -= 4
            elif arch_id in recent_archetypes:
                weight -= 2

            total_uses = usage_counts.get(arch_id, 0)
            score = weight * 10 - total_uses
            candidates.append((score, arch_id))

        candidates.sort(key=lambda x: x[0], reverse=True)
        chosen_id = candidates[0][1] if candidates else "skeptical_truth_teller"
        archetype = NARRATIVE_ARCHETYPES[chosen_id]

        # 3. Build positive prompt guidance & negative constraint
        banned_list = sorted(list(banned_phrases))
        banned_bullets = "\n".join(f"  * DO NOT USE: \"{p}\"" for p in banned_list[:8])

        prompt_directive = f"""
============================================================
🎭 YOUTUBE DIRECTOR AI: FRESH DIALOGUE & NARRATIVE ARCHETYPE
============================================================
ACTIVE NARRATIVE STYLE: {archetype['name']}
Style Philosophy: {archetype['tone_desc']}

🌟 FRESH HOOK EXAMPLES TO MODEL (DO NOT COPY WORD-FOR-WORD, MATCH THIS FRESH VIBE):
- "{archetype['hook_templates'][0]}"
- "{archetype['hook_templates'][1]}"
- "{archetype['hook_templates'][2]}"

⚡ FRESH WITTY PUNCHLINE EXAMPLES:
- "{archetype['punchline_samples'][0]}"
- "{archetype['punchline_samples'][1]}"
- "{archetype['punchline_samples'][2]}"

🎯 FRESH HIGH-ENGAGEMENT COMMENT TRIGGER & CTA:
"{archetype['cta_template']}"

🚫 STRICTLY FORBIDDEN RECENT CLICHÉS (TEMPORARILY BANNED TO GUARANTEE FRESHNESS):
{banned_bullets}
- MANDATORY: Write 100% original, creative creator dialogues. Avoid tired repetitive clichés!
============================================================
"""

        return {
            "archetype_id": chosen_id,
            "archetype_name": archetype["name"],
            "fresh_hooks": archetype["hook_templates"],
            "fresh_punchlines": archetype["punchline_samples"],
            "fresh_cta": archetype["cta_template"],
            "banned_cliches": banned_list,
            "prompt_directive": prompt_directive,
        }

    # ==========================================================================
    # 3. DIALOGUE RECORDING & REPUTATION AUDIT
    # ==========================================================================
    def record_script_dialogues(self, script: str, topic: str, channel: str = "Channel 2", archetype_id: str = ""):
        """
        Extracts key phrases from the generated script, tracks clichés, and logs
        into the persistent ledger.
        """
        ledger = self._read_ledger()
        clean_text = script.strip()
        lines = [l.strip() for l in clean_text.splitlines() if l.strip()]

        # Extract opening hook
        first_line = lines[0] if lines else clean_text[:80]
        sentences = re.split(r'[.!?—\n]+', first_line)
        hook_sentence = sentences[0].strip() if sentences else first_line[:60]
        hook_lead = " ".join(hook_sentence.split()[:5])

        # Detect clichés present in script
        detected = []
        for pat in KNOWN_CLICHE_PATTERNS:
            match = re.search(pat, clean_text)
            if match:
                detected.append(match.group(0).strip())

        # Extract closing CTA line
        cta_line = lines[-1] if lines else ""

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "channel": channel,
            "topic": topic,
            "archetype_id": archetype_id or "skeptical_truth_teller",
            "hook_lead": hook_lead,
            "detected_cliches": list(set(detected)),
            "cta_sample": cta_line[:80],
            "word_count": len(clean_text.split()),
        }

        history = ledger.get("history", [])
        history.append(entry)
        # Cap history to last 100 entries
        if len(history) > 100:
            history = history[-100:]
        ledger["history"] = history

        # Update archetype usage counts
        counts = ledger.get("archetype_usage_counts", {})
        if archetype_id:
            counts[archetype_id] = counts.get(archetype_id, 0) + 1
        ledger["archetype_usage_counts"] = counts

        self._write_ledger(ledger)
        print(f"🧠 [YouTube Director] Recorded script dialogues in ledger: {len(detected)} clichés logged, archetype='{archetype_id}'.")

    def calculate_freshness_score(self, script: str) -> Tuple[int, List[str]]:
        """
        Evaluates the dialogue freshness of a script (0 - 100%).
        100% means zero stale clichés. Each detected cliché penalizes score by 15-25 points.
        """
        clean_text = script.strip()
        detected = []
        for pat in KNOWN_CLICHE_PATTERNS:
            match = re.search(pat, clean_text)
            if match:
                detected.append(match.group(0).strip())

        penalty = len(detected) * 20
        score = max(20, 100 - penalty)
        return score, detected

    def sanitize_script_cliches(self, script: str) -> str:
        """
        Rapidly scrubs and replaces any overused clichés with fresh, natural Telugu idioms.
        """
        cleaned = script
        for pat, rep in CLICHE_AUTO_REPLACEMENTS:
            cleaned = re.sub(pat, rep, cleaned, flags=re.IGNORECASE)
        return cleaned


# Global Singleton instance
_director_instance: Optional[YouTubeDirectorAI] = None

def get_youtube_director() -> YouTubeDirectorAI:
    global _director_instance
    if _director_instance is None:
        _director_instance = YouTubeDirectorAI()
    return _director_instance

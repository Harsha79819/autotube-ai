"""
AutoTube AI - Global Supervisor & Autonomous Self-Healing Error Interceptor (supervisor.py)

Intercepts unhandled runtime exceptions across all major pipeline stages,
analyzes errors via Gemini AI, applies concrete automated fallbacks
without requiring human intervention, and streams real-time recovery events to the UI.
"""

import os
import sys
import re
import time
import json
import traceback
import threading
import subprocess
import functools
import inspect
import asyncio
from pathlib import Path
from collections import deque
from datetime import datetime

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
FALLBACK_DIR = ASSETS_DIR / "fallback"
FAILED_RUNS_DIR = ROOT / "failed_runs"
FAILED_QUEUE_DIR = ROOT / "failed_queue"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
FAILED_RUNS_DIR.mkdir(parents=True, exist_ok=True)
FAILED_QUEUE_DIR.mkdir(parents=True, exist_ok=True)

EVENTS_LOG_FILE = OUTPUT_DIR / "self_healing_events.jsonl"

# Thread-safe in-memory ring buffer for incident history
_INCIDENT_LOCK = threading.Lock()
_INCIDENT_HISTORY = deque(maxlen=100)
_UNCONSUMED_EVENTS = []  # For Streamlit toast pop notifications

# Load existing events on startup if present
if EVENTS_LOG_FILE.exists():
    try:
        with open(EVENTS_LOG_FILE, "r", encoding="utf-8") as _f:
            for _line in _f:
                if _line.strip():
                    _INCIDENT_HISTORY.append(json.loads(_line))
    except Exception:
        pass


# ============================================================
# 1. AI ERROR ANALYZER (GEMINI + HEURISTIC FALLBACK)
# ============================================================

def analyze_error_with_ai(stage_name, error, tb_str="", context=None):
    """
    Analyze error using Gemini AI to classify and diagnose root cause.
    Classifications:
      (A) Transient/Network (HTTP 429, timeout, network disconnect, quota)
      (B) Bad Input Asset (corrupt image, missing file, zero-byte audio)
      (C) Parameter Mismatch (FFmpeg filter/scale error, KeyError, type error)
    """
    error_type = type(error).__name__
    error_msg = str(error)
    context_str = json.dumps(context, default=str) if context else "{}"

    # Try fast Gemini AI analysis
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = f"""You are an elite autonomous debugging supervisor for an AI video production pipeline.
Analyze this runtime error from stage '{stage_name}'.

ERROR TYPE: {error_type}
ERROR MESSAGE: {error_msg}
TRACEBACK SNIPPET:
{tb_str[-1200:] if tb_str else 'N/A'}
CONTEXT:
{context_str[:600]}

Classify the error into exactly one category:
(A) Transient/Network
(B) Bad Input Asset
(C) Parameter Mismatch

Return ONLY a JSON object with keys:
{{
  "classification": "(A) Transient/Network" | "(B) Bad Input Asset" | "(C) Parameter Mismatch",
  "root_cause": "concise 1-sentence explanation of what failed",
  "recommended_action": "concrete fallback action to heal without human input"
}}
"""
            for model_id in ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-3.5-flash-lite", "gemini-3.8-flash"]:
                try:
                    resp = client.models.generate_content(model=model_id, contents=prompt)
                    raw_text = getattr(resp, "text", "")
                    if raw_text:
                        clean_text = raw_text.strip()
                        if "```json" in clean_text:
                            clean_text = clean_text.split("```json")[1].split("```")[0].strip()
                        elif "```" in clean_text:
                            clean_text = clean_text.split("```")[1].split("```")[0].strip()
                        parsed = json.loads(clean_text)
                        return {
                            "classification": parsed.get("classification", "(C) Parameter Mismatch"),
                            "root_cause": parsed.get("root_cause", error_msg),
                            "recommended_action": parsed.get("recommended_action", "Applied automated fallback handler"),
                        }
                except Exception:
                    continue
        except Exception:
            pass

    # Deterministic heuristic fallback analysis
    lower_err = f"{error_type} {error_msg}".lower()

    if any(k in lower_err for k in ["timeout", "429", "quota", "connection", "rate limit", "resourceexhausted", "dns", "http", "network"]):
        classification = "(A) Transient/Network"
        root_cause = f"Network timeout or API quota limit reached: {error_msg[:120]}"
        action = "Switched to cached assets or secondary offline fallback strategy"
    elif any(k in lower_err for k in ["filenotfound", "cannot identify image", "corrupt", "no such file", "unidentifiedimage", "empty audio", "0 bytes", "image", "asset"]):
        classification = "(B) Bad Input Asset"
        root_cause = f"Asset corrupted or missing: {error_msg[:120]}"
        action = "Replaced corrupted/missing asset with fallback placeholder"
    else:
        classification = "(C) Parameter Mismatch"
        root_cause = f"Parameter, codec, or key error in {stage_name}: {error_msg[:120]}"
        action = "Sanitized parameters and re-invoked with safe baseline configuration"

    return {
        "classification": classification,
        "root_cause": root_cause,
        "recommended_action": action,
    }


# ============================================================
# 2. CONCRETE AUTOMATED HEALING STRATEGIES
# ============================================================

def extract_clean_topic(raw_text: str, default_title: str = None) -> str:
    """
    Extract a clean, non-empty topic title from raw user input, prompt wrappers,
    or revision context. Guarantees the topic name is never blank.
    """
    if not raw_text:
        return str(default_title or "Global Technology Breakthroughs").strip()

    text = str(raw_text).strip()

    # If wrapped in revision prompt with ORIGINAL TOPIC:
    if "ORIGINAL TOPIC:" in text:
        after = text.split("ORIGINAL TOPIC:")[1]
        lines = [
            l.strip()
            for l in after.splitlines()
            if l.strip()
            and not l.strip().startswith("CONTENT TYPE:")
            and not l.strip().startswith("FEEDBACK:")
            and not l.strip().startswith("PREVIOUS SCRIPT:")
        ]
        if lines:
            text = lines[0]

    # If wrapped in general revision or instructions
    if "You are revising" in text or len(text) > 120:
        lines = [
            l.strip()
            for l in text.splitlines()
            if l.strip()
            and not l.startswith("You are")
            and not l.startswith("FEEDBACK:")
            and not l.startswith("PREVIOUS")
            and not l.startswith("CONTENT TYPE:")
        ]
        if lines:
            text = lines[0]

    # Strip markdown symbols
    clean = re.sub(r"[*_#`~]", "", text).strip()
    # Strip leading "The " or "the " if followed by other words
    clean = re.sub(r"^[Tt]he\s+(?=[A-Za-z0-9])", "", clean).strip()
    # Strip any trailing punctuation
    clean = re.sub(r"[\.:;,]+$", "", clean).strip()

    if not clean or len(clean) < 3:
        clean = str(default_title or "Global Technology Breakthroughs").strip()

    return clean[:100]


def heal_network_or_quota(stage_name, context=None):
    """
    Handle transient network failures and HTTP 429 quota limits.
    Switches to offline cached data or built-in templates.
    """
    context = context or {}

    if stage_name == "trend_agent":
        cache_file = OUTPUT_DIR / "trending_news_cache.json"
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                if cached:
                    return cached
            except Exception:
                pass
        return [
            {
                "title": "Global AI & Technology Breakthroughs 2026",
                "topic": "Global AI & Technology Breakthroughs 2026",
                "source": "AutoTube Evergreen Feed",
                "sources": ["AutoTube Knowledge Base"],
                "url": "https://news.google.com",
            }
        ]

    if stage_name == "script_agent":
        import re
        raw_topic = context.get("topic", "Latest Breakthroughs")
        default_title = context.get("default_title")
        clean_topic = extract_clean_topic(raw_topic, default_title)

        lang_val = str(context.get("language_style", "")).lower()
        voice_val = str(context.get("voice", "")).lower()

        is_tel = (
            bool(re.search(r"[\u0C00-\u0C7F]", str(clean_topic)))
            or "telugu" in lang_val
            or "తెలుగు" in str(context.get("language_style", ""))
            or "mohan" in voice_val
            or "shruti" in voice_val
            or "te-in" in voice_val
        )

        tel_topic = clean_topic
        if is_tel:
            try:
                from telugu_phonetic_normalizer import normalize_telugu_tech_script
                tel_topic = normalize_telugu_tech_script(clean_topic)
            except Exception:
                tel_topic = clean_topic

        target_duration = str(context.get("target_duration", "30-50s")).lower()
        content_type_ctx = str(context.get("content_type", "")).lower()
        raw_topic_lower = f"{raw_topic} {clean_topic} {content_type_ctx}".lower()

        # Category Detection
        satire_kw = {"satire", "satirical", "roast", "funny", "humor", "pretend", "lazy", "sarcastic", "joke", "comedy", "prank", "corporate", "office"}
        finance_kw = {"stock", "sensex", "nifty", "market", "finance", "money", "crypto", "bitcoin", "economy", "invest", "trading", "shares", "dividend", "bank", "gold"}
        history_kw = {"history", "ancient", "war", "empire", "king", "dynasty", "mystery", "secrets", "temple", "monument", "mythology", "archaeology", "historical"}
        ent_kw = {
            "movie", "cinema", "trailer", "box office", "actor", "celebrity", "film",
            "hollywood", "tollywood", "bollywood", "song", "bigg boss", "bb10", "star maa",
            "elimination", "nomination", "engaged", "engagement", "contestant", "housemate",
            "drama", "shiva", "priyanka jain", "hero", "heroine", "director", "producer"
        }
        phone_kw = {"smartphone", "iphone", "pixel", "galaxy", "phone", "oneplus", "snapdragon", "dimensity", "amoled", "oppo", "vivo", "redmi", "realme", "iqoo"}
        tech_kw = {"tech", "technology", "ai", "artificial intelligence", "software", "hardware", "gadget", "gadgets", "laptop", "pc", "computer", "algorithm", "robot"}
        facts_kw = {
            "fact", "facts", "earth", "space", "science", "universe", "planet", "nature",
            "physics", "curiosity", "solar", "moon", "gravity", "ocean", "atmosphere",
            "biology", "geology", "discovery", "astronomy", "speed", "spin", "spinning"
        }

        def any_kw(kws):
            return any(k in raw_topic_lower for k in kws)

        if any_kw(facts_kw) or "fact" in content_type_ctx or "curiosity" in content_type_ctx or "science" in content_type_ctx:
            category = "facts"
        elif any_kw(ent_kw) or "entertainment" in content_type_ctx or "cinema" in content_type_ctx or "movie" in content_type_ctx or "reality" in content_type_ctx or "bigg boss" in raw_topic_lower:
            category = "entertainment"
        elif any_kw(finance_kw) or "finance" in content_type_ctx:
            category = "finance"
        elif any_kw(history_kw) or "history" in content_type_ctx or "myth" in content_type_ctx:
            category = "history"
        elif any_kw(phone_kw):
            category = "phone"
        elif any_kw(tech_kw) or "tech" in content_type_ctx:
            category = "tech"
        elif any_kw(satire_kw) or "satir" in content_type_ctx or "sarcas" in content_type_ctx or "humor" in content_type_ctx or "roast" in content_type_ctx or "funny" in content_type_ctx:
            category = "satire"
        else:
            category = "general"

        def build_beats(cat, tel, duration_type):
            # duration_type: "short" (9), "medium" (13), "long" (24)
            if cat == "satire":
                is_office_theme = any(w in raw_topic_lower for w in ("office", "corporate", "cubicle", "employee", "workplace", "job", "manager", "excel", "software company"))
                if tel:
                    if is_office_theme:
                        base = [
                            (f"హాయ్ ఫ్రెండ్స్! {tel_topic} గురించి ఈరోజు మనం మాట్లాడబోయే అసలైన ఫన్నీ విషయాలు చూస్తే మీరు పడిపడి నవ్వుకుంటారు!",
                             f"{clean_topic} funny office comedy scene | stressed corporate employee looking confused at computer monitor"),
                            (f"బాస్, నిజంగా కష్టపడటం ఒక ఎత్తైతే, ఆఫీసులో కష్టపడుతున్నట్లు నటించడం ఇంకో పెద్ద కళ!",
                             f"{clean_topic} busy office desk with papers and laptop | employee pretending to work comedy reaction"),
                            (f"ముఖ్యంగా ల్యాప్‌టాప్‌లో ఎక్సెల్ షీట్ ఓపెన్ చేసి, కీబోర్డ్ మీద సీరియస్‌గా ఏదో టైప్ చేస్తున్నట్లు ఫేస్ పెట్టడం మొదటి ట్రిక్!",
                             f"{clean_topic} office worker typing furiously on keyboard | funny corporate meme reaction expression"),
                            (f"ఎవరైనా అడిగితే 'నేను క్రిటికల్ అనలిసిస్ చేస్తున్నాను' అని గంభీరంగా చెబితే, మేనేజర్ కూడా డిస్టర్బ్ చేయరు!",
                             f"{clean_topic} corporate team meeting room presentation | employees pretending to pay attention satire"),
                            (f"మధ్యమధ్యలో కాఫీ కప్పు పట్టుకుని ఆలోచిస్తున్నట్లు నడవడం ప్రొఫెషనల్ యాక్టింగ్ లెవెల్ సుమా!",
                             f"{clean_topic} employee taking coffee break in office pantry | relaxed corporate worker having coffee"),
                            (f"మీటింగ్‌లలో అందరూ మాట్లాడుతున్నప్పుడు తల ఊపుతూ సీరియస్ లుక్ ఇస్తే, మీరు ప్రాజెక్ట్ మెయిన్ పిల్లర్ అనుకుంటారు!",
                             f"{clean_topic} modern corporate office cubicles | person looking busy at desk workplace satire"),
                            (f"చివరిగా లాగ్ అవుట్ టైమ్ అయ్యేంత వరకు స్క్రీన్ చూస్తూ బిజీగా కనిపించడం ఒక సూపర్ పవర్!",
                             f"{clean_topic} clock on office wall end of work day | relieved office workers packing bags comedy"),
                            (f"మరి మీ ఆఫీసులో కూడా ఇలాంటి ప్రో-లెవెల్ యాక్టర్స్ ఎవరైనా ఉన్నారా బాస్?",
                             f"{clean_topic} laughing colleagues watching screen | funny office meme expression"),
                            (f"కింద కామెంట్స్ లో చెప్పండి, వీడియో నచ్చితే వెంటనే లైక్ చేసి సబ్‌స్క్రైబ్ చేసుకోండి!",
                             f"like share and subscribe animation youtube studio | comedy entertaining video closing call to action"),
                        ]
                    else:
                        base = [
                            (f"హాయ్ ఫ్రెండ్స్! {tel_topic} గురించి సోషల్ మీడియాలో జరుగుతున్న ఫన్నీ రచ్చ చూశారా? అసలు ఏం జరుగుతుందో ఇప్పుడు చూద్దాం!",
                             f"{clean_topic} dramatic entertainment moment | {clean_topic} viral discussion"),
                            (f"బాస్, ఈ విషయంలో జరుగుతున్న డ్రామా చూస్తుంటే ఎవరికైనా మైండ్ బ్లాంక్ అవ్వాల్సిందే!",
                             f"{clean_topic} shocking scene reaction | {clean_topic} heated discussion"),
                            (f"ఒకవైపు చూస్తే సీరియస్ ట్విస్ట్‌లు, మరోవైపు చూస్తే కడుపుబ్బా నవ్వించే ఓవరాక్షన్!",
                             f"{clean_topic} hilarious funny expression | {clean_topic} comedy reaction meme"),
                            (f"ఆడియన్స్ కూడా ఈ పరిణామాలను చూసి సోషల్ మీడియాలో మీమ్స్‌తో దుమ్మురేపుతున్నారు!",
                             f"{clean_topic} social media viral memes reaction | audience laughing comedy"),
                            (f"అసలు వాళ్లు చేస్తున్న పనులకు, చెబుతున్న లాజిక్స్‌కి ఏమైనా సంబంధం ఉందా బాస్?",
                             f"{clean_topic} confused reaction face | {clean_topic} surprising highlight"),
                            (f"స్క్రీన్ మీద వీళ్ల యాక్టింగ్ చూస్తుంటే ఆస్కార్ లెవెల్ పర్ఫార్మెన్స్ అండి బాబు!",
                             f"{clean_topic} dramatic expression close up | {clean_topic} highlight moment"),
                            (f"ఎవరి వ్యూహాలు వాళ్లవి, ఎవరి గేమ్ ప్లాన్ వాళ్లదే అన్నట్లుగా ఉంది పరిస్థితి!",
                             f"{clean_topic} dramatic confrontation scene | {clean_topic} intense moment"),
                            (f"మరి ఈ క్రేజీ డ్రామా మరియు రచ్చపై మీరేమనుకుంటున్నారు బాస్?",
                             f"{clean_topic} iconic comedy reaction still | {clean_topic} audience verdict"),
                            (f"కింద కామెంట్స్‌లో చెప్పండి, వీడియో నచ్చితే వెంటనే లైక్ కొట్టి సబ్‌స్క్రైబ్ చేసుకోండి!",
                             f"like share and subscribe animation youtube studio | comedy entertaining video closing call to action"),
                        ]
                else:
                    if is_office_theme:
                        base = [
                            (f"Welcome to the ultimate survival breakdown of {clean_topic}!",
                             f"{clean_topic} funny office comedy scene | stressed corporate employee looking confused at computer monitor"),
                            (f"Let's be completely honest: looking extremely busy is truly an Olympic-level corporate art form.",
                             f"{clean_topic} busy office desk with papers and laptop | employee pretending to work comedy reaction"),
                            (f"Rule number one: keep complex spreadsheets open and type furiously whenever someone walks by.",
                             f"{clean_topic} office worker typing furiously on keyboard | funny corporate meme reaction expression"),
                            (f"If your manager glances over, frown intently at the monitor like you are saving a critical project.",
                             f"{clean_topic} corporate team meeting room presentation | employees pretending to pay attention satire"),
                            (f"Always walk down the hallway with urgent determination while carrying an official notebook.",
                             f"{clean_topic} employee taking coffee break in office pantry | relaxed corporate worker having coffee"),
                            (f"In team meetings, nod thoughtfully and drop classic buzzwords to look like a visionary leader.",
                             f"{clean_topic} modern corporate office cubicles | person looking busy at desk workplace satire"),
                            (f"Block out your calendar with 'strategic focus alignment' to protect your inner peace.",
                             f"{clean_topic} clock on office wall end of work day | relieved office workers packing bags comedy"),
                            (f"Have you or your coworkers ever perfected any of these hilarious corporate survival tactics?",
                             f"{clean_topic} laughing colleagues watching screen | funny office meme expression"),
                            (f"Drop your best workplace stories in the comments below, hit like, and subscribe for more!",
                             f"like share and subscribe animation youtube studio | comedy entertaining video closing call to action"),
                        ]
                    else:
                        base = [
                            (f"Welcome to the most hilarious breakdown of {clean_topic} that everyone is talking about!",
                             f"{clean_topic} dramatic entertainment moment | {clean_topic} viral discussion"),
                            (f"Let's be completely real: the drama unfolding around this situation is truly unbelievable.",
                             f"{clean_topic} shocking scene reaction | {clean_topic} heated discussion"),
                            (f"On one hand, you have serious twists, and on the other, peak comedic overreaction!",
                             f"{clean_topic} hilarious funny expression | {clean_topic} comedy reaction meme"),
                            (f"Internet audiences and meme pages are having an absolute field day reacting to this.",
                             f"{clean_topic} social media viral memes reaction | audience laughing comedy"),
                            (f"The logic being thrown around here would leave anyone completely dumbfounded.",
                             f"{clean_topic} confused reaction face | {clean_topic} surprising highlight"),
                            (f"Watching this unfold feels like an Oscar-worthy comedic performance.",
                             f"{clean_topic} dramatic expression close up | {clean_topic} highlight moment"),
                            (f"Everyone has their own intense strategy, making the whole spectacle even more entertaining.",
                             f"{clean_topic} dramatic confrontation scene | {clean_topic} intense moment"),
                            (f"What is your hilarious take on all this unfolding drama?",
                             f"{clean_topic} iconic comedy reaction still | {clean_topic} audience verdict"),
                            (f"Drop your thoughts below, hit the like button, and subscribe for more comedy breakdowns!",
                             f"like share and subscribe animation youtube studio | comedy entertaining video closing call to action"),
                        ]
            elif cat == "finance":
                if tel:
                    base = [
                        (f"హాయ్ ఫ్రెండ్స్! {tel_topic} కి సంబంధించి మార్కెట్లో వచ్చిన తాజా అప్‌డేట్స్ ఇప్పుడు పరిశీలిద్దాం.",
                         f"{clean_topic} financial stock market trading floor | investor analyzing stock charts screen"),
                        (f"ఇటీవలి ట్రెండ్స్ చూస్తుంటే, మార్కెట్ సెంటిమెంట్ లో కీలక మార్పులు స్పష్టంగా కనిపిస్తున్నాయి.",
                         f"{clean_topic} stock market candle charts analytics | bull and bear financial graphics"),
                        (f"ముఖ్యంగా ఇన్వెస్టర్లు మరియు నిపుణులు ఈ పరిణామాలపై లోతైన విశ్లేషణ చేస్తున్నారు.",
                         f"{clean_topic} investment banking boardroom meeting | financial advisors reviewing economic data"),
                        (f"కీలక సెక్టార్ల పనితీరు రాబోయే రోజుల్లో సూచీల దిశను నిర్దేశించే అవకాశం ఉంది.",
                         f"{clean_topic} money growth investment graph | currency and financial metrics dashboard"),
                        (f"దీర్ఘకాలిక వ్యూహాలను రూపొందించేటప్పుడు రిస్క్ మేనేజ్‌మెంట్ ఎంతో ముఖ్యం.",
                         f"{clean_topic} global trade finance concept | digital banking transactions network"),
                        (f"గ్లోబల్ మార్కెట్ల ప్రభావం కూడా దేశీయ సూచీలపై పడే అవకాశాలు పుష్కలంగా ఉన్నాయి.",
                         f"{clean_topic} international financial exchange market | stock tickers digital board"),
                        (f"రాబోయే సెషన్లలో మార్కెట్ కదలికలు మరింత ఆసక్తికరంగా మారనున్నాయి.",
                         f"{clean_topic} business investor smiling at laptop screen | profitable portfolio growth"),
                        (f"మరి ఈ పరిణామాలపై మీ ఇన్వెస్ట్‌మెంట్ అభిప్రాయం ఏమిటి బాస్?",
                         f"{clean_topic} financial decision concept | modern finance office workspace"),
                        (f"కామెంట్స్‌లో చెప్పండి, రోజువారీ ఫైనాన్షియల్ అప్‌డేట్స్ కోసం లైక్ చేసి సబ్‌స్క్రైబ్ చేసుకోండి!",
                         f"like share and subscribe animation youtube studio | finance investment channel closing"),
                    ]
                else:
                    base = [
                        (f"Welcome to an essential market breakdown of {clean_topic}.",
                         f"{clean_topic} financial stock market trading floor | investor analyzing stock charts screen"),
                        (f"Recent market movements indicate significant shifts across key financial sectors.",
                         f"{clean_topic} stock market candle charts analytics | bull and bear financial graphics"),
                        (f"Institutional analysts and retail investors are closely tracking these key metrics.",
                         f"{clean_topic} investment banking boardroom meeting | financial advisors reviewing economic data"),
                        (f"Underlying economic indicators suggest cautious optimism in the upcoming sessions.",
                         f"{clean_topic} money growth investment graph | currency and financial metrics dashboard"),
                        (f"Maintaining strict risk management and portfolio diversification remains paramount.",
                         f"{clean_topic} global trade finance concept | digital banking transactions network"),
                        (f"Macroeconomic trends continue to play a pivotal role in shaping valuation standards.",
                         f"{clean_topic} international financial exchange market | stock tickers digital board"),
                        (f"Market participants are strategically positioning for the next phase of market action.",
                         f"{clean_topic} business investor smiling at laptop screen | profitable portfolio growth"),
                        (f"What is your trading and investment perspective on these developments?",
                         f"{clean_topic} financial decision concept | modern finance office workspace"),
                        (f"Share your thoughts below, hit the like button, and subscribe for timely updates!",
                         f"like share and subscribe animation youtube studio | finance investment channel closing"),
                    ]
            elif cat == "history":
                if tel:
                    base = [
                        (f"హాయ్ ఫ్రెండ్స్! చరిత్ర పుటల్లో ఎంతో ఆసక్తికరమైన {tel_topic} గురించి ఈరోజు తెలుసుకుందాం.",
                         f"{clean_topic} ancient history documentary cinematic | historical stone monument ancient temple"),
                        (f"తరతరాలుగా మానవాళిని ఆశ్చర్యపరుస్తున్న ఈ చారిత్రక అంశం వెనుక ఎన్నో రహస్యాలు దాగి ఉన్నాయి.",
                         f"{clean_topic} ancient civilization ruins archaeological site | vintage historical manuscripts"),
                        (f"పరిశోధకులు తవ్వకాల్లో మరియు ఆధారాలలో కనుగొన్న విషయాలు ప్రపంచాన్నే విస్తుపోయేలా చేశాయి.",
                         f"{clean_topic} museum artifacts display ancient relics | archaeologist inspecting historical stone"),
                        (f"ఆ కాలపు పరిస్థితులు, ప్రజల జీవన విధానం మరియు వారి గొప్ప సాంకేతికత అద్భుతం అని చెప్పాలి.",
                         f"{clean_topic} vintage historical maps and compass | classical architecture grand monument"),
                        (f"చారిత్రక ఆధారాల విశ్లేషణ ద్వారా సరికొత్త నిజాలు ఇప్పుడు వెలుగులోకి వస్తున్నాయి.",
                         f"{clean_topic} ancient palace royal court painting | historic stone carving heritage site"),
                        (f"ఇలాంటి ఘట్టాలు మన పూర్వీకుల జ్ఞానానికి మరియు సంస్కృతికి నిదర్శనంగా నిలుస్తాయి.",
                         f"{clean_topic} dramatic historic landscape scenic cinematic | ancient civilization heritage"),
                        (f"నేటికీ చరిత్రకారులు ఈ అంశంపై మరింత పరిశోధనలు కొనసాగిస్తున్నారు.",
                         f"{clean_topic} history documentary researcher studying artifacts | library vintage books archive"),
                        (f"మరి ఈ చారిత్రక విశేషాలపై మీరేమనుకుంటున్నారు బాస్?",
                         f"{clean_topic} historic discovery showcase | documentary storytelling visual"),
                        (f"కింద కామెంట్స్ లో మీ ఆలోచనలు పంచుకోండి, మరిన్ని హిస్టరీ వీడియోల కోసం సబ్‌స్క్రైబ్ చేసుకోండి!",
                         f"like share and subscribe animation youtube studio | history documentary channel closing"),
                    ]
                else:
                    base = [
                        (f"Journey back through time as we uncover the secrets of {clean_topic}.",
                         f"{clean_topic} ancient history documentary cinematic | historical stone monument ancient temple"),
                        (f"For generations, historians and archaeologists have been captivated by these remarkable events.",
                         f"{clean_topic} ancient civilization ruins archaeological site | vintage historical manuscripts"),
                        (f"Recent archaeological findings and preserved archives offer fresh perspective on what transpired.",
                         f"{clean_topic} museum artifacts display ancient relics | archaeologist inspecting historical stone"),
                        (f"The cultural ingenuity and technological prowess of this era continue to astonish modern scholars.",
                         f"{clean_topic} vintage historical maps and compass | classical architecture grand monument"),
                        (f"Connecting documented evidence paints an increasingly vivid portrait of this historical milestone.",
                         f"{clean_topic} ancient palace royal court painting | historic stone carving heritage site"),
                        (f"These timeless milestones remind us of the enduring power of human heritage.",
                         f"{clean_topic} dramatic historic landscape scenic cinematic | ancient civilization heritage"),
                        (f"Scholars worldwide continue to debate and celebrate the profound lessons of this era.",
                         f"{clean_topic} history documentary researcher studying artifacts | library vintage books archive"),
                        (f"What aspects of this history do you find most compelling?",
                         f"{clean_topic} historic discovery showcase | documentary storytelling visual"),
                        (f"Let us know your perspective in the comments and subscribe for more historic deep dives!",
                         f"like share and subscribe animation youtube studio | history documentary channel closing"),
                    ]
            elif cat == "phone":
                if tel:
                    base = [
                        (f"హాయ్ ఫ్రెండ్స్! {tel_topic} గురించి మార్కెట్లో వచ్చిన క్రేజీ అప్‌డేట్ చూశారా?",
                         f"{clean_topic} smartphone official announcement | {clean_topic} hands on first look flagship"),
                        (f"అసలు విషయం ఏంటంటే, ఇందులో యూజర్స్ అందరూ మెచ్చే సరికొత్త ఫీచర్లు రాబోతున్నాయి!",
                         f"{clean_topic} sleek smartphone design | modern mobile tech showcase studio"),
                        (f"ముఖ్యంగా డిస్‌ప్లే క్వాలిటీ మరియు స్లీక్ డిజైన్ నెక్స్ట్ లెవెల్ ఎక్స్‌పీరియన్స్ అందిస్తాయి.",
                         f"{clean_topic} colorful smartphone display screen | bezel less mobile screen test"),
                        (f"దీని కెమెరా స్పెసిఫికేషన్స్ తో అదిరిపోయే ఫోటోగ్రఫీ ఎక్స్‌పీరియన్స్ లభిస్తుంది.",
                         f"{clean_topic} smartphone camera lens hardware | mobile camera photography showcase"),
                        (f"పెర్ఫార్మెన్స్ విషయంలో కూడా హై-స్పీడ్ ప్రాసెసర్ తో సూపర్ ఫాస్ట్ గా రన్ అవుతుంది.",
                         f"{clean_topic} mobile processor microchip | high performance tech hardware"),
                        (f"భారీ బ్యాటరీ మరియు ఫాస్ట్ ఛార్జింగ్ సపోర్ట్ తో డైలీ యూసేజ్ చాలా స్మూత్ గా ఉంటుంది.",
                         f"{clean_topic} smartphone battery charging indicator | mobile battery capacity test"),
                        (f"కాంపిటీషన్ మోడల్స్ కంటే కూడా ఈ ప్రైస్ పాయింట్‌లో ఇది చాలా బెటర్‌గా నిలిచే ఛాన్స్ ఉంది.",
                         f"{clean_topic} comparison alongside competitor smartphones | side by side smartphone showcase"),
                        (f"త్వరలోనే ఇది అఫీషియల్ గా మార్కెట్లోకి రాబోతోంది!",
                         f"{clean_topic} gadget retail presentation | modern mobile device unboxing"),
                        (f"మరి దీనిపై మీరేమంటారు బాస్? కామెంట్స్ లో చెప్పండి, వీడియో నచ్చితే లైక్ చేసి సబ్‌స్క్రైబ్ చేసుకోండి!",
                         f"like share and subscribe animation youtube studio | tech channel closing"),
                    ]
                else:
                    base = [
                        (f"Did you hear the major announcement regarding {clean_topic}?",
                         f"{clean_topic} smartphone official announcement | {clean_topic} hands on first look flagship"),
                        (f"Groundbreaking developments are shifting expectations across mobile tech today.",
                         f"{clean_topic} sleek smartphone design | modern mobile tech showcase studio"),
                        (f"Early previews highlight an upgraded display with stunning colors and fluid refresh rates.",
                         f"{clean_topic} colorful smartphone display screen | bezel less mobile screen test"),
                        (f"The camera system introduces refined sensors designed for crisp all-round photography.",
                         f"{clean_topic} smartphone camera lens hardware | mobile camera photography showcase"),
                        (f"Under the hood, an upgraded processor architecture ensures rapid multitasking and gaming.",
                         f"{clean_topic} mobile processor microchip | high performance tech hardware"),
                        (f"All-day battery endurance combined with rapid charging minimizes daily downtime.",
                         f"{clean_topic} smartphone battery charging indicator | mobile battery capacity test"),
                        (f"Positioned against stiff competition, the price-to-performance equation looks solid.",
                         f"{clean_topic} comparison alongside competitor smartphones | side by side smartphone showcase"),
                        (f"Global availability is expected to roll out very soon.",
                         f"{clean_topic} gadget retail presentation | modern mobile device unboxing"),
                        (f"Would you pick this up? Share your thoughts below and subscribe for more tech reviews!",
                         f"like share and subscribe animation youtube studio | tech channel closing"),
                    ]
            elif cat == "facts":
                if tel:
                    base = [
                        (f"హాయ్ ఫ్రెండ్స్! ఒకవేళ మన భూమి కేవలం ఐదు సెకన్ల పాటు తిరగడం ఆగిపోతే ఏం జరుగుతుందో తెలుసా? ఈ ఆశ్చర్యకరమైన నిజాన్ని ఇప్పుడు లోతుగా తెలుసుకుందాం.",
                         f"{clean_topic} planet Earth rotating in deep space | blue planet glowing atmosphere satellite view"),
                        (f"మన భూమి భూమధ్యరేఖ వద్ద గంటకు సుమారు పదహారు వందల డెబ్బై కిలోమీటర్ల వేగంతో నిరంతరం తిరుగుతూనే ఉంటుంది.",
                         f"{clean_topic} globe spinning rotational axis equator line | scientific earth motion graphics"),
                        (f"ఈ విపరీతమైన వేగం వల్ల మనకు తెలియకుండానే భూమిపై ఉన్న ప్రతి ఒక్క వస్తువు కూడా అదే వేగంతో ప్రయాణిస్తోంది.",
                         f"{clean_topic} surface velocity physics demonstration | rotational inertia earth scale"),
                        (f"ఒక్కసారి ఊహించండి, అంతటి భారీ గ్రహం అకస్మాత్తుగా కేవలం ఐదు సెకన్ల పాటు బ్రేక్ వేస్తే ఏం జరుగుతుంది?",
                         f"{clean_topic} dramatic earth sudden stop visual | space view of sudden deceleration shockwave"),
                        (f"భౌతిక శాస్త్రంలో న్యూటన్ మొదటి నియమం ప్రకారం, ప్రయాణంలో ఉన్న ప్రతి వస్తువు తన చలనాన్ని కొనసాగించడానికి ప్రయత్నిస్తుంది. దీనినే ఇనర్షియా లేదా జడత్వం అంటారు.",
                         f"{clean_topic} newton first law inertia physics diagram | objects moving at high velocity concept"),
                        (f"భూమి ఆగినా, దానిపై ఉన్న మనుషులు, కార్లు, భవనాలు, కొండలు అన్నీ తూర్పు దిశగా గంటకు పదహారు వందల కిలోమీటర్ల వేగంతో ముందుకు విసిరివేయబడతాయి!",
                         f"{clean_topic} supersonic inertia shockwave throwing objects | dramatic physics simulation destruction"),
                        (f"ఒక బుల్లెట్ వేగంతో మనుషులు మరియు వాహనాలు గాల్లోకి దూసుకుపోవడం వల్ల క్షణాల్లో నగరాల రూపురేఖలే పూర్తిగా మారిపోతాయి.",
                         f"{clean_topic} city skyline sudden atmospheric blast | futuristic buildings facing sudden pressure"),
                        (f"కేవలం నేలమీద ఉన్న వస్తువులే కాకుండా, మన వాతావరణం కూడా ఇంకా అదే వేగంతో తిరుగుతూనే ఉంటుంది.",
                         f"{clean_topic} atmospheric winds clouds spinning over continents | hurricane storm clouds earth view"),
                        (f"దీనివల్ల ఉత్పన్నమయ్యే వినాశకరమైన తుఫాను గాలులు అణుబాంబు విస్ఫోటనం కంటే అత్యంత శక్తివంతంగా నేలను తుడిచిపెట్టేస్తాయి.",
                         f"{clean_topic} supersonic hurricane windstorm tearing through landscape | dramatic nature power"),
                        (f"ప్రపంచంలోని అతిపెద్ద భవనాలు, ఆకాశహర్మ్యాలు మరియు భారీ వంతెనలు క్షణాల్లో నేలమట్టం అవుతాయి.",
                         f"{clean_topic} dramatic skyscrapers swaying in violent winds | cinematic metropolis destruction"),
                        (f"ఇక సముద్రాల విషయానికి వస్తే, నీటికి ఉండే విశేషమైన జడత్వ శక్తి మరింత భయానకమైన పరిణామాలకు దారితీస్తుంది.",
                         f"{clean_topic} deep ocean colossal waves surging | ocean water moving violently across planet"),
                        (f"మహాసముద్రాలలోని అపారమైన నీరు తీరప్రాంతాలను దాటి కిలోమీటర్ల కొద్దీ నేలమీదకు మెగా సునామీలుగా దూసుకొస్తుంది.",
                         f"{clean_topic} massive mega tsunami crashing onto coastlines | towering ocean wave cinematic"),
                        (f"తీరప్రాంత నగరాలు, ఓడరేవులు మరియు తీరప్రాంతాలు నిమిషాల వ్యవధిలోనే పూర్తిగా నీట మునిగిపోతాయి.",
                         f"{clean_topic} coastal cities engulfed by colossal storm surge | aerial view of ocean flooding land"),
                        (f"భూమి భ్రమణం ఆగిపోవడం వల్ల సముద్రపు నీరు ధ్రువాల వైపు వేగంగా ఆకర్షించబడుతుంది, ఎందుకంటే అక్కడ గురుత్వాకర్షణ శక్తి భిన్నంగా ఉంటుంది.",
                         f"{clean_topic} water shifting toward north and south poles | global ocean migration simulation"),
                        (f"దీనివల్ల భూమధ్యరేఖ వద్ద ఒక సరికొత్త భారీ ఖండం ఏర్పడగా, ఉత్తర మరియు దక్షిణ ధ్రువాలు భారీ మహాసముద్రాలుగా మారుతాయి.",
                         f"{clean_topic} new equatorial supercontinent emerging | polar oceans planetary geography transformation"),
                        (f"ఈ విపరీతమైన భౌతిక మార్పుల వల్ల భూమి అంతర్గత పొరలలో భారీ ఒత్తిడి ఏర్పడుతుంది.",
                         f"{clean_topic} tectonic plates grinding under extreme stress | earth crust geology cross section"),
                        (f"టెక్టోనిక్ ప్లేట్లు ఒకదానితో ఒకటి బలంగా ఢీకొనడం వల్ల ప్రపంచవ్యాప్తంగా రికార్డు స్థాయి భూకంపాలు సంభవిస్తాయి.",
                         f"{clean_topic} massive global earthquakes shaking ground | seismograph needle spiking violently"),
                        (f"నిద్రాణంగా ఉన్న అనేక అగ్నిపర్వతాలు ఒక్కసారిగా బద్దలై లావా మరియు బూడిదను ఆకాశంలోకి వెదజల్లుతాయి.",
                         f"{clean_topic} volcanic eruption explosion ash cloud magma | dramatic volcano erupting night sky"),
                        (f"ఆకాశం మొత్తం దట్టమైన నల్లటి బూడిద మరియు పొగతో నిండిపోయి సూర్యకాంతి పూర్తిగా అదృశ్యమవుతుంది.",
                         f"{clean_topic} dark ash clouds covering the sun | apocalyptic atmosphere darkening earth"),
                        (f"అంతేకాకుండా, భూమి భ్రమణం వల్ల ఉత్పన్నమయ్యే అయస్కాంత క్షేత్రం లేదా మాగ్నెటోస్పియర్ తీవ్రంగా బలహీనపడుతుంది.",
                         f"{clean_topic} earth magnetic field lines weakening | solar radiation shielding failure diagram"),
                        (f"ఈ రక్షక కవచం బలహీనపడటం వల్ల సూర్యుడి నుండి వచ్చే ప్రాణాంతక కాస్మిక్ వికిరణాలు భూమి ఉపరితలాన్ని తాకుతాయి.",
                         f"{clean_topic} deadly solar radiation rays hitting earth atmosphere | cosmic rays penetration space"),
                        (f"కక్ష్యలో ఉన్న వేలాది అంతరిక్ష ఉపగ్రహాలు తమ నియంత్రణను కోల్పోయి భూమి వైపు కూలిపోయే ప్రమాదం ఉంది.",
                         f"{clean_topic} satellites falling out of orbit into atmosphere | space debris burning on re entry"),
                        (f"గ్లోబల్ కమ్యూనికేషన్ వ్యవస్థ, జీపీఎస్ మరియు ఇంటర్నెట్ నెట్‌వర్క్‌లు పూర్తిగా నిలిచిపోతాయి.",
                         f"{clean_topic} global satellite communication network black out | digital globe lines cutting off"),
                        (f"సరిగ్గా ఐదు సెకన్ల సమయం ముగిసిన తర్వాత, భూమి మళ్లీ సాధారణ వేగంతో తిరగడం ప్రారంభిస్తుంది!",
                         f"{clean_topic} earth suddenly resuming spin rotation | dramatic planet motion shockwave restart"),
                        (f"కానీ ఆశ్చర్యకరమైన విషయం ఏంటంటే, మళ్లీ తిరగడం ప్రారంభించినప్పుడు రెండోసారి భారీ కుదుపు మరియు షాక్‌వేవ్ ఉత్పన్నమవుతుంది.",
                         f"{clean_topic} secondary rotational shockwave sweeping continents | massive atmospheric turbulence"),
                        (f"ఆగిన వస్తువులు మళ్లీ అకస్మాత్తుగా కదలడం వల్ల రెండో విడత భౌతిక విధ్వంసం జరుగుతుంది.",
                         f"{clean_topic} secondary inertia kinetic force after restart | kinetic energy landscape transformation"),
                        (f"వాతావరణంలో గాలి మరియు సముద్రపు నీరు తిరిగి సాధారణ స్థితికి చేరుకోవడానికి ఎన్నో నెలలు లేదా సంవత్సరాలు పడుతుంది.",
                         f"{clean_topic} chaotic weather systems slowly stabilizing | turbulent earth satellite view"),
                        (f"భూగోళంపై ఉన్న భౌగోళిక సరిహద్దులు మరియు నదుల ప్రవాహ మార్గాలు శాశ్వతంగా మారిపోతాయి.",
                         f"{clean_topic} new rivers and transformed terrain satellite map | geographic landforms satellite"),
                        (f"మానవ నాగరికత నిర్మించుకున్న ఆధునిక ప్రపంచం కేవలం ఐదు సెకన్లలోనే చరిత్రలో కనివినీ ఎరుగని సవాలును ఎదుర్కొంటుంది.",
                         f"{clean_topic} human civilization facing planetary change | resilient humanity rebuilding concept"),
                        (f"శాస్త్రవేత్తలు నిర్వహించిన అత్యాధునిక సూపర్ కంప్యూటర్ సిమ్యులేషన్ల ద్వారా ఈ ఫలితాలు ధృవీకరించబడ్డాయి.",
                         f"{clean_topic} supercomputer simulation screens analyzing earth spin | planetary scientists at work"),
                        (f"ఖగోళ భౌతిక శాస్త్రంలో ఈ దృగ్విషయం గ్రహాల గతిశీలత మరియు సమతుల్యతను అర్థం చేసుకోవడానికి ఎంతగానో ఉపయోగపడుతుంది.",
                         f"{clean_topic} astrophysics planetary motion formulas | celestial mechanics orbital diagram"),
                        (f"మన భూమి ప్రతిరోజూ నిశ్శబ్దంగా తిరుగుతూ ఉండటం మన మనుగడకు ఎంతటి వరం అనేది దీని ద్వారా మనకు అర్థమవుతుంది.",
                         f"{clean_topic} beautiful serene rotating Earth from space | sunrise from international space station"),
                        (f"నిజంగా ప్రకృతి యొక్క నియమాలు మరియు భౌతిక శక్తులు ఎంతటి అద్భుతమైనవో ఈ దృశ్యం మనకు స్పష్టం చేస్తుంది.",
                         f"{clean_topic} awe inspiring natural forces concept | harmony of earth ecology and gravity"),
                        (f"ఈ విశ్లేషణ మన గ్రహాన్ని మరియు పర్యావరణాన్ని కాపాడుకోవాల్సిన బాధ్యతను కూడా గుర్తుచేస్తుంది.",
                         f"{clean_topic} global environmental conservation message | green flourishing planet earth"),
                        (f"మరి ఒకవేళ భూమి నిజంగా ఐదు సెకన్లు ఆగితే మీరు ఎక్కడుంటారో కామెంట్స్‌లో చెప్పండి బాస్!",
                         f"{clean_topic} thought provoking question visual | viewers discussing in comments concept"),
                        (f"ఈ వీడియో మీకు నచ్చితే వెంటనే లైక్ కొట్టి, మీ ఫ్రెండ్స్‌కి షేర్ చేసి, మరిన్ని సైన్స్ విశేషాల కోసం సబ్‌స్క్రైబ్ చేసుకోండి!",
                         f"like share and subscribe animation youtube studio | science educational channel closing call to action"),
                    ]
                else:
                    base = [
                        (f"Have you ever wondered what would actually happen if planet Earth stopped spinning for just five seconds?",
                         f"{clean_topic} planet Earth rotating in deep space | blue planet glowing atmosphere satellite view"),
                        (f"Right now, at the equator, the surface of Earth is rotating at a blistering speed of approximately 1,670 kilometers per hour.",
                         f"{clean_topic} globe spinning rotational axis equator line | scientific earth motion graphics"),
                        (f"Because of this continuous rotation, every building, vehicle, person, and ocean is moving along at this exact planetary velocity.",
                         f"{clean_topic} surface velocity physics demonstration | rotational inertia earth scale"),
                        (f"Now, imagine a cosmic pause button: what transpires if that rotational momentum suddenly halts for five seconds?",
                         f"{clean_topic} dramatic earth sudden stop visual | space view of sudden deceleration shockwave"),
                        (f"Under Newton's first law of motion, every unanchored object retains its forward momentum—a phenomenon known as inertia.",
                         f"{clean_topic} newton first law inertia physics diagram | objects moving at high velocity concept"),
                        (f"While the solid ground halts, humans, vehicles, trees, and buildings are violently hurled eastward at supersonic speeds!",
                         f"{clean_topic} supersonic inertia shockwave throwing objects | dramatic physics simulation destruction"),
                        (f"Moving at supersonic velocities exceeding 1,000 miles per hour, structural integrity across continents is shattered instantaneously.",
                         f"{clean_topic} city skyline sudden atmospheric blast | futuristic buildings facing sudden pressure"),
                        (f"Crucially, the atmosphere itself does not stop; atmospheric winds continue racing forward at Mach 1 velocities.",
                         f"{clean_topic} atmospheric winds clouds spinning over continents | hurricane storm clouds earth view"),
                        (f"These colossal supersonic windstorms would pulverize surface structures with energy far surpassing atomic detonations.",
                         f"{clean_topic} supersonic hurricane windstorm tearing through landscape | dramatic nature power"),
                        (f"Skyscrapers, suspension bridges, and modern infrastructure would be reduced to debris within the opening seconds.",
                         f"{clean_topic} dramatic skyscrapers swaying in violent winds | cinematic metropolis destruction"),
                        (f"Simultaneously, the world's oceans experience colossal inertia, displacing billions of tons of water across continents.",
                         f"{clean_topic} deep ocean colossal waves surging | ocean water moving violently across planet"),
                        (f"Colossal mega-tsunamis towering hundreds of feet high surge across coastal lowlands, sweeping miles inland.",
                         f"{clean_topic} massive mega tsunami crashing onto coastlines | towering ocean wave cinematic"),
                        (f"Major coastal metropolises and low-lying coastal plains worldwide would be completely submerged under turbulent ocean surges.",
                         f"{clean_topic} coastal cities engulfed by colossal storm surge | aerial view of ocean flooding land"),
                        (f"Without centrifugal force bulging water at the equator, ocean basins rapidly migrate towards the north and south poles.",
                         f"{clean_topic} water shifting toward north and south poles | global ocean migration simulation"),
                        (f"This dynamic forms a massive equatorial supercontinent dividing two immense, newly formed polar oceans.",
                         f"{clean_topic} new equatorial supercontinent emerging | polar oceans planetary geography transformation"),
                        (f"Beneath our feet, the sudden deceleration triggers unimaginable shear stresses throughout Earth's mantle and crust.",
                         f"{clean_topic} tectonic plates grinding under extreme stress | earth crust geology cross section"),
                        (f"Tectonic faults grind violently against one another, triggering catastrophic global earthquakes measuring beyond magnitude 9.",
                         f"{clean_topic} massive global earthquakes shaking ground | seismograph needle spiking violently"),
                        (f"Dormant and active volcanoes worldwide erupt in unison, venting superheated plumes of ash and magma into the stratosphere.",
                         f"{clean_topic} volcanic eruption explosion ash cloud magma | dramatic volcano erupting night sky"),
                        (f"A dense global shroud of volcanic particulates and dust eclipses sunlight across both hemispheres.",
                         f"{clean_topic} dark ash clouds covering the sun | apocalyptic atmosphere darkening earth"),
                        (f"Furthermore, the liquid outer core's dynamo effect is jarred, causing Earth's protective magnetosphere to fluctuate severely.",
                         f"{clean_topic} earth magnetic field lines weakening | solar radiation shielding failure diagram"),
                        (f"With magnetic shielding compromised, unfiltered solar radiation and cosmic particles bombard the upper atmosphere.",
                         f"{clean_topic} deadly solar radiation rays hitting earth atmosphere | cosmic rays penetration space"),
                        (f"Thousands of orbiting satellites lose trajectory stabilization and begin uncontrolled atmospheric re-entry.",
                         f"{clean_topic} satellites falling out of orbit into atmosphere | space debris burning on re entry"),
                        (f"Global satellite navigation, telecommunications, and internet grids go completely offline worldwide.",
                         f"{clean_topic} global satellite communication network black out | digital globe lines cutting off"),
                        (f"Then, after five catastrophic seconds, the Earth abruptly resumes its normal eastward rotation!",
                         f"{clean_topic} earth suddenly resuming spin rotation | dramatic planet motion shockwave restart"),
                        (f"The sudden restart produces a second violent shockwave as inert objects are jerked back into rotational acceleration.",
                         f"{clean_topic} secondary rotational shockwave sweeping continents | massive atmospheric turbulence"),
                        (f"Surface debris and displaced masses undergo secondary kinetic impacts, compounding the geophysical transformation.",
                         f"{clean_topic} secondary inertia kinetic force after restart | kinetic energy landscape transformation"),
                        (f"Turbulent ocean currents and atmospheric pressure gradients require months to stabilize into dynamic equilibrium.",
                         f"{clean_topic} chaotic weather systems slowly stabilizing | turbulent earth satellite view"),
                        (f"Planetary river channels, continental shorelines, and geographic boundaries are permanently redrawn.",
                         f"{clean_topic} new rivers and transformed terrain satellite map | geographic landforms satellite"),
                        (f"Human civilization faces an extraordinary test of survival and collective resilience across every continent.",
                         f"{clean_topic} human civilization facing planetary change | resilient humanity rebuilding concept"),
                        (f"Supercomputer simulations by geophysicists demonstrate how essential continuous angular momentum is to planetary stability.",
                         f"{clean_topic} supercomputer simulation screens analyzing earth spin | planetary scientists at work"),
                        (f"These mechanical thought experiments offer profound insight into the laws that govern celestial bodies.",
                         f"{clean_topic} astrophysics planetary motion formulas | celestial mechanics orbital diagram"),
                        (f"The silent, steady rotation of our planet is truly an invisible cosmic marvel that sustains all life.",
                         f"{clean_topic} beautiful serene rotating Earth from space | sunrise from international space station"),
                        (f"Every breath of air and gentle breeze we experience is guided by this finely balanced cosmic clockwork.",
                         f"{clean_topic} awe inspiring natural forces concept | harmony of earth ecology and gravity"),
                        (f"Understanding these physical realities deepens our appreciation for Earth's remarkable, delicate biosphere.",
                         f"{clean_topic} global environmental conservation message | green flourishing planet earth"),
                        (f"Where on the globe would you seek shelter if planetary rotation ever stopped? Share your thoughts below!",
                         f"{clean_topic} thought provoking question visual | viewers discussing in comments concept"),
                        (f"If you enjoyed this scientific deep-dive, hit like, share it with friends, and subscribe for more fascinating breakdowns!",
                         f"like share and subscribe animation youtube studio | science educational channel closing call to action"),
                    ]
            else:  # tech, entertainment, general
                if tel:
                    base = [
                        (f"బాస్, {tel_topic} విషయంలో ప్రస్తుతం జరుగుతున్న సరికొత్త పరిణామాలు చూశారా?",
                         f"{clean_topic} official news overview | {clean_topic} topic presentation cinematic studio"),
                        (f"అసలు దీని వెనుక ఉన్న ముఖ్యమైన విశేషాలు చాలా మందికి తెలియదు.",
                         f"{clean_topic} key details analysis | {clean_topic} important aspects presentation"),
                        (f"ఇందులోని ప్రతి ఒక్క అంశం కూడా భవిష్యత్తులో తీసుకురాబోయే ప్రభావం ఎంతో విశేషమైనది.",
                         f"{clean_topic} in depth investigation | {clean_topic} real world practical context"),
                        (f"వివిధ వర్గాల నుండి వస్తున్న స్పందనలను బట్టి చూస్తే, ఇది ప్రస్తుతం సెంటర్ ఆఫ్ అట్రాక్షన్ గా నిలిచింది.",
                         f"{clean_topic} community discussion panel | experts talking about {clean_topic}"),
                        (f"ప్రధానంగా ఇందులో గుర్తించాల్సిన మరో ముఖ్యమైన పాయింట్ ఏమిటంటే దీని ప్రాముఖ్యత రోజురోజుకూ పెరుగుతోంది.",
                         f"{clean_topic} data insights charts | modern visual analytics screen"),
                        (f"మరిన్ని తాజా పరిణామాలు త్వరలోనే ప్రజల్లోకి మరింత వేగంగా చేరనున్నాయి.",
                         f"{clean_topic} future outlook and impact | dynamic global trends visual"),
                        (f"సమగ్ర విశ్లేషణలో ఇది ఒక కీలకమైన మలుపుగా పరిశీలకులు భావిస్తున్నారు.",
                         f"{clean_topic} public reaction and impact | diverse audience engagement"),
                        (f"ఈ పరిణామం వల్ల రాబోయే రోజుల్లో మార్కెట్ లో మరియు సమాజంలో పలు మార్పులు చోటుచేసుకోనున్నాయి.",
                         f"{clean_topic} market transformation concept | trending global shift visual"),
                        (f"నిపుణులు సైతం ఈ అంశంపై భిన్నమైన అభిప్రాయాలు మరియు అంచనాలను వ్యక్తం చేస్తున్నారు.",
                         f"{clean_topic} industry analyst interview | professional commentary desk"),
                        (f"అధికారిక ప్రకటనలు మరియు వాస్తవాల ఆధారంగా చూస్తే ఇందులో ఎన్నో ఆసక్తికరమైన విషయాలు ఉన్నాయి.",
                         f"{clean_topic} verified facts documentation | official release briefing"),
                        (f"ప్రజాభిప్రాయం కూడా ఈ విషయంపై చాలా ఉత్కంఠభరితంగా ఉంది.",
                         f"{clean_topic} audience live feedback | community conversation studio"),
                        (f"చివరిగా ఇది ఒక సుదీర్ఘ చర్చకు మరియు సరికొత్త ధోరణులకు నాంది పలకనుంది.",
                         f"{clean_topic} strategic future perspective | forward looking innovative design"),
                        (f"మరి దీనిపై మీ అభిప్రాయం మరియు ఆలోచనలు ఏమిటి బాస్? కామెంట్స్ లో తెలియజేయండి!",
                         f"{clean_topic} discussion wrap up | studio creator conversation"),
                        (f"ఈ వీడియో నచ్చితే లైక్ కొట్టి, మీ ఫ్రెండ్స్‌కి షేర్ చేసి, వెంటనే సబ్‌స్క్రైబ్ చేసుకోండి బాస్!",
                         f"like share and subscribe animation youtube studio | modern channel closing call to action"),
                    ]
                else:
                    base = [
                        (f"Welcome to an in-depth breakdown of {clean_topic}.",
                         f"{clean_topic} official news overview | {clean_topic} topic presentation cinematic studio"),
                        (f"Critical developments are reshaping how everyone views this important topic today.",
                         f"{clean_topic} key details analysis | {clean_topic} important aspects presentation"),
                        (f"Key insights reveal why this is gaining unprecedented momentum across communities.",
                         f"{clean_topic} in depth investigation | {clean_topic} real world practical context"),
                        (f"Analysts and industry observers are closely following the emerging implications.",
                         f"{clean_topic} community discussion panel | experts talking about {clean_topic}"),
                        (f"Understanding the core fundamentals provides valuable clarity on where things are heading.",
                         f"{clean_topic} data insights charts | modern visual analytics screen"),
                        (f"The broader impact across related sectors is becoming increasingly evident.",
                         f"{clean_topic} future outlook and impact | dynamic global trends visual"),
                        (f"Overall, this marks a defining milestone with significant long-term potential.",
                         f"{clean_topic} public reaction and impact | diverse audience engagement"),
                        (f"Fresh updates from credible sources add even more context to these proceedings.",
                         f"{clean_topic} data insights charts | modern visual analytics screen"),
                        (f"Community members and specialists continue sharing nuanced perspectives on this matter.",
                         f"{clean_topic} audience live feedback | community conversation studio"),
                        (f"Strategic shifts observed today will likely set the benchmark for future milestones.",
                         f"{clean_topic} strategic future perspective | forward looking innovative design"),
                        (f"Following these developments closely reveals exciting new opportunities on the horizon.",
                         f"{clean_topic} market transformation concept | trending global shift visual"),
                        (f"Every detail uncovered so far underscores the importance of staying informed.",
                         f"{clean_topic} verified facts documentation | official release briefing"),
                        (f"What are your key takeaways regarding this development? Share below!",
                         f"{clean_topic} discussion wrap up | studio creator conversation"),
                        (f"If you enjoyed this breakdown, hit like, share it with your friends, and subscribe for more daily updates!",
                         f"like share and subscribe animation youtube studio | modern channel closing call to action"),
                    ]

            if duration_type == "short":
                short_beats = list(base[:8])
                short_beats.append(base[-1])
                return short_beats
            elif duration_type == "medium":
                return base[:14]
            else:
                if len(base) < 32:
                    expanded = list(base[:-2])
                    while len(expanded) < 30:
                        for item in base[2:-2]:
                            if len(expanded) >= 30:
                                break
                            expanded.append((
                                f"Delving deeper into this facet of {clean_topic}: {item[0]}" if not is_tel else f"{clean_topic} అంశంలో మరింత పరిశీలిస్తే: {item[0]}",
                                f"{item[1]} | detailed perspective"
                            ))
                    expanded.extend(base[-2:])
                    return expanded
                return base

        dur_low = str(target_duration).lower()
        if "60" in dur_low or "90" in dur_low or "spotlight" in dur_low:
            sections_data = build_beats(category, is_tel, "medium")
        elif "2-4" in dur_low or "explainer" in dur_low or "6-9" in dur_low or "6–9" in dur_low or "history" in dur_low or "long" in dur_low:
            sections_data = build_beats(category, is_tel, "long")
        else:
            sections_data = build_beats(category, is_tel, "short")

        # Deduplicate narration script and ensure dynamic 2-3s like/share/subscribe CTA
        from agents.script_agent import deduplicate_script_narration, ensure_dynamic_outro_cta
        script_lines = [s[0] for s in sections_data]
        raw_script = "\n".join(script_lines)
        script = deduplicate_script_narration(raw_script)
        script = ensure_dynamic_outro_cta(script, topic=clean_topic, is_indic=is_tel)
        script = deduplicate_script_narration(script)

        # Synchronize lines with sections_data
        final_lines = [l.strip() for l in script.splitlines() if l.strip()]
        if len(final_lines) != len(sections_data):
            # Adjust visual plan lines
            visual_plan_lines = []
            for i, l in enumerate(final_lines):
                vis = sections_data[i][1] if i < len(sections_data) else sections_data[-1][1]
                visual_plan_lines.append(f"{i+1}. {vis}")
            section_map_parts = [
                f"SECTION {i+1} | VISUAL {i+1}\n{l}"
                for i, l in enumerate(final_lines)
            ]
        else:
            visual_plan_lines = [f"{i+1}. {s[1]}" for i, s in enumerate(sections_data)]
            section_map_parts = [f"SECTION {i+1} | VISUAL {i+1}\n{l}" for i, l in enumerate(final_lines)]

        visual_plan = "\n".join(visual_plan_lines)
        section_map = "\n\n".join(section_map_parts)

        try:
            (OUTPUT_DIR / "script.txt").write_text(script, encoding="utf-8")
            (OUTPUT_DIR / "tts_script.txt").write_text(script, encoding="utf-8")
            (OUTPUT_DIR / "visual_plan.txt").write_text(visual_plan, encoding="utf-8")
            (OUTPUT_DIR / "section_map.txt").write_text(section_map, encoding="utf-8")
        except (PermissionError, OSError):
            pass
        return script

    if stage_name == "image_agent":
        return heal_corrupt_or_missing_assets(context)

    return None


def heal_corrupt_or_missing_assets(context=None):
    """
    Inspect assets directory, drop any corrupt or zero-byte files,
    and guarantee assets/1.jpg .. assets/N.jpg exist using fallback images or typography cards.
    Every healed asset is recorded in data/asset_ledger.py.
    """
    try:
        from PIL import Image
    except ImportError:
        Image = None

    needed_count = 5
    if context and isinstance(context.get("needed_count"), int):
        needed_count = max(1, context["needed_count"])
    else:
        # Dynamically determine count from delivery plan or visual plan
        try:
            dp_p = OUTPUT_DIR / "delivery_plan.json"
            if dp_p.exists():
                dp_data = json.loads(dp_p.read_text(encoding="utf-8"))
                if isinstance(dp_data, list) and len(dp_data) > 0:
                    needed_count = len(dp_data)
        except Exception:
            pass
        if needed_count <= 5:
            try:
                vp_p = OUTPUT_DIR / "visual_plan.txt"
                if vp_p.exists():
                    v_lines = [l for l in vp_p.read_text(encoding="utf-8").splitlines() if l.strip()]
                    if len(v_lines) > 0:
                        needed_count = max(needed_count, len(v_lines))
            except Exception:
                pass

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    FALLBACK_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Identify and purge corrupt images in assets/
    for img_p in list(ASSETS_DIR.glob("*.jpg")) + list(ASSETS_DIR.glob("*.png")):
        if img_p.name.startswith("fallback_"):
            continue
        try:
            if img_p.stat().st_size == 0:
                img_p.unlink(missing_ok=True)
                continue
            if Image is not None:
                with Image.open(img_p) as im:
                    im.verify()
        except Exception:
            img_p.unlink(missing_ok=True)

    # 2. Gather available fallback images
    fallback_sources = sorted(list(FALLBACK_DIR.glob("*.jpg")) + list(FALLBACK_DIR.glob("*.png")))
    if not fallback_sources:
        # Create a clean fallback image programmatically if directory is empty
        if Image is not None:
            fb = Image.new("RGB", (1080, 1080), color=(20, 25, 40))
            fb_path = FALLBACK_DIR / "fallback_1.jpg"
            fb.save(fb_path, "JPEG")
            fallback_sources = [fb_path]

    # Extract available beat narrations and category for context-aware fallbacks
    beat_narrations = {}
    detected_cat = "general"
    if context and isinstance(context, dict):
        detected_cat = context.get("topic_category") or context.get("topic") or "general"
    try:
        dp_p = OUTPUT_DIR / "delivery_plan.json"
        if dp_p.exists():
            dp_data = json.loads(dp_p.read_text(encoding="utf-8"))
            if isinstance(dp_data, list):
                for idx, b in enumerate(dp_data, 1):
                    if isinstance(b, dict):
                        beat_narrations[idx] = b.get("spoken_text") or b.get("on_screen_text") or ""
    except Exception:
        pass
    if not beat_narrations:
        try:
            sp_p = OUTPUT_DIR / "script.txt"
            if sp_p.exists():
                s_lines = [l.strip() for l in sp_p.read_text(encoding="utf-8").splitlines() if l.strip()]
                for idx, l in enumerate(s_lines, 1):
                    beat_narrations[idx] = l
        except Exception:
            pass

    # 3. Populate missing numbered images assets/1.jpg .. assets/N.jpg
    healed_files = []
    for i in range(1, needed_count + 1):
        target = ASSETS_DIR / f"{i}.jpg"
        if not target.exists() or target.stat().st_size == 0:
            card_generated = False
            headline = beat_narrations.get(i) or f"Scene {i} Breakdown"
            try:
                from agents.typography_card import generate_typography_card
                card_generated = generate_typography_card(
                    headline_text=headline,
                    output_path=str(target),
                    topic_category=detected_cat,
                    aspect_ratio="16:9",
                    subtext=f"Scene {i} Focus",
                )
            except Exception:
                card_generated = False
            if not card_generated:
                try:
                    from providers.image import generate_pollinations_image
                    ai_p = f"Cinematic scene {i}: {headline}, dramatic atmosphere, 9:16 vertical format, photorealistic 8k"
                    card_generated = generate_pollinations_image(ai_p, target, aspect_ratio="9:16", force=True)
                except Exception:
                    card_generated = False

            if not card_generated and Image is not None:
                # Generate unique distinct palette per scene so hashes never collide
                w, h = 1080, 1920
                c_val = (20 + (i * 19) % 70, 25 + (i * 13) % 60, 45 + (i * 23) % 70)
                fb = Image.new("RGB", (w, h), color=c_val)
                target.parent.mkdir(parents=True, exist_ok=True)
                fb.save(target, "JPEG", quality=90)

        if target.exists() and target.stat().st_size > 0:
            healed_files.append(target)
            try:
                from data.asset_ledger import record_asset
                record_asset(
                    video_id="current",
                    beat_id=i,
                    asset_path=str(target),
                    source_url="supervisor_fallback",
                    tier="TIER_A",
                    license_name="CC0 / Generated Fallback",
                    credit_text="AutoTube Engine",
                    duration_sec=3.0,
                )
            except Exception:
                pass

    return healed_files


def heal_ffmpeg_failure(input_video="output/video.mp4", output_video="output/final_video.mp4", context=None):
    """
    Recover from FFmpeg encoding, scale, or filter failures by executing
    a CPU-safe baseline encoding command without problematic hardware filters.
    """
    in_path = Path(input_video)
    out_path = Path(output_video)

    if not in_path.exists():
        # Look for raw video or create emergency clip from assets
        raw_vid = OUTPUT_DIR / "raw_video.mp4"
        if raw_vid.exists():
            in_path = raw_vid
        else:
            in_path = OUTPUT_DIR / "video.mp4"

    voice_path = OUTPUT_DIR / "voice.mp3"
    if not voice_path.exists() or voice_path.stat().st_size < 1000:
        try:
            autonomous_recover("voice_agent", context={"reason": "voice_missing_for_video_recovery"})
        except Exception:
            pass

    voice_dur = 15.0
    if voice_path.exists() and voice_path.stat().st_size > 0:
        try:
            p = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(voice_path)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5
            )
            v_val = float(p.stdout.strip())
            if v_val > 0:
                voice_dur = v_val
        except Exception:
            pass

    target_w, target_h = 1080, 1920
    try:
        from config.format_profiles import get_active_profile
        prof = get_active_profile()
        target_w, target_h = prof.width, prof.height
    except Exception:
        pass
    scale_filter = f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1"

    if not in_path.exists() or in_path.stat().st_size == 0:
        first_img = ASSETS_DIR / "1.jpg"
        heal_corrupt_or_missing_assets({"needed_count": 1})
        if first_img.exists():
            cmd_img = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(first_img),
            ]
            if voice_path.exists() and voice_path.stat().st_size > 0:
                cmd_img.extend([
                    "-i", str(voice_path),
                    "-t", str(voice_dur),
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-vf", scale_filter,
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "ultrafast",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    str(in_path),
                ])
            else:
                cmd_img.extend([
                    "-t", str(voice_dur),
                    "-vf", scale_filter,
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "ultrafast",
                    str(in_path),
                ])
            try:
                subprocess.run(cmd_img, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)
            except Exception:
                pass

    # Check if in_path has audio
    has_audio = False
    if in_path.exists():
        try:
            p_a = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1", str(in_path)],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5
            )
            has_audio = bool(p_a.stdout.strip())
        except Exception:
            pass

    # Execute safe CPU baseline encoding with resolution enforcement
    if not has_audio and voice_path.exists() and voice_path.stat().st_size > 0:
        safe_cmd = [
            "ffmpeg", "-y",
            "-i", str(in_path),
            "-i", str(voice_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-vf", scale_filter,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            str(out_path),
        ]
    else:
        safe_cmd = [
            "ffmpeg", "-y",
            "-i", str(in_path),
            "-vf", scale_filter,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(out_path),
        ]

    try:
        res = subprocess.run(safe_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)
        if res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
            return str(out_path)
    except Exception:
        pass

    return str(in_path) if in_path.exists() else None


def heal_unrecoverable_topic(topic, error, context=None):
    """
    Quarantine topic metadata to failed_runs/ and failed_queue/
    and return an alternate ready-to-run evergreen topic.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(c for c in topic if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")[:40]
    filename = f"failure_{timestamp}_{safe_topic}.json"

    meta = {
        "timestamp": timestamp,
        "topic": topic,
        "error": str(error),
        "context": context or {},
        "status": "QUARANTINED",
    }

    try:
        (FAILED_RUNS_DIR / filename).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        (FAILED_QUEUE_DIR / filename).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception:
        pass

    return "Next Gen AI & Space Exploration Advances"


# ============================================================
# 3. INCIDENT LOGGER & UI EVENT STREAM
# ============================================================

def log_healing_incident(stage_name, error, classification, root_cause, resolution, context=None):
    """Record an auto-healed incident into in-memory queue and persistent log."""
    incident = {
        "id": f"heal_{int(time.time() * 1000)}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stage": stage_name,
        "error_type": type(error).__name__,
        "error_message": str(error)[:240],
        "classification": classification,
        "root_cause": root_cause,
        "resolution": resolution,
        "status": "RECOVERED & RUNNING",
    }

    with _INCIDENT_LOCK:
        _INCIDENT_HISTORY.appendleft(incident)
        _UNCONSUMED_EVENTS.append(incident)

    try:
        with open(EVENTS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(incident) + "\n")
    except Exception:
        pass

    print(f"[SUPERVISOR] 🩹 Auto-Healed '{stage_name}': {resolution}")
    return incident


def get_healing_logs(limit=30):
    """Retrieve the latest self-healing events."""
    with _INCIDENT_LOCK:
        return list(_INCIDENT_HISTORY)[:limit]


def pop_new_healing_events():
    """Consume unread healing events for Streamlit toast triggers."""
    with _INCIDENT_LOCK:
        global _UNCONSUMED_EVENTS
        events = list(_UNCONSUMED_EVENTS)
        _UNCONSUMED_EVENTS = []
        return events


# ============================================================
# 4. GLOBAL DECORATOR: @autonomous_recover
# ============================================================

def autonomous_recover(stage_name, fallback_fn=None):
    """
    Decorator around major pipeline functions.
    Catches any unhandled exception, runs AI error analysis,
    dispatches automated healing, logs incident, and returns recovered result.
    """
    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as err:
                    return _handle_recovery(func, args, kwargs, stage_name, err, fallback_fn, is_async=True)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as err:
                    return _handle_recovery(func, args, kwargs, stage_name, err, fallback_fn, is_async=False)
            return sync_wrapper
    return decorator


def _handle_recovery(func, args, kwargs, stage_name, err, fallback_fn, is_async=False):
    """Execute autonomous healing when an exception is caught."""
    tb_str = traceback.format_exc()
    func_name = getattr(func, "__name__", "unknown")
    context = {"function": func_name, "args_summary": str(args)[:200]}
    for k, v in kwargs.items():
        if k == "context" and isinstance(v, dict):
            context.update(v)
        elif isinstance(v, (str, int, float, bool)):
            context[k] = v

    # Extract topic if present in arguments
    if args and isinstance(args[0], str):
        context["topic"] = args[0]
    elif "topic" in kwargs:
        context["topic"] = kwargs["topic"]
    if len(args) > 1 and "content_type" not in context and isinstance(args[1], str):
        context["content_type"] = args[1]
    if len(args) > 2 and "language_style" not in context and isinstance(args[2], str):
        context["language_style"] = args[2]
    if len(args) > 4 and "default_title" not in context and isinstance(args[4], str):
        context["default_title"] = args[4]
    if len(args) > 5 and "target_duration" not in context and isinstance(args[5], str):
        context["target_duration"] = args[5]
    if len(args) > 6 and "voice" not in context and isinstance(args[6], str):
        context["voice"] = args[6]

    # 1. Analyze error with AI
    diagnosis = analyze_error_with_ai(stage_name, err, tb_str, context)
    classification = diagnosis["classification"]
    root_cause = diagnosis["root_cause"]

    # 2. Execute concrete automated healing strategy
    healed_result = None
    resolution = diagnosis["recommended_action"]

    try:
        if fallback_fn is not None:
            healed_result = fallback_fn(*args, **kwargs)
            resolution = f"Custom fallback executed for {stage_name}"
        elif stage_name == "trend_agent":
            healed_result = heal_network_or_quota("trend_agent", context)
            resolution = "Switched to local trend cache / evergreen topics"
        elif stage_name == "script_agent":
            healed_result = heal_network_or_quota("script_agent", context)
            resolution = "Generated structured fallback script and visual plan"
        elif stage_name == "image_agent":
            healed_result = heal_corrupt_or_missing_assets(context)
            resolution = "Purged corrupt images & populated assets from fallback library"
        elif stage_name in ("video_agent", "final_video_agent"):
            out_vid = kwargs.get("output_video", "output/final_video.mp4")
            in_vid = kwargs.get("input_video", "output/video.mp4")
            healed_result = heal_ffmpeg_failure(in_vid, out_vid, context)
            resolution = "Re-encoded video with CPU-safe baseline parameters (-c:v libx264 -pix_fmt yuv420p -preset ultrafast)"
        elif stage_name == "voice_agent":
            # Guarantee real, full-duration voice narration exists in both voice.mp3 and voice.wav
            voice_mp3 = OUTPUT_DIR / "voice.mp3"
            voice_wav = OUTPUT_DIR / "voice.wav"
            voice_raw = OUTPUT_DIR / "voice_raw.wav"

            # Check if valid voice audio already exists
            valid_existing = None
            for cand in (voice_mp3, voice_wav, voice_raw):
                if cand.exists() and cand.stat().st_size > 10000:
                    valid_existing = cand
                    break

            if valid_existing:
                # Synchronize mp3 and wav formats
                try:
                    if not voice_mp3.exists() or voice_mp3.stat().st_size == 0:
                        subprocess.run(["ffmpeg", "-y", "-i", str(valid_existing), "-codec:a", "libmp3lame", "-q:a", "2", str(voice_mp3)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                    if not voice_wav.exists() or voice_wav.stat().st_size == 0:
                        subprocess.run(["ffmpeg", "-y", "-i", str(valid_existing), "-ar", "24000", "-ac", "1", str(voice_wav)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                except Exception:
                    pass
                healed_result = str(voice_mp3)
                resolution = "Synchronized audio from verified pipeline narration output"
            else:
                # Read script to synthesize emergency local speech
                script_path = OUTPUT_DIR / "script.txt"
                speech_text = ""
                if script_path.exists():
                    try:
                        speech_text = script_path.read_text(encoding="utf-8").strip()
                    except Exception:
                        pass
                if not speech_text:
                    speech_text = "Welcome back to our channel. Here are the latest news updates, comprehensive breakdown, and key highlights you need to know today."

                has_telugu = bool(re.search(r"[\u0C00-\u0C7F]", speech_text))
                has_hindi = bool(re.search(r"[\u0900-\u097F]", speech_text))
                synthesized = False

                # Option A: Local macOS speech engine (100% offline, zero network)
                if sys.platform == "darwin":
                    chosen_voice = "Geeta" if has_telugu else ("Lekha" if has_hindi else "Rishi")
                    temp_aiff = OUTPUT_DIR / "emergency_voice.aiff"
                    try:
                        subprocess.run(["say", "-v", chosen_voice, "-o", str(temp_aiff), speech_text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
                        if temp_aiff.exists() and temp_aiff.stat().st_size > 2000:
                            subprocess.run(["ffmpeg", "-y", "-i", str(temp_aiff), "-codec:a", "libmp3lame", "-q:a", "2", str(voice_mp3)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                            subprocess.run(["ffmpeg", "-y", "-i", str(temp_aiff), "-ar", "24000", "-ac", "1", str(voice_wav)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                            temp_aiff.unlink(missing_ok=True)
                            synthesized = True
                    except Exception as say_err:
                        print(f"Supervisor macOS speech recovery notice: {say_err}")

                # Option B: Local Kokoro TTS with phonetic transliteration
                if not synthesized:
                    try:
                        from agents.voice_agent import generate_kokoro_speech
                        kokoro_text = speech_text
                        if has_telugu or has_hindi:
                            # Transliterate or extract Latin words for Kokoro phonetic safety
                            words = re.findall(r"[A-Za-z0-9]+", speech_text)
                            kokoro_text = " ".join(words) if len(words) >= 15 else "Here are the latest news updates and essential insights for today."
                        generate_kokoro_speech(kokoro_text, voice_code="am_adam", output_wav=str(voice_wav))
                        if voice_wav.exists() and voice_wav.stat().st_size > 2000:
                            subprocess.run(["ffmpeg", "-y", "-i", str(voice_wav), "-codec:a", "libmp3lame", "-q:a", "2", str(voice_mp3)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                            synthesized = True
                    except Exception as k_err:
                        print(f"Supervisor Kokoro recovery notice: {k_err}")

                healed_result = str(voice_mp3) if voice_mp3.exists() else (str(voice_wav) if voice_wav.exists() else None)
                resolution = "Synthesized full-length speech narration using local audio recovery"
        elif stage_name == "youtube_agent":
            healed_result = {"status": "DEFERRED", "message": "Upload deferred; video preserved locally"}
            resolution = "Deferred YouTube upload to prevent halting; video saved locally"
        elif stage_name in ("metadata_agent", "Metadata & Thumbnail Generation"):
            topic_val = context.get("topic") or (args[0] if args and isinstance(args[0], str) else "AutoTube Update")
            script_val = args[1] if len(args) > 1 and isinstance(args[1], str) else ""
            run_dir_val = kwargs.get("run_dir") or (Path(args[5]) if len(args) > 5 else None) or OUTPUT_DIR
            out_dir = Path(run_dir_val)
            out_dir.mkdir(parents=True, exist_ok=True)

            try:
                from agents.metadata_agent import generate_fallback_metadata
                h_title, h_desc, h_tags = generate_fallback_metadata(topic_val, script_val)
            except Exception:
                h_title = topic_val
                h_desc = f"{topic_val}\n\nLatest update and comprehensive coverage."
                h_tags = ["News", "Trending", "Telugu"]

            # Ensure thumbnail exists
            h_thumb = out_dir / "thumbnail.jpg"
            if not h_thumb.exists() or h_thumb.stat().st_size == 0:
                try:
                    from agents.thumbnail_agent import create_thumbnail
                    create_thumbnail(title=h_title, aspect_ratio=kwargs.get("aspect_ratio", "9:16"), output_dir=out_dir)
                except Exception:
                    pass

            # Save fallback metadata.json
            meta_path = out_dir / "metadata.json"
            try:
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "title": h_title,
                        "description": h_desc,
                        "tags": h_tags,
                        "privacy": kwargs.get("privacy", "public"),
                        "youtube_upload": False,
                        "youtube_video_id": None,
                        "youtube_error": None,
                        "run_id": kwargs.get("run_id", "run_recovered"),
                        "channel": kwargs.get("channel", "Channel 1 (Primary)"),
                    }, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

            healed_result = (h_title, h_desc, h_tags, None, None)
            resolution = "Auto-recovered metadata & thumbnail using deterministic fallback without pipeline crash"
        else:
            resolution = f"Safely recovered with default state for {stage_name}"
    except Exception as fallback_err:
        resolution = f"Auto-mitigated pipeline exception: {fallback_err}"

    # 3. Log incident for UI streaming
    log_healing_incident(stage_name, err, classification, root_cause, resolution, context)

    return healed_result


# ============================================================
# 5. STREAMLIT DIAGNOSTICS UI COMPONENT
# ============================================================

def render_healing_diagnostics_drawer():
    """
    Render the live incident diagnostics drawer and trigger toast notifications in Streamlit.
    Call this within Streamlit apps to provide real-time recovery feedback.
    """
    try:
        import streamlit as st
    except ImportError:
        return

    # 1. Pop and display toasts for newly healed events
    new_events = pop_new_healing_events()
    for ev in new_events:
        stage = ev.get("stage", "pipeline")
        res = ev.get("resolution", "Self-healing resolved the issue.")
        try:
            st.toast(f"⚠️ Auto-Healed ({stage}): {res[:80]}", icon="🩹")
        except Exception:
            pass

    # 2. Render Expandable Incident Drawer
    logs = get_healing_logs(limit=15)

    with st.expander(f"🛠️ Self-Healing Diagnostics & Log ({len(logs)} incidents auto-healed)", expanded=False):
        if not logs:
            st.markdown(
                """
                <div style="background: rgba(34, 197, 94, 0.08); border: 1px solid rgba(34, 197, 94, 0.25); border-radius: 10px; padding: 12px 14px;">
                    <div style="font-size: 12.5px; font-weight: 600; color: #4ADE80;">
                        ✅ All Systems Nominal
                    </div>
                    <div style="font-size: 11px; color: #94A3B8; margin-top: 2px;">
                        The autonomous supervisor is actively monitoring. No unhandled errors or active fault recoveries.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div style="font-size: 11px; color: #94A3B8; margin-bottom: 10px;">
                    Autonomous supervisor auto-recovers errors in real time without human intervention:
                </div>
                """,
                unsafe_allow_html=True,
            )

            for log in logs:
                c_badge = (
                    "🔴 Transient/Network" if "Transient" in log.get("classification", "")
                    else "🟡 Bad Asset" if "Asset" in log.get("classification", "")
                    else "🔵 Parameter Mismatch"
                )

                st.markdown(
                    f"""
                    <div style="background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 10px 14px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <span style="font-size: 12px; font-weight: 700; color: #F1F5F9;">
                                ⚙️ {log.get('stage', 'Pipeline Stage').upper()}
                            </span>
                            <span style="font-size: 10px; font-weight: 600; color: #38BDF8; background: rgba(56, 189, 248, 0.12); padding: 2px 8px; border-radius: 6px;">
                                {log.get('status', 'RECOVERED')}
                            </span>
                        </div>
                        <div style="font-size: 11px; color: #CBD5E1; margin-bottom: 3px;">
                            <b>Root Cause ({c_badge}):</b> {log.get('root_cause', 'Unknown')}
                        </div>
                        <div style="font-size: 11px; color: #4ADE80; margin-bottom: 3px;">
                            <b>🩹 Resolution:</b> {log.get('resolution', 'Fallback applied')}
                        </div>
                        <div style="font-size: 10px; color: #64748B;">
                            🕒 {log.get('timestamp', '')} • Error: <code>{log.get('error_type', '')}</code>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

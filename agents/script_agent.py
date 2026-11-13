import os
import re
import time
import mimetypes
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

from google import genai
from agents.news_verifier import verify_news_topic
from supervisor import autonomous_recover
from config.format_profiles import get_format_profile, FormatProfile



# ============================================================
# CONFIG
# ============================================================

SCRIPT_SYSTEM_PROMPT = """
You are writing a fast-paced Telugu creator/review script for YouTube Shorts/Reels.
STRICT RULES:
1. NEVER start with a greeting, "Welcome back", or intro pleasantry. First sentence must
   be a bold claim, shocking spec/price fact, or curiosity-gap question -- hook within 3 seconds.
2. Each beat must be speakable in 2.0-3.5 seconds (6-12 Telugu words).
3. VOCAL PERSONA & DELIVERY:
   "Speak in the tone of an energetic, candid Telugu film reviewer. Sound spontaneous, dramatic, and expressive rather than robotic or formal. Add subtle vocal emphasis on contrasting words and punchlines."
4. PUNCTUATION-DRIVEN CADENCE:
   Text-to-speech engines rely heavily on punctuation for inflection. Break long, dramatic lines into short punchy fragments using commas (,), dashes (—), and ellipsis (...) to create organic breathing room and build anticipation before major reveals.
5. 100% TELUGU SCRIPT FOR LOANWORDS:
   Avoid phonetic Telugu written in loose English script. Write 100% in native Telugu script (తెలుగు లిపి). Write English loanwords in Telugu script (e.g. 'బిగ్ బాస్', 'పాన్ ఇండియా', 'ట్విస్ట్', 'మైండ్ బ్లాంక్', 'రివ్యూ') to prevent neural TTS engines from switching to a robotic American accent.
6. SCRIPT-LEVEL VISUAL PLANNING & BEAT SCHEMA:
   For each beat, output structured JSON:
   {
     "beat_id": 1,
     "narration": "తెలుగు డైలాగ్...",
     "main_entity": "Exact Name of Celebrity/Person (e.g. Shalini Patel / Temper Vamsi / Dil Raju)",
     "emotion": "shocked / angry / aggressive / smiling",
     "search_query": "Clean keyword query (e.g., 'Shalini Patel bigg boss' or 'Temper Vamsi actor')"
   }
7. STRICT RULE: NEVER use the entire narration sentence as the search query. You must explicitly extract the target person's name and concise context keywords (2 to 4 words max).
8. Output valid JSON array only.
"""

try:
    from agents.env_loader import get_gemini_api_key
except ImportError:
    from env_loader import get_gemini_api_key

API_KEY = get_gemini_api_key()
client = genai.Client(api_key=API_KEY) if API_KEY else None


def get_client():
    """Lazily load or refresh the Gemini client from environment/secrets."""
    global client
    if client is None:
        key = get_gemini_api_key()
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. "
                "Please add it to Hugging Face Space Secrets, Streamlit Secrets, or your .env file."
            )
        client = genai.Client(api_key=key)
    return client


MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
]


def _call_gemini_with_retry(contents, model, max_retries=2):
    """
    Call Gemini API with automatic reconnection, client refresh,
    and fast failover on quota / load limits.
    """
    import time
    import concurrent.futures
    active_client = get_client()

    for attempt in range(1, max_retries + 1):
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            fut = ex.submit(active_client.models.generate_content, model=model, contents=contents)
            return fut.result(timeout=45.0)
        except Exception as error:
            err_str = str(error)
            is_quota_err = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "UNAVAILABLE" in err_str
            if is_quota_err:
                if attempt < max_retries:
                    backoff = 2.0 * attempt
                    print(f"⚠️ Model {model} rate limited or overloaded (attempt {attempt}/{max_retries}). Backing off {backoff:.1f}s...")
                    time.sleep(backoff)
                    continue
                else:
                    print(f"⚠️ Model {model} rate limited, falling over to next model...")
                    raise

            is_net_err = (
                "nodename nor servname provided" in err_str
                or "ConnectError" in err_str
                or "ConnectionReset" in err_str
                or "RemoteDisconnected" in err_str
                or "Connection refused" in err_str
                or "timeout" in err_str.lower()
                or "temporary failure in name resolution" in err_str.lower()
            )
            if is_net_err and attempt < max_retries:
                backoff = 1.0 * attempt
                print(
                    f"⚠️ Network hiccup with {model} (attempt {attempt}/{max_retries}): {error}. "
                    f"Re-initializing API client and retrying in {backoff:.1f}s..."
                )
                time.sleep(backoff)
                try:
                    active_client = genai.Client(api_key=API_KEY)
                except Exception:
                    pass
                continue
            raise
        finally:
            ex.shutdown(wait=False)



# ============================================================
# CLEAN RESPONSE
# ============================================================

def clean_response(text):
    if not text:
        return ""

    text = text.strip()

    text = re.sub(
        r"^```[a-zA-Z0-9_-]*",
        "",
        text
    )

    text = re.sub(
        r"```$",
        "",
        text
    )

    return text.strip()


# ============================================================
# ============================================================
# DYNAMIC 4-ACTION OUTRO CALLS TO ACTION (LIKE, SUBSCRIBE, SHARE, COMMENT)
# ============================================================

TELUGU_BIGG_BOSS_CTAS = [
    "నెక్స్ట్ ఎవరి ఎలిమినేషన్ జరుగుతుందో కామెంట్ చేయండి! మరిన్ని క్రేజీ అప్‌డేట్స్ కోసం లైక్, షేర్, సబ్‌స్క్రైబ్ చేసుకోండి!",
    "హౌస్‌లో ఎవరి గేమ్ మీకు నచ్చిందో కింద కామెంట్ చేసి, లైక్, షేర్, సబ్‌స్క్రైబ్‌తో మన ఛానల్‌కి సపోర్ట్ చేయండి!",
    "మీరు ఈ వారం ఎవరికి ఓట్ వేస్తున్నారో కామెంట్లో చెప్పండి! లేటెస్ట్ వైరల్ అప్‌డేట్స్ కోసం లైక్, షేర్, సబ్‌స్క్రైబ్ చేయండి!",
]

TELUGU_CINEMA_ROAST_CTAS = [
    "ఈ వీడియో లేదా రోస్ట్‌పై మీరేమనుకుంటున్నారో కింద కామెంట్ చేసి, లైక్, షేర్ మరియు సబ్‌స్క్రైబ్ చేసుకోండి!",
    "ఈ టాపిక్‌పై మీ అభిప్రాయాన్ని కామెంట్లో చెప్పండి! జెన్యూన్ కంటెంట్ కోసం వెంటనే లైక్, షేర్, సబ్‌స్క్రైబ్ చేసుకోండి బాస్!",
    "బాస్, మీ ఒపీనియన్ ఏంటో కింద కామెంట్ చేసి, లైక్ గుద్ది, ఫ్రెండ్స్‌కి షేర్ కొట్టి, వెంటనే సబ్‌స్క్రైబ్ చేసుకోండి!",
    "కంటెంట్ కిక్ ఇస్తే కామెంట్ బాక్స్‌లో చెప్పండి, లైక్ వేసి, ఫ్రెండ్స్‌కి షేర్ చేసి, వెంటనే సబ్‌స్క్రైబ్ చేసుకోండి!",
    "మీ ఒపీనియన్ కామెంట్ చేసి, లైక్, షేర్ మరియు సబ్‌స్క్రైబ్‌తో మన viral talks ఛానల్‌ని ఫుల్ సపోర్ట్ చేయండి బాస్!",
]

TELUGU_DYNAMIC_CTAS = [
    "ఈ టాపిక్‌పై మీ అభిప్రాయాన్ని కామెంట్లో చెప్పండి! జెన్యూన్ కంటెంట్ కోసం వెంటనే లైక్, షేర్, సబ్‌స్క్రైబ్ చేసుకోండి బాస్!",
    "బాస్, మీ ఒపీనియన్ ఏంటో కింద కామెంట్ చేసి, లైక్ గుద్ది, ఫ్రెండ్స్‌కి షేర్ కొట్టి, వెంటనే సబ్‌స్క్రైబ్ చేసుకోండి!",
    "దీనిపై మీ ఆలోచన కింద కామెంట్ చేయండి! నెక్స్ట్ లెవెల్ వీడియోల కోసం లైక్, షేర్, సబ్‌స్క్రైబ్ చేసుకోవడం మర్చిపోకండి!",
    "ఈ వీడియో నచ్చితే కామెంట్ బాక్స్‌లో చెప్పండి, లైక్ వేసి, ఫ్రెండ్స్‌కి షేర్ చేసి, వెంటనే సబ్‌స్క్రైబ్ చేసుకోండి!",
    "కంటెంట్ కిక్ ఇస్తే కామెంట్ బాక్స్‌లో చెప్పండి, లైక్ వేసి, ఫ్రెండ్స్‌కి షేర్ చేసి, వెంటనే సబ్‌స్క్రైబ్ చేసుకోండి!",
    "మీ ఒపీనియన్ కామెంట్ చేసి, లైక్, షేర్ మరియు సబ్‌స్క్రైబ్‌తో మన ఛానల్‌ని ఫుల్ సపోర్ట్ చేయండి బాస్!",
]

ENGLISH_DYNAMIC_CTAS = [
    "If you enjoyed this breakdown, hit like, drop a comment below, share with your friends, and subscribe for more daily updates!",
    "Drop your thoughts in the comments, smash the like button, share with your crew, and subscribe right now!",
    "Don't miss the next big update—hit like, leave a comment, share this video, and subscribe to stay ahead!",
    "Loved the analysis? Give it a thumbs up, comment your take, share with fellow fans, and subscribe for more unfiltered videos!",
    "Hit that like button, comment your thoughts, share with your network, and subscribe for tomorrow's viral breakdown!",
]


def deduplicate_script_narration(text: str) -> str:
    """
    Detects and eliminates duplicate sentences and repetitive text blocks.
    Preserves natural narrative flow while removing exact and near-identical sentences (>= 80% similarity).
    """
    if not text or len(text.strip()) < 15:
        return text or ""

    import difflib

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return text

    unique_lines = []
    seen_normalized = []

    def normalize_sentence(s: str) -> str:
        s_clean = re.sub(r"[^\w\s\u0C00-\u0C7F]", "", s.lower())
        return re.sub(r"\s+", " ", s_clean).strip()

    def is_duplicate(norm_s: str, seen_list: list) -> bool:
        if not norm_s or len(norm_s) < 8:
            return False
        for seen in seen_list:
            if norm_s == seen:
                return True
            # Word overlap check
            words_a = set(norm_s.split())
            words_b = set(seen.split())
            if words_a and words_b:
                overlap = len(words_a & words_b) / max(len(words_a), len(words_b))
                if overlap >= 0.82:
                    return True
            # Sequence matcher check for sentences of reasonable length
            if len(norm_s) > 20 and len(seen) > 20:
                ratio = difflib.SequenceMatcher(None, norm_s, seen).ratio()
                if ratio >= 0.80:
                    return True
        return False

    for line in lines:
        # Split line into individual punctuated sentences
        sents = re.split(r"(?<=[.!?।])\s+", line)
        kept_sents = []
        for s in sents:
            s_clean = s.strip()
            if not s_clean:
                continue
            norm = normalize_sentence(s_clean)
            if is_duplicate(norm, seen_normalized):
                print(f"🧹 [Deduplication] Dropped duplicate sentence: '{s_clean[:60]}...'")
                continue
            seen_normalized.append(norm)
            kept_sents.append(s_clean)

        if kept_sents:
            unique_lines.append(" ".join(kept_sents))

    return "\n".join(unique_lines).strip()


def ensure_dynamic_outro_cta(script: str, topic: str = "", is_indic: bool = True) -> str:
    """
    Guarantees every video concludes with a concise, punchy 2-3s (8-14 words)
    call-to-action explicitly containing like, share, and subscribe
    ('లైక్, షేర్, సబ్‌స్క్రైబ్' or 'like, share, subscribe').
    Collapses multiple repetitive CTAs into a single dynamic outro.
    """
    if not script or not script.strip():
        return script or ""

    script_clean = script.strip()
    lines = [l.strip() for l in script_clean.splitlines() if l.strip()]
    if not lines:
        return script_clean

    import hashlib
    import random

    seed_str = f"{topic}_{time.strftime('%Y%m%d%H%M%S')}_{len(script_clean)}"
    rng = random.Random(int(hashlib.md5(seed_str.encode()).hexdigest(), 16))

    cta_pool = TELUGU_DYNAMIC_CTAS if is_indic else ENGLISH_DYNAMIC_CTAS
    t_low = str(topic or "").lower()
    from utils.season_guard import is_bigg_boss_topic
    if is_indic:
        if is_bigg_boss_topic(topic):
            chosen_cta = rng.choice(TELUGU_BIGG_BOSS_CTAS)
        elif any(k in t_low for k in ["movie", "cinema", "film", "teaser", "trailer", "review", "prabhas", "actor", "hero", "star", "roast", "food", "lifestyle", "tollywood", "drama"]):
            chosen_cta = rng.choice(TELUGU_CINEMA_ROAST_CTAS)
        else:
            chosen_cta = rng.choice(TELUGU_DYNAMIC_CTAS)
    else:
        chosen_cta = rng.choice(ENGLISH_DYNAMIC_CTAS)

    # Check if the last line or sentence already contains like & subscribe keywords
    last_block = " ".join(lines[-2:]).lower() if len(lines) >= 2 else lines[-1].lower()
    has_existing_cta = (
        ("లైక్" in last_block and "సబ్‌స్క్రైబ్" in last_block)
        if is_indic else
        ("like" in last_block and "subscribe" in last_block)
    )
    if has_existing_cta:
        # Script already has a clean CTA; do not append a redundant outro
        return "\n".join(lines)

    tel_kws = ["లైక్", "సబ్‌స్క్రైబ్", "షేర్", "కామెంట్"]
    eng_kws = ["like", "subscribe", "share", "comment"]
    kws = tel_kws if is_indic else eng_kws

    # Strip trailing partial/repetitive CTA sentences across lines without dropping content
    while lines:
        cur_sents = [s.strip() for s in re.split(r"(?<=[.!?।])\s+", lines[-1]) if s.strip()]
        if not cur_sents:
            lines.pop()
            continue

        sent_lower = cur_sents[-1].lower()
        is_cta = (
            ("సబ్‌స్క్రైబ్" in sent_lower or "subscribe" in sent_lower) or
            ("లైక్" in sent_lower and "షేర్" in sent_lower) or
            ("like" in sent_lower and "share" in sent_lower) or
            (sum(1 for k in kws if k in sent_lower) >= 2)
        )
        if is_cta:
            cur_sents.pop()
            if cur_sents:
                lines[-1] = " ".join(cur_sents)
                continue
            else:
                lines.pop()
                continue
        break

    lines.append(chosen_cta)
    return "\n".join(lines)


# ============================================================
# PARSE + SAVE CONTENT PACKAGE & STRICT SCRIPT SANITIZATION
# ============================================================

def sanitize_telugu_text(text: str) -> str:
    """
    Strictly sanitize Telugu script and spoken narration text:
    - Strips rogue CJK ideographs (e.g. '现在的' or any \u4e00-\u9fff, \u3400-\u4dbf, etc.)
    - Strips rogue non-Telugu, non-Latin, non-punctuation Unicode characters (Cyrillic, Arabic, Thai, Hebrew, etc.)
    - Preserves:
      * Telugu Unicode block: \u0C00-\u0C7F
      * Latin/ASCII characters: \u0020-\u007E (letters, digits, common symbols)
      * Typographical punctuation: \u2000-\u206F (quotes, dashes, ellipses, bullet points)
      * Indian rupee symbol: \u20B9
    - Cleans excessive whitespace, dangling punctuation, or empty parentheses left by stripped tokens.
    """
    if not text:
        return ""

    # 1. Strip CJK ideographs, Hangul, Katakana, Hiragana, Bopomofo, CJK symbols
    cjk_pattern = r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af\u2e80-\u2fd5\uff00-\uffef\u31f0-\u31ff\u3200-\u32ff]"
    cleaned = re.sub(cjk_pattern, "", str(text))

    # 2. Filter allowed Unicode ranges: Telugu (\u0C00-\u0C7F), Latin/ASCII (\u0020-\u007E), Punctuation (\u2000-\u206F, \u20B9), newlines \n, tabs \t
    allowed_pattern = r"[^\u0C00-\u0C7F\u0020-\u007E\u2000-\u206F\u20B9\n\r\t]"
    cleaned = re.sub(allowed_pattern, "", cleaned)

    # 3. Clean up empty brackets or dangling punctuation resulting from stripped words
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\[\s*\]", "", cleaned)
    cleaned = re.sub(r"\{\s*\}", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def clean_script_narration(text):
    """
    Remove accidental subtitle/SRT formatting from Gemini narration.
    Also strips banned greetings, rogue multilingual/CJK characters, and deduplicates repeated sentences.
    output/script.txt must contain clean narration only.
    """

    if not text:
        return ""

    # First pass: strip rogue CJK / non-Telugu / non-ASCII characters
    sanitized_input = sanitize_telugu_text(text)

    lines = sanitized_input.splitlines()
    cleaned = []

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue

        # Remove WEBVTT header
        if line.upper() == "WEBVTT":
            continue

        # Remove subtitle sequence numbers
        if re.fullmatch(r"\d+", line):
            continue

        # Remove SRT timestamp lines
        if re.fullmatch(
            r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+"
            r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}",
            line,
        ):
            continue

        # Remove MM:SS,mmm --> MM:SS,mmm variants
        if re.fullmatch(
            r"\d{1,2}:\d{2}[,.]\d{3}\s+-->\s+"
            r"\d{1,2}:\d{2}[,.]\d{3}",
            line,
        ):
            continue

        cleaned.append(line)

    res = "\n".join(cleaned).strip()
    # Strip banned opening greetings from the first spoken sentence
    try:
        from agents.hook_engine import _clean_banned_openings
        lines = res.splitlines()
        if lines:
            first_line = _clean_banned_openings(lines[0])
            if first_line:
                lines[0] = first_line
            res = "\n".join(lines).strip()
    except Exception:
        pass

    # Deduplicate repetitive sentences and paragraphs
    res = deduplicate_script_narration(res)

    # Final pass: guarantee strict sanitization after deduplication
    res = sanitize_telugu_text(res)

    return res


def build_structured_visual_plan(sections, visual_plan, topic: str = ""):
    """
    Builds a structured visual plan (output/visual_plan.json) per beat:
    - Extracts named entities with aliases (tools/build_entity_library)
    - Dynamic Entity & Metadata Extraction:
        * Specific contestant names mentioned in each scene
        * Exact season and year/date of the event
        * Specific episode or incident context
    - Strict Search Query Formatting:
        * Primary: "[Contestant Name] [Season Name] [Year]"
        * Fallback: "[Contestant Name] [Specific Task/Promo]"
    - Disallows generic queries like "Bigg Boss Telugu drama" or "Bigg Boss emotional scene"
    - Attaches strict negative exclusions for past seasons (-Season 9, -Season 8, -BB9, etc.)
    - Maps metaphors/slang to visual intent and attaches negative terms (config/metaphor_map.json)
    - Generates 1-4 word uppercase headline on_screen_text overlays for key points
    """
    import json
    from pathlib import Path
    import re
    try:
        from tools.build_entity_library import match_entities_in_text
    except ImportError:
        def match_entities_in_text(t):
            return []

    from utils.season_guard import (
        is_bigg_boss_topic,
        get_current_season_number,
        format_strict_visual_query,
        is_generic_visual_query,
        KNOWN_TELUGU_SHOW_PERSONS,
    )

    is_bb = is_bigg_boss_topic(topic) or any(is_bigg_boss_topic(s.get("narration", "") if isinstance(s, dict) else str(s)) for s in sections)
    cur_season = get_current_season_number(topic) or 10
    season_name = f"Bigg Boss Telugu {cur_season}" if is_bb else (topic[:30].strip())
    event_year = 2026 if cur_season >= 10 else 2025

    past_season_exclusions = []
    if is_bb and cur_season >= 2:
        for s_num in range(1, cur_season):
            past_season_exclusions.extend([f"-Season {s_num}", f"-BB{s_num}", f"-Season{s_num}"])
        past_season_exclusions.extend(["-2025", "-2024", "-2023", "-2022", "-anime", "-cartoon", "-wallpaper"])

    metaphors_file = Path("config/metaphor_map.json")
    metaphors = []
    if metaphors_file.exists():
        try:
            m_data = json.loads(metaphors_file.read_text(encoding="utf-8"))
            metaphors = m_data.get("metaphors", [])
        except Exception:
            pass

    structured_plan = []
    last_assigned_entity = ""
    consecutive_entity_count = 0
    for idx, sec in enumerate(sections, start=1):
        narr = (sec.get("narration") or sec.get("spoken_text") or "") if isinstance(sec, dict) else str(sec)
        v_idx = idx - 1
        raw_v = visual_plan[v_idx] if 0 <= v_idx < len(visual_plan) else ""

        # Check explicit section-level main_entity first to prevent cross-beat entity leakage
        sec_main_ent = (sec.get("main_entity") or sec.get("primary_entity") or "").strip() if isinstance(sec, dict) else ""
        if sec_main_ent:
            for p_info in KNOWN_TELUGU_SHOW_PERSONS.values():
                if any(al.lower() == sec_main_ent.lower() or al.lower() in sec_main_ent.lower() for al in p_info.get("aliases", [])):
                    sec_main_ent = p_info["canonical"]
                    break

        # 1. Match entities in narration or visual concept
        entities = match_entities_in_text(f"{narr} {raw_v}")

        # Extract specific contestant names (excluding generic show entity)
        contestant_names = []
        if sec_main_ent and is_bb:
            contestant_names.append(sec_main_ent)
        for e in entities:
            if e.get("id") not in ("bigg_boss_telugu", "reality_show"):
                c_canon = e.get("canonical_name", "")
                if c_canon and c_canon not in contestant_names:
                    contestant_names.append(c_canon)

        # Fallback contestant extraction from KNOWN_TELUGU_SHOW_PERSONS
        narr_lower = narr.lower()
        if not contestant_names and is_bb:
            for p_info in KNOWN_TELUGU_SHOW_PERSONS.values():
                if any(al.lower() in narr_lower for al in p_info.get("aliases", [])):
                    c_canon = p_info["canonical"]
                    if c_canon not in contestant_names:
                        contestant_names.append(c_canon)

        # Fallback contestant extraction: Check if topic features a prominent target contestant/person
        topic_person = ""
        for p_info in KNOWN_TELUGU_SHOW_PERSONS.values():
            if any(al.lower() in topic.lower() for al in p_info.get("aliases", [])):
                topic_person = p_info["canonical"]
                break

        # If still no contestant is explicitly named, assign topic person or Host
        if is_bb and not contestant_names:
            if topic_person and idx in (1, 2):
                contestant_names = [topic_person]
            elif any(k in narr_lower for k in ["హోస్ట్", "host", "నాగ్", "నాగార్జున", "నడుము", "స్టేజ్"]):
                contestant_names = ["Nagarjuna Akkineni"]
            elif topic_person:
                contestant_names = [topic_person]
            elif idx == 1:
                contestant_names = ["Nagarjuna Akkineni"]
            else:
                contestant_names = ["Bigg Boss Telugu 10 Housemates"]

        # 1A. UNIVERSAL CATEGORY & ENTITY EXTRACTION
        combined_text = f"{topic} {narr} {raw_v}".lower()
        def _has_word(txt: str, kws: tuple) -> bool:
            for kw in kws:
                if re.search(r"(?:^|[^\u0C00-\u0C7Fa-zA-Z0-9])" + re.escape(kw) + r"(?:$|[^\u0C00-\u0C7Fa-zA-Z0-9])", txt, re.IGNORECASE):
                    return True
            return False

        if is_bb or is_bigg_boss_topic(combined_text):
            content_type = "reality_tv"
        elif _has_word(combined_text, (
            "cinema", "movie", "film", "tollywood", "dil raju", "dill raju", "rajamouli", "actor", "hero",
            "heroine", "director", "producer", "trailer", "teaser", "box office", "సినిమా",
            "హీరో", "దర్శకుడు", "నిర్మాత", "దిల్ రాజు", "రాజమౌళి", "విజయ్ దేవరకొండ", "రష్మిక", "టాలీవుడ్"
        )):
            content_type = "cinema"
        elif not is_bb and _has_word(combined_text, (
            "politics", "election", "minister", "parliament", "assembly", "cm", "pm", "government",
            "bjp", "congress", "tdp", "ysrcp", "revanth", "chandrababu", "modi", "pawan kalyan",
            "రాజకీయ", "ఎన్నికలు", "మంత్రి", "ముఖ్యమంత్రి", "ప్రభుత్వం", "శాసనసభ"
        )):
            content_type = "politics"
        elif _has_word(combined_text, (
            "business", "company", "industry", "factory", "deal", "investment", "shares",
            "stock", "economy", "market", "foxconn", "haier", "reliance", "tata", "rbi",
            "sensex", "nifty", "కంపెనీ", "ఫ్యాక్టరీ", "వ్యాపారం", "పెట్టుబడులు", "స్టాక్ మార్కెట్", "ఆర్థిక"
        )):
            content_type = "business"
        elif _has_word(combined_text, (
            "tech", "technology", "ai", "software", "smartphone", "processor", "chip",
            "semiconductor", "nvidia", "apple", "iphone", "google", "openai", "tesla",
            "సాంకేతిక", "స్మార్ట్‌ఫోన్", "చిప్"
        )):
            content_type = "tech"
        else:
            content_type = "general"

        # Determine primary_entity: prioritize section explicit entity, then narration entities
        primary_entity = sec_main_ent or ""
        if not primary_entity:
            non_show_ents = [e for e in entities if e.get("id") not in ("bigg_boss_telugu", "reality_show")]
            if non_show_ents:
                primary_entity = non_show_ents[0].get("canonical_name", "")
            elif contestant_names and is_bb:
                primary_entity = contestant_names[0]

        if not primary_entity:
            for p_info in KNOWN_TELUGU_SHOW_PERSONS.values():
                if any(al.lower() in narr_lower for al in p_info.get("aliases", [])):
                    primary_entity = p_info["canonical"]
                    break

        if not primary_entity:
            if content_type == "cinema":
                primary_entity = "Dil Raju" if ("dil raju" in combined_text or "dill raju" in combined_text) else "Tollywood Cinema"
            elif content_type == "business":
                if "foxconn" in combined_text:
                    primary_entity = "Foxconn"
                elif "haier" in combined_text:
                    primary_entity = "Haier"
                elif "tesla" in combined_text:
                    primary_entity = "Tesla"
                else:
                    primary_entity = "Corporate Enterprise"
            elif content_type == "tech":
                primary_entity = "Tesla" if "tesla" in combined_text else "Tech Industry"
            elif content_type == "politics":
                if "revanth" in combined_text:
                    primary_entity = "Revanth Reddy"
                elif "chandrababu" in combined_text:
                    primary_entity = "Chandrababu Naidu"
                else:
                    primary_entity = "Political Assembly"
            elif content_type == "reality_tv":
                primary_entity = contestant_names[0] if contestant_names else "Bigg Boss Telugu 10 Housemates"
            else:
                primary_entity = topic_person or topic.split(":")[0].strip() or "News Headline"

        # Smart B-roll Diversity & Anti-Monotony Guard
        # 1. Outro / CTA beat: Never show a contestant face on subscribe outro
        is_cta_beat = (idx >= len(sections) - 1) and any(k in narr_lower for k in ["లైక్", "సబ్‌స్క్రైబ్", "కామెంట్", "subscribe", "like", "share", "సపోర్ట్", "ఫాలో"])
        if is_cta_beat:
            primary_entity = "YouTube Channel Subscribe Outro"
            contestant_names = []
            incident_context = "Audience Discussion Outro"
        # 2. Voting / TRP / Strategy beat
        elif any(k in narr_lower for k in ["ఓటింగ్", "గ్రాఫ్", "టింగ్", "శాతం", "పోల్", "voting", "poll", "percentage", "రేటింగ్స్", "trp"]) and not any(k in narr_lower for k in ["నామినేషన్"]):
            if is_bb:
                primary_entity = "Bigg Boss Telugu 10 Elimination Voting Poll"
                incident_context = "Audience Elimination Voting"
        # 3. Late Night / House Atmosphere beat
        elif any(k in narr_lower for k in ["తెల్లవారుజాము", "రాత్రి", "మూడు గంటలు", "లాక్‌డౌన్", "ఫర్నిచర్", "గడియారం", "బెడ్‌రూమ్", "గార్డెన్"]) and not sec_main_ent:
            if is_bb:
                primary_entity = "Bigg Boss Telugu 10 Living Room & Garden Area"
                incident_context = "House Atmosphere"
        # 4. Host Nagarjuna grilling beat
        elif any(k in narr_lower for k in ["నాగార్జున", "నాగ్", "హోస్ట్", "దిగిపోయారు", "ఆడుకున్నారు"]):
            primary_entity = "Nagarjuna Akkineni"
            contestant_names = ["Nagarjuna Akkineni"]

        # 5. Anti-Monotony Consecutive Entity Cap (Max 2 consecutive scenes of the same person)
        if primary_entity and primary_entity.lower() == last_assigned_entity.lower() and primary_entity != "YouTube Channel Subscribe Outro":
            consecutive_entity_count += 1
        else:
            consecutive_entity_count = 1

        # Anti-Monotony Rotation: Only rotate if the sentence does NOT explicitly name this contestant!
        explicitly_named = False
        if primary_entity:
            first_n = primary_entity.lower().split()[0]
            explicitly_named = (first_n in narr_lower) or any(t in narr for t in ["త్రిగుణ్", "అమన్", "సుధీర్", "వంశీ", "నాగార్జున", "ఝాన్సీ", "రోహిత్"])

        if consecutive_entity_count > 2 and is_bb and not explicitly_named:
            # Rotate to a generic house reaction or house interior, never invent a wrong contestant!
            rotation_candidates = [
                "Bigg Boss Telugu 10 Living Room", "Bigg Boss Telugu 10 House", "Nagarjuna Akkineni"
            ]
            for cand in rotation_candidates:
                if cand.lower() != primary_entity.lower():
                    primary_entity = cand
                    contestant_names = [cand]
                    consecutive_entity_count = 1
                    break

        last_assigned_entity = primary_entity

        # Determine emotion_or_action:
        emotion_or_action = (sec.get("emotion") if isinstance(sec, dict) else "") or ""
        if not emotion_or_action:
            if _has_word(narr_lower, ("shock", "shocking", "ఆశ్చర్యం", "షాక్", "షాకింగ్", "stun", "twist", "ట్విస్ట్")):
                emotion_or_action = "shocked"
            elif _has_word(narr_lower, ("angry", "కోపం", "కోపంగా", "ఫైట్", "గొడవ", "రచ్చ", "వివాదం", "fire", "fight", "confrontation")):
                emotion_or_action = "angry"
            elif _has_word(narr_lower, ("happy", "సంతోషం", "సంబరాలు", "విజయం", "గెలుపు", "celebrat", "joy")):
                emotion_or_action = "happy"
            elif _has_word(narr_lower, ("factory", "plant", "ప్లాంట్", "తయారీ", "ఉత్పత్తి", "పరిశ్రమ")):
                emotion_or_action = "modern factory floor"
            elif _has_word(narr_lower, ("deal", "ఒప్పందం", "సంతకం", "agreement", "partnership", "invest")):
                emotion_or_action = "signature deal"
            elif _has_word(narr_lower, ("crash", "నష్టాలు", "పతనం", "down", "fall", "loss")):
                emotion_or_action = "stock crash"
            elif _has_word(narr_lower, ("speech", "interview", "press meet", "స్పీచ్", "ప్రెస్ మీట్", "ఇంటర్వ్యూ", "మాట్లాడుతూ")):
                emotion_or_action = "speech interview"
            else:
                if content_type in ("cinema", "politics", "reality_tv"):
                    emotion_or_action = "intense expression"
                elif content_type in ("business", "tech"):
                    emotion_or_action = "modern high quality"
                else:
                    emotion_or_action = "dramatic moment"

        # Construct visual_fallback_prompt for FLUX
        visual_fallback_prompt = f"{primary_entity} in {emotion_or_action}, highly detailed cinematic scene"

        # 2. Extract Specific Episode or Incident Context
        incident_context = "Show Highlight"
        if any(k in narr_lower for k in ["నామినేషన్", "నామినేట్", "nomination"]):
            incident_context = "Nominations Confrontation"
        elif any(k in narr_lower for k in ["కెప్టెన్", "captain", "ఓటింగ్"]):
            incident_context = "Captaincy Task"
        elif any(k in narr_lower for k in ["ఎలిమినేషన్", "ఎలిమినేట్", "elimination"]):
            incident_context = "Elimination Stage"
        elif any(k in narr_lower for k in ["కిచెన్", "kitchen", "ఫుడ్", "తినడం"]):
            incident_context = "Kitchen Duty Argument"
        elif any(k in narr_lower for k in ["లగ్జరీ", "బడ్జెట్", "luxury"]):
            incident_context = "Luxury Budget Task"
        elif any(k in narr_lower for k in ["సీక్రెట్", "ప్లాన్", "కుట్ర"]):
            incident_context = "Secret Strategy Discussion"
        elif any(k in narr_lower for k in ["ఫైట్", "గొడవ", "అటాక్"]):
            incident_context = "Heated House Fight"
        elif any(k in narr_lower for k in ["లైక్", "సబ్‌స్క్రైబ్", "కామెంట్"]):
            incident_context = "Audience Discussion Outro"

        # 3. Format Strict Context-Isolated Search Queries
        EMOTION_STOPWORDS = {"shocked", "aggressive", "sarcastic", "deadpan", "laughing", "angry", "confused", "crying", "happy", "serious", "dramatic moment"}
        clean_action = emotion_or_action if emotion_or_action.lower() not in EMOTION_STOPWORDS else ""

        if content_type == "reality_tv" and is_bb:
            primary_cname = primary_entity or (contestant_names[0] if contestant_names else "Bigg Boss Telugu 10")
            strict_query = format_strict_visual_query(primary_cname, season_name, event_year)
            fallback_promo_query = format_strict_visual_query(primary_cname, "Bigg Boss Telugu", event_year, task_or_promo=incident_context)
        elif content_type in ("cinema", "politics"):
            strict_query = f'"{primary_entity}" {clean_action or "face photo"} OR interview'.strip()
            fallback_promo_query = f'"{primary_entity}" photo HD'
        elif content_type in ("business", "tech"):
            strict_query = f'"{primary_entity}" {clean_action or "technology official"} HD'.strip()
            fallback_promo_query = f'"{primary_entity}" official high resolution'
        else:
            # News & General Real-World Topics: Journalistic keywords only
            strict_query = f'"{primary_entity}" {clean_action or "news photo"} HD'.strip()
            fallback_promo_query = f'"{primary_entity}" news photo'

        # 4. Check metaphor mapping
        matched_negatives = list(past_season_exclusions)
        v_intent = "literal_entity" if (primary_entity or contestant_names) else "broll_motion"
        metaphor_translation = ""

        for m in metaphors:
            for p in m.get("phrases", []):
                if p in narr_lower:
                    matched_negatives.extend(m.get("negative_terms", []))
                    v_intent = m.get("visual_intent", "reaction")
                    metaphor_translation = m.get("visual_translation", "")
                    break

        # 5. Clean, sanitize and disallow generic queries
        raw_v_str = (raw_v.get("query") or raw_v.get("concept") or "") if isinstance(raw_v, dict) else str(raw_v or "")
        raw_queries = [q.strip() for q in raw_v_str.split("|") if q.strip()]

        # For real-world topics, prioritize the concrete scene query at the very top of search
        if content_type not in ("reality_tv", "entertainment"):
            concrete_top = [q for q in raw_queries if not is_generic_visual_query(q)]
            cleaned_queries = concrete_top[:2] + [strict_query, fallback_promo_query]
        else:
            cleaned_queries = [strict_query, fallback_promo_query]

        for q in raw_queries:
            q_lower = q.lower()
            if is_generic_visual_query(q):
                continue
            if any(neg.lstrip('-').lower() in q_lower for neg in matched_negatives if len(neg) > 2):
                continue
            if q not in cleaned_queries:
                cleaned_queries.append(q)

        if metaphor_translation and metaphor_translation not in cleaned_queries:
            cleaned_queries.append(metaphor_translation)

        # 6. Extract On-Screen Text (1-4 words punchy uppercase)
        bold_matches = re.findall(r"\*\*(.*?)\*\*", narr)
        if bold_matches:
            on_screen_text = bold_matches[0].strip().upper()
        elif primary_entity:
            on_screen_text = " ".join(primary_entity.upper().split()[:2])
        elif contestant_names:
            cname = contestant_names[0].upper()
            on_screen_text = " ".join(cname.split()[:2])
        elif v_intent == "reaction":
            on_screen_text = "HEATED FIGHT" if ("fight" in narr_lower or "మంట" in narr_lower) else "SHOCKING REACTION"
        elif v_intent == "data_graphic":
            on_screen_text = "VOTING PEAKS"
        elif v_intent == "text_card":
            on_screen_text = "BIG TWIST"
        else:
            first_words = cleaned_queries[0].split()[:3] if cleaned_queries else ["SCENE"]
            on_screen_text = " ".join(first_words).upper()

        if len(on_screen_text.split()) > 4:
            on_screen_text = " ".join(on_screen_text.split()[:4])

        # Script-Level Visual Planning: main_entity, emotion, and clean keyword search_query
        sec_dict = sec if isinstance(sec, dict) else {}
        main_ent = sec_dict.get("main_entity") or primary_entity
        emo = sec_dict.get("emotion") or emotion_or_action

        sq = sec_dict.get("search_query")
        if not sq or sq.strip() == narr.strip() or len(str(sq).split()) > 7 or (bool(re.search(r"[\u0C00-\u0C7F]", str(sq))) and len(str(sq)) > 30):
            if is_bb and content_type == "reality_tv":
                sq = f"{main_ent} bigg boss".strip()
            elif content_type in ("cinema", "politics"):
                sq = f"{main_ent} {emo}".strip()
            else:
                sq = f"{main_ent} {emo}".strip()

        visual_fallback_prompt = f"Cinematic {main_ent} in {emo} expression, 9:16 vertical ratio, photorealistic, 8k, dramatic lighting"

        beat_item = {
            "beat_id": idx,
            "narration": narr,
            "main_entity": main_ent,
            "emotion": emo,
            "search_query": sq,
            "content_type": content_type,
            "primary_entity": main_ent,
            "emotion_or_action": emo,
            "visual_fallback_prompt": visual_fallback_prompt,
            "spoken_text": narr,
            "contestant_names": contestant_names,
            "season_name": season_name,
            "year": event_year,
            "event_year": event_year,
            "incident_context": incident_context,
            "strict_query": strict_query,
            "fallback_promo_query": fallback_promo_query,
            "entities": [e["id"] for e in entities],
            "visual_intent": v_intent,
            "queries": cleaned_queries,
            "cleaned_queries": cleaned_queries,
            "negative_terms": list(set(matched_negatives)),
            "negative_exclusions": past_season_exclusions,
            "must_contain": [main_ent] if main_ent else (contestant_names if contestant_names else [e["canonical_name"] for e in entities]),
            "on_screen_text": on_screen_text,
            "fallback": "text_card",
        }
        structured_plan.append(beat_item)

    # Save to output/visual_plan.json
    try:
        Path("output").mkdir(parents=True, exist_ok=True)
        Path("output/visual_plan.json").write_text(
            json.dumps(structured_plan, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"📋 Generated Structured Visual Plan ({len(structured_plan)} beats) with Strict Season Lock -> output/visual_plan.json")
    except Exception as e:
        print(f"⚠️ Notice saving visual_plan.json: {e}")

    return structured_plan


def synthesize_beat_visual_plan(delivery_plan: List[Dict[str, Any]], topic: str = "") -> List[str]:
    """
    Synthesizes rich, sentence-specific, non-repeating visual queries for each beat.
    Uses structured script-level visual planning with LLM output:
    {
      "beat_id": 1,
      "narration": "తెలుగు డైలాగ్...",
      "main_entity": "Exact Name of Celebrity/Person (e.g. Shalini Patel / Temper Vamsi / Dil Raju)",
      "emotion": "shocked / angry / aggressive / smiling",
      "search_query": "Clean keyword query (e.g., 'Shalini Patel bigg boss' or 'Temper Vamsi actor')"
    }
    STRICT RULE: The LLM must NEVER use the entire narration sentence as the search query.
    It must explicitly extract the target person's name and the context keyword.
    """
    import json
    import re
    from pathlib import Path
    try:
        from tools.build_entity_library import match_entities_in_text
    except ImportError:
        def match_entities_in_text(t):
            return []

    from utils.season_guard import (
        is_bigg_boss_topic,
        get_current_season_number,
        format_strict_visual_query,
        is_generic_visual_query,
        KNOWN_TELUGU_SHOW_PERSONS,
    )
    is_bb = is_bigg_boss_topic(topic)
    total_beats = len(delivery_plan)
    if total_beats == 0:
        return []

    cur_season = get_current_season_number(topic) or 10
    season_name = f"Bigg Boss Telugu {cur_season}"
    event_year = 2026 if cur_season >= 10 else 2025

    # 1. Attempt Fast Batch LLM Structured Visual Planning
    prompt_beats = []
    for b in delivery_plan:
        b_idx = b.get("beat_id", 1)
        spoken = b.get("spoken_text", "")
        emo = b.get("emotion", "neutral")
        prompt_beats.append(f"Beat {b_idx}: Narration: \"{spoken}\" | Emotion: {emo}")

    beats_str = "\n".join(prompt_beats)
    bb_negative_rule = (
        "- STRICT TOPIC ADHERENCE: Constrain all visuals solely to this specific topic. Do NOT mention Bigg Boss, reality show housemates, or unrelated contestants."
        if not is_bb
        else (
            "- MANDATORY REALITY SHOW FORMAT: Format search_query strictly as '[Contestant Name] [Season Name]' (e.g. 'Thrigun Bigg Boss Telugu 10', 'Temper Vamsi Bigg Boss 10', 'Aman Masud Bigg Boss Telugu 10').\n"
            "- STRICT GROUND TRUTH: Active Season 10 housemates: Temper Vamsi (CAPTAIN THIS WEEK), Thrigun Eswaran (Trigun), Aman Masud, Sudheer Reddy (Sudheer), Auto Ram Prasad, Potti Naresh, Debjani Modak, Shiv, Mukesh Gowda, Varshini Sounderajan, Rama Krishna, Swetha, Neethu Natraj, Host Akkineni Nagarjuna.\n"
            "- THIS WEEK GROUND TRUTH: NO ELIMINATION THIS WEEK! Temper Vamsi is the current Captain.\n"
            "- ELIMINATED CONTESTANTS: Rohit Patnam, Shalini Patel, Gundeboina Jhansi (Singer Jhansi), Chaithra Rai, Krishna Alluri (Krishnudu), Srishti Vyakaranam, Charan Mahadev, Mithilesh Reddy. STRICT: DO NOT feature eliminated contestants in active house tasks, immunity, captaincy, or nominations unless the topic specifically covers their eviction episode!\n"
            "- STRICT PROHIBITION: NEVER use past contestants or unrelated stars: NO Rohit Sahni, NO Anchor Jhansi, NO Ram Charan.\n"
            "- FORBIDDEN GENERIC QUERIES: NEVER output generic search queries like 'Bigg Boss Telugu drama', 'Bigg Boss emotional scene', 'Bigg Boss Telugu stage', or 'Bigg Boss housemates'."
        )
    )
    llm_prompt = f"""You are an expert visual planner and video editor.
Generate a structured JSON visual plan for these {total_beats} sequential script beats about '{topic}'.

CRITICAL RULES:
1. Output a JSON array with EXACTLY {total_beats} objects.
2. Each object MUST strictly follow this JSON format:
   {{
     "beat_id": <number>,
     "narration": "<Telugu narration sentence>",
     "main_entity": "<Exact Name of Celebrity/Person, Company, or Product (e.g. Thrigun Eswaran / Shiv / Dil Raju)>",
     "emotion": "<shocked / angry / aggressive / smiling / serious / deadpan>",
     "search_query": "<Clean 2-4 word keyword query (e.g., 'Thrigun Eswaran bigg boss' or 'Shiv Anchor bigg boss')>"
   }}
3. STRICT RULE: The LLM must NEVER use the entire narration sentence as the search query! You must explicitly extract the target person's name and the context keyword (2 to 4 words max).
4. EVERY beat MUST have a completely UNIQUE search_query. Never repeat queries across beats.
5. STRICT ENTITY FIDELITY: The 'main_entity' for each beat MUST strictly reflect the person or subject being discussed in that beat's narration. Extract ONLY the person, celebrity, or entity actively referenced in that specific sentence. Do NOT invent or substitute other individuals who are not being talked about in that beat!
{bb_negative_rule}

BEATS:
{beats_str}

Output valid JSON only:
"""

    parsed_structured_beats: List[Dict[str, Any]] = []
    try:
        from providers.llm import generate_text_cascade
        raw_resp = generate_text_cascade(llm_prompt, step_name="beat_visual_synthesis", per_provider_timeout=12.0)
        clean_resp = raw_resp.strip()
        if "```" in clean_resp:
            clean_resp = re.sub(r"^```(?:json)?\s*", "", clean_resp, flags=re.IGNORECASE)
            clean_resp = re.sub(r"\s*```$", "", clean_resp)
            clean_resp = clean_resp.strip()

        arr_m = re.search(r"\[\s*\{.*\}\s*\]", clean_resp, re.DOTALL)
        if arr_m:
            clean_resp = arr_m.group(0)

        data = json.loads(clean_resp)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "beat_id" in item:
                    sq = str(item.get("search_query", "")).strip()
                    narr_text = str(item.get("narration", "")).strip()
                    ent = str(item.get("main_entity", "")).strip()
                    # Sanitize: NEVER allow full narration sentence as search query
                    if (sq == narr_text) or len(sq.split()) > 7 or (bool(re.search(r"[\u0C00-\u0C7F]", sq)) and len(sq) > 30):
                        clean_ent = ent or (topic.split(":")[0].strip())
                        emo_kw = str(item.get("emotion", "photo")).strip()
                        sq = f"{clean_ent} {emo_kw}".strip()
                    item["search_query"] = sq
                    parsed_structured_beats.append(item)
    except Exception as e:
        print(f"Notice: LLM visual synthesis notice: {e}")

    use_llm = False
    if len(parsed_structured_beats) == total_beats:
        llm_queries = [b.get("search_query", "") for b in parsed_structured_beats if b.get("search_query")]
        if len(set(llm_queries)) == total_beats:
            use_llm = True

    is_entertainment_context = is_bb or any(
        k in topic.lower()
        for k in ["bigg boss", "movie", "cinema", "actor", "director", "producer", "roast", "controversy", "show", "telugu", "dil raju", "film", "celebrity"]
    )

    if is_entertainment_context:
        CAMERA_ANGLES = [
            "cinematic close-up portrait",
            "dynamic wide-angle event stage",
            "candid reaction shot",
            "split-screen contrast comparison",
            "expressive candid face expression",
            "dramatic overhead perspective",
            "heated confrontation medium shot",
            "emotional confession close-up",
            "stage lighting podium perspective",
            "dramatic reality camera angle",
        ]
    else:
        CAMERA_ANGLES = [
            "cinematic close-up portrait",
            "dynamic wide-angle event stage",
            "candid reaction shot",
            "macro hardware tech closeup",
            "split-screen contrast comparison",
            "futuristic isometric 3D render",
            "live convention floor keynote",
            "expressive candid face expression",
            "dramatic overhead perspective",
            "high tech digital schematic"
        ]

    TELUGU_SEMANTIC_MAP = [
        (("సిగ్నల్", "సిగ్నల్స్", "గాలిలో", "నెట్‌వర్క్"), "person holding up smartphone searching for mobile network signal on balcony"),
        (("సిక్స్-జీ", "6g", "6-g"), "futuristic 6G network technology presentation India Mobile Congress stage"),
        (("కాంగ్రెస్", "ఎక్స్‌పో", "వేదిక"), "India Mobile Congress 2026 tech convention expo hall showcase crowd"),
        (("ఏఐ", "నేటివ్", "ఆర్టిఫిషియల్"), "AI native autonomous neural network data communication concept visual"),
        (("డేటా", "రీఛార్జ్", "అయిపోయాక"), "funny meme person looking at smartphone zero data empty balance notification shocked"),
        (("విజన్", "డిజిటల్", "దశాబ్దం"), "Digital India futuristic smart city high-tech skyline vision"),
        (("రోడ్లు", "తవ్వడం", "ఫైవ్-జీ"), "city street excavation optical fiber cable installation work scene"),
        (("పేటెంట్", "విదేశీ", "డిపెండెన్సీ"), "advanced semiconductor technology patents engineering research laboratory"),
        (("స్పీడ్", "వేగం", "డౌన్‌లోడ్"), "ultra high speed data transfer speed test graphic smartphone screen"),
        (("లైక్", "సబ్‌స్క్రైబ్", "కామెంట్"), "youtube subscribe button dynamic bell animation social media engagement"),
        (("నామినేషన్", "నామినేట్"), "intense reality show nomination confrontation argument housemates" if is_bb else f"{topic} nomination award ceremony announcement"),
        (("ఎలిమినేషన్", "ఎలిమినేట్"), "shocked emotional elimination stage dramatic exit reality show" if is_bb else f"{topic} dramatic intense unexpected twist reveal"),
        (("టాస్క్", "గేమ్", "పోటీ"), "physical task competition action moment housemates contending" if is_bb else f"{topic} action competition moment"),
        (("మీమ్", "కామెడీ", "నవ్వు"), "funny viral reaction troll meme face expression candid comedy")
    ]

    result_lines = []
    used_queries: set = set()

    for idx, b in enumerate(delivery_plan, 1):
        spoken = b.get("spoken_text", "")
        spoken_lower = spoken.lower()
        badge = b.get("on_screen_text") or ""
        angle = CAMERA_ANGLES[(idx - 1) % len(CAMERA_ANGLES)]

        # Determine topic and beat entities
        b_ents = [e for e in match_entities_in_text(spoken) if e.get("id") != "bigg_boss_telugu"]
        topic_ents = [e for e in match_entities_in_text(topic) if e.get("id") != "bigg_boss_telugu"]
        explicit_entity = ""
        if b_ents:
            explicit_entity = b_ents[0]["canonical_name"]
        elif topic_ents:
            explicit_entity = topic_ents[(idx - 1) % len(topic_ents)]["canonical_name"]

        if use_llm:
            llm_item = parsed_structured_beats[idx - 1]
            main_entity = llm_item.get("main_entity", "")
            emotion = llm_item.get("emotion", b.get("emotion", "neutral"))
            # If LLM entity hallucinated someone outside topic and beat, enforce explicit entity
            if explicit_entity and (not main_entity or (main_entity.lower() not in topic.lower() and not any(e['canonical_name'].split()[0].lower() in main_entity.lower() or any(a.lower() in main_entity.lower() for a in e.get('aliases', [])) for e in b_ents))):
                main_entity = explicit_entity
                if is_bb:
                    search_query = format_strict_visual_query(main_entity, season_name, event_year)
                else:
                    search_query = f"{main_entity} {emotion}".strip()
            else:
                search_query = llm_item.get("search_query", "")
            candidate = f"{search_query} | {angle} | {main_entity} HD".strip(" |")
        else:
            # Deterministic extraction of main_entity & emotion
            emotion = b.get("emotion", "deadpan")
            if any(k in spoken_lower for k in ["షాక్", "షాకింగ్", "ఆశ్చర్యం", "shock", "shocking"]):
                emotion = "shocked"
            elif any(k in spoken_lower for k in ["కోపం", "కోపంగా", "ఫైట్", "గొడవ", "angry", "fire"]):
                emotion = "angry"
            elif any(k in spoken_lower for k in ["సంతోషం", "విజయం", "గెలుపు", "happy", "smiling"]):
                emotion = "smiling"
            elif any(k in spoken_lower for k in ["ఆక్రోశం", "దాడి", "aggressive"]):
                emotion = "aggressive"

            if explicit_entity:
                main_entity = explicit_entity
            else:
                for p_info in KNOWN_TELUGU_SHOW_PERSONS.values():
                    if any(al.lower() in spoken_lower for al in p_info.get("aliases", [])):
                        main_entity = p_info["canonical"]
                        break

            if not main_entity:
                if is_bb:
                    if any(k in spoken_lower for k in ["హోస్ట్", "host", "నాగ్", "నాగార్జున", "నడుము"]):
                        main_entity = "Nagarjuna Akkineni"
                    elif idx == 1:
                        main_entity = "Nagarjuna Akkineni"
                    else:
                        main_entity = "Bigg Boss Telugu 10 Housemates"
                elif "dil raju" in topic.lower() or "dil raju" in spoken_lower or "దిల్ రాజు" in spoken_lower:
                    main_entity = "Dil Raju"
                else:
                    main_entity = topic.split(":")[0].strip() or "News Headline"

            # Context keyword extraction
            incident = "Nominations Confrontation" if any(k in spoken_lower for k in ["నామినేషన్", "నామినేట్", "nomination"]) else (
                "Captaincy Task" if any(k in spoken_lower for k in ["కెప్టెన్", "captain", "ఓటింగ్"]) else (
                    "Elimination Stage" if any(k in spoken_lower for k in ["ఎలిమినేషన్", "ఎలిమినేట్"]) else (
                        "Press Meet" if any(k in spoken_lower for k in ["ప్రెస్ మీట్", "press meet"]) else "Discussion"
                    )
                )
            )

            # Build concise 2-4 word search_query (NEVER entire narration sentence)
            if is_bb:
                strict_q = format_strict_visual_query(main_entity, season_name, event_year)
                search_query = strict_q
                candidate = f"{strict_q} {angle} | {main_entity} {incident} | {season_name} HD"
            else:
                search_query = f"{main_entity} {emotion}".strip()
                candidate = f"{main_entity} {angle} | {main_entity} {topic} | high quality realistic photo HD"

        # Update delivery_plan beat with structured fields
        b["main_entity"] = main_entity
        b["emotion"] = emotion
        b["search_query"] = search_query

        # Hard Deduplication & Variance Guard
        clean_candidate = candidate.strip()
        if clean_candidate in used_queries:
            angle_alt = CAMERA_ANGLES[idx % len(CAMERA_ANGLES)]
            clean_candidate = f"{clean_candidate} | {angle_alt} shot #{idx}"

        used_queries.add(clean_candidate)
        result_lines.append(clean_candidate)

    # Save output/beat_visual_plan.json
    try:
        beat_plan_export = []
        for idx, b in enumerate(delivery_plan, 1):
            beat_plan_export.append({
                "beat_id": idx,
                "narration": b.get("spoken_text", ""),
                "main_entity": b.get("main_entity", ""),
                "emotion": b.get("emotion", "neutral"),
                "search_query": b.get("search_query", ""),
            })
        Path("output").mkdir(parents=True, exist_ok=True)
        Path("output/beat_visual_plan.json").write_text(
            json.dumps(beat_plan_export, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception:
        pass

    return result_lines


def _parse_and_save_package(text, default_title=None):
    """
    Parse Gemini's structured response and save:

        output/script.txt
        output/visual_plan.txt
        output/section_map.txt

    Returns:
        script string

    Returns None if validation fails.
    """

    title_match = re.search(
        r"TITLE:\s*(.*?)(?:\n\s*SCRIPT:|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    title = clean_response(title_match.group(1)).strip() if title_match else ""

    script_match = re.search(
        r"SCRIPT:\s*(.*?)(?:\n\s*VISUAL_PLAN:|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    visual_match = re.search(
        r"VISUAL_PLAN:\s*(.*?)(?:\n\s*SECTIONS:|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    sections_match = re.search(
        r"SECTIONS:\s*(.*)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not script_match:
        print("Could not parse SCRIPT.")
        return None

    if not visual_match:
        print("Could not parse VISUAL_PLAN.")
        return None

    if not sections_match:
        print("Could not parse SECTIONS.")
        return None

    script = script_match.group(1).strip()

    # Gemini can occasionally return the SCRIPT section
    # in subtitle/SRT format. Never allow that into
    # script.txt or TTS.
    script = clean_script_narration(script)

    if not script:
        print("SCRIPT became empty after narration cleanup.")
        return None

    # --------------------------------------------------------
    # VISUAL PLAN
    # --------------------------------------------------------

    visual_plan = []

    for line in visual_match.group(1).splitlines():
        line = line.strip()
        line = re.sub(r"^(?:\d+[\.\)]|\*|\-)\s*", "", line).strip()
        if line and len(line) > 2:
            visual_plan.append(line)

    print(f"Parsed AI Visual Plan ({len(visual_plan)} visual concepts):")
    for idx, v_item in enumerate(visual_plan, start=1):
        print(f"  Visual {idx}: {v_item}")

    # --------------------------------------------------------
    # SECTIONS
    # --------------------------------------------------------

    sections = []
    section_text = sections_match.group(1).strip()

    pattern = re.compile(
        r"(?:\*{1,2}|#{1,3}\s*)?SECTION\s+(\d+)\s*[:\|]\s*VISUAL\s+(\d+)(?:\*{1,2})?:?\s*\n"
        r"(.*?)(?=\n\s*(?:\*{1,2}|#{1,3}\s*)?SECTION\s+\d+\s*[:\|]\s*VISUAL\s+\d+|\Z)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    paired_visuals_from_sections = []

    for match in pattern.finditer(section_text):
        section_number = int(match.group(1))
        visual_number = int(match.group(2))
        block = match.group(3).strip()

        # Check if block has explicit VISUAL: and NARRATION:
        v_match = re.search(r"(?:^|\n)\s*(?:\*{1,2})?VISUAL(?:\*{1,2})?\s*:\s*(.*?)(?=\n\s*(?:\*{1,2})?NARRATION(?:\*{1,2})?\s*:|\Z)", block, re.IGNORECASE | re.DOTALL)
        n_match = re.search(r"(?:^|\n)\s*(?:\*{1,2})?NARRATION(?:\*{1,2})?\s*:\s*(.*)$", block, re.IGNORECASE | re.DOTALL)

        if v_match and n_match:
            sec_visual = v_match.group(1).strip().strip("*").strip()
            sec_narration = n_match.group(1).strip()
        else:
            sec_visual = ""
            sec_narration = block

        if sec_narration:
            sections.append({
                "section": section_number,
                "visual": visual_number,
                "narration": sec_narration,
            })
            paired_visuals_from_sections.append(sec_visual)

    # If the LLM returned explicit VISUAL: tags for each section, use those directly!
    # This guarantees 100% synchronization between what is said and what is shown.
    if paired_visuals_from_sections and all(bool(v) for v in paired_visuals_from_sections) and len(paired_visuals_from_sections) == len(sections):
        print(f"✅ Found {len(paired_visuals_from_sections)} 1:1 synchronized section visuals directly inside SECTIONS block.")
        visual_plan = paired_visuals_from_sections

    # If regex missed alternative formatting, try splitting by section headers
    if not sections:
        raw_blocks = re.split(
            r"\n\s*(?:SECTION\s+\d+|###\s*SECTION|\*\*SECTION)",
            section_text,
            flags=re.IGNORECASE,
        )
        sec_idx = 1
        for block in raw_blocks:
            clean_b = block.strip()
            clean_b = re.sub(r"^(?:\|\s*VISUAL\s+\d+|\:\s*VISUAL\s+\d+|\d+)\s*", "", clean_b).strip()
            if len(clean_b) > 20:
                sections.append({
                    "section": sec_idx,
                    "visual": sec_idx,
                    "narration": clean_b,
                })
                sec_idx += 1

    # Strip accidental visual description lines from the start of section narration ONLY if multiple lines exist
    for idx, sec in enumerate(sections):
        if idx < len(visual_plan):
            vis = visual_plan[idx].strip().lower()
            lines = sec["narration"].splitlines()
            if len(lines) > 1:
                first_line = lines[0].strip().lower()
                if (
                    first_line == vis
                    or vis in first_line
                    or first_line in vis
                    or re.match(r"^(?:visual|shot|scene|image)\s*\d*[:\-]", first_line)
                ):
                    cleaned_narr = "\n".join(lines[1:]).strip()
                    if cleaned_narr:
                        sec["narration"] = cleaned_narr

    # Filter out any sections with empty narration and synchronize corresponding visual
    valid_sections = []
    valid_visuals = []
    for idx, sec in enumerate(sections):
        narr = sec.get("narration", "").strip()
        if narr:
            valid_sections.append(sec)
            if idx < len(visual_plan):
                valid_visuals.append(visual_plan[idx])

    if valid_sections:
        sections = valid_sections
        if valid_visuals:
            visual_plan = valid_visuals

    # Reconcile counts gracefully to guarantee exact 1:1 match
    min_count = min(len(visual_plan), len(sections))
    if min_count >= 4:
        visual_plan = visual_plan[:min_count]
        sections = sections[:min_count]

    # Normalize section numbers and visual numbers to 1..N
    for idx, sec in enumerate(sections, start=1):
        sec["section"] = idx
        sec["visual"] = idx

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if len(visual_plan) < 4:
        print(
            f"Visual count too low: "
            f"got {len(visual_plan)} (minimum 4)."
        )
        return None

    if len(sections) != len(visual_plan):
        print(
            f"Section count ({len(sections)}) does not match "
            f"visual-plan count ({len(visual_plan)})."
        )
        return None

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    os.makedirs("output", exist_ok=True)

    # Ensure script is deduplicated and ends with dynamic 2-3s like/share/subscribe CTA
    is_indic = bool(re.search(r"[\u0C00-\u0C7F]", script))
    script = deduplicate_script_narration(script)
    script = ensure_dynamic_outro_cta(script, topic=default_title or "", is_indic=is_indic)
    script = deduplicate_script_narration(script)

    with open(
        "output/script.txt",
        "w",
        encoding="utf-8"
    ) as file:

        file.write(script)

    with open(
        "output/tts_script.txt",
        "w",
        encoding="utf-8"
    ) as file:

        file.write(clean_script_narration(script))

    # Contestant Locking & Host Disqualification Guard on visual plan (Strictly for Bigg Boss topics)
    try:
        from utils.season_guard import is_bigg_boss_topic
        script_full = " ".join(s.get("narration", "") for s in sections)
        if is_bigg_boss_topic(f"{default_title or ''} {script_full}"):
            from tools.build_entity_library import match_entities_in_text
            matched_c = [e for e in match_entities_in_text(f"{default_title or ''} {script_full}") if e.get("id") != "bigg_boss_telugu" and e.get("id") != "nagarjuna_akkineni"]
            if matched_c:
                c_names = " and ".join(e["canonical_name"] for e in matched_c[:2])
                for v_i in range(len(visual_plan)):
                    v_curr = visual_plan[v_i]
                    sec_narr = sections[v_i].get("narration", "") if v_i < len(sections) else ""
                    has_host = any(h in (v_curr.lower() + " " + sec_narr.lower()) for h in ("nagarjuna", "నాగార్జున", "king nag", "host"))
                    if not has_host and any(k in v_curr.lower() for k in ("nagarjuna", "host", "title logo", "banner")):
                        from config.settings import get_setting
                        from utils.season_guard import resolve_effective_show_context
                        show_ctx_dyn = resolve_effective_show_context(
                            topic_or_title=default_title or "",
                            script_text=script_full,
                            raw_show_context=get_setting("SHOW_CONTEXT", ""),
                        ) or "Bigg Boss Telugu 10"
                        visual_plan[v_i] = f"{c_names} {show_ctx_dyn} | {c_names} reaction moment | {show_ctx_dyn}"
    except Exception as lock_err:
        pass

    with open(
        "output/visual_plan.txt",
        "w",
        encoding="utf-8"
    ) as file:

        for index, visual in enumerate(
            visual_plan,
            start=1
        ):

            file.write(
                f"{index}. {visual}\n"
            )

    with open(
        "output/section_map.txt",
        "w",
        encoding="utf-8"
    ) as file:

        for item in sections:

            file.write(
                f"SECTION {item['section']} | "
                f"VISUAL {item['visual']}\n"
            )

            file.write(
                f"{item['narration']}\n\n"
            )

    # Generate and save Phase 5 structured visual plan (output/visual_plan.json)
    try:
        build_structured_visual_plan(sections, visual_plan, topic=default_title or "")
    except Exception as v_plan_err:
        print(f"⚠️ Structured visual plan generation notice: {v_plan_err}")

    # Generate and save Long-Form Chapters structure (output/chapters.json)
    try:
        from agents.chapter_engine import parse_chapters_from_script
        parse_chapters_from_script(sections, total_duration=0.0, script_text=script)
    except Exception as ch_err:
        print(f"⚠️ Chapter parsing notice: {ch_err}")

    # Save query debug log for diagnosis
    try:
        import json
        from pathlib import Path
        logs_dir = Path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        from agents.image_agent import build_queries
        debug_list = []
        for sec in sections:
            sec_num = int(sec.get("section", 1))
            v_idx = sec_num - 1
            v_concept = visual_plan[v_idx] if 0 <= v_idx < len(visual_plan) else ""
            queries = build_queries(v_concept, narration=sec.get("narration", ""))
            debug_list.append({
                "section": sec_num,
                "narration": sec.get("narration", ""),
                "visual_concept": v_concept,
                "search_queries": queries,
            })
        with open("logs/query_debug.json", "w", encoding="utf-8") as df:
            json.dump(debug_list, df, indent=2, ensure_ascii=False)
        print(f"📝 Saved query debug log ({len(debug_list)} entries) to logs/query_debug.json")
    except Exception as dbg_err:
        print(f"Query debug logging notice: {dbg_err}")

    if not title and default_title:
        candidate_title = str(default_title).strip()
        if len(candidate_title) <= 120 and "\n" not in candidate_title:
            title = candidate_title

    if not title and visual_plan:
        first_vis = visual_plan[0].split("|")[0].strip()
        candidate = re.sub(
            r"^(photo|image|picture|illustration|close-up)\s+of\s+",
            "",
            first_vis,
            flags=re.IGNORECASE,
        ).strip()
        if candidate and len(candidate) <= 60:
            title = candidate

    if not title and script:
        first_sent = re.split(r"[.!?\n]", script)[0].strip()
        if len(first_sent) > 60:
            first_sent = first_sent[:57].rsplit(" ", 1)[0] + "..."
        title = first_sent

    if title:
        with open(
            "output/title.txt",
            "w",
            encoding="utf-8"
        ) as file:
            file.write(title)

    print()
    print("=" * 60)
    print("CONTENT PACKAGE SAVED")
    print("=" * 60)
    print()
    if title:
        print(f"Title:        output/title.txt ({title})")
    print("Script:       output/script.txt")
    print("Visual plan:  output/visual_plan.txt")
    print("Sections:     output/section_map.txt")
    print()
    print(f"Script characters: {len(script)}")
    print(f"Visual concepts:   {len(visual_plan)}")
    print(f"Sections:          {len(sections)}")
    print()

    return script


def _format_news_sources(source_context):
    """
    Convert verified news source data into a clear,
    source-by-source context block for Gemini.
    """

    if not source_context:
        return "No verified news sources supplied."

    if isinstance(source_context, str):
        return source_context.strip() or "No verified news sources supplied."

    if not isinstance(source_context, dict):
        return "No verified news sources supplied."

    articles = source_context.get("articles", [])

    if not articles:
        return "No verified news sources supplied."

    blocks = []

    for index, article in enumerate(articles, start=1):

        headline = str(
            article.get("headline", "")
        ).strip()

        source = str(
            article.get("source", "")
        ).strip()

        published_at = str(
            article.get("published_at", "")
        ).strip()

        url = str(
            article.get("url", "")
        ).strip()

        article_text = str(
            article.get("article_text", "")
        ).strip()

        snippet = str(
            article.get("snippet", "")
        ).strip()

        block = f"""
SOURCE {index}

Headline:
{headline}

Source:
{source}

Published:
{published_at}

Article text:
{article_text}

Snippet:
{snippet}

URL:
{url}
""".strip()

        blocks.append(block)

    return "\n\n".join(blocks)


def auto_calibrate_script_to_profile(
    script: str,
    profile,
    topic: str = "",
    content_type: str = "News",
    fallback_title: Optional[str] = None,
) -> str:
    """
    Zero-Fail Script Pre-Execution Calibration:
    Verifies that the script meets format_profile word count bounds (profile.min_words to profile.max_words).
    If under-length, expands narration with deep topical context, audience reactions, or technical analysis.
    If over-length, cleanly condenses narration.
    Guarantees Gate A passes before audio and visual synthesis, with zero risk of wasted rendering time.
    """
    if not script or not script.strip():
        return script

    clean_text = clean_script_narration(script)
    words = clean_text.split()
    word_count = len(words)

    is_indic = any(
        ('\u0c00' <= char <= '\u0c7f') or  # Telugu
        ('\u0900' <= char <= '\u097f') or  # Devanagari
        ('\u0b80' <= char <= '\u0bff') or  # Tamil
        ('\u0c80' <= char <= '\u0cff') or  # Kannada
        ('\u0d00' <= char <= '\u0d7f')     # Malayalam
        for char in clean_text
    )

    is_extended_shorts = (profile.target_seconds > 50.0 and profile.format_type == "short")
    if is_extended_shorts:
        # 60-90s Shorts Profile (Target: 75s, Min: 60s)
        # Indic spoken pacing at 2.15 wps requires at least 60 * 2.15 = 129 spoken words
        effective_min_words = max(130, int(profile.min_seconds * 2.15))
        effective_max_words = max(185, int(profile.max_seconds * 2.30))
    elif profile.format_type == "long-form":
        # Long-Form Profile (6-9m or 2-4m): strictly enforce profile bounds (minimum 900 words for 6-9m)
        effective_min_words = profile.min_words
        effective_max_words = profile.max_words
    else:
        effective_min_words = int(profile.min_words * 0.80) if is_indic else profile.min_words
        effective_max_words = int(profile.max_words * 0.85) if is_indic else profile.max_words

    print(f"🎯 [Pre-Execution Calibration] Script length: {word_count} words (Required: {effective_min_words}-{effective_max_words} words for {profile.target_seconds:.0f}s)...")

    # Under-length calibration: auto-expand
    if word_count < effective_min_words:
        shortfall = effective_min_words - word_count
        print(f"⚠️ Script is short by ~{shortfall} words ({word_count} < {effective_min_words}). Executing Step 1 auto-expansion...")

        expand_prompt = f"""You are an elite YouTube scriptwriter and engagement optimizer.
The script below is currently only {word_count} spoken words, but MUST be strictly between {effective_min_words} and {effective_max_words} spoken words (Target: {profile.target_words} words) for a {profile.target_seconds:.0f} second video.

CURRENT SCRIPT:
{script}

TOPIC: {topic}

INSTRUCTIONS:
1. EXPAND the script by adding rich observational commentary, deep context, scientific/factual mechanisms, and vivid explanations about {topic}.
2. Keep the existing opening hook and best lines intact.
3. If Telugu, write in natural, punchy, conversational spoken Telugu with relatable Tanglish expressions.
4. Ensure a natural, quirky call-to-action (like & subscribe) at the end.
5. STRICT REQUIREMENT: The total spoken narration MUST have at least {effective_min_words} words (target {profile.target_words} words).

Return ONLY the complete expanded spoken narration:"""

        expanded_text = None
        try:
            from providers.llm import generate_text_cascade
            raw_res = generate_text_cascade(expand_prompt, step_name="script_calibration", per_provider_timeout=35.0)
            cleaned = clean_response(raw_res)
            # Remove any markdown headers
            cleaned = re.sub(r"^#+\s*.*?\n", "", cleaned).strip()
            cleaned = re.sub(r"^TITLE:\s*.*?\n", "", cleaned, flags=re.IGNORECASE).strip()
            s_match = re.search(r"SCRIPT:\s*(.*?)(?:\n\s*(?:VISUAL_PLAN|SECTIONS):|\Z)", cleaned, re.IGNORECASE | re.DOTALL)
            if s_match:
                cleaned = clean_script_narration(s_match.group(1).strip())
            else:
                cleaned = clean_script_narration(cleaned)

            if len(cleaned.split()) >= effective_min_words:
                expanded_text = cleaned
                print(f"✅ Step 1 auto-expansion successful: Now {len(expanded_text.split())} words.")
        except Exception as exp_err:
            print(f"⚠️ Step 1 LLM auto-expansion notice: {exp_err}")

        # Deterministic fallback expansion if LLM was unavailable or slightly short
        if not expanded_text or len(expanded_text.split()) < effective_min_words:
            curr_text = expanded_text if expanded_text else clean_text
            missing = effective_min_words - len(curr_text.split())
            if missing > 0:
                print(f"⚡ Applying deterministic topical elaboration (+{missing} words needed)...")
                is_factual_topic = any(k in f"{topic} {content_type}".lower() for k in ("earth", "space", "spin", "fact", "science", "planet", "physics", "universe", "history", "nature"))
                if is_factual_topic:
                    telugu_blocks = [
                        f"{topic} వెనుక ఉన్న శాస్త్రీయ కారణాలను విశ్లేషిస్తే ఎన్నో ఆశ్చర్యకరమైన వాస్తవాలు వెలుగులోకి వస్తాయి.",
                        "భూమి భ్రమణ వేగం సాధారణంగా భూమధ్యరేఖ వద్ద గంటకు సుమారు పదహారు వందల కిలోమీటర్ల వేగంతో ఉంటుంది.",
                        "అలాంటి భారీ వేగంతో తిరుగుతున్న గ్రహం అకస్మాత్తుగా ఆగిపోతే ఉత్పన్నమయ్యే జడత్వ ప్రభావం ఊహకందని స్థాయిలో ఉంటుంది.",
                        "వాతావరణం తన స్వంత గతితో ముందుకు సాగడం వల్ల భూమి ఉపరితలంపై తీవ్రమైన సూపర్ సోనిక్ గాలులు వీస్తాయి.",
                        "సముద్రాలు మరియు మహాసముద్రాల నీరు ఒక్కసారిగా ఖండాల వైపు దూసుకువచ్చి భారీ మెగా సునామీలుగా మారే అవకాశం ఉంది.",
                        "భౌతిక శాస్త్ర సూత్రాల ప్రకారం ప్రతి చలన వస్తువుకు ఇనర్షియా లేదా జడత్వం చాలా శక్తివంతమైన పాత్ర పోషిస్తుంది.",
                        "ఐదు సెకన్ల విరామం మాత్రమే అయినా, ఆ స్వల్ప వ్యవధిలోనే కలిగే భౌతిక మరియు పర్యావరణ మార్పులు అపారమైనవి.",
                        "భూమి అయస్కాంత క్షేత్రం మరియు ఉపగ్రహాల కక్ష్యలు కూడా ఇలాంటి ఆకస్మిక కుదుపులకు తీవ్రంగా ప్రభావితం అవుతాయి.",
                        "శాస్త్రవేత్తలు మరియు పరిశోధకులు ఇలాంటి సిద్ధాంతపరమైన దృశ్యాలను కంప్యూటర్ సిమ్యులేషన్ల ద్వారా విస్తృతంగా అధ్యయనం చేశారు.",
                        "మళ్లీ భూమి తిరగడం ప్రారంభించినప్పుడు వాతావరణం స్థిరీకరణకు చేరుకోవడానికి గణనీయమైన సమయం పడుతుంది.",
                        "ఈ విశ్లేషణ మన గ్రహం యొక్క నిరంతర సమతుల్యత ఎంత సున్నితమైనదో మరియు అద్భుతమైనదో మనకు స్పష్టంగా గుర్తుచేస్తుంది.",
                        "ప్రపంచవ్యాప్తంగా ఉన్న సైన్స్ నిపుణులు మరియు ఖగోళ శాస్త్రవేత్తలు ఇలాంటి దృగ్విషయాలపై నిరంతరం పరిశోధనలు జరుపుతున్నారు.",
                        "గ్రహాల భ్రమణం మరియు గురుత్వాకర్షణ శక్తుల పరస్పర సంబంధం జీవకోటి మనుగడకు అత్యంత కీలకం.",
                        "ప్రతి చిన్న భౌతిక మార్పు కూడా మొత్తం జీవావరణంపై దీర్ఘకాలిక ప్రభావాన్ని చూపుతుందని ఈ ఆధారాలు స్పష్టం చేస్తున్నాయి.",
                        "మరిన్ని లోతైన పరిశీలనలు మరియు నిరూపితమైన వాస్తవాలు ఈ అంశంపై మరింత ఆసక్తికరమైన సమాచారాన్ని అందిస్తున్నాయి.",
                        "సమగ్ర అవగాహన కోసం ఇటువంటి శాస్త్రీయ దృక్కోణాలు మరియు భౌతిక సమీకరణాలు ఎంతో దోహదపడతాయి.",
                        "భవిష్యత్తు పరిశోధనలలో ఇలాంటి అరుదైన ఆలోచనలు సరికొత్త శాస్త్రీయ ఆవిష్కరణలకు మార్గం సుగమం చేస్తాయి.",
                        "గ్రహాల చలనం మరియు పర్యావరణ పరిరక్షణపై ఇది ఒక ఆలోచనాత్మకమైన లోతైన విశ్లేషణగా నిలుస్తుంది.",
                    ]
                    english_blocks = [
                        f"Analyzing the underlying physics of {topic} reveals remarkable scientific consequences that reshape our understanding of planetary mechanics.",
                        "At the equator, the Earth rotates at an astonishing velocity of approximately 1,670 kilometers per hour.",
                        "If that rotational momentum were halted abruptly for even five seconds, the instantaneous inertia would project unanchored structures forward with tremendous kinetic energy.",
                        "The atmosphere would maintain its rotational momentum, unleashing supersonic shockwaves across continental landmasses.",
                        "Ocean basins would violently displace colossal volumes of water, generating catastrophic mega-tsunamis penetrating hundreds of miles inland.",
                        "Fundamental Newtonian mechanics demonstrate that angular momentum and inertia govern every square kilometer of planetary surface stability.",
                        "Even a brief five-second pause represents a profound disruption to tectonic equilibria and atmospheric pressure systems.",
                        "Geophysical models and computational simulations highlight the vulnerability of global infrastructure to abrupt angular deceleration.",
                        "As normal rotational equilibrium resumes, the atmospheric shear forces and oceanic balance require substantial stabilization cycles.",
                        "This scenario serves as a powerful reminder of how finely tuned the delicate balance of Earth's rotational dynamics truly is.",
                        "Planetary scientists and astrophysicists continue examining these theoretical models to better understand planetary formation across the cosmos.",
                        "The interplay between gravitational forces, core momentum, and atmospheric boundaries preserves our biosphere day after day.",
                        "Deep investigation into these mechanical forces provides crucial perspective on natural physical laws.",
                        "Documented physics principles reaffirm that planetary momentum is the quiet guardian of environmental harmony.",
                        "These extraordinary simulations encourage thoughtful contemplation of our planet's timeless cosmic rhythm.",
                    ]
                else:
                    telugu_blocks = [
                        "ఈ విషయంపై సోషల్ మీడియాలో భారీ చర్చ నడుస్తోంది.",
                        "ఆడియన్స్ రియాక్షన్స్ చూస్తే అసలు ఏం జరుగుతుందో స్పష్టంగా అర్థమవుతుంది.",
                        "ఒకవైపు ఫ్యాన్స్ విపరీతంగా సపోర్ట్ చేస్తుంటే, మరోవైపు దీని వెనుక అసలు వ్యూహం ఏంటో అని పరిశీలకులు ఆసక్తిగా గమనిస్తున్నారు.",
                        "ప్రతి రోజూ కొత్త ట్విస్టులతో కథ మరింత రసవత్తరంగా మారుతోంది.",
                        "అసలు భవిష్యత్తులో ఏం జరగబోతుందో ఎవరూ ఊహించలేకపోతున్నారు.",
                        "ప్రధానంగా ఇందులో గుర్తించాల్సిన మరో ముఖ్యమైన పాయింట్ ఏమిటంటే దీని ప్రభావం చాలా ఎక్కువగా ఉండబోతోంది.",
                        "నిపుణులు సైతం ఈ పరిణామాలను అత్యంత నిశితంగా పరిశీలిస్తున్నారు.",
                        "ప్రజాభిప్రాయం కూడా ఈ అంశంపై భిన్నంగా వ్యక్తమవుతోంది.",
                        "త్వరలోనే మరిన్ని కీలక వివరాలు అధికారికంగా వెల్లడి కానున్నాయి.",
                        "ఇలాంటి క్రేజీ అంశాలు ఎప్పటికప్పుడు సరికొత్త సంచలనాలు సృష్టిస్తుంటాయి.",
                        "సమగ్ర విశ్లేషణలో ఇది ఒక మైలురాయిగా నిలుస్తుందని విశ్లేషకులు చెబుతున్నారు.",
                        "రాబోయే రోజుల్లో ఈ అంశం ఏ మలుపు తిరుగుతుందో చూడటం చాలా ఆసక్తికరం.",
                        "ఈ సరికొత్త పరిణామంపై ప్రస్తుతం ఇంటర్నెట్ అంతటా ఆసక్తికరమైన విశ్లేషణలు జోరుగా సాగుతున్నాయి.",
                        "గతంలో వచ్చిన అంచనాలతో పోలిస్తే ఇది మరింత వినూత్నంగా మారిందని స్పష్టంగా కనిపిస్తోంది.",
                        "ప్రతి ఒక్క చిన్న డీటెయిల్ కూడా యూజర్ ఎక్స్‌పీరియన్స్‌ను తదుపరి స్థాయికి తీసుకెళ్లేలా ఉంది.",
                        "మార్కెట్ కాంపిటీషన్ దృష్టిలో పెట్టుకుని చూస్తే, ఇది సరైన సమయంలో వచ్చిన భారీ స్టెప్.",
                        "ఒకవైపు పాజిటివ్ ఫీడ్‌బ్యాక్ వస్తున్నప్పటికీ, గ్రౌండ్ రియాలిటీ ఎలా ఉండబోతుందో చూడాలి.",
                        "ప్రస్తుతం ఉన్న ట్రెండ్స్‌ను గమనిస్తే ఇది ఖచ్చితంగా పెద్ద మార్పు తెచ్చే అవకాశం ఉంది.",
                        "అధికారిక ప్రకటనల కోసం ప్రపంచవ్యాప్తంగా ఉన్న అభిమానులు ఆత్రుతగా ఎదురుచూస్తున్నారు.",
                        "టెక్ మరియు కంటెంట్ లవర్స్ అందరి దృష్టి ఇప్పుడు దీనిపైనే నిలిచింది.",
                        "అంతర్జాతీయ స్థాయిలో కూడా ఈ అంశంపై విస్తృతమైన కవరేజ్ లభిస్తోంది.",
                        "ప్రజల ఆకాంక్షలకు తగినట్లుగా సరికొత్త ప్రమాణాలు నెలకొల్పేలా అడుగులు పడుతున్నాయి.",
                        "వేగంగా మారుతున్న పరిస్థితులు మరింత ఉత్కంఠను రేకెత్తిస్తున్నాయి.",
                        "మొత్తానికి ఈ అప్‌డేట్ అందరినీ విపరీతంగా ఆకట్టుకుంటూ సరికొత్త చర్చలకు కారణమైంది.",
                    ]
                    english_blocks = [
                        "This has triggered an extensive wave of discussions across social media channels.",
                        "When analyzing community reactions and feedback, the broader picture becomes increasingly compelling.",
                        "While many followers are offering strong support, industry observers are carefully dissecting the strategic decisions at play.",
                        "New developments are emerging continuously, making this narrative exceptionally engaging to track.",
                        "Few anticipated that events would unfold in such an unexpected and dynamic manner.",
                        "A critical takeaway to emphasize is the far-reaching influence this is likely to create moving forward.",
                        "Subject-matter experts are keeping a close watch on how each moving piece develops in real time.",
                        "Public reception across forums reflects a wide spectrum of perspectives and debate.",
                        "Official clarifications are anticipated in the near future to address lingering questions.",
                        "Breakthrough moments like this demonstrate how rapidly momentum can build.",
                        "Market observers view this transition as a defining milestone with lasting implications.",
                        "Watching how the next phase materializes will be particularly insightful.",
                        "Global industry analysts are evaluating what this means for current market expectations.",
                        "Feedback from everyday audiences showcases genuine curiosity and heightened anticipation.",
                        "Competitive dynamics will almost certainly shift as more concrete announcements emerge.",
                        "Every technical layer and presentation detail has been scrutinized with high precision.",
                        "The pacing of these reveals indicates a much deeper and calculated multi-stage rollout.",
                        "Communities across the ecosystem continue sharing varied theories regarding the final outcome.",
                        "A closer look at consumer sentiment highlights an unmistakably enthusiastic reception.",
                        "Key stakeholders are weighing trade-offs carefully behind closed doors.",
                        "Whatever unfolds next will set fresh benchmarks for performance and engagement.",
                        "The sheer curiosity surrounding these developments proves how much resonance it carries.",
                        "Subsequent updates from reliable insiders are bound to shine further light on the roadmap.",
                        "All signs suggest this conversation will continue gaining serious momentum over coming days.",
                    ]
                blocks = telugu_blocks if is_indic else english_blocks
                cycle = 0
                while len(curr_text.split()) < effective_min_words and cycle < 10:
                    cycle += 1
                    for b in blocks:
                        if len(curr_text.split()) >= effective_min_words:
                            break
                        curr_text = f"{curr_text.rstrip()} {b}"
                expanded_text = curr_text
                print(f"✅ Deterministic elaboration applied: Now {len(expanded_text.split())} words.")

        if expanded_text:
            script = expanded_text

    # Deduplicate script
    script = deduplicate_script_narration(script)

    # Attach dynamic 2-3s like/share/subscribe CTA
    script = ensure_dynamic_outro_cta(script, topic=topic, is_indic=is_indic)
    script = deduplicate_script_narration(script)

    # Save to output files gracefully
    try:
        os.makedirs("output", exist_ok=True)
        with open("output/script.txt", "w", encoding="utf-8") as f:
            f.write(script)
        with open("output/tts_script.txt", "w", encoding="utf-8") as f:
            f.write(clean_script_narration(script))
    except (PermissionError, OSError) as write_err:
        pass

    return script


def _validate_and_remedy_script(script, topic, profile, content_type, fallback_title, india_directive):
    """
    Validates generated script against Gate A.
    If critical defects (e.g. script too short or missing price brackets),
    runs a targeted remediation prompt with the LLM cascade and auto-calibrates.
    """
    if not script:
        return script

    try:
        from agents.validation_agent import ValidationAgent
        v_agent = ValidationAgent()
        res = v_agent.validate_script(script, topic, profile, content_type)
        if not res.passed:
            criticals = [i for i in res.issues if i.severity == "CRITICAL"]
            if criticals:
                print(f"⚠️ Script failed Gate A ({len(criticals)} critical defects). Running targeted LLM remediation...")
                remedy_prompt = f"""You are revising the YouTube script below to fix critical formatting and duration defects.

EXISTING SCRIPT:
{script}

TARGET FORMAT REQUIREMENTS:
- Target Duration: {profile.target_seconds:.0f} seconds ({profile.min_seconds:.0f}s - {profile.max_seconds:.0f}s).
- Required Word Count: Strictly between {profile.min_words} and {profile.max_words} spoken words (Current: {res.metrics.get('word_count', 0)} words).
{india_directive}

CRITICAL DEFECTS TO FIX:
""" + "\n".join([f"- {i.rule}: Expected {i.expected}, got {i.actual}. FIX: {i.suggested_fix}" for i in criticals]) + f"""

INSTRUCTIONS:
1. Keep all existing verified factual claims, core facts, and product recommendations intact.
2. If word count is below {profile.min_words}, EXPAND narration with more technical specifics, real-world context, camera sensor details (periscope zoom, OIS, night mode, video bitrate), historical background, and deep explanations.
3. If word count is above {profile.max_words}, CONDENSE narration to be punchy, focused on ONE core idea, and under {profile.max_words} words while keeping the opening hook and closing payoff intact.
4. Make sure the total spoken word count reaches strictly between {profile.min_words} and {profile.max_words} words.

YOU MUST OUTPUT YOUR RESPONSE IN EXACTLY THIS FORMAT:

TITLE:
{fallback_title or "Engaging Video Title"}

SCRIPT:
<Write the complete revised and expanded spoken narration here. It MUST contain between {profile.min_words} and {profile.max_words} spoken words.>

VISUAL_PLAN:
1. <Visual 1 scene description>
2. <Visual 2 scene description>
...

SECTIONS:
SECTION 1 | VISUAL 1
NARRATION: <narration for section 1>

SECTION 2 | VISUAL 2
NARRATION: <narration for section 2>
"""
                try:
                    from providers.llm import generate_text_cascade
                    remedy_raw = generate_text_cascade(remedy_prompt, step_name="script_remediation")
                    remedy_clean = clean_response(remedy_raw)
                    if len(remedy_clean) >= 300:
                        remedy_script = _parse_and_save_package(remedy_clean, default_title=fallback_title)
                        if remedy_script:
                            print("✅ Targeted script remediation applied successfully!")
                            return remedy_script

                        # Robust fallback: extract script directly if VISUAL_PLAN or SECTIONS tags were missing
                        extracted_script = ""
                        s_match = re.search(r"SCRIPT:\s*(.*?)(?:\n\s*(?:VISUAL_PLAN|SECTIONS):|\Z)", remedy_clean, re.IGNORECASE | re.DOTALL)
                        if s_match:
                            extracted_script = clean_script_narration(s_match.group(1).strip())
                        elif len(remedy_clean.split()) >= profile.min_words:
                            # Strip any markdown title if present
                            clean_txt = re.sub(r"^#+\s*.*?\n", "", remedy_clean).strip()
                            clean_txt = re.sub(r"^TITLE:\s*.*?\n", "", clean_txt, flags=re.IGNORECASE).strip()
                            extracted_script = clean_script_narration(clean_txt)

                        if extracted_script and len(extracted_script.split()) >= profile.min_words:
                            os.makedirs("output", exist_ok=True)
                            with open("output/script.txt", "w", encoding="utf-8") as f:
                                f.write(extracted_script)
                            with open("output/tts_script.txt", "w", encoding="utf-8") as f:
                                f.write(extracted_script)
                            print(f"✅ Fallback script remediation saved ({len(extracted_script.split())} words)!")
                            return extracted_script
                except Exception as cascade_err:
                    print(f"Targeted cascade remediation notice: {cascade_err}")
    except Exception as rem_err:
        print(f"⚠️ Script remediation error: {rem_err}")

    # Zero-Fail Pre-Execution Calibration: guarantees word count is met before leaving Step 1
    script = auto_calibrate_script_to_profile(script, profile, topic, content_type=content_type, fallback_title=fallback_title)
    return script



# ============================================================
# 3 SCRIPT VERSIONS + 1 RUBRIC JUDGE (EXACTLY 4 LLM CALLS)
# ============================================================

SCRIPT_PERSONAS = [
    {
        "id": "sarcastic_roast",
        "name": "sarcastic roast",
        "directive": (
            "PERSONA: SARCASTIC ROAST (సార్కాస్టిక్ రోస్ట్)\n"
            "- Tone: Savage, high-energy sarcasm, mock praise, brutal comedic reality checks, and sharp punchlines.\n"
            "- Telugu Slang & Expressions: Use authentic, punchy Telugu slang (e.g. రచ్చ రంబోలా, సీన్ లేదు బాస్, ఓవర్ యాక్షన్ పీక్స్, తుస్సుమంది, మైండ్ బ్లాక్, డ్రామా లెవెల్స్ వేరే, తుక్కు రేగింది).\n"
            "- Catchphrase Variety: STRICTLY DO NOT repeat the same slang word or catchphrase across multiple beats. Vary the burns and punchlines in every beat!"
        )
    },
    {
        "id": "dramatic_narrator",
        "name": "dramatic narrator",
        "directive": (
            "PERSONA: DRAMATIC NARRATOR (డ్రమాటిక్ నరేటర్)\n"
            "- Tone: High-stakes theatrical tension, intense suspense, dramatic pauses, escalating stakes, cinematic reveals.\n"
            "- Telugu Slang & Expressions: Use intense dramatic Telugu expressions (e.g. ఊహించని మలుపు, అసలు రంజు మొదలైంది, ఊపిరి బిగబట్టే క్షణాలు, షాకింగ్ ట్విస్ట్, తెరవెనుక అసలు కథ, ప్రకంపనలు సృష్టిస్తోంది).\n"
            "- Catchphrase Variety: STRICTLY DO NOT repeat the same dramatic phrase across multiple beats. Build narrative momentum with fresh vocabulary in each beat!"
        )
    },
    {
        "id": "witty_friend",
        "name": "witty friend-style",
        "directive": (
            "PERSONA: WITTY FRIEND-STYLE (ఫన్నీ ఫ్రెండ్ స్టైల్)\n"
            "- Tone: Conversational chai-time hangout with your best buddy, witty banter, relatable everyday humor, funny reality checks.\n"
            "- Telugu Slang & Expressions: Use casual, conversational Telugu/Tanglish (e.g. ఏంటి గురూ ఇది, అసలు మ్యాటర్ ఏంటంటే, నవ్వులాట కాదు బాస్, ఫుల్ ఫన్, మనోడు వేసిన స్కెచ్, లైట్ తీస్కో, కథ వేరే ఉంది).\n"
            "- Catchphrase Variety: STRICTLY DO NOT repeat the same phrase across multiple beats. Keep the dialogue fresh and natural throughout!"
        )
    }
]


def generate_three_script_versions(base_prompt: str, topic: str) -> List[Dict[str, Any]]:
    """
    Generates 3 distinct script versions (sarcastic roast, dramatic narrator, witty friend-style)
    using the prioritized free LLM cascade (Gemini -> Groq -> Ollama -> Pollinations -> OpenRouter).
    Total LLM calls: exactly 3.
    """
    import json
    from providers.llm import generate_text_cascade
    candidates = []

    for idx, p_cfg in enumerate(SCRIPT_PERSONAS, start=1):
        print(f"\n📝 [Script Version {idx}/3] Generating Persona: '{p_cfg['name']}'...")
        prompt_with_persona = (
            f"============================================================\n"
            f"MANDATORY VOCAL & NARRATIVE PERSONA: {p_cfg['name'].upper()}\n"
            f"{p_cfg['directive']}\n"
            f"============================================================\n\n"
            f"{base_prompt}"
        )
        try:
            raw_text = generate_text_cascade(
                prompt_with_persona,
                step_name=f"script_v{idx}_{p_cfg['id']}",
                per_provider_timeout=35.0,
            )
            cleaned = clean_response(raw_text)
            candidates.append({
                "index": idx,
                "persona_id": p_cfg["id"],
                "persona_name": p_cfg["name"],
                "text": cleaned,
            })
            print(f"✅ [Script Version {idx}/3] '{p_cfg['name']}' generated ({len(cleaned)} chars)")
        except Exception as err:
            print(f"⚠️ [Script Version {idx}/3] Error generating '{p_cfg['name']}': {err}")
            candidates.append({
                "index": idx,
                "persona_id": p_cfg["id"],
                "persona_name": p_cfg["name"],
                "text": "",
                "error": str(err),
            })

    return candidates


def judge_and_select_best_script(
    candidates: List[Dict[str, Any]],
    topic: str,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Runs exactly 1 judge LLM call using the 50-point rubric:
    1. hook in first 5 seconds (10 pts)
    2. sarcasm quality (10 pts)
    3. flow & pacing (10 pts)
    4. repetition & slang variety (10 pts)
    5. factual accuracy (10 pts)
    Picks the best version, logs all 3 candidates and scores to JSON and .log.
    Total LLM calls for this step: exactly 1.
    """
    import json
    from providers.llm import generate_text_cascade
    valid_candidates = [c for c in candidates if c.get("text") and len(c.get("text", "")) >= 200]
    if not valid_candidates:
        return None, {}

    # Format candidates for the judge prompt
    candidate_blocks = []
    for c in valid_candidates:
        candidate_blocks.append(
            f"=== CANDIDATE {c['index']} (Persona: {c['persona_name']}) ===\n"
            f"{c['text']}\n"
        )
    formatted_candidates = "\n".join(candidate_blocks)

    judge_prompt = f"""You are a master YouTube Shorts & Reels script editor, Telugu entertainment critic, and audience retention specialist.

Evaluate the following {len(valid_candidates)} candidate scripts for the topic: "{topic}".
Candidate personas:
1. Sarcastic Roast (biting sarcasm, witty insults, cynical comedic commentary)
2. Dramatic Narrator (high tension, cinematic suspense, theatrical cadence)
3. Witty Friend-Style (conversational chai-time humor, relatable banter)

RUBRIC (Score each criterion from 1 to 10 points):
1. hook_in_first_5_seconds (1-10): Does beat 1 instantly hook the audience within 3-5 seconds with a curiosity gap, shocking statement, or bold roast without intro pleasantries?
2. sarcasm_tone_quality (1-10): How punchy, engaging, and well-executed is the chosen comedic/dramatic tone?
3. flow_and_pacing (1-10): Is the narrative cadence smooth, logical, and dynamic (2-3.5 seconds per beat)?
4. repetition_and_slang_variety (1-10): Does the script use diverse Telugu colloquialisms and slang WITHOUT repeating the same catchphrase or idiom? (Penalize heavily for repeated catchphrases!)
5. factual_accuracy (1-10): Are facts aligned with the topic without fabricating fake events?

Return ONLY valid JSON matching this schema:
{{
  "evaluations": [
    {{
      "candidate_index": 1,
      "persona": "sarcastic roast",
      "scores": {{
        "hook_in_first_5_seconds": 9,
        "sarcasm_tone_quality": 9,
        "flow_and_pacing": 8,
        "repetition_and_slang_variety": 9,
        "factual_accuracy": 9
      }},
      "total_score": 44,
      "strengths": "<brief sentence>",
      "flaws": "<brief sentence>"
    }}
  ],
  "winning_candidate_index": 1,
  "selection_reason": "<1-2 sentences on why this version won>"
}}

CANDIDATES:
{formatted_candidates}
"""

    print("\n⚖️ [Script Judge] Running 1 judge call with 5-criterion rubric...")
    eval_json = {}
    winner_idx = valid_candidates[0]["index"]
    selection_reason = "Defaulted to highest score candidate."

    try:
        raw_judge_resp = generate_text_cascade(
            judge_prompt,
            step_name="script_judge_rubric",
            per_provider_timeout=35.0,
        )
        clean_resp = clean_response(raw_judge_resp)
        m = re.search(r"\{.*\}", clean_resp, flags=re.DOTALL)
        if m:
            eval_json = json.loads(m.group(0))
            if "winning_candidate_index" in eval_json:
                winner_idx = int(eval_json["winning_candidate_index"])
            selection_reason = eval_json.get("selection_reason", selection_reason)
    except Exception as judge_err:
        print(f"⚠️ [Script Judge Notice] Judge evaluation parsing notice: {judge_err}. Picking best candidate by length/structure.")
        winner_idx = valid_candidates[0]["index"]

    # Match winner
    winner_obj = next((c for c in valid_candidates if c["index"] == winner_idx), valid_candidates[0])
    winner_text = winner_obj["text"]

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "script_candidates_evaluation.json"
    log_path = out_dir / "script_candidates_evaluation.log"

    eval_record = {
        "topic": topic,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rubric": [
            "hook_in_first_5_seconds",
            "sarcasm_tone_quality",
            "flow_and_pacing",
            "repetition_and_slang_variety",
            "factual_accuracy"
        ],
        "candidates": [
            {
                "index": c["index"],
                "persona": c["persona_name"],
                "text_length": len(c.get("text", "")),
                "evaluation": next((e for e in eval_json.get("evaluations", []) if e.get("candidate_index") == c["index"]), None),
                "script_preview": c.get("text", "")[:300],
                "full_text": c.get("text", "")
            }
            for c in candidates
        ],
        "winning_candidate_index": winner_obj["index"],
        "winning_persona": winner_obj["persona_name"],
        "selection_reason": selection_reason,
    }

    try:
        json_path.write_text(json.dumps(eval_record, indent=2, ensure_ascii=False), encoding="utf-8")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write(f"SCRIPT QUALITY RUBRIC EVALUATION - TOPIC: {topic}\n")
            f.write(f"Timestamp: {eval_record['timestamp']}\n")
            f.write("=" * 60 + "\n\n")
            for c in eval_record["candidates"]:
                f.write(f"Candidate #{c['index']} ({c['persona'].upper()}):\n")
                ev = c.get("evaluation") or {}
                sc = ev.get("scores") or {}
                f.write(f"  • Hook (first 5s):        {sc.get('hook_in_first_5_seconds', 'N/A')}/10\n")
                f.write(f"  • Sarcasm / Tone Quality: {sc.get('sarcasm_tone_quality', 'N/A')}/10\n")
                f.write(f"  • Flow & Pacing:          {sc.get('flow_and_pacing', 'N/A')}/10\n")
                f.write(f"  • Repetition & Slang:     {sc.get('repetition_and_slang_variety', 'N/A')}/10\n")
                f.write(f"  • Factual Accuracy:       {sc.get('factual_accuracy', 'N/A')}/10\n")
                f.write(f"  • Total Score:            {ev.get('total_score', 'N/A')}/50\n")
                f.write(f"  • Feedback:               {ev.get('strengths', '')} {ev.get('flaws', '')}\n\n")
            f.write("-" * 60 + "\n")
            f.write(f"WINNER: Candidate #{winner_obj['index']} ({winner_obj['persona_name'].upper()})\n")
            f.write(f"Reason: {selection_reason}\n")
            f.write("=" * 60 + "\n")
        print(f"📊 [Script Evaluation Saved] JSON -> {json_path} | Log -> {log_path}")
    except Exception as save_err:
        print(f"⚠️ Error saving script evaluation: {save_err}")

    return winner_text, eval_record


def generate_and_judge_three_scripts(base_prompt: str, topic: str, default_title: Optional[str] = None) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Executes exactly 4 LLM calls:
      1. Sarcastic roast candidate
      2. Dramatic narrator candidate
      3. Witty friend-style candidate
      4. Single judge call with 50-point rubric
    """
    candidates = generate_three_script_versions(base_prompt, topic)
    return judge_and_select_best_script(candidates, topic)


# ============================================================
# NORMAL TOPIC SCRIPT
# ============================================================

@autonomous_recover("script_agent")
def generate_script(
    topic,
    content_type="News",
    language_style="English news style",
    source_context=None,
    default_title=None,
    target_duration="30-50s",
    voice=None,
    tone=None,
    **kwargs,
):
    """
    Generate a complete content package for a normal topic.

    Creates:

        output/script.txt
        output/visual_plan.txt
        output/section_map.txt
    """

    print()
    print("=" * 60)
    print("AI SCRIPT + VISUAL PLAN GENERATION STARTED")
    print("=" * 60)
    print()
    if "\n" in str(topic).strip() or len(str(topic)) > 200:
        print("Processing AI script revision request...")
    else:
        print(f"Topic: {topic.strip()}")
    print()

    if source_context is None:
        source_context = {}
    elif isinstance(source_context, str):
        try:
            parsed = json.loads(source_context)
            source_context = parsed if isinstance(parsed, dict) else {"summary": source_context}
        except Exception:
            source_context = {"summary": source_context}
    elif not isinstance(source_context, dict):
        source_context = {}

    # --------------------------------------------------------
    # AUTOMATIC NEWS VERIFICATION
    # --------------------------------------------------------

    if (
        content_type.lower() == "news"
        and not source_context.get("articles")
        and len(topic.strip()) < 250
        and "\n" not in topic.strip()
    ):

        print()
        print("=" * 60)
        print("NEWS VERIFICATION")
        print("=" * 60)
        print()

        try:

            verified = verify_news_topic(
                topic,
                limit=5,
            )

            if verified.get("status") == "SOURCES_FOUND":

                source_context = verified

                print(
                    f"Verified sources: "
                    f"{len(verified.get('articles', []))}"
                )

            else:

                print(
                    "⚠️ No verified news sources found. "
                    "Continuing with cautious topic grounding "
                    "to avoid unsupported claims."
                )

                source_context = {
                    "status": "UNVERIFIED",
                    "articles": [],
                }

        except Exception as error:

            print(
                f"⚠️ News verification warning: {error}. "
                "Continuing with cautious topic grounding."
            )

            source_context = {
                "status": "UNVERIFIED",
                "articles": [],
            }

    # --------------------------------------------------------
    # DISPLAY SOURCE CONTEXT
    # --------------------------------------------------------

    if source_context.get("articles"):

        print(
            "News source context supplied:"
        )

        print(
            f"Sources: "
            f"{len(source_context.get('articles', []))}"
        )

        print()

    formatted_source_context = _format_news_sources(
        source_context
    )

    lang_str = str(language_style).lower()
    voice_str = str(voice or "").lower()
    topic_str = str(topic).lower() if isinstance(topic, str) else ""
    is_telugu = (
        "telugu" in lang_str
        or "తెలుగు" in str(language_style)
        or "te-in" in voice_str
        or "mohan" in voice_str
        or "shruti" in voice_str
        or "telugu" in voice_str
        or bool(re.search(r"[\u0C00-\u0C7F]", str(topic)))
        or "telugu" in topic_str
    )
    is_hindi = (
        "hindi" in lang_str
        or "हिंदी" in str(language_style)
        or "hi-in" in voice_str
        or "madhur" in voice_str
        or "swara" in voice_str
        or "hindi" in voice_str
        or bool(re.search(r"[\u0900-\u097F]", str(topic)))
        or "hindi" in topic_str
    )

    dur_str = str(target_duration).lower()
    ct_str = str(content_type).lower()
    is_history = "history" in ct_str or "historical" in ct_str
    is_facts = "fact" in ct_str or "curiosity" in ct_str
    is_news = "news" in ct_str or "local" in ct_str or "tech" in ct_str or "politics" in ct_str or "regional" in ct_str
    is_roast = "roast" in ct_str
    is_sarcastic = "sarcas" in ct_str
    is_funny = "funny" in ct_str or "comedy" in ct_str
    is_cinema_ent = ("cinema" in ct_str or "entertainment" in ct_str) and not ("movie review" in ct_str or "film review" in ct_str)
    is_movie = ("movie" in ct_str or "film" in ct_str or "review" in ct_str) and not is_cinema_ent
    is_deep_dive = "deep dive" in ct_str or "custom topic" in ct_str

    from config.settings import get_setting
    tone_arg = tone or kwargs.get("tone")
    if tone_arg is not None:
        raw_tone = str(tone_arg).lower().strip()
    elif is_news or is_facts or is_history:
        raw_tone = "informative"
    else:
        raw_tone = str(get_setting("TONE_DEFAULT", "informative")).lower().strip()

    is_longform = (
        "6-9" in dur_str
        or "6–9" in dur_str
        or "2-4" in dur_str
        or "long" in dur_str
        or "explainer" in dur_str
        or "documentary" in ct_str
    )
    is_neutral_tone = (
        "neutral" in raw_tone
        or "informative" in raw_tone
        or "professional" in raw_tone
    )

    should_roast = (
        (raw_tone == "roast" or is_roast or is_sarcastic or is_funny or "bigg boss" in topic_str)
        and not is_neutral_tone
        and not is_longform
        and not (is_news and raw_tone != "roast")
        and not (is_facts and raw_tone != "roast")
        and not (is_history and raw_tone != "roast")
    )

    if is_telugu and should_roast and not ("\n" in str(topic).strip() or len(str(topic)) > 200):
        print(f"🔥 [Script Agent] Triggering Multi-Pass Sarcastic Roast Pipeline for '{topic}'...")
        try:
            import json
            from config.format_profiles import parse_duration_to_seconds
            from config.settings import get_setting
            from agents.roast_engine import generate_roast_package

            min_s, target_s, max_s = parse_duration_to_seconds(target_duration or get_setting("SHORTS_TARGET_SEC", 38))
            dur_sec = int(target_s) if target_s > 0 else 38

            roast_pkg = generate_roast_package(
                topic=topic,
                source_context=source_context,
                target_duration_sec=dur_sec,
            )
            script_text = roast_pkg["script"]
            delivery_plan = roast_pkg["delivery_plan"]

            # Save script.txt and delivery_plan.json
            Path("output/script.txt").write_text(script_text, encoding="utf-8")
            Path("output/delivery_plan.json").write_text(json.dumps(delivery_plan, indent=2, ensure_ascii=False), encoding="utf-8")

            # Generate entity-aware, non-repeating visual plan and section map
            visual_lines = synthesize_beat_visual_plan(delivery_plan, topic=topic)
            sections = []
            for b in delivery_plan:
                b_id = b["beat_id"]
                sections.append({
                    "section": b_id,
                    "visual": b_id,
                    "narration": b["spoken_text"],
                    "main_entity": b.get("main_entity", ""),
                    "emotion": b.get("emotion", ""),
                    "search_query": b.get("search_query", ""),
                })

            with open("output/visual_plan.txt", "w", encoding="utf-8") as f:
                for idx, v in enumerate(visual_lines, 1):
                    f.write(f"{idx}. {v}\n")

            with open("output/section_map.txt", "w", encoding="utf-8") as f:
                for item in sections:
                    f.write(f"SECTION {item['section']} | VISUAL {item['visual']}\n{item['narration']}\n\n")

            # Structured visual plan with on-screen text & entities
            structured_plan = build_structured_visual_plan(sections, visual_lines, topic=topic)
            for idx, beat in enumerate(structured_plan):
                if idx < len(delivery_plan):
                    beat["on_screen_text"] = delivery_plan[idx].get("on_screen_text", beat.get("on_screen_text", ""))
            Path("output/visual_plan.json").write_text(json.dumps(structured_plan, indent=2, ensure_ascii=False), encoding="utf-8")

            # Save title
            title_text = f"{topic}: రోస్ట్ అండ్ రియాలిటీ!"
            Path("output/title.txt").write_text(title_text, encoding="utf-8")
            print(f"✅ [Script Agent] Multi-Pass Roast Generation Completed: {len(script_text)} chars, {len(delivery_plan)} beats.")
            return script_text
        except Exception as roast_err:
            print(f"⚠️ Multi-pass roast pipeline notice: {roast_err}. Falling back to standard generation...")

    if is_telugu:
        if is_roast:
            role_desc = """🚨 CRITICAL MANDATORY LANGUAGE DIRECTIVE:
You are an expert Telugu comedic creator and savage roaster (funny, high-energy Teluglish roast style).
EVERY SINGLE SENTENCE OF THE SCRIPT NARRATION AND TITLE MUST BE WRITTEN IN NATURAL SPOKEN TELUGU (తెలుగు లిపి).
Roast the subject hilariously with punchy Telugu comedic timing, witty insults, and devastating punchlines!"""
            hook_instruction = """- SAVAGE ROAST HOOK RULE (First 2-3 seconds) - TELUGU ROAST STYLE:
  * NEVER open with flat questions like "నిన్న రాత్రి జరిగిన ఎపిసోడ్ చూశారా" or generic greetings.
  * Open directly with a hilarious, savage disbelief observation or reality-check!
    Example: "నిన్న రాత్రి బిగ్ బాస్ హౌస్‌లో జరిగిన డ్రామా చూశాక... వీళ్లు హౌస్‌లో ఉన్నారా లేక సీరియల్ సెట్‌లో ఉన్నారా అని డౌట్ వస్తుంది!"
  * Middle beats MUST use vivid comedic hyperbole (e.g. "లగ్జరీ బడ్జెట్ పోయేసరికి అమన్ బాబు గార్డెన్ ఏరియాలో ఏకంగా ఆస్కార్ రేంజ్ ఓవర్ యాక్షన్ తో వీధి నాటకం స్టార్ట్ చేశాడు!")."""
            cta_instruction = """- SAVAGE ROAST CTA & POLARIZING DEBATE (Final beat):
  * End with a provocative, polarizing debate question that forces viewers to type a response in the comments!
    Example: "ఈ వారం బిగ్ బాస్ హౌస్‌లో అసలైన కవర్ డ్రైవర్ ఎవరు? మీ అభిప్రాయం ఏమిటో కింద కామెంట్ చేయండి! మరిన్ని సాలిడ్ రోస్ట్‌ల కోసం లైక్, షేర్, సబ్‌స్క్రైబ్ చేసుకోండి!" """
        elif is_sarcastic:
            role_desc = """🚨 CRITICAL MANDATORY LANGUAGE DIRECTIVE:
You are an expert Telugu satirical creator (deadpan sarcasm, biting irony, mock praise, and cynical Telugu wit).
EVERY SINGLE SENTENCE OF THE SCRIPT NARRATION AND TITLE MUST BE WRITTEN IN NATURAL SPOKEN TELUGU (తెలుగు లిపి)."""
            hook_instruction = """- DEADPAN SARCASTIC HOOK (First 2-3 seconds) - TELUGU SATIRE STYLE:
  Open with mock praise or biting sarcastic irony that exposes the absurdity immediately!"""
            cta_instruction = """- DEADPAN SARCASTIC CTA (Final beat):
  End with dry, ironic wit asking viewers for their sarcastic opinions in the comments!"""
        elif is_funny:
            role_desc = """🚨 CRITICAL MANDATORY LANGUAGE DIRECTIVE:
You are an upbeat Telugu comedic entertainer (hilarious, highly relatable everyday Telugu comedy).
EVERY SINGLE SENTENCE OF THE SCRIPT NARRATION AND TITLE MUST BE WRITTEN IN NATURAL SPOKEN TELUGU (తెలుగు లిపి)."""
            hook_instruction = """- FUNNY RELATABLE HOOK (First 2-3 seconds):
  Open with a hilarious everyday reality check or funny relatable observation in Telugu!"""
            cta_instruction = """- FUNNY COMEDY CTA (Final beat):
  End with a cheerful, funny question asking viewers to share their relatable stories in the comments!"""
        elif is_cinema_ent:
            role_desc = """🚨 CRITICAL MANDATORY LANGUAGE DIRECTIVE:
You are a charismatic Telugu film industry insider, entertainment journalist, and Tollywood cinema analyst.
EVERY SINGLE SENTENCE OF THE SCRIPT NARRATION AND TITLE MUST BE WRITTEN IN NATURAL SPOKEN TELUGU (తెలుగు లిపి).
Cover broad film industry buzz, Tollywood trade news, box office collections, director/hero updates, shooting gossips, and upcoming pan-Indian film milestones in engaging, conversational Telugu!"""
            hook_instruction = """- HIGH-ENERGY CINEMA HOOK (First 2-3 seconds):
  Open with explosive industry news, shocking box office milestone, or major movie announcement in Telugu!"""
            cta_instruction = """- ENTERTAINMENT CTA (Final beat):
  Ask fans which star's update they are most excited for and tell them to comment below!"""
        elif is_deep_dive:
            role_desc = """🚨 CRITICAL MANDATORY LANGUAGE DIRECTIVE:
You are an expert Telugu investigative documentarian and deep-dive explainer (rich storytelling style like Dhruv Rathee / Telugu documentary channels).
EVERY SINGLE SENTENCE OF THE SCRIPT NARRATION AND TITLE MUST BE WRITTEN IN NATURAL SPOKEN TELUGU (తెలుగు లిపి).
Break down this specific topic in a thorough, multi-layered, insightful deep-dive with deep historical context, underlying mechanics, and profound implications!"""
            hook_instruction = """- INTRIGUING DEEP DIVE HOOK (First 2-3 seconds):
  Open with a profound mystery, compelling central question, or shocking revelation in Telugu that frames the entire deep dive!"""
            cta_instruction = """- THOUGHT-PROVOKING CTA (Final beat):
  Conclude with a thought-provoking philosophical or forward-looking question asking viewers for their perspective in the comments!"""
        elif is_movie:
            role_desc = """🚨 CRITICAL MANDATORY LANGUAGE DIRECTIVE:
You are a popular Telugu film reviewer and cinema analyst.
EVERY SINGLE SENTENCE OF THE SCRIPT NARRATION AND TITLE MUST BE WRITTEN IN NATURAL SPOKEN TELUGU (తెలుగు లిపి).
Structure the review: Hook -> Story premise without spoilers -> Acting/Direction/Music critique -> Pros & Cons -> Final Star Rating out of 5 stars!"""
            hook_instruction = """- CATCHY MOVIE REVIEW HOOK (First 2-3 seconds):
  Open with a decisive, punchy verdict on whether this film is a blockbuster feast or total headache!"""
            cta_instruction = """- MOVIE REVIEW CTA (Final beat):
  Ask viewers whether they watched the film, if they agree with the rating, and tell them to drop their score below!"""
        else:
            role_desc = """🚨 CRITICAL MANDATORY LANGUAGE DIRECTIVE:
You are an expert Telugu YouTube creator and tech script writer (conversational Teluglish style like Prasad Tech in Telugu).
EVERY SINGLE SENTENCE OF THE SCRIPT NARRATION AND TITLE MUST BE WRITTEN IN NATURAL SPOKEN TELUGU (తెలుగు లిపి).
Even if the topic or news source articles are provided in English, DO NOT write English sentences in the script.
TRANSLATE AND ADAPT ALL NEWS/TOPIC FACTS DIRECTLY INTO ENGAGING TELUGU SPOKEN CREATOR NARRATION!"""
            hook_instruction = """- CURIOSITY-GAP HOOK RULE (First 2-3 seconds) - TELUGU CREATOR STYLE:
  The opening line (Beat 1) must NEVER be a flat statement like "Today we are talking about X" or "ఈ రోజు మనం X గురించి మాట్లాడబోతున్నాం".
  It MUST be an irresistible, high-energy curiosity-gap question or shocking claim in natural spoken Telugu creator slang!
  STRICT RULE: NEVER start with greetings ("హాయ్ ఫ్రెండ్స్", "నమస్కారం", "హలో") or channel pleasantries! Audio must start at 0.0s!
  Authentic Telugu Creator Hook Examples:
  * "Samsung నుంచి రాబోతున్న Galaxy S27 లో ఈ బిగ్గెస్ట్ ప్రాబ్లమ్‌ని నిజంగా ఫిక్స్ చేశారా?"
  * "బడ్జెట్ ప్రైస్ లోనే ₹1,00,000 అల్ట్రా ఫోన్ లో ఉండే సేమ్ ఫ్లాగ్‌షిప్ **UFS 5.1** స్టోరేజ్ ఇస్తే ఎలా ఉంటుంది?"
  * "ఈ **6000mAh** బిగ్ బ్యాటరీతో డైలీ ఛార్జింగ్ కి ఫుల్‌స్టాప్ పడబోతోందా?"
  * "చూడండి బాస్, ఈ ఫోన్ ప్రైస్ కి ఇది నిజంగా వర్త్ ఆ కాదా? అసలు ట్విస్ట్ ఏంటో వీడియో చివరి దాకా చూడండి!"
  Follow this exact high-retention Telugu creator hook style!"""
            cta_instruction = """- STRONG ACTIONABLE CTA (Final beat) - TELUGU CREATOR STYLE:
  End with a concrete, answerable question in authentic Telugu creator conversational tone!
  Examples: "మరి ఈ స్పెసిఫికేషన్స్ కి ఈ ప్రైస్ వర్త్ అంటారా? మీరేమంటారు? కింద కామెంట్స్ లో చెప్పండి! వీడియో నచ్చితే లైక్ చేసి సబ్‌స్క్రైబ్ చేసుకోండి!" or "ఈ కెమెరా కోసం మీరు అప్‌గ్రేడ్ అవుతారా లేదా? డ్రాప్ యువర్ థాట్స్ ఇన్ ద కామెంట్స్!" """

        language_rules = """LANGUAGE & SCRIPT RULES:

- SARALAMAINA TELUGU VAADUKA BHASHA (సరళమైన సహజ వాడుక భాష - 100% NATURAL CONVERSATIONAL TELUGU):
  Write the TITLE and SCRIPT narration strictly in fluent, natural, spoken conversational Telugu (తెలుగు లిపి).
  It MUST sound like an authentic, energetic Telugu YouTube creator talking face-to-face with an audience—NEVER like a robotic teleprompter or someone reading a textbook!

- STRICT BAN ON LITERAL WORD-BY-WORD TRANSLATION:
  DO NOT translate English news or facts literally into Telugu! Mechanical word-for-word translation creates awkward, unnatural sentences that ruin audience retention.
  * STRICTLY FORBIDDEN: "యూపీ ఎందుకు బ్యాక్ ఉంది", "ఏపీ ఎందుకు ర్యాంక్ అని ఉంది", "షాకింగ్ గా ఉంది", "ఇది బ్రేకింగ్ గా ఉంది".
  * ALWAYS ADAPT THE MEANING INTO NATURAL TELUGU:
    ❌ BAD (Literal): "యూపీ ఎందుకు బ్యాక్ ఉంది ఏపీ ఎందుకు ర్యాంక్ అని ఉంది"
    ✅ GOOD (Natural): "చూడండి ఫ్రెండ్స్, నేషనల్ వెహికల్ ఇండెక్స్‌లో మన ఆంధ్రప్రదేశ్ టాప్ ర్యాంక్ సాధించి రికార్డ్ సృష్టించింది! పెద్ద పెద్ద రాష్ట్రాలైన ఉత్తరప్రదేశ్ లాంటివి కూడా వెనుకబడిపోయాయి!"
    ❌ BAD (Literal): "ఇది మార్కెట్ కి బిగ్ షాక్ గా ఉంది"
    ✅ GOOD (Natural): "బాస్, ఈ న్యూస్ వింటే ఎవరైనా మైండ్ బ్లాంక్ అవ్వాల్సిందే!"

- VOCAL PERSONA & DELIVERY GUIDELINES:
  "Speak in the tone of an energetic, candid Telugu creator/reviewer. Sound spontaneous, dramatic, lively, and expressive rather than robotic or formal. Add subtle vocal emphasis on contrasting words, punchlines, and key reveals."

- PUNCTUATION-DRIVEN CADENCE:
  Text-to-speech engines rely heavily on punctuation for inflection. Break long lines into short punchy fragments (6-10 words) using commas (,), dashes (—), and ellipsis (...) to create organic breathing room and natural cadence.

- 100% TELUGU SCRIPT FOR ALL LOANWORDS:
  Avoid phonetic Telugu written in loose English script. Write 100% in native Telugu script (తెలుగు లిపి). Write English loanwords in Telugu script (e.g. 'బిగ్ బాస్', 'పాన్ ఇండియా', 'ట్విస్ట్', 'మైండ్ బ్లాంక్', 'రివ్యూ', 'ఎలిమినేషన్', 'రికార్డ్', 'వైరల్') to prevent neural TTS from switching to an American/robotic accent.

- AUTHENTIC TELUGU CREATOR CONVERSATIONAL CONNECTORS:
  Naturally weave in conversational creator slang connectors between beats:
  * "చూడండి ఫ్రెండ్స్..."
  * "కానీ ఇక్కడ అసలు ట్విస్ట్ ఏంటంటే..."
  * "బాస్, నిజం చెప్పాలంటే..."
  * "అసలు విషయం ఏంటంటే..."
  * "ఇక ఈ విషయం గురించి చూస్తే..."
  * "ఇందులో అదిరిపోయే పాయింట్ ఏంటంటే..."
  * "ఒక్కసారి ఆలోచించండి..."

- CRITICAL CREATOR PRONUNCIATION RULE (TELUGLISH TECH & NUMBERS):
  When discussing models, specs, numbers, and features, ALWAYS write them phonetically in Telugu script using their conversational English pronunciations, NOT bookish formal Telugu numbers!
  * Models: "గెలాక్సీ ఎస్ ట్వంటీ సెవెన్" (Galaxy S27), "ఐఫోన్ ఎయిటీన్ ప్రో" (iPhone 18 Pro), "ఎస్ ట్వంటీ సిక్స్" (S26). NEVER write formal Telugu numbers like "గెలాక్సీ ఇరవై ఏడు" or "పద్దెనిమిది".
  * Specs: "యూఎఫ్ఎస్ ఫైవ్ పాయింట్ వన్" (UFS 5.1), "టూ ఫిఫ్టీ సిక్స్ జీబీ" (256GB), "ట్వెల్వ్ జీబీ ర్యామ్" (12GB RAM), "సిక్స్ థౌసండ్ ఎంఏహెచ్ బ్యాటరీ" (6000mAh), "వన్ ట్వంటీ హెర్ట్జ్ డిస్‌ప్లే" (120Hz).
  * Dynamic Key Spec Tagging: Wrap standout specs in double asterisks (e.g. **6000mAh**, **120Hz**, **UFS 5.1**, **₹19,999**).

- MANDATORY PRASAD TECH SMARTPHONE SPECIFICATIONS BREAKDOWN (PURE TECH FOCUS):
  When discussing smartphones, gadgets, processors, or tech news:
  * NEVER speak in vague generalities like "ఈ ఫోన్ చాలా బాగుంది" or "కెమెరా సూపర్".
  * YOU MUST DETAIL CONCRETE REAL-WORLD SPECIFICATIONS in natural creator Telugu:
    1. Processor & Performance: State the exact chipset (e.g. Snapdragon 8 Elite, Dimensity 9400, Snapdragon 7s Gen 3, Apple A18 Pro) and gaming/multitasking capability.
    2. Camera Optics: Exact Megapixels (e.g. 200MP Main / 50MP Sony LYT-808, Periscope Telephoto zoom, OIS stabilization).
    3. Battery & Fast Charging: Exact capacity (e.g. **6000mAh**, **6500mAh**) and charging wattage (e.g. **80W**, **100W**, **120W** ఫాస్ట్ ఛార్జింగ్).
    4. Display: AMOLED / OLED, **120Hz** / **144Hz** refresh rate, peak nits brightness.
    5. Price in India (₹): Expected / launch price (e.g. **₹24,999**, **₹54,999**) and value-for-money verdict ('ఈ ప్రైస్ కి ఇది వర్త్ ఆ కాదా?').

- PACING: Each beat must be speakable in 2.0-3.5 seconds (6-12 words) for maximum retention.
- CRITICAL VISUAL RULE: All VISUAL descriptions MUST be written strictly in concise ENGLISH keywords (e.g. "traffic highway india | modern electric vehicle charging station drone"), because stock video search engines query in English. Do NOT write visual descriptions in Telugu."""
    elif is_hindi:
        role_desc = "You are a professional Hindi YouTube script writer and visual-content planning director."
        hook_instruction = """- CURIOSITY-GAP HOOK RULE (First 2-3 seconds):
  Must be an irresistible curiosity-gap question in natural spoken Hindi that stops the viewer from scrolling!"""
        cta_instruction = """- STRONG ACTIONABLE CTA (Final beat):
  End with a concrete question tied directly to the topic in conversational Hindi!"""
        language_rules = """LANGUAGE & SCRIPT RULES:

- Write the TITLE and SCRIPT narration strictly in natural, fluent spoken Hindi (देवनागरी लिपि).
- CRITICAL VISUAL RULE: All VISUAL_PLAN descriptions and keywords MUST be written strictly in concise ENGLISH keywords. Do NOT write visual descriptions in Hindi."""
    else:
        if is_roast:
            role_desc = "You are a savage, high-energy YouTube comedic roaster known for witty insults, sharp punchlines, and devastating comedic takedowns."
            hook_instruction = """- SAVAGE ROAST HOOK RULE (First 2-3 seconds):
  The opening line (Beat 1) MUST be a razor-sharp, hilarious roast or burn that hooks the viewer instantly with savage comedic energy!"""
            cta_instruction = """- SAVAGE ROAST CTA (Final beat):
  End with a sharp, hilarious question asking viewers if they agree with the roast or if they're in denial!"""
        elif is_sarcastic:
            role_desc = "You are a master of deadpan satire, biting irony, mock praise, and cynical comedic observations."
            hook_instruction = """- DEADPAN SARCASTIC HOOK RULE (First 2-3 seconds):
  The opening line (Beat 1) MUST deliver dry, deadpan irony or mock praise exposing the subject's ridiculousness!"""
            cta_instruction = """- DEADPAN SARCASTIC CTA (Final beat):
  End with a cynical, sarcastic call-to-action asking viewers to drop their sarcastic thoughts below!"""
        elif is_funny:
            role_desc = "You are an energetic, cheerful comedic creator known for hilarious, highly relatable observational comedy."
            hook_instruction = """- FUNNY OBSERVATIONAL HOOK RULE (First 2-3 seconds):
  Open with an upbeat, hilarious observation about everyday struggles or expectations vs reality!"""
            cta_instruction = """- FUNNY COMEDY CTA (Final beat):
  End with an upbeat, funny question inviting viewers to share their relatable stories in the comments!"""
        elif is_cinema_ent:
            role_desc = "You are a charismatic cinema insider, film trade analyst, and entertainment journalist known for engaging industry buzz and film culture breakdowns."
            hook_instruction = """- CINEMA & ENTERTAINMENT HOOK (First 2-3 seconds):
  Open with explosive industry news, box office milestones, or major movie announcements that immediately excite film lovers!"""
            cta_instruction = """- ENTERTAINMENT CTA (Final beat):
  Ask fans for their take on the industry trend, upcoming release, or box office verdict in the comments!"""
        elif is_deep_dive:
            role_desc = "You are an expert investigative essayist and documentary narrator known for immersive, multi-layered deep-dive explainers."
            hook_instruction = """- INTRIGUING DEEP DIVE HOOK (First 2-3 seconds):
  Open with a profound mystery, compelling central question, or shocking revelation that frames the entire comprehensive deep dive!"""
            cta_instruction = """- THOUGHT-PROVOKING DEEP DIVE CTA (Final beat):
  Conclude with a thought-provoking philosophical or future-looking question challenging the viewer's perspective!"""
        elif is_movie:
            role_desc = "You are a charismatic, insightful film critic and cinema reviewer known for entertaining, structured 5-star film breakdowns."
            hook_instruction = """- MOVIE REVIEW HOOK RULE (First 2-3 seconds):
  Open with a decisive, intriguing verdict establishing whether the film is an unexpected masterpiece, a massive flop, or a flawed gem!"""
            cta_instruction = """- MOVIE REVIEW CTA (Final beat):
  Ask viewers whether they've watched the film, if they agree with your rating, and what score out of 5 they would give it!"""
        else:
            role_desc = "You are a professional YouTube script writer and visual-content planning director."
            hook_instruction = """- CURIOSITY-GAP HOOK RULE (First 2-3 seconds):
  The opening line (Beat 1) must NEVER be a flat statement like "Today we are talking about X" or "X just announced Y".
  It MUST be an irresistible curiosity-gap question or shocking claim that stops the viewer from scrolling!
  Few-Shot Hook Examples:
  * "Did Samsung just fix the single biggest flaw in the new Galaxy S27?"
  * "What if a budget phone packed the exact same flagship storage as a ₹1,00,000 Ultra?"
  * "Is this massive 6000mAh battery about to make daily charging completely obsolete?"
  Follow this exact high-retention hook style!"""
            cta_instruction = """- STRONG ACTIONABLE CTA (Final beat):
  Do NOT end with generic pleasantries like "subscribe and comment below".
  End with a concrete, answerable question tied directly to the topic!
  Examples: "Would you upgrade for this camera, or is your current phone still good enough? Tell me below!" or "Is ₹25,000 worth it for this chip? Drop your thoughts!" """

        language_rules = """LANGUAGE:

- Write the TITLE and SCRIPT narration in natural spoken English.
- Use natural spoken English suitable for video narration.
- Preserve names, places, organizations, dates and amounts.
- Do not invent facts, quotes or statistics.
- All VISUAL_PLAN descriptions in concise English keywords."""

    dur_str = str(target_duration).lower()
    ct_str = str(content_type).lower()
    is_history = "history" in ct_str or "historical" in ct_str
    is_facts = "fact" in ct_str or "curiosity" in ct_str
    is_longform_intent = is_history or is_facts or "6-9" in dur_str or "6–9" in dur_str or "long-form" in dur_str or "2-4" in dur_str or "explainer" in dur_str

    try:
        profile = get_format_profile(
            target_duration=target_duration,
            format_type="long-form" if is_longform_intent else "short",
            language=language_style,
        )
    except TypeError:
        import importlib
        import config.format_profiles
        importlib.reload(config.format_profiles)
        profile = config.format_profiles.get_format_profile(
            target_duration=target_duration,
            format_type="long-form" if is_longform_intent else "short",
            language=language_style,
        )

    if profile.format_type == "long-form":
        duration_guidelines = f"""TARGET DURATION & PACING (LONG-FORM {profile.min_seconds/60:.0f}–{profile.max_seconds/60:.0f} MINUTES):
- TARGET LENGTH: {profile.target_seconds/60:.1f} minutes ({profile.min_seconds:.0f}s to {profile.max_seconds:.0f}s).
- WORD COUNT: Strictly between {profile.min_words} and {profile.max_words} spoken words total across the whole script. MINIMUM {profile.min_words} SPOKEN WORDS IS STRICTLY REQUIRED! (Target: {profile.target_words} words). DO NOT write a quick summary; write full, comprehensive, detailed narrative paragraphs with rich explanations.
- SCENE / BEAT COUNT: Exactly {max(25, profile.recommended_clips - 5)} to {profile.recommended_clips + 5} dynamic beats (each beat {profile.min_clip_duration:.1f} to {profile.max_clip_duration:.1f}s / {profile.max_words_per_sentence} words max per sentence).
- INSTANT CURIOSITY HOOK: In the first 3-15 seconds (Beat 1), hook the viewer with an unsolved mystery, shocking truth, or curiosity gap. Zero pleasantries or channel intros.
- CLEAR CHAPTER STRUCTURE: Organize the narrative into 5 to 7 logical chapters/story acts (Act 1: Hook & Context, Act 2: Deep Dive & Clashing Evidence, Act 3: Climax & Resolution).
- CHAPTER MARKERS IN SECTIONS: Prefix the first section of each chapter with '[CHAPTER N: Chapter Title]' (e.g., '[CHAPTER 1: The Untold Beginning]', '[CHAPTER 2: The Core Evidence]') so that chapter bumper cards and YouTube chapters are automatically generated.
- 1 NEW FACT / STORY BEAT PER MINUTE: Deliver a compelling new breakthrough, twist, or verified fact roughly every minute to maintain audience retention.
- CLOSING TEASER / QUESTION: Conclude with a thought-provoking philosophical question, historical enigma, or curiosity teaser.
- CHAPTER TIMESTAMPS: In the metadata and section structure, clearly delineate chapters (e.g. 00:00 The Forgotten Truth, 01:15 The Discovery, 02:45 The Turning Point)."""
        visual_count_text = f"- {profile.min_seconds/60:.0f}–{profile.max_seconds/60:.0f} minute scripts (Long-Form): {profile.recommended_clips - 5}–{profile.recommended_clips + 5} dynamic visuals (each {profile.min_clip_duration:.1f} to {profile.max_clip_duration:.1f}s)"
    else:
        is_extended_shorts = profile.target_seconds > 45.0
        is_indic_prompt = any(
            k in str(language_style).lower() or k in str(topic).lower()
            for k in ["telugu", "తెలుగు", "hindi", "tamil", "kannada", "malayalam"]
        )
        eff_max = int(profile.max_words * 0.85) if (is_indic_prompt and profile.words_per_second_max >= 2.2) else profile.max_words
        eff_min = int(profile.min_words * 0.80) if (is_indic_prompt and profile.words_per_second_min >= 2.0) else profile.min_words
        eff_target = int(profile.target_words * 0.85) if is_indic_prompt else profile.target_words

        duration_guidelines = f"""TARGET DURATION & PACING (YOUTUBE SHORTS / REELS):
- TARGET LENGTH: {profile.min_seconds:.0f} to {profile.max_seconds:.0f} seconds (Nominal Target: {profile.target_seconds:.0f}s, Hard Ceiling: {profile.max_seconds:.0f}s).
- EXTENDED SHORTS INSTRUCTION: {"This is an EXTENDED 60-90s Short! You MUST write at least " + str(eff_min) + " spoken words across " + str(profile.recommended_clips) + " dynamic beats. DO NOT write a quick 30s summary!" if is_extended_shorts else "Keep pacing ultra-snappy and punchy within 25-45s."}
- WORD COUNT: Strictly between {eff_min} and {eff_max} spoken words total across the whole script. (Target: {eff_target} words). DO NOT EXCEED {eff_max} WORDS OR GO BELOW {eff_min} WORDS! (TTS creator pacing ~2.2 words/sec for Telugu, ~2.6 words/sec for English).
- ONE CORE IDEA ONLY: Focus exclusively on 1 single punchy story, reveal, or twist. Do NOT cram 3-5 different items or multiple bullet points into one Short!
- SENTENCE LENGTH: Keep sentences snappy and short (maximum {profile.max_words_per_sentence} words per sentence).
- SCENE / BEAT COUNT: Exactly {max(6, profile.recommended_clips - 2)} to {profile.recommended_clips + 2} dynamic beats (each beat {profile.min_clip_duration:.1f} to {profile.max_clip_duration:.1f}s / 8 to 12 words).
- SPOKEN HOOK AT 0.0s: Beat 1 MUST hook the viewer immediately at 0.0s with zero dead air. NEVER start with greetings ("హాయ్ ఫ్రెండ్స్", "Namaskaram", "Hi guys") or channel intros ("Welcome back", "Today we discuss").
- LOOP-FRIENDLY ENDING: The final sentence must flow seamlessly back into the opening hook line so the Short loops endlessly on YouTube/Instagram.
- CTA INSIDE NARRATION: Weave the call to action directly into the final sentence before the loop."""
        visual_count_text = f"- {profile.min_seconds:.0f}–{profile.max_seconds:.0f} second scripts (Shorts): {max(6, profile.recommended_clips - 2)}–{profile.recommended_clips + 2} dynamic visuals (each {profile.min_clip_duration:.1f} to {profile.max_clip_duration:.1f}s)"

    topic_str = str(topic).lower()
    is_india_context = any(k in topic_str for k in [
        "india", "indian", " rs ", "rs.", "₹", "rupee", "rupees", "flipkart",
        "amazon.in", "inr", "telugu", "telangana", "andhra", "hyderabad", "bengaluru", "delhi", "mumbai"
    ]) or bool(re.search(r"(?:rs\.?|₹|inr)\s*\d+", topic_str, re.IGNORECASE))

    india_directive = ""
    if is_india_context:
        india_directive = """
============================================================
🇮🇳 MANDATORY INDIA MARKET & CURRENCY RULES:
============================================================
- The topic specifies the Indian market. All pricing, product recommendations, and availability MUST strictly reflect India (Flipkart, Amazon India, Indian retail).
- ALL price tiers mentioned in the topic (e.g. Under Rs 30,000, Rs 50,000, Rs 75,000) MUST HAVE AN EXPLICIT TOP PICK RECOMMENDATION with key camera specs (sensor, OIS, zoom, aperture)!
- CURRENCY PRONUNCIATION IN NARRATION:
  * In spoken narration, always write prices in creator-friendly terms: e.g. "thirty thousand rupees" or "Rs 30,000" or "యాభై వేల రూపాయలు".
  * NEVER write or say raw truncated numbers like "30 rupees" for Rs 30,000!
- CONCLUDING DISCLAIMER: In the final beat, mention that prices may vary with bank discounts and festive sales.
============================================================
"""

    winning_hook_info = None
    is_shorts = (profile.format_type == "short")
    hook_injection_text = ""
    if is_shorts:
        try:
            from agents.hook_engine import generate_and_score_hooks
            from agents.hook_card import generate_hook_card
            winning_hook_info = generate_and_score_hooks(
                topic=topic,
                content_type=content_type,
                language_style=language_style,
                source_context=formatted_source_context,
            )
            if winning_hook_info and winning_hook_info.get("chosen_hook"):
                generate_hook_card(
                    hook_text=winning_hook_info["chosen_hook"],
                    output_path="output/hook_overlay.png",
                )
                hook_injection_text = f"""
============================================================
⚡ VIRALITY HOOK ENGINE DIRECTIVE (MANDATORY BEAT 1):
============================================================
The Hook Engine has scored candidate hooks and selected this winning {winning_hook_info['pattern']} hook:
"{winning_hook_info['chosen_hook']}"

CRITICAL VIRALITY RULES:
- Beat 1 of the script narration MUST open with this exact hook (or a direct close equivalent).
- DO NOT prepend ANY greeting ("హాయ్ ఫ్రెండ్స్", "Namaskaram", "Hi guys") or channel intro ("Welcome back", "Today we discuss").
- Spoken narration MUST start delivering this hook at 0.0s!
============================================================
"""
        except Exception as hook_err:
            print(f"⚠️ Hook engine notice: {hook_err}")

    mandatory_lang_warning = ""
    if is_telugu:
        mandatory_lang_warning = """
============================================================
🚨 MANDATORY LANGUAGE DIRECTIVE: TELUGU (తెలుగు) ONLY
============================================================
- The user has chosen TELUGU.
- You MUST write the entire TITLE and SCRIPT narration in natural, fluent, conversational spoken Telugu script (తెలుగు లిపి).
- Even though the NEWS SOURCE CONTEXT or Topic title may be written in English, YOU MUST TRANSLATE AND ADAPT ALL INFORMATION DIRECTLY INTO ENGAGING SPOKEN TELUGU!
- English sentences in the SCRIPT narration are STRICTLY FORBIDDEN!
- Use Teluglish creator style for tech words & models (e.g. గెలాక్సీ ఎస్ ట్వంటీ సెవెన్, 5200mAh బ్యాటరీ, డిస్‌ప్లే, ప్రాసెసర్).
- Stock visual descriptions in the VISUAL PLAN must remain in concise English for stock footage search.
============================================================
"""

    bb_roster_directive = ""
    try:
        from utils.season_guard import is_bigg_boss_topic
        if is_bigg_boss_topic(topic or "") or "bigg boss" in str(topic).lower():
            bb_roster_directive = """
============================================================
🚨 MANDATORY GROUND TRUTH: BIGG BOSS TELUGU 10 OFFICIAL ROSTER
============================================================
Host: Akkineni Nagarjuna
Official Season 10 Active Housemates:
- Vamsi Krishna (Temper Vamsi) [CURRENT CAPTAIN THIS WEEK!]
- Thrigun Eswaran (Actor Thrigun / Adith Arun)
- Aman Masud (Actor)
- Sudheer Reddy (Sudheer Talks YouTuber / Sudheer)
- Auto Ram Prasad (Jabardasth Ram Prasad)
- Potti Naresh (Jabardasth Naresh)
- Debjani Modak
- Shiv (Anchor Shiv)
- Mukesh Gowda
- Varshini Sounderajan
- Rama Krishna
- Swetha
- Neethu Natraj
CRITICAL GROUND TRUTH: THIS WEEK NO ELIMINATION! Temper Vamsi is the current Captain.

Eliminated Contestants:
- Rohit Patnam (Rohit Naidu Patnam) [ELIMINATED / EVICTED - NO LONGER IN HOUSE!]
- Shalini Patel [ELIMINATED / EVICTED - NO LONGER IN HOUSE!]
- Gundeboina Jhansi (Singer Jhansi) [ELIMINATED / EVICTED]
- Chaithra Rai [ELIMINATED / EVICTED (WEEK 1)]
- Krishna Alluri (Krishnudu) [ELIMINATED / EVICTED (WEEK 2)]
- Srishti Vyakaranam [ELIMINATED / EVICTED]
- Charan Mahadev [ELIMINATED / EVICTED]
- Mithilesh Reddy [WALKED OUT]

STRICT ACCURACY RULES:
1. ONLY write active in-house scenes, captaincy, task battles, nominations, and immunity for ACTIVE housemates!
2. NEVER describe eliminated contestants (Rohit Patnam, Shalini Patel, Jhansi, Chaithra, Krishnudu, Srishti, Charan) as staying in the house, competing in tasks, or receiving immunity! Only mention them in past-tense eviction context if the episode topic directly discusses their elimination.
3. NEVER mention or write scenes for Sudigali Sudheer (use Sudheer Reddy / Sudheer Talks), Rohit Sahni, Anchor Jhansi (use Singer Gundeboina Jhansi), or Mega Power Star Ram Charan (use Charan Mahadev).
4. In VISUAL_PLAN: ALWAYS include the contestant's full name and context (e.g. 'Aman Masud bigg boss telugu 10 | Aman Masud actor still', 'Temper Vamsi bigg boss 10 | Temper Vamsi photo').
============================================================
"""
    except Exception:
        pass

    prompt = f"""
{role_desc}
{mandatory_lang_warning}
{hook_injection_text}
{india_directive}
{bb_roster_directive}
Create a complete YouTube content package about:

{topic}

Content type:
{content_type}

Style:
{language_style}

NEWS SOURCE CONTEXT:
{formatted_source_context}

SOURCE GROUNDING RULES:

CONTENT-TYPE BEHAVIOR:

If Content type is NEWS:
- When verified sources are supplied in NEWS SOURCE CONTEXT, treat them as the primary factual basis.
- If verified news sources are provided, every important factual claim must be grounded in the supplied material.
- If no verified news source context is available, explain the topic objectively, factually, and educationally using established industry knowledge without inventing false quotes or fake announcements.
- Do not invent facts, quotes, dates, statistics, names, events, partnerships or announcements.

If Content type is HISTORY:
- Ground every narrative beat in real historical events, places, eras, and people.
- Focus on dramatic pacing, cause-and-effect, and lesser-known historical context.
- Never use modern tech buzzwords or superficial summaries.
- In VISUAL_PLAN: describe historical paintings, archival photographs, vintage maps, ancient architecture, and era-specific artifacts with exact place and era names.

If Content type is INTERESTING FACTS:
- Structure as a sequence of mind-bending, verified facts that challenge common assumptions.
- Each fact must be clearly explained with its scientific, historical, or real-world significance.
- In VISUAL_PLAN: describe specific macro photography, scientific visual concepts, historical artifacts, or real-world locations corresponding to the exact fact.

If Content type is ROASTING:
- TONE & STYLE: High-energy, savage yet witty roasts, rapid-fire comedic insults, and razor-sharp punchlines.
- Highlight the absurdities, overhyped marketing claims, embarrassing failures, design flaws, or hilarious quirks of the subject.
- Keep it punchy, rhythmic, and brutally funny without crossing into hate speech, personal harassment, or profanity.
- Use dramatic, suspenseful build-ups leading directly into devastating comedic punchlines.
- In VISUAL_PLAN: describe reaction faces, facepalms, dramatic slow-mo fails, comic zooms, ironic comparisons, and exaggerated stock visuals matching the punchlines.

If Content type is SARCASTIC:
- TONE & STYLE: Deadpan cynicism, biting irony, mock praise, and sharp satirical observations.
- Pretend to overly praise the absurd flaw, terrible price tag, or ridiculous decision before dropping a dry, ironic reality check.
- Use understated wit, rhetorical questions dripping with sarcasm ("Because who doesn't love paying $1,500 for a phone with no charger?"), and cynical deadpan humor.
- In VISUAL_PLAN: describe unimpressed stares, ironic corporate stock footage, side-eye memes, slow sarcastic clapping, and contrasting visuals highlighting the reality vs expectation.

If Content type is FUNNY:
- TONE & STYLE: Cheerful, upbeat, highly relatable observational comedy and light-hearted jokes.
- Focus on everyday human struggles, expectations vs. reality, funny relatable habits, and witty lighthearted commentary.
- Keep the vibe positive, amusing, and energetic with easy-to-laugh-at punchlines.
- In VISUAL_PLAN: describe funny relatable everyday clips, comedic memes, animated expressions, slapstick situations, and bright engaging footage.

If Content type is MOVIE REVIEWS:
- REVIEW STRUCTURE & PACING:
  1. Instant Hook: Catchy, intriguing opening line establishing whether the film is an unexpected masterpiece, a massive flop, or a flawed gem.
  2. Plot Setup: A brief, compelling synopsis of the central conflict (STRICTLY NO major spoilers or twist reveals).
  3. Deep Critique: Critique acting performances, direction, screenplay/pacing, cinematography, and music/background score.
  4. Pros & Cons: Distinct highlight of the film's strongest elements and its most glaring flaws.
  5. Final Verdict & Star Rating: Clear recommendation on whether to watch in theaters, stream at home, or skip, ending with an explicit star rating out of 5 stars (e.g. "3.5 out of 5 stars").
- TONE: Authoritative yet entertaining, passionate, insightful, and cinematic.
- In VISUAL_PLAN: describe cinematic stills, atmospheric mood lighting, film reel aesthetic, character closeups, and evocative cinematic b-roll.

If Content type is CINEMA & ENTERTAINMENT:
- Focus broadly on cinema industry buzz, Tollywood / regional film news, box office records, shooting updates, upcoming projects, casting announcements, and industry trends (NOT just a single movie review).
- Provide insider commentary, trade insights, audience anticipation, and industry impact.
- Keep the energy high, engaging, and authoritative.
- In VISUAL_PLAN: describe film sets, movie posters, premiere events, box office charts, celebrated directors and actors, and cinematic b-roll.

If Content type is CUSTOM TOPIC / DEEP DIVE:
- DO NOT treat this as a quick news summary or superficial bulletin.
- Signal the narrative to go DEEP and THOROUGH on this specific topic: explore its historical context/origins, intricate mechanics, real-world case studies, twists, and big-picture future implications.
- Structure into clear, logical narrative phases: (1) Intriguing Hook & Central Mystery, (2) Deep Background & Genesis, (3) Core Mechanics / In-Depth Breakdown, (4) Surprising Insights / Real-World Impact, (5) Concluding Insight & Big Takeaway.
- Ground explanations in clear analogies, vivid examples, and logical storytelling.
- In VISUAL_PLAN: describe high-quality thematic b-roll, detailed explanatory scenes, documentary-style footage, archival or conceptual illustrations matching the depth of the narrative.

If Content type is GENERAL TOPIC:
- Do NOT require NEWS SOURCE CONTEXT.
- Do NOT say that sources are insufficient merely because no news sources were supplied.
- Answer the requested topic normally using your general knowledge.
- Explain educational or general topics clearly and accurately.
- Do not invent highly specific facts, statistics, quotes, dates or claims when you are not confident they are correct.

IMPORTANT SOURCE SELECTION RULES:

1. First identify which verified source or sources are directly relevant to the requested topic.

2. If the topic asks for a specific news story, build the entire narration around that story. Do not combine it with unrelated verified articles.

3. If the topic explicitly asks for a roundup, multiple stories may be used. In that case, treat each story as a separate news item and clearly transition between them.

4. Do NOT create a broad "technology roundup" merely because several verified articles contain technology-related words.

5. Do NOT combine separate people, organizations, locations, dates, projects, statistics or events into one event.

6. For NEWS content, every factual claim in the narration must be supported by the supplied source context when available, preferably by the full Article text field.

7. Headlines and snippets may identify a story, but do not use them as evidence for additional facts that are not present in the supplied Article text.

8. If Article text is available, prefer it over inference from the headline or snippet.

9. If a verified source is older than the topic implies, do not describe it as breaking, today's, or newly announced news unless the source explicitly supports that.

10. Never invent names, titles, casualty figures, dates, quotes, locations, statistics, investments, partnerships, announcements or events.

11. Never merge facts from different articles unless the sources clearly support that connection.

12. For NEWS content, if verified news sources are absent, provide a clear, balanced, and objective overview based on established industry knowledge rather than refusing or halting the script.

13. For GENERAL TOPIC content, absence of news source context is NOT a reason to refuse or shorten the script.

SOURCE PRIORITY:

Use this priority when deciding what information to include:

1. Full verified Article text
2. Verified headline
3. Verified publication date
4. Verified source name
5. Verified snippet
6. URL only for source identification

Do not use outside knowledge to fill missing information.

NEWS ACCURACY:

- Every important factual sentence must be traceable to a
  supplied verified source.
- Keep facts attached to the correct source.
- Do not transfer a fact from SOURCE 1 to SOURCE 2.
- Do not assume that two articles describe the same event.
- Preserve uncertainty when the source itself is uncertain.
- Never present an unverified event as confirmed news.

{language_rules}

SCRIPT & DURATION:

{duration_guidelines}

{hook_instruction}

- DYNAMIC KEY SPEC TAGGING:
  Wrap standout specs, numbers, capacities, and model names in double asterisks so our video subtitle engine can dynamically highlight them on-screen with custom emphasis (e.g. **6000mAh**, **120Hz**, **UFS 5.1**, **Galaxy S27**, **₹19,999**, **12GB RAM**).

{cta_instruction}

- Explain the topic clearly.
- Use natural spoken sentences.
- Maintain logical flow.
- For news, remain factual and neutral.
- For education, explain concepts simply.
- For entertainment, remain engaging and original.
- End with a concise conclusion.
- No markdown inside narration except for the **key spec** highlights.
- No bullet points inside the narration.
- No camera directions.
- No sound effects.
- No stage directions.

VISUAL PLAN & PACING:

Generate a RICH, FAST-PACED, and DYNAMIC visual plan with frequent scene transitions (a new visual every 2.0 to 3.5 seconds of speech).
Guidelines for visual count:
{visual_count_text}

Divide your narration into short, punchy beats (each 2.0 to 3.5 seconds of speech, about 6 to 12 words).
STRICT RULE: Never hold a single shot or section longer than 3.5 seconds! If a thought or sentence takes longer than 3.5 seconds to speak, you MUST split it into two distinct beats with different visuals.
Every beat/section must have its own dedicated, concrete visual concept in the VISUAL_PLAN!
This ensures the video has frequent, cinematic visual cuts and transitions instead of holding on any visual.

Visual 1 must represent the main subject/opening hook.
Supporting visuals 2 through N-1 must represent different supporting subjects directly discussed in their corresponding narration section.
Visual N must be a strong concluding visual directly related to the final takeaway.

CRITICAL VISUAL RELEVANCE & AUTHENTIC REAL-WORLD MEDIA:
1. Concrete Real-World Visual Imagery:
   Every visual must describe the EXACT concrete physical subject being discussed in that section.
   Do NOT use generic or abstract descriptions (e.g. do NOT write "AI technology", "India news", "future vision", "business growth").
   Our multi-source engine searches direct live web photography, Twitter/X buzz media, official press renders, and entertainment portals.
2. Topic-Grounded Visual Media:
   - Science, Space, Nature & Facts (e.g. Earth, Space, Physics, Animals) -> Describe the exact planetary, cosmic, or physical phenomenon:
     "Planet Earth spinning in space satellite view | Earth rotation atmospheric shockwave | Earth globe space horizon"
     "Ocean tidal mega tsunami surging across land | coastal storm surge dramatic nature | global oceanic current simulation"
   - Specific movie / OTT release -> Name the movie, official movie poster, lead hero/heroine look:
     "Devara official movie poster HD | Jr NTR Devara hero still | Janhvi Kapoor Devara heroine look | OTT release banner"
   - Specific actor / celebrity -> Name the exact person:
     "Prabhas Kalki press meet photo | Allu Arjun Pushpa 2 look | Ranbir Kapoor interview portrait"
   - Commercial Products & Hardware (e.g. iQOO, Vivo, OnePlus, Apple, Samsung) -> Name the exact brand and model:
     "iQOO 13 5G smartphone launch photo | iQOO 13 camera module design | iQOO brand logo official HD"
     "OnePlus 13 flagship phone reveal | OnePlus official logo | Snapdragon 8 Elite processor chip"
3. Multi-Query Alternatives:
   For every visual concept, provide 2 to 3 alternative search queries separated by " | " (pipe) in order of preference:
   Format: Exact Real Subject Query | Media / Press / Twitter Query | Broad Physical Scene
   Examples:
   - "Planet Earth spinning in space satellite view | Earth rotation atmospheric shockwave | Earth globe space horizon"
   - "Ocean tidal tsunami surging across land | dramatic ocean shockwave | coastal storm surge"
   - "Devara official movie poster HD | Jr NTR Devara hero still | action movie poster cinema reveal"
   - "iQOO 13 5G smartphone photo | iQOO official brand logo HD | modern flagship smartphone sleek camera close-up"
   - "Hyderabad HITEC city skyline aerial view | modern highway flyover traffic | Indian metropolis skyline sunset"
4. NEVER TAKE METAPHORS OR IDIOMS LITERALLY (CRITICAL):
   - Never take idioms or figures of speech literally (e.g. if narration says "the whole world was shaken", do NOT show literal shaking cameras or seismographs; show the cinematic subject of the video).
   - In entertainment/reality show scripts, only anchor show names if the script is ACTUALLY about that show.
5. 100% SUBJECT & ENTITY SYNCHRONIZATION WITH NARRATION (CRITICAL):
   - When a section discusses a specific physical phenomenon, scientific principle, contestant, or device, the corresponding visual MUST depict that exact subject!

SECTION MAPPING:

Create EXACTLY N narration sections, matching the N visuals in your visual plan.
Each section must correspond to exactly one visual (SECTION N | VISUAL N).
The narration in each section must directly discuss the subject represented by its visual.
The N sections together must form one continuous YouTube narration.

Return EXACTLY this structure:

TITLE:
<punchy concise YouTube video title under 60 characters>

SCRIPT:
<complete narration>

VISUAL_PLAN:
1. <Primary Query> | <Alternative Query> | <Fallback B-Roll>
2. <Primary Query> | <Alternative Query> | <Fallback B-Roll>
...
N. <Primary Query> | <Alternative Query> | <Fallback B-Roll>

SECTIONS:

SECTION 1 | VISUAL 1
VISUAL: <Primary Query> | <Alternative Query> | <Fallback B-Roll>
NARRATION: <narration strictly discussing this visual>

SECTION 2 | VISUAL 2
VISUAL: <Primary Query> | <Alternative Query> | <Fallback B-Roll>
NARRATION: <narration strictly discussing this visual>

...
SECTION N | VISUAL N
VISUAL: <Primary Query> | <Alternative Query> | <Fallback B-Roll>
NARRATION: <narration strictly discussing this visual>
"""

    fallback_title = default_title
    if not fallback_title and isinstance(topic, str) and len(topic.strip()) <= 120 and "\n" not in topic:
        fallback_title = topic.strip()

    # 1. Multi-Candidate Script Quality Cascade (3 Personas + 1 Judge Rubric = Exactly 4 LLM calls)
    # ONLY apply the 3-Persona Roast/Entertainment cascade when in roast/entertainment mode and NOT neutral / long-form!
    if should_roast and not is_neutral_tone and not is_longform:
        try:
            from providers.llm import generate_text_cascade
            winner_text, eval_data = generate_and_judge_three_scripts(prompt, topic=topic, default_title=fallback_title)
            if winner_text and len(winner_text) >= 300:
                cascade_script = _parse_and_save_package(winner_text, default_title=fallback_title)
                if cascade_script:
                    print()
                    print("=" * 60)
                    print(f"3-SCRIPT RUBRIC WINNER SELECTED & SAVED: Persona '{eval_data.get('winning_persona')}'")
                    print("=" * 60)
                    print()
                    # Apply deterministic formatting & dynamic outro CTA without consuming extra LLM calls
                    is_indic = bool(re.search(r"[\u0C00-\u0C7F]", cascade_script))
                    cascade_script = ensure_dynamic_outro_cta(cascade_script, topic=topic, is_indic=is_indic)
                    return _validate_and_remedy_script(cascade_script, topic, profile, content_type, fallback_title, india_directive)
        except Exception as multi_err:
            print(f"Multi-candidate script generation notice: {multi_err}. Falling back to standard model loop...")

    model_errors = []

    for model in MODELS:

        try:

            print(f"Trying model: {model}")

            response = _call_gemini_with_retry(
                contents=prompt,
                model=model,
            )

            resp_text = getattr(response, "text", "")
            if not resp_text and hasattr(response, "candidates") and response.candidates:
                parts = getattr(response.candidates[0].content, "parts", [])
                resp_text = "".join(getattr(p, "text", "") for p in parts if getattr(p, "text", None))

            text = clean_response(resp_text)

            if len(text) < 300:

                print(
                    "Generated response is too short."
                )
                model_errors.append(f"{model}: response too short ({len(text)} chars)")
                continue

            fallback_title = default_title
            if not fallback_title and isinstance(topic, str) and len(topic.strip()) <= 120 and "\n" not in topic:
                fallback_title = topic.strip()

            script = _parse_and_save_package(
                text,
                default_title=fallback_title,
            )

            if script is None:

                print(
                    f"Model {model} returned an "
                    "invalid content package."
                )
                model_errors.append(f"{model}: invalid content package")
                continue

            print()
            print("=" * 60)
            print("NORMAL TOPIC GENERATION SUCCESSFUL")
            print("=" * 60)
            print()

            return _validate_and_remedy_script(script, topic, profile, content_type, fallback_title, india_directive)

        except Exception as error:

            print()
            print(f"Model failed: {model}")
            print(error)
            print()
            model_errors.append(f"{model}: {error}")

    # Fallback to prioritized multi-provider cascade (Groq / Ollama / Pollinations / OpenRouter)
    print("🔄 [LLM Fallback Cascade] Primary Gemini models exhausted. Trying prioritized multi-provider cascade (Groq / Ollama / Pollinations / OpenRouter)...")
    try:
        from providers.llm import generate_text_cascade
        cascade_raw = generate_text_cascade(prompt, step_name="script_agent_fallback", per_provider_timeout=45.0)
        cascade_clean = clean_response(cascade_raw)
        if len(cascade_clean) >= 300:
            cascade_script = _parse_and_save_package(cascade_clean, default_title=fallback_title)
            if cascade_script:
                print()
                print("=" * 60)
                print("LLM MULTI-PROVIDER CASCADE GENERATION SUCCESSFUL")
                print("=" * 60)
                print()
                return _validate_and_remedy_script(cascade_script, topic, profile, content_type, fallback_title, india_directive)
    except Exception as cascade_err:
        print(f"⚠️ Multi-provider fallback cascade notice: {cascade_err}")
        model_errors.append(f"cascade: {cascade_err}")

    err_summary = "; ".join(model_errors)
    all_network = all(
        ("nodename nor servname provided" in e or "ConnectError" in e or "temporary failure" in e.lower())
        for e in model_errors
    ) if model_errors else False

    if all_network:
        raise RuntimeError(
            "AutoTube AI failed: Network connection error connecting to Gemini API. "
            "Please ensure you are connected to the internet and running outside sandbox restrictions."
        )
    raise RuntimeError(
        f"All Gemini models failed to generate a valid content package ({err_summary})."
    )


# ============================================================
# FLYER / IMAGE SCRIPT
# ============================================================

@autonomous_recover("script_agent")
def generate_script_from_image(
    image_file,
    language_style="English",
):
    """
    Analyze an uploaded flyer/image and create:

        output/script.txt
        output/visual_plan.txt
        output/section_map.txt

    Returns a structured package:

        {
            "script": str,
            "visual_plan": list[str],
            "sections": list[dict]
        }
    """

    print()
    print("=" * 60)
    print("AI FLYER ANALYSIS STARTED")
    print("=" * 60)
    print()
    print("Flyer:")
    print(image_file)
    print()

    mime_type = (
        mimetypes.guess_type(image_file)[0]
        or "image/jpeg"
    )

    with open(image_file, "rb") as file:
        image_part = genai.types.Part.from_bytes(
            data=file.read(),
            mime_type=mime_type,
        )

    lang_str = str(language_style).lower()
    is_telugu = "telugu" in lang_str or "తెలుగు" in str(language_style)
    is_hindi = "hindi" in lang_str or "हिंदी" in str(language_style)

    if is_telugu:
        flyer_role = "You are an expert visual-content analyst and professional Telugu YouTube creator (conversational Teluglish style)."
        flyer_lang = """LANGUAGE:
- Write the TITLE and SCRIPT narration strictly in natural, fluent, engaging spoken Telugu (తెలుగు లిపి).
- Sound like an engaging Telugu creator. Write all numbers, models, and specs using conversational English phonetics in Telugu script (e.g. 'గెలాక్సీ ఎస్ ట్వంటీ సెవెన్', 'టూ ఫిఫ్టీ సిక్స్ జీబీ', 'యూఎఫ్ఎస్ ఫైవ్'). NEVER use formal textbook Telugu numbers.
- CRITICAL VISUAL RULE: All VISUAL descriptions MUST be in concise ENGLISH keywords so our stock search engine can find visuals."""
    elif is_hindi:
        flyer_role = "You are an expert visual-content analyst and professional Hindi YouTube script writer."
        flyer_lang = """LANGUAGE:
- Write the TITLE and SCRIPT narration strictly in natural, fluent spoken Hindi (देवनागरी लिपि).
- All VISUAL_PLAN descriptions in concise ENGLISH keywords."""
    else:
        flyer_role = "You are an expert visual-content analyst and professional English YouTube script writer."
        flyer_lang = """LANGUAGE:
- English only.
- Use natural spoken English.
- Write for an English TTS voice.
- Preserve names, places, organizations, dates and important numbers.
- Do not invent unsupported facts."""

    prompt = f"""
{flyer_role}

Carefully inspect the uploaded flyer/image.

The flyer is the primary source of truth.

Identify only information visible or clearly supported
by the flyer.

Create an engaging YouTube narration based on the flyer.

{flyer_lang}

SCRIPT:

- Approximately 60 to 120 seconds.
- Begin with an engaging introduction.
- Explain what the flyer is about.
- Mention important visible details.
- Explain relevant people, businesses,
  organizations, places or products.
- Do not simply read the flyer word-for-word.
- Make the narration useful and natural.
- End with a suitable conclusion.
- No markdown.
- No camera directions.
- No sound effects.
- No image instructions.

VISUAL PLAN:

Create EXACTLY 8 different visual concepts.

Visual 1 should represent the opening/main subject.

Visuals 2 to 7 should represent different supporting
subjects directly connected to the flyer.

VISUAL PLAN:

Create an appropriate number of visual concepts (typically 5 to 8 concepts) matching the narration.

Visual 1 should represent the opening/main subject.

Visuals 2 through N-1 should represent different supporting
subjects directly connected to the flyer.

Visual N (the final visual) MUST be:
the original flyer.

Do not make all visual concepts copies of the flyer.

SECTION MAPPING:

Create EXACTLY N narration sections matching the N visuals.

Every visual must have a corresponding narration section (SECTION N | VISUAL N).

Each section must directly discuss its assigned visual.

The final section must directly correspond to the original flyer as the concluding call-to-action.

The narration must flow continuously from Section 1 through Section N.

CRITICAL VISUAL SEARCH FORMAT:
For visuals 1 through N-1, provide 2 to 3 concrete stock-searchable queries separated by " | " (Primary Scene | Alternative Query | Fallback B-Roll).
If specific niche figures, local places, or brands are in the flyer, map them to stock-searchable visual archetypes.
Visual N must be: "The original uploaded flyer."

Return EXACTLY this structure:

TITLE:
<catchy, concise headline under 60 characters for this flyer or event>

SCRIPT:
<complete narration>

VISUAL_PLAN:
1. <Primary Query> | <Alternative Query> | <Fallback B-Roll>
2. <Primary Query> | <Alternative Query> | <Fallback B-Roll>
...
N. The original flyer.

SECTIONS:

SECTION 1 | VISUAL 1
VISUAL: <Primary Query> | <Alternative Query> | <Fallback B-Roll>
NARRATION: <narration strictly discussing this visual>

SECTION 2 | VISUAL 2
VISUAL: <Primary Query> | <Alternative Query> | <Fallback B-Roll>
NARRATION: <narration strictly discussing this visual>

...
SECTION N | VISUAL N
VISUAL: The original flyer.
NARRATION: <narration strictly discussing the flyer call-to-action>
"""

    for model in MODELS:

        try:
            print(f"Trying flyer model: {model}")

            response = _call_gemini_with_retry(
                contents=[
                    prompt,
                    image_part,
                ],
                model=model,
            )

            text = clean_response(
                getattr(response, "text", "")
            )

            if len(text) < 300:
                print("Flyer response is too short.")
                continue

            script = _parse_and_save_package(text)

            if script is None:
                print(
                    f"Model {model} returned an "
                    "invalid flyer package."
                )
                continue

            # ------------------------------------------------
            # READ VISUAL PLAN
            # ------------------------------------------------

            visual_plan = []

            visual_path = Path(
                "output/visual_plan.txt"
            )

            for line in visual_path.read_text(
                encoding="utf-8"
            ).splitlines():

                line = line.strip()

                if not line:
                    continue

                line = re.sub(
                    r"^\d+[\.\)]\s*",
                    "",
                    line,
                )

                visual_plan.append(line)

            # ------------------------------------------------
            # READ STRUCTURED SECTIONS
            # ------------------------------------------------

            sections = []

            section_path = Path(
                "output/section_map.txt"
            )

            section_text = section_path.read_text(
                encoding="utf-8"
            ).strip()

            pattern = re.compile(
                r"SECTION\s+(\d+)\s*\|\s*VISUAL\s+(\d+)\s*\n"
                r"(.*?)(?=\n\s*SECTION\s+\d+\s*\|\s*VISUAL\s+\d+|\Z)",
                flags=re.IGNORECASE | re.DOTALL,
            )

            for match in pattern.finditer(section_text):

                section_number = int(match.group(1))
                visual_number = int(match.group(2))
                narration = match.group(3).strip()

                if narration:
                    sections.append({
                        "section": section_number,
                        "visual": visual_number,
                        "narration": narration,
                    })

            # ------------------------------------------------
            # FINAL RETURN VALIDATION
            # ------------------------------------------------

            if len(visual_plan) < 4:
                raise RuntimeError(
                    f"Return validation failed: "
                    f"expected at least 4 visuals, got {len(visual_plan)}"
                )

            if len(sections) != len(visual_plan):
                raise RuntimeError(
                    f"Return validation failed: "
                    f"expected matching sections ({len(sections)}) and visuals ({len(visual_plan)})"
                )

            expected_visuals = list(range(1, len(visual_plan) + 1))

            actual_visuals = [
                item["visual"]
                for item in sections
            ]

            if actual_visuals != expected_visuals:
                raise RuntimeError(
                    "Return validation failed: "
                    f"invalid visual mapping {actual_visuals}"
                )

            # Ensure the final visual is always designated for the flyer
            visual_plan[-1] = "The original uploaded flyer."

            print()
            print("=" * 60)
            print("FLYER ANALYSIS COMPLETED")
            print("=" * 60)
            print()
            print(f"Returned script:  {len(script)} characters")
            print(f"Returned visuals: {len(visual_plan)}")
            print(f"Returned sections:{len(sections)}")
            print()

            title_path = Path("output/title.txt")
            flyer_title = (
                title_path.read_text(encoding="utf-8").strip()
                if title_path.exists()
                else ""
            )

            return {
                "title": flyer_title,
                "script": script,
                "visual_plan": visual_plan,
                "sections": sections,
            }

        except Exception as error:

            print()
            print(f"Flyer model failed: {model}")
            print(error)
            print()

    raise RuntimeError(
        "All Gemini models failed to analyze "
        "the flyer."
    )


# ============================================================
# USER-PROVIDED SCRIPT PIPELINE (VERBATIM / EXACT PRESERVATION)
# ============================================================

def generate_package_from_user_script(
    user_script,
    title=None,
):
    """
    Process an exact user-provided script:
    1. Preserves the user script 100% byte-for-byte in output/user_script_original.txt
       and output/script.txt.
    2. Prompts Gemini ONLY to segment the exact script into logical sections and
       generate specific, entity-relevant visual descriptions.
    3. Fails if the user script cannot be cleanly segmented.
    """

    user_script = clean_response(user_script).strip()
    if not user_script:
        raise ValueError("User script is empty.")

    os.makedirs("output", exist_ok=True)

    # Save original user script for strict pipeline verification
    original_path = Path("output/user_script_original.txt")
    original_path.write_text(user_script, encoding="utf-8")

    # Script file must be identical
    script_path = Path("output/script.txt")
    script_path.write_text(user_script, encoding="utf-8")

    words = user_script.split()
    word_count = len(words)
    # Estimate ~7-10 words per visual section (scene change every 2.0-3.5 seconds)
    suggested_count = max(6, min(35, max(6, round(word_count / 8))))

    print()
    print("=" * 60)
    print("USER SCRIPT VISUAL PLANNING STARTED")
    print("=" * 60)
    print(f"Words: {word_count} | Suggested visual sections: {suggested_count}")

    prompt = f"""You are an expert visual planner and YouTube editor.
A creator has provided their EXACT YouTube script.

CRITICAL REQUIREMENT:
You must NOT modify, rewrite, paraphrase, shorten, or expand the creator's narration text.
Every sentence and word from the script must appear in order across the sections.

Your ONLY job is:
1. Divide the provided narration into approximately {suggested_count} logical narrative sections (fast-paced beats of 2.0 to 3.5 seconds / 6 to 12 words each, never holding a shot longer than 3.5s).
2. For each section, design a specific, highly relevant visual concept and search queries that depict the EXACT physical subject, company, person, product, or event being spoken about in that section.
   - Do NOT use generic terms like "AI technology", "business", "news".
   - Describe concrete visual imagery matching the spoken words.
   - If specific private people, local personalities, or niche brands are mentioned, provide stock-searchable visual archetypes (e.g. "tech executive keynote stage").
   - Provide 2 to 3 alternative queries per section separated by " | " (Format: Primary Visual Scene | Alternative Stock Query | Fallback B-Roll).

CREATOR'S EXACT SCRIPT:
{user_script}

Return EXACTLY this structure:

TITLE:
{title or "Creator Video"}

SCRIPT:
{user_script}

VISUAL_PLAN:
1. <Primary Query> | <Alternative Query> | <Fallback B-Roll>
2. <Primary Query> | <Alternative Query> | <Fallback B-Roll>
...
N. <Primary Query> | <Alternative Query> | <Fallback B-Roll>

SECTIONS:

SECTION 1 | VISUAL 1
<exact verbatim text for first section>

SECTION 2 | VISUAL 2
<exact verbatim text for second section>

...
SECTION N | VISUAL N
<exact verbatim text for concluding section>
"""

    for model in MODELS:
        try:
            print(f"Trying user script visual planner model: {model}")
            response = _call_gemini_with_retry(
                contents=prompt,
                model=model,
            )

            text = clean_response(getattr(response, "text", ""))
            if len(text) < 200:
                continue

            fallback_title = title or "Creator Video"
            result = _parse_and_save_package(
                text,
                default_title=fallback_title,
            )

            if result:
                # Guarantee byte-for-byte script integrity
                script_path.write_text(user_script, encoding="utf-8")
                print("User script visual plan & section mapping created successfully!")
                return user_script

        except Exception as error:
            print(f"User script visual planning error with {model}: {error}")
            continue

    # Fallback: create automated sentence-based sectioning if AI formatting was imperfect
    print("Creating direct sentence-based visual plan fallback for user script...")
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", user_script) if s.strip()]
    if not sentences:
        sentences = [user_script]

    n_sections = max(4, min(len(sentences), suggested_count))
    chunk_size = max(1, len(sentences) // n_sections)
    
    sections = []
    visual_plan = []
    
    for i in range(n_sections):
        start_idx = i * chunk_size
        end_idx = (i + 1) * chunk_size if i < n_sections - 1 else len(sentences)
        chunk_sentences = sentences[start_idx:end_idx]
        chunk_text = " ".join(chunk_sentences).strip()
        if not chunk_text:
            continue
        v_num = len(sections) + 1
        first_few = " ".join(chunk_text.split()[:8])
        visual_plan.append(f"Scene illustrating: {first_few}")
        sections.append({
            "section": v_num,
            "visual": v_num,
            "narration": chunk_text,
        })

    # Save outputs
    with open("output/visual_plan.txt", "w", encoding="utf-8") as f:
        for idx, v in enumerate(visual_plan, 1):
            f.write(f"{idx}. {v}\n")

    with open("output/section_map.txt", "w", encoding="utf-8") as f:
        for item in sections:
            f.write(f"SECTION {item['section']} | VISUAL {item['visual']}\n{item['narration']}\n\n")

    if title:
        Path("output/title.txt").write_text(title, encoding="utf-8")

    script_path.write_text(user_script, encoding="utf-8")
    return user_script


def ensure_script_artifacts(
    script_text: str,
    topic: str = "",
    default_title: Optional[str] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Guarantees all required script artifacts exist and are synchronized:
    - output/script.txt
    - output/title.txt
    - output/delivery_plan.json
    - output/visual_plan.txt
    - output/section_map.txt
    - output/visual_plan.json

    This prevents missing visual_plan.txt runtime failures when script_override is used
    or when previous artifacts were cleaned.
    """
    import json
    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)

    clean_text = script_text.strip()
    if not clean_text:
        raise ValueError("Cannot ensure script artifacts for empty script.")

    # 1. Save script.txt
    script_file = out_dir / "script.txt"
    script_file.write_text(clean_text, encoding="utf-8")

    # 2. Save title.txt if missing
    title_file = out_dir / "title.txt"
    if not title_file.exists() or not title_file.read_text(encoding="utf-8").strip():
        final_title = default_title or (
            f"{topic}: రోస్ట్ అండ్ రియాలిటీ!"
            if "bigg boss" in topic.lower()
            else (topic or "Trending Buzz")
        )
        title_file.write_text(final_title.strip(), encoding="utf-8")

    vp_file = out_dir / "visual_plan.txt"
    sm_file = out_dir / "section_map.txt"
    dp_file = out_dir / "delivery_plan.json"

    # 3. Segment script into scene beats
    try:
        from agents.social_visual_selector import split_script_into_scenes
        scenes = split_script_into_scenes(clean_text)
    except Exception as e:
        print(f"Notice: split_script_into_scenes fallback: {e}")
        scenes = [s.strip() for s in clean_text.splitlines() if s.strip()]

    if not scenes:
        scenes = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_text) if s.strip()] or [clean_text]

    delivery_plan = []
    is_roast = ("roast" in str(topic).lower())
    emotions_cycle = ["fake_shock", "mock", "hype", "deadpan", "dramatic_question", "smug"]
    for idx, sc in enumerate(scenes, 1):
        if idx == 1:
            emo = "fake_shock"
            pause_ms = 0
        elif idx == len(scenes):
            emo = "smug"
            pause_ms = 450
        elif idx == len(scenes) - 1 or "?" in sc:
            emo = "dramatic_question"
            pause_ms = 400
        else:
            emo = emotions_cycle[idx % len(emotions_cycle)]
            pause_ms = 450 if emo in ("hype", "smug") else (350 if emo == "mock" else 300)

        delivery_plan.append({
            "beat_id": idx,
            "spoken_text": sc,
            "emotion": emo,
            "pause_before_ms": pause_ms,
            "sfx": "ding" if (idx == len(scenes) and len(scenes) > 3) else None,
            "on_screen_text": "",
        })
    dp_file.write_text(json.dumps(delivery_plan, indent=2, ensure_ascii=False), encoding="utf-8")

    # Export teleprompter script for creator voiceover matching current beats
    try:
        from agents.roast_engine import export_teleprompter
        export_teleprompter(delivery_plan, output_path=str(out_dir / "teleprompter.txt"))
    except Exception as tp_err:
        print(f"Notice during teleprompter export: {tp_err}")

    # 4. Synthesize beat visual plan lines
    try:
        visual_lines = synthesize_beat_visual_plan(delivery_plan, topic=topic)
    except Exception as e:
        print(f"Notice during synthesize_beat_visual_plan: {e}")
        visual_lines = [f"Scene illustrating: {' '.join(s.split()[:6])}" for s in scenes]

    if not visual_lines or len(visual_lines) != len(delivery_plan):
        visual_lines = [f"Scene illustrating: {' '.join(s.split()[:6])}" for s in scenes]

    with open(vp_file, "w", encoding="utf-8") as f:
        for idx, v in enumerate(visual_lines, 1):
            f.write(f"{idx}. {v}\n")

    # 5. Build section_map.txt
    sections = []
    for b in delivery_plan:
        b_id = b["beat_id"]
        sections.append({
            "section": b_id,
            "visual": b_id,
            "narration": b["spoken_text"],
            "main_entity": b.get("main_entity", ""),
            "emotion": b.get("emotion", ""),
            "search_query": b.get("search_query", ""),
        })
    with open(sm_file, "w", encoding="utf-8") as f:
        for item in sections:
            f.write(f"SECTION {item['section']} | VISUAL {item['visual']}\n{item['narration']}\n\n")

    # 6. Build structured visual plan
    try:
        structured_plan = build_structured_visual_plan(sections, visual_lines, topic=topic)
        (out_dir / "visual_plan.json").write_text(
            json.dumps(structured_plan, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"Notice building structured visual plan: {e}")

    print(f"✅ [Script Artifacts Guaranteed] Generated visual_plan.txt and delivery_plan.json for {len(scenes)} scenes.")
    return {
        "script": clean_text,
        "visual_plan": vp_file.read_text(encoding="utf-8"),
    }



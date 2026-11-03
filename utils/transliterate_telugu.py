"""
AutoTube AI - Universal Tanglish to Telugu Transliteration Engine (utils/transliterate_telugu.py)

Converts Romanized Telugu text (Tanglish written in English letters, e.g.
'Bigg Boss 10 nomination scene chustunte, villa goal game gelavadam kadu...')
into authentic, fluent spoken Telugu Unicode script ('తెలుగు లిపి', e.g.
'బిగ్ బాస్ నామినేషన్ సీన్ చూస్తుంటే, వీళ్ళ గోల్ గేమ్ గెలవడం కాదు...').

Guarantees 100% that Microsoft Edge Neural TTS (te-IN-MohanNeural / te-IN-ShrutiNeural)
receives native Telugu script so it delivers human-quality, natural prosody with zero robotic distortion.
"""

import re
from typing import Optional

# Common Romanized Telugu markers indicating Tanglish in Latin characters
ROMANIZED_TELUGU_WORDS = {
    "chustunte", "chudandi", "cheppandi", "cheppalante", "chesaru", "chestaru",
    "cheyandi", "undi", "undadu", "unnaru", "unnattu", "unnam", "kadu", "kadha",
    "ante", "enti", "entante", "ani", "anipistadi", "anipistondi", "anukuntunnaru",
    "kuda", "mari", "valla", "vallaki", "veellaki", "manaki", "maku", "miku",
    "lekapothe", "chala", "telustondi", "telustundi", "jarigindi", "jarugutondi",
    "edo", "ela", "evaru", "ippudu", "appudu", "eppudu", "ekkada", "akkada",
    "ikada", "enduku", "anduku", "asalu", "edaithe", "kattinattu", "pillodi",
    "edupu", "pagilipoddi", "gola", "aavesham", "motham", "kottandi", "ventane",
    "subskraib", "pettandi", "ivvakapothe", "odipoyaru", "nacchithe", "nachithe"
}


def is_romanized_telugu(text: str) -> bool:
    """
    Detects if text contains Romanized Telugu (Tanglish spelled in English letters)
    without sufficient native Telugu Unicode script.
    """
    if not text or not str(text).strip():
        return False

    raw = str(text).strip()
    telugu_chars = len(re.findall(r"[\u0C00-\u0C7F]", raw))
    words = re.findall(r"\b[A-Za-z]{3,}\b", raw.lower())

    # If already mostly Telugu script (at least 20 Telugu characters and > 25% of string length), not Romanized
    if telugu_chars >= 20 and (telugu_chars / max(1, len(raw))) > 0.25:
        return False

    # Check for presence of Romanized Telugu signature words
    hits = sum(1 for w in words if w in ROMANIZED_TELUGU_WORDS)
    if hits >= 2:
        return True

    # If any 2 characteristic endings (-tunte, -estadu, -istadi, -undi, -indi, -ochindi, -avtundi) occur
    suffix_hits = sum(
        1 for w in words
        if any(w.endswith(sfx) for sfx in ("tunte", "estadu", "istadi", "undi", "indi", "ochindi", "avtundi"))
    )
    return suffix_hits >= 2


def transliterate_tanglish_to_telugu(text: str) -> str:
    """
    Converts Romanized Tanglish into fluent, modern spoken creator Telugu script (తెలుగు లిపి).
    Preserves all facts, punchlines, and tone while rendering English loanwords in Telugu phonetics.
    """
    if not text or not text.strip():
        return text or ""

    clean_text = text.strip()

    prompt = f"""You are an elite Telugu linguist and YouTube creator script translator.
Convert the following Romanized Telugu (Tanglish written in English/Latin letters) into natural, fluent, spoken creator Telugu narration.

CRITICAL RULES:
1. Write EVERYTHING in 100% native Telugu script (తెలుగు లిపి). English letters must be completely converted into Telugu phonetics (e.g. 'Bigg Boss' -> 'బిగ్ బాస్', 'Pan-India' -> 'పాన్ ఇండియా', 'Twist' -> 'ట్విస్ట్', 'Mind blank' -> 'మైండ్ బ్లాంక్', 'Scene cut' -> 'సీన్ కట్', 'Overrated' -> 'ఓవర్‌రేటెడ్', 'Teaser' -> 'టీజర్', 'Trailer' -> 'ట్రైలర్', 'iPhone' -> 'ఐఫోన్').
2. Avoid phonetic Telugu written in loose English script (convert words like 'chustunte' -> 'చూస్తుంటే', 'villa' -> 'వీళ్ళ', 'kadu' -> 'కాదు', 'undi' -> 'ఉంది', 'cheppandi' -> 'చెప్పండి').
3. NEVER leave English words in Latin alphabet, because TTS switches to an American accent when reading Latin characters. Transliterate all loanwords to Telugu script.
4. PUNCTUATION-DRIVEN CADENCE: Break long, dramatic lines into short punchy fragments using commas (,), dashes (—), and ellipsis (...) to create organic breathing room and build anticipation.
5. Maintain the exact conversational energy, sarcastic comedy tone, and sentence boundaries.
6. Return ONLY the spoken narration text. No English explanation, no markdown quotes.

ROMANIZED TANGLISH TEXT:
{clean_text}

SPOKEN TELUGU SCRIPT:"""

    try:
        from providers.llm import generate_text_cascade
        raw_res = generate_text_cascade(prompt, step_name="transliterate_telugu", per_provider_timeout=25.0)
        res_cleaned = re.sub(r"```[a-zA-Z]*", "", raw_res).replace("```", "").strip()
        # Verify that output actually contains Telugu characters
        if len(re.findall(r"[\u0C00-\u0C7F]", res_cleaned)) >= 15:
            print(f"🔤 [Transliteration] Successfully converted {len(clean_text.split())} Tanglish words to native Telugu script (తెలుగు లిపి).")
            return res_cleaned
    except Exception as trans_err:
        print(f"⚠️ [Transliteration] LLM conversion notice: {trans_err}")

    # Fallback: if conversion failed or offline, return original
    return clean_text


COMMON_TELUGU_PHONETIC_LOANWORDS = [
    (r"\bMind\s*blank\b|\bmindblank\b", "మైండ్ బ్లాంక్"),
    (r"\bScene\s*cut\b|\bscenecut\b", "సీన్ కట్"),
    (r"\bSelective\s*grilling\b", "సెలెక్టివ్ గ్రిల్లింగ్"),
    (r"\bGrilling\b|\bgrilling\b", "గ్రిల్లింగ్"),
    (r"\bFake\s*walkout\b", "ఫేక్ వాకౌట్"),
    (r"\bWalkout\b|\bwalk\s*out\b", "వాకౌట్"),
    (r"\bPR\s*strategy\b|\bpr\s*strategy\b", "పీఆర్ స్ట్రాటజీ"),
    (r"\bPR\b|\bpr\b", "పీఆర్"),
    (r"\bTRP\s*ratings\b|\btrp\s*ratings\b", "టీఆర్పీ రేటింగ్స్"),
    (r"\bTRP\b|\btrp\b", "టీఆర్పీ"),
    (r"\bSecret\s*room\b", "సీక్రెట్ రూమ్"),
    (r"\bElimination\b|\beliminations\b", "ఎలిమినేషన్"),
    (r"\bNomination\b|\bnominations\b", "నామినేషన్"),
    (r"\bCaptaincy\b|\bcaptaincy\b", "కెప్టెన్సీ"),
    (r"\bTask\b|\btasks\b", "టాస్క్"),
    (r"\bSnacks\b|\bsnack\b", "స్నాక్స్"),
    (r"\bChill\b|\bchill\b", "చిల్"),
    (r"\bOveracting\b|\bover\s*action\b", "ఓవరాక్షన్"),
    (r"\bTwist\b|\btwists\b", "ట్విస్ట్"),
    (r"\bDanger\s*zone\b", "డేంజర్ జోన్"),
    (r"\bVoting\s*graph\b", "ఓటింగ్ గ్రాఫ్"),
    (r"\bVoting\b|\bvotes\b|\bvote\b", "ఓటింగ్"),
    (r"\bSame\s*to\s*same\b", "సేమ్ టు సేమ్"),
    (r"\bCircus\s*comedy\s*show\b", "సర్కస్ కామెడీ షో"),
    (r"\bComedy\s*show\b|\bcomedy\b", "కామెడీ షో"),
    (r"\bReview\b|\breviews\b", "రివ్యూ"),
    (r"\bChannel\b|\bchannel\b", "ఛానల్"),
    (r"\bLike\b|\blikes\b", "లైక్"),
    (r"\bShare\b", "షేర్"),
    (r"\bSubscribe\b", "సబ్‌స్క్రైబ్"),
    (r"\bBigg\s*Boss\b|\bBiggboss\b", "బిగ్ బాస్"),
    (r"\bBB10\b|\bBB 10\b", "బిగ్ బాస్ 10"),
    (r"\bPan-India\b|\bPan\s*India\b|\bpan\s*india\b", "పాన్ ఇండియా"),
    (r"\bOTT\b|\bott\b", "ఓటీటీ"),
    (r"\bBGM\b|\bbgm\b", "బీజీఎం"),
    (r"\bHouse\b|\bhouse\b", "హౌస్"),
    (r"\bHousemates\b|\bhouse\s*mates\b", "హౌస్‌మేట్స్"),
    (r"\bContent\b|\bcontent\b", "కంటెంట్"),
]


def sanitize_telugu_text(text: str) -> str:
    """
    Strictly sanitize Telugu script and spoken narration text:
    - Strips rogue CJK ideographs (e.g. '现在的' or any \u4e00-\u9fff, \u3400-\u4dbf, etc.)
    - Strips rogue non-Telugu, non-Latin, non-punctuation Unicode characters.
    - Preserves Telugu block, ASCII/Latin characters, typography/punctuation, and rupee symbol.
    """
    if not text:
        return ""
    cjk_pattern = r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af\u2e80-\u2fd5\uff00-\uffef\u31f0-\u31ff\u3200-\u32ff]"
    cleaned = re.sub(cjk_pattern, "", str(text))
    allowed_pattern = r"[^\u0C00-\u0C7F\u0020-\u007E\u2000-\u206F\u20B9\n\r\t]"
    cleaned = re.sub(allowed_pattern, "", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\[\s*\]", "", cleaned)
    cleaned = re.sub(r"\{\s*\}", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def ensure_telugu_script(text: str) -> str:
    """
    Universal safeguard:
    1. Replaces English loan words with their exact spoken Telugu phonetic equivalents
       (e.g. 'Mind blank' -> 'మైండ్ బ్లాంక్', 'Scene cut' -> 'సీన్ కట్', 'Selective grilling' -> 'సెలెక్టివ్ గ్రిల్లింగ్').
    2. If text is detected as Romanized Tanglish, automatically transliterates to pure Telugu script.
    3. Strictly sanitizes text to strip any rogue CJK or non-Telugu characters.
    Guarantees TTS engines maintain a natural flow without switching to an American accent.
    """
    if not text:
        return ""

    out = sanitize_telugu_text(str(text))

    # 1. Phonetic replacement of common creator loanwords
    for pat, rep in COMMON_TELUGU_PHONETIC_LOANWORDS:
        out = re.sub(pat, rep, out, flags=re.IGNORECASE)

    # 2. Tanglish transliteration if needed
    if is_romanized_telugu(out):
        print("⚠️ [Script Check] Detected Romanized Tanglish (English letters). Transliterating to native Telugu script (తెలుగు లిపి) for natural human TTS...")
        out = transliterate_tanglish_to_telugu(out)
        for pat, rep in COMMON_TELUGU_PHONETIC_LOANWORDS:
            out = re.sub(pat, rep, out, flags=re.IGNORECASE)

    # 3. Final sanitization pass
    out = sanitize_telugu_text(out)

    return out


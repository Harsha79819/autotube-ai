"""
data/bb10_contestants.py - Bigg Boss Telugu Season 10 Contestant Registry & Disambiguation Rules

Enforces:
1. Strict disambiguation between Season 10 housemates and prior season namesakes
   (e.g., Rohit Patnam vs Rohit Sahni, Shalini Patel vs Shalini Nair).
2. Prior season firewall (Season 1 to 9).
3. Anti-politics / non-entertainment entity guards.
"""

from typing import List, Dict, Tuple, Optional
import re

POLITICAL_BLACKLIST: List[str] = [
    "jagan", "ysr", "ysrcp", "chandrababu", "naidu", "tdp", "pawan kalyan",
    "janasena", "revanth", "kcr", "brs", "modi", "rahul gandhi", "court",
    "arrest", "assembly", "amaravati", "parliament", "mla", "mp", "minister", "police"
]

POLITICAL_URL_SEGMENTS: List[str] = [
    "/politics/", "/political/", "/telangana/", "/andhra-pradesh/",
    "/national/", "/crime/", "/assembly/", "/election/", "/elections/"
]

PRIOR_SEASON_REGEXES: List[str] = [
    r"\bseason\s*[-_]?(?:telugu\s*[-_]?)?([1-9]|1[1-9])\b",
    r"\bbigg\s*[-_]?boss\s*[-_]?(?:telugu\s*[-_]?)?([1-9]|1[1-9])\b",
    r"\bbb\s*[-_]?(?:telugu\s*[-_]?)?([1-9]|1[1-9])\b",
    r"\bmalayalam\b",
    r"\bkannada\b",
    r"\bnau\b",
    r"\bhindi\b",
    r"\btamil\b",
    r"\bmarathi\b",
    r"\bthakare\b",
    r"\bshiv\s*thakare\b",
]

CONTESTANTS_BB10: Dict[str, Dict] = {
    "rohit": {
        "full_name": "Rohit Patnam",
        "aliases": ["rohit", "rohit patnam", "రోహిత్", "రోహిత్ పట్నం"],
        "negative_tokens": ["sahni", "marina", "season 6", "bb6", "2022", "season-6", "wife"],
        "status": "eliminated",
        "is_active": False,
    },
    "shalini": {
        "full_name": "Shalini Patel",
        "aliases": ["shalini", "shalini patel", "shalini damera", "శాలిని", "శాలిని పటేల్", "షాలిని"],
        "negative_tokens": ["nair", "malayalam", "season 4", "bb4", "zain"],
        "status": "eliminated",
        "is_active": False,
    },
    "aman": {
        "full_name": "Aman Masud",
        "aliases": ["aman", "aman masud", "aman masood", "అమన్", "అమన్ మసూద్"],
        "negative_tokens": ["verma", "nau", "hindi", "season 9"],
    },
    "thrigun": {
        "full_name": "Thrigun Eswaran",
        "aliases": ["thrigun", "trigun", "thrigun eswaran", "త్రిగుణ్", "త్రిగుణ్ ఈశ్వరన్"],
        "negative_tokens": [],
    },
    "temper vamsi": {
        "full_name": "Temper Vamsi",
        "aliases": ["temper vamsi", "vamsi", "టెంపర్ వంశీ", "వంశీ"],
        "negative_tokens": [],
        "is_captain": True,
    },
    "charan": {
        "full_name": "Charan Mahadev",
        "aliases": ["charan", "charan mahadev", "charan kumar", "చరణ్", "చరణ్ మహాదేవ్"],
        "negative_tokens": ["ram charan"],
        "status": "eliminated",
        "is_active": False,
    },
    "sudheer": {
        "full_name": "Sudheer Reddy",
        "aliases": ["sudheer", "sudheer reddy", "sudheer talks", "సుధీర్", "సుధీర్ రెడ్డి"],
        "negative_tokens": ["rashmi", "sudigali"],
    },
    "nagarjuna": {
        "full_name": "Akkineni Nagarjuna",
        "aliases": ["nagarjuna", "akkineni nagarjuna", "నాగార్జున", "king nag"],
        "negative_tokens": [],
    },
    "chaithra": {
        "full_name": "Chaithra Rai",
        "aliases": ["chaithra", "chaithra rai", "చైత్ర", "చైత్ర రాయ్"],
        "negative_tokens": [],
        "status": "eliminated",
        "is_active": False,
    },
    "jhansi": {
        "full_name": "Gundeboina Jhansi",
        "aliases": ["jhansi", "singer jhansi", "gundeboina jhansi", "ఝాన్సీ", "సింగర్ ఝాన్సీ"],
        "negative_tokens": ["anchor jhansi", "fort"],
        "status": "eliminated",
        "is_active": False,
    },
    "debjani": {
        "full_name": "Debjani Modak",
        "aliases": ["debjani", "debjani modak", "దేబ్జాని", "దేవజాని"],
        "negative_tokens": [],
        "is_active": True,
    },
    "ram prasad": {
        "full_name": "Auto Ram Prasad",
        "aliases": ["ram prasad", "auto ram prasad", "రామ్ ప్రసాద్", "ఆటో రామ్ ప్రసాద్"],
        "negative_tokens": [],
        "is_active": True,
    },
    "shiv": {
        "full_name": "Shiv",
        "aliases": ["shiv", "shiva", "anchor shiva", "శివ్", "శివ"],
        "negative_tokens": ["lord shiva", "shiva rajkumar", "temple", "pooja", "bhagwan", "thakare", "shiv thakare", "khatron", "lock upp", "roadies", "hindi", "marathi"],
        "is_active": True,
    },
    "naresh": {
        "full_name": "Potti Naresh",
        "aliases": ["naresh", "potti naresh", "jabardasth naresh", "నరేష్", "పొట్టి నరేష్"],
        "negative_tokens": ["allari naresh", "senior naresh", "vk naresh", "pavitra lokesh", "actor naresh", "mahesh babu"],
        "is_active": True,
    },
    "mukesh": {
        "full_name": "Mukesh Gowda",
        "aliases": ["mukesh", "mukesh gowda", "ముఖేష్", "ముఖేష్ గౌడ"],
        "negative_tokens": ["mukesh ambani", "reliance"],
        "is_active": True,
    },
    "varshini": {
        "full_name": "Varshini Sounderajan",
        "aliases": ["varshini", "varshini sounderajan", "వర్షిణి", "వర్షిణి సౌందరరాజన్"],
        "negative_tokens": [],
        "is_active": True,
    },
    "rama krishna": {
        "full_name": "Rama Krishna",
        "aliases": ["rama krishna", "ramakrishna", "రామకృష్ణ"],
        "negative_tokens": ["ramakrishna paramahamsa", "mission", "math"],
        "is_active": True,
    },
    "swetha": {
        "full_name": "Swetha",
        "aliases": ["swetha", "sweatha", "శ్వేత"],
        "negative_tokens": [],
        "is_active": True,
    },
    "neethu": {
        "full_name": "Neethu Natraj",
        "aliases": ["neethu", "neethu natraj", "నీతు", "నీతు నటరాజ్"],
        "negative_tokens": [],
        "is_active": True,
    },
}

# Ground Truth Realities for Current Week:
THIS_WEEK_NO_ELIMINATION = True
CURRENT_CAPTAIN = "Temper Vamsi"
ACTIVE_CONTESTANTS_SUMMARY = "Debjani Modak, Auto Ram Prasad, Shiv, Potti Naresh, Mukesh Gowda, Varshini Sounderajan, Aman Masud, Thrigun Eswaran, Rama Krishna, Swetha, Neethu Natraj, Temper Vamsi (Captain), Sudheer Reddy"

PAST_SEASONS_KNOWN_NAMES: List[str] = [
    "kalyan padala", "winner kalyan", "ashwini sri", "ashwini",
    "pallavi prashanth", "sivaji", "amardeep chowdary", "shobha shetty",
    "rohit sahni", "marina abraham", "vj sunny", "kaushal", "kaushal manda",
    "bindu madhavi", "rahul sipligunj", "shiva jyothi", "shanmukh jaswanth",
    "thakare", "shiv thakare", "jr ntr", "jr. ntr", "siva balaji", "abhijeet"
]

IRRELEVANT_DOMAINS_AND_PATHS: List[str] = [
    "careers.", "/fashion/", "/lifestyle/", "/apparel/", "/clothing/",
    "boutique", "etsy.com", "pinterest.com/pin/", "aliexpress"
]


def is_bigg_boss_context(text: str) -> bool:
    """Checks if the given text relates to the Bigg Boss show."""
    if not text:
        return False
    t_lower = str(text).lower()
    if any(k in t_lower for k in ("bigg boss", "biggboss", "big boss", "bigboss", "బిగ్ బాస్", "బిగ్‌బాస్")):
        return True
    
    # Check if any BB10 contestant is mentioned alongside Bigg Boss house/task keywords
    bb_keywords = [
        "jail", "జైలు", "జైల్లో", "నామినేషన్", "ఎలిమినేషన్", "కెప్టెన్", "గేమ్‌ప్లే",
        "gameplay", "housemates", "హౌస్", "వరస్ట్", "టాస్క్", "task", "assembly"
    ]
    contestant_matches = 0
    for c_info in CONTESTANTS_BB10.values():
        if any(al in t_lower or al in text for al in c_info["aliases"]):
            contestant_matches += 1

    if contestant_matches >= 1 and any(kw in t_lower or kw in text for kw in bb_keywords):
        return True
    if contestant_matches >= 2:
        return True
    return False


def check_political_blacklist(text: str, url: str = "") -> Tuple[bool, Optional[str]]:
    """Returns (True, token) if text or URL matches political blacklist."""
    if url:
        u_lower = url.lower()
        for seg in POLITICAL_URL_SEGMENTS:
            if seg in u_lower:
                return True, f"political URL segment '{seg}'"

    if not text:
        return False, None
    t_lower = str(text).lower()
    for token in POLITICAL_BLACKLIST:
        pattern = r"\b" + re.escape(token) + r"\b"
        if re.search(pattern, t_lower):
            return True, token
    return False, None


def check_prior_seasons(text: str) -> Tuple[bool, Optional[str]]:
    """Returns (True, token) if text references an older Bigg Boss season (1 to 9)."""
    if not text:
        return False, None
    t_lower = str(text).lower()
    for pattern in PRIOR_SEASON_REGEXES:
        m = re.search(pattern, t_lower)
        if m:
            return True, m.group(0)
    for name in PAST_SEASONS_KNOWN_NAMES:
        pattern = r"\b" + r"\s+".join(re.escape(part) for part in name.split()) + r"\b"
        if re.search(pattern, t_lower):
            return True, f"past season personality '{name}'"
    # Prior years in BB context (2017 to 2025 are Seasons 1-9)
    if is_bigg_boss_context(t_lower):
        m_year = re.search(r"\b(201[7-9]|202[0-5])\b", t_lower)
        if m_year:
            return True, f"prior season year '{m_year.group(0)}'"
    return False, None


def validate_candidate_metadata(
    url: str,
    title: str = "",
    caption: str = "",
    entity_hint: str = "",
    is_bb: bool = True
) -> Tuple[bool, str]:
    """
    Comprehensive validator for candidate image/article metadata.
    Returns (True, "OK") or (False, reason).
    """
    import urllib.parse
    norm_url = urllib.parse.unquote(url).replace("+", " ").replace("_", " ").replace("-", " ")
    combined = f"{url} {norm_url} {title} {caption}".lower()

    # 0. Negative Memory Ledger persistent exclusions
    try:
        from data.negative_ledger import get_negative_ledger
        neg_ledger = get_negative_ledger()
        clean, neg_reason = neg_ledger.audit_candidate(url=url, ocr_text=combined)
        if not clean:
            return False, neg_reason
    except Exception:
        pass

    # 1. Politics / Non-entertainment guard
    is_pol, pol_tok = check_political_blacklist(combined, url=url)
    if is_pol:
        return False, f"Matches political blacklist token: '{pol_tok}'"

    # 2. Check irrelevant shopping / fashion / careers domains
    for irr in IRRELEVANT_DOMAINS_AND_PATHS:
        if irr in combined:
            return False, f"Matches irrelevant domain/path: '{irr}'"

    # If this is NOT a Bigg Boss topic, prior season check is not applicable
    if not is_bb:
        return True, "OK"

    # 3. Prior Bigg Boss Seasons guard (Seasons 1-9)
    is_prior, prior_tok = check_prior_seasons(combined)
    if is_prior:
        return False, f"Matches disallowed prior season/language token: '{prior_tok}'"

    # 4. Contestant-specific negative tokens disambiguation
    ent_key = entity_hint.strip().lower()
    for key, c_info in CONTESTANTS_BB10.items():
        if key in ent_key or any(a in ent_key for a in c_info["aliases"]):
            for neg in c_info["negative_tokens"]:
                pattern = r"\b" + r"\s+".join(re.escape(part) for part in neg.split()) + r"\b"
                if re.search(pattern, combined):
                    return False, f"Matches disambiguation negative token '{neg}' for {c_info['full_name']}"

    return True, "OK"


def is_eliminated_contestant(name: str) -> bool:
    """Returns True if the contestant has been eliminated from Bigg Boss Telugu 10."""
    name_clean = str(name).strip().lower()
    for key, c_info in CONTESTANTS_BB10.items():
        if c_info.get("status") == "eliminated" or not c_info.get("is_active", True):
            if key in name_clean or any(a.lower() in name_clean for a in c_info.get("aliases", [])):
                return True
    return False


def get_active_contestants() -> List[str]:
    """Returns list of currently active housemates in Bigg Boss Telugu 10."""
    return [
        c_info["full_name"]
        for c_info in CONTESTANTS_BB10.values()
        if c_info.get("is_active", True)
        and c_info.get("status") != "eliminated"
        and c_info["full_name"] != "Akkineni Nagarjuna"
    ]

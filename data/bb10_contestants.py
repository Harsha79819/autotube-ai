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

NON_BB_CELEBS: List[str] = [
    "allu arjun", "allu_arjun", "prabhas", "kalki", "devara", "ram charan",
    "ram_charan", "game changer", "game_changer", "mahesh babu", "mahesh_babu",
    "mahesh", "pawan kalyan", "pawan_kalyan", "chiranjeevi", "balakrishna",
    "sukumar", "dil raju", "rajamouli", "ss rajamouli", "రాజమౌళి", "మహేష్ బాబు"
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
        "negative_tokens": ["verma", "nau", "hindi", "season 9", "bangladesh", "bnp", "politician", "narayanganj", "bengali", "party", "press conference", "rally", "election", "dhaka", "masuduzzaman"],
    },
    "thrigun": {
        "full_name": "Thrigun",
        "aliases": ["thrigun", "trigun", "త్రిగుణ్", "thrigun eswaran"],
        "negative_tokens": ["anime", "manga", "vash", "stampede", "badlands", "cartoon", "analysis of", "podcast", "review", "theme", "themes", "gun", "tri-gun"],
    },
    "temper vamsi": {
        "full_name": "Temper Vamsi",
        "aliases": ["temper vamsi", "vamsi", "టెంపర్ వంశీ", "వంశీ"],
        "negative_tokens": ["chiranjeevi", "balakrishna"],
        "is_captain": False,
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
        "negative_tokens": ["rashmi", "sudigali", "kannada", "serial"],
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
        "is_captain": True,
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
        "full_name": "Swetha Naidu",
        "aliases": ["swetha", "sweatha", "swetha naidu", "swethanaidu", "శ్వేత", "శ్వేత నాయుడు"],
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

# Ground Truth Realities for Current Timeline:
CURRENT_SEASON = 10
CURRENT_WEEK = 11
CURRENT_DAY = 75
THIS_WEEK_NO_ELIMINATION = False
CURRENT_CAPTAIN = "Potti Naresh"
CURRENT_CAPTAIN_TELUGU = "పొట్టి నరేష్"
ACTIVE_CONTESTANTS_SUMMARY = "Debjani Modak, Auto Ram Prasad, Shiv, Potti Naresh (Current Captain), Mukesh Gowda, Varshini Sounderajan, Aman Masud, Thrigun, Rama Krishna, Swetha, Neethu Natraj, Temper Vamsi, Sudheer Reddy"

PAST_SEASONS_KNOWN_NAMES: List[str] = [
    # Season 8 & 9
    "nabeel", "nabeel afridi", "yashmi", "yashmi gowda", "prerana", "prerana kambam",
    "vishnupriya", "vishnu priya", "nainika", "manikanta", "prithviraj", "sonia akula",
    "aditya om", "seetha", "shekhar basha", "bebakka", "hariteja", "gangavva",
    "avinash", "mukku avinash", "rohini", "gautam krishna", "nayani pavani", "mehboob",
    # Season 7
    "kalyan padala", "winner kalyan", "ashwini sri", "ashwini", "pallavi prashanth",
    "sivaji", "amardeep chowdary", "shobha shetty", "tasty teja", "priyanka jain",
    "rathika", "rathika rose", "damini", "subhashree", "pooja murthy", "bhole shavali",
    "prince yawar", "yawar",
    # Season 6
    "revanth", "singer revanth", "srihan", "adi reddy", "geetu royal", "faima",
    "inaya", "inaya sultana", "chanti", "chalaki chanti", "arjun kalyan", "bala aditya",
    "keerthi bhat", "surya", "vj surya", "rohit sahni", "marina abraham",
    # Season 5
    "vj sunny", "shanmukh", "shanmukh jaswanth", "siri hanmanth", "manas", "kajal",
    "priyanka singh", "anchor ravi", "lobo", "vishwa", "hamida", "sweta varma", "lahari shari",
    # Season 4
    "abhijeet", "akhil sarthak", "syed sohel", "ariyana", "ariyana glory", "dethadi harika",
    "monal gajjar", "lasya", "kumar sai", "divi vadthya", "mehaboob",
    # Season 3
    "rahul sipligunj", "sreemukhi", "baba bhaskar", "varun sandesh", "vithika sheru",
    "shiva jyothi", "ali reza", "mahesh vitta", "punarnavi", "ashu reddy", "himaja",
    # Season 2
    "kaushal", "kaushal manda", "geetha madhuri", "tanish", "deepti nallamothu", "samrat",
    "roll rida", "babu gogineni", "tejaswi madivada", "nutan naidu",
    # Season 1 & General non-S10
    "siva balaji", "aadarsh", "navdeep", "archana", "mumaith khan", "dhanraj",
    "sampoornesh babu", "bindu madhavi", "thakare", "shiv thakare"
]

IRRELEVANT_DOMAINS_AND_PATHS: List[str] = [
    "careers.", "/fashion/", "/lifestyle/", "/apparel/", "/clothing/",
    "boutique", "etsy.com", "pinterest.com/pin/", "aliexpress",
    "girlfriend", "dating", "companion", "ai-character", "aigirlfriend",
    "adult", "erotic", "casino", "gambling", "betting", "game", "slot",
    "software", "tutorial", "tool", "pricing", "free-trial"
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

    # 3.1. Strict rejection of old Season 6 contestant Rohit Sahni
    if any(rs in combined for rs in ("rohit sahni", "rohit_sahni", "రోహిత్ సాహ్ని")):
        return False, "Disqualified old Season 6 contestant Rohit Sahni in Bigg Boss 10 context"

    # 3.2. Unrelated Cinema / Celebrity Leakage Firewall for Reality TV
    # When in Bigg Boss context, strictly reject non-contestant Tollywood superstars
    # unless the entity_hint explicitly requested them
    ent_key = entity_hint.strip().lower()
    NON_CONTESTANT_STARS = [
        "allu arjun", "alluarjun", "pushpa", "prabhas", "kalki", "devara",
        "ram charan", "ramcharan", "game changer", "gamechanger", "mahesh babu",
        "maheshbabu", "pawan kalyan", "pawankalyan", "chiranjeevi", "balakrishna",
        "sukumar", "prashanth neel", "dil raju"
    ]
    for star in NON_CONTESTANT_STARS:
        if star in combined and star not in ent_key:
            return False, f"Matches non-contestant Tollywood star '{star}' in Bigg Boss context"

    # 4. Contestant-specific negative tokens disambiguation
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


def get_eliminated_contestants() -> List[str]:
    """Returns list of eliminated contestants in Bigg Boss Telugu 10."""
    return [
        c_info["full_name"]
        for c_info in CONTESTANTS_BB10.values()
        if c_info.get("status") == "eliminated" or not c_info.get("is_active", True)
    ]


def get_current_captain() -> Dict[str, str]:
    """Returns current Week 11 captain details."""
    return {"english": CURRENT_CAPTAIN, "telugu": CURRENT_CAPTAIN_TELUGU}


def get_active_contestants_prompt_context() -> str:
    """Returns grounded prompt instructions for BB10 Week 11 (Day 75+)."""
    active = [
        "Temper Vamsi (టెంపర్ వంశీ)",
        "Thrigun (త్రిగుణ్)",
        "Aman Masud (అమన్)",
        "Sudheer Reddy (సుధీర్ రెడ్డి)",
        "Auto Ram Prasad (ఆటో రామ్ ప్రసాద్)",
        "Potti Naresh (పొట్టి నరేష్ - CURRENT WEEK 11 CAPTAIN)",
        "Debjani Modak (దేబ్జాని)",
        "Shiv (శివ్)",
        "Mukesh Gowda (ముకేష్ గౌడ)",
        "Varshini Sounderajan (వర్షిణి)",
        "Rama Krishna (రామకృష్ణ)",
        "Swetha Naidu (శ్వేత)",
        "Neethu Natraj (నీతు)"
    ]
    eliminated = [
        "Gundeboina Jhansi (సింగర్ ఝాన్సీ)",
        "Rohit Patnam (రోహిత్)",
        "Shalini Patel (శాలిని)",
        "Charan Mahadev (చరణ్)",
        "Chaithra Rai (చైత్ర)",
        "Krishna Alluri (కృష్ణుడు)",
        "Srishti Vyakaranam (సృష్టి)",
        "Mithilesh Reddy (మిథిలేష్)"
    ]
    return (
        f"CURRENT REALITY (Bigg Boss Telugu 10 - Day 75-76 / Week 11):\n"
        f"- Current Captain (Week 11): Potti Naresh (పొట్టి నరేష్). CRITICAL: Potti Naresh is the sole current Captain of the house. Temper Vamsi is NOT the captain. NEVER describe Temper Vamsi as captain!\n"
        f"- Active Housemates ONLY: {', '.join(active)}\n"
        f"- Host: Akkineni Nagarjuna (గౌరవంగా 'నాగ్‌గారు' అని సంబోధించాలి)\n"
        f"- Strictly Eliminated (DO NOT use as active housemates): {', '.join(eliminated)}\n"
        f"- Real Timeline & Ongoing Drama (Day 75-76 / Week 11 Weekdays, Nov 20-21, 2026):\n"
        f"  1. Ticket to Finale Arena Clash: Thrigun's team dominated the tasks with Aman Masud giving an explosive performance. Sanchalak Mukesh Gowda made biased, confusing decisions causing massive arguments in the house.\n"
        f"  2. Upcoming Weekend Episode Expectations: The weekend episode has NOT aired yet. Frame Host Nagarjuna's grilling as UPCOMING ANTICIPATION ('ఈ వీకెండ్‌లో నాగార్జునగారు ముకేష్‌కి ఎలాంటి క్లాస్ పీకబోతున్నారో చూడాలి!', 'నాగ్‌గారి చేతిలో ముకేష్‌కి వార్నింగ్ తప్పేలా లేదు'). NEVER claim in past tense that Nagarjuna already grilled Mukesh this week!\n"
        f"  3. House Satires: Swetha Naidu got store room sit-ups punishment, while Captain Potti Naresh issued hilarious warnings waving a toy dagger prop.\n"
        f"  4. Elimination Stakes: Varshini Sounderajan and Debjani Modak facing intense tension in the Week 11 nomination danger zone."
    )

"""
AutoTube AI - Season Guard & Person Verification Engine (utils/season_guard.py)

Guarantees 100% that:
1. When a seasonal show is active (e.g. Bigg Boss Telugu 10), images from past seasons
   (Season 1 through Season 9, BB1-BB9, Telugu-8, etc.) are strictly hard-blocked.
2. When a script scene mentions a specific person (e.g. Nagarjuna, Sudheer, Rohit, etc.),
   the visual pipeline searches specifically for that person, verifies their identity,
   and prevents generic show pools or images of different persons from being used.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Pre-defined known contestants / hosts mapped to aliases
KNOWN_TELUGU_SHOW_PERSONS: Dict[str, Dict[str, Any]] = {
    "nagarjuna": {
        "canonical": "Nagarjuna",
        "search_name": "Nagarjuna Akkineni",
        "aliases": ["nagarjuna", "king nagarjuna", "నాగార్జున", "akkineni nagarjuna", "nag sir", "host nagarjuna"],
    },
    "sudheer": {
        "canonical": "Sudheer Reddy",
        "search_name": "Sudheer Reddy Sudheer Talks Bigg Boss",
        "aliases": ["sudheer reddy", "సుధీర్ రెడ్డి", "sudheer", "సుధీర్", "sudheer talks", "సుధీర్ టాక్స్"],
        "disallow_terms": ["sudigali sudheer", "సుడిగాలి సుధీర్", "sudheer anand", "cartoon", "anime"],
    },
    "rohit": {
        "canonical": "Rohit Patnam",
        "search_name": "Rohit Patnam Bigg Boss Telugu 10",
        "aliases": ["rohit", "రోహిత్", "rohit patnam", "రోహిత్ పట్నం", "rohit naidu"],
        "status": "eliminated",
        "is_active": False,
        "disallow_terms": [
            "rohit sahni", "rohit sharma", "cricket", "bcci", "hitman", "ipl", "mumbai indians", "cartoon", "anime",
        ],
    },
    "jhansi": {
        "canonical": "Gundeboina Jhansi",
        "search_name": "Gundeboina Jhansi singer Bigg Boss Telugu 10",
        "aliases": ["jhansi", "ఝాన్సీ", "ఝాన్సి", "singer jhansi", "సింగర్ ఝాన్సీ", "gundeboina jhansi"],
        "status": "eliminated",
        "is_active": False,
        "disallow_terms": [
            "anchor jhansi", "యాంకర్ ఝాన్సీ", "fort", "rani laxmibai", "queen", "uttar pradesh", "tourism", "monument", "cartoon", "anime",
        ],
    },
    "charan": {
        "canonical": "Charan Mahadev",
        "search_name": "Charan Mahadev RJ Bigg Boss Telugu 10",
        "aliases": ["charan", "చరణ్", "charan mahadev", "చరణ్ మహాదేవ్", "rj charan"],
        "status": "eliminated",
        "is_active": False,
        "disallow_terms": [
            "ram charan", "ramcharan", "konidela", "rrr", "game changer", "gamechanger",
            "pushpa", "upasana", "mega power star", "megapowerstar", "chiranjeevi", "allu arjun", "sukumar",
            "sree vishnu", "sreevishnu",
            "cartoon", "anime",
        ],
    },
    "naresh": {
        "canonical": "Potti Naresh",
        "search_name": "Potti Naresh Jabardasth Bigg Boss Telugu 10",
        "aliases": ["naresh", "నరేష్", "potti naresh", "పొట్టి నరేష్", "jabardasth naresh", "జబర్దస్త్ నరేష్"],
        "disallow_terms": ["allari naresh", "vk naresh", "actor naresh", "cartoon", "anime"],
    },
    "thrigun": {
        "canonical": "Thrigun",
        "search_name": "Thrigun actor Bigg Boss Telugu 10",
        "aliases": ["thrigun", "trigun", "త్రిగుణ్", "త్రిగన్", "adith arun", "adith", "actor thrigun", "adith eswaran"],
        "disallow_terms": [
            "anime", "manga", "vash", "wallpaper", "cartoon", "drawing", "illustration",
            "cosplay", "stampede", "alphacoders", "getwallpapers", "zerochan", "fanart",
            "pixiv", "danbooru", "uhdpaper", "pxfuel", "wallpapercrafter", "besthdwallpaper",
            "wallpapers.com", "kannada",
        ],
    },
    "aman": {
        "canonical": "Aman Masud",
        "search_name": "Aman Masud actor Bigg Boss Telugu 10",
        "aliases": ["aman", "aman masud", "ఆమన్", "అమన్", "aman deep", "amandeep"],
        "disallow_terms": [
            "sehrawat", "wrestling", "wrestler", "olympic", "kushti", "cartoon", "anime",
            "hotel", "resort", "amanyara", "aman gupta",
        ],
    },
    "varshini": {
        "canonical": "Varshini",
        "search_name": "Varshini Sounderajan Bigg Boss Telugu",
        "aliases": ["varshini", "వర్షిణి", "varshini sounderajan", "anchor varshini", "varshini bigg boss"],
        "disallow_terms": ["cartoon", "anime"],
    },
    "mukesh": {
        "canonical": "Mukesh",
        "search_name": "Mukesh Gowda Bigg Boss Telugu 10",
        "aliases": ["mukesh", "ముకేష్", "mukesh gowda", "actor mukesh", "mukesh bigg boss"],
        "disallow_terms": ["cartoon", "anime", "mukesh ambani", "reliance"],
    },
    "shalini": {
        "canonical": "Shalini Patel",
        "search_name": "Shalini Patel Bigg Boss Telugu 10",
        "aliases": ["shalini patel", "shalini", "శాలిని పటేల్", "శాలిని", "షాలిని పటేల్", "షాలిని"],
        "status": "eliminated",
        "is_active": False,
        "disallow_terms": ["cartoon", "anime", "shalini ajith", "baby shalini"],
    },
    "chaitra": {
        "canonical": "Chaithra Rai",
        "search_name": "Chaithra Rai actress Bigg Boss Telugu 10",
        "aliases": ["chaitra", "చైత్ర", "chaitra rai", "చైత్ర రాయ్", "chaithra rai"],
        "status": "eliminated",
        "is_active": False,
        "disallow_terms": ["cartoon", "anime"],
    },
    "debjani": {
        "canonical": "Debjani Modak",
        "search_name": "Debjani Modak actress Bigg Boss Telugu 10",
        "aliases": ["debjani", "దేబ్జాని", "debjani modak", "దేబ్జాని మోదక్"],
        "disallow_terms": ["cartoon", "anime"],
    },
    "krishnudu": {
        "canonical": "Krishnudu",
        "search_name": "Krishnudu Telugu actor",
        "aliases": ["krishnudu", "కృష్ణుడు", "actor krishnudu"],
        "status": "eliminated",
        "is_active": False,
        "disallow_terms": ["cartoon", "anime", "lord krishna", "iskcon"],
    },
    "daakshi": {
        "canonical": "Daakshi",
        "search_name": "Daakshi Guthikonda",
        "aliases": ["daakshi", "దాక్షి", "daakshi guthikonda"],
        "disallow_terms": ["cartoon", "anime"],
    },
    "ramprasad": {
        "canonical": "Auto Ram Prasad",
        "search_name": "Auto Ram Prasad Jabardasth",
        "aliases": ["ram prasad", "రామ్ ప్రసాద్", "auto ram prasad", "ఆటో రాంప్రసాద్"],
        "disallow_terms": ["cartoon", "anime"],
    },
    "temper_vamsi": {
        "canonical": "Temper Vamsi",
        "search_name": "Temper Vamsi actor",
        "aliases": ["temper vamsi", "టెంపర్ వంశీ", "vamsi"],
        "disallow_terms": ["cartoon", "anime"],
    },
    "rajinikanth": {
        "canonical": "Rajinikanth",
        "search_name": "Rajinikanth Kabali",
        "aliases": ["rajinikanth", "రజినీకాంత్", "రజనీకాంత్", "kabali", "కబాలి", "rajini sir", "superstar rajinikanth"],
        "disallow_terms": ["cartoon", "anime", "wallpaper"],
    },
    "vijay_deverakonda": {
        "canonical": "Vijay Deverakonda",
        "search_name": "Vijay Deverakonda actor",
        "aliases": ["vijay deverakonda", "vijay devarakonda", "విజయ్ దేవరకొండ", "దేవరకొండ", "deverakonda", "devarakonda"],
        "disallow_terms": ["junior ntr", "jr ntr", "devara: part 1", "devara movie", "devara 1", "koratala siva"],
    },
    "rashmika": {
        "canonical": "Rashmika Mandanna",
        "search_name": "Rashmika Mandanna actress",
        "aliases": ["rashmika mandanna", "rashmika", "రష్మిక మందన్న", "రష్మిక"],
        "disallow_terms": ["cartoon", "anime"],
    },
    "dil_raju": {
        "canonical": "Dil Raju",
        "search_name": "Dil Raju producer Tollywood",
        "aliases": ["dil raju", "dill raju", "దిల్ రాజు", "దిల్రాజు", "producer dil raju"],
        "disallow_terms": ["cartoon", "anime", "wallpaper"],
    },
    "apoorva": {
        "canonical": "Apoorva",
        "search_name": "Apoorva Bigg Boss Telugu",
        "aliases": ["apoorva", "అపూర్వ", "apoorva mukundan"],
        "disallow_terms": ["cartoon", "anime"],
    },
    "shiv": {
        "canonical": "Shiv",
        "search_name": "Shiv Bigg Boss Telugu 10",
        "aliases": ["shiv", "shiva", "శివ్", "శివ", "anchor shiva"],
        "disallow_terms": ["lord shiva", "temple", "pooja", "cartoon", "anime", "shiva rajkumar"],
    },
}

# Common celebrity collisions for reality show contestants and cinema entities (Bug 2 Fix)
COMMON_CELEBRITY_COLLISION_NEGATIVES: Dict[str, List[str]] = {
    "sudheer": ["-sudigali", "-anand"],
    "rohit": ["-cricket", "-sharma", "-hitman", "-bcci", "-ipl", "-team india", "-sahni"],
    "charan": ["-ram", "-konidela", "-rrr", "-chiranjeevi", "-upasana", "-game changer", "-gamechanger", "-rc16", "-sree", "-vishnu"],
    "arjun": ["-allu", "-stylish", "-pushpa", "-kapoor", "-arjun reddy"],
    "aman": ["-sehrawat", "-wrestler", "-wrestling", "-olympic", "-kushti", "-gupta"],
    "jhansi": ["-anchor", "-fort", "-laxmibai", "-rani", "-monument", "-queen", "-tourism", "-uttar", "-pradesh"],
    "mukesh": ["-ambani", "-reliance"],
    "thrigun": ["-anime", "-manga", "-vash", "-stampede", "-trigun", "-cartoon", "-drawing"],
    "devara": ["-deverakonda", "-devarakonda", "-vijay"],
    "deverakonda": ["-devara", "-koratala"],
    "vijay": ["-devara", "-sethupathi"],
}


def get_celebrity_collision_negative_keywords(person_or_entity: str) -> List[str]:
    """
    Returns a list of negative search keywords (e.g. ['-cricket', '-sharma']) for
    common celebrity collisions to prevent reality show contestants from matching
    famous actors, cricketers, or historical figures.
    """
    if not person_or_entity:
        return []
    raw = str(person_or_entity).lower().strip()
    res: List[str] = [
        "-anime", "-manga", "-cartoon", "-drawing", "-illustration", "-sketch", "-vector"
    ]

    for key, negs in COMMON_CELEBRITY_COLLISION_NEGATIVES.items():
        if key in raw or raw in key:
            for n in negs:
                if n not in res:
                    res.append(n)

    for p_key, p_info in KNOWN_TELUGU_SHOW_PERSONS.items():
        if (
            p_key in raw
            or p_info.get("canonical", "").lower() in raw
            or any(a.lower() in raw for a in p_info.get("aliases", []))
        ):
            for dt in p_info.get("disallow_terms", []):
                dt_clean = dt.strip().lower()
                neg_tag = f"-{dt_clean}" if not dt_clean.startswith("-") else dt_clean
                if neg_tag not in res and len(dt_clean) > 2:
                    res.append(neg_tag)

    return res


def get_celebrity_collision_negative_string(person_or_entity: str) -> str:
    """Returns space-separated negative keywords string for celebrity collisions."""
    neg_list = get_celebrity_collision_negative_keywords(person_or_entity)
    return " ".join(neg_list)


def get_current_season_number(show_context: str = "") -> Optional[int]:
    """
    Extracts integer season number from show context string.
    e.g. 'Bigg Boss Telugu 10' -> 10, 'Bigboss 10' -> 10, 'BB8' -> 8.
    """
    if not show_context:
        try:
            from config.settings import get_setting
            show_context = get_setting("SHOW_CONTEXT", "")
        except Exception:
            show_context = ""

    raw = str(show_context or "").strip()
    if not raw or raw.lower() == "auto":
        return 10  # Default to current season 10

    # Match patterns like 'Season 10', 'BB10', 'Bigg Boss 10', 'Telugu 10'
    m = re.search(r"\b(?:season|bb|bigg\s*boss(?:\s*telugu)?|telugu)\s*[-_:]*\s*(\d{1,2})\b", raw, flags=re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass

    # Direct number at end or boundary
    m2 = re.search(r"\b(\d{1,2})\b", raw)
    if m2:
        try:
            return int(m2.group(1))
        except ValueError:
            pass

    return 10


# Disqualification blacklist for past Telugu & Hindi contestants when Season 10 is active
PAST_SEASON_CONTESTANTS: Set[str] = {
    # Season 9 (2025)
    "shivaji", "sivaji", "prashanth", "pallavi prashanth", "teja", "tasty teja",
    # Season 8 (2024)
    "nikhil maliyakkal", "yashmi gowda", "yashmi", "prerana", "nabeel afridi", "nabeel",
    "vishnu priya", "manikanta", "kirrak seetha", "seetha", "aditya om", "nainika",
    # Season 7 (2023)
    "amar deep", "shobha shetty", "rathika rose", "rathika", "prince yawar", "bhole shavali", "ashwini sree",
    # Season 6 (2022)
    "revanth", "baladithya", "inaya sulthana", "inaya", "srihan", "faima", "geetu royal", "geetu",
    # Season 1-5 (2017-2021)
    "kaushal manda", "kaushal", "abhijeet", "bindu madhavi", "rahul sipligunj", "shiva jyothi",
    "shanmukh jaswanth", "shanmukh", "vj sunny", "siri hanmanth", "ariana glory", "syed sohel",
    "akhil sarthak", "himaja", "baba bhaskar", "deepthi sunaina", "tanish",
    # Hindi Bigg Boss 10 (2016)
    "manveer gurjar", "manveer", "elena kazan", "priyanka jagga", "swami om", "bani j",
    "rohan mehra", "nitibha kaul", "manu punjabi", "monalisa", "lopamudra raut", "lopamudra",
}

PAST_YEARS_PATTERNS = [
    r"[-_/](201[0-9]|202[0-5])[-_/.]",
    r"\b(201[0-9]|202[0-5])\b",
]


def format_strict_visual_query(
    contestant_name: str,
    season_name: str = "Bigg Boss Telugu 10",
    year: int = 2026,
    task_or_promo: str = "",
) -> str:
    """
    Format visual search queries with strict keywords and contestant names:
    Query format: "[Contestant Name] [Season Name] [Year]" OR "[Contestant Name] [Specific Task/Promo]".
    Enforces exact quote operators to eliminate generic older-season search bleed.
    """
    c_clean = str(contestant_name or "").strip()
    s_clean = str(season_name or "").strip()
    y_str = str(year or 2026).strip()

    if not s_clean:
        s_clean = "Bigg Boss Telugu 10"

    if task_or_promo and task_or_promo.strip():
        t_clean = task_or_promo.strip()
        return f'"{c_clean}" "{s_clean}" "{t_clean}"'
    return f'"{c_clean}" "{s_clean}" {y_str}'


def is_generic_visual_query(query: str) -> bool:
    """
    Detects forbidden generic search queries like 'Bigg Boss Telugu drama',
    'Bigg Boss emotional scene', or 'Bigg Boss Telugu stage'.
    """
    if not query:
        return True
    q = query.lower().strip()
    generic_patterns = [
        r"^(?:bigg\s*boss(?:\s*telugu)?|reality\s*show)\s*(?:drama|emotional\s*scene|stage|scene|house|fight|reactions?|housemates?)$",
        r"^(?:telugu\s*)?reality\s*show\s*(?:drama|scene|stage|housemates?)$",
        r"^(?:dramatic|emotional|happy|sad)\s*(?:scene|moment|reaction)$",
        r"^bigg\s*boss\s*housemates?$",
    ]
    for pat in generic_patterns:
        if re.search(pat, q):
            return True
    return False


def extract_year_from_metadata(text_or_url: str) -> Optional[int]:
    """Extracts 4-digit year from image URL path or caption."""
    if not text_or_url:
        return None
    raw = str(text_or_url)
    # Check URL date path e.g. /2026/06/ or /2025/07/ or /2024/11/ or 20250905
    m_url = re.search(r"[-_/](202[0-9])(?:[-_/]|(?=\d{4}))", raw)
    if m_url:
        try:
            return int(m_url.group(1))
        except ValueError:
            pass
    # Check general 4-digit year 2016-2029
    m_yr = re.search(r"\b(202[0-9]|201[6-9])\b", raw)
    if m_yr:
        try:
            return int(m_yr.group(1))
        except ValueError:
            pass
    return None


UNWANTED_CARTOON_ANIME_KEYWORDS: Set[str] = {
    "anime", "manga", "cartoon", "illustration", "fanart", "drawing", "drawings",
    "cosplay", "deviantart", "artstation", "wallpapercave", "alphacoders",
    "getwallpapers", "zerochan", "danbooru", "pixiv", "chibi", "comic", "animated",
    "wallpapercrafter", "besthdwallpaper", "wallpapers.com", "uhdpaper", "pxfuel",
}

GLOBAL_OFFTOPIC_KEYWORDS: Set[str] = {
    "eurovision", "sofia pride", "bulgaria", "dara", "bts", "kpop", "k-pop",
    "mexico", "mexican", "albania", "serbia", "romania", "gta", "gta 6", "rockstar games",
    "national flag", "flag of", "map of", "geography", "wallpaper", "wallpapers", "zerochan",
    "alphacoders", "wallpapercave", "wallpapercrafter", "pxfuel", "uhdpaper", "besthdwallpaper",
    "wallpapersko", "esctoday", "ejecentral", "eloutput", "concert poster", "korean concert",
}

TELUGU_SHOW_RELEVANCE_TOKENS: Set[str] = {
    "bigg boss", "biggboss", "బిగ్ బాస్", "బిగ్‌బాస్", "bb10", "bb9", "bb8", "bb7", "bb6", "bb5",
    "telugu", "tollywood", "star maa", "hotstar", "nagarjuna", "charan", "kabali", "rajini",
    "rajinikanth", "housemate", "contestant", "eviction", "elimination", "wildcard", "nomination",
    "sudheer", "rohit", "bebakka", "shekhar", "kalyan", "thrigun", "aman", "apoorva", "jhansi",
    "varshini", "mukesh", "shalini", "chaitra", "debjani", "krishnudu", "daakshi", "ramprasad",
    "brahmanandam", "jabardasth", "etv telugu", "tv9", "gulte", "10tv", "sakshi", "greatandhra"
}


def is_bigg_boss_topic(text: str) -> bool:
    """Check if a topic, text, or title refers to Bigg Boss."""
    if not text:
        return False
    t = str(text).lower()
    t_norm = re.sub(r"[-_]+", " ", t)
    if any(k in t_norm for k in (
        "bigg boss", "biggboss", "big boss", "bigboss", "బిగ్ బాస్", "బిగ్‌బాస్",
        "bb10", "bb9", "bb8", "bb7", "bb6", "bb5",
        "bbt10", "bbtelugu"
    )):
        return True
    if bool(re.search(r"\b(?:bb|bbt)\s*\d{1,2}\b", t_norm)):
        return True
    try:
        from data.bb10_contestants import is_bigg_boss_context
        if is_bigg_boss_context(text):
            return True
    except Exception:
        pass
    return False


def is_entertainment_or_roast_topic(text: str) -> bool:
    """
    Checks if a topic, category, or query is about entertainment, cinema, movies,
    celebrity culture, roasts, or reality shows (e.g. Bigg Boss).
    """
    if not text:
        return False
    t = str(text).lower()
    t_norm = re.sub(r"[-_]+", " ", t)
    if is_bigg_boss_topic(t_norm):
        return True
    keywords = (
        "entertainment", "cinema", "movie", "film", "roast", "trailer", "teaser",
        "review", "box office", "tollywood", "kollywood", "bollywood", "celebrity",
        "actor", "actress", "hero", "heroine", "సినిమా", "రోస్ట్", "రివ్యూ", "నటుడు",
        "నటి", "విజయ్ దేవరకొండ", "రష్మిక", "vijay deverakonda", "vijay devarakonda", "rashmika",
        "reality", "reality show", "tv show", "show", "nomination", "contestant",
        "housemate", "housemates", "elimination", "promo", "episode", "season", "anchor",
        "హౌస్‌", "కంటెస్టెంట్", "నామినేషన్", "ఎలిమినేషన్", "bigg boss", "biggboss",
    )
    if any(k in t_norm for k in keywords):
        return True
    for p_key, p_info in KNOWN_TELUGU_SHOW_PERSONS.items():
        if p_key in t_norm or p_info.get("canonical", "").lower() in t_norm:
            return True
    return False


def resolve_effective_show_context(
    topic_or_title: str = "",
    script_text: str = "",
    raw_show_context: Optional[str] = None,
) -> str:
    """
    Resolves the effective show context, strictly preventing context contamination.
    If raw_show_context refers to a seasonal reality show (like Bigg Boss Telugu),
    but neither topic_or_title nor script_text is about Bigg Boss,
    the stale show context is ignored to prevent search query and prompt pollution.
    """
    ctx = raw_show_context
    if ctx is None:
        try:
            from config.settings import get_setting
            ctx = get_setting("SHOW_CONTEXT", "")
        except Exception:
            ctx = ""

    ctx_str = str(ctx).strip() if ctx else ""
    if not ctx_str or ctx_str.lower() in ("auto", "none", "null"):
        return ""

    # If configured context is Bigg Boss, verify current topic/script actually relates to Bigg Boss
    if is_bigg_boss_topic(ctx_str):
        if not (is_bigg_boss_topic(topic_or_title) or is_bigg_boss_topic(script_text)):
            return ""

    return ctx_str


def is_unwanted_visual_candidate(
    text_or_url: str,
    disallow_terms: Optional[List[str]] = None,
    is_bb_context: bool = False,
) -> bool:
    """
    Checks if a candidate is unwanted:
    - In reality/celebrity context (like Bigg Boss), strictly rejects cartoon/anime/wallpaper sources.
    - Strictly rejects person-specific disallow terms (e.g. anime/vash for Thrigun, wrestler for Aman).
    """
    if not text_or_url:
        return False
    raw = str(text_or_url).lower().strip()
    # Strip negative search query flags (e.g. ' -anime', ' -2024') to avoid false positive triggers
    clean_text = re.sub(r"(?:^|\s)-[a-zA-Z0-9_]+", " ", raw)

    # Reject person-specific disallow terms
    if disallow_terms:
        for dt in disallow_terms:
            if dt and dt.lower() in clean_text:
                return True

    # In Bigg Boss / reality show context, reject any anime, cartoon, illustration, drawing, wallpaper sites
    if is_bb_context or is_bigg_boss_topic(clean_text):
        for kw in UNWANTED_CARTOON_ANIME_KEYWORDS:
            if kw in clean_text:
                return True

    return False


def is_conflicting_season_candidate(
    text_or_url: str,
    current_season: Optional[int] = None,
    is_bb_context: bool = False,
    disallow_terms: Optional[List[str]] = None,
    target_person: Optional[str] = None,
    target_season: Optional[int] = None,
) -> bool:
    """
    Determines if candidate metadata (URL, caption, title) mentions a past or different season
    than the currently active season for a seasonal show (like Bigg Boss Telugu),
    contains unwanted anime/cartoon/wrong-profession entities, or is from another regional language.
    Strictly prevents past seasons (Season 1-9, BB1-9, S1-9) from leaking in even if the person/host matches.
    """
    if not text_or_url:
        return False

    raw = str(text_or_url).lower().strip()

    # Automatically derive disallow_terms and collision keywords from target_person
    effective_disallows = list(disallow_terms or [])
    if target_person:
        p_negs = get_celebrity_collision_negative_keywords(target_person)
        for pn in p_negs:
            clean_pn = pn.lstrip("-").strip().lower()
            if clean_pn and clean_pn not in effective_disallows:
                effective_disallows.append(clean_pn)
        try:
            p_dt = get_person_disallowed_terms(target_person)
            for dt in p_dt:
                dt_clean = dt.strip().lower()
                if dt_clean and dt_clean not in effective_disallows:
                    effective_disallows.append(dt_clean)
        except Exception:
            pass

    # Reject unwanted cartoon/anime or person-disallowed candidates immediately
    if is_unwanted_visual_candidate(raw, disallow_terms=effective_disallows, is_bb_context=is_bb_context):
        return True

    # Hard rejection for global off-topic keywords (Eurovision, BTS, GTA, flags, wallpapers)
    if any(ot in raw for ot in GLOBAL_OFFTOPIC_KEYWORDS):
        return True

    cur_s = (
        target_season
        if target_season is not None
        else (current_season if current_season is not None else get_current_season_number())
    )
    if cur_s is None:
        cur_s = 10

    # Scope check: Is this candidate or context related to Bigg Boss or past seasons?
    is_bb = is_bb_context or is_bigg_boss_topic(raw)
    has_season_indicator = bool(
        re.search(
            r"(?:season|bb|s)[-_:\s]*([1-9])(?!\d)|[-_/](?:season|bb|s)[-_]?([1-9])[-_/.]",
            raw,
            flags=re.IGNORECASE,
        )
    )
    has_past_contestant = any(past_name in raw for past_name in PAST_SEASON_CONTESTANTS)

    if is_bb:
        # Strictly reject other regional Bigg Boss languages when in Telugu show context
        OTHER_REGIONAL_SHOW_LANGUAGES = {
            "kannada", "tamil", "malayalam", "hindi", "marathi", "bengali",
            "colors kannada", "vijay tv", "asianet", "colors tamil", "bbk", "bbk11", "bbk10", "tv9kannada",
        }
        if any(reg in raw for reg in OTHER_REGIONAL_SHOW_LANGUAGES):
            return True
    elif not has_season_indicator and not has_past_contestant:
        return False

    # 1. Strict rejection of past season markers in Telugu Bigg Boss context (or when season 10 is targeted)
    if cur_s == 10:
        past_season_tokens = {
            "bb8", "bb9", "bb7", "bb6", "bb5", "bb4", "bb3", "bb2", "bb1",
            "bbt8", "bbt9", "bbt7", "bbt6", "bbt5",
            "season 8", "season 9", "season 7", "season 6", "season 5", "season 4",
            "season8", "season9", "season7", "season6", "season5",
            "season-8", "season-9", "season-7", "season-6",
            "bb-8", "bb-9", "bb-7", "bb-6",
            "s-8", "s-9", "s-7", "s-6",
            "9 bigg boss", "8 bigg boss", "7 bigg boss",
            "bigg boss 9", "bigg boss 8", "bigg boss 7", "bigg boss 6",
            "bigg boss telugu 9", "bigg boss telugu 8", "bigg boss telugu 7",
            "బిగ్ బాస్ 8", "బిగ్ బాస్ 9", "బిగ్ బాస్ 7", "బిగ్ బాస్ 6",
            "బిగ్‌బాస్ 8", "బిగ్‌బాస్ 9", "బిగ్‌బాస్ 7", "బిగ్‌బాస్ 6",
            "సీజన్ 8", "సీజన్ 9", "సీజన్ 7", "సీజన్ 6",
        }
        for pst in past_season_tokens:
            if re.search(r"(?:^|[^a-zA-Z0-9])" + re.escape(pst) + r"(?![a-zA-Z0-9])", raw):
                return True

        # Strictly disqualify known past-season contestants
        for past_name in PAST_SEASON_CONTESTANTS:
            if past_name in raw and (not target_person or past_name not in target_person.lower()):
                return True

        # Strengthened regex to reject any candidate containing Season [1-9], BB[1-9], or S[1-9]
        # Uses word/boundary checks so S3 does not match s3fs (Amazon S3 storage)
        strict_past_season_patterns = [
            r"\bseason\s*[-_:]*\s*([1-9])(?!\d)",
            r"\bbb\s*[-_:]*\s*([1-9])(?!\d)",
            r"(?:\b|_)s[-_]?([1-9])(?:\b|_)",
            r"[-_/](?:season|bb)[-_]?([1-9])[-_/.]",
            r"[-_/]s([1-9])[-_/.]",
            r"[-_/](\d{1,2})[-_]?(?:season|bb|s|bigg[-_]?boss)[-_/.]",
            r"\b(\d{1,2})\s*[-_:]*\s*(?:bigg[\s_-]*boss|bb|season)\b",
            r"\bbigg[\s_-]*boss[\s_-]*(?:telugu[\s_-]*)?([1-9])(?!\d)",
            r"\btelugu[\s_-]+([1-9])(?!\d)",
            r"బిగ్[\s_-]*బాస్[\s_-]*([1-9])(?!\d)",
            r"సీజన్[\s_-]*([1-9])(?!\d)",
        ]
        for pat in strict_past_season_patterns:
            m = re.search(pat, raw, flags=re.IGNORECASE)
            if m:
                try:
                    s_val = int(m.group(1))
                    if s_val < 10:
                        return True
                except (ValueError, IndexError):
                    return True

    # 2. General Season number regex patterns
    patterns = [
        r"\bseason\s*[-_:]*\s*(\d{1,2})\b",
        r"\bbb\s*[-_:]*\s*(\d{1,2})\b",
        r"\bbb(\d{1,2})(?:[^\d]|$)",
        r"\bbigg[\s_-]*boss[\s_-]*(?:telugu[\s_-]*)?(\d{1,2})\b",
        r"\b(\d{1,2})\s*[-_:]*\s*bigg[\s_-]*boss\b",
        r"\b(\d{1,2})\s*[-_:]*\s*bb\b",
        r"\btelugu[\s_-]+(\d{1,2})\b",
        r"[-_/]season[-_]?(\d{1,2})[-_/.]",
        r"[-_/]bb[-_]?(\d{1,2})[-_/.]",
        r"[-_/](\d{1,2})[-_]?bigg[-_]?boss[-_/.]",
        r"[-_/]telugu[-_]?(\d{1,2})[-_/.]",
        r"బిగ్[\s_-]*బాస్[\s_-]*(\d{1,2})",
        r"సీజన్[\s_-]*(\d{1,2})",
    ]

    for pat in patterns:
        for match in re.finditer(pat, raw, flags=re.IGNORECASE):
            try:
                s_num = int(match.group(1))
                if s_num != cur_s:
                    return True
            except ValueError:
                continue

    # Check if this candidate is an authentic portrait/photo of the target person
    is_person_match = False
    if target_person:
        tp_lower = target_person.lower()
        search_toks = [tp_lower]
        for p_info in KNOWN_TELUGU_SHOW_PERSONS.values():
            if p_info["canonical"].lower() == tp_lower:
                search_toks.extend([a.lower() for a in p_info["aliases"]])
                break
        is_person_match = any(tok in raw for tok in search_toks if len(tok) >= 3)

    # In reality show / Bigg Boss context, candidate must have domain relevance unless verified person match
    if is_bb and not is_person_match:
        if not any(tok in raw for tok in TELUGU_SHOW_RELEVANCE_TOKENS):
            return True

    # 3. Strict Year / Date Filtering for Season 10 (2026 only, rejecting <= 2025)
    # If in Bigg Boss context:
    # - Generic show stills/promos without a verified contestant strictly reject <= 2025.
    # - Host Nagarjuna photos strictly reject <= 2025 (to prevent Season 9/8 stages & old logos).
    # - Non-host contestant portraits (e.g. Apoorva, Thrigun) can use recent headshots (2024-2025)
    #   as long as they do not mention past seasons (Season 9/8/BB9 etc., checked in step 1).
    if cur_s == 10:
        raw_for_dates = re.sub(r"(?:^|\s)-[a-zA-Z0-9_]+", " ", raw)
        cand_year = extract_year_from_metadata(raw_for_dates)
        is_host = bool(target_person and any(h in target_person.lower() for h in ("nagarjuna", "నాగార్జున", "king nag", "host")))
        block_past_dates = (not is_person_match) or is_host

        if cand_year is not None and cand_year <= 2025:
            if block_past_dates:
                return True

        # Check explicit past year markers in URL path or filename
        for y_pat in PAST_YEARS_PATTERNS:
            if re.search(y_pat, raw_for_dates):
                y_match = re.search(y_pat, raw_for_dates)
                if y_match:
                    try:
                        yr_val = int(y_match.group(1))
                        if yr_val <= 2025 and block_past_dates:
                            return True
                    except ValueError:
                        pass

    return False


def extract_person_from_scene(scene_text: str) -> Optional[str]:
    """
    Scans a scene script sentence (Telugu or English) and identifies if a specific
    known person, host, or contestant is mentioned.
    Returns the canonical English name of the person, or None.
    """
    if not scene_text:
        return None

    raw_lower = scene_text.lower()

    # 1. Fast match against known Telugu show personalities (earliest occurrence)
    earliest_pos = None
    earliest_person = None
    for p_id, p_info in KNOWN_TELUGU_SHOW_PERSONS.items():
        for alias in p_info["aliases"]:
            pos = raw_lower.find(alias)
            if pos != -1:
                if earliest_pos is None or pos < earliest_pos:
                    earliest_pos = pos
                    earliest_person = p_info["canonical"]

    if earliest_person:
        return earliest_person

    # 2. Match against entity library
    try:
        from tools.build_entity_library import match_entities_in_text
        matches = match_entities_in_text(scene_text)
        for ent in matches:
            cat = ent.get("category", "").lower()
            ent_id = ent.get("id", "").lower()
            if ent_id != "bigg_boss_telugu" and cat in ("entertainment", "person", "actor"):
                return ent.get("canonical_name", "")
    except Exception:
        pass

    # 3. Match English proper names in Telugu script
    eng_words = re.findall(r"\b[A-Z][a-z]{2,}\b", scene_text)
    skip_common = {
        "Bigg", "Boss", "Season", "House", "Episode", "Twitter", "Youtube", "Instagram",
        "News", "Viral", "King", "Host", "Task", "Today", "Star", "Show", "Media", "Telugu"
    }
    for ew in eng_words:
        if ew in skip_common:
            continue
        for p_id, p_info in KNOWN_TELUGU_SHOW_PERSONS.items():
            if ew.lower() in [a.lower() for a in p_info["aliases"]] or ew.lower() == p_info["canonical"].lower():
                return p_info["canonical"]

    return None


def extract_all_persons_from_scene(scene_text: str) -> List[str]:
    """
    Returns ALL persons/contestants mentioned in a scene script sentence.
    """
    if not scene_text:
        return []
    raw_lower = scene_text.lower()
    found = []
    for p_id, p_info in KNOWN_TELUGU_SHOW_PERSONS.items():
        if any(alias in raw_lower for alias in p_info["aliases"]):
            if p_info["canonical"] not in found:
                found.append(p_info["canonical"])
    return found


def verify_candidate_person(
    candidate_text: str,
    target_person: str,
    aliases: Optional[List[str]] = None,
) -> Tuple[bool, bool]:
    """
    Verifies if a candidate's text (caption + URL + title) matches the target person.
    Returns:
        (is_match, is_conflict)
        - is_match: True if target person's name or aliases appear in candidate text
        - is_conflict: True if another known competing person is explicitly mentioned instead
    """
    if not target_person:
        return (True, False)

    cand_lower = str(candidate_text or "").lower()
    target_lower = target_person.lower()

    search_tokens = [target_lower]
    if aliases:
        search_tokens.extend([a.lower() for a in aliases if len(a) >= 3])

    for p_info in KNOWN_TELUGU_SHOW_PERSONS.values():
        if p_info["canonical"].lower() == target_lower:
            search_tokens.extend(p_info["aliases"])
            break

    def _matches_person_token(text: str, token: str) -> bool:
        if not token:
            return False
        clean_tok = token.strip()
        if re.match(r'^[a-zA-Z0-9_\s]+$', clean_tok):
            pattern = r'(?:\b|^)' + re.escape(clean_tok) + r'(?:\b|$)'
            return bool(re.search(pattern, text))
        return clean_tok in text

    is_match = any(_matches_person_token(cand_lower, tok) for tok in search_tokens)

    is_conflict = False
    for p_info in KNOWN_TELUGU_SHOW_PERSONS.values():
        if p_info["canonical"].lower() != target_lower:
            other_aliases = [p_info["canonical"].lower()] + [a for a in p_info["aliases"] if len(a) >= 4]
            filtered_other = [oa for oa in other_aliases if oa not in search_tokens]
            if any(_matches_person_token(cand_lower, oa) for oa in filtered_other):
                is_conflict = True
                break

    return (is_match, is_conflict)


def get_person_search_name(person_name: str, cur_season: Optional[int] = 10) -> str:
    """
    Returns the most effective, disambiguated search name for a person in show context.
    MANDATORY RULE: Never return bare single names (e.g. 'Charan', 'Rohit').
    Strict format: '{Contestant_Name} Bigg Boss Telugu' or '{Contestant_Name} Bigg Boss'.
    """
    if not person_name:
        return f"Bigg Boss Telugu {cur_season}" if cur_season else "Bigg Boss Telugu"
    target_lower = person_name.lower().strip()
    for p_info in KNOWN_TELUGU_SHOW_PERSONS.values():
        if p_info["canonical"].lower() == target_lower or target_lower in [a.lower() for a in p_info["aliases"]]:
            s_name = p_info.get("search_name", p_info["canonical"])
            if "bigg boss" not in s_name.lower():
                s_name = f"{s_name} Bigg Boss Telugu"
            return s_name

    clean_p = person_name.strip()
    if "bigg boss" not in clean_p.lower():
        return f"{clean_p} Bigg Boss Telugu"
    return clean_p


def get_person_disallowed_terms(person_name: str) -> List[str]:
    """Returns disallow terms for a specific person to filter out wrong entities."""
    if not person_name:
        return []
    target_lower = person_name.lower().strip()
    for p_info in KNOWN_TELUGU_SHOW_PERSONS.values():
        if p_info["canonical"].lower() == target_lower or target_lower in [a.lower() for a in p_info["aliases"]]:
            return list(p_info.get("disallow_terms", []))
    return []


def get_allowed_tier_b_threshold(content_type: str = "", topic: str = "") -> float:
    """
    Returns allowable Tier B share based on content category:
    - Roasting / Sarcastic / Funny / News / Entertainment / Cinema / Reality: 0.80 (80% under Editorial Fair Dealing)
    - Others (Tech / Explainer / Educational): 0.50 (50%)
    """
    ct = str(content_type or "").lower()
    top = str(topic or "").lower()
    entertainment_markers = (
        "roast", "sarcastic", "funny", "news", "entertainment", "cinema", "movie",
        "bigg boss", "reality", "tollywood", "celebrity", "drama"
    )
    if any(m in ct for m in entertainment_markers) or any(m in top for m in entertainment_markers):
        return 0.80
    return 0.50


def is_contestant_eliminated(person_name: str) -> bool:
    """Returns True if the specified contestant has been eliminated from the show."""
    if not person_name:
        return False
    target_lower = person_name.lower().strip()
    for p_info in KNOWN_TELUGU_SHOW_PERSONS.values():
        if p_info.get("status") == "eliminated" or not p_info.get("is_active", True):
            if p_info["canonical"].lower() == target_lower or target_lower in [a.lower() for a in p_info["aliases"]]:
                return True
            if p_info["canonical"].lower() in target_lower:
                return True
            for a in p_info["aliases"]:
                if len(a) >= 4 and a.lower() in target_lower:
                    return True
    return False


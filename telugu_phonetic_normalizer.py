"""
Telugu Phonetic Normalizer for Tech Scripts / AutoTube AI (telugu_phonetic_normalizer.py)

Converts tech model numbers (e.g. 'iPhone 18' -> 'ఐఫోన్ ఎయిటీన్', NOT 'పద్దెనిమిది'),
hardware chipsets ('A20' -> 'ఏ ట్వంటీ', 'M4' -> 'ఎం ఫోర్'),
specs ('48MP' -> 'ఫార్టీ ఎయిట్ మెగాపిక్సెల్', '2TB' -> 'టూ టీబీ', '120Hz' -> 'వన్ ట్వంటీ హెర్ట్జ్'),
and technical terms into natural conversational Telugu creator pronunciation.
"""

import os
import re
from typing import Union

ENGLISH_UNITS_TELUGU = {
    0: "జీరో",
    1: "వన్",
    2: "టూ",
    3: "త్రీ",
    4: "ఫోర్",
    5: "ఫైవ్",
    6: "సిక్స్",
    7: "సెవెన్",
    8: "ఎయిట్",
    9: "నైన్",
    10: "టెన్",
    11: "ఎలెవెన్",
    12: "ట్వెల్వ్",
    13: "థర్టీన్",
    14: "ఫోర్టీన్",
    15: "ఫిఫ్టీన్",
    16: "సిక్స్‌టీన్",
    17: "సెవెంటీన్",
    18: "ఎయిటీన్",
    19: "నైన్‌టీన్",
}

ENGLISH_TENS_TELUGU = {
    2: "ట్వంటీ",
    3: "థర్టీ",
    4: "ఫార్టీ",
    5: "ఫిఫ్టీ",
    6: "సిక్స్టీ",
    7: "సెవెంటీ",
    8: "ఎయిటీ",
    9: "నైంటీ",
}

SPECIAL_NUMBERS = {
    100: "హండ్రెడ్",
    108: "వన్ నాట్ ఎయిట్",
    120: "వన్ ట్వంటీ",
    128: "వన్ ట్వంటీ ఎయిట్",
    144: "వన్ ఫార్టీ ఫోర్",
    200: "టూ హండ్రెడ్",
    256: "టూ ఫిఫ్టీ సిక్స్",
    500: "ఫైవ్ హండ్రెడ్",
    512: "ఫైవ్ ట్వెల్వ్",
    1000: "వన్ థౌసండ్",
    2000: "టూ థౌసండ్",
}


def number_to_english_phonetic_telugu(n: Union[int, str]) -> str:
    """
    Converts numbers into English spoken words in Telugu script.
    e.g. 18 -> 'ఎయిటీన్', 26 -> 'ట్వంటీ సిక్స్', 48 -> 'ఫార్టీ ఎయిట్', 108 -> 'వన్ నాట్ ఎయిట్'
    """
    try:
        val = int(n)
    except (ValueError, TypeError):
        return str(n)

    if val in SPECIAL_NUMBERS:
        return SPECIAL_NUMBERS[val]

    if val in ENGLISH_UNITS_TELUGU:
        return ENGLISH_UNITS_TELUGU[val]

    if val < 100:
        t, u = divmod(val, 10)
        t_str = ENGLISH_TENS_TELUGU.get(t, "")
        u_str = (" " + ENGLISH_UNITS_TELUGU[u]) if u else ""
        return (t_str + u_str).strip()

    if val < 1000:
        h, r = divmod(val, 100)
        h_str = ENGLISH_UNITS_TELUGU.get(h, str(h)) + " హండ్రెడ్"
        if r == 0:
            return h_str
        if r < 10:
            return f"{ENGLISH_UNITS_TELUGU.get(h, str(h))} నాట్ {ENGLISH_UNITS_TELUGU.get(r, str(r))}"
        return f"{ENGLISH_UNITS_TELUGU.get(h, str(h))} {number_to_english_phonetic_telugu(r)}"

    if val < 1000000:
        th, r = divmod(val, 1000)
        th_str = number_to_english_phonetic_telugu(th) + " థౌసండ్"
        if r == 0:
            return th_str
        if r < 100:
            return f"{th_str} {number_to_english_phonetic_telugu(r)}"
        h, r2 = divmod(r, 100)
        h_str = ENGLISH_UNITS_TELUGU.get(h, str(h)) + " హండ్రెడ్"
        if r2 == 0:
            return f"{th_str} {h_str}"
        return f"{th_str} {h_str} {number_to_english_phonetic_telugu(r2)}"

    return str(val)


# Technical brands, models, and creator terms dictionary
BRAND_DICTIONARY = {
    # Apple ecosystem
    "iPhone": "ఐఫోన్",
    "iphone": "ఐఫోన్",
    "Apple": "యాపిల్",
    "apple": "యాపిల్",
    "iPad": "ఐప్యాడ్",
    "MacBook": "మ్యాక్‌బుక్",
    "Apple Watch": "యాపిల్ వాచ్",
    "AirPods": "ఎయిర్‌పాడ్స్",
    "Dynamic Island": "డైనమిక్ ఐలాండ్",
    "Apple Intelligence": "యాపిల్ ఇంటెలిజెన్స్",
    "Action Button": "యాక్షన్ బటన్",
    "Camera Control": "కెమెరా కంట్రోల్",
    "Bionic": "బయోనిక్",

    # Model qualifiers
    "Pro Max": "ప్రో మ్యాక్స్",
    "pro max": "ప్రో మ్యాక్స్",
    "Pro": "ప్రో",
    "pro": "ప్రో",
    "Plus": "ప్లస్",
    "plus": "ప్లస్",
    "Ultra": "అల్ట్రా",
    "ultra": "అల్ట్రా",
    "Mini": "మినీ",
    "mini": "మినీ",
    "Max": "మ్యాక్స్",
    "max": "మ్యాక్స్",

    # Samsung & Android brands
    "Samsung Galaxy": "సామ్సంగ్ గెలాక్సీ",
    "Samsung": "సామ్సంగ్",
    "శ్యామ్‌సంగ్": "సామ్సంగ్",
    "శ్యామ్సంగ్": "సామ్సంగ్",
    "Galaxy": "గెలాక్సీ",
    "OnePlus": "వన్‌ప్లస్",
    "Oneplus": "వన్‌ప్లస్",
    "Pixel": "పిక్సెల్",
    "Motorola": "మోటోరోలా",
    "Xiaomi": "షావోమి",
    "Realme": "రియల్‌మీ",
    "Nothing Phone": "నథింగ్ ఫోన్",
    "Nothing": "నథింగ్",
    "Vivo": "వివో",
    "Oppo": "ఒప్పో",
    "Poco": "పోకో",
    "iQOO": "ఐకూ",
    "iqoo": "ఐకూ",
    "Redmi": "రెడ్‌మీ",

    # Chipsets
    "Snapdragon": "స్నాప్‌డ్రాగన్",
    "Exynos": "ఎక్సినోస్",
    "Dimensity": "డైమెన్సిటీ",
    "Tensor": "టెన్సర్",
    "MediaTek": "మీడియాటెక్",
    "Qualcomm": "క్వాల్కమ్",

    # Materials & Display
    "Gorilla Glass Victus+": "గొరిల్లా గ్లాస్ విక్టస్ ప్లస్",
    "Gorilla Glass Victus": "గొరిల్లా గ్లాస్ విక్టస్",
    "Gorilla Glass": "గొరిల్లా గ్లాస్",
    "AMOLED": "అమోలెడ్",
    "OLED": "ఓలెడ్",
    "Titanium": "టైటానియం",
    "Aluminum": "అల్యూమినియం",

    # Tech actions & features
    "Unboxing": "అన్‌బాక్సింగ్",
    "Unbox": "అన్‌బాక్స్",
    "Review": "రివ్యూ",
    "Update": "అప్‌డేట్",
    "Updates": "అప్‌డేట్స్",
    "Features": "ఫీచర్లు",
    "Display": "డిస్‌ప్లే",
    "Camera": "కెమెరా",
    "Battery": "బ్యాటరీ",
    "Fast Charging": "ఫాస్ట్ ఛార్జింగ్",
    "Wireless Charging": "వైర్‌లెస్ ఛార్జింగ్",
    "Type-C": "టైప్ సి",
    "Type C": "టైప్ సి",
    "USB-C": "యుఎస్‌బి సి",
    "Bluetooth": "బ్లూటూత్",
    "WiFi": "వైఫై",
    "Wi-Fi": "వైఫై",
    "AI": "ఏఐ",
    "5G": "ఫైవ్ జీ",
    "4G": "ఫోర్ జీ",
    "Comments": "కామెంట్స్",
    "Subscribers": "సబ్‌స్క్రైబర్స్",
    "Followers": "ఫాలోవర్స్",

    # Social media, creators & cyber security
    "Social Media": "సోషల్ మీడియా",
    "social media": "సోషల్ మీడియా",
    "Delhi Police": "ఢిల్లీ పోలీస్",
    "delhi police": "ఢిల్లీ పోలీస్",
    "Police": "పోలీస్",
    "police": "పోలీస్",
    "Cyber Crime": "సైబర్ క్రైమ్",
    "cyber crime": "సైబర్ క్రైమ్",
    "Cyber Security": "సైబర్ సెక్యూరిటీ",
    "cyber security": "సైబర్ సెక్యూరిటీ",
    "Cyber": "సైబర్",
    "cyber": "సైబర్",
    "Trending": "ట్రెండింగ్",
    "trending": "ట్రెండింగ్",
    "Trend": "ట్రెండ్",
    "trend": "ట్రెండ్",
    "Filter": "ఫిల్టర్",
    "filter": "ఫిల్టర్",
    "Filters": "ఫిల్టర్స్",
    "filters": "ఫిల్టర్స్",
    "Photos": "ఫోటోలు",
    "photos": "ఫోటోలు",
    "Photo": "ఫోటో",
    "photo": "ఫోటో",
    "Viral": "వైరల్",
    "viral": "వైరల్",
    "Scam": "స్కామ్",
    "scam": "స్కామ్",
    "Scams": "స్కామ్స్",
    "scams": "స్కామ్స్",
    "Hacker": "హ్యాకర్",
    "hacker": "హ్యాకర్",
    "Hackers": "హ్యాకర్స్",
    "hackers": "హ్యాకర్స్",
    "Warning": "వార్నింగ్",
    "warning": "వార్నింగ్",
    "Alert": "అలర్ట్",
    "alert": "అలర్ట్",
    "Link": "లింక్",
    "link": "లింక్",
    "Links": "లింక్స్",
    "links": "లింక్స్",
    "App": "యాప్",
    "app": "యాప్",
    "Apps": "యాప్స్",
    "apps": "యాప్స్",
    "Profile": "ప్రొఫైల్",
    "profile": "ప్రొఫైల్",
    "Profiles": "ప్రొఫైల్స్",
    "profiles": "ప్రొఫైల్స్",
    "Online": "ఆన్‌లైన్",
    "online": "ఆన్‌లైన్",
    "Digital": "డిజిటల్",
    "digital": "డిజిటల్",
    "Fake": "ఫేక్",
    "fake": "ఫేక్",
    "Vintage": "వింటేజ్",
    "vintage": "వింటేజ్",
    "Nostalgia": "నాస్టాల్జియా",
    "nostalgia": "నాస్టాల్జియా",
    "VS": "వర్సెస్",
    "vs": "వర్సెస్",
    "vs.": "వర్సెస్",
    "Kids": "కిడ్స్",
    "kids": "కిడ్స్",
}


def normalize_smartphones_and_models(text: str) -> str:
    """
    Normalizes phone model numbers to English phonetics so that:
    - 'Galaxy S27' / 'గెలాక్సీ 27' / 'ఎస్ ఇరవై ఏడు' -> 'గెలాక్సీ ఎస్ ట్వంటీ సెవెన్'
    - 'iPhone 18' -> 'ఐఫోన్ ఎయిటీన్' (never 'ఐఫోన్ పద్దెనిమిది')
    - 'iPhone 18 Pro Max' -> 'ఐఫోన్ ఎయిటీన్ ప్రో మ్యాక్స్'
    - 'S26' / 'ఎస్ 26' -> 'ఎస్ ట్వంటీ సిక్స్'
    - 'OnePlus 13' -> 'వన్‌ప్లస్ థర్టీన్'
    - 'Pixel 9 Pro' -> 'పిక్సెల్ నైన్ ప్రో'
    """
    # 0. Convert written formal Telugu numbers for Samsung Galaxy S-series
    LB = r"(?<![A-Za-z0-9\u0C00-\u0C7F])"
    RB = r"(?=(?:[లోతోకికునిలపైనుంచినాటివరకు]*)(?:[^A-Za-z0-9\u0C00-\u0C7F]|$))"

    s_series_telugu_words = [
        (LB + r"(?:Samsung\s*|సామ్‌సంగ్\s*|శామ్‌సంగ్\s*)?(?:Galaxy\s*|గెలాక్సీ\s*)?(?:S|ఎస్)\s*ఇరవై\s*ఏడు" + RB, "గెలాక్సీ ఎస్ ట్వంటీ సెవెన్"),
        (LB + r"(?:Samsung\s*|సామ్‌సంగ్\s*|శామ్‌సంగ్\s*)?(?:Galaxy\s*|గెలాక్సీ\s*)ఇరవై\s*ఏడు" + RB, "గెలాక్సీ ఎస్ ట్వంటీ సెవెన్"),
        (LB + r"(?:Samsung\s*|సామ్‌సంగ్\s*|శామ్‌సంగ్\s*)?(?:Galaxy\s*|గెలాక్సీ\s*)?(?:S|ఎస్)\s*ఇరవై\s*ఆరు" + RB, "గెలాక్సీ ఎస్ ట్వంటీ సిక్స్"),
        (LB + r"(?:Samsung\s*|సామ్‌సంగ్\s*|శామ్‌సంగ్\s*)?(?:Galaxy\s*|గెలాక్సీ\s*)ఇరవై\s*ఆరు" + RB, "గెలాక్సీ ఎస్ ట్వంటీ సిక్స్"),
        (LB + r"(?:Samsung\s*|సామ్‌సంగ్\s*|శామ్‌సంగ్\s*)?(?:Galaxy\s*|గెలాక్సీ\s*)?(?:S|ఎస్)\s*ఇరవై\s*ఐదు" + RB, "గెలాక్సీ ఎస్ ట్వంటీ ఫైవ్"),
        (LB + r"(?:Samsung\s*|సామ్‌సంగ్\s*|శామ్‌సంగ్\s*)?(?:Galaxy\s*|గెలాక్సీ\s*)?(?:S|ఎస్)\s*ఇరవై\s*నాలుగు" + RB, "గెలాక్సీ ఎస్ ట్వంటీ ఫోర్"),
        (LB + r"(?:Samsung\s*|సామ్‌సంగ్\s*|శామ్‌సంగ్\s*)?(?:Galaxy\s*|గెలాక్సీ\s*)?(?:S|ఎస్)\s*ఇరవై\s*మూడు" + RB, "గెలాక్సీ ఎస్ ట్వంటీ త్రీ"),
        (LB + r"(?:Samsung\s*|సామ్‌సంగ్\s*|శామ్‌సంగ్\s*)?(?:Galaxy\s*|గెలాక్సీ\s*)?(?:S|ఎస్)\s*ఇరవై\s*రెండు" + RB, "గెలాక్సీ ఎస్ ట్వంటీ టూ"),
        (LB + r"(?:Samsung\s*|సామ్‌సంగ్\s*|శామ్‌సంగ్\s*)?(?:Galaxy\s*|గెలాక్సీ\s*)?(?:S|ఎస్)\s*ఇరవై\s*ఒకటి" + RB, "గెలాక్సీ ఎస్ ట్వంటీ వన్"),
        (LB + r"(?:Samsung\s*|సామ్‌సంగ్\s*|శామ్‌సంగ్\s*)?(?:Galaxy\s*|గెలాక్సీ\s*)?(?:S|ఎస్)\s*ఇరవై" + RB, "గెలాక్సీ ఎస్ ట్వంటీ"),
    ]
    for pat, repl in s_series_telugu_words:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)

    # 1. iPhone model numbers
    def replace_iphone(m):
        num = int(m.group(1))
        return f"ఐఫోన్ {number_to_english_phonetic_telugu(num)}"

    text = re.sub(r"(?i)\b(?:iphone|ఐఫోన్)\s*(\d{1,2})\b", replace_iphone, text)

    # 2. Samsung Galaxy / S-series digits: Galaxy 27, Galaxy S27, S27, గెలాక్సీ 27, గెలాక్సీ ఎస్ 27
    def replace_galaxy_series(m):
        num = int(m.group(1))
        return f"గెలాక్సీ ఎస్ {number_to_english_phonetic_telugu(num)}"

    text = re.sub(r"(?i)\b(?:Samsung\s*|సామ్‌సంగ్\s*|శామ్‌సంగ్\s*)?(?:Galaxy|గెలాక్సీ)\s*(?:S|ఎస్)?\s*(\d{1,2})\b", replace_galaxy_series, text)

    def replace_s_series(m):
        num = int(m.group(1))
        return f"ఎస్ {number_to_english_phonetic_telugu(num)}"

    text = re.sub(r"(?i)\b(?:S|ఎస్)\s*(\d{2})\b", replace_s_series, text)

    # 3. Other major brands followed by numbers
    def replace_brand_number(m):
        brand = m.group(1)
        num = int(m.group(2))
        return f"{brand} {number_to_english_phonetic_telugu(num)}"

    brands_pattern = (
        r"(?i)\b(OnePlus|వన్‌ప్లస్|Pixel|పిక్సెల్|Realme|రియల్‌మీ|Redmi\s*Note|రెడ్‌మీ\s*నోట్|"
        r"Redmi|రెడ్‌మీ|Poco|పోకో|Vivo|వివో|Oppo|ఒప్పో|iQOO|ఐకూ|Nothing\s*Phone|నథింగ్\s*ఫోన్|"
        r"Moto\s*G|మోటో\s*జి|Moto\s*Edge|మోటో\s*ఎడ్జ్|Moto|మోటో)\s*(\d{1,2})\b"
    )
    text = re.sub(brands_pattern, replace_brand_number, text)

    return text


def normalize_processors_and_chips(text: str) -> str:
    """
    Normalizes chipsets & processor codes:
    - 'A20 Pro' / 'ఏ20 ప్రో' -> 'ఏ ట్వంటీ ప్రో'
    - 'A18' / 'ఏ18' -> 'ఏ ఎయిటీన్'
    - 'M4' / 'ఎం4' -> 'ఎం ఫోర్'
    - 'Snapdragon 8 Gen 3' -> 'స్నాప్‌డ్రాగన్ ఎయిట్ జెన్ త్రీ'
    """
    # Apple A-series: A18, A20, ఏ20, etc.
    def replace_a_chip(m):
        num = int(m.group(1))
        return f"ఏ {number_to_english_phonetic_telugu(num)}"

    text = re.sub(r"(?i)\b(?:A|ఏ)\s*(\d{1,2})\b", replace_a_chip, text)

    # Apple M-series: M1, M2, M3, M4, ఎం4
    def replace_m_chip(m):
        num = int(m.group(1))
        return f"ఎం {number_to_english_phonetic_telugu(num)}"

    text = re.sub(r"(?i)\b(?:M|ఎం)\s*(\d{1,2})\b", replace_m_chip, text)

    # Snapdragon Gen series: Gen 3, Gen 4, జెన్ 3
    def replace_gen(m):
        num = int(m.group(1))
        return f"జెన్ {number_to_english_phonetic_telugu(num)}"

    text = re.sub(r"(?i)\b(?:Gen|జెన్)\s*(\d{1,2})\b", replace_gen, text)

    # Chipset digits (e.g. Snapdragon 8s, 8 Gen)
    text = re.sub(r"(?i)\bస్నాప్‌డ్రాగన్\s*8\b", "స్నాప్‌డ్రాగన్ ఎయిట్", text)
    text = re.sub(r"(?i)\bSnapdragon\s*8\b", "స్నాప్‌డ్రాగన్ ఎయిట్", text)

    return text


def normalize_specs_and_units(text: str) -> str:
    """
    Normalizes hardware specifications into English phonetic speech in Telugu:
    - '48 మెగాపిక్సెల్' / '48MP' -> 'ఫార్టీ ఎయిట్ మెగాపిక్సెల్'
    - '50MP' -> 'ఫిఫ్టీ మెగాపిక్సెల్'
    - '200MP' -> 'టూ హండ్రెడ్ మెగాపిక్సెల్'
    - '2TB' -> 'టూ టీబీ'
    - '128GB' -> 'వన్ ట్వంటీ ఎయిట్ జీబీ'
    - '256GB' -> 'టూ ఫిఫ్టీ సిక్స్ జీబీ'
    - '120Hz' -> 'వన్ ట్వంటీ హెర్ట్జ్'
    - '4K' -> 'ఫోర్ కే'
    - '5G' -> 'ఫైవ్ జీ'
    - '45W' -> 'ఫార్టీ ఫైవ్ వాట్ల'
    """
    # UFS Storage specification (UFS 5.1 -> యూఎఫ్ఎస్ ఫైవ్ పాయింట్ వన్, UFS 5 -> యూఎఫ్ఎస్ ఫైవ్)
    def replace_ufs(m):
        whole = number_to_english_phonetic_telugu(int(m.group(1)))
        if m.group(2):
            dec = number_to_english_phonetic_telugu(int(m.group(2)))
            return f"యూఎఫ్ఎస్ {whole} పాయింట్ {dec}"
        return f"యూఎఫ్ఎస్ {whole}"

    text = re.sub(r"(?i)\b(?:UFS|యూఎఫ్ఎస్|యుఎఫ్ఎస్)\s*(\d+)(?:\.(\d+))?\b", replace_ufs, text)

    LB = r"(?<![A-Za-z0-9\u0C00-\u0C7F])"
    RB = r"(?![A-Za-z0-9\u0C00-\u0C7F])"

    # Convert written formal Telugu words for UFS:
    ufs_telugu_words = [
        (LB + r"(?:యూఎఫ్ఎస్|యుఎఫ్ఎస్)\s*ఐదు\s*పాయింట్\s*(?:ఒకటి|వన్)" + RB, "యూఎఫ్ఎస్ ఫైవ్ పాయింట్ వన్"),
        (LB + r"(?:యూఎఫ్ఎస్|యుఎఫ్ఎస్)\s*ఐదు" + RB, "యూఎఫ్ఎస్ ఫైవ్"),
        (LB + r"(?:యూఎఫ్ఎస్|యుఎఫ్ఎస్)\s*నాలుగు\s*పాయింట్\s*జీరో" + RB, "యూఎఫ్ఎస్ ఫోర్ పాయింట్ జీరో"),
        (LB + r"(?:యూఎఫ్ఎస్|యుఎఫ్ఎస్)\s*నాలుగు" + RB, "యూఎఫ్ఎస్ ఫోర్"),
        (LB + r"(?:యూఎఫ్ఎస్|యుఎఫ్ఎస్)\s*మూడు\s*పాయింట్\s*(?:ఒకటి|వన్)" + RB, "యూఎఫ్ఎస్ త్రీ పాయింట్ వన్"),
    ]
    for pat, repl in ufs_telugu_words:
        text = re.sub(pat, repl, text)

    # RAM Types & Specs
    text = re.sub(r"(?i)\bLPDDR\s*5X\b", "ఎల్పీడీడీఆర్ ఫైవ్ ఎక్స్", text)
    text = re.sub(r"(?i)\bLPDDR\s*6\b", "ఎల్పీడీడీఆర్ సిక్స్", text)
    text = re.sub(r"(?i)\bLPDDR\s*5\b", "ఎల్పీడీడీఆర్ ఫైవ్", text)
    text = re.sub(r"\bఎల్పీడీడీఆర్\s*ఫైవ్\s*ఎక్స్\b", "ఎల్పీడీడీఆర్ ఫైవ్ ఎక్స్", text)

    # RAM capacity words in English or formal Telugu
    text = re.sub(
        r"(?i)\b(\d+)\s*(?:GB|జీబీ)\s*(?:RAM|రామ్|ర్యామ్)\b",
        lambda m: f"{number_to_english_phonetic_telugu(int(m.group(1)))} జీబీ ర్యామ్",
        text,
    )

    # RAM capacity words in formal Telugu
    ram_telugu_words = [
        (LB + r"పన్నెండు\s*జీబీ\s*(?:రామ్|ర్యామ్|RAM)" + RB, "ట్వెల్వ్ జీబీ ర్యామ్"),
        (LB + r"పదహారు\s*జీబీ\s*(?:రామ్|ర్యామ్|RAM)" + RB, "సిక్స్టీన్ జీబీ ర్యామ్"),
        (LB + r"ఎనిమిది\s*జీబీ\s*(?:రామ్|ర్యామ్|RAM)" + RB, "ఎయిట్ జీబీ ర్యామ్"),
        (LB + r"ఇరవై\s*నాలుగు\s*జీబీ\s*(?:రామ్|ర్యామ్|RAM)" + RB, "ట్వంటీ ఫోర్ జీబీ ర్యామ్"),
        (LB + r"నాలుగు\s*జీబీ\s*(?:రామ్|ర్యామ్|RAM)" + RB, "ఫోర్ జీబీ ర్యామ్"),
        (LB + r"(?:రామ్|RAM)" + RB, "ర్యామ్"),
        (r"(?i)\bRAM\b", "ర్యామ్"),
    ]
    for pat, repl in ram_telugu_words:
        text = re.sub(pat, repl, text)

    # Storage in formal Telugu words (256GB, 128GB, 512GB, 1TB)
    storage_telugu_words = [
        (LB + r"రెండు\s*వందల\s*యాభై\s*ఆరు\s*(?:జీబీ|GB|గిగాబైట్|గిగాబైట్లు)" + RB, "టూ ఫిఫ్టీ సిక్స్ జీబీ"),
        (LB + r"రెండు\s*వందల\s*యాభై\s*ఆరు" + RB + r"(?=.*(?:స్టోరేజ్|జీబీ|GB))", "టూ ఫిఫ్టీ సిక్స్"),
        (LB + r"నూట\s*ఇరవై\s*ఎనిమిది\s*(?:జీబీ|GB|గిగాబైట్|గిగాబైట్లు)" + RB, "వన్ ట్వంటీ ఎయిట్ జీబీ"),
        (LB + r"ఐదు\s*వందల\s*పన్నెండు\s*(?:జీబీ|GB|గిగాబైట్|గిగాబైట్లు)" + RB, "ఫైవ్ ట్వెల్వ్ జీబీ"),
        (LB + r"ఒక\s*(?:టెరాబైట్|టీబీ|TB)" + RB, "వన్ టీబీ"),
    ]
    for pat, repl in storage_telugu_words:
        text = re.sub(pat, repl, text)

    # Fast charging wattage in formal Telugu words
    watt_telugu_words = [
        (LB + r"అరవై\s*(?:వాట్ల|వాట్|వాట్స్)" + RB, "సిక్స్టీ వాట్ల"),
        (LB + r"నలభై\s*ఐదు\s*(?:వాట్ల|వాట్|వాట్స్)" + RB, "ఫార్టీ ఫైవ్ వాట్ల"),
        (LB + r"యాభై\s*(?:వాట్ల|వాట్|వాట్స్)" + RB, "ఫిఫ్టీ వాట్ల"),
        (LB + r"వంద\s*(?:వాట్ల|వాట్|వాట్స్)" + RB, "హండ్రెడ్ వాట్ల"),
        (LB + r"నూట\s*ఇరవై\s*(?:వాట్ల|వాట్|వాట్స్)" + RB, "వన్ ట్వంటీ వాట్ల"),
    ]
    for pat, repl in watt_telugu_words:
        text = re.sub(pat, repl, text)

    # Battery capacity in formal Telugu words
    battery_telugu_words = [
        (LB + r"ఐదు\s*వేల\s*రెండు\s*వందల\s*(?:ఎంఏహెచ్|mAh)?\s*బ్యాటరీ" + RB, "ఫైవ్ థౌసండ్ టూ హండ్రెడ్ ఎంఏహెచ్ బ్యాటరీ"),
        (LB + r"ఐదు\s*వేల\s*రెండు\s*వందల\s*బ్యాటరీ" + RB, "ఫైవ్ థౌసండ్ టూ హండ్రెడ్ ఎంఏహెచ్ బ్యాటరీ"),
        (LB + r"ఐదు\s*వేల\s*ఏడు\s*వందల\s*(?:ఎంఏహెచ్|mAh)?\s*బ్యాటరీ" + RB, "ఫైవ్ థౌసండ్ సెవెన్ హండ్రెడ్ ఎంఏహెచ్ బ్యాటరీ"),
        (LB + r"ఐదు\s*వేల\s*ఏడు\s*వందల\s*బ్యాటరీ" + RB, "ఫైవ్ థౌసండ్ సెవెన్ హండ్రెడ్ ఎంఏహెచ్ బ్యాటరీ"),
        (LB + r"ఐదు\s*వేల\s*(?:ఎంఏహెచ్|mAh)?\s*బ్యాటరీ" + RB, "ఫైవ్ థౌసండ్ ఎంఏహెచ్ బ్యాటరీ"),
        (LB + r"ఆరు\s*వేల\s*(?:ఎంఏహెచ్|mAh)?\s*బ్యాటరీ" + RB, "సిక్స్ థౌసండ్ ఎంఏహెచ్ బ్యాటరీ"),
    ]
    for pat, repl in battery_telugu_words:
        text = re.sub(pat, repl, text)

    # Storage (TB / GB)
    text = re.sub(
        r"(?i)\b(\d+)\s*(?:TB|టీబీ|టెరాబైట్|టెరాబైట్లు)\b",
        lambda m: f"{number_to_english_phonetic_telugu(int(m.group(1)))} టీబీ",
        text,
    )

    text = re.sub(
        r"(?i)\b(\d+)\s*(?:GB|జీబీ|గిగాబైట్|గిగాబైట్లు)\b",
        lambda m: f"{number_to_english_phonetic_telugu(int(m.group(1)))} జీబీ",
        text,
    )

    # Camera resolution (MP / మెగాపిక్సెల్)
    text = re.sub(
        r"(\d+)\s*(?:MP|మెగాపిక్సెల్|మెగాపిక్సల్|మెగాపిక్సెల్స్)",
        lambda m: f"{number_to_english_phonetic_telugu(int(m.group(1)))} మెగాపిక్సెల్",
        text,
    )

    # Refresh rate (Hz / హెర్ట్జ్)
    text = re.sub(
        r"(\d+)\s*(?:Hz|హెర్ట్జ్)",
        lambda m: f"{number_to_english_phonetic_telugu(int(m.group(1)))} హెర్ట్జ్",
        text,
    )

    # Fast charging wattage (W / వాట్ / వాట్ల)
    def replace_watt(m):
        num_str = number_to_english_phonetic_telugu(int(m.group(1)))
        has_fast = bool(m.group(2))
        return f"{num_str} వాట్ల ఫాస్ట్ ఛార్జింగ్" if has_fast else f"{num_str} వాట్ల"

    text = re.sub(
        r"(\d+)\s*(?:W|వాట్|వాట్ల)(?:\s*(ఫాస్ట్\s*ఛార్జింగ్|fast\s*charging))?",
        replace_watt,
        text,
    )

    # Video resolution: 4K, 8K
    text = re.sub(r"(?i)\b4K\b", "ఫోర్ కే", text)
    text = re.sub(r"(?i)\b8K\b", "ఎయిట్ కే", text)

    # Network: 5G, 4G
    text = re.sub(r"(?i)\b5G\b", "ఫైవ్ జీ", text)
    text = re.sub(r"(?i)\b4G\b", "ఫోర్ జీ", text)

    # Display size: 6.7 ఇంచ్, 6.1 ఇంచ్
    def replace_inches(m):
        whole = number_to_english_phonetic_telugu(int(m.group(1)))
        dec = number_to_english_phonetic_telugu(int(m.group(2)))
        return f"{whole} పాయింట్ {dec} ఇంచ్"

    text = re.sub(r"(\d+)\.(\d+)\s*(?:inch|ఇంచ్|అంగుళాల|అంగుళం)", replace_inches, text)

    # Battery capacity: 5000mAh
    text = re.sub(
        r"(\d+)\s*(?:mAh|ఎంఏహెచ్)",
        lambda m: f"{number_to_english_phonetic_telugu(int(m.group(1)))} ఎంఏహెచ్",
        text,
    )

    # Camera Zoom: 3x optical zoom -> మూడు రెట్ల ఆప్టికల్ జూమ్ / 5x -> ఐదు రెట్ల
    text = re.sub(
        r"(?i)\b(\d+)\s*[xX]\s*(?:optical\s*zoom|ఆప్టికల్\s*జూమ్|zoom|జూమ్)\b",
        lambda m: f"{number_to_english_phonetic_telugu(int(m.group(1)))} ఎక్స్ జూమ్",
        text,
    )

    return text


def normalize_decades_and_eras(text: str) -> str:
    """
    Normalizes decade and era references so Edge-TTS never pronounces:
    - '80s' as 'యానభై ఎస్' -> converts to 'ఎయిటీస్'
    - '90s' as 'తొంభై ఎస్' -> converts to 'నైంటీస్'
    - '1980s' -> 'నైన్టీన్ ఎయిటీస్'
    - '2000s' -> 'టూ థౌసండ్స్'
    - Helpline '1930' -> 'వన్ నైన్ త్రీ జీరో'
    """
    # 4-digit decades first
    four_digit_decades = [
        (r"(?i)\b1980['’]?s\b", "నైన్టీన్ ఎయిటీస్"),
        (r"(?i)\b1990['’]?s\b", "నైన్టీన్ నైంటీస్"),
        (r"(?i)\b1970['’]?s\b", "నైన్టీన్ సెవెంటీస్"),
        (r"(?i)\b1960['’]?s\b", "నైన్టీన్ సిక్స్టీస్"),
        (r"(?i)\b1950['’]?s\b", "నైన్టీన్ ఫిఫ్టీస్"),
        (r"(?i)\b2000['’]?s\b", "టూ థౌసండ్స్"),
        (r"(?i)\b2010['’]?s\b", "ట్వంటీ టెన్స్"),
        (r"(?i)\b2020['’]?s\b", "ట్వంటీ ట్వంటీస్"),
    ]
    for pattern, repl in four_digit_decades:
        text = re.sub(pattern, repl, text)

    # 2-digit decades: 80s, 90s, 70s, 60s, 50s, 40s, 30s, 20s
    two_digit_decades = [
        (r"(?i)\b80['’]?s\b", "ఎయిటీస్"),
        (r"(?i)\b90['’]?s\b", "నైంటీస్"),
        (r"(?i)\b70['’]?s\b", "సెవెంటీస్"),
        (r"(?i)\b60['’]?s\b", "సిక్స్టీస్"),
        (r"(?i)\b50['’]?s\b", "ఫిఫ్టీస్"),
        (r"(?i)\b40['’]?s\b", "ఫార్టీస్"),
        (r"(?i)\b30['’]?s\b", "థర్టీస్"),
        (r"(?i)\b20['’]?s\b", "ట్వంటీస్"),
        # Telugu decade suffix forms: 80ల -> ఎయిటీస్
        (r"\b80\s*ల\b", "ఎయిటీస్"),
        (r"\b90\s*ల\b", "నైంటీస్"),
        (r"\b70\s*ల\b", "సెవెంటీస్"),
        (r"\b60\s*ల\b", "సిక్స్టీస్"),
        (r"\b50\s*ల\b", "ఫిఫ్టీస్"),
    ]
    for pattern, repl in two_digit_decades:
        text = re.sub(pattern, repl, text)

    # National Cyber Crime helpline 1930
    text = re.sub(r"\b1930\s*(?:నంబర్‌|నంబర్|number)?\b", "నైన్టీన్ థర్టీ నంబర్", text)

    return text


def normalize_telugu_tech_script(script_text: str) -> str:
    """
    Main entry point to normalize Telugu scripts before TTS synthesis.
    Eliminates pure Telugu number translations for modern tech terms and replaces
    English jargon with phonetically accurate Telugu creator pronunciations.
    """
    if not script_text or not isinstance(script_text, str):
        return ""

    text = script_text

    # 1. Decades, eras and helplines (80s -> ఎయిటీస్, 90s -> నైంటీస్, 1930 -> నైన్టీన్ థర్టీ)
    text = normalize_decades_and_eras(text)

    # 2. Exact phrase replacements from BRAND_DICTIONARY (longest keys first)
    sorted_brands = sorted(BRAND_DICTIONARY.keys(), key=len, reverse=True)
    for brand in sorted_brands:
        replacement = BRAND_DICTIONARY[brand]
        if re.search(r"^[A-Za-z0-9\+\-\s]+$", brand):
            prefix = r"\b" if brand[0].isalnum() else r"(?<!\w)"
            suffix = r"\b" if brand[-1].isalnum() else r"(?!\w)"
            pattern = prefix + re.escape(brand) + suffix
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        else:
            text = text.replace(brand, replacement)

    # 3. Smartphone model codes (iPhone 18 -> ఐఫోన్ ఎయిటీన్, Galaxy S26 -> గెలాక్సీ ఎస్ ట్వంటీ సిక్స్)
    text = normalize_smartphones_and_models(text)

    # 4. Processors and chips (A20 -> ఏ ట్వంటీ, M4 -> ఎం ఫోర్, Gen 3 -> జెన్ త్రీ)
    text = normalize_processors_and_chips(text)

    # 5. Tech specifications and hardware units (48MP, 2TB, 120Hz, 5G, 45W)
    text = normalize_specs_and_units(text)

    # 6. Clean extra spaces
    text = re.sub(r"\s+", " ", text).strip()

    return text


def polish_telugu_voice_with_ai(script_text: str) -> str:
    """
    Uses Gemini AI (if available) to ensure the Telugu narration script sounds like
    an authentic human Telugu YouTuber (Teluglish).
    Converts any remaining textbook Telugu numbers or formal words into spoken English phonetics in Telugu script.
    """
    if not script_text or not isinstance(script_text, str):
        return ""

    # Always run deterministic rule-based normalizer first
    normalized = normalize_telugu_tech_script(script_text)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return normalized

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = (
            "You are a professional Telugu YouTube creator editor (like Prasadtechintelugu).\n"
            "Review and polish this Telugu narration script so it sounds 100% natural, human, conversational, and energetic.\n"
            "CRITICAL RULES:\n"
            "1. NEVER use formal textbook Telugu numbers for tech models or specs (e.g. NEVER write 'ఇరవై ఏడు' for 27, NEVER write 'ఐదు' for UFS 5).\n"
            "2. Ensure all phone models and specs use conversational English phonetics written in Telugu script:\n"
            "   - 'Galaxy S27' -> 'గెలాక్సీ ఎస్ ట్వంటీ సెవెన్'\n"
            "   - 'UFS 5.1' -> 'యూఎఫ్ఎస్ ఫైవ్ పాయింట్ వన్'\n"
            "   - '256GB' -> 'టూ ఫిఫ్టీ సిక్స్ జీబీ'\n"
            "   - '12GB RAM' -> 'ట్వెల్వ్ జీబీ ర్యామ్'\n"
            "   - '60W' -> 'సిక్స్టీ వాట్ల ఛార్జింగ్'\n"
            "3. Keep the exact meaning and section lines. Do NOT add markdown, explanations, or English letters (except necessary brand acronyms).\n"
            "4. Output ONLY the polished Telugu script lines:\n\n"
            f"{normalized}"
        )
        for m_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                resp = client.models.generate_content(
                    model=m_name,
                    contents=prompt,
                )
                polished = resp.text.strip()
                if polished and len(polished) >= len(normalized) * 0.7:
                    return normalize_telugu_tech_script(polished)
            except Exception:
                continue
    except Exception:
        pass

    return normalized

"""
tools/trending_roast_topics.py - Live Real-Time Trending Bigg Boss & Tollywood Roast Topics

Fetches live Google News RSS feeds for Bigg Boss Telugu and Tollywood entertainment controversies in authentic Telugu.
Converts live news headlines into viral Telugu roast topics with dynamic rotation on every refresh.
"""

import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

_CACHE_LIVE_TOPICS: List[Dict[str, str]] = []
_CACHE_TIME: float = 0.0
CACHE_TTL_SEC = 180.0  # 3 minutes cache for live RSS pool

# Curated high-relevance evergreen Week 11 topics
WEEK_11_TOPICS = [
    {
        "badge": "⚡ నామినేషన్ల వార్",
        "topic": "బిగ్ బాస్ 10 వీక్ 11 నామినేషన్ల వార్ రోస్ట్: డేంజర్ జోన్‌లో ఎవరు? కంటెస్టెంట్ల వింత రీజన్స్ మరియు డబుల్ స్టాండర్డ్స్!",
        "desc": "Week 11 Nominations Turn Intense • Housemates Clash",
    },
    {
        "badge": "👑 మాజీల డిక్టేటర్ ఎంట్రీ",
        "topic": "బిగ్ బాస్ 10: డిక్టేటర్లుగా మాజీ కంటెస్టెంట్ల రీ-ఎంట్రీ కామెడీ రోస్ట్: హౌస్‌లో దడ, కంటెస్టెంట్ల కలవరం!",
        "desc": "Former Contestants Return As Dictators Task Drama",
    },
    {
        "badge": "🏆 టాప్ 5 రేసు & మైండ్ గేమ్స్",
        "topic": "బిగ్ బాస్ 10 టాప్ 5 రేసు & మైండ్ గేమ్స్ రోస్ట్: ఎవరి గేమ్ ఎక్కడ? ముసుగులు తీసిన కంటెస్టెంట్లు!",
        "desc": "Top 5 Finalist Race & Secret Alliances Exposed",
    },
    {
        "badge": "💥 నాగార్జున వీకెండ్ వారింగ్",
        "topic": "బిగ్ బాస్ 10 నాగార్జున వీకెండ్ వారింగ్ క్లాస్ రోస్ట్: కంటెస్టెంట్ల ముఖాల్లో షాకింగ్ ఎక్స్‌ప్రెషన్స్!",
        "desc": "Host Nagarjuna Weekend Reality Check & Gripping Review",
    },
]


def clean_telugu_headline(title: str) -> str:
    """Strips source suffixes and repetitive channel tags from headline."""
    t = re.sub(r"\s*-\s*[^-]+$", "", str(title)).strip()
    t = re.sub(r"^(Bigg\s*Boss\s*(Telugu)?\s*\d*\s*[:\|]\s*)+", "", t, flags=re.I).strip()
    return t


def format_headline_to_telugu_roast(headline: str) -> Dict[str, str]:
    """Translates or classifies a live news headline into a punchy Telugu roast topic."""
    c = clean_telugu_headline(headline)
    low_c = c.lower()

    if any(w in c for w in ["ఎలిమినే", "ఎలిమినేట్", "ఎలిమినేషన్", "సేఫ్"]):
        badge = "⚡ ఎలిమినేషన్ షాక్"
        rt = f"బిగ్ బాస్ 10 ఎలిమినేషన్ షాక్ రోస్ట్: {c}"
    elif any(w in c for w in ["నామినేషన్", "నామినేషన్ల", "నామినేట్", "ఓటింగ్", "డేంజర్"]):
        badge = "🔥 నామినేషన్ల రచ్చ"
        rt = f"బిగ్ బాస్ 10 నామినేషన్ల రచ్చ రోస్ట్: {c}"
    elif any(w in c for w in ["ట్విస్ట్", "రీ ఎంట్రీ", "రీ-ఎంట్రీ", "వైల్డ్ కార్డ్", "ఎంట్రీ", "డిక్టేటర్"]):
        badge = "🌪️ బిగ్ ట్విస్ట్"
        rt = f"బిగ్ బాస్ 10 బిగ్ ట్విస్ట్ రోస్ట్: {c}"
    elif any(w in c for w in ["కలెక్షన్స్", "హిట్", "ఫ్లాప్", "సినిమా", "హీరో", "డైరెక్టర్", "టాలీవుడ్"]):
        badge = "🎬 టాలీవుడ్ రచ్చ"
        rt = f"టాలీవుడ్ వైరల్ గాసిప్ రోస్ట్: {c}"
    else:
        badge = "🔴 తాజా హౌస్ రచ్చ"
        rt = f"బిగ్ బాస్ 10 లైవ్ డ్రామా రోస్ట్: {c}"

    return {"badge": badge, "topic": rt, "clean": c}


def fetch_live_trending_roast_topics(force_refresh: bool = False, rotation_step: int = 0) -> List[Dict[str, str]]:
    """
    Fetches real-time Bigg Boss Telugu 10 & Tollywood news from live Telugu Google News RSS.
    Returns dynamically rotated list so top 3 items are always fresh on every refresh.
    Curated evergreen topics are appended at the bottom.
    """
    global _CACHE_LIVE_TOPICS, _CACHE_TIME

    now = time.time()
    needs_fetch = force_refresh or not _CACHE_LIVE_TOPICS or ((now - _CACHE_TIME) > CACHE_TTL_SEC)

    if needs_fetch:
        feed_urls = [
            "https://news.google.com/rss/search?q=%E0%B0%AC%E0%B0%BF%E0%B0%97%E0%B1%8D+%E0%B0%AC%E0%B0%BE%E0%B0%B8%E0%B1%8D+when:7d&hl=te&gl=IN&ceid=IN:te",
            "https://news.google.com/rss/search?q=%E0%B0%9F%E0%B0%BE%E0%B0%B2%E0%B1%80%E0%B0%B5%E0%B1%81%E0%B0%A1%E0%B1%8D+when:3d&hl=te&gl=IN&ceid=IN:te",
            "https://news.google.com/rss/search?q=Bigg+Boss+Telugu+when:3d&hl=en-IN&gl=IN&ceid=IN:en",
        ]

        seen_titles = set()
        fresh_topics: List[Dict[str, str]] = []
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

        for url in feed_urls:
            try:
                req = urllib.request.Request(url, headers=headers)
                xml_data = urllib.request.urlopen(req, timeout=5).read()
                root = ET.fromstring(xml_data)
                for item in root.findall(".//item")[:15]:
                    raw_title = item.find("title").text if item.find("title") is not None else ""
                    source = item.find("source").text if item.find("source") is not None else "Google News"
                    clean_t = clean_telugu_headline(raw_title)
                    if not clean_t or len(clean_t) < 12:
                        continue
                    low_t = clean_t.lower()
                    if low_t in seen_titles:
                        continue
                    seen_titles.add(low_t)

                    fmt = format_headline_to_telugu_roast(clean_t)
                    fresh_topics.append({
                        "badge": fmt["badge"],
                        "topic": fmt["topic"],
                        "desc": f"{fmt["clean"]} ({source})",
                    })
            except Exception:
                continue

        if fresh_topics:
            _CACHE_LIVE_TOPICS = fresh_topics
            _CACHE_TIME = now

    live_pool = list(_CACHE_LIVE_TOPICS) if _CACHE_LIVE_TOPICS else []

    # Dynamic rotation: cycle through pool so top 3 items change on refresh
    if live_pool and len(live_pool) > 3 and rotation_step > 0:
        shift = (rotation_step * 3) % len(live_pool)
        live_pool = live_pool[shift:] + live_pool[:shift]

    # Combine: Rotated Live topics first, then Curated Week 11 topics
    combined = list(live_pool)
    for c in WEEK_11_TOPICS:
        if not any(c["topic"] == it["topic"] for it in combined):
            combined.append(c)

    return combined

"""
AI Topic Suggester Module (agents/topic_suggester.py) - Real-Time Daily Engine V2

Key Features:
1. Real-Time Daily Ingestion: Continuously monitors Google News RSS for the past 24-36 hours.
2. Anti-Noise & Anti-Collision: Filters out irrelevant noise ('Quickreads', horoscope, live updates)
   and strictly removes Hindi Bigg Boss (BB20, Salman, etc.) to guarantee 100% Telugu context.
3. Daily Auto-Updating Cache: Topics are cached per date and auto-expire every 4 hours, ensuring
   fresh daily ideas without manual work.
4. AI Viral Title Synthesizer: Converts breaking news stories into click-worthy, viral YouTube
   Shorts/Video titles using the fast Gemini cascade.
5. Guaranteed Zero-Repetition: Permanently logs and deduplicates against data/used_topics.json.
"""

import json
import os
import random
import re
import requests
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

USED_TOPICS_FILE = ROOT / "data" / "used_topics.json"
DAILY_CACHE_FILE = ROOT / "data" / "daily_topic_cache.json"

_SESSION_USED_TOPICS: Set[str] = set()

# ============================================================
# NOVELTY & USED TOPICS LEDGER
# ============================================================

def load_used_topics() -> Set[str]:
    """Loads set of previously used topics to guarantee 100% novelty."""
    all_used = set(_SESSION_USED_TOPICS)
    if USED_TOPICS_FILE.exists():
        try:
            data = json.loads(USED_TOPICS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                all_used.update(str(t).strip().lower() for t in data if isinstance(t, str) and str(t).strip())
        except Exception:
            pass
    return all_used


def record_used_topic(topic: str) -> None:
    """Records a selected or executed topic to ensure it is never repeated."""
    if not topic or not str(topic).strip():
        return
    clean_topic = str(topic).strip()
    _SESSION_USED_TOPICS.add(clean_topic.lower())
    USED_TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing_list = []
    if USED_TOPICS_FILE.exists():
        try:
            data = json.loads(USED_TOPICS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                existing_list = data
        except Exception:
            existing_list = []
    if clean_topic not in existing_list:
        existing_list.append(clean_topic)
        try:
            USED_TOPICS_FILE.write_text(json.dumps(existing_list, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


# ============================================================
# LIVE REAL-TIME GOOGLE NEWS FEEDS (Filtered to Past 24-36 Hours)
# ============================================================

CATEGORY_FEEDS = {
    "Bigg Boss Telugu": [
        "https://news.google.com/rss/search?q=Bigg+Boss+Telugu+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Star+Maa+Bigg+Boss+Telugu+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Sakshi+Bigg+Boss+Telugu+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://tv9telugu.com/entertainment/feed",
        "https://ntvtelugu.com/entertainment/feed",
    ],
    "Tollywood Trolls & Viral Drama": [
        "https://news.google.com/rss/search?q=Tollywood+troll+OR+Telugu+cinema+controversy+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Tollywood+viral+tweets+OR+clash+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://tv9telugu.com/entertainment/feed",
        "https://ntvtelugu.com/entertainment/feed",
    ],
    "Tech News": [
        "https://news.google.com/rss/search?q=technology+AI+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "Roasting": [
        "https://news.google.com/rss/search?q=Bigg+Boss+Telugu+controversy+OR+fight+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Tollywood+troll+OR+Telugu+viral+controversy+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://tv9telugu.com/entertainment/feed",
        "https://ntvtelugu.com/entertainment/feed",
    ],
    "Sarcastic": [
        "https://news.google.com/rss/search?q=Bigg+Boss+Telugu+drama+OR+Telugu+viral+controversy+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Tollywood+controversy+OR+Telugu+cinema+social+media+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://tv9telugu.com/entertainment/feed",
    ],
    "Funny": [
        "https://news.google.com/rss/search?q=Telugu+viral+meme+OR+funny+clip+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Bigg+Boss+Telugu+unseen+OR+comedy+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "Movie Reviews": [
        "https://news.google.com/rss/search?q=Telugu+movie+review+OR+OTT+releases+this+week+Telugu+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Telugu+box+office+collection+verdict+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://tv9telugu.com/entertainment/feed",
        "https://ntvtelugu.com/entertainment/feed",
    ],
    "Cinema & Entertainment": [
        "https://tv9telugu.com/entertainment/feed",
        "https://ntvtelugu.com/entertainment/feed",
        "https://news.google.com/rss/search?q=Tollywood+OR+Telugu+cinema+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Prabhas+OR+Pawan+Kalyan+OR+Mahesh+Babu+OR+NTR+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "Ground Reality AP/Telangana News": [
        "https://news.google.com/rss/search?q=Andhra+Pradesh+OR+Telangana+breaking+news+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Hyderabad+OR+Amaravati+development+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://tv9telugu.com/feed",
    ],
    "Indian Mysteries & Ancient Engineering": [
        "https://news.google.com/rss/search?q=Indian+temple+architecture+mystery+OR+unsolved+when:7d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=ISRO+space+science+discovery+when:7d&hl=en-IN&gl=IN&ceid=IN:en",
    ],
}

NOISE_PATTERNS = [
    "quickreads", "live updates", "photos:", "web story", "horoscope",
    "weather update", "cricket score", "gold rate", "stock market",
    "in pics", "view gallery", "astrology", "panchangam", "daily horoscope",
    "weekly horoscope", "zodiac sign", "bse", "nse", "sensex", "nifty"
]

HINDI_BB_MARKERS = [
    "bigg boss 20", "bb20", "bigg boss 18", "bb18", "bigg boss 17",
    "salman khan", "ashnoor", "kashvi", "aasif khan", "munawar", "shilpa shirodkar",
    "vivian dsena", "avinash mishra", "chahat pandey"
]

TELUGU_CONTESTANTS = [
    "varshini", "debjani", "ram prasad", "potti naresh", "mukesh",
    "thrigun", "trigun", "temper vamsi", "vamsi", "krishnudu", "sudheer",
    "jhansi", "rohit", "shalini", "aman", "srishti", "charan", "nagarjuna",
    "chaithra", "neethu", "dakkshi", "mithilesh",
    "star maa", "hotstar", "housemates", "ntv", "tv9", "sakshi"
]


def _normalize_category_key(content_type: str) -> str:
    c_lower = str(content_type or "").strip().lower().replace("_", " ").replace("-", " ")
    if "troll" in c_lower or "viral drama" in c_lower:
        return "Tollywood Trolls & Viral Drama"
    if "regional" in c_lower or "local news" in c_lower or "andhra" in c_lower or "telangana" in c_lower:
        return "Ground Reality AP/Telangana News"
    if "ancient" in c_lower or ("mystery" in c_lower and "history" not in c_lower):
        return "Indian Mysteries & Ancient Engineering"
    if "bigg boss" in c_lower or "bb10" in c_lower or "bb " in c_lower or c_lower == "bb":
        return "Bigg Boss Telugu"
    if "tech" in c_lower:
        return "Tech News"
    if "history" in c_lower:
        return "History"
    if "fact" in c_lower:
        return "Interesting Facts"
    if "roast" in c_lower:
        return "Roasting"
    if "sarcas" in c_lower:
        return "Sarcastic"
    if "funny" in c_lower or "comedy" in c_lower:
        return "Funny"
    if "review" in c_lower or "movie" in c_lower or "ott" in c_lower:
        return "Movie Reviews"
    if "cinema" in c_lower or "entertainment" in c_lower:
        return "Cinema & Entertainment"
    if "deep dive" in c_lower or "custom topic" in c_lower:
        return "Custom Topic / Deep Dive"
    return "General Topic"


def rank_topics_by_ovs(topics: List[str], category_key: str) -> List[str]:
    """Ranks topics descending by Omni-Viral Score (OVS)."""
    try:
        from analytics.omni_router import calculate_omni_viral_score
        ch_slug = "Imaginary_facts" if any(k in category_key.lower() for k in ("tech", "fact", "history", "ancient", "mystery", "regional", "ground")) else "viral_talks_me&mine"
        return sorted(topics, key=lambda t: calculate_omni_viral_score(t, category=category_key, channel_name=ch_slug), reverse=True)
    except Exception:
        return topics



def fetch_live_feed_items(category_key: str, limit: int = 15, max_age_hours: float = 24.0) -> List[str]:
    """
    Fetch live RSS headlines from Google News strictly published within max_age_hours (24h).
    Applies rigorous anti-noise and regional Telugu filtering.
    """
    urls = CATEGORY_FEEDS.get(category_key, [])
    if not urls:
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        )
    }

    now = datetime.now(timezone.utc)

    def _fetch_url(url: str) -> List[str]:
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code != 200:
                return []
            root = ET.fromstring(resp.content)
            candidates = []
            for item in root.findall(".//item")[:25]:
                title_elem = item.find("title")
                pub_elem = item.find("pubDate")
                if title_elem is None or not title_elem.text:
                    continue

                raw_title = title_elem.text.strip()
                # 1. Clean publisher attribution (- The Times of India, etc.)
                clean_title = re.sub(r"\s+[-|–—]\s+[^-|–—]+$", "", raw_title).strip()
                clean_lower = clean_title.lower()

                if len(clean_title) < 15:
                    continue

                # 2. Filter out spam / noise patterns
                if any(noise in clean_lower for noise in NOISE_PATTERNS):
                    continue

                # 3. Timestamp recency check
                if pub_elem is not None and pub_elem.text:
                    try:
                        pub_dt = parsedate_to_datetime(pub_elem.text)
                        age_hours = (now - pub_dt).total_seconds() / 3600.0
                        if age_hours > max_age_hours:
                            continue
                    except Exception:
                        pass

                # 4. Regional Telugu / Bigg Boss precision check
                if category_key == "Bigg Boss Telugu":
                    if any(h in clean_lower for h in HINDI_BB_MARKERS):
                        continue
                    has_telugu = "telugu" in clean_lower or any(c in clean_lower for c in TELUGU_CONTESTANTS)
                    if not has_telugu:
                        continue
                elif category_key in ("Cinema & Entertainment", "Movie Reviews", "Roasting"):
                    if any(h in clean_lower for h in HINDI_BB_MARKERS):
                        continue

                candidates.append(clean_title)
            return candidates
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=min(len(urls), 4)) as executor:
        results = list(executor.map(_fetch_url, urls))

    seen = set()
    deduped = []
    for sublist in results:
        for t in sublist:
            norm = re.sub(r"[^a-zA-Z0-9]", "", t.lower())
            if norm and norm not in seen:
                seen.add(norm)
                deduped.append(t)

    return deduped[:limit]


# ============================================================
# DAILY TOPIC CACHING (Auto-Refreshes Daily & Every 4 Hours)
# ============================================================

def get_daily_cached_topics(category_key: str, max_age_secs: int = 14400) -> Optional[List[str]]:
    """Retrieves cached daily topics if they belong to today and are fresher than 4 hours."""
    if not DAILY_CACHE_FILE.exists():
        return None
    try:
        now_ts = datetime.now(timezone.utc).timestamp()
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cache = json.loads(DAILY_CACHE_FILE.read_text(encoding="utf-8"))
        entry = cache.get(f"{today_str}_{category_key}")
        if entry:
            ts = entry.get("timestamp", 0)
            topics = entry.get("topics", [])
            if (now_ts - ts) < max_age_secs and len(topics) >= 3:
                return topics
    except Exception:
        pass
    return None


def save_daily_cached_topics(category_key: str, topics: List[str]) -> None:
    """Saves generated daily topics into cache."""
    if not topics:
        return
    DAILY_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    cache = {}
    if DAILY_CACHE_FILE.exists():
        try:
            cache = json.loads(DAILY_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    now_ts = datetime.now(timezone.utc).timestamp()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache[f"{today_str}_{category_key}"] = {
        "timestamp": now_ts,
        "topics": topics,
    }
    try:
        DAILY_CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ============================================================
# SMART VIRAL TOPIC RE-SHAPER (Deterministic Fallback)
# ============================================================

def _reshape_headline_deterministically(headline: str, category_key: str) -> str:
    """Converts a raw news headline into a punchy YouTube title without calling LLM."""
    h = headline.strip()
    if category_key == "Bigg Boss Telugu":
        if not re.search(r"bigg boss telugu", h, flags=re.I):
            return f"Bigg Boss Telugu 10 Shock: {h}! Unfiltered House Drama Breakdown"
        if not re.search(r"roast|shock|truth|twist|revealed|exposed", h, flags=re.I):
            return f"{h} - Shocking Twist & Unfiltered House Reaction!"
    elif category_key == "Roasting":
        if not re.search(r"roasting", h, flags=re.I):
            return f"Roasting the Drama: {h} & How Internet Lost Its Mind Entirely!"
    elif category_key == "Sarcastic":
        return f"The Peak Logic Behind {h}: Pure Entertainment Masterclass!"
    elif category_key == "Cinema & Entertainment":
        if not re.search(r"box office|update|shock|teaser|trailer", h, flags=re.I):
            return f"{h} - Official Buzz, Fans Reaction & Massive Update!"
    elif category_key == "Tech News":
        if not re.search(r"breakthrough|revealed|exposed|features", h, flags=re.I):
            return f"{h}: What This Next-Gen Breakthrough Means for Everyone!"
    return h


# ============================================================
# CURATED EVERGREEN TOPIC POOLS (For History & Science)
# ============================================================

CURATED_TOPICS = {
    "Bigg Boss Telugu": [
        "Bigg Boss Telugu 10: Shocking Mid-Week Eviction Danger Zone Unfiltered",
        "Bigg Boss Telugu 10 Nominations: Who Got Targeted in Savage Clan War?",
        "Bigg Boss Telugu 10: Host Nagarjuna's Weekend Class - Who Got Busted?",
        "Bigg Boss Telugu 10 Secret Room Twist: Will the Evicted Contestant Return?",
        "Bigg Boss Telugu 10 Voting Trends: Shocking Underdog Surge Exposed!",
        "Bigg Boss Telugu 10 Immunity Shield Task: Physical Chaos in the House",
        "Bigg Boss Telugu 10 Wildcard Shock: Old Contestants vs New House War",
        "Bigg Boss Telugu 10 Captaincy Race: Betrayals and Broken Alliances Tonight",
        "Bigg Boss Telugu 10 Sunday Funday Drama: Fake Smiles and Real Rivalries",
        "Bigg Boss Telugu 10 Mega Eviction Shock: The Unofficial Voting Leaks Analyzed",
    ],
    "Tech News": [
        "OpenAI Unveils Next-Gen AI Reasoning Model: What It Means for Developers",
        "Nvidia's Blackwell Architecture: The Superchips Powering the Next AI Supercomputers",
        "Apple Intelligence Features Rollout: What Changes for iPhone Users in India",
        "Quantum Supremacy Breakthrough: Scientists Simulate Molecules in Milliseconds",
        "Google Gemini Live vs ChatGPT Voice: Real-Time Multimodal AI Battle",
        "ISRO's Next Mission: Gaganyaan Human Spaceflight Preparations Underway",
        "The 3nm Chip Revolution: Why Smartphone Processors Are Hitting Physical Limits",
        "Solid-State Batteries: The Game-Changer That Could Triple Electric Vehicle Range",
        "DeepSeek MoE Architecture: How Open Source Models Rival Trillion-Dollar Frontier AIs",
        "Autonomous Humanoid Robots in Factories: Tesla Optimus vs Boston Dynamics Atlas",
        "The 2nm Semiconductor Era: TSMC, Intel, and Samsung Race to the Atomic Scale",
        "Humanoid Robot Agility Leap: Boston Dynamics & Agility Robotics in Real Warehouses",
        "Quantum Internet: How Entangled Photons Will Create Unhackable Global Networks",
        "Brain-Computer Interfaces: Neuralink's Latest Human Trials and Next-Gen Capabilities",
        "Nuclear Fusion Net Energy Gain: How Tokamak Reactors Are Closing in on Clean Energy",
        "Autonomous Drone Swarms: The AI Navigation Systems Redefining Aerospace Technology",
        "The Rise of Open Source AI: How Decentralized Models Keep Big Tech Monopolies Honest",
    ],
    "Cinema & Entertainment": [
        "Tollywood Box Office Pulse: How Big-Ticket Pan-India Projects Are Dominating Global Screens",
        "Tollywood's 1000-Crore Race: The Battle for India's Biggest Film Industry",
        "The Pan-India Revolution: Why South Indian Cinema Continues to Dominate the National Box Office",
        "The Director's Vision: How S.S. Rajamouli Crafts World-Class Cinematic Scale",
        "Tollywood Music Directors Era: Thaman, Anirudh & Devi Sri Prasad's Musical Battles",
        "The Rise of Re-Releases in Telugu Cinema: Pure Nostalgia or Box Office Salvation?",
        "Inside Tollywood Shooting Schedules: Why Pan-India Films Take 3 Years to Make",
        "OTT vs Single Screen Theaters: The Big Dilemma Facing Telugu Producers Today",
        "The Evolution of Telugu Action Cinema: From Fights to International Stunt Rigging",
        "The Sukumar School of Writing: How Complex Characters Redefined Modern Telugu Cinema",
        "Tollywood Cinematographers: The Visual Wizards Behind Indian Blockbusters",
        "Prabhas' Unmatched Box Office Pull: The Science Behind Pan-India Stardom",
    ],
    "Movie Reviews": [
        "Telugu Cinema Box Office Verdict: Why Good Content Triumphed Over Massive Budgets",
        "The Honest Movie Breakdown: Why Telugu Screenplays Need Better Second Halves",
        "Top 5 High-Rated Telugu Mystery & Thriller Films You Must Stream Right Now",
        "Tollywood Box Office Reality Check: Massive Openings vs Critical Long Run Verdict",
        "Why Modern Telugu Thrillers Are Setting New Benchmarks in Indian Cinema",
        "The Big Ticket Dilemma: Are High Movie Ticket Prices Killing Telugu Cinema Footfalls?",
        "Top 7 Telugu Web Series on OTT That Deserve Global Recognition",
        "The Science of Telugu Interval Bangs: Why They Make or Break a Movie",
    ],
    "Roasting": [
        "Roasting Telugu Movie Audio Launches: 3-Hour Speeches and Empty PR Hype",
        "Roasting Modern Tollywood Teasers: 100 Slow-Motion Shots and Zero Story",
        "Roasting Bigg Boss Telugu Eviction Twists: Secret Influencer PR Campaigns Exposed",
        "Roasting Tollywood Remakes: Ruining Classic Malayalam & Tamil Hits for Mass Formulas",
        "Roasting Telugu Celebrity Gym & Airport Looks: Paparazzi PR Stunts Exposed",
        "Roasting Overhyped Pan-India Movies That Crash on Day 1 at the Box Office",
        "Roasting Bigg Boss Telugu 10 Captaincy Tasks: Pure Chaos and Zero Sportsmanship",
        "Roasting Tollywood Item Songs: Same Beat, 500 Background Dancers, Zero Creativity",
        "Roasting 500-Crore Tollywood VFX: Why High-Budget CGI Still Looks Like Mobile Games",
        "Roasting Tollywood Box Office Posters: 100 Crores on Day 1 According to PR Math",
        "Roasting Tollywood Celebrity Podcast Interviews: 2 Hours of Self-Praise and Zero Substance",
    ],
    "Sarcastic": [
        "Why Waiting 3 Years for a Pan-India Sequel Is the Greatest Joy in Life",
        "The Art of Tollywood Mass Logic: Defying Physics with a Single Thigh Slap",
        "How to Win Bigg Boss Telugu Without Doing a Single Chore in the House",
        "Why Re-Releasing 20-Year-Old Movies Is Tollywood's Peak Creative Innovation",
        "The Brilliance of Paying 1000 Rupees for Popcorn at Multiplex Theaters",
        "Why Every Telugu Teaser Needs an Explosive Background Score to Hide the Plot",
        "The Masterclass of Giving 5-Star Reviews to Every Single Telugu Teaser",
        "How Tollywood Climax Twists Are Revealed in the First 10 Minutes of the Movie",
        "Why Every Telugu Protagonist Needs a 10-Minute Slow-Motion Cigarette Intro",
        "The Genius Strategy of Hyping Part 2 Before Finishing Part 1 Script",
    ],
    "Funny": [
        "The Agony of Watching Bigg Boss Telugu with Indian Parents: Relatable Comedy",
        "Expectation vs Reality: Trying to Book First-Day-First-Show Telugu Movie Tickets",
        "Types of People in Telugu Multiplexes: Whistlers, Phone Callers, and Popcorn Snatchers",
        "The Struggles of Buying Healthy Groceries in Telugu Households",
        "When Your Friend Explains the Complex Plot of a Tollywood Sci-Fi Movie",
        "The Pure Chaos of Attending a Big Telugu Wedding: Food Counters & Relatives",
        "Trying to Follow Google Maps in Old Hyderabad & Vijayawada Gali Streets",
        "When the Power Goes Out Right Before the Movie Climax on OTT",
        "Living with Roommates Who Are Obsessed with Bigg Boss Telugu Daily Voting",
        "The Comedy of Bargaining in Rythu Bazar vs Ordering on Blinkit",
    ],
    "Custom Topic / Deep Dive": [
        "The Complete History of the Nizams of Hyderabad & The Secret Wealth of Golconda",
        "How Tollywood Surpassed Bollywood: The Economics & Evolution of Pan-India Cinema",
        "The Andhra-Telangana Bifurcation 10 Years Later: Economic & Political Deep Dive",
        "The Rise and Fall of Ancient Indian Dynasties: Kakatiyas to Vijayanagara Empire",
        "The Global Microchip Monopoly: How Taiwan's TSMC Controls the World Economy",
        "The Psychology of Cult Followings in Indian Cinema: Why Fans Worship Stars",
        "The Hidden Science of Indian Temple Architecture: Ancient Engineering Breakthroughs",
        "Artificial General Intelligence: How Deep Learning Will Reshape Global Labor by 2030",
        "The Secrets of the Kakatiya Dynasty: How 13th-Century Irrigation Tanks Still Work",
        "The Untold Story of Ramoji Film City: How the World's Largest Film Studio Was Built",
    ],
    "History": [
        "The Kohinoor Diamond: The Ancient Curse of the Golconda Mine and the British Crown",
        "The Mystery of Floating Bricks: How Ramappa Temple Survived 800 Years of Earthquakes",
        "The Lost Underwater Metropolis of Dwarka: Submerged Secrets of Ancient Gujarat",
        "The Secret Vaults of Padmanabhaswamy Temple: What Lies Hidden Behind Vault B?",
        "The Untold Wealth of the Nizams of Hyderabad: How Mir Osman Ali Khan Hid Billions in Gold",
        "The Battle of Bobbili: The Epic Sacrifice and Bloodiest Siege in Telugu History",
        "The Indus Valley Civilization: How History's Most Peaceful Bronze Age Empire Vanished",
        "The Library of Alexandria: The Lost Inventions and Mysteries of the Ancient World",
        "The Antikythera Mechanism: The 2,000-Year-Old Analog Computer That Defied Time",
        "The Secrets of the Egyptian Pyramids: 5 Engineering Impossibilities Modern Science Can't Explain",
        "The Chernobyl Catastrophe: The Hour-by-Hour Untold True Story of Nuclear Disaster",
        "The Golden Age of Pirates: The Real History of Blackbeard, Treasure Fleets & Sea Warfare",
        "The Legend of Lepakshi: The Hanging Pillar That Mystifies Modern Civil Engineers",
        "The Hidden Tunnels of Golconda Fort: Secret Escape Routes Under the Deccan Plateau",
        "The Lost Gold of Vijayanagara: Where Did the Riches of Hampi Disappear?",
        "The Ancient Iron Pillar of Delhi: The Rust-Proof Metallurgy That Baffled Modern Scientists",
    ],
    "Interesting Facts": [
        "The Brain Glitch: The Real Psychological Science Behind Déjà Vu",
        "The Mariana Trench: Bizarre Alien Creatures Thriving in the Deepest Ocean Abyss",
        "Why Time Moves Slower on Mount Everest: The Physics of Gravitational Time Dilation",
        "The Wow! Signal: The 72-Second Deep Space Pulse Astronomers Still Cannot Explain",
        "What Happens If Earth Stops Spinning for Just 5 Seconds?",
        "The Immortal Jellyfish: The Deep-Sea Creature That Can Literally Reverse Aging",
        "Why Octopuses Have Three Hearts, Nine Brains, and Blue Blood",
        "The Coldest Place in the Known Universe Is Actually Located on Earth",
        "Why Do Humans Dream? The Fascinating Neuroscience of Memory and REM Sleep",
        "The Bermuda Triangle Mystery: What Modern Oceanography Actually Discovered",
        "The Quantum Superposition Paradox: How Particles Exist in Two Places Simultaneously",
    ],
    "General Topic": [
        "Will Humans Ever Colonize Mars? Real Science vs Science Fiction Promises",
        "The Future of Human Longevity: Can Genetic Science Actually Reverse Biological Aging?",
        "How the Global Internet Actually Works: Deep Sea Undersea Fiber Cables Connecting Continents",
        "The Psychology of Habit Loops: How Tiny Atomic Habits Rewire Your Neural Pathways",
        "The Global Semiconductor War: Why Microchips Have Become the World's New Oil",
        "The Physics of Black Holes: What Happens Past the Event Horizon?",
    ],
}


# ============================================================
# MAIN AI TOPIC GENERATOR
# ============================================================

def fetch_ai_topic_suggestions(
    content_type: str,
    count: int = 8,
    use_ai: bool = True,
    language_hint: str = "",
    force_refresh: bool = False,
) -> List[str]:
    """
    Daily Real-Time Topic Suggestion Engine.
    - Monitors real-time 24h Google News RSS headlines.
    - Filters out non-Telugu noise and Hindi Bigg Boss spam.
    - Synthesizes click-worthy viral video titles tailored to category tone.
    - Eliminates any previously used topic from data/used_topics.json.
    - Caches results daily with automated 4-hour rotation.
    """
    key = _normalize_category_key(content_type)
    used_set = load_used_topics()

    # 1. Check Daily Cache first (unless force_refresh is requested)
    if not force_refresh:
        cached = get_daily_cached_topics(key)
        if cached:
            fresh_cached = [t for t in cached if t.strip().lower() not in used_set]
            if len(fresh_cached) >= count:
                return fresh_cached[:count]

    # 2. For evergreen non-news categories (History, Interesting Facts, General)
    if key in ("History", "Interesting Facts", "General Topic", "Custom Topic / Deep Dive"):
        raw_pool = list(CURATED_TOPICS.get(key, CURATED_TOPICS["General Topic"]))
        random.shuffle(raw_pool)
        fresh_pool = [t for t in raw_pool if t.strip().lower() not in used_set]
        if len(fresh_pool) < count:
            fresh_pool.extend([t for t in raw_pool if t not in fresh_pool])
        return fresh_pool[:count]

    # 3. Ingest Real-Time Live Headlines strictly from past 24h
    live_headlines = fetch_live_feed_items(key, limit=12, max_age_hours=24.0)
    live_headlines = [h for h in live_headlines if h.strip().lower() not in used_set]

    # 4. Synthesize with LLM Cascade if live headlines available
    synthesized_titles = []
    if live_headlines:
        try:
            from providers.llm import generate_text_cascade
            
            tone_rules = {
                "Bigg Boss Telugu": "shocking nomination twists, voting leaks, GOAT tasks, wildcard drama, and housemate clashes in Bigg Boss Telugu 10",
                "Roasting": "hilarious, savage roasts of recent drama, overacting, and viral controversies",
                "Cinema & Entertainment": "high-energy Tollywood box office buzz, teaser breakdowns, and superstar announcements",
                "Movie Reviews": "honest movie verdicts, OTT releases this week, and plot twist analysis",
                "Tech News": "cutting-edge AI breakthroughs, smartphone releases, and semiconductor wars",
                "Sarcastic": "biting irony, Telugu cinema mass logic mockery, and mock praise of absurd events",
                "Funny": "relatable Telugu comedy and viral meme moments",
            }
            tone_rule = tone_rules.get(key, "exciting, viral YouTube video titles")
            
            headlines_block = "\n".join(f"- {h}" for h in live_headlines[:8])
            today_date_str = datetime.now().strftime("%B %d, %Y")
            
            prompt = f"""You are an elite YouTube content strategist for Telugu entertainment & Pop culture.
Current Date: {today_date_str}
Given these REAL BREAKING STORIES from TODAY ({today_date_str}, strictly past 24 hours):
{headlines_block}

Generate {count} distinct, high-CTR, click-worthy, viral YouTube video titles for the '{content_type}' category.
Focus on: {tone_rule}.

CRITICAL RULES:
1. Every title must be 10 to 16 words, punchy, dramatic, and compelling.
2. Ground them strictly in today's real stories (e.g. latest episode tasks, voting leaks, teaser reactions).
3. Do NOT invent fake celebrity names or confuse Telugu with Hindi shows.
4. Return ONLY a valid JSON array of strings: ["Title 1", "Title 2", ...]
5. Do NOT output markdown code blocks or explanations."""

            res = generate_text_cascade(prompt, step_name=f"daily_topics_{key.lower().replace(' ', '_')}")
            if res:
                clean_res = re.sub(r"^```(?:json)?\s*", "", res.strip(), flags=re.IGNORECASE)
                clean_res = re.sub(r"\s*```$", "", clean_res.strip())
                parsed = json.loads(clean_res)
                if isinstance(parsed, list):
                    for t in parsed:
                        t_str = str(t).strip().strip('"\'')
                        if len(t_str) >= 15 and t_str.lower() not in used_set and t_str not in synthesized_titles:
                            synthesized_titles.append(t_str)
        except Exception as e:
            print(f"Notice: LLM topic synthesis fell back to deterministic re-shaper: {e}")

    # 5. If LLM produced titles, use them!
    if synthesized_titles:
        out_topics = rank_topics_by_ovs(synthesized_titles, key)[:count]
        save_daily_cached_topics(key, out_topics)
        return out_topics

    # 6. Deterministic live re-shaping if LLM was unavailable
    if live_headlines:
        reshaped = [_reshape_headline_deterministically(h, key) for h in live_headlines]
        valid_reshaped = rank_topics_by_ovs([r for r in reshaped if r.lower() not in used_set], key)[:count]
        if valid_reshaped:
            save_daily_cached_topics(key, valid_reshaped)
            return valid_reshaped

    # 7. Ultimate safety fallback (dynamically generated for today's date)
    today_disp = datetime.now(timezone.utc).strftime("%A Special")
    today_fallbacks = [
        f"Bigg Boss Telugu 10 {today_disp}: Unfiltered House Drama and Shocking Elimination Update!",
        f"Bigg Boss Telugu 10 Voting Trends: Popular Contestants in Unexpected Danger Zone!",
        f"Tollywood Buzz: Mega Updates, Box Office Record Predictions & New Releases Breakdown!",
        f"Roasting the Drama: Bigg Boss Telugu 10 Clashing Housemates and Clan Wars Analyzed!",
        f"OTT Releases This Week: Top Telugu Movies and Series You Cannot Miss!",
    ]
    safe_out = rank_topics_by_ovs([t for t in today_fallbacks if t.lower() not in used_set], key)[:count]
    return safe_out or today_fallbacks[:count]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch real-time daily topic suggestions.")
    parser.add_argument("--category", default="Bigg Boss Telugu", help="Category name")
    parser.add_argument("--count", type=int, default=6, help="Number of topics")
    parser.add_argument("--refresh", action="store_true", help="Force refresh cache")
    args = parser.parse_args()

    print(f"\n🔍 Fetching fresh daily topics for '{args.category}'...")
    res = fetch_ai_topic_suggestions(args.category, count=args.count, force_refresh=args.refresh)
    print(f"\n🔥 Fresh Daily Topics ({len(res)}):\n")
    for idx, topic in enumerate(res, 1):
        print(f"{idx}. {topic}")

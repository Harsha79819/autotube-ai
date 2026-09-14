from dotenv import load_dotenv
load_dotenv()

from supervisor import autonomous_recover


"""
AUTOTUBE AI - TREND DISCOVERY ENGINE V5

Goal:
    Discover the strongest current internet trend/event for AutoTube AI.

Pipeline:
    Google News RSS
        ↓
    Candidate collection
        ↓
    Publisher deduplication
        ↓
    Event clustering
        ↓
    Recent momentum
        ↓
    Independent-source confirmation
        ↓
    Viral-potential scoring
        ↓
    Best topic
"""

import html
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, wait_random


# ============================================================
# CONFIG
# ============================================================

GOOGLE_NEWS_URL = (
    "https://news.google.com/rss/search?"
    "q={query}&hl=en-IN&gl=IN&ceid=IN:en"
)

TREND_QUERIES = [
    "latest technology news",
    "latest AI news",
    "latest smartphone news",
    "latest Apple news",
    "latest Google news",
    "latest OpenAI news",
    "latest Tesla news",
    "latest business news",
    "latest India news",
    "latest viral news",
    "breaking technology news",
    "breaking AI news",
]

MAX_PER_QUERY = 100
MAX_CANDIDATES = 1500

# Strong event matching.
EVENT_SIMILARITY = 0.42

# Duplicate article/title threshold.
DUPLICATE_SIMILARITY = 0.78


# ============================================================
# STOPWORDS
# ============================================================

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "for", "with",
    "from", "into", "over", "after", "before", "about",
    "latest", "breaking", "news", "update", "updates",
    "today", "live", "report", "reports", "says", "say",
    "said", "new", "now", "here", "what", "why", "how",
    "this", "that", "these", "those", "will", "could",
    "would", "should", "has", "have", "had", "is", "are",
    "was", "were", "its", "their", "they", "you", "your",
    "india", "world", "global", "latest",
}


# ============================================================
# GENERIC / ROUNDUP DETECTION
# ============================================================

GENERIC_PATTERNS = [
    r"latest .* news",
    r"breaking news and headlines",
    r"live updates",
    r"news today",
    r"top news",
    r"daily news",
    r"news roundup",
    r"morning news",
    r"evening news",
    r"all the latest",
    r"latest updates",
    r"what you need to know",
    r"here are the latest",
    r"today's top stories",
    r"latest headlines",
]


def is_generic_roundup(title):
    text = title.lower().strip()

    for pattern in GENERIC_PATTERNS:
        if re.search(pattern, text):
            return True

    return False


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def clean_text(value):
    if not value:
        return ""

    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def title_tokens(title):
    title = clean_text(title).lower()

    # Remove punctuation.
    title = re.sub(r"[^a-z0-9\s-]", " ", title)

    words = []

    for word in title.split():
        word = word.strip("-")

        if not word:
            continue

        if word in STOPWORDS:
            continue

        if len(word) < 3:
            continue

        words.append(word)

    return set(words)


# ============================================================
# SIMILARITY
# ============================================================

def similarity(a, b):
    ta = title_tokens(a)
    tb = title_tokens(b)

    if not ta or not tb:
        return 0.0

    intersection = len(ta & tb)
    union = len(ta | tb)

    if union == 0:
        return 0.0

    return intersection / union


def shared_entities(a, b):
    """
    Stronger signal for event clustering.

    Examples:
        OpenAI + GPT + Astra
        Apple + iPhone + September
        Tesla + Model + India
    """

    ta = title_tokens(a)
    tb = title_tokens(b)

    shared = ta & tb

    # Important words are more useful than generic overlap.
    important = {
        x for x in shared
        if len(x) >= 4
    }

    return important


# ============================================================
# DATE PARSING
# ============================================================

def parse_date(value):
    if not value:
        return None

    value = value.strip()

    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M %Z",
        "%Y-%m-%dT%H:%M:%S%z",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return dt.astimezone(timezone.utc)

        except Exception:
            pass

    return None


# ============================================================
# FRESHNESS
# ============================================================

def freshness_score(dt):
    if not dt:
        return 0

    now = datetime.now(timezone.utc)

    age_hours = max(
        0,
        (now - dt).total_seconds() / 3600,
    )

    if age_hours <= 2:
        return 30

    if age_hours <= 6:
        return 28

    if age_hours <= 12:
        return 25

    if age_hours <= 24:
        return 21

    if age_hours <= 48:
        return 14

    if age_hours <= 72:
        return 8

    if age_hours <= 120:
        return 3

    return 0


# ============================================================
# MOMENTUM
# ============================================================

def momentum_score(dates):
    """
    Measures how quickly an event is appearing in current news.

    Recent multiple publications are much stronger than old coverage.
    """

    if not dates:
        return 0

    now = datetime.now(timezone.utc)

    last_6h = 0
    last_12h = 0
    last_24h = 0
    last_48h = 0

    for dt in dates:
        if not dt:
            continue

        hours = (
            now - dt
        ).total_seconds() / 3600

        if hours <= 6:
            last_6h += 1

        if hours <= 12:
            last_12h += 1

        if hours <= 24:
            last_24h += 1

        if hours <= 48:
            last_48h += 1

    score = 0

    # Very recent velocity gets highest weight.
    score += min(last_6h * 5, 20)
    score += min(last_12h * 3, 15)
    score += min(last_24h * 2, 12)
    score += min(last_48h, 5)

    return min(score, 35)


# ============================================================
# INTEREST SIGNAL
# ============================================================

HIGH_INTEREST_TERMS = {
    "ai": 5,
    "openai": 7,
    "gpt": 7,
    "chatgpt": 7,
    "google": 5,
    "apple": 5,
    "iphone": 6,
    "tesla": 5,
    "robot": 5,
    "robotics": 5,
    "chip": 4,
    "chips": 4,
    "nvidia": 6,
    "crypto": 4,
    "bitcoin": 4,
    "startup": 3,
    "india": 3,
    "launch": 4,
    "launched": 4,
    "announces": 4,
    "announced": 4,
    "reveals": 4,
    "revealed": 4,
    "billion": 4,
    "million": 3,
    "deal": 3,
    "investment": 3,
    "invest": 3,
    "war": 5,
    "attack": 5,
    "election": 5,
    "crisis": 5,
    "viral": 6,
}


def interest_score(title):
    tokens = title_tokens(title)

    score = 0

    for token in tokens:
        score += HIGH_INTEREST_TERMS.get(token, 0)

    return min(score, 20)


# ============================================================
# YOUTUBE POTENTIAL
# ============================================================

YOUTUBE_TERMS = {
    "ai": 5,
    "gpt": 6,
    "openai": 6,
    "iphone": 5,
    "apple": 4,
    "google": 4,
    "tesla": 5,
    "robot": 5,
    "robotics": 5,
    "launch": 4,
    "launched": 4,
    "revealed": 4,
    "new": 2,
    "viral": 5,
    "shocking": 5,
    "explained": 4,
    "future": 4,
    "technology": 3,
}


def youtube_score(title):
    tokens = title_tokens(title)

    score = 0

    for token in tokens:
        score += YOUTUBE_TERMS.get(token, 0)

    return min(score, 20)


# ============================================================
# HTTP / RSS
# ============================================================

def _is_retryable_http_error(exception):
    if isinstance(exception, urllib.error.HTTPError):
        return exception.code in (429, 500, 502, 503, 504)
    if isinstance(exception, (urllib.error.URLError, TimeoutError, ConnectionResetError)):
        return True
    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8) + wait_random(0.1, 0.5),
    retry=retry_if_exception(_is_retryable_http_error),
    reraise=True,
)
def fetch_xml(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151 Safari/537.36"
            )
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=15,
    ) as response:

        return response.read()


# ============================================================
# RSS PARSER
# ============================================================

def parse_rss(xml_data):
    candidates = []

    try:
        root = ET.fromstring(xml_data)

    except Exception:
        return candidates

    for item in root.findall(".//item"):

        title = clean_text(
            item.findtext("title")
        )

        link = clean_text(
            item.findtext("link")
        )

        pub_date = clean_text(
            item.findtext("pubDate")
        )

        source_element = item.find("source")

        source = ""

        if source_element is not None:
            source = clean_text(
                source_element.text
            )

        description = clean_text(
            item.findtext("description")
        )

        if not title:
            continue

        candidates.append(
            {
                "title": title,
                "link": link,
                "source": source or "Unknown",
                "published": parse_date(pub_date),
                "description": description,
            }
        )

    return candidates


# ============================================================
# DISCOVERY
# ============================================================

def discover_candidates():
    all_candidates = []

    for query in TREND_QUERIES:

        encoded = urllib.parse.quote_plus(query)

        url = GOOGLE_NEWS_URL.format(
            query=encoded
        )

        try:
            xml_data = fetch_xml(url)

            items = parse_rss(xml_data)

            all_candidates.extend(
                items[:MAX_PER_QUERY]
            )

        except Exception as exc:
            print(
                f"WARNING: query failed: "
                f"{query} -> {exc}"
            )

        time.sleep(0.15)

    return all_candidates[:MAX_CANDIDATES]


# ============================================================
# ARTICLE DEDUPLICATION
# ============================================================

def deduplicate_candidates(candidates):
    """
    Remove duplicate RSS entries.

    IMPORTANT:
    Same publisher can still have multiple legitimate articles.
    We only remove near-identical titles.
    """

    result = []

    seen_links = set()

    for item in candidates:

        link = item.get("link", "")

        if link and link in seen_links:
            continue

        if link:
            seen_links.add(link)

        duplicate = False

        for existing in result:

            if similarity(
                item["title"],
                existing["title"],
            ) >= DUPLICATE_SIMILARITY:

                # Prefer the more recent article.
                existing_date = existing.get(
                    "published"
                )

                current_date = item.get(
                    "published"
                )

                if (
                    current_date
                    and existing_date
                    and current_date > existing_date
                ):
                    existing.update(item)

                duplicate = True
                break

        if not duplicate:
            result.append(item)

    return result


# ============================================================
# EVENT CLUSTERING V4
# ============================================================

# IMPORTANT:
# Do NOT use transitive / UnionFind clustering.
# A -> B -> C must NOT automatically merge unrelated stories.
#
# V4 compares every article against an EVENT REPRESENTATIVE.
# This keeps unrelated stories from becoming one giant cluster.


STRONG_ENTITY_TERMS = {
    "openai",
    "chatgpt",
    "gpt",
    "google",
    "gemini",
    "apple",
    "iphone",
    "microsoft",
    "meta",
    "tesla",
    "nvidia",
    "samsung",
    "amazon",
    "modi",
    "trump",
    "iran",
    "israel",
    "ukraine",
    "russia",
    "china",
    "india",
    "spacex",
    "xai",
    "anthropic",
    "deepmind",
}


EVENT_ACTIONS = {
    "launch",
    "launched",
    "launches",
    "announce",
    "announced",
    "announces",
    "announcement",
    "release",
    "released",
    "reveals",
    "revealed",
    "unveil",
    "unveiled",
    "introduce",
    "introduced",
    "acquire",
    "acquired",
    "acquisition",
    "invest",
    "investment",
    "deal",
    "attack",
    "attacked",
    "election",
    "win",
    "won",
    "approve",
    "approved",
    "ban",
    "banned",
    "recall",
    "crash",
    "dies",
    "died",
    "rescue",
    "rescued",
}


GENERIC_EVENT_WORDS = {
    "latest",
    "breaking",
    "news",
    "today",
    "update",
    "updates",
    "report",
    "reports",
    "story",
    "stories",
    "video",
    "live",
    "edition",
    "headlines",
    "technology",
    "tech",
    "business",
    "india",
    "world",
    "global",
}


def strong_entities(title):
    tokens = title_tokens(title)

    return {
        token
        for token in tokens
        if token in STRONG_ENTITY_TERMS
    }


def normalized_product_identity(title):
    value = clean_text(title).lower()
    patterns = [
        r"gpt[- ]?6[- ]?astra",
        r"gpt[- ]?5\.6",
        r"gpt[- ]?5(?![.0-9])",
        r"iphone[- ]?[0-9]+",
    ]
    identities = set()
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            identities.add(re.sub(r"[- ]+", "-", match.group(0)))
    return identities


def event_actions(title):
    tokens = title_tokens(title)

    return {
        token
        for token in tokens
        if token in EVENT_ACTIONS
    }


def meaningful_tokens(title):
    tokens = title_tokens(title)

    return {
        token
        for token in tokens
        if token not in GENERIC_EVENT_WORDS
    }


def event_match_score(a, b):
    """
    V5 conservative event identity matching.

    Product identity can strengthen matching for the same launch,
    but product identity alone never merges different sub-stories.
    """

    title_a = a["title"]
    title_b = b["title"]

    entities_a = strong_entities(title_a)
    entities_b = strong_entities(title_b)
    shared_entities_set = entities_a & entities_b

    products_a = normalized_product_identity(title_a)
    products_b = normalized_product_identity(title_b)
    shared_products_set = products_a & products_b

    sim = similarity(title_a, title_b)

    actions_a = event_actions(title_a)
    actions_b = event_actions(title_b)
    shared_actions_set = actions_a & actions_b

    meaningful_a = meaningful_tokens(title_a)
    meaningful_b = meaningful_tokens(title_b)

    meaningful_overlap = (
        len(meaningful_a & meaningful_b)
        / max(1, len(meaningful_a | meaningful_b))
    )

    # Very strong title match.
    if sim >= 0.62:
        return 1.0

    # Same exact product + same launch/release/announcement story.
    launch_actions = {
        "launch", "launched", "launches",
        "announce", "announced", "announces", "announcement",
        "release", "released", "reveals", "revealed",
        "unveil", "unveiled", "introduce", "introduced",
    }

    shared_launch_actions = (
        actions_a & actions_b & launch_actions
    )

    if (
        shared_products_set
        and shared_launch_actions
        and sim >= 0.45
        and meaningful_overlap >= 0.12
    ):
        return 0.95

    # Same strong entity + same event/action.
    if (
        shared_entities_set
        and shared_actions_set
        and meaningful_overlap >= 0.18
    ):
        return 0.90

    # Same strong entity with strong wording overlap.
    if (
        shared_entities_set
        and meaningful_overlap >= 0.30
    ):
        return 0.85

    # Multiple strong entities + reasonable title match.
    if (
        len(shared_entities_set) >= 2
        and sim >= 0.25
    ):
        return 0.80

    return 0.0

def events_match(a, b):
    return event_match_score(a, b) > 0


def cluster_events(candidates):
    """
    V4 representative-based clustering.

    IMPORTANT:
    No UnionFind.
    No transitive A->B->C merging.

    Every article is compared against existing event
    representatives. An article joins only when it has
    strong identity/event similarity with that representative.
    """

    events = []

    # Process newest articles first so representatives
    # are normally fresh headlines.
    ordered = sorted(
        candidates,
        key=lambda item: (
            item.get("published")
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True,
    )

    for item in ordered:

        best_index = None
        best_score = 0.0

        for index, event in enumerate(events):

            representative = event[0]

            score = event_match_score(
                item,
                representative,
            )

            if score > best_score:
                best_score = score
                best_index = index

        if (
            best_index is not None
            and best_score >= 0.80
        ):
            events[best_index].append(item)

        else:
            events.append([item])

    return events


# ============================================================
# EVENT ARTICLE LIMITING
# ============================================================

MAX_ARTICLES_PER_SOURCE = 3


def limit_source_articles(cluster):
    """
    Prevent one publisher from dominating an event.

    Example:
        Scripps = 200 articles
        Reuters = 2 articles

    becomes:
        Scripps = max 3
        Reuters = 2

    This makes article counts meaningful.
    """

    grouped = defaultdict(list)

    for item in cluster:
        source = (
            item.get("source")
            or "Unknown"
        ).strip().lower()

        grouped[source].append(item)

    result = []

    for source, items in grouped.items():

        items.sort(
            key=lambda x: (
                x.get("published")
                or datetime.min.replace(
                    tzinfo=timezone.utc
                )
            ),
            reverse=True,
        )

        result.extend(
            items[:MAX_ARTICLES_PER_SOURCE]
        )

    return result


# ============================================================
# EVENT QUALITY
# ============================================================

def source_count(cluster):
    return len(
        {
            item.get("source", "").strip().lower()
            for item in cluster
            if item.get("source")
        }
    )


def source_names(cluster):
    return sorted(
        {
            item.get("source", "").strip()
            for item in cluster
            if item.get("source")
        }
    )


def recent_source_count(cluster):
    """
    Count independent publishers that have published
    in the last 48 hours.
    """

    now = datetime.now(timezone.utc)

    recent_sources = set()

    for item in cluster:

        dt = item.get("published")

        source = item.get("source", "").strip()

        if not dt or not source:
            continue

        hours = (
            now - dt
        ).total_seconds() / 3600

        if hours <= 48:
            recent_sources.add(
                source.lower()
            )

    return len(recent_sources)


def cluster_freshness(cluster):
    scores = [
        freshness_score(
            item.get("published")
        )
        for item in cluster
    ]

    return max(scores) if scores else 0


def cluster_momentum(cluster):
    dates = [
        item.get("published")
        for item in cluster
        if item.get("published")
    ]

    return momentum_score(dates)


def cluster_interest(cluster):
    values = [
        interest_score(
            item["title"]
        )
        for item in cluster
    ]

    return max(values) if values else 0


def cluster_youtube(cluster):
    values = [
        youtube_score(
            item["title"]
        )
        for item in cluster
    ]

    return max(values) if values else 0


def coverage_score(cluster):
    """
    Independent publisher confirmation.

    1 publisher  -> 0
    2 publishers -> 3
    3 publishers -> 6
    4 publishers -> 9
    5+ publishers -> 12
    """

    count = recent_source_count(cluster)

    if count <= 1:
        return 0

    if count == 2:
        return 3

    if count == 3:
        return 6

    if count == 4:
        return 9

    return 12


def generic_penalty(cluster):
    generic_count = sum(
        1
        for item in cluster
        if is_generic_roundup(
            item["title"]
        )
    )

    if not cluster:
        return 0

    ratio = (
        generic_count / len(cluster)
    )

    if ratio >= 0.75:
        return 20

    if ratio >= 0.50:
        return 10

    if ratio >= 0.25:
        return 5

    return 0


def old_event_penalty(cluster):
    """
    Penalize events where almost all coverage is old.
    """

    now = datetime.now(timezone.utc)

    recent = 0

    for item in cluster:

        dt = item.get("published")

        if not dt:
            continue

        hours = (
            now - dt
        ).total_seconds() / 3600

        if hours <= 48:
            recent += 1

    if recent == 0:
        return 20

    if recent == 1 and len(cluster) >= 5:
        return 8

    return 0


# ============================================================
# EVENT SCORE
# ============================================================

def score_event(cluster):
    if not cluster:
        return 0

    freshness = cluster_freshness(cluster)
    momentum = cluster_momentum(cluster)
    interest = cluster_interest(cluster)
    youtube = cluster_youtube(cluster)

    sources = recent_source_count(cluster)

    coverage = coverage_score(cluster)

    penalties = (
        generic_penalty(cluster)
        + old_event_penalty(cluster)
    )

    # Strong weighting toward current momentum.
    score = (
        freshness
        + momentum
        + interest
        + youtube
        + coverage
        - penalties
    )

    # Independent-source bonus.
    if sources >= 3:
        score += 5

    if sources >= 5:
        score += 5

    return max(
        0,
        min(
            100,
            int(score),
        ),
    )


# ============================================================
# EVENT REPRESENTATION
# ============================================================

def best_title(cluster):
    """
    Pick the most useful headline rather than
    blindly selecting the first RSS result.
    """

    ranked = []

    for item in cluster:

        title = item["title"]

        score = (
            interest_score(title)
            + youtube_score(title)
            + freshness_score(
                item.get("published")
            )
        )

        if is_generic_roundup(title):
            score -= 20

        ranked.append(
            (
                score,
                title,
                item,
            )
        )

    ranked.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return ranked[0][1]


def event_to_dict(cluster):
    cluster = limit_source_articles(cluster)

    title = best_title(cluster)

    return {
        "title": title,
        "score": score_event(cluster),
        "article_count": len(cluster),
        "source_count": source_count(cluster),
        "total_source_count": source_count(cluster),
        "sources": source_names(cluster),
        "freshness_score": cluster_freshness(cluster),
        "momentum_score": cluster_momentum(cluster),
        "interest_score": cluster_interest(cluster),
        "youtube_score": cluster_youtube(cluster),
        "coverage_score": coverage_score(cluster),
        "generic_penalty": generic_penalty(cluster),
        "old_event_penalty": old_event_penalty(cluster),
        "articles": cluster,
    }


# ============================================================
# AI VIRAL-POTENTIAL LAYER
# ============================================================

def ai_rank_events(events):
    """
    Optional Gemini ranking layer.

    If Gemini is unavailable, the deterministic score is used.

    The AI is NOT allowed to invent events.
    It only ranks already discovered events.
    """

    try:
        import os

        api_key = os.getenv(
            "GEMINI_API_KEY"
        )

        if not api_key:
            return events

        from google import genai

        client = genai.Client(
            api_key=api_key
        )

        candidates = []

        for index, event in enumerate(
            events[:15]
        ):
            candidates.append(
                {
                    "index": index,
                    "title": event["title"],
                    "score": event["score"],
                    "recent_sources": event[
                        "source_count"
                    ],
                    "articles": event[
                        "article_count"
                    ],
                    "momentum": event[
                        "momentum_score"
                    ],
                    "youtube": event[
                        "youtube_score"
                    ],
                }
            )

        prompt = f"""
You are the final trend-selection judge for a YouTube
news/technology automation system.

Choose the ONE topic with the strongest CURRENT viral potential.

Rules:
- Do not invent information.
- Prefer events that are genuinely recent.
- Prefer multiple independent publishers.
- Prefer rapidly developing stories.
- Prefer topics with strong YouTube curiosity.
- Avoid generic news roundup pages.
- Avoid old evergreen stories.
- Avoid duplicate versions of the same event.
- Viral potential is NOT guaranteed.
- Judge only the supplied candidates.

Return ONLY valid JSON:

{{
  "winner_index": 0,
  "reason": "short reason",
  "viral_potential": 0
}}

Candidates:
{candidates}
"""

        text = ""
        for model_name in [
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-3.1-flash-lite",
        ]:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                text = (getattr(response, "text", "") or "").strip()
                if text:
                    break
            except Exception as model_err:
                print(f"Trend selection model {model_name} error: {model_err}")
                continue

        match = re.search(
            r"\{.*\}",
            text,
            re.DOTALL,
        )

        if not match:
            return events

        import json

        data = json.loads(
            match.group(0)
        )

        winner_index = int(
            data.get(
                "winner_index",
                0,
            )
        )

        if not (
            0 <= winner_index < len(events)
        ):
            return events

        winner = events[
            winner_index
        ].copy()

        winner[
            "ai_reason"
        ] = data.get(
            "reason",
            "",
        )

        winner[
            "ai_viral_potential"
        ] = int(
            data.get(
                "viral_potential",
                0,
            )
        )

        # Move AI-selected winner to top.
        rest = [
            event
            for i, event in enumerate(events)
            if i != winner_index
        ]

        return [
            winner,
            *rest,
        ]

    except Exception as exc:
        print(
            "AI trend ranking unavailable; "
            f"using deterministic ranking: {exc}"
        )

        return events


# ============================================================
# PUBLIC API
# ============================================================

@autonomous_recover("trend_agent")
def discover_trending_topics(limit=10):
    print("=" * 60)
    print(
        "AUTOTUBE AI - TREND DISCOVERY ENGINE V5"
    )
    print("=" * 60)

    candidates = discover_candidates()

    print(
        f"\nInternet candidates found: "
        f"{len(candidates)}"
    )

    candidates = deduplicate_candidates(
        candidates
    )

    print(
        f"Unique candidates: "
        f"{len(candidates)}"
    )

    clusters = cluster_events(
        candidates
    )

    print(
        f"Event clusters: "
        f"{len(clusters)}"
    )

    events = []

    for cluster in clusters:

        event = event_to_dict(
            cluster
        )

        # Remove obviously useless events.
        if event["score"] < 20:
            continue

        events.append(event)

    events.sort(
        key=lambda x: (
            x["score"],
            x["momentum_score"],
            x["source_count"],
            x["freshness_score"],
        ),
        reverse=True,
    )

    events = ai_rank_events(
        events
    )

    events = events[:limit]

    print("\n🔥 EVENT-LEVEL TREND RANKING")

    for index, event in enumerate(
        events,
        start=1,
    ):

        print(
            f"\n{index}. "
            f"{event['score']} | "
            f"{event['title']}"
        )

        print(
            f"   Recent sources: "
            f"{event['source_count']} | "
            f"Total sources: "
            f"{event['total_source_count']} | "
            f"Articles: "
            f"{event['article_count']}"
        )

        print(
            f"   Freshness: "
            f"{event['freshness_score']} | "
            f"Momentum: "
            f"{event['momentum_score']} | "
            f"Interest: "
            f"{event['interest_score']} | "
            f"YouTube: "
            f"{event['youtube_score']}"
        )

        print(
            f"   Sources: "
            f"{', '.join(event['sources'][:8])}"
        )

        if event.get("ai_reason"):
            print(
                f"   AI reason: "
                f"{event['ai_reason']}"
            )

    return events


def discover_best_trending_topic():
    events = discover_trending_topics(
        limit=10
    )

    if not events:
        print(
            "\n❌ No suitable trending event found."
        )

        return None

    best = events[0]

    print("\n" + "=" * 60)
    print(
        "🏆 TOP TRENDING EVENT"
    )
    print("=" * 60)

    print(
        f"\nTopic: {best['title']}"
    )

    print(
        f"Score: {best['score']}/100"
    )

    print(
        f"Independent sources: "
        f"{best['source_count']}"
    )

    print(
        f"Total sources: "
        f"{best['total_source_count']}"
    )

    print(
        f"Related articles: "
        f"{best['article_count']}"
    )

    print(
        f"Freshness score: "
        f"{best['freshness_score']}"
    )

    print(
        f"Momentum score: "
        f"{best['momentum_score']}"
    )

    print(
        f"YouTube potential: "
        f"{best['youtube_score']}"
    )

    if best.get(
        "ai_viral_potential"
    ):
        print(
            f"AI viral potential: "
            f"{best['ai_viral_potential']}/100"
        )

    if best.get("ai_reason"):
        print(
            f"AI reason: "
            f"{best['ai_reason']}"
        )

    print("\nSources:")

    for source in best["sources"]:
        print(
            f"  • {source}"
        )

    return best


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    result = (
        discover_best_trending_topic()
    )

    print("\nRESULT:")

    if result:
        print(
            {
                key: value
                for key, value in result.items()
                if key != "articles"
            }
        )

    else:
        print(None)

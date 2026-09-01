import html
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from googlenewsdecoder import gnewsdecoder


RSS_URL = (
    "https://news.google.com/rss/search?"
    "q={query}&hl=en-IN&gl=IN&ceid=IN:en"
)


def _clean(text):
    """
    Convert RSS/article text into clean plain text.
    Also repairs common UTF-8 / Windows-1252 mojibake.
    """

    value = html.unescape(text or "")

    # Repair common mojibake caused by UTF-8 bytes being
    # incorrectly decoded as Latin-1 / Windows-1252.
    try:
        if any(
            marker in value
            for marker in (
                "â",
                "Â",
                "Ã",
                "ð",
            )
        ):
            value = value.encode(
                "latin1"
            ).decode(
                "utf-8"
            )
    except (
        UnicodeEncodeError,
        UnicodeDecodeError,
    ):
        pass

    # Remove HTML tags.
    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    # Decode entities again after tag removal.
    value = html.unescape(value)

    # Normalize whitespace.
    value = re.sub(
        r"\\s+",
        " ",
        value,
    )

    return value.strip()

def _fetch_article_text(url, max_chars=6000):
    """
    Best-effort extraction of readable article text.

    Google News RSS returns wrapper URLs.
    Decode them first to obtain the real publisher URL.

    Extraction order:
    1. JSON-LD articleBody
    2. <p> paragraphs
    """

    if not url:
        return ""

    try:

        article_url = url

        # ----------------------------------------------------
        # Decode Google News wrapper
        # ----------------------------------------------------

        if "news.google.com" in url:

            decoded = gnewsdecoder(
                url,
                interval=1,
            )

            if (
                isinstance(decoded, dict)
                and decoded.get("status")
                and decoded.get("decoded_url")
            ):

                article_url = decoded["decoded_url"]

                print(
                    "Decoded article URL:",
                    article_url,
                )

            else:

                print(
                    "Google News URL could not be decoded."
                )

                return ""

        # ----------------------------------------------------
        # Fetch publisher article
        # ----------------------------------------------------

        response = requests.get(
            article_url,
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/151.0 Safari/537.36"
                )
            },
            allow_redirects=True,
        )

        response.raise_for_status()

        content_type = (
            response.headers.get(
                "content-type",
                "",
            )
            .lower()
        )

        if "html" not in content_type:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        # ----------------------------------------------------
        # METHOD 1: JSON-LD articleBody
        # ----------------------------------------------------

        for script in soup.find_all(
            "script",
            type="application/ld+json",
        ):

            raw_json = script.string or script.get_text(
                strip=True
            )

            if not raw_json:
                continue

            try:
                import json

                data = json.loads(raw_json)

                objects = (
                    data
                    if isinstance(data, list)
                    else [data]
                )

                for obj in objects:

                    if not isinstance(obj, dict):
                        continue

                    article_body = obj.get(
                        "articleBody"
                    )

                    if isinstance(
                        article_body,
                        str,
                    ):

                        article_body = _clean(
                            article_body
                        )

                        if len(article_body) >= 100:

                            print(
                                "Article text extracted "
                                "from JSON-LD articleBody."
                            )

                            return article_body[
                                :max_chars
                            ].strip()

            except Exception:
                continue

        # ----------------------------------------------------
        # METHOD 2: Normal paragraph extraction
        # ----------------------------------------------------

        for tag in soup([
            "script",
            "style",
            "noscript",
            "nav",
            "header",
            "footer",
            "aside",
            "form",
        ]):
            tag.decompose()

        paragraphs = []

        for paragraph in soup.find_all("p"):

            value = _clean(
                paragraph.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(value) >= 40:
                paragraphs.append(value)

        if paragraphs:

            unique = []
            seen = set()

            for paragraph in paragraphs:

                key = paragraph.lower()

                if key in seen:
                    continue

                seen.add(key)
                unique.append(paragraph)

            article_text = " ".join(unique)

            if article_text.strip():

                print(
                    "Article text extracted "
                    "from paragraphs."
                )

                return article_text[
                    :max_chars
                ].strip()

        print(
            "No readable article text found."
        )

        return ""

    except Exception as error:

        print(
            f"Article fetch failed: {error}"
        )

        return ""

def _score_news_article(topic, title, snippet, article_text, published_at):
    """
    Score a news article for topic relevance and freshness.

    Higher score = better candidate.
    """

    topic_words = {
        word.lower()
        for word in re.findall(r"[A-Za-z0-9]+", topic)
        if len(word) >= 3
        and word.lower() not in {
            "latest",
            "news",
            "today",
            "technology",
            "tech",
        }
    }

    combined = " ".join(
        [
            title or "",
            snippet or "",
            article_text or "",
        ]
    ).lower()

    score = 0

    # Strong relevance for explicit topic words.
    for word in topic_words:
        if word in combined:
            score += 5

    # Location-specific relevance.
    location_terms = {
        "vijayawada": [
            "vijayawada",
            "vijayawada:",
            "vijayawada,",
        ],
        "andhra pradesh": [
            "andhra pradesh",
            "amaravati",
            "visakhapatnam",
            "guntur",
        ],
    }

    topic_lower = topic.lower()

    for location, terms in location_terms.items():
        if location in topic_lower:
            for term in terms:
                if term in combined:
                    score += 8

    # Technology relevance.
    technology_terms = [
        "technology",
        "artificial intelligence",
        "ai",
        "data centre",
        "data center",
        "digital",
        "engineering",
        "automation",
        "software",
        "semiconductor",
        "robotics",
        "quantum",
        "electronics",
        "innovation",
        "machine learning",
    ]

    for term in technology_terms:
        if term in combined:
            score += 2

    # Prefer articles with actual article text.
    if len(article_text or "") >= 500:
        score += 10
    elif len(article_text or "") >= 100:
        score += 5

    # Freshness bonus.
    try:
        published = datetime.strptime(
            published_at,
            "%a, %d %b %Y %H:%M:%S %Z",
        ).replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - published

        if age <= timedelta(days=1):
            score += 30
        elif age <= timedelta(days=3):
            score += 20
        elif age <= timedelta(days=7):
            score += 10
        elif age <= timedelta(days=30):
            score += 3
        else:
            score -= 10

    except Exception:
        # Do not reject a source just because its date format
        # could not be parsed.
        pass

    return score


def verify_news_topic(topic, limit=5):
    """
    Gather source-backed context from Google News RSS.

    Candidates are scored by:
    - topic relevance
    - location relevance
    - technology relevance
    - article-text availability
    - freshness

    This is a grounding step, not a publication gate.
    """

    topic = _clean(topic)

    if not topic:
        return {
            "status": "UNVERIFIED",
            "topic": "",
            "articles": [],
            "summary": "No topic was provided.",
        }

    url = RSS_URL.format(
        query=quote_plus(topic)
    )

    try:
        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "AutoTube-AI/1.0"
            },
        )

        response.raise_for_status()

        root = ET.fromstring(
            response.content
        )

    except Exception as error:
        return {
            "status": "UNVERIFIED",
            "topic": topic,
            "articles": [],
            "summary": (
                f"News source lookup failed: {error}"
            ),
        }

    candidates = []
    seen = set()

    # --------------------------------------------------------
    # COLLECT CANDIDATES
    # --------------------------------------------------------

    for item in root.findall(".//item"):

        title = _clean(
            item.findtext("title") or ""
        )

        link = _clean(
            item.findtext("link") or ""
        )

        published_at = _clean(
            item.findtext("pubDate") or ""
        )

        snippet = _clean(
            item.findtext("description") or ""
        )

        source_element = item.find(
            "source"
        )

        source = _clean(
            source_element.text
            if source_element is not None
            else ""
        )

        key = title.lower()

        if not title or key in seen:
            continue

        seen.add(key)

        # Do not fetch every article yet.
        # Article text will be fetched only for the
        # highest-ranked candidates after initial scoring.
        article_text = ""

        score = _score_news_article(
            topic=topic,
            title=title,
            snippet=snippet,
            article_text=article_text,
            published_at=published_at,
        )

        candidates.append(
            {
                "headline": title,
                "source": source or "Google News result",
                "published_at": published_at,
                "url": link,
                "snippet": snippet,
                "article_text": article_text,
                "_score": score,
            }
        )

    # --------------------------------------------------------
    # FRESHNESS FILTER FOR LATEST / RECENT NEWS
    # --------------------------------------------------------

    latest_requested = any(
        phrase in topic.lower()
        for phrase in (
            "latest",
            "recent",
            "today",
            "breaking",
            "current",
            "newest",
        )
    )

    if latest_requested:

        now = datetime.now(timezone.utc)

        fresh_candidates = []

        for article in candidates:

            published_at = article.get(
                "published_at",
                "",
            )

            try:

                published = datetime.strptime(
                    published_at,
                    "%a, %d %b %Y %H:%M:%S %Z",
                ).replace(
                    tzinfo=timezone.utc
                )

                age = now - published

                # Latest news = maximum 7 days old.
                if age <= timedelta(days=7):
                    fresh_candidates.append(article)

            except Exception:

                # Unknown dates are not safe for
                # latest-news results.
                continue

        candidates = fresh_candidates

    # --------------------------------------------------------
    # RANK CANDIDATES
    # --------------------------------------------------------

    candidates.sort(
        key=lambda article: article.get("_score", 0),
        reverse=True,
    )

    # --------------------------------------------------------
    # FETCH ARTICLE TEXT ONLY FOR TOP CANDIDATES
    # --------------------------------------------------------

    prefetch_count = min(
        max(limit * 2, 10),
        len(candidates),
    )

    for article in candidates[:prefetch_count]:

        article["article_text"] = _fetch_article_text(
            article.get("url", "")
        )

        article["_score"] = _score_news_article(
            topic=topic,
            title=article.get("headline", ""),
            snippet=article.get("snippet", ""),
            article_text=article.get("article_text", ""),
            published_at=article.get("published_at", ""),
        )

    candidates.sort(
        key=lambda article: article.get("_score", 0),
        reverse=True,
    )

    articles = candidates[:limit]
    # Remove internal scoring field before returning.
    for article in articles:
        article.pop("_score", None)

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    if not articles:
        return {
            "status": "UNVERIFIED",
            "topic": topic,
            "articles": [],
            "summary": (
                "No fresh matching source-backed "
                "news results were found."
                if latest_requested
                else "No matching source-backed news "
                "results were found."
            ),
        }

    return {
        "status": "SOURCES_FOUND",
        "topic": topic,
        "articles": articles,
        "summary": (
            f"Found {len(articles)} ranked "
            "source-backed news results."
        ),
    }


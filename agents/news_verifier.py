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
            timeout=6,
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
            "recent",
            "breaking",
            "current",
            "newest",
            "topic",
            "your",
            "video",
            "create",
            "make",
            "about",
            "please",
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
    # FETCH ARTICLE TEXT ONLY FOR TOP CANDIDATES (PARALLEL)
    # --------------------------------------------------------

    prefetch_count = min(
        max(limit, 4),
        len(candidates),
    )

    from concurrent.futures import ThreadPoolExecutor

    target_articles = candidates[:prefetch_count]

    def _fetch_and_score(article):
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
        return article

    if target_articles:
        with ThreadPoolExecutor(max_workers=min(4, len(target_articles))) as executor:
            list(executor.map(_fetch_and_score, target_articles))

    candidates.sort(
        key=lambda article: article.get("_score", 0),
        reverse=True,
    )

    # --------------------------------------------------------
    # MINIMUM RELEVANCE GATE
    # --------------------------------------------------------
    #
    # Google News may return articles because a generic word
    # appears in the headline/snippet. That is not sufficient
    # evidence that the article is actually about the topic.
    #
    # Require at least one meaningful topic word to appear in
    # the article content before returning SOURCES_FOUND.
    # --------------------------------------------------------

    verification_words = {
        word.lower()
        for word in re.findall(
            r"[A-Za-z0-9]+",
            topic,
        )
        if len(word) >= 3
        and word.lower() not in {
            "latest",
            "news",
            "today",
            "technology",
            "tech",
            "recent",
            "breaking",
            "current",
            "newest",
            "topic",
            "your",
            "video",
            "create",
            "make",
            "about",
            "please",
        }
    }

    if verification_words:

        relevant_candidates = []

        for article in candidates:

            combined = " ".join(
                [
                    article.get("headline", ""),
                    article.get("snippet", ""),
                    article.get("article_text", ""),
                ]
            ).lower()

            matched_words = {
                word
                for word in verification_words
                if word in combined
            }

            article_score = article.get(
                "_score",
                0,
            )

            # Accept the article when either:
            #
            # 1. A meaningful topic word is directly found
            #    in the article content, OR
            #
            # 2. The article has a strong overall relevance
            #    score from topic/location/technology/freshness.
            #
            # This prevents false positives such as
            # "YOUR_TOPIC", while allowing legitimate articles
            # whose publisher text does not repeat the exact
            # location/topic wording.
            if matched_words or article_score >= 40:

                article["_matched_topic_words"] = len(
                    matched_words
                )

                relevant_candidates.append(
                    article
                )

        candidates = relevant_candidates

    else:
        # A query containing only generic words is not specific
        # enough to safely verify as news.
        candidates = []

    articles = candidates[:limit]

    # Remove internal scoring fields before returning.
    for article in articles:
        article.pop("_score", None)
        article.pop("_matched_topic_words", None)

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


# ============================================================
# PRE-PUBLISH CONTENT SAFETY & POLICY MODERATION
# ============================================================

_HEURISTIC_UNSAFE_PATTERNS = {
    "hate_speech": [
        r"\b(racial slur|n-word|white supremacy|hate speech|subhuman)\b",
        r"\b(kill all|death to|wipe out)\s+(jews|muslims|christians|hindus|blacks|whites|asians|immigrants)\b",
        r"\b(genocide|ethnic cleansing)\s+(advocacy|celebration)\b",
    ],
    "violence_harm": [
        r"\b(pipe\s+bomb|bomb\s+tutorial|bomb\s+making|weapons?\s+tutorial)\b",
        r"\b(how to\s+)?(make|build|assemble|craft)\s+(a\s+)?(pipe\s+)?bomb\b",
        r"\b(how to\s+)?(commit\s+)?suicide\b",
        r"\b(assassinate|assassination|school\s+shooting|mass\s+shooting|attack\s+schools?|attack\s+civilians?)\b",
        r"\b(build|manufacture|make)\s+(an\s+)?explosive\b",
        r"\b(manufacture ricin|poisoning water supply|mass casualty)\b",
    ],
    "sexual_content": [
        r"\b(hardcore porn|explicit sex|child exploitation|nonconsensual sexual|csam)\b",
    ],
    "dangerous_content": [
        r"\b(ransomware tutorial|ddos attack tool|how to hack credit cards|carding tutorial|malware payload tutorial)\b",
    ],
}


def _heuristic_safety_check(text, topic=None):
    """
    Fast offline heuristic moderation check using regex safety rules.
    """
    combined = f"{topic or ''} {text or ''}".lower()

    for category, patterns in _HEURISTIC_UNSAFE_PATTERNS.items():
        for pat in patterns:
            match = re.search(pat, combined, flags=re.IGNORECASE)
            if match:
                return {
                    "safe": False,
                    "category": category,
                    "confidence": 0.95,
                    "reason": f"Content violates safety policy ({category}): matched '{match.group(0)}'",
                    "checked_by": "heuristic",
                }

    return {
        "safe": True,
        "category": "none",
        "confidence": 0.85,
        "reason": "Passed heuristic policy and safety check",
        "checked_by": "heuristic",
    }


def verify_content_safety_and_policy(text, topic=None):
    """
    Pre-Publish Safety & Policy Filter.
    Validates script or topic against YouTube Community Guidelines:
    - Toxicity & Hate Speech
    - Harassment & Cyberbullying
    - Graphic Violence & Self-Harm
    - Sexually Explicit Material
    - Dangerous & Illegal Activities

    Uses fast Gemini evaluation with transparent heuristic fallback.
    """
    import os
    import json
    from dotenv import load_dotenv

    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")

    if not text and not topic:
        return {
            "safe": True,
            "category": "none",
            "confidence": 1.0,
            "reason": "Empty content is safe by default",
            "checked_by": "empty_bypass",
        }

    # 1. Try Gemini Content Moderation
    if api_key:
        try:
            from google import genai

            client = genai.Client(api_key=api_key)

            prompt = f"""You are an elite YouTube content moderation and safety officer.
Analyze the following script/news content against YouTube Community Guidelines & Terms of Service:
- Hate Speech & Toxicity (slurs, promoting violence/hatred against protected classes)
- Harassment & Cyberbullying
- Graphic Violence, Terrorist Propaganda, Suicide/Self-Harm
- Sexually Explicit or Inappropriate Content
- Dangerous Content (bomb-making, illegal weapons, malicious hacking, dangerous frauds)

TOPIC: {topic or 'N/A'}
CONTENT:
{(text or '')[:3000]}

Return ONLY a JSON object:
{{
  "safe": true,
  "category": "none",
  "confidence": 0.95,
  "reason": "Short 1-sentence explanation"
}}
If unsafe, set safe: false and category to one of ["hate_speech", "violence", "toxicity", "sexual_content", "dangerous_content"].
"""
            models_to_try = [
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-1.5-flash",
                "gemini-3.5-flash",
                "gemini-flash-lite-latest",
            ]

            for m in models_to_try:
                try:
                    resp = client.models.generate_content(
                        model=m,
                        contents=prompt,
                    )
                    raw = getattr(resp, "text", "")
                    if raw:
                        clean = raw.strip()
                        if "```json" in clean:
                            clean = clean.split("```json")[1].split("```")[0].strip()
                        elif "```" in clean:
                            clean = clean.split("```")[1].split("```")[0].strip()

                        data = json.loads(clean)
                        return {
                            "safe": bool(data.get("safe", True)),
                            "category": str(data.get("category", "none")),
                            "confidence": float(data.get("confidence", 0.9)),
                            "reason": str(data.get("reason", "Verified by Gemini AI moderation")),
                            "checked_by": "gemini",
                        }
                except Exception:
                    continue

        except Exception as exc:
            print(f"⚠️ Gemini moderation check exception: {exc}")

    # 2. Heuristic Moderation Fallback
    return _heuristic_safety_check(text, topic=topic)


# ============================================================
# VISUAL ASSET VALIDATOR & WATERMARK FILTER
# ============================================================

def validate_visual_assets(assets_dir=None, fallback_dir=None):
    """
    Validates all visual image assets in the assets directory:
    - Tests for file corruption (zero-byte or invalid image headers).
    - Checks minimum resolution (>= 200x200).
    - Checks for stock watermark signatures or overlay anomalies.
    - Automatically drops and replaces corrupt/bad images with clean
      images from assets/fallback/.
    """
    import shutil
    from pathlib import Path
    from PIL import Image

    root = Path(__file__).resolve().parent.parent
    a_dir = Path(assets_dir) if assets_dir else (root / "assets")
    f_dir = Path(fallback_dir) if fallback_dir else (root / "assets" / "fallback")

    if not a_dir.exists():
        return {
            "valid": False,
            "total_inspected": 0,
            "corrupt_count": 0,
            "watermarked_count": 0,
            "replaced": [],
            "details": {},
        }

    # Discover fallback candidates
    fallbacks = []
    if f_dir.exists():
        fallbacks = sorted([
            f for f in f_dir.iterdir()
            if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and f.stat().st_size > 1024
        ])

    image_files = sorted([
        f for f in a_dir.iterdir()
        if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        and not f.name.startswith("contact_sheet")
    ])

    total_inspected = len(image_files)
    corrupt_count = 0
    watermarked_count = 0
    replaced = []
    details = {}
    fallback_idx = 0

    stock_watermark_keywords = [
        "watermark",
        "shutterstock",
        "gettyimages",
        "istock",
        "alamy",
        "dreamstime",
        "depositphotos",
        "123rf",
    ]

    for img_path in image_files:
        filename = img_path.name
        is_corrupt = False
        is_watermarked = False
        reason = "Clean"

        # Check 1: File size
        if img_path.stat().st_size < 1024:
            is_corrupt = True
            reason = "File size below 1KB (empty or truncated)"

        # Check 2: Header integrity & decodability
        if not is_corrupt:
            try:
                with Image.open(img_path) as img:
                    img.verify()
                # Reopen to check dimensions and color
                with Image.open(img_path) as img:
                    w, h = img.size
                    if w < 200 or h < 200:
                        is_corrupt = True
                        reason = f"Resolution too low ({w}x{h})"

                    # Check 3: Watermark keywords in EXIF / Metadata
                    info_str = str(getattr(img, "info", {})).lower()
                    if any(kw in info_str for kw in stock_watermark_keywords):
                        is_watermarked = True
                        reason = "Stock agency watermark detected in image metadata"

            except Exception as err:
                is_corrupt = True
                reason = f"Image decode failure: {err}"

        # Check 4: Watermark keywords in filename
        if not is_corrupt and not is_watermarked:
            if any(kw in filename.lower() for kw in stock_watermark_keywords):
                is_watermarked = True
                reason = "Watermark keyword found in filename"

        # Replacement action if defective
        if is_corrupt or is_watermarked:
            if is_corrupt:
                corrupt_count += 1
            if is_watermarked:
                watermarked_count += 1

            if fallbacks:
                clean_fb = fallbacks[fallback_idx % len(fallbacks)]
                fallback_idx += 1
                try:
                    shutil.copy2(clean_fb, img_path)
                    replaced.append(filename)
                    print(f"🛡️ [Asset Safety] Replaced defective {filename} ({reason}) with fallback {clean_fb.name}")
                    reason += f" -> replaced with {clean_fb.name}"
                except Exception as cp_err:
                    print(f"⚠️ Failed to copy fallback over {filename}: {cp_err}")

        details[filename] = {
            "status": "REPLACED" if filename in replaced else ("DEFECTIVE" if (is_corrupt or is_watermarked) else "PASS"),
            "reason": reason,
        }

    return {
        "valid": len(replaced) == 0 and corrupt_count == 0 and watermarked_count == 0,
        "total_inspected": total_inspected,
        "corrupt_count": corrupt_count,
        "watermarked_count": watermarked_count,
        "replaced": replaced,
        "details": details,
    }



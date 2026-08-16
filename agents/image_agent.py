"""
AutoTube AI - Image Agent
News-relevant image downloader.
Wikimedia Commons + Bing Images fallback.
Strict relevance filtering.
"""

import os
import re
import time
import hashlib
import html
import json
from pathlib import Path
from urllib.parse import quote_plus

import requests
from PIL import Image


# ============================================================
# CONFIG
# ============================================================

ASSETS_DIR = Path("assets")

TARGET_IMAGES = 12

MIN_WIDTH = 500
MIN_HEIGHT = 300

MAX_FILE_SIZE = 12 * 1024 * 1024

REQUEST_TIMEOUT = 20

MAX_WIKIMEDIA_RESULTS = 20
MAX_BING_RESULTS = 40

WIKIMEDIA_DELAY = 3


# ============================================================
# SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "AutoTubeAI/1.0 "
            "(news video project; contact: autotube-ai)"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
)


# ============================================================
# HELPERS
# ============================================================

def line():
    print("=" * 60)


def clean_text(text):

    if not text:
        return ""

    text = html.unescape(str(text))

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def normalize_text(text):

    text = clean_text(text).lower()

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# STORY TYPE
# ============================================================

def detect_story(topic):

    text = normalize_text(topic)

    if any(
        word in text
        for word in [
            "hormuz",
            "iran",
            "uae",
            "adnoc",
            "vessel",
            "tanker",
            "shipping",
        ]
    ):
        return "HORMUZ"

    if any(
        word in text
        for word in [
            "supreme court",
            "chief justice",
            "justice",
            "lawyer",
            "court",
        ]
    ):
        return "LEGAL"

    if any(
        word in text
        for word in [
            "india",
            "indian",
        ]
    ):
        return "INDIA"

    return "GENERAL"


# ============================================================
# QUERY BUILDER
# ============================================================

def build_queries(topic):

    text = normalize_text(topic)

    story = detect_story(topic)

    queries = []

    if story == "HORMUZ":

        queries = [
            "Strait of Hormuz",
            "Strait of Hormuz ships",
            "Strait of Hormuz tanker",
            "Strait of Hormuz oil tanker",
            "Hormuz maritime shipping",
            "UAE Iran Strait Hormuz",
            "ADNOC UAE oil tanker",
            "ADNOC vessel UAE",
            "Iran UAE shipping",
            "Persian Gulf tanker",
            "Hormuz satellite map",
            "Hormuz shipping route",
        ]

    elif story == "LEGAL":

        queries = [
            "Supreme Court of India",
            "Chief Justice India",
            "Indian lawyers court",
            "Indian judiciary",
            "Supreme Court India lawyers",
        ]

    elif story == "INDIA":

        queries = [
            "India news",
            "Indian government",
            "India parliament",
            "India current affairs",
        ]

    else:

        words = [
            word
            for word in text.split()
            if len(word) >= 4
        ]

        queries = [
            " ".join(words[:8])
        ]

    final = []

    for query in queries:

        if query not in final:

            final.append(query)

    return final


# ============================================================
# WIKIMEDIA
# ============================================================

def search_wikimedia(query):

    url = "https://commons.wikimedia.org/w/api.php"

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": MAX_WIKIMEDIA_RESULTS,
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "iiurlwidth": 1600,
    }

    try:

        response = SESSION.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        data = response.json()

    except Exception as exc:

        print(
            f"Wikimedia search failed: {exc}"
        )

        return []

    pages = (
        data
        .get("query", {})
        .get("pages", {})
    )

    results = []

    for page in pages.values():

        title = clean_text(
            page.get(
                "title",
                ""
            )
        )

        info_list = page.get(
            "imageinfo",
            []
        )

        if not info_list:
            continue

        info = info_list[0]

        image_url = (
            info.get("thumburl")
            or info.get("url")
        )

        width = info.get(
            "width",
            0
        )

        height = info.get(
            "height",
            0
        )

        mime = info.get(
            "mime",
            ""
        )

        if not image_url:
            continue

        if not mime.startswith("image/"):
            continue

        if width < MIN_WIDTH:
            continue

        if height < MIN_HEIGHT:
            continue

        results.append(
            {
                "image_url": image_url,
                "page_url": (
                    "https://commons.wikimedia.org/wiki/"
                    + quote_plus(
                        title.replace(
                            " ",
                            "_"
                        )
                    )
                ),
                "title": title,
                "source": "Wikimedia Commons",
            }
        )

    return results


# ============================================================
# BING
# ============================================================

def search_bing(query):

    url = (
        "https://www.bing.com/images/async"
        f"?q={quote_plus(query)}"
        "&first=0"
        f"&count={MAX_BING_RESULTS}"
        "&adlt=off"
    )

    try:

        response = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

    except Exception as exc:

        print(
            f"Bing search failed: {exc}"
        )

        return []

    pattern = re.compile(
        r'<a[^>]+class="[^"]*iusc[^"]*"[^>]+m="([^"]+)"',
        re.IGNORECASE
    )

    matches = pattern.findall(
        response.text
    )

    results = []

    for raw in matches:

        try:

            raw = html.unescape(
                raw
            )

            data = json.loads(
                raw
            )

        except Exception:

            continue

        image_url = (
            data.get("murl")
            or data.get("turl")
        )

        if not image_url:
            continue

        results.append(
            {
                "image_url": image_url,
                "page_url": data.get(
                    "purl",
                    ""
                ),
                "title": clean_text(
                    data.get(
                        "t",
                        ""
                    )
                    or data.get(
                        "desc",
                        ""
                    )
                ),
                "source": "Bing Images",
            }
        )

    return results


# ============================================================
# POSITIVE KEYWORDS
# ============================================================

HORMUZ_POSITIVE = [
    "hormuz",
    "strait of hormuz",
    "tanker",
    "oil tanker",
    "oil ship",
    "vessel",
    "ship",
    "shipping",
    "maritime",
    "waterway",
    "persian gulf",
    "gulf of oman",
    "adnoc",
    "abu dhabi",
    "uae",
    "united arab emirates",
    "iran",
    "iranian",
    "naval",
    "port",
    "cargo",
]


# ============================================================
# NEGATIVE KEYWORDS
# ============================================================

HORMUZ_NEGATIVE = [
    "supreme court",
    "court of india",
    "chief justice",
    "justice surya",
    "surya kant",
    "lawyer",
    "lawyers",
    "advocate",
    "advocates",
    "freedom struggle",
    "freedom movement",
    "independence movement",
    "independence day",
    "mahatma gandhi",
    "gandhi",
    "nehru",
    "ambedkar",
    "patel",
    "parliament of india",
    "lok sabha",
    "rajya sabha",
    "cricket",
    "bollywood",
]


# ============================================================
# RELEVANCE SCORE
# ============================================================

def score_candidate(candidate, topic):

    story = detect_story(topic)

    title = normalize_text(
        candidate.get(
            "title",
            ""
        )
    )

    page = normalize_text(
        candidate.get(
            "page_url",
            ""
        )
    )

    url = normalize_text(
        candidate.get(
            "image_url",
            ""
        )
    )

    combined = (
        title
        + " "
        + page
        + " "
        + url
    )

    score = 0

    if story == "HORMUZ":

        # Strong keywords
        for word in HORMUZ_POSITIVE:

            if word in title:
                score += 10

            elif word in page:
                score += 5

            elif word in url:
                score += 2

        # Strong combinations
        if (
            "hormuz" in combined
            and "tanker" in combined
        ):
            score += 25

        if (
            "hormuz" in combined
            and "ship" in combined
        ):
            score += 20

        if (
            "hormuz" in combined
            and "vessel" in combined
        ):
            score += 20

        if (
            "uae" in combined
            and "iran" in combined
        ):
            score += 20

        if (
            "adnoc" in combined
            and "tanker" in combined
        ):
            score += 25

        if (
            "adnoc" in combined
            and "vessel" in combined
        ):
            score += 25

        if (
            "persian gulf" in combined
            and "ship" in combined
        ):
            score += 15

        # Negative penalty
        for word in HORMUZ_NEGATIVE:

            if word in combined:

                score -= 60

    else:

        topic_words = [
            word
            for word in normalize_text(topic).split()
            if len(word) >= 4
        ]

        for word in topic_words:

            if word in title:
                score += 8

            elif word in page:
                score += 4

            elif word in url:
                score += 2

    if (
        candidate.get("source")
        == "Wikimedia Commons"
    ):
        score += 5

    return score


# ============================================================
# RELEVANCE FILTER
# ============================================================

def is_relevant(candidate, topic):

    story = detect_story(topic)

    title = normalize_text(
        candidate.get(
            "title",
            ""
        )
    )

    page = normalize_text(
        candidate.get(
            "page_url",
            ""
        )
    )

    url = normalize_text(
        candidate.get(
            "image_url",
            ""
        )
    )

    combined = (
        title
        + " "
        + page
        + " "
        + url
    )

    if story == "HORMUZ":

        # NEVER allow these unrelated visuals
        for bad in HORMUZ_NEGATIVE:

            if bad in combined:

                return False

        positive_hits = 0

        for word in HORMUZ_POSITIVE:

            if word in combined:

                positive_hits += 1

        # Hormuz itself is very strong
        if "strait of hormuz" in combined:

            return True

        if "hormuz" in combined:

            if positive_hits >= 2:

                return True

        # ADNOC + maritime visual
        if "adnoc" in combined:

            if any(
                word in combined
                for word in [
                    "ship",
                    "vessel",
                    "tanker",
                    "oil",
                    "marine",
                    "maritime",
                ]
            ):

                return True

        # UAE + Iran + maritime
        if (
            (
                "uae" in combined
                or "abu dhabi" in combined
            )
            and (
                "iran" in combined
                or "iranian" in combined
            )
            and any(
                word in combined
                for word in [
                    "ship",
                    "vessel",
                    "tanker",
                    "maritime",
                    "shipping",
                    "waterway",
                ]
            )
        ):

            return True

        # Generic tanker is allowed only if page/title
        # has Gulf/Hormuz/UAE/Iran context.
        if (
            "tanker" in combined
            and any(
                word in combined
                for word in [
                    "gulf",
                    "hormuz",
                    "uae",
                    "iran",
                    "abu dhabi",
                ]
            )
        ):

            return True

        return False

    score = score_candidate(
        candidate,
        topic
    )

    return score >= 15


# ============================================================
# DOWNLOAD
# ============================================================

def download_image(
    candidate,
    destination
):

    image_url = candidate.get(
        "image_url",
        ""
    )

    if not image_url:
        return False

    try:

        response = SESSION.get(
            image_url,
            timeout=REQUEST_TIMEOUT,
            stream=True
        )

        response.raise_for_status()

        temp = destination.with_suffix(
            ".tmp"
        )

        total = 0

        with open(
            temp,
            "wb"
        ) as file:

            for chunk in response.iter_content(
                chunk_size=65536
            ):

                if not chunk:
                    continue

                total += len(chunk)

                if total > MAX_FILE_SIZE:

                    temp.unlink(
                        missing_ok=True
                    )

                    return False

                file.write(
                    chunk
                )

        try:

            with Image.open(
                temp
            ) as image:

                image.verify()

        except Exception:

            temp.unlink(
                missing_ok=True
            )

            return False

        try:

            with Image.open(
                temp
            ) as image:

                width, height = image.size

                if width < MIN_WIDTH:
                    temp.unlink(
                        missing_ok=True
                    )
                    return False

                if height < MIN_HEIGHT:
                    temp.unlink(
                        missing_ok=True
                    )
                    return False

                image = image.convert(
                    "RGB"
                )

                image.save(
                    destination,
                    "JPEG",
                    quality=90
                )

        except Exception:

            temp.unlink(
                missing_ok=True
            )

            return False

        temp.unlink(
            missing_ok=True
        )

        return True

    except Exception:

        return False


# ============================================================
# HASH
# ============================================================

def image_hash(path):

    try:

        with Image.open(
            path
        ) as image:

            image = image.convert(
                "RGB"
            )

            image = image.resize(
                (32, 32)
            )

            return hashlib.md5(
                image.tobytes()
            ).hexdigest()

    except Exception:

        return None


# ============================================================
# CLEAN ASSETS
# ============================================================

def clean_assets():

    ASSETS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    for file in ASSETS_DIR.iterdir():

        if file.is_file():

            try:
                file.unlink()
            except Exception:
                pass


# ============================================================
# MAIN
# ============================================================

def download_images(topic):

    line()

    print(
        "AI IMAGE SEARCH STARTED"
    )

    line()

    print()
    print("Topic:")
    print(topic)

    print()
    print(
        "Story type:",
        detect_story(topic)
    )

    clean_assets()

    queries = build_queries(
        topic
    )

    print()
    line()

    print(
        f"TOTAL SEARCHES: {len(queries)}"
    )

    line()

    for i, query in enumerate(
        queries,
        1
    ):

        print(
            f"{i}. {query}"
        )

    candidates = []

    seen = set()

    # ========================================================
    # SEARCH
    # ========================================================

    for i, query in enumerate(
        queries,
        1
    ):

        print()
        line()

        print(
            f"SEARCHING {i}/{len(queries)}"
        )

        print(query)

        line()

        # Wikimedia
        wikimedia = search_wikimedia(
            query
        )

        print(
            f"Wikimedia results: "
            f"{len(wikimedia)}"
        )

        for candidate in wikimedia:

            url = candidate.get(
                "image_url",
                ""
            )

            key = url.split(
                "?",
                1
            )[0]

            if not key or key in seen:
                continue

            seen.add(key)

            if is_relevant(
                candidate,
                topic
            ):

                candidate["score"] = score_candidate(
                    candidate,
                    topic
                )

                candidates.append(
                    candidate
                )

        # Bing
        bing = search_bing(
            query
        )

        print(
            f"Bing results: "
            f"{len(bing)}"
        )

        for candidate in bing:

            url = candidate.get(
                "image_url",
                ""
            )

            key = url.split(
                "?",
                1
            )[0]

            if not key or key in seen:
                continue

            seen.add(key)

            if is_relevant(
                candidate,
                topic
            ):

                candidate["score"] = score_candidate(
                    candidate,
                    topic
                )

                candidates.append(
                    candidate
                )

        # Small delay
        time.sleep(
            WIKIMEDIA_DELAY
        )

    # ========================================================
    # SORT
    # ========================================================

    candidates.sort(
        key=lambda x: x.get(
            "score",
            0
        ),
        reverse=True
    )

    print()
    line()

    print(
        f"RELEVANT CANDIDATES: "
        f"{len(candidates)}"
    )

    line()

    if not candidates:

        print()
        print(
            "NO RELEVANT IMAGE CANDIDATES FOUND."
        )

        print(
            "No unrelated fallback images will be used."
        )

        return 0

    # ========================================================
    # TOP CANDIDATES
    # ========================================================

    print()
    print(
        "TOP CANDIDATES:"
    )

    for i, candidate in enumerate(
        candidates[:25],
        1
    ):

        print(
            f"{i:02d}. "
            f"Score={candidate.get('score', 0):03d} | "
            f"{candidate.get('source', '')} | "
            f"{candidate.get('title', '')[:120]}"
        )

    # ========================================================
    # DOWNLOAD
    # ========================================================

    print()
    line()

    print(
        "DOWNLOADING IMAGES"
    )

    line()

    count = 0

    used_hashes = set()

    used_urls = set()

    for candidate in candidates:

        if count >= TARGET_IMAGES:
            break

        url = candidate.get(
            "image_url",
            ""
        )

        if url in used_urls:
            continue

        used_urls.add(
            url
        )

        number = count + 1

        destination = (
            ASSETS_DIR
            / f"{number}.jpg"
        )

        print()
        print(
            f"Trying image {number}"
        )

        print(
            f"Score: "
            f"{candidate.get('score', 0)}"
        )

        print(
            f"Source: "
            f"{candidate.get('source', '')}"
        )

        print(
            f"Title: "
            f"{candidate.get('title', '')[:150]}"
        )

        success = download_image(
            candidate,
            destination
        )

        if not success:

            print(
                "Skipped: download failed"
            )

            destination.unlink(
                missing_ok=True
            )

            continue

        file_hash = image_hash(
            destination
        )

        if not file_hash:

            destination.unlink(
                missing_ok=True
            )

            continue

        if file_hash in used_hashes:

            print(
                "Skipped: duplicate"
            )

            destination.unlink(
                missing_ok=True
            )

            continue

        used_hashes.add(
            file_hash
        )

        with Image.open(
            destination
        ) as image:

            print(
                f"OK - Image {number} saved "
                f"{image.size[0]}x{image.size[1]}"
            )

        count += 1

    # ========================================================
    # FINAL
    # ========================================================

    print()
    line()

    print(
        f"FINAL IMAGES: {count}"
    )

    line()

    if count:

        print()
        print(
            f"Images saved in: "
            f"{ASSETS_DIR.resolve()}"
        )

        print()
        print(
            "IMAGE PIPELINE COMPLETED"
        )

    else:

        print()
        print(
            "No usable images downloaded."
        )

    return count


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    test_topic = (
        "UAE says Iran attacked ADNOC vessel "
        "in Hormuz, urges waterway's reopening - Reuters"
    )

    result = download_images(
        test_topic
    )

    print()
    print(
        f"Returned image count: {result}"
    )
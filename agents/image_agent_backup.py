"""
AutoTube AI - Image Agent
=========================

Purpose:
    Find highly relevant news images for a video topic.

Important:
    - No Gemini
    - No icrawler
    - Uses Bing Images metadata
    - Search query is NEVER used as evidence of relevance
    - Strong entity/person matching
    - Rejects unrelated results aggressively
    - Downloads and validates images locally
    - Removes visual duplicates

Function:
    download_images(topic) -> int

Output:
    assets/1.jpg
    assets/2.jpg
    ...
"""

import os
import re
import time
import hashlib
import html
import json
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests
from PIL import Image, ImageStat


# ============================================================
# CONFIG
# ============================================================

ASSETS_DIR = Path("assets")

TARGET_IMAGES = 12

RESULTS_PER_QUERY = 35

MIN_RELEVANCE_SCORE = 12

MIN_WIDTH = 500
MIN_HEIGHT = 300

MAX_FILE_SIZE = 12 * 1024 * 1024

REQUEST_TIMEOUT = 15

SEARCH_DELAY = 0.4

MAX_CANDIDATES_TO_DOWNLOAD = 80


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.bing.com/",
        "Connection": "keep-alive",
    }
)


# ============================================================
# WORDS THAT SHOULD NOT DRIVE RELEVANCE
# ============================================================

STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "that",
    "this",
    "about",
    "highlights",
    "highlight",
    "role",
    "roles",
    "says",
    "said",
    "news",
    "latest",
    "today",
    "india",
    "indian",
    "photo",
    "photograph",
    "image",
    "images",
    "picture",
    "pictures",
    "supreme",
    "court",
    "lawyer",
    "lawyers",
    "advocate",
    "advocates",
}


# ============================================================
# HARD BLOCKED DOMAINS / CONTENT
# ============================================================

BAD_DOMAINS = {
    "pinterest.com",
    "pinimg.com",
    "freepik.com",
    "vecteezy.com",
    "shutterstock.com",
    "istockphoto.com",
    "dreamstime.com",
    "wallpaperaccess.com",
    "wallpapers.com",
    "wallpapercave.com",
    "ebayimg.com",
    "sokmil.com",
    "porn",
    "adult",
    "anime",
    "recipe",
    "food",
    "cooking",
    "dog",
    "dogs",
    "cat",
    "cats",
    "fashion",
    "music",
}


# ============================================================
# GOOD NEWS DOMAINS
# ============================================================

GOOD_DOMAINS = {
    "supremecourtofindia.nic.in": 8,
    "sci.gov.in": 8,
    "pib.gov.in": 7,

    "thehindu.com": 6,
    "indianexpress.com": 6,
    "reuters.com": 6,
    "apnews.com": 6,

    "ndtv.com": 5,
    "news18.com": 5,
    "indiatoday.in": 5,
    "hindustantimes.com": 5,
    "timesofindia.indiatimes.com": 5,

    "deccanherald.com": 5,
    "telegraphindia.com": 5,

    "bbc.com": 5,
    "bbc.co.uk": 5,

    "wikimedia.org": 4,
    "wikipedia.org": 3,
}


# ============================================================
# GENERIC UNRELATED WORDS
# ============================================================

UNRELATED_TERMS = {
    "dog",
    "dogs",
    "puppy",
    "puppies",
    "cat",
    "cats",
    "kitten",
    "recipe",
    "salad",
    "chicken",
    "cooking",
    "food",
    "restaurant",
    "fashion",
    "dress",
    "makeup",
    "anime",
    "manga",
    "singer",
    "actress",
    "actor",
    "football",
    "cricket",
    "gaming",
    "game",
    "wallpaper",
    "vector",
    "illustration",
    "clipart",
    "stock",
    "toy",
    "toys",
    "action figure",
    "action figures",
    "diy",
    "craft",
    "amazon",
    "ebay",
    "pinterest",
    "etsy",
    "product",
    "shopping",
    "lamp",
    "globe",
    "light",
    "lighting",
    "furniture",
}


# ============================================================
# HELPERS
# ============================================================

def line():
    print("=" * 60)


def clean_text(value):
    if not value:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_text(value):
    value = clean_text(value).lower()

    value = value.replace("-", " ")
    value = value.replace("_", " ")
    value = value.replace("/", " ")

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def contains_word(text, word):
    """
    Whole-word matching.

    Prevents:
        court -> courtyard
        india -> indian
        art -> article
    """

    text = normalize_text(text)
    word = normalize_text(word)

    if not text or not word:
        return False

    pattern = r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])"

    return re.search(pattern, text) is not None


def contains_any(text, words):
    return any(contains_word(text, word) for word in words)


def tokenize(text):
    text = normalize_text(text)

    words = re.findall(r"[a-z0-9]+", text)

    result = []

    for word in words:

        if len(word) < 3:
            continue

        if word in STOP_WORDS:
            continue

        if word not in result:
            result.append(word)

    return result


def get_domain(url):
    try:
        domain = urlparse(url).netloc.lower()
        domain = domain.replace("www.", "")
        return domain
    except Exception:
        return ""


# ============================================================
# TOPIC ANALYSIS
# ============================================================

def analyze_topic(topic):

    text = normalize_text(topic)

    analysis = {
        "person": False,
        "surya_kant": False,
        "supreme_court": False,
        "lawyers": False,
        "freedom": False,
    }

    if (
        "surya kant" in text
        or "surya" in text and "kant" in text
    ):
        analysis["surya_kant"] = True
        analysis["person"] = True

    if (
        "supreme court" in text
        or "cji" in text
        or "chief justice" in text
    ):
        analysis["supreme_court"] = True

    if contains_any(
        text,
        [
            "lawyer",
            "lawyers",
            "advocate",
            "advocates",
            "barrister",
        ],
    ):
        analysis["lawyers"] = True

    if contains_any(
        text,
        [
            "freedom struggle",
            "freedom movement",
            "independence movement",
            "independence struggle",
            "indian independence",
        ],
    ):
        analysis["freedom"] = True

    return analysis


# ============================================================
# SEARCH QUERY GENERATION
# ============================================================

def build_search_queries(topic):

    analysis = analyze_topic(topic)

    queries = []

    # --------------------------------------------------------
    # PERSON
    # --------------------------------------------------------

    if analysis["surya_kant"]:

        queries.extend(
            [
                "Justice Surya Kant India",
                "Justice Surya Kant Supreme Court India",
                "Justice Surya Kant Chief Justice India",
                "CJI Surya Kant Supreme Court",
                "Surya Kant Supreme Court judge",
                "Surya Kant lawyers Supreme Court",
                "Surya Kant advocate lawyers India",
                "Surya Kant courtroom",
            ]
        )

    # --------------------------------------------------------
    # SUPREME COURT
    # --------------------------------------------------------

    if analysis["supreme_court"]:

        queries.extend(
            [
                "Supreme Court of India judges",
                "Supreme Court of India lawyers",
                "Supreme Court India courtroom",
                "Supreme Court India advocates",
                "Indian lawyers Supreme Court",
                "Indian advocates Supreme Court",
                "Indian lawyers courtroom",
            ]
        )

    # --------------------------------------------------------
    # FREEDOM MOVEMENT
    # --------------------------------------------------------

    if analysis["freedom"]:

        queries.extend(
            [
                "Indian freedom struggle lawyers",
                "Indian independence movement lawyers",
                "freedom movement Indian barristers",
                "Indian freedom fighters lawyers",
            ]
        )

    # --------------------------------------------------------
    # GENERIC FALLBACK
    # --------------------------------------------------------

    tokens = tokenize(topic)

    if tokens:

        query = " ".join(tokens[:8])

        queries.append(query)

    # --------------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------------

    final = []

    for query in queries:

        query = query.strip()

        if not query:
            continue

        if query not in final:
            final.append(query)

    return final[:20]


# ============================================================
# BING IMAGE SEARCH
# ============================================================

def search_bing_images(query, limit=RESULTS_PER_QUERY):

    url = (
        "https://www.bing.com/images/async"
        f"?q={quote_plus(query)}"
        f"&first=0"
        f"&count={limit}"
        f"&adlt=off"
    )

    try:

        response = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

    except Exception as exc:

        print(f"Search request failed: {exc}")

        return []

    page = response.text

    candidates = []

    pattern = re.compile(
        r'<a[^>]+class="[^"]*iusc[^"]*"[^>]+m="([^"]+)"',
        re.IGNORECASE,
    )

    matches = pattern.findall(page)

    for raw_metadata in matches:

        try:

            metadata_text = html.unescape(
                raw_metadata
            )

            data = json.loads(metadata_text)

        except Exception:
            continue

        image_url = (
            data.get("murl")
            or data.get("turl")
            or ""
        )

        page_url = data.get("purl", "") or ""

        title = (
            data.get("t")
            or data.get("desc")
            or data.get("pt")
            or ""
        )

        if not image_url:
            continue

        candidates.append(
            {
                "image_url": image_url,
                "page_url": page_url,
                "title": clean_text(title),
                "query": query,
            }
        )

    return candidates


# ============================================================
# DOMAIN SCORING
# ============================================================

def domain_score(url):

    domain = get_domain(url)

    if not domain:
        return 0

    # Hard block
    for bad in BAD_DOMAINS:

        if bad in domain:
            return -50

    # Good sources
    for good, score in GOOD_DOMAINS.items():

        if good in domain:
            return score

    return 0


# ============================================================
# HARD UNRELATED CHECK
# ============================================================

def is_obviously_unrelated(candidate):

    title = normalize_text(
        candidate.get("title", "")
    )

    page_url = normalize_text(
        candidate.get("page_url", "")
    )

    image_url = normalize_text(
        candidate.get("image_url", "")
    )

    # IMPORTANT:
    # Do NOT include candidate["query"] here.
    #
    # The search query describes what WE asked Bing.
    # It is NOT evidence that the returned image is relevant.

    evidence = (
        title
        + " "
        + page_url
        + " "
        + image_url
    )

    for term in UNRELATED_TERMS:

        if contains_word(evidence, term):
            return True

    return False


# ============================================================
# RELEVANCE SCORING
# ============================================================

def relevance_score(candidate, topic):

    analysis = analyze_topic(topic)

    title = normalize_text(
        candidate.get("title", "")
    )

    page_url = normalize_text(
        candidate.get("page_url", "")
    )

    image_url = normalize_text(
        candidate.get("image_url", "")
    )

    # --------------------------------------------------------
    # VERY IMPORTANT
    #
    # Search query is intentionally NOT included.
    #
    # Previous bug:
    #
    # combined = title + page_url + image_url + query
    #
    # This caused unrelated images to score highly because
    # the query itself contained "Supreme Court", "India",
    # "lawyers", etc.
    # --------------------------------------------------------

    evidence = (
        title
        + " "
        + page_url
        + " "
        + image_url
    )

    score = 0

    # --------------------------------------------------------
    # HARD UNRELATED
    # --------------------------------------------------------

    if is_obviously_unrelated(candidate):
        return -50

    # --------------------------------------------------------
    # PERSON: SURYA KANT
    # --------------------------------------------------------

    if analysis["surya_kant"]:

        has_surya = contains_word(
            evidence,
            "surya",
        )

        has_kant = contains_word(
            evidence,
            "kant",
        )

        has_full_name = (
            "surya kant" in evidence
        )

        if has_full_name:

            score += 40

        elif has_surya and has_kant:

            score += 30

        else:

            # If the actual result doesn't mention the person,
            # it should NOT rank highly just because the query did.
            score -= 20

    # --------------------------------------------------------
    # SUPREME COURT
    # --------------------------------------------------------

    if analysis["supreme_court"]:

        if "supreme court" in evidence:
            score += 15

        elif "supremecourt" in evidence:
            score += 12

        if contains_word(
            evidence,
            "justice",
        ):
            score += 5

        if contains_word(
            evidence,
            "judge",
        ):
            score += 5

        if contains_word(
            evidence,
            "courtroom",
        ):
            score += 5

    # --------------------------------------------------------
    # LAWYERS
    # --------------------------------------------------------

    if analysis["lawyers"]:

        lawyer_terms = [
            "lawyer",
            "lawyers",
            "advocate",
            "advocates",
            "barrister",
            "legal",
            "courtroom",
        ]

        for term in lawyer_terms:

            if contains_word(title, term):
                score += 6

            elif contains_word(page_url, term):
                score += 3

    # --------------------------------------------------------
    # FREEDOM MOVEMENT
    # --------------------------------------------------------

    if analysis["freedom"]:

        freedom_terms = [
            "freedom struggle",
            "freedom movement",
            "independence movement",
            "independence struggle",
            "indian independence",
            "freedom fighter",
            "national movement",
            "barrister",
        ]

        found_freedom = False

        for term in freedom_terms:

            if term in title:

                score += 10
                found_freedom = True

            elif term in page_url:

                score += 5
                found_freedom = True

        # Generic historical lawyers are useful for the
        # secondary part of the story, but only if the image
        # actually contains historical/freedom evidence.
        if contains_word(title, "lawyer"):
            score += 3

        if contains_word(title, "lawyers"):
            score += 3

        if not found_freedom and analysis["surya_kant"]:
            # Person images are still useful.
            pass

    # --------------------------------------------------------
    # TITLE QUALITY
    # --------------------------------------------------------

    if title:

        if contains_word(title, "photo"):
            score += 2

        if contains_word(title, "photograph"):
            score += 2

        if contains_word(title, "news"):
            score += 2

    # --------------------------------------------------------
    # DOMAIN
    # --------------------------------------------------------

    source_url = (
        candidate.get("page_url", "")
        or candidate.get("image_url", "")
    )

    score += domain_score(source_url)

    # --------------------------------------------------------
    # EXTRA SAFETY
    # --------------------------------------------------------

    # If we are searching for a specific person,
    # unrelated generic images should not survive.
    if analysis["surya_kant"]:

        has_person = (
            "surya kant" in evidence
            or (
                contains_word(evidence, "surya")
                and contains_word(evidence, "kant")
            )
        )

        if not has_person:

            # Allow generic Supreme Court images only as
            # secondary B-roll.
            if "supreme court" not in evidence:
                score -= 25

    return score


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(candidate, destination):

    image_url = candidate.get("image_url")

    if not image_url:
        return False

    temp_file = destination.with_suffix(".tmp")

    try:

        response = SESSION.get(
            image_url,
            timeout=REQUEST_TIMEOUT,
            stream=True,
            headers={
                "Referer": "https://www.bing.com/",
                "User-Agent": SESSION.headers["User-Agent"],
            },
        )

        response.raise_for_status()

        content_type = (
            response.headers.get(
                "Content-Type",
                ""
            )
            .lower()
        )

        # Reject obvious HTML pages
        if "text/html" in content_type:
            return False

        content_length = response.headers.get(
            "Content-Length"
        )

        if content_length:

            try:

                if int(content_length) > MAX_FILE_SIZE:
                    return False

            except Exception:
                pass

        total = 0

        with open(
            temp_file,
            "wb",
        ) as file:

            for chunk in response.iter_content(
                chunk_size=64 * 1024
            ):

                if not chunk:
                    continue

                total += len(chunk)

                if total > MAX_FILE_SIZE:

                    try:
                        temp_file.unlink()
                    except Exception:
                        pass

                    return False

                file.write(chunk)

        # ----------------------------------------------------
        # PIL validation
        # ----------------------------------------------------

        try:

            with Image.open(temp_file) as image:
                image.verify()

        except Exception:

            try:
                temp_file.unlink()
            except Exception:
                pass

            return False

        # ----------------------------------------------------
        # Reopen and convert
        # ----------------------------------------------------

        try:

            with Image.open(temp_file) as image:

                width, height = image.size

                if width < MIN_WIDTH:
                    return False

                if height < MIN_HEIGHT:
                    return False

                ratio = width / float(height)

                # Allow normal landscape / portrait,
                # reject extreme banners and tiny strips.
                if ratio < 0.55 or ratio > 2.5:
                    return False

                image = image.convert("RGB")

                image.save(
                    destination,
                    "JPEG",
                    quality=92,
                    optimize=True,
                )

        except Exception:

            return False

        return True

    except Exception:

        return False

    finally:

        try:
            if temp_file.exists():
                temp_file.unlink()
        except Exception:
            pass


# ============================================================
# IMAGE HASH
# ============================================================

def image_hash(path):

    try:

        with Image.open(path) as image:

            image = image.convert("L")

            image = image.resize(
                (32, 32)
            )

            data = bytes(
                image.getdata()
            )

            return hashlib.md5(
                data
            ).hexdigest()

    except Exception:

        return None


# ============================================================
# VISUAL QUALITY
# ============================================================

def visual_quality_score(path):

    try:

        with Image.open(path) as image:

            image = image.convert("RGB")

            stat = ImageStat.Stat(image)

            means = stat.mean

            contrast = (
                sum(stat.stddev) / 3
            )

            brightness = (
                sum(means) / 3
            )

            score = 0

            if contrast > 18:
                score += 3

            if contrast > 30:
                score += 2

            if 25 < brightness < 235:
                score += 3

            if brightness < 10:
                score -= 10

            if brightness > 250:
                score -= 10

            return score

    except Exception:

        return -100


# ============================================================
# FINAL VALIDATION
# ============================================================

def validate_final_image(path):

    try:

        with Image.open(path) as image:

            width, height = image.size

            if width < MIN_WIDTH:
                return False

            if height < MIN_HEIGHT:
                return False

            quality = visual_quality_score(
                path
            )

            if quality < 0:
                return False

        return True

    except Exception:

        return False


# ============================================================
# CLEAN OLD ASSETS
# ============================================================

def clean_assets():

    ASSETS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for file in ASSETS_DIR.iterdir():

        if file.is_file():

            try:
                file.unlink()
            except Exception:
                pass


# ============================================================
# MAIN FUNCTION
# ============================================================

def download_images(topic):

    line()

    print("AI IMAGE SEARCH STARTED")

    line()

    print()
    print("Topic:")
    print(topic)
    print()

    # --------------------------------------------------------
    # Topic analysis
    # --------------------------------------------------------

    analysis = analyze_topic(topic)

    print("Topic analysis:")

    print(
        f"Surya Kant: "
        f"{analysis['surya_kant']}"
    )

    print(
        f"Supreme Court: "
        f"{analysis['supreme_court']}"
    )

    print(
        f"Lawyers: "
        f"{analysis['lawyers']}"
    )

    print(
        f"Freedom movement: "
        f"{analysis['freedom']}"
    )

    # --------------------------------------------------------
    # Clean old images
    # --------------------------------------------------------

    print()
    print("Cleaning old image assets...")

    clean_assets()

    # --------------------------------------------------------
    # Build searches
    # --------------------------------------------------------

    queries = build_search_queries(
        topic
    )

    print()

    line()

    print(
        f"TOTAL SEARCHES: {len(queries)}"
    )

    line()

    for index, query in enumerate(
        queries,
        start=1,
    ):

        print(
            f"{index}. {query}"
        )

    print()

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    all_candidates = []

    seen_urls = set()

    for index, query in enumerate(
        queries,
        start=1,
    ):

        line()

        print(
            f"SEARCHING {index}/{len(queries)}"
        )

        print(query)

        line()

        results = search_bing_images(
            query,
            RESULTS_PER_QUERY,
        )

        print(
            f"Metadata results found: "
            f"{len(results)}"
        )

        added = 0

        for candidate in results:

            image_url = (
                candidate.get(
                    "image_url",
                    "",
                )
            )

            if not image_url:
                continue

            normalized_url = (
                image_url
                .split("?")[0]
                .strip()
                .lower()
            )

            if normalized_url in seen_urls:
                continue

            seen_urls.add(
                normalized_url
            )

            # ------------------------------------------------
            # Score ONLY actual result evidence.
            # Search query is deliberately excluded.
            # ------------------------------------------------

            score = relevance_score(
                candidate,
                topic,
            )

            candidate["score"] = score

            title = candidate.get(
                "title",
                "",
            )

            # ------------------------------------------------
            # Hard reject
            # ------------------------------------------------

            if score < MIN_RELEVANCE_SCORE:

                print(
                    f"Skipped: relevance "
                    f"{score} | "
                    f"{title[:100]}"
                )

                continue

            all_candidates.append(
                candidate
            )

            added += 1

        print(
            f"Accepted from search: "
            f"{added}"
        )

        time.sleep(
            SEARCH_DELAY
        )

    # --------------------------------------------------------
    # Candidate summary
    # --------------------------------------------------------

    line()

    print(
        f"RELEVANT CANDIDATES: "
        f"{len(all_candidates)}"
    )

    line()

    if not all_candidates:

        print()
        print(
            "⚠️ No relevant image candidates found."
        )
        print()

        return 0

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    all_candidates.sort(
        key=lambda item: item.get(
            "score",
            0,
        ),
        reverse=True,
    )

    # --------------------------------------------------------
    # Remove duplicate titles / URLs
    # --------------------------------------------------------

    unique_candidates = []

    seen_titles = set()

    for candidate in all_candidates:

        title = normalize_text(
            candidate.get(
                "title",
                "",
            )
        )

        # Don't over-filter empty titles
        if title:

            title_key = title[:150]

            if title_key in seen_titles:
                continue

            seen_titles.add(
                title_key
            )

        unique_candidates.append(
            candidate
        )

    all_candidates = unique_candidates

    # --------------------------------------------------------
    # TOP CANDIDATES
    # --------------------------------------------------------

    print()
    print("TOP CANDIDATES:")

    for index, candidate in enumerate(
        all_candidates[:30],
        start=1,
    ):

        source = (
            candidate.get(
                "page_url",
                "",
            )
            or candidate.get(
                "image_url",
                "",
            )
        )

        domain = get_domain(
            source
        )

        print(
            f"{index:02d}. "
            f"Score="
            f"{candidate.get('score', 0):03d} | "
            f"{domain} | "
            f"{candidate.get('title', '')[:100]}"
        )

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    print()

    line()

    print(
        "DOWNLOADING BEST IMAGES"
    )

    line()

    final_count = 0

    used_hashes = set()

    attempts = min(
        len(all_candidates),
        MAX_CANDIDATES_TO_DOWNLOAD,
    )

    for candidate in all_candidates[
        :attempts
    ]:

        if final_count >= TARGET_IMAGES:
            break

        next_number = (
            final_count + 1
        )

        output_path = (
            ASSETS_DIR
            / f"{next_number}.jpg"
        )

        score = candidate.get(
            "score",
            0,
        )

        title = candidate.get(
            "title",
            "",
        )

        print()

        print(
            f"Trying candidate "
            f"score={score}"
        )

        print(
            f"Title: "
            f"{title[:120]}"
        )

        success = download_image(
            candidate,
            output_path,
        )

        if not success:

            print(
                "Skipped: "
                "download/validation failed"
            )

            try:
                output_path.unlink()
            except Exception:
                pass

            continue

        # ----------------------------------------------------
        # Final validation
        # ----------------------------------------------------

        if not validate_final_image(
            output_path
        ):

            print(
                "Skipped: "
                "visual quality failed"
            )

            try:
                output_path.unlink()
            except Exception:
                pass

            continue

        # ----------------------------------------------------
        # Duplicate detection
        # ----------------------------------------------------

        file_hash = image_hash(
            output_path
        )

        if not file_hash:

            print(
                "Skipped: "
                "hash calculation failed"
            )

            try:
                output_path.unlink()
            except Exception:
                pass

            continue

        if file_hash in used_hashes:

            print(
                "Skipped: duplicate image"
            )

            try:
                output_path.unlink()
            except Exception:
                pass

            continue

        used_hashes.add(
            file_hash
        )

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        print(
            f"✅ Final image "
            f"{next_number} saved"
        )

        final_count += 1

    # --------------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------------

    print()

    line()

    print(
        f"FINAL RELEVANT IMAGES: "
        f"{final_count}"
    )

    line()

    if final_count == 0:

        print()
        print(
            "⚠️ No usable relevant images were found."
        )
        print()

    else:

        print()

        print(
            "✅ Image pipeline completed successfully."
        )

        print(
            f"Images saved in: "
            f"{ASSETS_DIR.resolve()}"
        )

        print()

        for index in range(
            1,
            final_count + 1,
        ):

            path = (
                ASSETS_DIR
                / f"{index}.jpg"
            )

            if not path.exists():
                continue

            try:

                with Image.open(path) as image:

                    print(
                        f"Image {index}: "
                        f"{image.size[0]}x"
                        f"{image.size[1]}"
                    )

            except Exception:
                pass

    return final_count


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    test_topic = (
        "CJI Surya Kant Highlights "
        "Lawyers Role In Freedom Struggle"
    )

    count = download_images(
        test_topic
    )

    print()

    print(
        f"Returned image count: {count}"
    )
    
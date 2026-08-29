import os
import re
import time
import hashlib
import html
from pathlib import Path


import requests
from PIL import Image


# ============================================================
# CONFIG
# ============================================================

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
OUTPUT_DIR = ROOT / "output"

TARGET_IMAGES = 12

MIN_PIXEL_X = 500
MIN_PIXEL_Y = 300

MAX_FILE_SIZE = 12 * 1024 * 1024

REQUEST_TIMEOUT = 20

MAX_WIKIMEDIA_RESULTS = 20
MAX_BING_RESULTS = 40

WIKIMEDIA_DELAY = 2


# ============================================================
# SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "AutoTubeAI/2.0 "
            "(automated video project)"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
)


# ============================================================
# TEXT HELPERS
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


def text_tokens(text):
    return set(normalize_text(text).split())


# ============================================================
# STORY DETECTION
# ============================================================

def detect_story(topic):

    text = normalize_text(topic)

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
            "technology",
            "tech",
            "ai",
            "artificial intelligence",
            "software",
            "startup",
            "semiconductor",
            "chip",
            "robot",
            "cybersecurity",
        ]
    ):
        return "TECH"

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
        return "MARITIME"

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
# NORMAL TOPIC QUERIES
# ============================================================

def build_queries(topic):

    text = normalize_text(topic)

    words = [
        word
        for word in text.split()
        if len(word) >= 4
    ]

    story = detect_story(topic)

    queries = []

    if story == "LEGAL":

        queries = [
            topic,
            "Supreme Court India",
            "Chief Justice India",
            "Indian lawyers court",
            "Indian judiciary",
        ]

    elif story == "TECH":

        queries = [
            topic,
            " ".join(words[:8]) + " technology",
            " ".join(words[:6]) + " tech news",
            " ".join(words[:6]) + " India technology",
        ]

    elif story == "MARITIME":

        queries = [
            topic,
            "Strait of Hormuz ships",
            "Hormuz maritime shipping",
            "Persian Gulf tanker",
            "Iran Gulf shipping",
        ]

    elif story == "INDIA":

        queries = [
            topic,
            " ".join(words[:8]),
            "India " + " ".join(words[:5]),
        ]

    else:

        queries = [
            topic,
            " ".join(words[:8]),
        ]

    final = []

    for query in queries:

        query = query.strip()

        if query and query not in final:
            final.append(query)

    return final


# ============================================================
# WIKIMEDIA SEARCH
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
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        data = response.json()

    except Exception as error:

        print(
            f"Wikimedia search failed: {error}"
        )

        return []

    pages = (
        data
        .get("query", {})
        .get("pages", {})
    )

    results = []

    for page in pages.values():

        imageinfo = page.get(
            "imageinfo",
            []
        )

        if not imageinfo:
            continue

        info = imageinfo[0]

        image_url = (
            info.get("thumburl")
            or info.get("url")
        )

        if not image_url:
            continue

        results.append(
            {
                "image_url": image_url,
                "title": clean_text(
                    page.get("title", "")
                ),
                "source": "Wikimedia",
                "width": info.get(
                    "width",
                    0
                ),
                "height": info.get(
                    "height",
                    0
                ),
                "mime": info.get(
                    "mime",
                    ""
                ),
            }
        )

    return results


# ============================================================
# BING IMAGE SEARCH
# ============================================================

def search_bing(query):

    url = (
        "https://www.bing.com/images/"
        "search"
    )

    params = {
        "q": query,
        "form": "HDRSC2",
        "first": 1,
    }

    try:

        response = SESSION.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

    except Exception as error:

        print(
            f"Bing search failed: {error}"
        )

        return []

    html_text = response.text

    results = []

    pattern = re.compile(
        r'murl&quot;:&quot;(.*?)&quot;.*?'
        r'mid&quot;:&quot;(.*?)&quot;',
        re.DOTALL,
    )

    matches = pattern.findall(
        html_text
    )

    for image_url, mid in matches:

        image_url = (
            image_url
            .replace("\\/", "/")
            .replace("\\u002f", "/")
        )

        if not image_url.startswith(
            "http"
        ):
            continue

        results.append(
            {
                "image_url": image_url,
                "title": query,
                "source": "Bing",
                "width": 0,
                "height": 0,
                "mime": "",
                "mid": mid,
            }
        )

        if len(results) >= MAX_BING_RESULTS:
            break

    return results


# ============================================================
# RELEVANCE
# ============================================================

def score_candidate(
    candidate,
    query,
):

    title_tokens = text_tokens(
        candidate.get(
            "title",
            ""
        )
    )

    query_words = [
        word
        for word in normalize_text(
            query
        ).split()
        if len(word) >= 2
    ]

    if not query_words:
        return 0

    score = 0

    for word in query_words:

        if word in title_tokens:
            score += 10

    width = candidate.get(
        "width",
        0
    )

    height = candidate.get(
        "height",
        0
    )

    if width >= 1000:
        score += 5

    if height >= 600:
        score += 5

    return score


def is_relevant(
    candidate,
    query,
):

    score = score_candidate(
        candidate,
        query
    )

    return score >= 5


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(
    candidate,
    destination,
):

    url = candidate.get(
        "image_url",
        ""
    )

    if not url:
        return False

    try:

        with SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT,
            stream=True,
        ) as response:
            response.raise_for_status()

            content_type = (
                response.headers
                .get(
                    "content-type",
                    ""
                )
                .lower()
            )

            if (
                content_type
                and "image" not in content_type
            ):
                return False

            content_length = int(
                response.headers.get(
                    "content-length",
                    0
                )
                or 0
            )

            if (
                content_length
                and content_length > MAX_FILE_SIZE
            ):
                return False

            data = response.content

        if len(data) > MAX_FILE_SIZE:
            return False

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(
            destination,
            "wb"
        ) as file:

            file.write(data)

        with Image.open(
            destination
        ) as image:

            image.verify()

        with Image.open(
            destination
        ) as image:

            pixel_x, pixel_y = image.size

        if pixel_x < MIN_PIXEL_X:
            destination.unlink(
                missing_ok=True
            )
            return False

        if pixel_y < MIN_PIXEL_Y:
            destination.unlink(
                missing_ok=True
            )
            return False

        with Image.open(
            destination
        ) as image:

            image.convert(
                "RGB"
            ).save(
                destination,
                "JPEG",
                quality=90,
            )

        return True

    except Exception as error:

        print(
            f"Download failed: {error}"
        )

        destination.unlink(
            missing_ok=True
        )

        return False


# ============================================================
# IMAGE HASH
# ============================================================

def image_hash(path):

    try:

        hasher = hashlib.sha256()

        with open(
            path,
            "rb"
        ) as file:

            while True:

                chunk = file.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                hasher.update(
                    chunk
                )

        return hasher.hexdigest()

    except Exception:

        return None


def save_flyer_fallback(flyer_path, destination):
    if not flyer_path:
        return False

    source = Path(flyer_path)

    if not source.exists():
        return False

    try:
        with Image.open(source) as image:
            image.convert("RGB").save(
                destination,
                "JPEG",
                quality=95,
            )
        return True
    except Exception as error:
        print(
            f"Could not create flyer fallback: {error}"
        )
        destination.unlink(missing_ok=True)
        return False


# ============================================================
# CLEAN ASSETS
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
# SEARCH CANDIDATES
# ============================================================

def collect_candidates(
    queries,
):

    candidates = []

    seen_urls = set()

    for index, query in enumerate(
        queries,
        1
    ):

        print()
        line()

        print(
            f"SEARCH {index}/{len(queries)}"
        )

        print(
            query
        )

        line()

        sources = []

        sources.extend(
            search_wikimedia(
                query
            )
        )

        sources.extend(
            search_bing(
                query
            )
        )

        for candidate in sources:

            url = candidate.get(
                "image_url",
                ""
            )

            key = url.split(
                "?",
                1
            )[0]

            if not key:
                continue

            if key in seen_urls:
                continue

            seen_urls.add(
                key
            )

            if not is_relevant(
                candidate,
                query
            ):
                continue

            candidate["score"] = (
                score_candidate(
                    candidate,
                    query
                )
            )

            candidate["visual_query"] = (
                query
            )

            candidates.append(
                candidate
            )

        time.sleep(
            WIKIMEDIA_DELAY
        )

    candidates.sort(
        key=lambda item: item.get(
            "score",
            0
        ),
        reverse=True,
    )

    return candidates


# ============================================================
# NORMAL TOPIC MODE
# ============================================================

def download_images(
    topic
):

    line()

    print(
        "AI IMAGE SEARCH STARTED"
    )

    line()

    print()
    print(
        "Topic:"
    )
    print(topic)

    clean_assets()

    queries = build_queries(
        topic
    )

    print()
    print(
        f"SEARCH QUERIES: {len(queries)}"
    )

    for index, query in enumerate(
        queries,
        1
    ):

        print(
            f"{index}. {query}"
        )

    candidates = collect_candidates(
        queries
    )

    return _download_top_candidates(
        candidates
    )


# ============================================================
# DOWNLOAD TOP CANDIDATES
# ============================================================

def _download_top_candidates(
    candidates,
    flyer_path=None,
):

    count = 0

    used_hashes = set()
    used_urls = set()
    used_titles = set()

    for candidate in candidates:

        if count >= TARGET_IMAGES:
            break

        url = candidate.get(
            "image_url",
            ""
        )

        title_key = normalize_text(
            candidate.get(
                "title",
                ""
            )
        )

        if url in used_urls:
            continue

        if (
            title_key
            and title_key in used_titles
        ):
            continue

        number = count + 1

        destination = (
            ASSETS_DIR
            / f"{number}.jpg"
        )

        print()
        print(
            f"Trying candidate for visual {number}: "
            f"{candidate.get('visual_query', '')}"
        )

        print(
            f"Score: {candidate.get('score', 0)}"
        )

        print(
            f"Source: {candidate.get('source', '')}"
        )

        success = download_image(
            candidate,
            destination
        )

        if not success:
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
                "Skipped duplicate"
            )

            destination.unlink(
                missing_ok=True
            )

            continue

        used_hashes.add(
            file_hash
        )

        used_urls.add(
            url
        )

        if title_key:
            used_titles.add(
                title_key
            )

        count += 1

        print(
            f"OK - Visual {count} saved as {count}.jpg"
        )

        with Image.open(destination) as image:
            print(
                f"Size: {image.size[0]}x{image.size[1]}"
            )

    # --------------------------------------------------------
    # Flyer = VISUAL 8
    # --------------------------------------------------------

    if flyer_path and os.path.exists(flyer_path):

        try:

            flyer_destination = (
                ASSETS_DIR / "8.jpg"
            )

            with Image.open(flyer_path) as image:

                image.convert("RGB").save(
                    flyer_destination,
                    "JPEG",
                    quality=95,
                )

            print()
            print(
                "Original flyer included as Visual 8:"
            )
            print(
                flyer_destination
            )

        except Exception as error:

            print(
                f"Could not include flyer: {error}"
            )

            flyer_destination.unlink(
                missing_ok=True
            )

    print()
    line()

    print(
        f"FINAL IMAGES: {count}"
    )

    return count


# ============================================================
# VISUAL PLAN MODE
# ============================================================

def download_images_from_visual_plan(
    visual_plan_path=OUTPUT_DIR / "visual_plan.txt",
    flyer_path=None,
):

    line()

    print(
        "AI FLYER VISUAL SEARCH STARTED"
    )

    line()

    visual_plan_path = Path(
        visual_plan_path
    )

    if not visual_plan_path.exists():

        raise FileNotFoundError(
            f"Visual plan not found: {visual_plan_path}"
        )

    concepts = []

    with open(
        visual_plan_path,
        "r",
        encoding="utf-8",
    ) as file:

        for raw_line in file:

            line_text = raw_line.strip()

            match = re.match(
                r"^\d+\.\s*(.+)$",
                line_text,
            )

            if not match:
                continue

            concept = match.group(1).strip()

            if concept:
                concepts.append(
                    concept
                )

    if not concepts:

        raise ValueError(
            "No visual concepts found in visual plan"
        )

    print()
    print(
        f"VISUAL CONCEPTS: {len(concepts)}"
    )

    clean_assets()

    downloaded = 0

    for index, concept in enumerate(
        concepts,
        1
    ):

        print()
        line()

        print(
            f"VISUAL {index}/{len(concepts)}"
        )

        print(
            f"Concept: {concept}"
        )

        line()

        # ----------------------------------------------------
        # Original flyer
        # ----------------------------------------------------

        if index == len(concepts) and (
            concept.lower()
            in {
                "the original flyer",
                "original flyer",
                "the flyer",
            }
            or "original flyer" in concept.lower()
        ):

            print(
                f"Visual {index} -> original flyer"
            )

            if flyer_path and Path(
                flyer_path
            ).exists():

                destination = (
                    ASSETS_DIR
                    / f"{index}.jpg"
                )

                with Image.open(
                    flyer_path
                ) as image:

                    image.convert(
                        "RGB"
                    ).save(
                        destination,
                        "JPEG",
                        quality=95,
                    )

                print(
                    f"Saved: {destination}"
                )

                downloaded += 1

            else:

                print(
                    "Original flyer not found"
                )

            continue

        # ----------------------------------------------------
        # Search this visual concept
        # ----------------------------------------------------

        candidates = collect_candidates(
            [concept]
        )

        if not candidates:

            print(
                f"No candidates found for visual {index}"
            )

            continue

        used_hashes = set()

        saved = False

        for candidate in candidates:

            print()

            print(
                f"Trying candidate for visual {index}: "
                f"{concept}"
            )

            print(
                f"Score: "
                f"{candidate.get('score', 0)}"
            )

            print(
                f"Source: "
                f"{candidate.get('source', '')}"
            )

            destination = (
                ASSETS_DIR
                / f"{index}.jpg"
            )

            if not download_image(
                candidate,
                destination,
            ):

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

                width, height = image.size

            print()
            print(
                f"OK - Visual {index} saved as "
                f"{index}.jpg"
            )

            print(
                f"Size: {width}x{height}"
            )

            downloaded += 1
            saved = True

            break

        if not saved:

            print(
                f"FAILED - Visual {index}"
            )

    print()
    line()

    print(
        f"VISUAL PLAN IMAGES DOWNLOADED: "
        f"{downloaded}"
    )

    print(
        f"VISUAL CONCEPTS: {len(concepts)}"
    )

    print()

    for index, concept in enumerate(
        concepts,
        1
    ):

        path = (
            ASSETS_DIR
            / f"{index}.jpg"
        )

        status = (
            "OK"
            if path.exists()
            else "MISSING"
        )

        print(
            f"{index}.jpg -> {concept}"
            if status == "OK"
            else f"{index}.jpg -> MISSING"
        )

    print()

    return downloaded

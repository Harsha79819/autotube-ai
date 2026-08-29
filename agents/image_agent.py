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

# IMPORTANT:
# Script agent creates exactly 8 visual concepts.
TARGET_IMAGES = 8

MIN_PIXEL_X = 500
MIN_PIXEL_Y = 300

MAX_FILE_SIZE = 12 * 1024 * 1024

REQUEST_TIMEOUT = 20

MAX_WIKIMEDIA_RESULTS = 12
MAX_BING_RESULTS = 30

WIKIMEDIA_DELAY = 2


# ============================================================
# SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "AutoTubeAI/2.1 "
            "(automated video project)"
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
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_text(text):
    text = clean_text(text).lower()

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def text_tokens(text):
    return set(
        normalize_text(text).split()
    )


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
# SEARCH QUERIES
# ============================================================

def build_queries(topic):

    text = normalize_text(topic)

    words = [
        word
        for word in text.split()
        if len(word) >= 4
    ]

    story = detect_story(topic)

    # Build topic-relevant image queries.
    # IMPORTANT: Do not inject unrelated categories such as
    # "technology", "tech news", or "latest news".

    queries = []

    if story == "LEGAL":

        queries = [
            topic,
            "Supreme Court India",
            "Indian judiciary",
            "Indian court hearing",
        ]

    elif story == "TECH":

        queries = [
            topic,
            " ".join(words[:8]),
            " ".join(words[:6]) + " India",
        ]

    elif story == "MARITIME":

        queries = [
            topic,
            "Strait of Hormuz ships",
            "Hormuz maritime shipping",
            "Persian Gulf tanker",
        ]

    elif story == "INDIA":

        queries = [
            topic,
            " ".join(words[:8]),
            "India " + " ".join(words[:5]),
            " ".join(words[:6]) + " India",
        ]

    else:

        queries = [
            topic,
            " ".join(words[:8]),
            " ".join(words[:6]) + " India",
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
            [],
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
                    0,
                ),
                "height": info.get(
                    "height",
                    0,
                ),
                "mime": info.get(
                    "mime",
                    "",
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

        if not image_url.startswith("http"):
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

def score_candidate(candidate, query):

    title_tokens = text_tokens(
        candidate.get(
            "title",
            "",
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
        0,
    )

    height = candidate.get(
        "height",
        0,
    )

    if width >= 1000:
        score += 5

    if height >= 600:
        score += 5

    # Penalize obvious logo / text-only results.
    title = normalize_text(
        candidate.get("title", "")
    )

    bad_words = [
        "logo",
        "newspaper",
        "radio logo",
        "svg",
    ]

    for bad in bad_words:

        if bad in title:
            score -= 15

    return score


def is_relevant(candidate, query):

    return (
        score_candidate(
            candidate,
            query,
        )
        >= 5
    )


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(
    candidate,
    destination,
):

    url = candidate.get(
        "image_url",
        "",
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
                    "",
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
                    0,
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
            "wb",
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
# HASH
# ============================================================

def image_hash(path):

    try:

        hasher = hashlib.sha256()

        with open(
            path,
            "rb",
        ) as file:

            while True:

                chunk = file.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                hasher.update(chunk)

        return hasher.hexdigest()

    except Exception:

        return None


# ============================================================
# FLYER
# ============================================================

def save_flyer_fallback(
    flyer_path,
    destination,
):

    if not flyer_path:
        return False

    source = Path(flyer_path)

    if not source.exists():
        return False

    try:

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with Image.open(source) as image:

            image.convert(
                "RGB"
            ).save(
                destination,
                "JPEG",
                quality=95,
            )

        return True

    except Exception as error:

        print(
            f"Could not create flyer fallback: {error}"
        )

        destination.unlink(
            missing_ok=True
        )

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
# COLLECT CANDIDATES
# ============================================================

def collect_candidates(queries):

    candidates = []

    seen_urls = set()

    for index, query in enumerate(
        queries,
        1,
    ):

        print()
        print(
            f"SEARCH {index}/{len(queries)}"
        )

        print(query)

        # ----------------------------------------------------
        # Wikimedia
        # ----------------------------------------------------

        wikimedia = search_wikimedia(
            query
        )

        for candidate in wikimedia:

            url = candidate.get(
                "image_url"
            )

            if not url:
                continue

            if url in seen_urls:
                continue

            if not is_relevant(
                candidate,
                query,
            ):
                continue

            seen_urls.add(url)

            candidates.append(candidate)

        # Be polite to Wikimedia.
        time.sleep(WIKIMEDIA_DELAY)

        # ----------------------------------------------------
        # Bing
        # ----------------------------------------------------

        bing = search_bing(query)

        for candidate in bing:

            url = candidate.get(
                "image_url"
            )

            if not url:
                continue

            if url in seen_urls:
                continue

            if not is_relevant(
                candidate,
                query,
            ):
                continue

            seen_urls.add(url)

            candidates.append(candidate)

    # --------------------------------------------------------
    # Highest relevance first.
    # --------------------------------------------------------

    candidates.sort(
        key=lambda item: score_candidate(
            item,
            item.get("title", ""),
        ),
        reverse=True,
    )

    return candidates


# ============================================================
# DOWNLOAD IMAGES
# ============================================================

def download_images(
    topic,
    flyer_path=None,
):

    line()
    print("AI IMAGE SEARCH STARTED")
    line()

    print()
    print("Topic:")
    print(topic)

    # --------------------------------------------------------
    # ALWAYS CLEAN OLD ASSETS.
    # --------------------------------------------------------

    clean_assets()

    queries = build_queries(topic)

    print()
    print(
        f"SEARCH QUERIES: {len(queries)}"
    )

    for index, query in enumerate(
        queries,
        1,
    ):

        print(
            f"{index}. {query}"
        )

    # --------------------------------------------------------
    # Collect candidates.
    # --------------------------------------------------------

    candidates = collect_candidates(
        queries
    )

    # --------------------------------------------------------
    # Download EXACTLY 8 images.
    # --------------------------------------------------------

    downloaded = 0

    used_hashes = set()

    for candidate in candidates:

        # HARD STOP.
        # This is the important fix.
        if downloaded >= TARGET_IMAGES:
            break

        query_title = candidate.get(
            "title",
            topic,
        )

        score = score_candidate(
            candidate,
            query_title,
        )

        visual_number = (
            downloaded + 1
        )

        destination = (
            ASSETS_DIR
            / f"{visual_number}.jpg"
        )

        print()
        print(
            f"Trying candidate for visual "
            f"{visual_number}: {query_title}"
        )

        print(
            f"Score: {score}"
        )

        success = download_image(
            candidate,
            destination,
        )

        if not success:
            continue

        # ----------------------------------------------------
        # Duplicate detection.
        # ----------------------------------------------------

        file_hash = image_hash(
            destination
        )

        if (
            file_hash
            and file_hash in used_hashes
        ):

            print(
                "Duplicate image skipped."
            )

            destination.unlink(
                missing_ok=True
            )

            continue

        if file_hash:
            used_hashes.add(
                file_hash
            )

        downloaded += 1

        print(
            f"OK - Visual {downloaded} "
            f"saved as {visual_number}.jpg"
        )

        try:

            with Image.open(
                destination
            ) as image:

                print(
                    f"Size: {image.width}x"
                    f"{image.height}"
                )

        except Exception:
            pass

    # --------------------------------------------------------
    # Flyer fallback.
    #
    # Flyer is NOT allowed to replace the 8 normal visuals.
    # It can only be used separately by callers that need it.
    # --------------------------------------------------------

    if downloaded < TARGET_IMAGES:

        print()
        print(
            f"WARNING: Only {downloaded}/"
            f"{TARGET_IMAGES} images downloaded."
        )

        raise RuntimeError(
            f"Could not download exactly "
            f"{TARGET_IMAGES} valid images. "
            f"Only {downloaded} were downloaded."
        )

    # --------------------------------------------------------
    # FINAL HARD VALIDATION.
    # --------------------------------------------------------

    final_images = []

    for number in range(
        1,
        TARGET_IMAGES + 1,
    ):

        path = (
            ASSETS_DIR
            / f"{number}.jpg"
        )

        if not path.exists():
            raise RuntimeError(
                f"Missing required image: "
                f"{path.name}"
            )

        final_images.append(path)

    # Remove any accidental numbered files
    # outside the expected 1-8 range.
    for file in ASSETS_DIR.iterdir():

        if not file.is_file():
            continue

        match = re.fullmatch(
            r"(\d+)\.(jpg|jpeg|png|webp)",
            file.name,
            re.IGNORECASE,
        )

        if not match:
            continue

        number = int(
            match.group(1)
        )

        if number > TARGET_IMAGES:

            print(
                f"Removing extra image: "
                f"{file.name}"
            )

            file.unlink(
                missing_ok=True
            )

    print()
    line()

    print(
        f"FINAL IMAGES: {len(final_images)}"
    )

    print(
        "Images Downloaded"
    )

    line()

    return [
        str(path)
        for path in final_images
    ]


# ============================================================
# VISUAL PLAN IMAGE DOWNLOAD
# ============================================================

def download_images_from_visual_plan(
    visual_plan_path,
    flyer_path=None,
):

    visual_plan_file = Path(
        visual_plan_path
    )

    if not visual_plan_file.exists():
        raise FileNotFoundError(
            f"Visual plan not found: "
            f"{visual_plan_file}"
        )

    visuals = []

    with open(
        visual_plan_file,
        "r",
        encoding="utf-8",
    ) as file:

        for raw_line in file:

            line_text = raw_line.strip()

            match = re.match(
                r"^\d+[\.\)]\s*(.+)$",
                line_text,
            )

            if match:
                visuals.append(
                    match.group(1).strip()
                )

    if len(visuals) != TARGET_IMAGES:
        raise RuntimeError(
            f"Expected {TARGET_IMAGES} "
            f"visual concepts, got "
            f"{len(visuals)}."
        )

    # ========================================================
    # DOWNLOAD ONE IMAGE FOR EACH VISUAL DESCRIPTION
    # ========================================================

    line()
    print("AI VISUAL-PLAN IMAGE SEARCH")
    line()

    clean_assets()

    used_hashes = set()
    final_images = []

    for visual_number, visual_query in enumerate(
        visuals,
        start=1,
    ):

        print()
        print(
            f"VISUAL {visual_number}/{TARGET_IMAGES}"
        )

        print(
            f"Query: {visual_query}"
        )

        queries = build_queries(
            visual_query
        )

        candidates = collect_candidates(
            queries
        )

        saved = False

        for candidate in candidates:

            destination = (
                ASSETS_DIR
                / f"{visual_number}.jpg"
            )

            title = candidate.get(
                "title",
                visual_query,
            )

            print()
            print(
                f"Trying Visual {visual_number}: "
                f"{title}"
            )

            success = download_image(
                candidate,
                destination,
            )

            if not success:
                continue

            file_hash = image_hash(
                destination
            )

            if (
                file_hash
                and file_hash in used_hashes
            ):

                print(
                    "Duplicate image skipped."
                )

                destination.unlink(
                    missing_ok=True
                )

                continue

            if file_hash:
                used_hashes.add(
                    file_hash
                )

            final_images.append(
                destination
            )

            print(
                f"OK - Visual {visual_number} "
                f"saved as {visual_number}.jpg"
            )

            try:

                with Image.open(
                    destination
                ) as image:

                    print(
                        f"Size: {image.width}x"
                        f"{image.height}"
                    )

            except Exception:
                pass

            saved = True
            break

        if not saved:

            raise RuntimeError(
                f"Could not download a valid "
                f"image for Visual "
                f"{visual_number}: "
                f"{visual_query}"
            )

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    if len(final_images) != TARGET_IMAGES:
        raise RuntimeError(
            f"Expected {TARGET_IMAGES} images, "
            f"got {len(final_images)}."
        )

    for number in range(
        1,
        TARGET_IMAGES + 1,
    ):

        path = (
            ASSETS_DIR
            / f"{number}.jpg"
        )

        if not path.exists():
            raise RuntimeError(
                f"Missing required image: "
                f"{number}.jpg"
            )

    print()
    line()

    print(
        f"FINAL IMAGES: {len(final_images)}"
    )

    print(
        "Visual-plan image download successful"
    )

    line()

    return [
        str(
            ASSETS_DIR / f"{number}.jpg"
        )
        for number in range(
            1,
            TARGET_IMAGES + 1,
        )
    ]

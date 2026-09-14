import html
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from PIL import Image
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential, wait_random
from urllib3.util.retry import Retry
from supervisor import autonomous_recover

load_dotenv()



# ============================================================
# CONFIG
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

ASSETS_DIR = ROOT / "assets"
FALLBACK_DIR = ASSETS_DIR / "fallback"
OUTPUT_DIR = ROOT / "output"

# IMPORTANT:
# Script agent creates exactly 8 visual concepts.
TARGET_IMAGES = 8

MIN_PIXEL_X = 500
MIN_PIXEL_Y = 300

MAX_FILE_SIZE = 12 * 1024 * 1024

REQUEST_TIMEOUT = 6

try:
    from agents.env_loader import get_pexels_api_key
except ImportError:
    from env_loader import get_pexels_api_key

PEXELS_API_KEY = get_pexels_api_key()
MAX_PEXELS_RESULTS = 10

MAX_WIKIMEDIA_RESULTS = 12
MAX_BING_RESULTS = 30

WIKIMEDIA_DELAY = 0.3


# ============================================================
# THREAD-LOCAL HTTP SESSION WITH BACKOFF RETRY
# ============================================================

_thread_local = threading.local()


def get_session():
    """Return a thread-local requests Session with exponential backoff retries."""
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": (
                    "AutoTubeAI/2.1 "
                    "(https://github.com/lazyline/autotube; contact: autotube-ai@local.dev) "
                    "requests/2.31"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _thread_local.session = s
    return _thread_local.session


def _is_retryable_requests_error(exception):
    """Check if exception is an HTTP 429/5xx or network connection drop."""
    if isinstance(exception, requests.HTTPError) and exception.response is not None:
        return exception.response.status_code in (429, 500, 502, 503, 504)
    if isinstance(exception, (requests.ConnectionError, requests.Timeout)):
        return True
    return False



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

def build_queries(visual_description, narration=None):
    """
    Build highly relevant, concrete search queries derived from the visual concept
    and its assigned narration section.
    CRITICAL RULE: Never inject generic placeholders like 'technology news' or
    unrelated country names unless explicitly part of the subject.
    """
    clean_desc = re.sub(
        r"^(?:visual|scene|shot|image|photo|picture|graphic)\s*\d*\s*[:\-]\s*",
        "",
        visual_description.strip(),
        flags=re.IGNORECASE,
    ).strip()
    clean_desc = re.sub(
        r"^(photo|image|picture|illustration|graphic|close[- ]?up|shot|scene|view)\s+(of|showing|depicting|illustrating)?\s*",
        "",
        clean_desc,
        flags=re.IGNORECASE,
    ).strip()

    raw_words = [re.sub(r"[^\w\s-]", "", w).strip() for w in clean_desc.split()]
    desc_words = [
        w for w in raw_words
        if w and w.lower() not in {
            "the", "a", "an", "and", "or", "to", "of", "in", "on", "for",
            "at", "with", "from", "by", "visual", "concept", "representing",
            "scene", "shot", "image", "photo", "picture",
        } and len(w) > 1
    ]

    queries = []

    # Primary query: concise core visual concept (up to 7 words)
    primary = " ".join(desc_words[:7])
    if primary:
        queries.append(primary)

    # Secondary query: specific entity keywords from narration if available
    if narration:
        clean_narration = clean_text(narration)
        # Extract potential named entities / capitalized words from narration
        entities = [
            w for w in re.findall(r"\b[A-Z][a-zA-Z0-9-]+\b", clean_narration)
            if w.lower() not in {"this", "that", "these", "those", "when", "while", "here", "there"}
        ]
        if entities:
            entity_query = " ".join(entities[:4])
            if entity_query and entity_query not in queries:
                queries.append(entity_query)

    # Tertiary query: key nouns / subjects
    if len(desc_words) > 3:
        short_desc = " ".join(desc_words[:4])
        if short_desc not in queries:
            queries.append(short_desc)

    # Fallback to visual description if queries empty
    if not queries:
        queries.append(clean_desc[:60])

    final = []
    for q in queries:
        q = q.strip()
        if q and q not in final:
            final.append(q)

    return final


# ============================================================
# PEXELS HD STOCK IMAGE SEARCH
# ============================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8) + wait_random(0.1, 0.5),
    retry=retry_if_exception(_is_retryable_requests_error),
    reraise=False,
)
def search_pexels(query):
    """
    Search high-resolution royalty-free landscape stock photos via Pexels API.
    """
    global PEXELS_API_KEY
    if not PEXELS_API_KEY:
        PEXELS_API_KEY = get_pexels_api_key()

    if not PEXELS_API_KEY:
        return []

    url = "https://api.pexels.com/v1/search"

    headers = {
        "Authorization": PEXELS_API_KEY,
        "User-Agent": get_session().headers.get("User-Agent", "AutoTubeAI/2.1"),
    }

    params = {
        "query": query,
        "per_page": MAX_PEXELS_RESULTS,
        "orientation": "landscape",
    }

    try:

        response = get_session().get(
            url,
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        data = response.json()

    except Exception as error:

        print(
            f"Pexels search warning: {error}"
        )

        return []

    photos = data.get("photos", [])

    results = []

    for photo in photos:

        src = photo.get("src", {})

        image_url = (
            src.get("large2x")
            or src.get("large")
            or src.get("landscape")
            or src.get("original")
        )

        if not image_url:
            continue

        alt = photo.get("alt", "").strip()

        title = clean_text(alt) if alt else query

        results.append(
            {
                "image_url": image_url,
                "title": title,
                "source": "Pexels",
                "width": photo.get("width", 1920),
                "height": photo.get("height", 1080),
                "mime": "image/jpeg",
            }
        )

    return results


# ============================================================
# PEXELS HD STOCK VIDEO SEARCH (OPTIONAL VIDEO FOOTAGE)
# ============================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8) + wait_random(0.1, 0.5),
    retry=retry_if_exception(_is_retryable_requests_error),
    reraise=False,
)
def search_pexels_video(query):
    """
    Search high-quality royalty-free video footage via Pexels API.
    Tries multiple keyword variations to maximize matching relevant stock footage.
    Returns download url and metadata if a relevant HD video is found.
    """
    global PEXELS_API_KEY
    if not PEXELS_API_KEY:
        PEXELS_API_KEY = get_pexels_api_key()

    if not PEXELS_API_KEY:
        return None

    url = "https://api.pexels.com/videos/search"

    headers = {
        "Authorization": PEXELS_API_KEY,
        "User-Agent": get_session().headers.get("User-Agent", "AutoTubeAI/2.1"),
    }

    clean_q = re.sub(r"[^a-zA-Z0-9\s]", " ", query).strip()
    words = clean_q.split()
    search_terms = []
    if len(words) >= 4:
        search_terms.append(" ".join(words[:4]))
    if len(words) >= 3:
        search_terms.append(" ".join(words[:3]))
    if len(words) >= 2:
        search_terms.append(" ".join(words[:2]))
    if words:
        search_terms.append(words[0])

    for term in search_terms:
        if not term.strip():
            continue
        params = {
            "query": term,
            "per_page": 4,
            "orientation": "landscape",
        }
        try:
            resp = get_session().get(
                url,
                headers=headers,
                params=params,
                timeout=(3, 6),
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            videos = data.get("videos", [])
            if not videos:
                continue

            for vid in videos:
                files = vid.get("video_files", [])
                hd_files = [
                    f for f in files
                    if f.get("quality") == "hd" and (f.get("width") or 0) >= 1280
                ]
                if not hd_files:
                    hd_files = [f for f in files if (f.get("width") or 0) >= 640]
                if hd_files:
                    best_file = hd_files[0]
                    slug = re.sub(r"[^a-zA-Z0-9]+", "_", term.lower()).strip("_")[:30]
                    return {
                        "download_url": best_file.get("link"),
                        "title": slug,
                        "duration": vid.get("duration", 10),
                        "source": "Pexels Video",
                    }
        except Exception as err:
            continue

    return None


def extract_video_frame(video_path, image_dest):
    """Extract a representative keyframe from an MP4 video clip to use as image fallback & thumbnail."""
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            "00:00:01",
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-q:v",
            "2",
            str(image_dest),
        ]
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        return image_dest.exists() and image_dest.stat().st_size > 0
    except Exception:
        return False


def download_video_clip(video_info, destination):
    """Safely download video footage with timeout."""
    url = video_info.get("download_url")
    if not url:
        return False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with get_session().get(url, timeout=(4, 12), stream=True) as resp:
            resp.raise_for_status()
            with open(destination, "wb") as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
        return destination.exists() and destination.stat().st_size > 10000
    except Exception as e:
        print(f"Video download warning: {e}")
        destination.unlink(missing_ok=True)
        return False


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

        response = get_session().get(
            url,
            params=params,
            timeout=(3, REQUEST_TIMEOUT),
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

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8) + wait_random(0.1, 0.5),
    retry=retry_if_exception(_is_retryable_requests_error),
    reraise=False,
)
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

        response = get_session().get(
            url,
            params=params,
            timeout=(3, REQUEST_TIMEOUT),
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

    if candidate.get("source") == "Pexels":
        score += 8

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

        with get_session().get(
            url,
            timeout=(3, REQUEST_TIMEOUT),
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
        # Pexels (HD Stock Photos)
        # ----------------------------------------------------

        pexels = search_pexels(
            query
        )

        for candidate in pexels:

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

        # Early exit if we already have plenty of candidates
        if len(candidates) >= TARGET_IMAGES * 2:
            print(f"Collected {len(candidates)} candidates, stopping search early.")
            break

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
            f"{TARGET_IMAGES} images downloaded from web. Applying offline fallback pool..."
        )
        fallback_pool = sorted(FALLBACK_DIR.glob("*.jpg")) if FALLBACK_DIR.exists() else []
        for i in range(downloaded + 1, TARGET_IMAGES + 1):
            dest = ASSETS_DIR / f"{i}.jpg"
            if fallback_pool:
                src = fallback_pool[(i - 1) % len(fallback_pool)]
                import shutil
                shutil.copyfile(src, dest)
                print(f"  ✓ Applied fallback image {src.name} -> {i}.jpg")
                downloaded += 1
            else:
                img = Image.new("RGB", (1280, 720), color=(25, 30, 45))
                img.save(dest, "JPEG", quality=90)
                downloaded += 1

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

@autonomous_recover("image_agent")
def download_images_from_visual_plan(
    visual_plan_path,
    flyer_path=None,
    feedback=None,
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
            if not line_text:
                continue

            cleaned = re.sub(r"^[\*\-\#\>\s]+", "", line_text).strip()
            match = re.match(
                r"^(?:\*?\*?visual\s*)?(\d+)[\.\)\:\-]\*?\*?\s*(.+)$",
                cleaned,
                re.IGNORECASE,
            )
            if match:
                visual = match.group(2).strip().strip("*").strip()
                if visual:
                    visuals.append(visual)
            elif cleaned and len(cleaned) > 10 and not cleaned.lower().startswith("visual plan"):
                visuals.append(cleaned)

    # Fallback to section map or script if visual plan had < 4 concepts
    if len(visuals) < 4:
        section_map_file = OUTPUT_DIR / "section_map.txt"
        if section_map_file.exists():
            try:
                sec_text = section_map_file.read_text(encoding="utf-8")
                pattern = re.compile(
                    r"SECTION\s+(\d+)\s*\|\s*VISUAL\s+(\d+)\s*\n(.*?)(?=\n\s*SECTION\s+\d+\s*\|\s*VISUAL\s+\d+|\Z)",
                    re.DOTALL | re.IGNORECASE,
                )
                for m in pattern.finditer(sec_text):
                    narration = m.group(3).strip()
                    if narration:
                        words = narration.split()
                        visuals.append(" ".join(words[:8]))
            except Exception:
                pass

    if len(visuals) < 4:
        topic_preview = visuals[0] if visuals else "news story"
        while len(visuals) < 4:
            visuals.append(f"{topic_preview} scene {len(visuals) + 1}")

    target_count = len(visuals)

    # Load section narrations if available for targeted context
    section_map_file = OUTPUT_DIR / "section_map.txt"
    section_narrations = {}
    if section_map_file.exists():
        try:
            sec_text = section_map_file.read_text(encoding="utf-8")
            pattern = re.compile(
                r"SECTION\s+(\d+)\s*\|\s*VISUAL\s+(\d+)\s*\n(.*?)(?=\n\s*SECTION\s+\d+\s*\|\s*VISUAL\s+\d+|\Z)",
                re.DOTALL | re.IGNORECASE,
            )
            for m in pattern.finditer(sec_text):
                v_num = int(m.group(2))
                section_narrations[v_num] = m.group(3).strip()
        except Exception:
            pass

    # ========================================================
    # DOWNLOAD ONE IMAGE FOR EACH VISUAL DESCRIPTION
    # ========================================================

    line()
    print("AI VISUAL-PLAN IMAGE & VIDEO SEARCH")
    line()

    clean_assets()

    used_hashes = set()
    hash_lock = threading.Lock()

    def process_single_visual(visual_tuple):
        visual_number, visual_query = visual_tuple
        destination = ASSETS_DIR / f"{visual_number}.jpg"
        video_dest = ASSETS_DIR / f"{visual_number}.mp4"

        # Dedicated uploaded flyer for final visual
        if visual_number == target_count and flyer_path:
            print(f"Using uploaded flyer as dedicated final Visual {target_count}.")
            if save_flyer_fallback(flyer_path, destination):
                return visual_number, destination

        assigned_narration = section_narrations.get(visual_number, "")
        queries = build_queries(
            visual_query,
            narration=assigned_narration,
        )

        # Targeted Self-Healing: adjust keywords based on review feedback
        if feedback:
            extra_words = [
                w for w in re.findall(r"\b[A-Za-z]{4,}\b", str(feedback))
                if w.lower() not in {"visual", "mismatch", "image", "resolution", "section", "agent", "quality", "failing"}
            ]
            if extra_words:
                queries.insert(0, f"{visual_query} {' '.join(extra_words[:2])}")

        # 1. Search for real video clip on Pexels first
        has_video = False
        if PEXELS_API_KEY and visual_number <= target_count:
            for q in queries[:3]:
                try:
                    video_info = search_pexels_video(q)
                    if video_info and video_info.get("download_url"):
                        print(f"🎥 Found Pexels video footage for Visual {visual_number} ('{q}'): {video_info.get('title')}")
                        if download_video_clip(video_info, video_dest):
                            has_video = True
                            print(f"✅ Video clip saved: assets/{visual_number}.mp4")
                            # Extract preview keyframe as .jpg for thumbnail and image fallback
                            extract_video_frame(video_dest, destination)
                            break
                except Exception as v_err:
                    print(f"Video search note for Visual {visual_number}: {v_err}")

        # 2. Always ensure a fallback image exists
        if not destination.exists():
            candidates = collect_candidates(queries)
            for candidate in candidates:
                success = download_image(candidate, destination)
                if not success:
                    continue

                file_hash = image_hash(destination)
                with hash_lock:
                    if file_hash and file_hash in used_hashes:
                        destination.unlink(missing_ok=True)
                        continue
                    if file_hash:
                        used_hashes.add(file_hash)

                print(f"OK - Visual {visual_number} saved as {visual_number}.jpg")
                break

        if has_video and video_dest.exists():
            return visual_number, video_dest
        elif destination.exists():
            return visual_number, destination

        return visual_number, None

    # Requirement 2.1: Restrict concurrent outgoing requests to max 3 workers
    workers = min(3, target_count)
    print(f"Downloading {target_count} visuals in parallel with {workers} worker threads (concurrency limited to max 3)...")
    results_map = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_single_visual, (num, q)): num
            for num, q in enumerate(visuals, start=1)
        }
        for future in as_completed(futures):
            num = futures[future]
            try:
                v_num, dest = future.result(timeout=25)
                if dest and dest.exists():
                    results_map[v_num] = dest
            except Exception as e:
                print(f"Visual {num} download warning: {e}")

    # Requirement 2.3: Offline Fallback Media Pool
    fallback_pool_images = sorted(FALLBACK_DIR.glob("*.jpg")) if FALLBACK_DIR.exists() else []
    fallback_pool_videos = sorted(FALLBACK_DIR.glob("*.mp4")) if FALLBACK_DIR.exists() else []

    for num in range(1, target_count + 1):
        dest = ASSETS_DIR / f"{num}.jpg"
        video_dest = ASSETS_DIR / f"{num}.mp4"
        if num not in results_map or not dest.exists():
            print(f"Warning: Applying offline fallback pool for Visual {num}.")
            import shutil
            applied = False

            # Check offline fallback media pool first
            if fallback_pool_videos or fallback_pool_images:
                pool_idx = (num - 1)
                if fallback_pool_videos:
                    src_vid = fallback_pool_videos[pool_idx % len(fallback_pool_videos)]
                    shutil.copyfile(src_vid, video_dest)
                    extract_video_frame(video_dest, dest)
                    results_map[num] = video_dest
                    applied = True
                    print(f"  ✓ Applied fallback video {src_vid.name} -> {num}.mp4 and extracted frame")
                elif fallback_pool_images:
                    src_img = fallback_pool_images[pool_idx % len(fallback_pool_images)]
                    shutil.copyfile(src_img, dest)
                    results_map[num] = dest
                    applied = True
                    print(f"  ✓ Applied fallback image {src_img.name} -> {num}.jpg")

            if not applied:
                if results_map:
                    first_valid = next(iter(results_map.values()))
                    if first_valid.suffix.lower() in (".mp4", ".mov", ".webm"):
                        if not extract_video_frame(first_valid, dest):
                            img = Image.new("RGB", (1280, 720), color=(25, 30, 45))
                            img.save(dest, "JPEG", quality=90)
                    else:
                        shutil.copyfile(first_valid, dest)
                elif flyer_path and save_flyer_fallback(flyer_path, dest):
                    pass
                else:
                    img = Image.new("RGB", (1280, 720), color=(25, 30, 45))
                    img.save(dest, "JPEG", quality=90)
                results_map[num] = dest

    final_images = [results_map[num] for num in range(1, target_count + 1)]

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    for number in range(1, target_count + 1):
        path = ASSETS_DIR / f"{number}.jpg"
        vid_path = ASSETS_DIR / f"{number}.mp4"
        if not path.exists() or path.stat().st_size == 0:
            if vid_path.exists():
                extract_video_frame(vid_path, path)
            if not path.exists() or path.stat().st_size == 0:
                if fallback_pool_images:
                    src_fallback = fallback_pool_images[(number - 1) % len(fallback_pool_images)]
                    import shutil
                    shutil.copyfile(src_fallback, path)
                    print(f"[Self-Healing] Sourced missing {number}.jpg from fallback {src_fallback.name}")
                else:
                    img = Image.new("RGB", (1280, 720), color=(25, 30, 45))
                    img.save(path, "JPEG", quality=90)
                    print(f"[Self-Healing] Created placeholder for missing {number}.jpg")

    final_images = [
        ASSETS_DIR / f"{number}.jpg"
        for number in range(1, target_count + 1)
    ]

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
            target_count + 1,
        )
    ]

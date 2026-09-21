import html
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
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

WIKIMEDIA_DELAY = 0.05


def get_image_filename(image_input):
    """
    Safely extract filename from UploadedFile, Path, or str.
    Completely eliminates "'str' object has no attribute 'name'".
    """
    if hasattr(image_input, "name"):
        return image_input.name
    elif isinstance(image_input, str):
        return os.path.basename(image_input)
    elif isinstance(image_input, Path):
        return image_input.name
    raise TypeError(f"Unexpected image input type: {type(image_input)}")


# ============================================================
# SIGLIP 2 VISUAL RELEVANCE & FLUX PROMPT REWRITING
# ============================================================

_SIGLIP_MODEL = None
_SIGLIP_PROCESSOR = None

def get_siglip_pipeline():
    global _SIGLIP_MODEL, _SIGLIP_PROCESSOR
    if _SIGLIP_MODEL is None or _SIGLIP_PROCESSOR is None:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer, SiglipImageProcessor, SiglipProcessor

            model_id = "google/siglip2-so400m-patch14-384"
            try:
                tok = AutoTokenizer.from_pretrained(model_id)
                img_proc = SiglipImageProcessor.from_pretrained(model_id)
                _SIGLIP_PROCESSOR = SiglipProcessor(image_processor=img_proc, tokenizer=tok)
                _SIGLIP_MODEL = AutoModel.from_pretrained(model_id, dtype=torch.float32)
                _SIGLIP_MODEL.eval()
            except Exception as e:
                print(f"[SigLIP2] Fallback to base model: {e}")
                tok = AutoTokenizer.from_pretrained("google/siglip2-base-patch16-224")
                img_proc = SiglipImageProcessor.from_pretrained("google/siglip2-base-patch16-224")
                _SIGLIP_PROCESSOR = SiglipProcessor(image_processor=img_proc, tokenizer=tok)
                _SIGLIP_MODEL = AutoModel.from_pretrained("google/siglip2-base-patch16-224", dtype=torch.float32)
                _SIGLIP_MODEL.eval()
        except Exception as import_err:
            print(f"[SigLIP2] Notice: SigLIP model not loaded ({import_err}). Using heuristic relevance.")
            return None, None

    return _SIGLIP_MODEL, _SIGLIP_PROCESSOR

RELEVANCE_THRESHOLD = 0.05  # Calibrated SigLIP 2 threshold: rejects completely off-topic visuals (prob < 0.005) while accepting matching stock (prob > 0.05)

def score_visual_relevance(image_path: str, query_text: str) -> float:
    """
    SigLIP 2 visual relevance scorer (google/siglip2-so400m-patch14-384).
    Calculates zero-shot relevance probability (0.0 to 1.0) against an off-topic anchor.
    Accepts if > RELEVANCE_THRESHOLD (0.05).
    """
    try:
        model, processor = get_siglip_pipeline()
        if model is None or processor is None:
            return 0.50
        import torch
        image = Image.open(image_path).convert("RGB")
        unrelated_anchor = "unrelated off-topic random photo"
        inputs = processor(
            text=[query_text[:120], unrelated_anchor],
            images=image,
            padding="max_length",
            return_tensors="pt"
        )
        with torch.no_grad():
            outputs = model(**inputs)
            # Softmax against negative anchor yields normalized probability in [0, 1]
            prob = torch.softmax(outputs.logits_per_image, dim=-1)[0, 0].item()
        return float(prob)
    except Exception as e:
        print(f"score_visual_relevance notice: {e}")
        return 0.50


def rewrite_query_for_flux(query_text: str, is_explainer: bool = False) -> str:
    """Turn a search query into a concrete FLUX prompt.
    If is_explainer=True, bias heavily toward diagrams, infographic style, and animated concept illustration."""
    if is_explainer:
        explainer_bias = "diagram, infographic style, animated concept illustration, clean minimalist educational schematic, high visual clarity, isometric vector design"
        try:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                client = genai.Client(api_key=api_key)
                prompt = (
                    f"Rewrite this video scene query into a clean, modern technical diagram, infographic style, animated concept illustration description in 1 sentence. "
                    f"Focus on educational schematics, isometric concept visuals, high clarity, and infographic breakdown.\n"
                    f"Scene query: {query_text}\n"
                    f"Rewritten prompt:"
                )
                for m_name in ["gemini-2.5-flash-lite", "gemini-3.6-flash", "gemini-flash-lite-latest"]:
                    try:
                        response = client.models.generate_content(
                            model=m_name,
                            contents=prompt,
                        )
                        rewritten = response.text.strip().replace('"', '')
                        if len(rewritten.split()) >= 4:
                            return f"{rewritten}, {explainer_bias}"
                    except Exception:
                        continue
        except Exception as err:
            print(f"Gemini explainer prompt rewrite notice: {err}")
        return f"{query_text}, {explainer_bias}"

    if len(query_text.split()) >= 6:
        return query_text
    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            client = genai.Client(api_key=api_key)
            prompt = (
                f"Rewrite this video search query into a concrete, filmable, photorealistic image description in 1 sentence. "
                f"Do not include brand logos, cartoon hands, or abstract graphics. "
                f"Focus strictly on physical objects, lighting, and camera angle.\n"
                f"Query to rewrite: {query_text}\n"
                f"Rewritten prompt:"
            )
            for m_name in ["gemini-2.5-flash-lite", "gemini-3.6-flash", "gemini-flash-lite-latest"]:
                try:
                    response = client.models.generate_content(
                        model=m_name,
                        contents=prompt,
                    )
                    rewritten = response.text.strip().replace('"', '')
                    if len(rewritten.split()) >= 4:
                        return rewritten
                except Exception:
                    continue
    except Exception as err:
        print(f"Gemini prompt rewrite notice: {err}")
    return f"cinematic photography of {query_text}, ultra detailed, studio lighting, 8k"


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
# NAMED PRODUCT / BRAND DETECTION
# ============================================================

def detect_named_product(text):
    """
    Detect if text mentions a specific commercial hardware/device/vehicle product
    (e.g., iPhone 18, Samsung Galaxy S25, Tesla Model 2, RTX 5090, PS6).
    Returns:
        (is_product: bool, product_name: str, generic_fallback_prompt: str)
    """
    if not text:
        return False, "", ""

    lower_text = str(text).lower()

    PRODUCT_RULES = [
        # Apple iPhone
        (
            r"\b(iphone\s*(?:1[0-9]|[2-9][0-9]|[a-z]+)?(?:\s*(?:pro\s*max|pro|plus|mini|ultra|air|se))?)\b",
            "modern flagship smartphone sleek camera close-up on dark table",
        ),
        # Apple iPad / Mac / Watch / Vision
        (
            r"\b(ipad\s*(?:pro|air|mini)?(?:\s*m[1-4])?)\b",
            "modern sleek tablet computer touchscreen display on desk",
        ),
        (
            r"\b(macbook\s*(?:pro|air)?(?:\s*m[1-4](?:\s*pro|\s*max)?)?)\b",
            "sleek aluminum laptop computer open keyboard screen on office desk",
        ),
        (
            r"\b(apple\s*watch\s*(?:series\s*\d+|ultra\s*\d*|se)?)\b",
            "modern smart watch fitness tracker wrist closeup",
        ),
        (
            r"\b(vision\s*pro(?:\s*2)?)\b",
            "futuristic virtual reality spatial computing headset visor",
        ),
        # Samsung Galaxy
        (
            r"\b(samsung\s*galaxy\s*(?:s\d+|z\s*fold\d*|z\s*flip\d*|note\d*)(?:\s*ultra|\s*plus|\s*fe)?)\b",
            "high-end modern android smartphone curved screen display",
        ),
        (
            r"\b(galaxy\s*(?:s\d+|z\s*fold\d*|z\s*flip\d*)(?:\s*ultra|\s*plus)?)\b",
            "high-end modern android smartphone curved screen display",
        ),
        # Google Pixel
        (
            r"\b(google\s*pixel\s*\d+(?:\s*pro|\s*a|\s*fold)?)\b",
            "modern sleek android smartphone camera bar close-up",
        ),
        (
            r"\b(pixel\s*\d+(?:\s*pro|\s*a|\s*fold)?)\b",
            "modern sleek android smartphone camera bar close-up",
        ),
        # Gaming Consoles
        (
            r"\b(playstation\s*[4-6](?:\s*(?:pro|slim))?|ps[4-6](?:\s*(?:pro|slim))?)\b",
            "modern gaming console controller glowing neon lights living room",
        ),
        (
            r"\b(xbox\s*(?:series\s*[xs]|one\s*[xs]?))\b",
            "sleek black gaming console gamepad modern entertainment setup",
        ),
        (
            r"\b(nintendo\s*switch(?:\s*oled|\s*2)?)\b",
            "portable handheld gaming console colorful joycon controllers",
        ),
        # GPUs & Processors
        (
            r"\b(rtx\s*\d{4}(?:\s*ti|\s*super)?|geforce\s*rtx\s*\d{4})\b",
            "high performance computer graphics card gpu cooling fans circuit board",
        ),
        (
            r"\b(snapdragon\s*\d+\s*(?:gen\s*\d+)?|intel\s*core\s*(?:ultra\s*)?\d+|ryzen\s*\d{4}[x]?)\b",
            "semiconductor microchip silicon wafer glowing circuit processor closeup",
        ),
        # Tesla & EVs
        (
            r"\b(tesla\s*(?:cybertruck|model\s*[3ysx]|roadster))\b",
            "futuristic aerodynamic luxury electric vehicle driving highway",
        ),
        (
            r"\b(cybertruck)\b",
            "angular stainless steel electric pickup truck exterior view",
        ),
        # OnePlus, Xiaomi, Vivo, Oppo, iQOO, Nothing
        (
            r"\b((?:oneplus|xiaomi|redmi|realme|vivo|oppo|iqoo|nothing\s*phone)\s*(?:[a-z]\s*)?\d+[a-z]*(?:\s*(?:pro\s*plus|pro\s*max|pro|ultra|plus|lite|neo))?)\b",
            "modern flagship smartphone sleek camera close-up",
        ),
    ]

    for pattern, generic_cat in PRODUCT_RULES:
        m = re.search(pattern, lower_text)
        if m:
            matched_name = m.group(1).title()
            return True, matched_name, generic_cat

    return False, "", ""


# ============================================================
# SEARCH QUERIES
# ============================================================

def build_queries(visual_description, narration=None):
    """
    Build highly relevant, concrete search queries derived from the visual concept
    (including multi-query alternatives separated by '|') and its assigned narration section.
    CRITICAL RULE: Never inject generic placeholders like 'technology news' or
    unrelated country names unless explicitly part of the subject.
    """
    raw_segments = [seg.strip() for seg in str(visual_description).split("|") if seg.strip()]
    if not raw_segments:
        raw_segments = [str(visual_description)]

    queries = []

    # If visual description contains non-Latin characters (e.g. Telugu), map to English queries
    if re.search(r"[\u0c00-\u0c7f]", str(visual_description)):
        try:
            from semantic_broll_mapper import generate_search_queries
            mapped_qs = generate_search_queries(str(visual_description), topic_category="tech")
            if mapped_qs:
                queries.extend(mapped_qs)
        except Exception:
            pass

    for seg in raw_segments:
        clean_desc = re.sub(
            r"^(?:visual|scene|shot|image|photo|picture|graphic)\s*\d*\s*[:\-]\s*",
            "",
            seg.strip(),
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

        if len(desc_words) >= 2:
            punchy = " ".join(desc_words[:3])
            if punchy not in queries:
                queries.append(punchy)

        primary = " ".join(desc_words[:5])
        if primary and primary not in queries:
            queries.append(primary)

    # Entity keywords from narration if available
    if narration:
        clean_narration = clean_text(narration)
        entities = [
            w for w in re.findall(r"\b[A-Z][a-zA-Z0-9-]+\b", clean_narration)
            if w.lower() not in {"this", "that", "these", "those", "when", "while", "here", "there", "section"}
        ]
        if entities:
            entity_query = " ".join(entities[:3])
            if entity_query and entity_query not in queries:
                queries.append(entity_query)

    if not queries:
        queries.append(visual_description[:60].replace("|", " ").strip())

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
def search_pexels(query, orientation=None):
    """
    Search high-resolution royalty-free stock photos via Pexels API with dynamic orientation.
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
    }
    if orientation in ("landscape", "portrait", "square"):
        params["orientation"] = orientation

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

        photo_id = photo.get("id")
        alt = photo.get("alt", "").strip()
        title = clean_text(alt) if alt else query
        tags = [w.lower() for w in re.findall(r"\b\w+\b", alt)]

        results.append(
            {
                "id": f"pexels_{photo_id}" if photo_id else None,
                "image_url": image_url,
                "title": title,
                "alt": alt,
                "tags": tags,
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
def search_pexels_video(query, orientation=None):
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
            "per_page": 6,
        }
        if orientation in ("landscape", "portrait", "square"):
            params["orientation"] = orientation
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

            from agents.visual_verifier import rank_video_candidates
            best_clip = rank_video_candidates(videos, query=term, orientation=orientation)
            if best_clip:
                vid_id = f"pexels_video_{best_clip.get('id', '')}"
                vid_tags = best_clip.get("title", "").split()
                try:
                    from semantic_broll_mapper import is_result_allowed, is_asset_fresh
                    if not is_result_allowed(vid_tags, topic_category="tech"):
                        print(f"❌ Filtered out off-topic video: {best_clip.get('title', '')[:40]}")
                        continue
                    if not is_asset_fresh(vid_id):
                        print(f"🔄 Skipped recently used video (30-day history): {vid_id}")
                        continue
                except Exception:
                    pass
                return best_clip
        except Exception as err:
            continue

    return None


def extract_video_frame(video_path, image_dest):
    """Extract a representative keyframe from an MP4 video clip to use as image fallback & thumbnail."""
    try:
        dest = Path(image_dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
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
            str(dest),
        ]
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        return dest.exists() and dest.stat().st_size > 0
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

def collect_candidates(queries, orientation=None, topic_category="tech"):

    candidates = []

    seen_urls = set()

    try:
        from semantic_broll_mapper import is_result_allowed, is_asset_fresh
    except ImportError:
        is_result_allowed = lambda tags, cat: True
        is_asset_fresh = lambda aid: True

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
            query,
            orientation=orientation,
        )

        for candidate in pexels:

            url = candidate.get(
                "image_url"
            )

            if not url:
                continue

            if url in seen_urls:
                continue

            # Negative keyword check & asset freshness
            cand_tags = candidate.get("tags") or candidate.get("title", "").split()
            if not is_result_allowed(cand_tags, topic_category):
                print(f"❌ Filtered out off-topic candidate ({topic_category} negative match): {candidate.get('title', '')[:40]}")
                continue

            cid = candidate.get("id")
            if cid and not is_asset_fresh(cid):
                print(f"🔄 Skipped recently used asset (30-day history): {cid}")
                continue

            if not is_relevant(
                candidate,
                query,
            ):
                continue

            seen_urls.add(url)

            candidates.append(candidate)

        # ----------------------------------------------------
        # DuckDuckGo (Free Web Photography - No Key Required)
        # ----------------------------------------------------
        try:
            from providers.image import search_duckduckgo_images
            ddg_items = search_duckduckgo_images(query, max_results=8)
            for candidate in ddg_items:
                url = candidate.get("image_url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                candidates.append(candidate)
        except Exception as ddg_err:
            pass

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
        # Pixabay (Optional Free API Key)
        # ----------------------------------------------------
        try:
            from providers.image import search_pixabay
            pix_items = search_pixabay(query, orientation=orientation or "landscape", max_results=6)
            for candidate in pix_items:
                url = candidate.get("image_url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                candidates.append(candidate)
        except Exception:
            pass

        # ----------------------------------------------------
        # Bing Fallback
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
                print(f"  ✓ Applied fallback image {get_image_filename(src)} -> {i}.jpg")
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
    aspect_ratio="16:9",
    generation_mode="stock",
    user_assets=None,
    user_assets_map=None,
    *args,
    **kwargs,
):

    visual_plan_file = Path(
        visual_plan_path
    )

    if not visual_plan_file.exists():
        raise FileNotFoundError(
            f"Visual plan not found: "
            f"{visual_plan_file}"
        )

    # Derive orientation matching the requested aspect ratio
    orientation = "landscape"
    if aspect_ratio == "9:16":
        orientation = "portrait"
    elif aspect_ratio == "1:1":
        orientation = "square"

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

    # Mode 2: If user provided their own media, map them and bypass stock search
    is_user_mode = (
        generation_mode in ("user_media", "My Own Images/Videos", "📁 My Own Images/Videos")
        or (user_assets and len(user_assets) > 0 and generation_mode not in ("stock", "🎬 AI Stock Search"))
    )
    if is_user_mode:
        print("📁 [Multi-Mode] User Media Mode active. Mapping scenes directly to user footage...")
        clean_assets()
        try:
            from agents.multimode_agent import map_script_to_user_assets, apply_user_assets_to_visuals
            mapped = user_assets_map or map_script_to_user_assets(visuals, user_assets)
            applied = apply_user_assets_to_visuals(mapped, ASSETS_DIR)
            print(f"✅ Applied {len(applied)} user media assets directly to visual timeline.")
            from agents.video_agent import ensure_visual_assets_exist
            ensure_visual_assets_exist()
            return [(i, ASSETS_DIR / f"{i}.mp4" if (ASSETS_DIR / f"{i}.mp4").exists() else ASSETS_DIR / f"{i}.jpg") for i in range(1, target_count + 1)]
        except Exception as u_err:
            print(f"User media mapping warning: {u_err}. Falling back to standard visual sourcing.")

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
    claimed_urls = set()
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

        # Mode 3: Explainer Style Query Transformation
        if generation_mode in ("explainer", "Explainer Style", "📊 Explainer Style"):
            try:
                from agents.multimode_agent import transform_queries_for_explainer
                queries = transform_queries_for_explainer(queries)
            except Exception:
                pass

        # Semantic B-roll mapper: convert brands/abstractions to filmable English stock search queries
        try:
            from semantic_broll_mapper import generate_search_queries
            semantic_qs = generate_search_queries(
                chunk=f"{visual_query}. {assigned_narration}"[:250],
                topic_category="tech",
            )
            for sq in semantic_qs:
                if sq not in queries:
                    queries.insert(1, sq)
        except Exception:
            pass

        # Targeted Self-Healing: adjust keywords based on review feedback
        if feedback:
            extra_words = [
                w for w in re.findall(r"\b[A-Za-z]{4,}\b", str(feedback))
                if w.lower() not in {"visual", "mismatch", "image", "resolution", "section", "agent", "quality", "failing"}
            ]
            if extra_words:
                queries.insert(0, f"{visual_query} {' '.join(extra_words[:2])}")

        # Check if this visual is discussing a specific named commercial product (e.g. iPhone 18)
        is_prod, prod_name, generic_cat = detect_named_product(f"{visual_query} {assigned_narration}")

        if is_prod:
            print(f"📱 Detected commercial product for Visual {visual_number}: '{prod_name}'. Sourcing scene-targeted web photography...")
            try:
                from providers.image import search_web_product_images
                # Pass both product name and specific scene query to get scene-specific imagery
                prod_candidates = search_web_product_images(prod_name, scene_query=visual_query, max_results=14)
                if len(prod_candidates) < 3:
                    clean_q = re.sub(r"^(?:\d+[\.\:\-]\s*|(?:visual|scene|shot)\s*\d*[\.\:\-]?\s*)", "", str(visual_query), flags=re.IGNORECASE).strip()
                    for b_cand in search_bing(f"{prod_name} {clean_q}")[:6]:
                        b_url = b_cand.get("image_url")
                        if b_url and b_url not in [c.get("image_url") for c in prod_candidates]:
                            b_cand["source"] = "Web Product Photography (Editorial Fair-Use)"
                            b_cand["is_editorial"] = True
                            b_cand["product_name"] = prod_name
                            prod_candidates.append(b_cand)

                for candidate in prod_candidates:
                    cand_url = candidate.get("image_url")
                    if not cand_url:
                        continue

                    # Atomic check to prevent two scenes from claiming the same image URL
                    with hash_lock:
                        if cand_url in claimed_urls:
                            continue
                        claimed_urls.add(cand_url)

                    success = download_image(candidate, destination)
                    if not success:
                        with hash_lock:
                            claimed_urls.discard(cand_url)
                        continue

                    # Validation: verify with PIL
                    try:
                        with Image.open(destination) as img:
                            w, h = img.size
                            if w < 400 or h < 300:
                                destination.unlink(missing_ok=True)
                                with hash_lock:
                                    claimed_urls.discard(cand_url)
                                continue
                    except Exception:
                        destination.unlink(missing_ok=True)
                        with hash_lock:
                            claimed_urls.discard(cand_url)
                        continue

                    # SigLIP 2 relevance check: ensure product image matches scene context (rejects off-topic portraits/selfies)
                    rel_score = score_visual_relevance(str(destination), f"{prod_name} {visual_query}")
                    if rel_score < RELEVANCE_THRESHOLD:
                        print(f"⚠️ Product photo candidate rejected (SigLIP 2 score {rel_score:.4f} < {RELEVANCE_THRESHOLD}): '{cand_url[:60]}'")
                        destination.unlink(missing_ok=True)
                        with hash_lock:
                            claimed_urls.discard(cand_url)
                        continue

                    file_hash = image_hash(destination)
                    with hash_lock:
                        if file_hash and file_hash in used_hashes:
                            destination.unlink(missing_ok=True)
                            claimed_urls.discard(cand_url)
                            continue
                        if file_hash:
                            used_hashes.add(file_hash)

                    print(f"✅ Visual {visual_number} saved unique product photography for '{prod_name}' (Scene: '{visual_query[:40]}', SigLIP 2 score: {rel_score:.4f})")
                    break
            except Exception as p_err:
                print(f"Product web search notice for Visual {visual_number}: {p_err}")

            if destination.exists():
                return visual_number, destination

        # 1. Search for real video clip on Pexels first (for dynamic B-roll)
        has_video = False
        primary_q = visual_query.split("|")[0].strip()

        if PEXELS_API_KEY and visual_number <= target_count:
            for q in queries[:3]:
                try:
                    video_info = search_pexels_video(q, orientation=orientation)
                    v_url = video_info.get("download_url") if video_info else None
                    if video_info and v_url:
                        with hash_lock:
                            if v_url in claimed_urls:
                                continue
                            claimed_urls.add(v_url)

                        print(f"🎥 Found Pexels video footage for Visual {visual_number} ('{q}'): {video_info.get('title')}")
                        if download_video_clip(video_info, video_dest):
                            extract_video_frame(video_dest, destination)
                            v_score = score_visual_relevance(destination, primary_q)
                            print(f"🎥 Pexels video frame SigLIP 2 score for Visual {visual_number}: {v_score:.4f} (Threshold: {RELEVANCE_THRESHOLD})")
                            if v_score >= RELEVANCE_THRESHOLD:
                                has_video = True
                                print(f"✅ Video clip verified and accepted: assets/{visual_number}.mp4")
                                try:
                                    from semantic_broll_mapper import mark_asset_used
                                    mark_asset_used(f"pexels_video_{video_info.get('id', '')}")
                                except Exception:
                                    pass
                                break
                            else:
                                print(f"❌ Video clip rejected (low SigLIP 2 score {v_score:.4f} < {RELEVANCE_THRESHOLD}): {video_info.get('title')}")
                                video_dest.unlink(missing_ok=True)
                                destination.unlink(missing_ok=True)
                                with hash_lock:
                                    claimed_urls.discard(v_url)
                except Exception as v_err:
                    print(f"Video search note for Visual {visual_number}: {v_err}")

        # 2. Search and verify stock image candidates with SigLIP 2 relevance
        if not destination.exists():
            candidates = collect_candidates(queries, orientation=orientation)
            for candidate in candidates:
                cand_url = candidate.get("image_url")
                if not cand_url:
                    continue

                with hash_lock:
                    if cand_url in claimed_urls:
                        continue
                    claimed_urls.add(cand_url)

                success = download_image(candidate, destination)
                if not success:
                    with hash_lock:
                        claimed_urls.discard(cand_url)
                    continue

                score = score_visual_relevance(destination, primary_q)
                if score < RELEVANCE_THRESHOLD:
                    print(f"⚠️ Stock candidate rejected (SigLIP 2 score {score:.4f} < {RELEVANCE_THRESHOLD}): {candidate.get('title', '')[:30]}")
                    destination.unlink(missing_ok=True)
                    with hash_lock:
                        claimed_urls.discard(cand_url)
                    continue

                file_hash = image_hash(destination)
                with hash_lock:
                    if file_hash and file_hash in used_hashes:
                        destination.unlink(missing_ok=True)
                        claimed_urls.discard(cand_url)
                        continue
                    if file_hash:
                        used_hashes.add(file_hash)

                print(f"OK - Visual {visual_number} verified (SigLIP 2 score {score:.4f} >= {RELEVANCE_THRESHOLD}) saved as {visual_number}.jpg")
                try:
                    from semantic_broll_mapper import mark_asset_used
                    if candidate.get("id"):
                        mark_asset_used(candidate["id"])
                except Exception:
                    pass
                break

        # 3. Pollinations.ai FLUX AI Generative Fallback (Tailored directly to the specific scene)
        if not destination.exists():
            try:
                from providers.image import generate_pollinations_image
                is_expl = generation_mode in ("explainer", "Explainer Style", "📊 Explainer Style")
                flux_prompt = rewrite_query_for_flux(f"{primary_q} {assigned_narration[:80]}", is_explainer=is_expl)
                print(f"✨ Sourcing Pollinations FLUX AI visual for Scene {visual_number}: '{flux_prompt[:70]}...'")
                if generate_pollinations_image(flux_prompt, destination, aspect_ratio=aspect_ratio):
                    file_hash = image_hash(destination)
                    with hash_lock:
                        if file_hash and file_hash not in used_hashes:
                            used_hashes.add(file_hash)
                            print(f"✅ Generated Pollinations FLUX image accepted for Visual {visual_number}: assets/{visual_number}.jpg")
                        elif file_hash in used_hashes:
                            destination.unlink(missing_ok=True)
            except Exception as ai_err:
                print(f"Pollinations AI fallback notice for Visual {visual_number}: {ai_err}")

        if has_video and video_dest.exists():
            return visual_number, video_dest
        elif destination.exists():
            return visual_number, destination

        return visual_number, None

    # Parallel download workers (optimized for high throughput)
    workers = min(5, target_count)
    print(f"Downloading {target_count} visuals in parallel with {workers} worker threads...")
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

    # Fallback Handling: Dynamic FLUX first before static offline fallback pool
    fallback_pool_images = sorted(FALLBACK_DIR.glob("*.jpg")) if FALLBACK_DIR.exists() else []
    fallback_pool_videos = sorted(FALLBACK_DIR.glob("*.mp4")) if FALLBACK_DIR.exists() else []

    for num in range(1, target_count + 1):
        dest = ASSETS_DIR / f"{num}.jpg"
        video_dest = ASSETS_DIR / f"{num}.mp4"
        if num not in results_map or not dest.exists():
            applied = False
            # 1. Attempt dynamic FLUX generation for the specific scene concept
            try:
                from providers.image import generate_pollinations_image
                prompt_q = visuals[num - 1] if num - 1 < len(visuals) else "cinematic visual scene"
                is_expl = generation_mode in ("explainer", "Explainer Style", "📊 Explainer Style")
                clean_p = rewrite_query_for_flux(prompt_q, is_explainer=is_expl)
                print(f"🎨 Generating dynamic FLUX visual for Scene {num}: '{clean_p[:60]}...'")
                if generate_pollinations_image(clean_p, dest, aspect_ratio=aspect_ratio):
                    file_hash = image_hash(dest)
                    with hash_lock:
                        if file_hash:
                            used_hashes.add(file_hash)
                    results_map[num] = dest
                    applied = True
                    print(f"  ✓ Dynamically generated tailored FLUX image for Visual {num}")
            except Exception as dyn_err:
                print(f"  Dynamic FLUX generation note: {dyn_err}")

            # 2. Offline fallback media pool only if internet/FLUX is unreachable
            if not applied and (fallback_pool_videos or fallback_pool_images):
                pool_idx = (num - 1)
                if fallback_pool_videos:
                    src_vid = fallback_pool_videos[pool_idx % len(fallback_pool_videos)]
                    shutil.copyfile(src_vid, video_dest)
                    extract_video_frame(video_dest, dest)
                    results_map[num] = video_dest
                    applied = True
                    print(f"  ✓ Applied fallback video {get_image_filename(src_vid)} -> {num}.mp4")
                elif fallback_pool_images:
                    src_img = fallback_pool_images[pool_idx % len(fallback_pool_images)]
                    shutil.copyfile(src_img, dest)
                    results_map[num] = dest
                    applied = True
                    print(f"  ✓ Applied fallback image {get_image_filename(src_img)} -> {num}.jpg")

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
                    print(f"[Self-Healing] Sourced missing {number}.jpg from fallback {get_image_filename(src_fallback)}")
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

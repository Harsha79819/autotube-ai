"""
AutoTube AI - Multi-Provider Image & Video Sourcing Subsystem (providers/image.py)
Supports:
  1. Pexels API (HD Stock Photos & Stock Videos) with dynamic aspect ratio orientation
  2. DuckDuckGo Image Search (Free, no API key, live web photography)
  3. Wikimedia Commons (Historical figures, politics, landmarks)
  4. Pixabay API (Free stock photos & videos if PIXABAY_API_KEY is configured)
  5. Pollinations.ai FLUX AI Generative Fallback (100% free, no API key, photorealistic AI generation)
"""

import os
import re
import html
import json
import urllib.parse
import requests
from pathlib import Path
from PIL import Image

REQUEST_TIMEOUT = 7
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ------------------------------------------------------------
# 1. PEXELS API (STOCK PHOTOS & VIDEOS)
# ------------------------------------------------------------

def search_pexels_photos(query, pexels_key=None, orientation="landscape", per_page=8):
    """Search high-definition photos via Pexels API with dynamic orientation."""
    key = pexels_key or os.getenv("PEXELS_API_KEY", "")
    if not key:
        return []

    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": key, "User-Agent": USER_AGENT}
    params = {"query": query, "per_page": per_page}
    if orientation in ("landscape", "portrait", "square"):
        params["orientation"] = orientation

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for photo in data.get("photos", []):
            src = photo.get("src", {})
            img_url = src.get("large2x") or src.get("large") or src.get("original")
            if img_url:
                results.append({
                    "title": photo.get("alt") or query,
                    "image_url": img_url,
                    "source": "pexels",
                    "width": photo.get("width", 1920),
                    "height": photo.get("height", 1080),
                })
        return results
    except Exception as e:
        print(f"Pexels photo search notice ({query}): {e}")
        return []


def search_pexels_videos(query, pexels_key=None, orientation="landscape", per_page=4):
    """Search cinematic stock video footage via Pexels API with dynamic orientation."""
    key = pexels_key or os.getenv("PEXELS_API_KEY", "")
    if not key:
        return None

    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": key, "User-Agent": USER_AGENT}
    
    clean_q = re.sub(r"[^a-zA-Z0-9\s]", " ", query).strip()
    words = clean_q.split()
    search_terms = []
    if len(words) >= 3:
        search_terms.append(" ".join(words[:3]))
    if len(words) >= 2:
        search_terms.append(" ".join(words[:2]))
    if words:
        search_terms.append(words[0])

    for term in search_terms:
        params = {"query": term, "per_page": per_page}
        if orientation in ("landscape", "portrait", "square"):
            params["orientation"] = orientation
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=(3, 6))
            if resp.status_code != 200:
                continue
            data = resp.json()
            videos = data.get("videos", [])
            for vid in videos:
                files = vid.get("video_files", [])
                hd_files = [
                    f for f in files
                    if f.get("quality") == "hd" and (f.get("width") or 0) >= 720
                ]
                if hd_files:
                    best = max(hd_files, key=lambda x: (x.get("width", 0), x.get("height", 0)))
                    return {
                        "video_url": best.get("link"),
                        "width": best.get("width"),
                        "height": best.get("height"),
                        "duration": vid.get("duration"),
                        "term": term,
                        "source": "pexels_video",
                    }
        except Exception:
            continue
    return None


# ------------------------------------------------------------
# 2. DUCKDUCKGO HIGH-RES IMAGE SEARCH (100% FREE, NO KEY)
# ------------------------------------------------------------

def search_duckduckgo_images(query, max_results=12):
    """
    Search direct high-resolution web photography via DuckDuckGo with Bing fallback.
    """
    results = []
    seen_urls = set()

    # Step 1: Try DuckDuckGo
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://duckduckgo.com/",
        })

        token_url = "https://duckduckgo.com/"
        t_resp = session.get(token_url, params={"q": query}, timeout=4)
        if t_resp.status_code == 200:
            vqd_match = re.search(r'vqd=([\d-]+)', t_resp.text) or re.search(r'vqd="([^"]+)"', t_resp.text)
            if vqd_match:
                vqd = vqd_match.group(1)
                img_url = "https://duckduckgo.com/i.js"
                params = {
                    "l": "us-en",
                    "o": "json",
                    "q": query,
                    "vqd": vqd,
                    "f": ",,,type:photo,,,",
                    "p": "1",
                }
                res = session.get(img_url, params=params, timeout=4)
                if res.status_code == 200:
                    data = res.json()
                    for item in data.get("results", []):
                        direct_url = item.get("image")
                        if not direct_url or direct_url in seen_urls:
                            continue
                        low_url = direct_url.lower()
                        if any(low_url.endswith(ext) for ext in [".svg", ".gif", ".ico"]):
                            continue

                        w = item.get("width") or 800
                        h = item.get("height") or 600
                        if w >= 400 and h >= 300:
                            seen_urls.add(direct_url)
                            results.append({
                                "title": item.get("title") or query,
                                "image_url": direct_url,
                                "source": "duckduckgo",
                                "width": w,
                                "height": h,
                            })
                            if len(results) >= max_results:
                                break
    except Exception as err:
        print(f"DuckDuckGo image search notice ({query}): {err}")

    # Step 2: Fallback to Bing Images if DuckDuckGo returned few or no results
    if len(results) < 3:
        try:
            bing_url = "https://www.bing.com/images/search"
            b_params = {"q": query, "first": 1}
            b_resp = requests.get(bing_url, params=b_params, headers={"User-Agent": USER_AGENT}, timeout=5)
            if b_resp.status_code == 200:
                pattern = re.compile(r'murl&quot;:&quot;(.*?)&quot;', re.DOTALL)
                for m in pattern.findall(b_resp.text):
                    img_url = m.replace("\\/", "/").replace("\\u002f", "/")
                    if img_url.startswith("http") and img_url not in seen_urls:
                        seen_urls.add(img_url)
                        results.append({
                            "title": query,
                            "image_url": img_url,
                            "source": "bing",
                            "width": 800,
                            "height": 600,
                        })
                        if len(results) >= max_results:
                            break
        except Exception as b_err:
            print(f"Bing fallback notice ({query}): {b_err}")

    return results


def search_web_product_images(product_name, scene_query=None, max_results=12):
    """
    Dedicated web search for specific commercial products, hardware, devices, and accessories.
    Sources real tech news imagery, press renders, reviews, and photography matching the exact scene context.
    Applies resolution filtering (>=500x350) and discards logos, icons, and vector clipart.
    """
    clean_name = re.sub(r"[^\w\s-]", " ", product_name).strip()
    targeted_queries = []

    if scene_query:
        # Clean scene query: remove prefixes like '1.', 'visual 1:', etc.
        clean_scene = re.sub(r"^(?:\d+[\.\:\-]\s*|(?:visual|scene|shot)\s*\d*[\.\:\-]?\s*)", "", str(scene_query), flags=re.IGNORECASE).strip()
        # Split multi-query alternatives if present
        scene_parts = [p.strip() for p in clean_scene.split("|") if p.strip()]
        for part in scene_parts:
            # Combine product name with scene part if not already present
            if clean_name.lower() not in part.lower():
                targeted_queries.append(f"{clean_name} {part}")
            targeted_queries.append(part)

    # General high-intent fallback queries
    targeted_queries.extend([
        f"{clean_name} hands on review photo",
        f"{clean_name} official render photo",
        f"{clean_name} tech reveal",
    ])

    candidates = []
    seen_urls = set()

    for q in targeted_queries:
        if len(candidates) >= max_results:
            break
        # Query DuckDuckGo
        ddg_results = search_duckduckgo_images(q, max_results=6)
        for cand in ddg_results:
            url = cand.get("image_url", "")
            if not url or url in seen_urls:
                continue

            title = str(cand.get("title", "")).lower()
            # Negative filtering: discard only true spam/junk (icons, vector clipart, teardown diagrams)
            negative_keywords = [
                "logo", "icon", "vector", "svg", "clipart", "wallpaper",
                "teardown diagram", "battery replacement guide", "dummy model blueprint"
            ]
            if any(neg in title for neg in negative_keywords):
                continue

            w = cand.get("width", 0)
            h = cand.get("height", 0)
            if (w and w < 500) or (h and h < 350):
                continue

            cand["source"] = "Web Product Photography (Editorial Fair-Use)"
            cand["is_editorial"] = True
            cand["product_name"] = clean_name
            seen_urls.add(url)
            candidates.append(cand)

    print(f"🌐 Sourced {len(candidates)} real web photography candidates for: '{clean_name}' (Scene: '{str(scene_query)[:40]}')")
    return candidates


# ------------------------------------------------------------
# 3. WIKIMEDIA COMMONS SEARCH (FREE, OPEN ACCESS)
# ------------------------------------------------------------

def search_wikimedia(query, max_results=10):
    """Search Wikimedia Commons for historical, geographical, and news imagery."""
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"File:{query}",
        "gsrlimit": max_results,
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "format": "json",
    }
    headers = {"User-Agent": "AutoTubeAI/2.1 (contact: autotube@local.dev)"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        results = []
        for page in pages.values():
            info_list = page.get("imageinfo", [])
            if not info_list:
                continue
            info = info_list[0]
            mime = info.get("mime", "").lower()
            if "image" not in mime or "svg" in mime:
                continue
            img_url = info.get("url")
            w = info.get("width", 0)
            h = info.get("height", 0)
            if img_url and w >= 500 and h >= 300:
                results.append({
                    "title": page.get("title") or query,
                    "image_url": img_url,
                    "source": "wikimedia",
                    "width": w,
                    "height": h,
                })
        return results
    except Exception as err:
        print(f"Wikimedia search notice ({query}): {err}")
        return []


# ------------------------------------------------------------
# 4. PIXABAY API SEARCH (FREE WITH OPTIONAL KEY)
# ------------------------------------------------------------

def search_pixabay(query, orientation="horizontal", max_results=8):
    """Search Pixabay for free commercial stock photography."""
    key = os.getenv("PIXABAY_API_KEY", "")
    if not key:
        return []

    url = "https://pixabay.com/api/"
    pix_orient = "horizontal" if orientation == "landscape" else ("vertical" if orientation == "portrait" else "all")
    params = {
        "key": key,
        "q": query,
        "image_type": "photo",
        "orientation": pix_orient,
        "per_page": max_results,
        "safesearch": "true",
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for hit in data.get("hits", []):
            img_url = hit.get("largeImageURL") or hit.get("webformatURL")
            if img_url:
                results.append({
                    "title": hit.get("tags") or query,
                    "image_url": img_url,
                    "source": "pixabay",
                    "width": hit.get("imageWidth", 1280),
                    "height": hit.get("imageHeight", 720),
                })
        return results
    except Exception as err:
        print(f"Pixabay search notice ({query}): {err}")
        return []


# ------------------------------------------------------------
# 5. POLLINATIONS.AI FLUX GENERATIVE FALLBACK (100% FREE AI)
# ------------------------------------------------------------

def generate_pollinations_image(prompt, destination_path, width=1080, height=1080, aspect_ratio="1:1"):
    """
    Generate an ultra-photorealistic FLUX AI image via Pollinations.ai on-the-fly.
    Used when stock photo databases have 0 matches for abstract or rare topics.
    Zero API key required, 100% free.
    """
    if aspect_ratio == "9:16":
        w, h = 720, 1280
    elif aspect_ratio == "16:9":
        w, h = 1280, 720
    else:
        w, h = width, height

    clean_prompt = re.sub(r"[^a-zA-Z0-9\s,.-]", " ", prompt).strip()
    enhanced_prompt = f"{clean_prompt}, cinematic lighting, photorealistic, 8k, detailed documentary style, hyperrealistic"
    encoded = urllib.parse.quote(enhanced_prompt[:250])
    
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&nologo=true&model=flux"
    
    try:
        print(f"🎨 Generating FLUX AI image via Pollinations for: '{prompt[:45]}...'")
        resp = requests.get(url, timeout=16, headers={"User-Agent": USER_AGENT})
        if resp.status_code == 200 and len(resp.content) > 5000:
            dest = Path(destination_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            # Verify valid image with PIL
            with Image.open(dest) as img:
                img.verify()
            print(f"✅ Generated and verified Pollinations FLUX image: {destination_path}")
            return True
    except Exception as e:
        print(f"⚠️ Pollinations generative AI notice: {e}")
    return False


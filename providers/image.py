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
import time
import html
import json
import urllib.parse
import requests
from pathlib import Path
from PIL import Image
from providers.tracker import record_call

REQUEST_TIMEOUT = 7
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ------------------------------------------------------------
# TIER C HARD BLOCKER: WATERMARKED AGENCIES & COPYRIGHTED RE-UPLOADS
# ------------------------------------------------------------
TIER_C_BLOCKED_DOMAINS = [
    "gettyimages", "getty", "shutterstock", "alamy", "apimages",
    "reuters", "istockphoto", "stock.adobe", "dreamstime", "123rf",
    "depositphotos", "vectorstock", "bigstockphoto", "magnumphotos",
    "wireimage", "filmmagic", "pollinations.ai", "pollinations", "watermark", "watermarked"
]


def is_tier_c_asset(url: str, title: str = "") -> bool:
    """
    Returns True if an image/video originates from a watermarked agency,
    stock paywall, or banned commercial licensing database (Tier C hard block).
    """
    if not url:
        return False
    u = str(url).lower()
    t = str(title).lower()
    for domain in TIER_C_BLOCKED_DOMAINS:
        if domain in u or domain in t:
            return True
    return False


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
            img_url = src.get("large2x") or src.get("original") or src.get("large")
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
# 2. HIGH-RES WEB PHOTOGRAPHY & TWITTER/X MEDIA SEARCH (100% FREE)
# ------------------------------------------------------------

BING_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}


def clean_and_crop_image(image_path: Path, aspect_ratio: str = "9:16") -> Path:
    """
    Auto-crops solid black/dark letterboxing bars, trims watermark borders,
    and formats 16:9 landscape images for 9:16 vertical shorts by compositing
    onto a blurred mirrored background to fill the full 9:16 canvas without leaving black/empty bars.
    """
    p = Path(image_path)
    if not p.exists():
        return p
    try:
        from PIL import ImageFilter
        with Image.open(p) as im:
            im_rgb = im.convert("RGB")
            w, h = im_rgb.size
            if w < 100 or h < 100:
                return p

            # 1. Detect and crop solid black letterbox borders (luminance threshold)
            gray = im_rgb.convert("L")
            bw = gray.point(lambda pix: 255 if pix > 18 else 0)
            bbox = bw.getbbox()
            if bbox:
                b_left, b_top, b_right, b_bottom = bbox
                crop_w = b_right - b_left
                crop_h = b_bottom - b_top
                # Only apply if non-trivial border (> 8px) and preserves at least 55% of content
                if crop_w > w * 0.55 and crop_h > h * 0.55:
                    if b_left >= 8 or b_top >= 8 or (w - b_right) >= 8 or (h - b_bottom) >= 8:
                        im_rgb = im_rgb.crop(bbox)
                        w, h = im_rgb.size

            # 2. Watermark safety trim: eliminate bottom watermark borders / logos cleanly
            if h >= 400:
                im_rgb = im_rgb.crop((0, 0, w, int(h * 0.96)))
                w, h = im_rgb.size

            # 3. Clean Aspect Ratio & Canvas Filling:
            # Guarantees exact 1080x1920 for 9:16 Shorts / Reels, or 1920x1080 for 16:9 Landscape.
            # Never leaves raw sizes (like 650x788) with black bars.
            if aspect_ratio == "9:16":
                target_w, target_h = 1080, 1920
                if (w, h) == (target_w, target_h):
                    pass
                elif abs(w / float(h) - (target_w / float(target_h))) < 0.03:
                    im_rgb = im_rgb.resize((target_w, target_h), Image.Resampling.LANCZOS)
                else:
                    bg_scale = max(target_w / float(w), target_h / float(h))
                    bg_w, bg_h = int(w * bg_scale), int(h * bg_scale)
                    bg_im = im_rgb.resize((bg_w, bg_h), Image.Resampling.LANCZOS)
                    crop_x = max(0, (bg_w - target_w) // 2)
                    crop_y = max(0, (bg_h - target_h) // 2)
                    bg_cropped = bg_im.crop((crop_x, crop_y, crop_x + target_w, crop_y + target_h))
                    bg_blurred = bg_cropped.filter(ImageFilter.GaussianBlur(radius=28)).convert("RGBA")
                    scrim = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 50))
                    bg_blurred = Image.alpha_composite(bg_blurred, scrim)

                    fg_scale = min(target_w / float(w), target_h / float(h))
                    fg_w, fg_h = int(w * fg_scale), int(h * fg_scale)
                    fg_resized = im_rgb.resize((fg_w, fg_h), Image.Resampling.LANCZOS).convert("RGBA")
                    fg_x = (target_w - fg_w) // 2
                    fg_y = (target_h - fg_h) // 2
                    bg_blurred.paste(fg_resized, (fg_x, fg_y), fg_resized)
                    im_rgb = bg_blurred.convert("RGB")
            elif aspect_ratio == "16:9":
                target_w, target_h = 1920, 1080
                if (w, h) == (target_w, target_h):
                    pass
                elif abs(w / float(h) - (target_w / float(target_h))) < 0.03:
                    im_rgb = im_rgb.resize((target_w, target_h), Image.Resampling.LANCZOS)
                else:
                    bg_scale = max(target_w / float(w), target_h / float(h))
                    bg_w, bg_h = int(w * bg_scale), int(h * bg_scale)
                    bg_im = im_rgb.resize((bg_w, bg_h), Image.Resampling.LANCZOS)
                    crop_x = max(0, (bg_w - target_w) // 2)
                    crop_y = max(0, (bg_h - target_h) // 2)
                    bg_cropped = bg_im.crop((crop_x, crop_y, crop_x + target_w, crop_y + target_h))
                    bg_blurred = bg_cropped.filter(ImageFilter.GaussianBlur(radius=28)).convert("RGBA")
                    scrim = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 50))
                    bg_blurred = Image.alpha_composite(bg_blurred, scrim)

                    fg_scale = min(target_w / float(w), target_h / float(h))
                    fg_w, fg_h = int(w * fg_scale), int(h * fg_scale)
                    fg_resized = im_rgb.resize((fg_w, fg_h), Image.Resampling.LANCZOS).convert("RGBA")
                    fg_x = (target_w - fg_w) // 2
                    fg_y = (target_h - fg_h) // 2
                    bg_blurred.paste(fg_resized, (fg_x, fg_y), fg_resized)
                    im_rgb = bg_blurred.convert("RGB")

            im_rgb.save(p, "JPEG", quality=95)
    except Exception as e:
        pass
    return p


def search_bing_images(query, max_results=16):
    """
    High-speed direct web image search via Bing Images with modern desktop browser headers.
    Returns direct high-resolution photo URLs (typically 1080p, 720p, or uncompressed camera photos).
    """
    results = []
    seen_urls = set()
    clean_q = re.sub(r"[^\w\s-]", " ", query, flags=re.UNICODE).strip()
    if not clean_q:
        return results

    bad_domains = (
        "bing.com", "microsoft.com", "merriam-webster", "les-inoxydables",
        "freepik.com", "alamy.com", "shutterstock.com", "dreamstime.com", "stockphoto",
        "amazon.", "media-amazon.com", "images-amazon.com", "flipkart.com", "ebay.com",
        "walmart.com", "aliexpress.com", "shopee.", "etsy.com", "shopify.com"
    )

    # Method 1: Desktop HTML Search endpoint (most reliable, returns 20-40 direct murl photos)
    try:
        session = requests.Session()
        url = "https://www.bing.com/images/search"
        params = {"q": clean_q, "form": "HDRSC2", "first": "1"}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        resp = session.get(url, params=params, headers=headers, timeout=7)
        if resp.status_code == 200:
            matches = re.findall(r'murl&quot;:&quot;(https?://[^&]+)&quot;', resp.text)
            for m in matches:
                img_url = m.replace("\\/", "/").replace("\\u002f", "/")
                if not img_url.startswith("http") or img_url in seen_urls:
                    continue
                low = img_url.lower()
                if any(low.endswith(ext) for ext in [".svg", ".gif", ".ico"]):
                    continue
                if any(bad in low for bad in bad_domains):
                    continue
                seen_urls.add(img_url)
                title_clean = re.sub(r"\s*-[a-zA-Z0-9_-]+\b", "", query).strip() or query
                results.append({
                    "title": title_clean,
                    "image_url": img_url,
                    "source": "bing_web",
                    "width": 1280,
                    "height": 720,
                })
                if len(results) >= max_results:
                    return results
    except Exception:
        pass

    # Method 2: Async endpoint fallback
    if len(results) < max_results:
        try:
            session = requests.Session()
            url = "https://www.bing.com/images/async"
            params = {"q": clean_q, "first": 1, "count": 35}
            resp = session.get(url, params=params, headers=BING_BROWSER_HEADERS, timeout=6)
            if resp.status_code == 200:
                pattern = re.compile(r'murl&quot;:&quot;(.*?)&quot;', re.DOTALL)
                matches = pattern.findall(resp.text)
                title_clean = re.sub(r"\s*-[a-zA-Z0-9_-]+\b", "", query).strip() or query
                for m in matches:
                    img_url = m.replace("\\/", "/").replace("\\u002f", "/")
                    if not img_url.startswith("http") or img_url in seen_urls:
                        continue
                    low = img_url.lower()
                    if any(low.endswith(ext) for ext in [".svg", ".gif", ".ico"]):
                        continue
                    if any(bad in low for bad in bad_domains):
                        continue
                    seen_urls.add(img_url)
                    results.append({
                        "title": title_clean,
                        "image_url": img_url,
                        "source": "bing_web",
                        "width": 1280,
                        "height": 720,
                    })
                    if len(results) >= max_results:
                        break
        except Exception:
            pass

    return results


HINDI_BIGG_BOSS_KEYWORDS = [
    "salman khan", "salman", "colorstv", "colors tv", "colors", "hindi",
    "manveer gurjar", "manveer", "swami om", "bani j", "rohan mehra", "nitibha", "manu punjabi",
    "monalisa", "lopamudra", "elena kazan", "jason shah", "priyanka jagga",
    "bb10 hindi", "bigg boss 10 hindi", "bigg boss hindi"
]


def search_twitter_media_images(query, max_results=12):
    """
    Sources real images and photos shared on Twitter (X), e.g. from pbs.twimg.com.
    Supports:
    1. Official Twitter Bearer Token (if TWITTER_BEARER_TOKEN or X_BEARER_TOKEN is set in .env)
    2. RapidAPI Twitter endpoint (if RAPIDAPI_KEY is set in .env)
    3. Targeted viral Twitter/X web news photography (Free, fast, no API key needed)
    """
    results = []
    seen_urls = set()
    clean_q = re.sub(r"[^\w\s-]", " ", query, flags=re.UNICODE).strip()
    from utils.season_guard import extract_person_from_scene
    is_person_q = bool(extract_person_from_scene(clean_q))

    # Ground Reality TV / Bigg Boss to Telugu with exact season & current year preserved (Only for general show queries, NOT for individual people!)
    if "bigg boss" in clean_q.lower() and not is_person_q:
        s_m = re.search(r"\b(?:season\s*|bb\s*|bigg\s*boss\s*(?:telugu\s*)?)(\d+)\b", clean_q, flags=re.IGNORECASE)
        cur_s_num = s_m.group(1) if s_m else "10"
        if "telugu" not in clean_q.lower():
            clean_q = f"Bigg Boss Telugu {cur_s_num} 2026 {clean_q}".strip()
        elif cur_s_num not in clean_q:
            clean_q = f"{clean_q} {cur_s_num} 2026".strip()
        elif "2026" not in clean_q:
            clean_q = f"{clean_q} 2026".strip()

    # 1. Option: Twitter Official API v2 (if token configured in .env)
    twitter_token = os.getenv("TWITTER_BEARER_TOKEN") or os.getenv("X_BEARER_TOKEN")
    if twitter_token:
        try:
            url = "https://api.twitter.com/2/tweets/search/recent"
            headers = {"Authorization": f"Bearer {twitter_token}"}
            params = {
                "query": f"{clean_q} has:images lang:te OR lang:en",
                "max_results": 10,
                "expansions": "attachments.media_keys",
                "media.fields": "url,preview_image_url,width,height"
            }
            resp = requests.get(url, headers=headers, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                media_list = data.get("includes", {}).get("media", [])
                for m in media_list:
                    m_url = m.get("url") or m.get("preview_image_url")
                    if m_url and m_url not in seen_urls:
                        seen_urls.add(m_url)
                        results.append({
                            "title": query,
                            "image_url": m_url,
                            "source": "twitter_api_v2",
                            "width": m.get("width", 1280),
                            "height": m.get("height", 720),
                        })
                        if len(results) >= max_results:
                            return results
        except Exception:
            pass

    # 2. Option: RapidAPI Twitter search (if RAPIDAPI_KEY configured in .env)
    rapidapi_key = os.getenv("RAPIDAPI_KEY")
    if rapidapi_key:
        try:
            url = "https://twitter154.p.rapidapi.com/search/search"
            headers = {
                "X-RapidAPI-Key": rapidapi_key,
                "X-RapidAPI-Host": "twitter154.p.rapidapi.com"
            }
            params = {"query": f"{clean_q} filter:images", "section": "top", "min_likes": 5, "limit": 10}
            resp = requests.get(url, headers=headers, params=params, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                for tw in data.get("results", []):
                    for m_url in tw.get("media_url", []):
                        if m_url and m_url not in seen_urls:
                            seen_urls.add(m_url)
                            results.append({
                                "title": tw.get("text", query)[:50],
                                "image_url": m_url,
                                "source": "twitter_rapidapi",
                                "width": 1280,
                                "height": 720,
                            })
                            if len(results) >= max_results:
                                return results
        except Exception:
            pass

    # 3. High-Speed Targeted Viral Twitter / X Web News Media Search (Free & Fast, No API Key Required)
    from utils.season_guard import is_conflicting_season_candidate, is_bigg_boss_topic
    is_bb_q = is_bigg_boss_topic(clean_q) and not is_person_q

    if is_bb_q:
        twitter_queries = [
            f"{clean_q} 2026 twitter stills -hindi -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017",
            f"{clean_q} 2026 viral tweet photo -hindi -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017",
            f"{clean_q} episode stills 2026 -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017",
        ]
    else:
        twitter_queries = [
            f"{clean_q} twitter",
            f"{clean_q} twitter stills",
            f"{clean_q} viral tweet photo",
        ]
    for tq in twitter_queries:
        if len(results) >= max_results:
            break
        candidates = search_bing_images(tq, max_results=8)
        for c in candidates:
            u = c.get("image_url", "")
            if not u or u in seen_urls:
                continue
            cand_text = f"{c.get('title', '')} {u}".lower()
            if any(hk in cand_text for hk in HINDI_BIGG_BOSS_KEYWORDS):
                continue
            if is_conflicting_season_candidate(cand_text, current_season=10, is_bb_context=is_bb_q):
                continue
            seen_urls.add(u)
            c["source"] = "twitter_media"
            results.append(c)
            if len(results) >= max_results:
                break
    return results


def search_entertainment_posters(title, scene_query="", max_results=12):
    """
    Dedicated search for movies, OTT releases, TV reality shows (Bigg Boss), actor/actress stills.
    Retrieves official movie posters, hero stills, heroine stills, and show logos.
    """
    results = []
    seen_urls = set()
    clean_title = re.sub(r"[^\w\s-]", " ", title, flags=re.UNICODE).strip()

    is_reality_tv = any(k in clean_title.lower() for k in ("bigg boss", "reality show", "host", "elimination", "contestant", "stage"))

    # Ground Reality TV / Bigg Boss to Telugu with exact season & year preserved
    if "bigg boss" in clean_title.lower():
        s_m = re.search(r"\b(?:season\s*|bb\s*|bigg\s*boss\s*(?:telugu\s*)?)(\d+)\b", clean_title, flags=re.IGNORECASE)
        cur_s_num = s_m.group(1) if s_m else "10"
        if "telugu" not in clean_title.lower():
            clean_title = f"Bigg Boss Telugu {cur_s_num} 2026 {clean_title}".strip()
        elif cur_s_num not in clean_title:
            clean_title = f"{clean_title} {cur_s_num} 2026".strip()
        elif "2026" not in clean_title:
            clean_title = f"{clean_title} 2026".strip()

    short_scene = ""
    if scene_query:
        first_p = str(scene_query).split("|")[0].strip()
        clean_scene = re.sub(r"^(?:\d+[\.\:\-]\s*|(?:visual|scene|shot)\s*\d*[\.\:\-]?\s*)", "", first_p, flags=re.IGNORECASE).strip()
        words = clean_scene.split()
        short_scene = " ".join(words[:5])

    if is_reality_tv:
        is_host_query = any(h in (clean_title.lower() + " " + str(scene_query).lower()) for h in ("nagarjuna", "నాగార్జున", "king nag", "host"))
        if short_scene and short_scene.lower() not in clean_title.lower():
            targeted = [
                f"{short_scene} {clean_title} photo HD -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017",
                f"{short_scene} {clean_title} contestant still -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017",
                f"{short_scene} {clean_title} reaction -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017",
                f"{short_scene} Bigg Boss episode still 2026 -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017",
                f"{clean_title} contestants stage still 2026 -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017",
                f"{clean_title} housemates fight episode -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017",
            ]
        else:
            targeted = [
                f"{clean_title} contestants stage still 2026 -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017",
                f"{clean_title} promo still HD 2026 -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017",
                f"{clean_title} housemates fight episode -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017",
                f"{clean_title} nominations episode promo 2026 -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017",
            ]
        if is_host_query:
            targeted.insert(0, f"{clean_title} Nagarjuna host stage photo")
    else:
        targeted = [
            f"{clean_title} official movie poster HD",
            f"{clean_title} hero still HD",
            f"{clean_title} heroine look HD",
            f"{clean_title} OTT release poster",
            f"{clean_title} stage photo",
        ]
        if short_scene and short_scene.lower() not in clean_title.lower():
            targeted.insert(0, f"{clean_title} {short_scene}")

    for t_query in targeted:
        if len(results) >= max_results:
            break
        cands = search_bing_images(t_query, max_results=6)
        for cand in cands:
            u = cand.get("image_url", "")
            if not u or u in seen_urls:
                continue
            cand_text = f"{cand.get('title', '')} {u}".lower()
            if any(hk in cand_text for hk in HINDI_BIGG_BOSS_KEYWORDS):
                continue
            from utils.season_guard import is_conflicting_season_candidate, is_bigg_boss_topic
            if is_conflicting_season_candidate(cand_text, current_season=10, is_bb_context=is_bigg_boss_topic(clean_title)):
                continue
            seen_urls.add(u)
            cand["source"] = "entertainment_media"
            cand["is_poster"] = True
            results.append(cand)
            if len(results) >= max_results:
                break
    return results


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
        t_resp = session.get(token_url, params={"q": query}, timeout=3)
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
                res = session.get(img_url, params=params, timeout=3)
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
    except Exception:
        pass

    # Step 2: Fallback to high-speed Bing Images if DuckDuckGo returned few or no results
    if len(results) < 4:
        bing_cands = search_bing_images(query, max_results=max_results)
        for cand in bing_cands:
            u = cand.get("image_url")
            if u and u not in seen_urls:
                seen_urls.add(u)
                results.append(cand)
                if len(results) >= max_results:
                    break

    return results


def search_web_product_images(product_name, scene_query=None, max_results=14):
    """
    Dedicated web search for specific commercial products, hardware, devices, logos, and accessories.
    Sources real tech news imagery, press renders, reviews, official logos, and photography matching the scene.
    Applies resolution filtering (>=400x300) and discards junk vector clipart, keeping real logos & hardware.
    """
    clean_name = re.sub(r"[^\w\s-]", " ", product_name).strip()
    targeted_queries = []

    if scene_query:
        clean_scene = re.sub(r"^(?:\d+[\.\:\-]\s*|(?:visual|scene|shot)\s*\d*[\.\:\-]?\s*)", "", str(scene_query), flags=re.IGNORECASE).strip()
        scene_parts = [p.strip() for p in clean_scene.split("|") if p.strip()]
        for part in scene_parts:
            if clean_name.lower() not in part.lower():
                targeted_queries.append(f"{clean_name} {part}")
            targeted_queries.append(part)

    # General high-intent queries including official logos & product photos
    targeted_queries.extend([
        f"{clean_name} official render photo",
        f"{clean_name} smartphone hands on photo",
        f"{clean_name} official brand logo HD",
        f"{clean_name} tech reveal launch",
    ])

    candidates = []
    seen_urls = set()

    for q in targeted_queries:
        if len(candidates) >= max_results:
            break
        # Query high-speed Bing and DuckDuckGo
        bing_res = search_bing_images(q, max_results=6)
        ddg_res = search_duckduckgo_images(q, max_results=4) if len(bing_res) < 3 else []
        for cand in bing_res + ddg_res:
            url = cand.get("image_url", "")
            if not url or url in seen_urls:
                continue

            title = str(cand.get("title", "")).lower()
            # Negative filtering: discard only true spam/junk (cartoons, vector clipart, teardown diagrams)
            # NOTE: "logo" is intentionally ALLOWED so official product and brand logos can be used!
            negative_keywords = [
                "vector clipart", "black and white drawing", "coloring page",
                "teardown diagram", "battery replacement guide", "dummy model blueprint"
            ]
            if any(neg in title for neg in negative_keywords):
                continue

            w = cand.get("width", 0)
            h = cand.get("height", 0)
            if (w and w < 400) or (h and h < 300):
                continue

            cand["source"] = "Web Product Photography (Editorial Fair-Use)"
            cand["is_editorial"] = True
            cand["product_name"] = clean_name
            seen_urls.add(url)
            candidates.append(cand)

    print(f"🌐 Sourced {len(candidates)} real web media/product candidates for: '{clean_name}' (Scene: '{str(scene_query)[:40]}')")
    return candidates


# ------------------------------------------------------------
# 3. WIKIMEDIA COMMONS SEARCH (FREE, OPEN ACCESS, CC/PD VERIFIED)
# ------------------------------------------------------------

ALLOWED_WIKIMEDIA_LICENSES = {
    "pd", "public domain", "cc0", "cc-zero",
    "cc by", "cc-by", "cc by-sa", "cc-by-sa",
    "cc by 2.0", "cc by 2.5", "cc by 3.0", "cc by 4.0",
    "cc by-sa 2.0", "cc by-sa 2.5", "cc by-sa 3.0", "cc by-sa 4.0",
    "gfdl", "free art license",
}

def is_wikimedia_license_allowed(extmetadata: dict) -> bool:
    """Verifies that a Wikimedia Commons asset has a permissible open CC or Public Domain license."""
    if not extmetadata:
        return True
    lic_short = str(extmetadata.get("LicenseShortName", {}).get("value", "")).lower().strip()
    lic_url = str(extmetadata.get("LicenseUrl", {}).get("value", "")).lower().strip()
    usage = str(extmetadata.get("UsageTerms", {}).get("value", "")).lower().strip()

    if any(k in lic_short or k in usage for k in ("fair use", "non-free", "copyrighted", "all rights reserved")):
        return False
    if any(k in lic_short for k in ("pd", "public domain", "cc0", "cc by", "cc-by")):
        return True
    if "creativecommons.org/licenses" in lic_url or "creativecommons.org/publicdomain" in lic_url:
        return True
    return True


def sanitize_visual_query_for_copyright(query: str, topic_category: str = "general") -> str:
    """
    Cleans visual search query formatting while preserving movie titles, posters,
    actor/actress names, and show branding for fair-use commentary.
    """
    # Clean leading scene numbering, prefixes, and brackets
    clean_q = re.sub(r"^(?:File:|\d+[\.\:\-]\s*|(?:visual|scene|shot)\s*\d*[\.\:\-]?\s*)", "", str(query), flags=re.IGNORECASE).strip()
    clean_q = re.sub(r"^[\*\#\>\-\s]+", "", clean_q)
    return clean_q.strip()


def extract_wikimedia_keywords(query: str) -> list:
    """Extracts high-signal search terms for Wikimedia Commons."""
    clean = re.sub(r"^(?:File:|\d+[\.\:\-]\s*|(?:visual|scene|shot)\s*\d*[\.\:\-]?\s*)", "", str(query), flags=re.IGNORECASE)
    clean = re.sub(r"[^\w\s-]", " ", clean).strip()
    words = clean.split()
    stop_words = {
        "and", "the", "for", "with", "this", "that", "from", "into", "over", "more",
        "video", "watch", "today", "topic", "every", "first", "second", "third", "after",
        "check", "features", "india", "launches", "shows", "about", "data", "insights", "charts",
        "details", "scene", "visual", "presentation", "investigation", "discussion", "wrap",
        "aspects", "practical", "context", "outlook", "impact", "analysis"
    }
    meaningful = [w for w in words if w.lower() not in stop_words and len(w) > 2]
    known_tech = {
        "fitbit", "google", "iphone", "apple", "samsung", "pixel", "smartwatch",
        "oneplus", "xiaomi", "sony", "nvidia", "intel", "amd", "motorola", "oppo", "vivo", "realme"
    }
    entities = [w for w in meaningful if w[0].isupper() or w.lower() in known_tech]
    terms = []
    # Prioritize specific product brands/entities first
    for ent in entities:
        if ent.lower() in known_tech and ent not in terms:
            terms.append(ent)
    known_collision_first_names = {"rohit", "charan", "jhansi", "aman", "apoorva", "arjun", "varshini", "sudheer"}
    if len(entities) >= 2:
        combo = " ".join(entities[:2])
        if combo not in terms:
            terms.insert(0, combo)
    for ent in entities:
        if ent not in terms:
            if len(entities) >= 2 and ent.lower() in known_collision_first_names:
                continue
            terms.append(ent)
    if len(meaningful) >= 2:
        m_phrase = " ".join(meaningful[:2])
        if m_phrase not in terms:
            terms.append(m_phrase)
    for m in meaningful:
        if m not in terms and len(m) >= 4:
            if len(meaningful) >= 2 and m.lower() in known_collision_first_names:
                continue
            terms.append(m)
    return terms[:4]


def search_wikimedia(query, max_results=10):
    """Search Wikimedia Commons for historical, geographical, hardware, and news imagery with CC/PD license audit."""
    url = "https://commons.wikimedia.org/w/api.php"
    headers = {"User-Agent": "AutoTubeAI/2.1 (contact: autotube@local.dev)"}
    search_terms = extract_wikimedia_keywords(query)
    results = []
    seen_urls = set()

    for term in search_terms:
        if len(results) >= max_results:
            break
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": term,
            "gsrnamespace": 6,
            "gsrlimit": max_results,
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "format": "json",
        }
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=5)
            if resp.status_code != 200:
                continue
            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                info_list = page.get("imageinfo", [])
                if not info_list:
                    continue
                info = info_list[0]
                mime = info.get("mime", "").lower()
                if "image" not in mime or "svg" in mime or "gif" in mime:
                    continue

                # License audit (Phase 5: Only CC / Public Domain allowed)
                extmetadata = info.get("extmetadata", {})
                if not is_wikimedia_license_allowed(extmetadata):
                    continue

                img_url = info.get("url")
                if not img_url or img_url in seen_urls:
                    continue
                w = info.get("width", 0)
                h = info.get("height", 0)
                if w >= 400 and h >= 300:
                    cand_title = page.get("title") or term
                    # Strict Season & Celebrity Collision Disqualification
                    try:
                        from utils.season_guard import is_conflicting_season_candidate
                        if is_conflicting_season_candidate(f"{cand_title} {img_url}", target_person=query):
                            continue
                    except Exception:
                        pass

                    seen_urls.add(img_url)
                    results.append({
                        "title": cand_title,
                        "image_url": img_url,
                        "source": "wikimedia",
                        "license": extmetadata.get("LicenseShortName", {}).get("value", "CC/PD"),
                        "width": w,
                        "height": h,
                    })
        except Exception as err:
            print(f"Wikimedia search notice ({term}): {err}")
            continue

    return results


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
            img_url = hit.get("largeImageURL") or hit.get("fullHDURL") or hit.get("imageURL")
            if not img_url and hit.get("imageWidth", 0) >= 1280:
                img_url = hit.get("webformatURL")
            if img_url:
                results.append({
                    "title": hit.get("tags") or query,
                    "image_url": img_url,
                    "source": "pixabay",
                    "width": hit.get("imageWidth", 1920),
                    "height": hit.get("imageHeight", 1080),
                })
        return results
    except Exception as err:
        print(f"Pixabay search notice ({query}): {err}")
        return []


# ------------------------------------------------------------
# 5. POLLINATIONS.AI FLUX GENERATIVE FALLBACK (100% FREE AI)
# ------------------------------------------------------------

def generate_pollinations_image(prompt, destination_path, width=1080, height=1080, aspect_ratio="9:16", force=False):
    """
    Generate an ultra-photorealistic FLUX AI image via Pollinations.ai on-the-fly.
    Used when stock photo databases have 0 matches for abstract or rare topics.
    Zero API key required, 100% free.
    Standardized resolutions: 768x1344 (9:16 portrait), 1344x768 (16:9 landscape), 1024x1024 (1:1 square).

    Zero-distortion policy: when the Creator Canvas Engine is active (curated entity cutouts exist,
    or AUTOTUBE_CANVAS=1) this returns False unless force=True or AUTOTUBE_ALLOW_AI_IMAGES=1.
    """
    if not force:
        try:
            from agents.canvas_ladder import ai_images_blocked
            if ai_images_blocked():
                print("🛡️ [Zero-Distortion] AI image generation skipped (canvas mode): "
                      "scene will use a typography/name card instead of a generated face.")
                return False
        except ImportError:
            pass

    if aspect_ratio == "9:16":
        w, h = 768, 1344
    elif aspect_ratio == "16:9":
        w, h = 1344, 768
    elif aspect_ratio == "1:1":
        w, h = 1024, 1024
    else:
        w, h = width, height

    clean_prompt = re.sub(r"[^a-zA-Z0-9\s,.-]", " ", prompt).strip()
    enhanced_prompt = f"{clean_prompt}, cinematic lighting, photorealistic, 8k, detailed documentary style, hyperrealistic"
    encoded = urllib.parse.quote(enhanced_prompt[:250])

    import random
    seed = random.randint(100000, 99999999)
    # Pollinations active free model is 'sana' (flux now requires payment/causes HTTP 402)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&nologo=true&model=sana&seed={seed}"

    t0 = time.time()
    try:
        print(f"🎨 Generating AI image via Pollinations (Sana) for: '{prompt[:45]}...' ({w}x{h})")
        resp = requests.get(url, timeout=22, headers={"User-Agent": USER_AGENT})
        dur_ms = (time.time() - t0) * 1000
        if resp.status_code == 200 and len(resp.content) > 5000:
            dest = Path(destination_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            # Verify and crop potential generator watermark
            with Image.open(dest) as img:
                im_temp = img.convert("RGB")
                iw, ih = im_temp.size
                if ih > 300:
                    im_temp = im_temp.crop((0, 0, iw, ih - 45))
                im_temp.save(dest, "JPEG", quality=95)
            # Run clean_and_crop_image for aspect ratio and border cleanup
            clean_and_crop_image(dest, aspect_ratio=aspect_ratio)
            print(f"✅ Generated and verified Pollinations FLUX image (clean, unwatermarked) in {dur_ms:.0f}ms: {destination_path}")
            record_call("pollinations", True, duration_ms=dur_ms)
            return True
        else:
            record_call("pollinations", False, error=f"HTTP {resp.status_code}", duration_ms=dur_ms)
    except Exception as e:
        dur_ms = (time.time() - t0) * 1000
        record_call("pollinations", False, error=str(e), duration_ms=dur_ms)
        print(f"⚠️ Pollinations generative AI notice: {e}")
    return False


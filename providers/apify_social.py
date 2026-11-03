"""
AutoTube AI - Apify Social Media Scraper & Cache Gateway (providers/apify_social.py)

Fetches authentic candidate images from Instagram and Twitter/X using Apify actors:
- Instagram: `apify/instagram-hashtag-scraper`
- Twitter/X: `apidojo/tweet-scraper`
Saves image URL, caption, post URL, username, and platform for every candidate.

Features intelligent disk caching for both query metadata and image binaries
so that Apify credits ($5 free monthly limit) are strictly preserved across repeat runs.
"""

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"
CACHE_FILE = CACHE_DIR / "social_candidates.json"
IMAGES_CACHE_DIR = CACHE_DIR / "social_images"

# Ensure cache directories exist
CACHE_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_apify_api_token() -> str:
    """Retrieve Apify API token from environment."""
    return os.getenv("APIFY_API_TOKEN", "").strip()


# ============================================================
# PERSISTENT CACHE HELPERS
# ============================================================

_MEMORY_CACHE: Dict[str, Any] = {}


def _load_metadata_cache() -> Dict[str, Any]:
    global _MEMORY_CACHE
    if _MEMORY_CACHE:
        return dict(_MEMORY_CACHE)
    if not CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        _MEMORY_CACHE = data
        return dict(_MEMORY_CACHE)
    except Exception:
        return {}


def _save_metadata_cache(cache_data: Dict[str, Any]) -> None:
    global _MEMORY_CACHE
    _MEMORY_CACHE = dict(cache_data)
    try:
        CACHE_FILE.write_text(json.dumps(cache_data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as err:
        pass


def _query_cache_key(platform: str, query: str) -> str:
    clean = re.sub(r"\s+", " ", query.strip().lower())
    return f"{platform}:{clean}"


# ============================================================
# CANDIDATE NORMALIZATION
# ============================================================

def _normalize_candidate(
    image_url: str,
    caption: str,
    post_url: str,
    username: str,
    platform: str,
    query: str,
) -> Optional[Dict[str, Any]]:
    if not image_url or not isinstance(image_url, str) or not image_url.startswith("http"):
        return None

    # Filter out obvious UI icons or thumbnails, and e-commerce product listings
    low = image_url.lower()
    if any(k in low for k in ["emoji", "favicon", "1x1", "placeholder", "icon"]):
        return None
    if any(d in low for d in ["amazon.", "media-amazon.com", "images-amazon.com", "flipkart.", "ebay.", "walmart.", "aliexpress.", "shopee.", "etsy.", "shopify."]):
        return None

    clean_caption = re.sub(r"\s+", " ", (caption or "").strip())
    return {
        "image_url": image_url,
        "caption": clean_caption[:500],
        "post_url": post_url or "",
        "username": username or "unknown",
        "platform": platform,
        "query": query,
        "fetched_at": time.time(),
    }


# ============================================================
# APIFY ACTOR RUNNERS
# Global failover flag to skip slow Apify retries if monthly limit exceeded
_APIFY_DISABLED = False
APIFY_QUOTA_FLAG_FILE = CACHE_DIR / "apify_quota_exceeded.flag"


def is_apify_disabled() -> bool:
    global _APIFY_DISABLED
    if _APIFY_DISABLED:
        return True
    if APIFY_QUOTA_FLAG_FILE.exists():
        try:
            mtime = APIFY_QUOTA_FLAG_FILE.stat().st_mtime
            # Keep flag active for 24 hours before re-checking
            if time.time() - mtime < 86400:
                _APIFY_DISABLED = True
                return True
            else:
                APIFY_QUOTA_FLAG_FILE.unlink(missing_ok=True)
        except Exception:
            pass
    return False


def mark_apify_disabled():
    global _APIFY_DISABLED
    _APIFY_DISABLED = True
    try:
        APIFY_QUOTA_FLAG_FILE.write_text(
            json.dumps({"disabled_at": time.time(), "reason": "Monthly usage hard limit exceeded"}),
            encoding="utf-8"
        )
    except Exception:
        pass


def fetch_instagram_candidates_apify(
    hashtag: str,
    limit: int = 30,
    api_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Runs Apify Instagram Hashtag Scraper actor and returns parsed candidate list.
    """
    if is_apify_disabled():
        return []

    token = api_token or get_apify_api_token()
    if not token:
        return []

    clean_tag = hashtag.strip().lstrip("#")
    if not clean_tag:
        return []

    cache_key = _query_cache_key("instagram", clean_tag)
    meta_cache = _load_metadata_cache()
    if cache_key in meta_cache:
        cached_items = meta_cache[cache_key].get("candidates", [])
        if cached_items is not None:
            print(f"⚡ [Social Cache Hit] Instagram #{clean_tag} ({len(cached_items)} candidates)")
            return cached_items

    actor_id = "apify~instagram-hashtag-scraper"
    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": token}
    payload = {
        "hashtags": [clean_tag],
        "resultsLimit": limit,
    }

    candidates = []
    print(f"🌐 [Apify] Calling Instagram Hashtag Scraper for #{clean_tag} (limit: {limit})...")

    try:
        resp = requests.post(url, params=params, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            items = resp.json()
            if isinstance(items, list):
                for item in items:
                    img_url = item.get("displayUrl") or item.get("imageUrl") or item.get("url")
                    caption = item.get("caption") or item.get("text") or ""
                    post_url = item.get("url") or item.get("postUrl") or ""
                    owner = (
                        item.get("ownerUsername")
                        or item.get("username")
                        or (item.get("owner", {}).get("username") if isinstance(item.get("owner"), dict) else "")
                    )
                    cand = _normalize_candidate(
                        image_url=img_url,
                        caption=caption,
                        post_url=post_url,
                        username=owner,
                        platform="instagram",
                        query=clean_tag,
                    )
                    if cand:
                        candidates.append(cand)
            print(f"✅ [Apify Instagram] Retrieved {len(candidates)} candidates for #{clean_tag}")
        else:
            print(f"⚠️ Apify Instagram HTTP {resp.status_code}: {resp.text[:160]}")
            if resp.status_code == 403 or (resp.status_code in (400, 401, 403, 429) and "limit exceeded" in resp.text.lower()):
                mark_apify_disabled()
                print("⚡ [Apify Failover] Monthly usage limit reached. Bypassing Apify actors and using high-speed web scrapers.")
    except Exception as err:
        print(f"⚠️ Apify Instagram exception: {err}")

    meta_cache[cache_key] = {"candidates": candidates, "cached_at": time.time()}
    _save_metadata_cache(meta_cache)

    return candidates


def batch_fetch_instagram_candidates_apify(
    hashtags: List[str],
    limit_per_tag: int = 20,
    api_token: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Batches multiple hashtag searches into a SINGLE Apify run
    (apify/instagram-hashtag-scraper), populating the local metadata cache.
    """
    token = api_token or get_apify_api_token()
    clean_tags = list(dict.fromkeys([h.strip().lstrip("#") for h in hashtags if h and h.strip().lstrip("#")]))
    results_by_tag: Dict[str, List[Dict[str, Any]]] = {t: [] for t in clean_tags}
    if not clean_tags:
        return results_by_tag

    meta_cache = _load_metadata_cache()
    uncached_tags = []
    for t in clean_tags:
        ck = _query_cache_key("instagram", t)
        if ck in meta_cache and meta_cache[ck].get("candidates") is not None:
            results_by_tag[t] = meta_cache[ck]["candidates"]
            print(f"⚡ [Social Cache Hit] Instagram #{t} ({len(results_by_tag[t])} candidates)")
        else:
            uncached_tags.append(t)

    if not uncached_tags or is_apify_disabled() or not token:
        return results_by_tag

    actor_id = "apify~instagram-hashtag-scraper"
    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": token}
    payload = {
        "hashtags": uncached_tags,
        "resultsLimit": min(limit_per_tag * len(uncached_tags), 100),
    }

    print(f"🌐 [Apify Batch] Executing SINGLE run for {len(uncached_tags)} hashtags: {', '.join(uncached_tags[:5])}...")
    try:
        resp = requests.post(url, params=params, json=payload, timeout=25)
        if resp.status_code in (200, 201):
            items = resp.json()
            if isinstance(items, list):
                for item in items:
                    img_url = item.get("displayUrl") or item.get("imageUrl") or item.get("url")
                    caption = item.get("caption") or item.get("text") or ""
                    post_url = item.get("url") or item.get("postUrl") or ""
                    owner = (
                        item.get("ownerUsername")
                        or item.get("username")
                        or (item.get("owner", {}).get("username") if isinstance(item.get("owner"), dict) else "")
                    )
                    # Associate with relevant tag
                    matched_tag = uncached_tags[0]
                    for t in uncached_tags:
                        if t.lower() in caption.lower() or t.lower() in post_url.lower():
                            matched_tag = t
                            break
                    cand = _normalize_candidate(
                        image_url=img_url,
                        caption=caption,
                        post_url=post_url,
                        username=owner,
                        platform="instagram",
                        query=matched_tag,
                    )
                    if cand:
                        results_by_tag[matched_tag].append(cand)

                for t in uncached_tags:
                    ck = _query_cache_key("instagram", t)
                    meta_cache[ck] = {"candidates": results_by_tag[t], "cached_at": time.time()}
                _save_metadata_cache(meta_cache)
                print(f"✅ [Apify Batch Instagram] Retrieved candidates across {len(uncached_tags)} hashtags in single run.")
        else:
            if resp.status_code == 403 or (resp.status_code in (400, 401, 403, 429) and "limit exceeded" in resp.text.lower()):
                mark_apify_disabled()
                print("⚡ [Apify Failover] Usage limit reached. Bypassing Apify actors.")
    except Exception as err:
        print(f"⚠️ Apify batch Instagram exception: {err}")

    return results_by_tag


def batch_fetch_social_candidates(
    hashtags: List[str],
    search_terms: List[str],
    is_bb_context: bool = False,
    disallow_terms: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Batches all hashtag and search queries across the video into a single Apify execution,
    caching results to disk and falling back safely.
    """
    combined_candidates = []
    # 1. Batch Instagram hashtags
    ig_map = batch_fetch_instagram_candidates_apify(hashtags)
    for t_cands in ig_map.values():
        combined_candidates.extend(t_cands)

    # 2. Augment with fallback/web candidates if needed
    if len(combined_candidates) < 15:
        primary_entity = search_terms[0] if search_terms else "Bigg Boss Telugu 10"
        fb = _fetch_social_web_fallback(
            entity=primary_entity,
            hashtags=hashtags,
            keywords=None,
            limit=30,
            is_bb_context=is_bb_context,
            disallow_terms=disallow_terms,
        )
        combined_candidates.extend(fb)

    # Deduplicate
    seen = set()
    unique = []
    for c in combined_candidates:
        u = c.get("image_url")
        if u and u not in seen:
            seen.add(u)
            unique.append(c)
    return unique


def fetch_twitter_candidates_apify(
    search_term: str,
    limit: int = 30,
    api_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Runs Apify Tweet Scraper actor (apidojo/tweet-scraper) and returns candidate images.
    """
    if is_apify_disabled():
        return []

    token = api_token or get_apify_api_token()
    if not token:
        return []

    clean_term = search_term.strip()
    if not clean_term:
        return []

    cache_key = _query_cache_key("twitter", clean_term)
    meta_cache = _load_metadata_cache()
    if cache_key in meta_cache:
        cached_items = meta_cache[cache_key].get("candidates", [])
        if cached_items is not None:
            print(f"⚡ [Social Cache Hit] Twitter '{clean_term}' ({len(cached_items)} candidates)")
            return cached_items

    actor_id = "apidojo~tweet-scraper"
    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": token}
    payload = {
        "searchTerms": [clean_term],
        "maxItems": limit,
        "onlyImage": True,
    }

    candidates = []
    print(f"🌐 [Apify] Calling Tweet Scraper for '{clean_term}' (limit: {limit})...")

    try:
        resp = requests.post(url, params=params, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            items = resp.json()
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue

                    # Media URL extraction
                    entities_obj = item.get("entities") if isinstance(item.get("entities"), dict) else {}
                    extended_obj = item.get("extended_entities") if isinstance(item.get("extended_entities"), dict) else {}
                    media_list = entities_obj.get("media", []) or extended_obj.get("media", []) or item.get("media", [])
                    
                    img_url = ""
                    if isinstance(media_list, list) and media_list:
                        first_m = media_list[0]
                        if isinstance(first_m, dict):
                            img_url = first_m.get("media_url_https") or first_m.get("url") or first_m.get("mediaUrl") or ""
                        elif isinstance(first_m, str):
                            img_url = first_m

                    if not img_url and item.get("imageUrl"):
                        img_url = item.get("imageUrl")
                    elif not img_url and item.get("displayUrl"):
                        img_url = item.get("displayUrl")

                    caption = item.get("full_text") or item.get("text") or ""
                    post_url = item.get("twitterUrl") or item.get("url") or ""
                    
                    author_obj = item.get("author") or item.get("user")
                    if isinstance(author_obj, dict):
                        username = author_obj.get("userName") or author_obj.get("screen_name") or author_obj.get("name") or ""
                    elif isinstance(author_obj, str):
                        username = author_obj
                    else:
                        username = item.get("userName") or item.get("screen_name") or ""

                    cand = _normalize_candidate(
                        image_url=img_url,
                        caption=caption,
                        post_url=post_url,
                        username=username,
                        platform="twitter",
                        query=clean_term,
                    )
                    if cand:
                        candidates.append(cand)
            print(f"✅ [Apify Twitter] Retrieved {len(candidates)} candidates for '{clean_term}'")
        else:
            print(f"⚠️ Apify Twitter HTTP {resp.status_code}: {resp.text[:160]}")
            if resp.status_code == 403 or (resp.status_code in (400, 401, 403, 429) and "limit exceeded" in resp.text.lower()):
                mark_apify_disabled()
                print("⚡ [Apify Failover] Monthly usage limit reached. Bypassing Apify actors and using high-speed web scrapers.")
    except Exception as err:
        print(f"⚠️ Apify Twitter exception: {err}")

    meta_cache[cache_key] = {"candidates": candidates, "cached_at": time.time()}
    _save_metadata_cache(meta_cache)

    return candidates


# ============================================================
# COMPREHENSIVE COMBINED SOCIAL FETCHER WITH OFFLINE FALLBACK
# ============================================================

def fetch_social_candidates_for_scene(
    entity: str,
    hashtags: List[str],
    query_keywords: Optional[str] = None,
    target_count: int = 35,
    is_bb_context: bool = False,
    disallow_terms: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Fetches 30-50 candidate images across Instagram and Twitter/X.
    Uses Apify if token is provided; leverages local caching and resilient fallback.
    """
    candidates = []
    token = get_apify_api_token()

    from utils.season_guard import is_conflicting_season_candidate, get_current_season_number, is_bigg_boss_topic
    cur_season = get_current_season_number()
    is_bb = is_bb_context or is_bigg_boss_topic(entity) or any(is_bigg_boss_topic(h) for h in hashtags)

    # Ground Reality TV / Bigg Boss to Telugu with exact season number preserved
    if "bigg boss" in (entity or "").lower():
        s_match = re.search(r"\b(?:season\s*|bb\s*|bigg\s*boss\s*(?:telugu\s*)?)(\d+)\b", entity, flags=re.IGNORECASE)
        s_num = str(cur_season) if cur_season else "10"
        if s_match:
            try:
                parsed_s = int(s_match.group(1))
                if parsed_s == cur_season:
                    s_num = str(parsed_s)
            except ValueError:
                pass
        if "telugu" not in (entity or "").lower():
            entity = f"Bigg Boss Telugu {s_num}".strip()
        elif s_num and s_num not in entity:
            entity = f"{entity} {s_num}".strip()

    cleaned_hashtags = []
    for h in hashtags:
        h_str = str(h)
        # Drop past season tags like #BiggBoss8, #BB8, #BB9
        if cur_season == 10 and re.search(r"(?:bb|season|telugu)[-_]?[1-9]\b", h_str, re.I):
            continue
        if "biggboss" in h_str.lower() and "telugu" not in h_str.lower():
            s_tag = f"#BiggBossTelugu{cur_season}" if cur_season else "#BiggBossTelugu"
            cleaned_hashtags.append(s_tag)
        else:
            cleaned_hashtags.append(h_str)
    hashtags = cleaned_hashtags

    # 1 & 2. Concurrent Instagram & Twitter Queries (Only if Apify is active)
    if not is_apify_disabled() and token:
        import concurrent.futures

        tw_queries = []
        if entity and query_keywords:
            tw_queries.append(f"{entity} {query_keywords}")
        elif entity:
            tw_queries.append(f"{entity}")
        if hashtags:
            tw_queries.append(hashtags[0])

        def _get_ig(t):
            return fetch_instagram_candidates_apify(t, limit=20, api_token=token)

        def _get_tw(q):
            return fetch_twitter_candidates_apify(q, limit=20, api_token=token)

        tasks = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            for tag in hashtags[:2]:
                tasks.append(ex.submit(_get_ig, tag))
            for tq in tw_queries[:2]:
                tasks.append(ex.submit(_get_tw, tq))

            for f in tasks:
                try:
                    res = f.result(timeout=20)
                    if res:
                        candidates.extend(res)
                except Exception:
                    pass

    # 3. Offline / Web Media Fallback if candidates < 10 or token missing or Apify disabled
    if len(candidates) < 10:
        if is_apify_disabled():
            pass  # Fast silent failover
        elif not token:
            print("ℹ️ APIFY_API_TOKEN is not configured in .env. Activating verified social web fallback...")
        else:
            print(f"ℹ️ Low candidate count ({len(candidates)}). Augmenting with verified social media scraper...")

        fallback_candidates = _fetch_social_web_fallback(
            entity,
            hashtags,
            query_keywords,
            limit=target_count,
            is_bb_context=is_bb,
            disallow_terms=disallow_terms,
        ) or []
        candidates.extend(fallback_candidates)

    # Deduplicate by image_url within candidate pool and filter conflicting seasons
    seen_urls = set()
    unique_candidates = []
    for c in candidates:
        u = c["image_url"]
        cap = c.get("caption", "")
        if is_conflicting_season_candidate(
            f"{cap} {u}",
            current_season=cur_season,
            is_bb_context=is_bb,
            disallow_terms=disallow_terms,
        ):
            continue
        if u not in seen_urls:
            seen_urls.add(u)
            unique_candidates.append(c)

    return unique_candidates[:target_count]


def _fetch_social_web_fallback(
    entity: str,
    hashtags: List[str],
    keywords: Optional[str] = None,
    limit: int = 30,
    is_bb_context: bool = False,
    disallow_terms: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Fallback that scrapes real Twitter/Instagram media photos via high-speed web scrapers
    and local entity library, ensuring zero downtime if Apify credits expire or token is unset.
    """
    results = []
    from providers.image import search_twitter_media_images, search_bing_images, HINDI_BIGG_BOSS_KEYWORDS
    from utils.season_guard import is_conflicting_season_candidate, get_current_season_number

    cur_season = get_current_season_number()
    search_terms = []
    clean_entity = (entity or "").strip()
    if "bigg boss" in clean_entity.lower():
        s_match = re.search(r"\b(?:season\s*|bb\s*|bigg\s*boss\s*(?:telugu\s*)?)(\d+)\b", clean_entity, flags=re.IGNORECASE)
        s_num = s_match.group(1) if s_match else (str(cur_season) if cur_season else "10")
        if "telugu" not in clean_entity.lower():
            clean_entity = f"Bigg Boss Telugu {s_num}".strip()
        elif s_num and s_num not in clean_entity:
            clean_entity = f"{clean_entity} {s_num}".strip()

    is_bb = is_bb_context or ("bigg boss" in clean_entity.lower())
    neg_suffix = " -2024 -2023 -2022 -2021 -2020 -2019 -2018 -2017"
    if is_bb:
        neg_suffix += " -anime -manga -cartoon -illustration -wallpaper -eurovision -bts"
        if cur_season and cur_season >= 10:
            neg_suffix += " -2025 -Season 9 -Season 8 -BB9 -BB8"
    if disallow_terms:
        for dt in disallow_terms:
            if dt and len(dt) > 2:
                neg_suffix += f" -{dt}"

    from utils.season_guard import get_celebrity_collision_negative_keywords
    celeb_negs = get_celebrity_collision_negative_keywords(clean_entity)
    for cn in celeb_negs:
        if cn not in neg_suffix:
            neg_suffix += f" {cn}"

    is_cta = (clean_entity.lower() in ("youtube", "outro", "subscribe")) or (keywords and any(k in str(keywords).lower() for k in ("subscribe", "like share", "outro", "bell icon")))
    if is_cta:
        search_terms.append("youtube like share subscribe social media button 3d")
        search_terms.append("youtube subscribe bell icon button")
        search_terms.append("youtube subscribe like share animation still")

    from utils.season_guard import extract_person_from_scene, format_strict_visual_query, is_generic_visual_query
    is_person = bool(extract_person_from_scene(clean_entity))

    if is_person:
        p_canon = extract_person_from_scene(clean_entity) or clean_entity
        from utils.season_guard import KNOWN_TELUGU_SHOW_PERSONS
        p_search_name = clean_entity
        for p_info in KNOWN_TELUGU_SHOW_PERSONS.values():
            if p_info["canonical"].lower() == (p_canon or "").lower():
                p_search_name = p_info.get("search_name", clean_entity)
                p_canon = p_info["canonical"]
                break
        
        if is_bb:
            s_name = f"Bigg Boss Telugu {cur_season or 10}"
            ev_year = 2026 if (cur_season or 10) >= 10 else 2025
            strict_q = format_strict_visual_query(p_canon, s_name, ev_year)
            search_terms.append(f"{strict_q}{neg_suffix}")
            if keywords:
                task_q = format_strict_visual_query(p_canon, "Bigg Boss Telugu", ev_year, task_or_promo=str(keywords))
                search_terms.append(f"{task_q}{neg_suffix}")
            search_terms.append(f'"{p_canon}" {s_name} photo HD{neg_suffix}')
        else:
            search_terms.append(f"{p_search_name} photo HD")
            search_terms.append(f"{clean_entity} photo HD")
            search_terms.append(f"{p_search_name} stills photo")
            if keywords:
                search_terms.append(f"{p_search_name} {keywords}")
            search_terms.append(f"{clean_entity} photo")
    elif keywords and clean_entity and not is_cta:
        if is_bb:
            search_terms.append(f'"{clean_entity}" "{keywords}" stills photo{neg_suffix}')
            search_terms.append(f'"{clean_entity}" "{keywords}" memes viral{neg_suffix}')
            search_terms.append(f'"{clean_entity}" "{keywords}" today episode{neg_suffix}')
        else:
            search_terms.append(f"{clean_entity} {keywords} photo HD")
            search_terms.append(f"{clean_entity} {keywords}")
    elif keywords and not is_cta:
        search_terms.append(f"{keywords} photo HD")

    if not is_person and clean_entity and not is_cta:
        if is_bb:
            if not is_generic_visual_query(clean_entity):
                search_terms.append(f'"{clean_entity}" stills photo{neg_suffix}')
                search_terms.append(f'"{clean_entity}" viral memes{neg_suffix}')
        else:
            search_terms.append(f"{clean_entity} photo HD")
            search_terms.append(f"{clean_entity} image")

    GENERIC_TAGS = {"telugu", "trending", "viral", "video", "trendingtelugu", "viralvideo", "tollywood", "tv", "show", "media"}
    for h in hashtags:
        h_clean = h.lstrip('#')
        if "biggboss" in h_clean.lower() and "telugu" not in h_clean.lower():
            h_clean = f"BiggBossTelugu{cur_season}" if cur_season else "BiggBossTelugu"
        if is_bb:
            if h_clean.lower() not in GENERIC_TAGS:
                search_terms.append(f'"{h_clean}" "Bigg Boss Telugu {cur_season}" stills photo{neg_suffix}')
        elif not is_cta:
            search_terms.append(f"{h_clean} photo HD")

    for st in search_terms:
        if len(results) >= limit:
            break
        if is_bb and is_generic_visual_query(st):
            continue
        raw_items = search_twitter_media_images(st, max_results=12)
        if not raw_items or len(raw_items) < 4:
            more_items = search_bing_images(f"{st} photo HD", max_results=12)
            raw_items = (raw_items or []) + more_items

        for item in raw_items:
            img_url = item.get("image_url")
            title = item.get("title", "")
            cand_text = f"{title} {img_url}".lower()
            if any(hk in cand_text for hk in HINDI_BIGG_BOSS_KEYWORDS):
                continue
            if is_conflicting_season_candidate(
                cand_text,
                current_season=cur_season,
                is_bb_context=is_bb,
                disallow_terms=disallow_terms,
            ):
                continue

            cand = _normalize_candidate(
                image_url=img_url,
                caption=title,
                post_url=item.get("page_url", "https://twitter.com"),
                username="social_media",
                platform="twitter" if "twimg" in (img_url or "").lower() else "web_social",
                query=st,
            )
            if cand:
                results.append(cand)
                if len(results) >= limit:
                    break

    return results


# ============================================================
# IMAGE DOWNLOAD & LOCAL DISK CACHE
# ============================================================

def download_candidate_image(candidate: Dict[str, Any], destination_path: Path) -> bool:
    """
    Downloads candidate image to destination, leveraging local persistent image cache.
    """
    image_url = candidate.get("image_url")
    if not image_url:
        return False

    url_hash = hashlib.sha256(image_url.encode("utf-8")).hexdigest()
    cached_file = IMAGES_CACHE_DIR / f"{url_hash}.jpg"

    if cached_file.exists() and cached_file.stat().st_size > 2000:
        try:
            from PIL import Image
            with Image.open(cached_file) as im:
                im.verify()
            shutil.copy2(cached_file, destination_path)
            return True
        except Exception:
            cached_file.unlink(missing_ok=True)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": "https://www.google.com/",
    }

    try:
        resp = requests.get(image_url, headers=headers, timeout=12, stream=True)
        if resp.status_code == 200:
            with open(cached_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=16384):
                    if chunk:
                        f.write(chunk)

            if cached_file.stat().st_size > 2000:
                try:
                    from PIL import Image
                    with Image.open(cached_file) as im:
                        im.verify()
                    shutil.copy2(cached_file, destination_path)
                    return True
                except Exception:
                    cached_file.unlink(missing_ok=True)
            else:
                cached_file.unlink(missing_ok=True)
    except Exception as err:
        pass

    return False

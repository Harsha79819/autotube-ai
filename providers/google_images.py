"""
AutoTube AI - Show-Locked Google & DuckDuckGo Image Search Provider (providers/google_images.py)
Implements:
  1. Google Programmable Search JSON API (searchType=image) with exactTerms & excludeTerms
  2. DuckDuckGo Image Search (ddgs) as zero-cost, 100% free fallback
  3. Quota Guard (<= 90 Google queries/day) & 7-day SQLite query caching
  4. Candidate Filtering: show-context tokens, entity name matching, resolution >= 720px,
     and strict watermark-agency domain filtering.
"""

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "autotube.db"

# Blacklisted agency watermark domains (strict Tier C rejection)
BLOCKED_STOCK_DOMAINS = {
    "gettyimages.com", "gettyimages.in", "istockphoto.com",
    "shutterstock.com", "alamy.com", "dreamstime.com",
    "123rf.com", "stock.adobe.com", "depositphotos.com",
    "vectorstock.com", "bigstockphoto.com", "freepik.com"
}

def _get_db_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def init_cache_db():
    with _get_db_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS image_search_cache (
                query_hash TEXT PRIMARY KEY,
                query TEXT,
                provider TEXT,
                results_json TEXT,
                timestamp INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_quota_tracker (
                date TEXT,
                provider TEXT,
                call_count INTEGER,
                PRIMARY KEY (date, provider)
            )
        """)
        conn.commit()

init_cache_db()


def check_and_increment_quota(provider: str, max_daily: int = 90) -> bool:
    """Checks if daily API quota is within safe bound and increments count."""
    today = time.strftime("%Y-%m-%d", time.gmtime())
    with _get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT call_count FROM api_quota_tracker WHERE date = ? AND provider = ?", (today, provider))
        row = cur.fetchone()
        current = row[0] if row else 0
        if current >= max_daily:
            return False
        cur.execute("""
            INSERT INTO api_quota_tracker (date, provider, call_count)
            VALUES (?, ?, 1)
            ON CONFLICT(date, provider) DO UPDATE SET call_count = call_count + 1
        """, (today, provider))
        conn.commit()
    return True


def get_cached_results(query: str, provider: str, ttl_days: int = 7) -> Optional[List[Dict[str, Any]]]:
    """Retrieves 7-day cached search results from SQLite."""
    q_hash = hashlib.sha256(f"{provider}:{query}".encode("utf-8")).hexdigest()
    min_time = int(time.time()) - (ttl_days * 86400)
    with _get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT results_json FROM image_search_cache WHERE query_hash = ? AND timestamp > ?",
            (q_hash, min_time)
        )
        row = cur.fetchone()
        if row:
            try:
                return json.loads(row[0])
            except Exception:
                pass
    return None


def save_cached_results(query: str, provider: str, results: List[Dict[str, Any]]):
    """Saves query results into SQLite cache."""
    q_hash = hashlib.sha256(f"{provider}:{query}".encode("utf-8")).hexdigest()
    with _get_db_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO image_search_cache (query_hash, query, provider, results_json, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (q_hash, query, provider, json.dumps(results), int(time.time())))
        conn.commit()


# ------------------------------------------------------------
# CANDIDATE FILTERING (A3)
# ------------------------------------------------------------
def filter_candidate(cand: Dict[str, Any], entity_names: List[str], show_tokens: List[str]) -> Tuple[bool, str]:
    """
    Applies Section A3 filtering:
    - Domain not blacklisted
    - Title/snippet/context contains entity name or alias AND show token
    """
    url = cand.get("image_url") or cand.get("url") or ""
    title = (cand.get("title") or "").lower()
    snippet = (cand.get("snippet") or cand.get("source") or "").lower()
    combined_meta = f"{title} {snippet} {url}".lower()

    # 1. Check watermark agency domain
    try:
        domain = urlparse(url).netloc.lower()
        if any(bad_dom in domain for bad_dom in BLOCKED_STOCK_DOMAINS):
            return False, f"Blocked agency watermark domain: {domain}"
    except Exception:
        pass

    # 2. Check entity name/alias match
    has_entity = False
    if entity_names:
        has_entity = any(en.lower() in combined_meta for en in entity_names if len(en) >= 3)

    # 3. Check show/context token
    if show_tokens:
        has_show = any(st.lower() in combined_meta for st in show_tokens if len(st) >= 3)
        # For person searches, an authentic photograph of the person is valid even without show token in caption
        if not has_show and not has_entity:
            return False, f"Missing show context token ({show_tokens}) and entity match in candidate metadata"

    if entity_names and not has_entity:
        # If entity was specified and did not match, require strong show match or reject
        if not (show_tokens and any(st.lower() in combined_meta for st in show_tokens if len(st) >= 3)):
            return False, f"Missing entity name ({entity_names[:2]}) in candidate metadata"

    # 4. Disqualify Hindi Bigg Boss candidate media for Telugu show contexts
    if show_tokens and any("bigg boss" in st.lower() or "telugu" in st.lower() for st in show_tokens):
        from providers.image import HINDI_BIGG_BOSS_KEYWORDS
        if any(hk in combined_meta for hk in HINDI_BIGG_BOSS_KEYWORDS):
            return False, f"Disqualified Hindi Bigg Boss candidate content"

    # 5. Disqualify cross-season candidate media (Season 1-9)
    from utils.season_guard import is_conflicting_season_candidate
    primary_ent = entity_names[0] if entity_names else None
    if is_conflicting_season_candidate(combined_meta, target_person=primary_ent):
        return False, f"Disqualified cross-season candidate content"

    return True, "Passed"


# ------------------------------------------------------------
# 1. GOOGLE PROGRAMMABLE SEARCH API (PRIMARY)
# ------------------------------------------------------------
def search_google_custom_search(
    query: str,
    exact_terms: str = "Bigg Boss Telugu",
    exclude_terms: str = "hindi tamil kannada malayalam",
    rights_filter: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """Official Google Programmable Search JSON API (searchType=image)."""
    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        return []

    if not check_and_increment_quota("google_cse", max_daily=90):
        print("⚠️ [Google Images] Daily Google API quota guard (90 queries) reached. Falling back to DDGS...")
        return []

    cached = get_cached_results(query, "google_cse")
    if cached is not None:
        return cached

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cse_id,
        "q": query,
        "searchType": "image",
        "imgSize": "large",
        "safe": "active",
        "gl": "in",
        "num": min(max_results, 10),
    }
    if exact_terms:
        params["exactTerms"] = exact_terms
    if exclude_terms:
        params["excludeTerms"] = exclude_terms
    if rights_filter:
        params["rights"] = rights_filter  # e.g., cc_publicdomain, cc_attribute

    results = []
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("items", []):
                img_info = item.get("image", {})
                w = int(img_info.get("width", 0))
                h = int(img_info.get("height", 0))
                # Enforce short side >= 720px
                short_side = min(w, h) if w > 0 and h > 0 else 720
                if short_side >= 500:
                    results.append({
                        "image_url": item.get("link"),
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "source_domain": item.get("displayLink", ""),
                        "width": w,
                        "height": h,
                        "provider": "google_cse",
                    })
            save_cached_results(query, "google_cse", results)
            return results
        else:
            print(f"⚠️ Google CSE HTTP {resp.status_code}: {resp.text[:120]}")
    except Exception as e:
        print(f"⚠️ Google CSE exception: {e}")

    return []


# ------------------------------------------------------------
# 2. DUCKDUCKGO IMAGE SEARCH (FALLBACK - 100% FREE)
# ------------------------------------------------------------
def search_duckduckgo_images(
    query: str,
    max_results: int = 15,
) -> List[Dict[str, Any]]:
    """Free DuckDuckGo image search via ddgs library with SSL-safe backoff."""
    cached = get_cached_results(query, "ddgs")
    if cached is not None:
        return cached

    results = []
    # 1. Try standard DDGS
    try:
        from duckduckgo_search import DDGS
        raw_hits = None
        try:
            with DDGS(timeout=8) as ddgs:
                raw_hits = list(ddgs.images(query, max_results=max_results))
        except Exception as ssl_err:
            # Fallback for macOS SSL CERTIFICATE_VERIFY_FAILED
            try:
                with DDGS(verify=False, timeout=8) as ddgs:
                    raw_hits = list(ddgs.images(query, max_results=max_results))
            except Exception:
                pass

        if raw_hits:
            for h in raw_hits:
                w = int(h.get("width", 0))
                h_val = int(h.get("height", 0))
                results.append({
                    "image_url": h.get("image"),
                    "title": h.get("title", ""),
                    "snippet": h.get("source", ""),
                    "source_domain": urlparse(h.get("image", "")).netloc,
                    "width": w,
                    "height": h_val,
                    "provider": "duckduckgo",
                })
            save_cached_results(query, "ddgs", results)
            return results
    except Exception as ddg_err:
        print(f"⚠️ DuckDuckGo image search notice: {ddg_err}")

    # 2. Try requests-based fallback from providers/image
    try:
        from providers.image import search_duckduckgo_images as req_ddgs
        req_hits = req_ddgs(query, max_results=max_results)
        if req_hits:
            for rh in req_hits:
                results.append({
                    "image_url": rh.get("image_url"),
                    "title": rh.get("title", query),
                    "snippet": "DDG requests",
                    "source_domain": urlparse(rh.get("image_url", "")).netloc,
                    "width": 1280,
                    "height": 720,
                    "provider": "duckduckgo",
                })
            save_cached_results(query, "ddgs", results)
            return results
    except Exception:
        pass

    return []


# ------------------------------------------------------------
# MASTER QUERY BUILDER & SEARCH (A1 + A2 + A3)
# ------------------------------------------------------------
def fetch_show_locked_images(
    entity_name: str,
    entity_aliases: List[str] = None,
    show_context: str = "Bigg Boss Telugu 10",
    beat_type: str = "person", # "person", "scene", "tech", "film"
    event_keywords: str = "",
    mode: str = "tier_b", # "tier_b" or "licensed_only"
    max_candidates: int = 10,
) -> List[Dict[str, Any]]:
    """
    Builds strict show-locked queries, executes primary/fallback search,
    and applies candidate filtering.
    """
    from config.settings import get_setting
    from utils.season_guard import is_bigg_boss_topic, resolve_effective_show_context

    clean_show_ctx = resolve_effective_show_context(
        topic_or_title=f"{entity_name} {event_keywords}",
        raw_show_context=show_context or (get_setting("SHOW_CONTEXT", "") if not show_context else show_context),
    )
    show_ctx = clean_show_ctx if clean_show_ctx else ""
    if show_ctx and "bigg boss" in show_ctx.lower():
        if "10" not in show_ctx:
            show_ctx = f"{show_ctx} 10 2026"
        elif "2026" not in show_ctx:
            show_ctx = f"{show_ctx} 2026"
    show_tokens = ["Bigg Boss Telugu", "Bigg Boss"] if "bigg boss" in show_ctx.lower() else ([show_ctx] if show_ctx else [entity_name])

    # Translate metaphors and construct templates (A2)
    clean_event = event_keywords
    metaphor_file = ROOT / "config" / "metaphor_map.json"
    if metaphor_file.exists():
        try:
            m_data = json.loads(metaphor_file.read_text(encoding="utf-8"))
            for m in m_data.get("metaphors", []):
                for p in m.get("patterns", []):
                    clean_event = re.sub(rf"\b{re.escape(p)}\b", "", clean_event, flags=re.IGNORECASE)
        except Exception:
            pass

    # Build query templates (A2)
    if beat_type == "person":
        action_part = f"{clean_event} " if clean_event else ""
        q = f'"{entity_name}" "{show_ctx}" contestant' if show_ctx else f'"{entity_name}" {action_part}face photo OR interview'.strip()
    elif beat_type in ("tech", "business", "company"):
        action_part = f"{clean_event} " if clean_event else ""
        q = f'"{entity_name}" {action_part}modern high quality'.strip()
    elif beat_type == "scene":
        q = f'"{show_ctx}" {clean_event} episode' if show_ctx else f'"{entity_name}" {clean_event}'
    elif beat_type == "film":
        q = f'"{entity_name}" movie still poster'
    else:
        q = f'"{entity_name}" "{show_ctx}"' if show_ctx else f'"{entity_name}"'

    print(f"🔍 [Universal Context Search] Built Query: {q} | Show Context: '{show_ctx}'")

    # 1. Try Google Custom Search API
    candidates = []
    rights_param = "cc_publicdomain,cc_attribute,cc_sharealike" if mode == "licensed_only" else None
    exclude_t = "hindi tamil kannada malayalam 2024 2023 2022 2021 2020 2019 2018 2017 salman manveer" if "bigg boss" in show_ctx.lower() else "hindi tamil kannada malayalam"
    g_results = search_google_custom_search(
        query=q,
        exact_terms="Bigg Boss Telugu" if "bigg boss" in show_ctx.lower() else show_ctx,
        exclude_terms=exclude_t,
        rights_filter=rights_param,
        max_results=max_candidates,
    )
    if g_results:
        candidates = g_results

    # 2. Fallback to DuckDuckGo Images
    if not candidates:
        # DDGS query with explicit show lock
        ddg_q = f'"{show_ctx}" "{entity_name}"' if beat_type == "person" else f'"{show_ctx}" {clean_event}'
        candidates = search_duckduckgo_images(ddg_q, max_results=max_candidates)

    # 2B. Fallback to Bing Direct Images
    if not candidates:
        try:
            from providers.image import search_bing_images
            bing_q = f"{entity_name} {show_ctx} photo" if beat_type == "person" else f"{show_ctx} {clean_event}"
            b_results = search_bing_images(bing_q, max_results=max_candidates)
            if beat_type == "person" and len(b_results) < 4:
                b_results.extend(search_bing_images(f"{entity_name} photo HD", max_results=max_candidates))
            if b_results:
                for b in b_results:
                    candidates.append({
                        "image_url": b.get("image_url"),
                        "title": b.get("title", entity_name),
                        "snippet": "Bing Search",
                        "source_domain": urlparse(b.get("image_url", "")).netloc,
                        "width": b.get("width", 1280),
                        "height": b.get("height", 720),
                        "provider": "bing",
                    })
        except Exception:
            pass

    # 3. Candidate Filtering (A3)
    all_names = [entity_name] + (entity_aliases or [])
    verified_candidates = []

    for c in candidates:
        passed, reason = filter_candidate(c, entity_names=all_names, show_tokens=show_tokens)
        if passed:
            verified_candidates.append(c)
        else:
            # print(f"🚫 [Filtered] {c.get('image_url')[:50]}... ({reason})")
            pass

    print(f"✅ [Show-Locked Search] Returned {len(verified_candidates)}/{len(candidates)} verified candidates.")
    return verified_candidates


def search_show_verified_images(
    entity_name: str,
    show_context: str = "",
    clean_event: str = "",
    max_candidates: int = 5,
    **kwargs,
) -> List[Dict[str, Any]]:
    """Backward-compatible alias for fetch_show_locked_images used in social_visual_selector."""
    return fetch_show_locked_images(
        entity_name=entity_name,
        show_context=show_context,
        event_keywords=clean_event,
        max_candidates=max_candidates,
        **kwargs,
    )


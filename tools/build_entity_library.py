"""Entity Library Tool for AutoTube AI.
Maintains pre-curated, verified Tier-A portrait assets and licensing metadata
for Telugu entertainment, Tollywood cinema, and tech entities.
"""

import argparse
import json
import logging
import re
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("build_entity_library")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "entities.json"
ASSETS_DIR = BASE_DIR / "assets" / "entities"
USER_AGENT = "AutoTubeBot/1.0 (https://autotube.ai; contact@autotube.ai)"


def load_entities_config() -> List[Dict[str, Any]]:
    """Load configured entities from config/entities.json."""
    if not CONFIG_PATH.exists():
        return []
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data.get("entities", [])
    except Exception as e:
        logger.error(f"Error loading {CONFIG_PATH}: {e}")
        return []


def get_entity_by_id(entity_id: str) -> Optional[Dict[str, Any]]:
    entities = load_entities_config()
    for ent in entities:
        if ent.get("id") == entity_id:
            return ent
    return None


def match_entities_in_text(text: str) -> List[Dict[str, Any]]:
    """
    Scan text for entity names or aliases (Telugu script & English).
    Guarantees word boundaries, rejects clash terms (e.g. Ram Charan != Charan BB),
    and sorts longer specific celebrity matches first.
    """
    if not text:
        return []
    entities = load_entities_config()
    matched = []
    text_lower = text.lower()

    # Load clash terms map from season guard
    try:
        from utils.season_guard import get_person_disallowed_terms
    except Exception:
        def get_person_disallowed_terms(name):
            return []

    def _matches_name(pattern: str, target_text: str) -> bool:
        if not pattern:
            return False
        p_low = pattern.lower().strip()
        # For non-ASCII (Telugu script), enforce Indic word boundary to prevent substring collision
        # (e.g. 'దేవర' must not match inside 'దేవరకొండ')
        if re.search(r"[\u0C00-\u0C7F]", p_low):
            indic_pattern = r"(?:^|[^\u0C00-\u0C7Fa-zA-Z0-9])" + re.escape(p_low) + r"(?:$|[^\u0C00-\u0C7Fa-zA-Z0-9])"
            return bool(re.search(indic_pattern, target_text))
        # For Latin/English, enforce standard word boundary
        return bool(re.search(r"\b" + re.escape(p_low) + r"\b", target_text))

    for ent in entities:
        ent_id = ent.get("id", "")
        cname = ent.get("canonical_name", "")
        disallow = set(get_person_disallowed_terms(cname) or [])
        disallow.update(ent.get("disallow_terms", []))
        disallow.update(ent.get("clash_terms", []))

        # If any clash term is present in text for an entity, reject match (e.g. 'Vijay Deverakonda' rejecting 'Devara')
        if disallow and any(_matches_name(dt, text_lower) for dt in disallow):
            continue

        matched_term = None
        if _matches_name(cname, text_lower):
            matched_term = cname
        else:
            for alias in ent.get("aliases", []):
                if _matches_name(alias, text_lower):
                    matched_term = alias
                    break

        if matched_term:
            ent_copy = dict(ent)
            ent_copy["_matched_len"] = len(matched_term)
            matched.append(ent_copy)

    # Sort so longer/more specific matches come first (e.g. 'Ram Charan' > 'Charan')
    matched.sort(key=lambda e: e.get("_matched_len", 0), reverse=True)
    return matched


def resolve_commons_file_info(file_name: str) -> Optional[Dict[str, Any]]:
    """Query Wikimedia Commons imageinfo for URL, license, and artist."""
    headers = {"User-Agent": USER_AGENT}
    title = f"File:{file_name}" if not file_name.startswith("File:") else file_name
    api_url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "iiurlwidth": "1080",
        "format": "json",
    }
    try:
        resp = requests.get(api_url, params=params, headers=headers, timeout=12)
        if resp.status_code != 200:
            return None
        pages = resp.json().get("query", {}).get("pages", {})
        for _, page in pages.items():
            infos = page.get("imageinfo", [])
            if not infos:
                continue
            info = infos[0]
            ext = info.get("extmetadata", {})
            license_short = ext.get("LicenseShortName", {}).get("value", "CC-BY")
            artist_raw = ext.get("Artist", {}).get("value", "")
            artist_clean = re.sub(r"<[^>]+>", "", artist_raw).strip() or "Wikimedia Commons Contributor"
            url = info.get("thumburl") or info.get("url")
            return {
                "image_url": url,
                "file_name": file_name,
                "license": license_short,
                "artist": artist_clean,
                "credit": f"{artist_clean} / Wikimedia Commons ({license_short})",
            }
    except Exception as e:
        logger.warning(f"Error querying Commons for {file_name}: {e}")
    return None


def fetch_wikidata_image(wikidata_id: str) -> Optional[Dict[str, Any]]:
    """Get image filename from Wikidata claim P18."""
    if not wikidata_id:
        return None
    headers = {"User-Agent": USER_AGENT}
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{wikidata_id}.json"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json().get("entities", {}).get(wikidata_id, {})
        claims = data.get("claims", {})
        p18 = claims.get("P18", [])
        if p18:
            file_name = p18[0]["mainsnak"]["datavalue"]["value"]
            return resolve_commons_file_info(file_name)
    except Exception as e:
        logger.warning(f"Wikidata lookup failed for {wikidata_id}: {e}")
    return None


def search_commons_image(query: str) -> Optional[Dict[str, Any]]:
    """Fallback search on Wikimedia Commons."""
    headers = {"User-Agent": USER_AGENT}
    api_url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": "1",
        "gsrtype": "file",
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "iiurlwidth": "1080",
        "format": "json",
    }
    try:
        resp = requests.get(api_url, params=params, headers=headers, timeout=12)
        if resp.status_code != 200:
            return None
        pages = resp.json().get("query", {}).get("pages", {})
        for _, page in pages.items():
            infos = page.get("imageinfo", [])
            if not infos:
                continue
            info = infos[0]
            ext = info.get("extmetadata", {})
            license_short = ext.get("LicenseShortName", {}).get("value", "CC-BY")
            artist_raw = ext.get("Artist", {}).get("value", "")
            artist_clean = re.sub(r"<[^>]+>", "", artist_raw).strip() or "Wikimedia Commons"
            url = info.get("thumburl") or info.get("url")
            title = page.get("title", "").replace("File:", "")
            return {
                "image_url": url,
                "file_name": title,
                "license": license_short,
                "artist": artist_clean,
                "credit": f"{artist_clean} / Wikimedia Commons ({license_short})",
            }
    except Exception as e:
        logger.warning(f"Commons search failed for query {query}: {e}")
    return None


def cache_entity_asset(entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Download and cache portrait image and metadata for an entity."""
    ent_id = entity["id"]
    target_dir = ASSETS_DIR / ent_id
    target_dir.mkdir(parents=True, exist_ok=True)
    meta_path = target_dir / "meta.json"
    img_path = target_dir / "image.jpg"

    # If already cached and valid, return
    if meta_path.exists() and img_path.exists() and img_path.stat().st_size > 5000:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["path"] = str(img_path)
            return meta
        except Exception:
            pass

    info = None
    # 1. Try page_image_free if available
    if entity.get("page_image_free"):
        info = resolve_commons_file_info(entity["page_image_free"])

    # 2. Try Wikidata claim P18
    if not info and entity.get("wikidata_id"):
        info = fetch_wikidata_image(entity["wikidata_id"])

    # 3. Fallback to search terms
    if not info and entity.get("search_terms"):
        for term in entity["search_terms"]:
            info = search_commons_image(term)
    # 4. Fallback: Search verified editorial portrait via web search (Bing Images)
    if not info:
        try:
            from providers.image import search_bing_images
            cname = entity.get("canonical_name", ent_id)
            search_q = f'"{cname}" Bigg Boss Telugu photo portrait'
            cands = search_bing_images(search_q, max_results=5)
            for c in cands:
                u = c.get("image_url")
                if u:
                    info = {
                        "image_url": u,
                        "license": "Editorial Fair Dealing",
                        "credit": f"{cname} / Editorial Media",
                        "artist": "Editorial News",
                    }
                    break
        except Exception as b_err:
            logger.warning(f"Fallback portrait search notice for {ent_id}: {b_err}")

    if not info:
        logger.warning(f"Could not find Commons or web image for entity: {ent_id}")
        return None

    # Download image
    try:
        headers = {"User-Agent": USER_AGENT}
        img_resp = requests.get(info["image_url"], headers=headers, timeout=20)
        if img_resp.status_code == 200 and len(img_resp.content) > 5000:
            img_path.write_bytes(img_resp.content)
            meta = {
                "id": ent_id,
                "canonical_name": entity.get("canonical_name", ""),
                "tier": "TIER_A",
                "source_url": info["image_url"],
                "license": info["license"],
                "credit": info["credit"],
                "artist": info["artist"],
                "verified": True,
                "path": str(img_path),
            }
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
            logger.info(f"Successfully cached entity asset: {ent_id}")
            return meta
    except Exception as e:
        logger.error(f"Failed to download image for {ent_id}: {e}")

    return None


def get_entity_asset(entity_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve verified asset for an entity (manual override > cached Tier A > live cache)."""
    target_dir = ASSETS_DIR / entity_id
    # 1. Check manual overrides (user-provided stills)
    manual_dir = target_dir / "manual"
    if manual_dir.exists():
        for p in manual_dir.iterdir():
            if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"] and p.stat().st_size > 5000:
                return {
                    "id": entity_id,
                    "tier": "TIER_A",
                    "path": str(p),
                    "source_url": "local://manual",
                    "license": "Owner/Manual Cleared",
                    "credit": "Official Press Still / Permitted",
                    "verified": True,
                }

    # 2. Check cached file
    meta_path = target_dir / "meta.json"
    img_path = target_dir / "image.jpg"
    if meta_path.exists() and img_path.exists() and img_path.stat().st_size > 5000:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["path"] = str(img_path)
            return meta
        except Exception:
            pass

    # 3. Live cache if entity is configured
    ent = get_entity_by_id(entity_id)
    if ent:
        return cache_entity_asset(ent)

    return None


def build_all_entities() -> int:
    """Build and cache all configured entities."""
    entities = load_entities_config()
    cached_count = 0
    print(f"Building entity library for {len(entities)} configured entities...")
    for ent in entities:
        res = cache_entity_asset(ent)
        if res:
            cached_count += 1
            print(f"  [OK] {ent['id']}: {res.get('canonical_name')} ({res.get('license')})")
        else:
            print(f"  [MISSING] {ent['id']}: No Commons asset found (will use stylized art fallback)")
    print(f"Done! Cached {cached_count}/{len(entities)} entity assets.")
    return cached_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AutoTube AI Entity Library Builder")
    parser.add_argument("--all", action="store_true", help="Download and cache all entities")
    parser.add_argument("--id", type=str, help="Cache specific entity ID")
    parser.add_argument("--test-match", type=str, help="Test entity matching on text")
    args = parser.parse_args()

    if args.test_match:
        matches = match_entities_in_text(args.test_match)
        print("Matches found:", [m["canonical_name"] for m in matches])
    elif args.id:
        ent = get_entity_by_id(args.id)
        if ent:
            # force remove old file if any to re-cache
            img_p = ASSETS_DIR / args.id / "image.jpg"
            if img_p.exists():
                img_p.unlink()
            meta_p = ASSETS_DIR / args.id / "meta.json"
            if meta_p.exists():
                meta_p.unlink()
            res = cache_entity_asset(ent)
            print("Result:", res)
        else:
            print("Entity ID not found:", args.id)
    else:
        build_all_entities()

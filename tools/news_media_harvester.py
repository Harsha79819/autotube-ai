#!/usr/bin/env python3
"""
tools/news_media_harvester.py - Automated Telugu News Media Harvester

Scrapes and extracts authentic high-resolution Telugu news images, episode stills,
and contestant photos directly from verified Telugu entertainment & news portals:
  - telugu.samayam.com (Times Internet)
  - www.sakshi.com
  - www.v6velugu.com
  - www.eenadu.net / tupaki.com / greatandhra.com / 10tv.in / tv9telugu.com

Key Features:
1. Dynamic Topic Sensitivity: Strict Bigg Boss 10 enforcement ONLY when topic is Bigg Boss;
   dynamically supports any other topic (tech, movie reviews, sports, etc.) without injecting BB keywords.
2. In-Article Content Targeting: Strips sidebars, trending, and footer widgets to eliminate
   political thumbnail leakage (e.g. YS Jagan / Chandrababu Naidu).
3. Prior Season Firewall & Entity Disambiguation: Rejects Season 1-9 artifacts, BB Malayalam/Kannada/Hindi,
   and namesake mix-ups (e.g. Rohit Sahni vs Rohit Patnam).
4. Concurrent Multi-URL Extraction: Uses ThreadPoolExecutor to discover and harvest images in parallel.
"""

import os
import re
import time
import hashlib
import urllib.parse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from PIL import Image

import sys
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from data.bb10_contestants import (
        validate_candidate_metadata,
        is_bigg_boss_context,
        check_political_blacklist,
        check_prior_seasons,
    )
except ImportError:
    def is_bigg_boss_context(t: str) -> bool:
        t_l = str(t).lower()
        return "bigg boss" in t_l or "biggboss" in t_l or "బిగ్ బాస్" in t

    def validate_candidate_metadata(url: str, title: str = "", caption: str = "", entity_hint: str = "", is_bb: bool = True) -> Tuple[bool, str]:
        comb = f"{url} {title} {caption}".lower()
        if any(p in comb for p in ["jagan", "ysr", "chandrababu", "naidu", "pawan kalyan", "revanth"]):
            return False, "politics"
        if is_bb and any(s in comb for s in ["season-6", "season 6", "bb6", "season-7", "bb7", "season-8", "bb8", "season-9", "bb9", "malayalam"]):
            return False, "prior_season"
        return True, "OK"

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache" / "news_episodes"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DISCOVERED_ARTICLES_FILE = CACHE_DIR.parent / "discovered_article_urls.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "te,en-US,en;q=0.9",
}

VERIFIED_DOMAINS = [
    "telugu.samayam.com",
    "www.sakshi.com",
    "sakshi.com",
    "www.v6velugu.com",
    "v6velugu.com",
    "www.eenadu.net",
    "eenadu.net",
    "tv9telugu.com",
    "10tv.in",
    "ntvtelugu.com",
    "telugu.abplive.com",
    "abplive.com",
    "telugu.news18.com",
    "news18.com",
    "telugu.asianetnews.com",
    "asianetnews.com",
    "telugu.hindustantimes.com",
    "hindustantimes.com",
    "telugu.filmibeat.com",
    "filmibeat.com",
    "telugu.oneindia.com",
    "tupaki.com",
    "greatandhra.com",
    "gulte.com",
    "123telugu.com",
    "cinemaexpress.com",
    "telugubulletin.com",
    "andhrajyothy.com",
    "vaartha.com",
    "namasthetelangaana.com",
    "suryaa.com",
    "etvbharat.com",
    "m9.news",
    "telugucinema.com",
    "telugu.timesnownews.com",
    "timesnownews.com",
    "msn.com",
]

DISALLOWED_IMAGE_TOKENS = [
    "logo", "icon", "banner", "author", "advertisement", "header", "footer",
    "whatsapp", "telegram", "facebook", "twitter", "share", "profile", "avatar",
    "scorecardresearch", "google-analytics", "favicon"
]

def record_discovered_article(url: str, title: str = "", query: str = "", image_count: int = 0):
    """Persists newly discovered Telugu news article links into continuous ledger."""
    try:
        import json
        articles = []
        if DISCOVERED_ARTICLES_FILE.exists():
            try:
                articles = json.loads(DISCOVERED_ARTICLES_FILE.read_text(encoding="utf-8"))
                if not isinstance(articles, list):
                    articles = []
            except Exception:
                articles = []
        existing_urls = {a.get("url") for a in articles if isinstance(a, dict)}
        if url not in existing_urls:
            domain = urllib.parse.urlsplit(url).netloc
            articles.append({
                "url": url,
                "domain": domain,
                "title": title[:100] if title else "",
                "query": query[:60] if query else "",
                "images_harvested": image_count,
                "discovered_at": time.time(),
            })
            if len(articles) > 200:
                articles = articles[-200:]
            DISCOVERED_ARTICLES_FILE.write_text(json.dumps(articles, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"Notice: Could not record discovered article: {e}")


def _is_valid_image_url(url: str, is_bb: bool = True, entity_hint: str = "") -> bool:
    if not url or not isinstance(url, str):
        return False
    u_lower = url.lower()
    if any(tok in u_lower for tok in DISALLOWED_IMAGE_TOKENS):
        return False
    if not (u_lower.startswith("//") or u_lower.startswith("http://") or u_lower.startswith("https://")):
        return False
    ok, _ = validate_candidate_metadata(url, is_bb=is_bb, entity_hint=entity_hint)
    return ok


def extract_images_from_article_url(
    url: str,
    max_images: int = 5,
    is_bb: bool = True,
    entity_hint: str = ""
) -> List[Path]:
    """
    Extracts high-resolution editorial photos and episode stills from a specific article URL.
    Enforces in-article body parsing (strips sidebars/trending widgets) and validates metadata.
    """
    if not url.startswith("http"):
        return []

    # Fast pre-validation on URL string
    ok, reason = validate_candidate_metadata(url, is_bb=is_bb, entity_hint=entity_hint)
    if not ok:
        return []

    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
    saved_paths = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=9)
        if resp.status_code != 200 or not resp.content:
            return []

        soup = BeautifulSoup(resp.content, "html.parser")

        # Validate page title
        page_title = soup.title.string.strip() if soup.title and soup.title.string else ""
        ok_title, _ = validate_candidate_metadata(url, title=page_title, is_bb=is_bb, entity_hint=entity_hint)
        if not ok_title:
            return []

        # Anti-sidebar / trending widget strip (eliminates political thumbnail leakage)
        for bad_elem in soup.find_all(attrs={"class": re.compile(r"sidebar|trending|widget|related|footer|popular|recommend|promo|ads|commercial|comment", re.I)}):
            bad_elem.decompose()
        for bad_elem in soup.find_all(attrs={"id": re.compile(r"sidebar|trending|widget|related|footer|popular|recommend|promo|ads|commercial|comment", re.I)}):
            bad_elem.decompose()

        candidate_urls = []

        # 1. Primary candidate: OpenGraph og:image (high resolution editorial headline image)
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            c_url = og_img.get("content").strip()
            if _is_valid_image_url(c_url, is_bb=is_bb, entity_hint=entity_hint):
                candidate_urls.append((c_url, page_title))

        # 2. In-article episode photos inside main article container
        article_container = (
            soup.find("article")
            or soup.find("div", class_=re.compile(r"article|story|content|body", re.I))
            or soup
        )

        for img in article_container.find_all("img"):
            src = (
                img.get("data-src")
                or img.get("data-original")
                or img.get("src")
                or ""
            ).strip()
            if not src:
                continue
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                base = urllib.parse.urlsplit(url)
                src = f"{base.scheme}://{base.netloc}{src}"

            img_caption = img.get("alt", "") or img.get("title", "")
            if not _is_valid_image_url(src, is_bb=is_bb, entity_hint=entity_hint):
                continue
            ok_img, _ = validate_candidate_metadata(src, caption=img_caption, is_bb=is_bb, entity_hint=entity_hint)
            if not ok_img:
                continue

            if not any(src == u[0] for u in candidate_urls):
                candidate_urls.append((src, img_caption))

        # 3. Download, validate resolution and aspect ratio
        img_idx = 1
        for c_url, c_cap in candidate_urls:
            if len(saved_paths) >= max_images:
                break
            try:
                i_resp = requests.get(c_url, headers=HEADERS, timeout=8)
                if i_resp.status_code != 200 or len(i_resp.content) < 8000:
                    continue

                with Image.open(BytesIO(i_resp.content)) as im:
                    w, h = im.size
                    if w < 400 or h < 250:
                        continue
                    aspect = w / max(1, h)
                    if aspect > 3.0 or aspect < 0.3:
                        continue

                    out_path = CACHE_DIR / f"news_{url_hash}_{img_idx}.jpg"
                    im_rgb = im.convert("RGB")
                    im_rgb.save(out_path, "JPEG", quality=92)
                    try:
                        from tools.watermark_remover import clean_and_remove_watermarks
                        is_clean, cleaned_p = clean_and_remove_watermarks(out_path)
                        if is_clean:
                            saved_paths.append(cleaned_p)
                            img_idx += 1
                        else:
                            out_path.unlink(missing_ok=True)
                    except Exception:
                        saved_paths.append(out_path)
                        img_idx += 1
            except Exception:
                continue

    except Exception as e:
        print(f"⚠️ Notice during article image extraction ({url[:45]}): {e}")

    return saved_paths


def search_news_article_urls(
    query: str,
    max_articles: int = 5,
    is_bb: Optional[bool] = None,
    entity_hint: str = ""
) -> List[str]:
    """
    Autonomously discovers fresh Telugu news article URLs matching query across 25+ major Telugu publications.
    Dynamically respects topic: only enforces Bigg Boss 10 if is_bb is True.
    """
    article_urls = []
    clean_q = re.sub(r"[^\w\s]", " ", query).strip()
    if not clean_q:
        return article_urls

    if is_bb is None:
        is_bb = is_bigg_boss_context(clean_q)

    bad_domains = (
        "youtube.com", "youtu.be", "facebook.com", "instagram.com", "twitter.com",
        "x.com", "pinterest.com", "reddit.com", "amazon.", "flipkart.com", "wikipedia.org",
        "imdb.com", "quora.com", "linkedin.com", "tiktok.com",
        "malayalam.", "kannada.", "gujarati.", "tamil.", "hindi."
    )

    # Method 1: High-Speed Bing Endpoint
    try:
        bing_url = "https://www.bing.com/images/search"
        if is_bb:
            search_terms = f'"{clean_q}" "Bigg Boss Telugu 10"' if "bigg boss" not in clean_q.lower() else clean_q
        else:
            search_terms = clean_q

        params = {"q": search_terms, "form": "HDRSC2", "first": "1"}
        resp = requests.get(bing_url, params=params, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            found_purls = re.findall(r'purl&quot;:&quot;(https?://[^&]+)&quot;', resp.text)
            for raw_p in found_purls:
                p_url = raw_p.replace("\\/", "/").replace("\\u002f", "/")
                if not p_url.startswith("http") or any(b in p_url.lower() for b in bad_domains):
                    continue
                low_p = p_url.lower()
                is_news_domain = any(dom in low_p for dom in VERIFIED_DOMAINS)
                is_news_path = any(k in low_p for k in ("/entertainment/", "/bigg-boss", "/tv/", "/movies/", "/television/", "/articleshow/", "/cinema/", "/article/"))
                if is_news_domain or is_news_path:
                    ok, _ = validate_candidate_metadata(p_url, is_bb=is_bb, entity_hint=entity_hint or clean_q)
                    if ok and p_url not in article_urls:
                        article_urls.append(p_url)
                        record_discovered_article(p_url, query=clean_q)
                        if len(article_urls) >= max_articles:
                            break
    except Exception as b_err:
        print(f"Notice: Bing news article discovery ({clean_q[:30]}): {b_err}")

    # Method 2: DuckDuckGo HTML fallback across verified Telugu news portals
    if len(article_urls) < max_articles:
        try:
            sample_domains = ["telugu.samayam.com", "sakshi.com", "v6velugu.com", "eenadu.net", "tv9telugu.com", "10tv.in", "telugu.hindustantimes.com", "telugu.filmibeat.com"]
            site_filter = " OR ".join([f"site:{d}" for d in sample_domains])
            search_query = f"({site_filter}) {clean_q}"
            ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(search_query)}"
            r = requests.get(ddg_url, headers=HEADERS, timeout=8)
            if r.status_code == 200:
                soup = BeautifulSoup(r.content, "html.parser")
                for a in soup.find_all("a", class_="result__url"):
                    href = a.get("href", "").strip()
                    if "uddg=" in href:
                        raw_dest = href.split("uddg=")[1].split("&")[0]
                        target_url = urllib.parse.unquote(raw_dest)
                    else:
                        target_url = href

                    if not any(b in target_url.lower() for b in bad_domains):
                        if any(dom in target_url.lower() for dom in VERIFIED_DOMAINS):
                            ok, _ = validate_candidate_metadata(target_url, is_bb=is_bb, entity_hint=entity_hint or clean_q)
                            if ok and target_url not in article_urls:
                                article_urls.append(target_url)
                                record_discovered_article(target_url, query=clean_q)
                                if len(article_urls) >= max_articles:
                                    break
        except Exception as ddg_err:
            print(f"Notice: DDG news search ({clean_q[:30]}): {ddg_err}")

    return article_urls


def harvest_news_images(
    query_or_url: str,
    max_images: int = 10,
    is_bb: Optional[bool] = None,
    entity_hint: str = ""
) -> List[Path]:
    """
    Main entry point for autonomous news media harvesting.
    Accepts either an article URL or search query string (e.g. 'Shalini Patel Rohit Patnam').
    Supports concurrent multi-URL harvesting, dynamic topic context, and strict entity verification.
    """
    if not query_or_url or not str(query_or_url).strip():
        return []

    target = str(query_or_url).strip()
    if is_bb is None:
        is_bb = is_bigg_boss_context(target)

    # Case 1: Direct URL provided
    if target.startswith("http://") or target.startswith("https://"):
        imgs = extract_images_from_article_url(target, max_images=max_images, is_bb=is_bb, entity_hint=entity_hint)
        record_discovered_article(target, query="direct_url", image_count=len(imgs))
        return imgs

    # Case 2: Query string provided -> Search news portals
    clean_q = re.sub(r"[^\w\s]", " ", target).strip()
    article_urls = search_news_article_urls(clean_q, max_articles=5, is_bb=is_bb, entity_hint=entity_hint)
    harvested_images = []
    seen_hashes = set()

    # Concurrent multi-URL extraction
    if article_urls:
        with ThreadPoolExecutor(max_workers=min(5, len(article_urls))) as executor:
            future_to_url = {
                executor.submit(extract_images_from_article_url, a_url, 3, is_bb, entity_hint or clean_q): a_url
                for a_url in article_urls
            }
            for future in as_completed(future_to_url):
                a_url = future_to_url[future]
                try:
                    imgs = future.result()
                    for img_p in imgs:
                        if len(harvested_images) >= max_images:
                            break
                        try:
                            h = hashlib.md5(img_p.read_bytes()).hexdigest()
                            if h not in seen_hashes:
                                seen_hashes.add(h)
                                harvested_images.append(img_p)
                        except Exception:
                            harvested_images.append(img_p)
                    record_discovered_article(a_url, query=target, image_count=len(imgs))
                except Exception as ex:
                    print(f"Notice: Error harvesting from {a_url[:40]}: {ex}")

    # Case 3: Direct verified Telugu news image harvesting across domains if needed
    if len(harvested_images) < max_images:
        try:
            from providers.image import search_bing_images
            top_domains = [
                "telugu.samayam.com", "sakshi.com", "v6velugu.com", "tv9telugu.com", "10tv.in",
                "eenadu.net", "abplive.com", "news18.com", "hindustantimes.com", "filmibeat.com",
                "tupaki.com", "greatandhra.com", "gulte.com", "123telugu.com", "vaartha.com"
            ]
            domains_filter = " OR ".join([f"site:{d}" for d in top_domains])
            if is_bb:
                news_img_q = f"({clean_q} 'Bigg Boss') ({domains_filter})"
            else:
                news_img_q = f"({clean_q}) ({domains_filter})"

            candidates = search_bing_images(news_img_q, max_results=(max_images - len(harvested_images)) * 3)

            def download_direct_cand(cand):
                i_url = cand.get("image_url")
                if not i_url:
                    return None
                ok, _ = validate_candidate_metadata(
                    i_url,
                    title=cand.get("title", ""),
                    is_bb=is_bb,
                    entity_hint=entity_hint or clean_q
                )
                if not ok:
                    return None
                try:
                    i_resp = requests.get(i_url, headers=HEADERS, timeout=8)
                    if i_resp.status_code == 200 and len(i_resp.content) >= 8000:
                        with Image.open(BytesIO(i_resp.content)) as im:
                            w, h = im.size
                            if w >= 400 and h >= 250:
                                im_bytes = i_resp.content
                                f_h = hashlib.md5(im_bytes).hexdigest()
                                h_name = f_h[:10]
                                out_path = CACHE_DIR / f"news_domain_{h_name}.jpg"
                                im.convert("RGB").save(out_path, "JPEG", quality=92)
                                try:
                                    from tools.watermark_remover import clean_and_remove_watermarks
                                    is_clean, cleaned_p = clean_and_remove_watermarks(out_path)
                                    if not is_clean:
                                        out_path.unlink(missing_ok=True)
                                        return None
                                    out_path = cleaned_p
                                except Exception:
                                    pass
                                return (f_h, out_path)
                except Exception:
                    pass
                return None

            with ThreadPoolExecutor(max_workers=4) as cand_exec:
                cand_futures = [cand_exec.submit(download_direct_cand, c) for c in candidates]
                for fut in as_completed(cand_futures):
                    if len(harvested_images) >= max_images:
                        break
                    res = fut.result()
                    if res:
                        f_h, out_path = res
                        if f_h not in seen_hashes:
                            seen_hashes.add(f_h)
                            harvested_images.append(out_path)

        except Exception as direct_err:
            print(f"Notice: Direct news domain harvesting ({target[:30]}): {direct_err}")

    return harvested_images


if __name__ == "__main__":
    import sys
    test_query = sys.argv[1] if len(sys.argv) > 1 else "Bigg Boss Telugu 10 Rohit Patnam"
    print(f"Testing News Media Harvester with: '{test_query}'...")
    results = harvest_news_images(test_query, max_images=3)
    print(f"Harvested {len(results)} images:")
    for p in results:
        print(f"  • {p} ({p.stat().st_size // 1024} KB)")

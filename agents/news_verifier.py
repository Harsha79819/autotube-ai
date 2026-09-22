import html
import json
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup
from googlenewsdecoder import gnewsdecoder


RSS_URL = (
    "https://news.google.com/rss/search?"
    "q={query}&hl=en-IN&gl=IN&ceid=IN:en"
)


def _clean(text):
    """
    Convert RSS/article text into clean plain text.
    Also repairs common UTF-8 / Windows-1252 mojibake.
    """

    value = html.unescape(text or "")

    # Repair common mojibake caused by UTF-8 bytes being
    # incorrectly decoded as Latin-1 / Windows-1252.
    try:
        if any(
            marker in value
            for marker in (
                "â",
                "Â",
                "Ã",
                "ð",
            )
        ):
            value = value.encode(
                "latin1"
            ).decode(
                "utf-8"
            )
    except (
        UnicodeEncodeError,
        UnicodeDecodeError,
    ):
        pass

    # Remove HTML tags.
    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    # Decode entities again after tag removal.
    value = html.unescape(value)

    # Normalize whitespace.
    value = re.sub(
        r"\\s+",
        " ",
        value,
    )

    return value.strip()

def _extract_article_media(soup, article_url):
    """
    Extract real incident media (lead image, inline article photos, embedded videos)
    directly from the parsed publisher HTML page.
    """
    media = {
        "lead_image": None,
        "images": [],
        "videos": [],
    }
    seen_urls = set()

    def _clean_url(raw_url):
        if not raw_url or not isinstance(raw_url, str):
            return None
        raw_url = raw_url.strip()
        if not raw_url or raw_url.startswith("data:") or raw_url.startswith("blob:") or raw_url.startswith("javascript:"):
            return None
        full_url = urljoin(article_url, raw_url)
        parsed = urlparse(full_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None
        return full_url

    def _is_junk_image(url_str, alt_text="", width=None, height=None):
        url_lower = url_str.lower()
        alt_lower = (alt_text or "").lower()
        combined = f"{url_lower} {alt_lower}"

        # Dimensions check from explicit attributes
        try:
            if width is not None and int(width) < 250:
                return True
            if height is not None and int(height) < 150:
                return True
        except (ValueError, TypeError):
            pass

        # Dimensions check from URL filename (e.g. image-96x96.jpg, thumb_100x100.png)
        dim_match = re.search(r"[-_](\d{2,4})x(\d{2,4})", url_lower)
        if dim_match:
            try:
                dw, dh = int(dim_match.group(1)), int(dim_match.group(2))
                if dw < 250 or dh < 150:
                    return True
            except Exception:
                pass

        # Skip SVGs, GIFs, and tiny format icons
        if url_lower.endswith(".svg") or ".svg?" in url_lower:
            return True
        if url_lower.endswith(".gif") or ".gif?" in url_lower:
            return True
        if url_lower.endswith(".ico") or ".ico?" in url_lower:
            return True

        # Check whole-word logo, watermark, avatar in alt text or URL
        if re.search(r"\b(logo|logos|watermark|avatar|gravatar|favicon)\b", combined):
            return True

        junk_patterns = [
            "avatar", "author", "user-profile", "user_profile", "gravatar",
            "site-logo", "publisher-logo", "brand-logo", "/logo.", "/logo-",
            "logo_", "logo-header", "logo-footer", "favicon", "share-icon",
            "social-icon", "social_share", "social-buttons", "button",
            "pixel", "1x1", "spacer", "tracking", "beacon", "ad-banner",
            "advertisement", "sponsor-logo", "newsletter", "watermark",
            "placeholder", "loading.gif", "blank.png", "spinner",
        ]
        for pat in junk_patterns:
            if pat in combined:
                return True
        return False

    def _parse_srcset(srcset_str):
        if not srcset_str:
            return None
        candidates = []
        for item in srcset_str.split(","):
            parts = item.strip().split()
            if not parts:
                continue
            url_part = parts[0]
            size_val = 0
            if len(parts) > 1:
                size_str = parts[1].lower()
                if size_str.endswith("w"):
                    try:
                        size_val = int(size_str[:-1])
                    except ValueError:
                        size_val = 0
                elif size_str.endswith("x"):
                    try:
                        size_val = int(float(size_str[:-1]) * 1000)
                    except ValueError:
                        size_val = 0
            candidates.append((size_val, url_part))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
        return None

    # ----------------------------------------------------
    # 1. OpenGraph & Twitter Card Metadata (Hero / Lead Media)
    # ----------------------------------------------------
    og_image = None
    for meta_prop in [
        "og:image",
        "og:image:url",
        "og:image:secure_url",
        "twitter:image",
        "twitter:image:src",
    ]:
        tag = soup.find("meta", attrs={"property": meta_prop}) or soup.find("meta", attrs={"name": meta_prop})
        if tag and tag.get("content"):
            cleaned = _clean_url(tag.get("content"))
            if cleaned and not _is_junk_image(cleaned):
                og_image = cleaned
                break

    if og_image:
        media["lead_image"] = og_image
        seen_urls.add(og_image)
        media["images"].append({
            "url": og_image,
            "type": "lead_image",
            "caption": "",
        })

    # ----------------------------------------------------
    # 2. JSON-LD Schema (Article / NewsArticle / ImageObject)
    # ----------------------------------------------------
    for script in soup.find_all("script", type="application/ld+json"):
        raw_json = script.string or script.get_text(strip=True)
        if not raw_json:
            continue
        try:
            data = json.loads(raw_json)
            objs = data if isinstance(data, list) else [data]
            graph_objs = []
            for item in objs:
                if isinstance(item, dict) and "@graph" in item and isinstance(item["@graph"], list):
                    graph_objs.extend(item["@graph"])
                elif isinstance(item, dict):
                    graph_objs.append(item)

            for obj in graph_objs:
                if not isinstance(obj, dict):
                    continue

                # Images
                img_data = obj.get("image") or obj.get("thumbnailUrl")
                if img_data:
                    img_list = img_data if isinstance(img_data, list) else [img_data]
                    for candidate in img_list:
                        img_url = None
                        caption = ""
                        w, h = None, None
                        if isinstance(candidate, str):
                            img_url = _clean_url(candidate)
                        elif isinstance(candidate, dict):
                            img_url = _clean_url(candidate.get("url") or candidate.get("contentUrl"))
                            caption = candidate.get("caption") or candidate.get("description") or ""
                            w = candidate.get("width")
                            h = candidate.get("height")

                        if img_url and img_url not in seen_urls and not _is_junk_image(img_url, caption, w, h):
                            seen_urls.add(img_url)
                            if not media["lead_image"]:
                                media["lead_image"] = img_url
                            media["images"].append({
                                "url": img_url,
                                "type": "json_ld",
                                "caption": str(caption).strip(),
                                "width": w,
                                "height": h,
                            })

                # Videos
                vid_data = obj.get("video")
                if vid_data:
                    vid_list = vid_data if isinstance(vid_data, list) else [vid_data]
                    for candidate in vid_list:
                        vid_url = None
                        caption = ""
                        if isinstance(candidate, str):
                            vid_url = _clean_url(candidate)
                        elif isinstance(candidate, dict):
                            vid_url = _clean_url(
                                candidate.get("contentUrl") or candidate.get("embedUrl") or candidate.get("url")
                            )
                            caption = candidate.get("name") or candidate.get("description") or ""
                            v_thumb = _clean_url(candidate.get("thumbnailUrl"))
                            if v_thumb and v_thumb not in seen_urls and not _is_junk_image(v_thumb):
                                seen_urls.add(v_thumb)
                                media["images"].append({
                                    "url": v_thumb,
                                    "type": "video_thumbnail",
                                    "caption": str(caption).strip(),
                                })
                        if vid_url and vid_url not in seen_urls:
                            seen_urls.add(vid_url)
                            media["videos"].append({
                                "url": vid_url,
                                "type": "json_ld_video",
                                "caption": str(caption).strip(),
                            })
        except Exception:
            continue

    # ----------------------------------------------------
    # 3. Inline <img> Elements in Article Body
    # ----------------------------------------------------
    content_container = (
        soup.find("article")
        or soup.find("main")
        or soup.find(class_=re.compile(r"(article|story|post|entry|content)-body", re.I))
        or soup.find(id=re.compile(r"(article|story|post|entry|content)-body", re.I))
        or soup.body
        or soup
    )

    if content_container:
        for img in content_container.find_all("img"):
            srcset_choice = _parse_srcset(img.get("srcset"))
            src = (
                srcset_choice
                or img.get("src")
                or img.get("data-src")
                or img.get("data-original")
                or img.get("data-lazy-src")
                or img.get("data-highres")
            )
            cleaned = _clean_url(src)
            if not cleaned or cleaned in seen_urls:
                continue

            alt = img.get("alt", "") or img.get("title", "")
            parent_figure = img.find_parent("figure")
            caption = alt
            if parent_figure:
                figcaption = parent_figure.find("figcaption")
                if figcaption:
                    caption = _clean(figcaption.get_text(strip=True))

            w = img.get("width")
            h = img.get("height")
            if _is_junk_image(cleaned, caption, w, h):
                continue

            seen_urls.add(cleaned)
            if not media["lead_image"]:
                media["lead_image"] = cleaned
            media["images"].append({
                "url": cleaned,
                "type": "inline_img",
                "caption": caption[:200] if caption else "",
                "width": w,
                "height": h,
            })

    # ----------------------------------------------------
    # 4. Embedded Video Players (<video> and <iframe>)
    # ----------------------------------------------------
    if content_container:
        for vid in content_container.find_all("video"):
            v_src = vid.get("src")
            if not v_src:
                src_tag = vid.find("source")
                if src_tag:
                    v_src = src_tag.get("src")
            cleaned = _clean_url(v_src)
            if cleaned and cleaned not in seen_urls:
                seen_urls.add(cleaned)
                media["videos"].append({
                    "url": cleaned,
                    "type": "html5_video",
                    "caption": "",
                })
            poster = _clean_url(vid.get("poster"))
            if poster and poster not in seen_urls and not _is_junk_image(poster):
                seen_urls.add(poster)
                media["images"].append({
                    "url": poster,
                    "type": "video_poster",
                    "caption": "Video Poster Frame",
                })

        for iframe in content_container.find_all("iframe"):
            i_src = iframe.get("src") or ""
            cleaned = _clean_url(i_src)
            if cleaned and any(vhost in cleaned.lower() for vhost in ["youtube.com", "youtu.be", "vimeo.com", "dailymotion.com"]):
                if cleaned not in seen_urls:
                    seen_urls.add(cleaned)
                    media["videos"].append({
                        "url": cleaned,
                        "type": "embedded_player",
                        "caption": iframe.get("title", ""),
                    })

    return media


def _fetch_article_content(url, max_chars=6000):
    """
    Best-effort extraction of readable article text AND real incident media.

    Google News RSS returns wrapper URLs.
    Decode them first to obtain the real publisher URL.

    Returns dict:
    {
        "text": str,
        "media": {
            "lead_image": str or None,
            "images": list of image dicts,
            "videos": list of video dicts,
        },
        "resolved_url": str,
    }
    """
    result = {
        "text": "",
        "media": {
            "lead_image": None,
            "images": [],
            "videos": [],
        },
        "resolved_url": url,
    }

    if not url:
        return result

    try:
        article_url = url

        # ----------------------------------------------------
        # Decode Google News wrapper
        # ----------------------------------------------------
        if "news.google.com" in url:
            decoded = gnewsdecoder(
                url,
                interval=1,
            )
            if (
                isinstance(decoded, dict)
                and decoded.get("status")
                and decoded.get("decoded_url")
            ):
                article_url = decoded["decoded_url"]
                print(
                    "Decoded article URL:",
                    article_url,
                )
            else:
                print(
                    "Google News URL could not be decoded."
                )
                return result

        result["resolved_url"] = article_url

        # ----------------------------------------------------
        # Fetch publisher article HTML
        # ----------------------------------------------------
        response = requests.get(
            article_url,
            timeout=6,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/151.0 Safari/537.36"
                )
            },
            allow_redirects=True,
        )
        response.raise_for_status()

        content_type = (
            response.headers.get(
                "content-type",
                "",
            ).lower()
        )

        if "html" not in content_type:
            return result

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        # ----------------------------------------------------
        # EXTRACT REAL INCIDENT MEDIA FIRST
        # (while DOM tree, scripts, and figure tags are intact)
        # ----------------------------------------------------
        try:
            result["media"] = _extract_article_media(soup, article_url)
            num_imgs = len(result["media"].get("images", []))
            num_vids = len(result["media"].get("videos", []))
            if num_imgs > 0 or num_vids > 0:
                print(
                    f"📷 Extracted {num_imgs} images and {num_vids} videos from {article_url}"
                )
        except Exception as media_err:
            print(f"Media extraction warning: {media_err}")

        # ----------------------------------------------------
        # METHOD 1: JSON-LD articleBody
        # ----------------------------------------------------
        for script in soup.find_all(
            "script",
            type="application/ld+json",
        ):
            raw_json = script.string or script.get_text(
                strip=True
            )
            if not raw_json:
                continue

            try:
                data = json.loads(raw_json)
                objects = (
                    data
                    if isinstance(data, list)
                    else [data]
                )
                for obj in objects:
                    if not isinstance(obj, dict):
                        continue

                    article_body = obj.get("articleBody")
                    if isinstance(article_body, str):
                        article_body = _clean(article_body)
                        if len(article_body) >= 100:
                            print(
                                "Article text extracted "
                                "from JSON-LD articleBody."
                            )
                            result["text"] = article_body[
                                :max_chars
                            ].strip()
                            return result
            except Exception:
                continue

        # ----------------------------------------------------
        # METHOD 2: Normal paragraph extraction
        # ----------------------------------------------------
        for tag in soup([
            "script",
            "style",
            "noscript",
            "nav",
            "header",
            "footer",
            "aside",
            "form",
        ]):
            tag.decompose()

        paragraphs = []
        for paragraph in soup.find_all("p"):
            value = _clean(
                paragraph.get_text(
                    " ",
                    strip=True,
                )
            )
            if len(value) >= 40:
                paragraphs.append(value)

        if paragraphs:
            unique = []
            seen = set()
            for paragraph in paragraphs:
                key = paragraph.lower()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(paragraph)

            article_text = " ".join(unique)
            if article_text.strip():
                print(
                    "Article text extracted "
                    "from paragraphs."
                )
                result["text"] = article_text[
                    :max_chars
                ].strip()
                return result

        print(
            "No readable article text found."
        )
        return result

    except Exception as error:
        print(
            f"Article fetch failed: {error}"
        )
        return result


def _fetch_article_text(url, max_chars=6000):
    """
    Best-effort extraction of readable article text.
    Maintained for backward compatibility.
    """
    content = _fetch_article_content(url, max_chars=max_chars)
    return content.get("text", "")

def _score_news_article(topic, title, snippet, article_text, published_at):
    """
    Score a news article for topic relevance and freshness.

    Higher score = better candidate.
    """

    topic_words = {
        word.lower()
        for word in re.findall(r"[A-Za-z0-9]+", topic)
        if len(word) >= 3
        and word.lower() not in {
            "latest",
            "news",
            "today",
            "technology",
            "tech",
            "recent",
            "breaking",
            "current",
            "newest",
            "topic",
            "your",
            "video",
            "create",
            "make",
            "about",
            "please",
        }
    }

    combined = " ".join(
        [
            title or "",
            snippet or "",
            article_text or "",
        ]
    ).lower()

    score = 0

    # Strong relevance for explicit topic words.
    for word in topic_words:
        if word in combined:
            score += 5

    # Location-specific relevance.
    location_terms = {
        "vijayawada": [
            "vijayawada",
            "vijayawada:",
            "vijayawada,",
        ],
        "andhra pradesh": [
            "andhra pradesh",
            "amaravati",
            "visakhapatnam",
            "guntur",
        ],
    }

    topic_lower = topic.lower()

    for location, terms in location_terms.items():
        if location in topic_lower:
            for term in terms:
                if term in combined:
                    score += 8

    # Technology relevance.
    technology_terms = [
        "technology",
        "artificial intelligence",
        "ai",
        "data centre",
        "data center",
        "digital",
        "engineering",
        "automation",
        "software",
        "semiconductor",
        "robotics",
        "quantum",
        "electronics",
        "innovation",
        "machine learning",
    ]

    for term in technology_terms:
        if term in combined:
            score += 2

    # Prefer articles with actual article text.
    if len(article_text or "") >= 500:
        score += 10
    elif len(article_text or "") >= 100:
        score += 5

    # Freshness bonus.
    try:
        published = datetime.strptime(
            published_at,
            "%a, %d %b %Y %H:%M:%S %Z",
        ).replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - published

        if age <= timedelta(days=1):
            score += 30
        elif age <= timedelta(days=3):
            score += 20
        elif age <= timedelta(days=7):
            score += 10
        elif age <= timedelta(days=30):
            score += 3
        else:
            score -= 10

    except Exception:
        # Do not reject a source just because its date format
        # could not be parsed.
        pass

    return score


def verify_news_topic(topic, limit=5):
    """
    Gather source-backed context from Google News RSS.

    Candidates are scored by:
    - topic relevance
    - location relevance
    - technology relevance
    - article-text availability
    - freshness

    This is a grounding step, not a publication gate.
    """

    topic = _clean(topic)

    if not topic:
        return {
            "status": "UNVERIFIED",
            "topic": "",
            "articles": [],
            "summary": "No topic was provided.",
        }

    url = RSS_URL.format(
        query=quote_plus(topic)
    )

    try:
        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "AutoTube-AI/1.0"
            },
        )

        response.raise_for_status()

        root = ET.fromstring(
            response.content
        )

    except Exception as error:
        return {
            "status": "UNVERIFIED",
            "topic": topic,
            "articles": [],
            "summary": (
                f"News source lookup failed: {error}"
            ),
        }

    candidates = []
    seen = set()

    # --------------------------------------------------------
    # COLLECT CANDIDATES
    # --------------------------------------------------------

    for item in root.findall(".//item"):

        title = _clean(
            item.findtext("title") or ""
        )

        link = _clean(
            item.findtext("link") or ""
        )

        published_at = _clean(
            item.findtext("pubDate") or ""
        )

        snippet = _clean(
            item.findtext("description") or ""
        )

        source_element = item.find(
            "source"
        )

        source = _clean(
            source_element.text
            if source_element is not None
            else ""
        )

        key = title.lower()

        if not title or key in seen:
            continue

        seen.add(key)

        # Do not fetch every article yet.
        # Article text will be fetched only for the
        # highest-ranked candidates after initial scoring.
        article_text = ""

        score = _score_news_article(
            topic=topic,
            title=title,
            snippet=snippet,
            article_text=article_text,
            published_at=published_at,
        )

        candidates.append(
            {
                "headline": title,
                "source": source or "Google News result",
                "published_at": published_at,
                "url": link,
                "snippet": snippet,
                "article_text": article_text,
                "_score": score,
            }
        )

    # --------------------------------------------------------
    # FRESHNESS FILTER FOR LATEST / RECENT NEWS
    # --------------------------------------------------------

    latest_requested = any(
        phrase in topic.lower()
        for phrase in (
            "latest",
            "recent",
            "today",
            "breaking",
            "current",
            "newest",
        )
    )

    if latest_requested:

        now = datetime.now(timezone.utc)

        fresh_candidates = []

        for article in candidates:

            published_at = article.get(
                "published_at",
                "",
            )

            try:

                published = datetime.strptime(
                    published_at,
                    "%a, %d %b %Y %H:%M:%S %Z",
                ).replace(
                    tzinfo=timezone.utc
                )

                age = now - published

                # Latest news = maximum 7 days old.
                if age <= timedelta(days=7):
                    fresh_candidates.append(article)

            except Exception:

                # Unknown dates are not safe for
                # latest-news results.
                continue

        candidates = fresh_candidates

    # --------------------------------------------------------
    # RANK CANDIDATES
    # --------------------------------------------------------

    candidates.sort(
        key=lambda article: article.get("_score", 0),
        reverse=True,
    )

    # --------------------------------------------------------
    # FETCH ARTICLE TEXT ONLY FOR TOP CANDIDATES (PARALLEL)
    # --------------------------------------------------------

    prefetch_count = min(
        max(limit, 4),
        len(candidates),
    )

    from concurrent.futures import ThreadPoolExecutor

    target_articles = candidates[:prefetch_count]

    def _fetch_and_score(article):
        content = _fetch_article_content(
            article.get("url", "")
        )
        article["article_text"] = content.get("text", "")
        article["media"] = content.get("media", {"lead_image": None, "images": [], "videos": []})
        article["resolved_url"] = content.get("resolved_url", article.get("url", ""))
        article["_score"] = _score_news_article(
            topic=topic,
            title=article.get("headline", ""),
            snippet=article.get("snippet", ""),
            article_text=article.get("article_text", ""),
            published_at=article.get("published_at", ""),
        )
        return article

    if target_articles:
        with ThreadPoolExecutor(max_workers=min(4, len(target_articles))) as executor:
            list(executor.map(_fetch_and_score, target_articles))

    candidates.sort(
        key=lambda article: article.get("_score", 0),
        reverse=True,
    )

    # --------------------------------------------------------
    # MINIMUM RELEVANCE GATE
    # --------------------------------------------------------
    #
    # Google News may return articles because a generic word
    # appears in the headline/snippet. That is not sufficient
    # evidence that the article is actually about the topic.
    #
    # Require at least one meaningful topic word to appear in
    # the article content before returning SOURCES_FOUND.
    # --------------------------------------------------------

    verification_words = {
        word.lower()
        for word in re.findall(
            r"[A-Za-z0-9]+",
            topic,
        )
        if len(word) >= 3
        and word.lower() not in {
            "latest",
            "news",
            "today",
            "technology",
            "tech",
            "recent",
            "breaking",
            "current",
            "newest",
            "topic",
            "your",
            "video",
            "create",
            "make",
            "about",
            "please",
        }
    }

    if verification_words:

        relevant_candidates = []

        for article in candidates:

            combined = " ".join(
                [
                    article.get("headline", ""),
                    article.get("snippet", ""),
                    article.get("article_text", ""),
                ]
            ).lower()

            matched_words = {
                word
                for word in verification_words
                if word in combined
            }

            article_score = article.get(
                "_score",
                0,
            )

            # Accept the article when either:
            #
            # 1. A meaningful topic word is directly found
            #    in the article content, OR
            #
            # 2. The article has a strong overall relevance
            #    score from topic/location/technology/freshness.
            #
            # This prevents false positives such as
            # "YOUR_TOPIC", while allowing legitimate articles
            # whose publisher text does not repeat the exact
            # location/topic wording.
            if matched_words or article_score >= 40:

                article["_matched_topic_words"] = len(
                    matched_words
                )

                relevant_candidates.append(
                    article
                )

        candidates = relevant_candidates

    else:
        # A query containing only generic words is not specific
        # enough to safely verify as news.
        candidates = []

    articles = candidates[:limit]

    # Remove internal scoring fields before returning.
    for article in articles:
        article.pop("_score", None)
        article.pop("_matched_topic_words", None)

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    if not articles:
        unverified_res = {
            "status": "UNVERIFIED",
            "topic": topic,
            "articles": [],
            "extracted_media": [],
            "summary": (
                "No fresh matching source-backed "
                "news results were found."
                if latest_requested
                else "No matching source-backed news "
                "results were found."
            ),
        }
        root_dir = Path(__file__).resolve().parent.parent
        try:
            log_file = root_dir / "logs" / "extracted_news_media.json"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump({
                    "topic": topic,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "total_articles": 0,
                    "total_media_items": 0,
                    "extracted_media": [],
                }, f, indent=2)
        except Exception:
            pass
        return unverified_res

    # --------------------------------------------------------
    # COMPILE & AGGREGATE EXTRACTED INCIDENT MEDIA
    # --------------------------------------------------------
    all_media = []
    seen_media_urls = set()
    for art in articles:
        med = art.get("media") or {}
        lead = med.get("lead_image")
        if lead and lead not in seen_media_urls:
            seen_media_urls.add(lead)
            all_media.append({
                "url": lead,
                "type": "lead_image",
                "headline": art.get("headline", ""),
                "source": art.get("source", ""),
                "article_url": art.get("resolved_url") or art.get("url", ""),
            })
        for img in med.get("images", []):
            iurl = img.get("url") if isinstance(img, dict) else img
            if iurl and iurl not in seen_media_urls:
                seen_media_urls.add(iurl)
                all_media.append({
                    "url": iurl,
                    "type": img.get("type", "inline") if isinstance(img, dict) else "inline",
                    "caption": img.get("caption", "") if isinstance(img, dict) else "",
                    "headline": art.get("headline", ""),
                    "source": art.get("source", ""),
                    "article_url": art.get("resolved_url") or art.get("url", ""),
                })
        for vid in med.get("videos", []):
            vurl = vid.get("url") if isinstance(vid, dict) else vid
            if vurl and vurl not in seen_media_urls:
                seen_media_urls.add(vurl)
                all_media.append({
                    "url": vurl,
                    "type": vid.get("type", "video") if isinstance(vid, dict) else "video",
                    "caption": vid.get("caption", "") if isinstance(vid, dict) else "",
                    "headline": art.get("headline", ""),
                    "source": art.get("source", ""),
                    "article_url": art.get("resolved_url") or art.get("url", ""),
                })

    result = {
        "status": "SOURCES_FOUND",
        "topic": topic,
        "articles": articles,
        "extracted_media": all_media,
        "summary": (
            f"Found {len(articles)} ranked "
            f"source-backed news results with {len(all_media)} extracted visuals."
        ),
    }

    # Save to logs/extracted_news_media.json and output/news_verification.json
    root_dir = Path(__file__).resolve().parent.parent
    try:
        log_file = root_dir / "logs" / "extracted_news_media.json"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump({
                "topic": topic,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_articles": len(articles),
                "total_media_items": len(all_media),
                "extracted_media": all_media,
            }, f, indent=2)
        print(f"📁 Extracted media logged to {log_file} ({len(all_media)} visual items)")
    except Exception as log_err:
        print(f"Warning: Failed to save extracted media log: {log_err}")

    try:
        out_file = root_dir / "output" / "news_verification.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    except Exception as out_err:
        print(f"Warning: Failed to save output/news_verification.json: {out_err}")

    return result


# ============================================================
# PRE-PUBLISH CONTENT SAFETY & POLICY MODERATION
# ============================================================

_HEURISTIC_UNSAFE_PATTERNS = {
    "hate_speech": [
        r"\b(racial slur|n-word|white supremacy|hate speech|subhuman)\b",
        r"\b(kill all|death to|wipe out)\s+(jews|muslims|christians|hindus|blacks|whites|asians|immigrants)\b",
        r"\b(genocide|ethnic cleansing)\s+(advocacy|celebration)\b",
    ],
    "violence_harm": [
        r"\b(pipe\s+bomb|bomb\s+tutorial|bomb\s+making|weapons?\s+tutorial)\b",
        r"\b(how to\s+)?(make|build|assemble|craft)\s+(a\s+)?(pipe\s+)?bomb\b",
        r"\b(how to\s+)?(commit\s+)?suicide\b",
        r"\b(assassinate|assassination|school\s+shooting|mass\s+shooting|attack\s+schools?|attack\s+civilians?)\b",
        r"\b(build|manufacture|make)\s+(an\s+)?explosive\b",
        r"\b(manufacture ricin|poisoning water supply|mass casualty)\b",
    ],
    "sexual_content": [
        r"\b(hardcore porn|explicit sex|child exploitation|nonconsensual sexual|csam)\b",
    ],
    "dangerous_content": [
        r"\b(ransomware tutorial|ddos attack tool|how to hack credit cards|carding tutorial|malware payload tutorial)\b",
    ],
}


def _heuristic_safety_check(text, topic=None):
    """
    Fast offline heuristic moderation check using regex safety rules.
    """
    combined = f"{topic or ''} {text or ''}".lower()

    for category, patterns in _HEURISTIC_UNSAFE_PATTERNS.items():
        for pat in patterns:
            match = re.search(pat, combined, flags=re.IGNORECASE)
            if match:
                return {
                    "safe": False,
                    "category": category,
                    "confidence": 0.95,
                    "reason": f"Content violates safety policy ({category}): matched '{match.group(0)}'",
                    "checked_by": "heuristic",
                }

    return {
        "safe": True,
        "category": "none",
        "confidence": 0.85,
        "reason": "Passed heuristic policy and safety check",
        "checked_by": "heuristic",
    }


def verify_content_safety_and_policy(text, topic=None):
    """
    Pre-Publish Safety & Policy Filter.
    Validates script or topic against YouTube Community Guidelines:
    - Toxicity & Hate Speech
    - Harassment & Cyberbullying
    - Graphic Violence & Self-Harm
    - Sexually Explicit Material
    - Dangerous & Illegal Activities

    Uses fast Gemini evaluation with transparent heuristic fallback.
    """
    import os
    import json
    from dotenv import load_dotenv

    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")

    if not text and not topic:
        return {
            "safe": True,
            "category": "none",
            "confidence": 1.0,
            "reason": "Empty content is safe by default",
            "checked_by": "empty_bypass",
        }

    # 1. Try Gemini Content Moderation
    if api_key:
        try:
            from google import genai

            client = genai.Client(api_key=api_key)

            prompt = f"""You are an elite YouTube content moderation and safety officer.
Analyze the following script/news content against YouTube Community Guidelines & Terms of Service:
- Hate Speech & Toxicity (slurs, promoting violence/hatred against protected classes)
- Harassment & Cyberbullying
- Graphic Violence, Terrorist Propaganda, Suicide/Self-Harm
- Sexually Explicit or Inappropriate Content
- Dangerous Content (bomb-making, illegal weapons, malicious hacking, dangerous frauds)

TOPIC: {topic or 'N/A'}
CONTENT:
{(text or '')[:3000]}

Return ONLY a JSON object:
{{
  "safe": true,
  "category": "none",
  "confidence": 0.95,
  "reason": "Short 1-sentence explanation"
}}
If unsafe, set safe: false and category to one of ["hate_speech", "violence", "toxicity", "sexual_content", "dangerous_content"].
"""
            models_to_try = [
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-1.5-flash",
                "gemini-2.0-flash-lite",
                "gemini-flash-lite-latest",
            ]

            for m in models_to_try:
                try:
                    resp = client.models.generate_content(
                        model=m,
                        contents=prompt,
                    )
                    raw = getattr(resp, "text", "")
                    if raw:
                        clean = raw.strip()
                        if "```json" in clean:
                            clean = clean.split("```json")[1].split("```")[0].strip()
                        elif "```" in clean:
                            clean = clean.split("```")[1].split("```")[0].strip()

                        data = json.loads(clean)
                        return {
                            "safe": bool(data.get("safe", True)),
                            "category": str(data.get("category", "none")),
                            "confidence": float(data.get("confidence", 0.9)),
                            "reason": str(data.get("reason", "Verified by Gemini AI moderation")),
                            "checked_by": "gemini",
                        }
                except Exception:
                    continue

        except Exception as exc:
            print(f"⚠️ Gemini moderation check exception: {exc}")

    # 2. Heuristic Moderation Fallback
    return _heuristic_safety_check(text, topic=topic)


# ============================================================
# VISUAL ASSET VALIDATOR & WATERMARK FILTER
# ============================================================

def validate_visual_assets(assets_dir=None, fallback_dir=None):
    """
    Validates all visual image assets in the assets directory:
    - Tests for file corruption (zero-byte or invalid image headers).
    - Checks minimum resolution (>= 200x200).
    - Checks for stock watermark signatures or overlay anomalies.
    - Automatically drops and replaces corrupt/bad images with clean
      images from assets/fallback/.
    """
    import shutil
    from pathlib import Path
    from PIL import Image

    root = Path(__file__).resolve().parent.parent
    a_dir = Path(assets_dir) if assets_dir else (root / "assets")
    f_dir = Path(fallback_dir) if fallback_dir else (root / "assets" / "fallback")

    if not a_dir.exists():
        return {
            "valid": False,
            "total_inspected": 0,
            "corrupt_count": 0,
            "watermarked_count": 0,
            "replaced": [],
            "details": {},
        }

    # Discover fallback candidates
    fallbacks = []
    if f_dir.exists():
        fallbacks = sorted([
            f for f in f_dir.iterdir()
            if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and f.stat().st_size > 1024
        ])

    image_files = sorted([
        f for f in a_dir.iterdir()
        if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        and not f.name.startswith("contact_sheet")
    ])

    total_inspected = len(image_files)
    corrupt_count = 0
    watermarked_count = 0
    replaced = []
    details = {}
    fallback_idx = 0

    stock_watermark_keywords = [
        "watermark",
        "shutterstock",
        "gettyimages",
        "istock",
        "alamy",
        "dreamstime",
        "depositphotos",
        "123rf",
    ]

    for img_path in image_files:
        filename = img_path.name
        is_corrupt = False
        is_watermarked = False
        reason = "Clean"

        # Check 1: File size
        if img_path.stat().st_size < 1024:
            is_corrupt = True
            reason = "File size below 1KB (empty or truncated)"

        # Check 2: Header integrity & decodability
        if not is_corrupt:
            try:
                with Image.open(img_path) as img:
                    img.verify()
                # Reopen to check dimensions and color
                with Image.open(img_path) as img:
                    w, h = img.size
                    if w < 200 or h < 200:
                        is_corrupt = True
                        reason = f"Resolution too low ({w}x{h})"

                    # Check 3: Watermark keywords in EXIF / Metadata
                    info_str = str(getattr(img, "info", {})).lower()
                    if any(kw in info_str for kw in stock_watermark_keywords):
                        is_watermarked = True
                        reason = "Stock agency watermark detected in image metadata"

            except Exception as err:
                is_corrupt = True
                reason = f"Image decode failure: {err}"

        # Check 4: Watermark keywords in filename
        if not is_corrupt and not is_watermarked:
            if any(kw in filename.lower() for kw in stock_watermark_keywords):
                is_watermarked = True
                reason = "Watermark keyword found in filename"

        # Replacement action if defective
        if is_corrupt or is_watermarked:
            if is_corrupt:
                corrupt_count += 1
            if is_watermarked:
                watermarked_count += 1

            if fallbacks:
                clean_fb = fallbacks[fallback_idx % len(fallbacks)]
                fallback_idx += 1
                try:
                    shutil.copy2(clean_fb, img_path)
                    replaced.append(filename)
                    print(f"🛡️ [Asset Safety] Replaced defective {filename} ({reason}) with fallback {clean_fb.name}")
                    reason += f" -> replaced with {clean_fb.name}"
                except Exception as cp_err:
                    print(f"⚠️ Failed to copy fallback over {filename}: {cp_err}")

        details[filename] = {
            "status": "REPLACED" if filename in replaced else ("DEFECTIVE" if (is_corrupt or is_watermarked) else "PASS"),
            "reason": reason,
        }

    return {
        "valid": len(replaced) == 0 and corrupt_count == 0 and watermarked_count == 0,
        "total_inspected": total_inspected,
        "corrupt_count": corrupt_count,
        "watermarked_count": watermarked_count,
        "replaced": replaced,
        "details": details,
    }



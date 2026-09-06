import random
import re
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
from agents.news_verifier import verify_news_topic


NEWS_QUERIES = {
    "General News": "latest news",
    "Politics": "latest politics news",
    "Technology": "latest technology news",
    "Business": "latest business news",
    "Movies / Entertainment": "latest movies entertainment news",
    "Sports": "latest sports news",
    "World News": "latest world news",
    "India News": "latest India news",
    "Auto": "latest automobile auto news",
    "Gadgets": "latest gadgets news",
    "Science": "latest science news",
    "Legal": "latest legal news",
    "Finance": "latest finance news",
    "Education": "latest education news",
    "Health": "latest health news",
    "Weather": "latest weather news",
    "Local News": "latest local news",
    "Trending": "latest trending news",
}


def verify_trend_candidates(ranked_clusters, max_candidates=5):
    """
    Verify top V3.3 trend candidates using independent sources.

    Uses event identity signals:
    - named entities / proper nouns
    - distinctive numbers
    - distinctive multi-word phrases
    - event/action terms

    Generic location/topic words are not sufficient for verification.
    """

    print()
    print("VERIFYING TOP TREND CANDIDATES")
    print("-" * 100)

    generic_words = {
        "the", "a", "an", "and", "or", "to", "of", "in", "on",
        "for", "at", "with", "from", "by", "after", "before",
        "latest", "news", "update", "india", "today", "new",
        "news", "technology", "tech", "local", "state",
        "andhra", "pradesh", "vijayawada", "airport",
        "city", "minister", "official", "officials",
        "says", "said", "gets", "get", "has", "have",
        "will", "plans", "plan", "review", "reviews",
        "progress", "launch", "launches", "launched",
        "announces", "announced",
    }

    event_words = {
        "launch", "launched", "launches",
        "open", "opened", "opens",
        "start", "started", "starts",
        "approve", "approved", "approves",
        "sign", "signed", "signs",
        "order", "orders", "ordered",
        "inaugurate", "inaugurated", "inaugurates",
        "appoint", "appointed", "appoints",
        "acquire", "acquired", "acquires",
        "invest", "invested", "investment",
        "announce", "announced", "announces",
        "flight", "flights",
        "morning", "terminal", "tower",
        "revenue", "crore", "crores",
        "percent", "billion", "million",
    }

    def normalize(value):
        value = value.lower()
        value = re.sub(r"[^a-z0-9\s]", " ", value)
        value = re.sub(r"\s+", " ", value)
        return value.strip()

    def tokens(value):
        return normalize(value).split()

    def meaningful_words(value):
        return {
            word
            for word in tokens(value)
            if len(word) >= 4
            and word not in generic_words
        }

    def distinctive_words(value):
        return {
            word
            for word in meaningful_words(value)
            if word not in event_words
        }

    def numbers(value):
        return set(
            re.findall(
                r"\b\d+(?:\.\d+)?\b",
                value.lower(),
            )
        )

    def phrases(value):
        words = tokens(value)

        words = [
            word
            for word in words
            if len(word) >= 4
            and word not in generic_words
        ]

        result = set()

        for i in range(len(words) - 1):
            result.add(
                f"{words[i]} {words[i + 1]}"
            )

        for i in range(len(words) - 2):
            result.add(
                f"{words[i]} {words[i + 1]} {words[i + 2]}"
            )

        return result

    def event_match(candidate, article):
        article_text = " ".join(
            [
                article.get("headline", ""),
                article.get("snippet", ""),
                article.get("article_text", ""),
            ]
        )

        candidate_words = meaningful_words(candidate)
        candidate_distinctive = distinctive_words(candidate)
        article_words = meaningful_words(article_text)
        article_distinctive = distinctive_words(article_text)

        if not candidate_words or not article_words:
            return False, 0, 0, 0

        word_overlap = (
            candidate_words & article_words
        )

        distinctive_overlap = (
            candidate_distinctive
            & article_distinctive
        )

        candidate_numbers = numbers(candidate)
        article_numbers = numbers(article_text)
        number_overlap = (
            candidate_numbers
            & article_numbers
        )

        candidate_phrases = phrases(candidate)
        article_normalized = normalize(article_text)

        phrase_matches = {
            phrase
            for phrase in candidate_phrases
            if phrase in article_normalized
        }

        candidate_event_words = (
            set(tokens(candidate))
            & event_words
        )

        article_event_words = (
            set(tokens(article_text))
            & event_words
        )

        event_overlap = (
            candidate_event_words
            & article_event_words
        )

        # Strong identity:
        # distinctive entities are the most important signal.
        strong_identity = (
            len(distinctive_overlap) >= 2
        )

        # One highly distinctive entity + a matching event
        # can also identify a story such as:
        # Fly91 + Tirupati + flights.
        entity_event_identity = (
            len(distinctive_overlap) >= 1
            and len(event_overlap) >= 1
            and (
                len(word_overlap) >= 3
                or len(phrase_matches) >= 1
            )
        )

        # Exact numbers are strong evidence for the same event.
        numeric_identity = (
            len(number_overlap) >= 1
            and len(distinctive_overlap) >= 1
        )

        # Multiple matching phrases can confirm the event
        # when the phrases contain meaningful terms.
        phrase_identity = (
            len(phrase_matches) >= 2
            and len(distinctive_overlap) >= 1
        )

        same_event = (
            strong_identity
            or entity_event_identity
            or numeric_identity
            or phrase_identity
        )

        return (
            same_event,
            len(word_overlap),
            len(distinctive_overlap),
            len(phrase_matches),
        )

    for index, cluster in enumerate(
        ranked_clusters[:max_candidates],
        start=1,
    ):
        original_candidate = cluster.get(
            "headline",
            "",
        ).strip()

        if not original_candidate:
            continue

        candidate = re.sub(
            r"\s+[-|–—]\s+[^-|–—]+$",
            "",
            original_candidate,
        ).strip()

        candidate_terms = meaningful_words(candidate)

        if len(candidate_terms) < 2:
            continue

        # Query with distinctive terms first.
        query_terms = list(
            distinctive_words(candidate)
        )

        if not query_terms:
            query_terms = list(
                candidate_terms
            )

        query_words = query_terms[:8]

        verification_query = (
            "latest "
            + " ".join(query_words)
        ).strip()

        print()
        print(
            f"VERIFY {index}/{max_candidates}: "
            f"{candidate}"
        )

        print(
            "Query:",
            verification_query,
        )

        try:
            result = verify_news_topic(
                verification_query,
                limit=10,
            )
        except Exception as error:
            print(
                "Verifier error:",
                str(error),
            )
            continue

        if result.get("status") != "SOURCES_FOUND":
            print(
                "❌ No verified sources found"
            )
            continue

        articles = result.get(
            "articles",
            [],
        )

        matching_articles = []

        for article in articles:
            (
                same_event,
                word_count,
                distinctive_count,
                phrase_count,
            ) = event_match(
                candidate,
                article,
            )

            print(
                f"   • "
                f"{article.get('source', 'Unknown')} "
                f"| words: {word_count} "
                f"| unique: {distinctive_count} "
                f"| phrases: {phrase_count} "
                f"| same event: "
                f"{'YES' if same_event else 'NO'}"
            )

            if same_event:
                matching_articles.append(
                    article
                )

        unique_sources = {
            article.get(
                "source",
                "",
            ).strip().lower()
            for article in matching_articles
            if article.get(
                "source",
                "",
            ).strip()
        }

        source_count = len(
            unique_sources
        )

        print()
        print(
            f"Same-event articles: "
            f"{len(matching_articles)} "
            f"| Independent sources: "
            f"{source_count}"
        )

        if source_count >= 2:
            print(
                "🏆 MULTI-SOURCE SAME-EVENT "
                "VERIFICATION PASSED"
            )

            return (
                cluster,
                source_count,
            )

        print(
            "⚠️ Same story not confirmed by "
            "2 independent publishers."
        )

    print()
    print(
        "⚠️ No candidate reached "
        "2-source same-event verification."
    )

    print(
        "Keeping original V3.3 winner."
    )

    return None, 0

def get_news(category="General News", location="Vijayawada"):

    query = NEWS_QUERIES.get(
        category,
        "latest news",
    )

    if category == "Local News":
        query = f"latest news {location}"
    elif location:
        query = f"{query} {location}"

    url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=en-IN&gl=IN&ceid=IN:en"
    )

    print("=" * 60)
    print("AUTOTUBE AI NEWS SEARCH")
    print("=" * 60)
    print("Category:", category)
    print("Location:", location)
    print("Query:", query)

    try:

        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/151.0 Safari/537.36"
                )
            },
        )

        response.raise_for_status()

        # ----------------------------------------------------
        # Parse Google News RSS using Python's built-in XML
        # parser. No lxml / bs4 XML parser required.
        # ----------------------------------------------------

        root = ET.fromstring(
            response.content
        )

        news_items = []

        for item in root.findall(
            ".//item"
        ):

            title_element = item.find(
                "title"
            )

            if title_element is None:
                continue

            title = (
                title_element.text or ""
            ).strip()

            if title:
                news_items.append(
                    title
                )

        # ----------------------------------------------------
        # No results
        # ----------------------------------------------------

        if not news_items:

            print(
                "No news found from Google News."
            )

            print("=" * 60)

            return (
                f"{category} latest news"
            )

        # ----------------------------------------------------
        # Remove duplicate headlines
        # ----------------------------------------------------

        unique_news = []

        seen = set()

        for headline in news_items:

            key = headline.lower().strip()

            if key in seen:
                continue

            seen.add(key)

            unique_news.append(
                headline
            )

        # ----------------------------------------------------
        # ----------------------------------------------------
        # V3.1 TREND ENGINE
        # ----------------------------------------------------
        #
        # Improvements over V3:
        #
        #   1. Real publisher/source extraction
        #   2. Real publication time extraction
        #   3. Freshness scoring
        #   4. Multi-source coverage
        #   5. Story repetition coverage
        #   6. Better story clustering
        #   7. Trend keywords
        #   8. YouTube potential
        #
        # This is still a heuristic trend estimator.
        # It does NOT guarantee virality.
        # ----------------------------------------------------

        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime

        # ----------------------------------------------------
        # Parse RSS items into structured news records
        # ----------------------------------------------------

        news_records = []

        try:

            root = ET.fromstring(response.text)

            for item in root.findall(".//item"):

                title_element = item.find("title")
                source_element = item.find("source")
                pubdate_element = item.find("pubDate")
                link_element = item.find("link")

                if title_element is None:
                    continue

                title = (
                    title_element.text or ""
                ).strip()

                if not title:
                    continue

                source = ""

                if source_element is not None:
                    source = (
                        source_element.text or ""
                    ).strip()

                published = ""

                if pubdate_element is not None:
                    published = (
                        pubdate_element.text or ""
                    ).strip()

                link = ""

                if link_element is not None:
                    link = (
                        link_element.text or ""
                    ).strip()

                news_records.append(
                    {
                        "title": title,
                        "source": source,
                        "published": published,
                        "link": link,
                    }
                )

        except Exception as e:

            print(
                "⚠️ RSS structured parsing failed:",
                e,
            )

            news_records = []

        # ----------------------------------------------------
        # Fallback if structured parsing failed
        # ----------------------------------------------------

        if not news_records:

            news_records = [
                {
                    "title": title,
                    "source": "",
                    "published": "",
                    "link": "",
                }
                for title in unique_news
            ]

        # ----------------------------------------------------
        # Clean publisher suffix from headline
        # ----------------------------------------------------

        def clean_topic(headline):

            topic = (
                headline or ""
            ).strip()

            topic = re.sub(
                r"\s+[-|–—]\s+[^-|–—]+$",
                "",
                topic,
            )

            topic = re.sub(
                r"\s+\|\s+[^|]+$",
                "",
                topic,
            )

            return topic.strip()

        # ----------------------------------------------------
        # Normalize story for clustering
        # ----------------------------------------------------

        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "of",
            "to",
            "in",
            "on",
            "for",
            "with",
            "from",
            "is",
            "are",
            "has",
            "have",
            "this",
            "that",
            "india",
            "latest",
            "news",
            "today",
        }

        def normalize_story(text):

            text = clean_topic(
                text
            ).lower()

            text = re.sub(
                r"[^a-z0-9 ]+",
                " ",
                text,
            )

            words = [
                word
                for word in text.split()
                if word not in stop_words
                and len(word) > 2
            ]

            return set(words)

        # ----------------------------------------------------
        # Parse publication date
        # ----------------------------------------------------

        def parse_pubdate(value):

            if not value:
                return None

            try:

                dt = parsedate_to_datetime(
                    value
                )

                if dt.tzinfo is None:

                    dt = dt.replace(
                        tzinfo=timezone.utc
                    )

                return dt.astimezone(
                    timezone.utc
                )

            except Exception:

                return None

        now_utc = datetime.now(
            timezone.utc
        )

        # ----------------------------------------------------
        # Freshness score
        # ----------------------------------------------------

        def freshness_score(
            published
        ):

            dt = parse_pubdate(
                published
            )

            if dt is None:
                return -20, "unknown"

            age_hours = (
                now_utc - dt
            ).total_seconds() / 3600

            if age_hours < 0:
                age_hours = 0

            # ------------------------------------------------
            # Freshness priority
            # ------------------------------------------------
            # Very recent news gets a strong bonus.
            # Old stories receive increasingly large penalties.
            # Anything older than 7 days is effectively rejected.
            # ------------------------------------------------

            if age_hours <= 1:
                return 35, f"{age_hours:.1f}h"

            if age_hours <= 3:
                return 32, f"{age_hours:.1f}h"

            if age_hours <= 6:
                return 28, f"{age_hours:.1f}h"

            if age_hours <= 12:
                return 24, f"{age_hours:.1f}h"

            if age_hours <= 24:
                return 20, f"{age_hours:.1f}h"

            if age_hours <= 48:
                return 12, f"{age_hours / 24:.1f}d"

            if age_hours <= 72:
                return 5, f"{age_hours / 24:.1f}d"

            if age_hours <= 168:
                return -15, f"{age_hours / 24:.1f}d"

            if age_hours <= 336:
                return -35, f"{age_hours / 24:.1f}d"

            return -55, f"{age_hours / 24:.1f}d"

        # ----------------------------------------------------
        # Trend keywords
        # ----------------------------------------------------

        trend_keywords = {

            "breaking": 12,
            "latest": 5,
            "major": 7,

            "launch": 10,
            "launched": 10,

            "ai": 12,
            "artificial intelligence": 12,

            "google": 8,
            "openai": 10,
            "chatgpt": 10,

            "iphone": 9,
            "android": 7,

            "tesla": 8,
            "elon musk": 8,

            "india": 6,

            "viral": 12,
            "trending": 12,

            "explained": 8,

            "crisis": 9,
            "war": 8,
            "election": 8,

            "earthquake": 10,
            "flood": 9,
            "storm": 8,

            "scandal": 8,
            "investigation": 7,

            "stock": 6,
            "market": 5,

            "price": 5,
            "record": 7,
            "first": 7,

            "million": 5,
            "billion": 6,
        }

        # ----------------------------------------------------
        # YouTube potential keywords
        # ----------------------------------------------------

        youtube_keywords = {

            "why": 8,
            "how": 8,
            "what": 7,

            "explained": 10,
            "impact": 7,
            "future": 7,

            "new": 4,
            "launch": 6,

            "price": 5,
            "comparison": 7,

            "update": 5,
            "worth": 6,

            "should you": 7,
        }

        generic_phrases = (
            "latest news",
            "daily update",
            "today news",
            "news update",
        )

        # ----------------------------------------------------
        # Calculate headline score
        # ----------------------------------------------------

        def calculate_base_score(
            headline
        ):

            text = (
                headline or ""
            ).lower()

            score = 0

            for keyword, points in (
                trend_keywords.items()
            ):

                if keyword in text:
                    score += points

            for keyword, points in (
                youtube_keywords.items()
            ):

                if keyword in text:
                    score += points

            if "?" in headline:
                score += 8

            if re.search(
                r"\d",
                headline,
            ):
                score += 4

            word_count = len(
                headline.split()
            )

            if 7 <= word_count <= 18:
                score += 5

            if any(
                phrase in text
                for phrase in generic_phrases
            ):
                score -= 8

            return score

        # ----------------------------------------------------
        # Deduplicate records
        # ----------------------------------------------------

        unique_records = []
        seen_records = set()

        for record in news_records:

            title = record.get("title", "").strip()
            source = record.get("source", "").strip().lower()

            normalized_title = re.sub(
                r"[^a-z0-9]+",
                " ",
                clean_topic(title).lower(),
            ).strip()

            if not normalized_title:
                continue

            # Keep the same story when it comes from different sources.
            record_key = (
                normalized_title,
                source,
            )

            if record_key in seen_records:
                continue

            seen_records.add(record_key)
            unique_records.append(record)

        # Give the trend engine more candidates.
        unique_records = unique_records[:100]

        # ----------------------------------------------------
        # Story clustering
        # ----------------------------------------------------

        clusters = []

        for record in unique_records:

            title = record.get("title", "")
            words = normalize_story(title)

            if not words:
                continue

            best_cluster = None
            best_similarity = 0

            for cluster in clusters:

                # Compare against every headline already
                # inside the cluster instead of only one
                # representative headline.
                cluster_best_similarity = 0

                for existing_record in cluster["records"]:

                    existing_words = normalize_story(
                        existing_record.get("title", "")
                    )

                    if not existing_words:
                        continue

                    overlap = len(
                        words & existing_words
                    )

                    smaller = min(
                        len(words),
                        len(existing_words),
                    )

                    if smaller == 0:
                        continue

                    similarity = (
                        overlap / smaller
                    )

                    cluster_best_similarity = max(
                        cluster_best_similarity,
                        similarity,
                    )

                # Flexible story matching:
                # 3+ shared meaningful words with 45% similarity
                # OR 2+ shared meaningful words with 65% similarity.
                if (
                    (
                        cluster_best_similarity >= 0.45
                        and cluster_best_similarity > best_similarity
                        and len(words) >= 3
                    )
                    or
                    (
                        cluster_best_similarity >= 0.65
                        and cluster_best_similarity > best_similarity
                    )
                ):
                    best_similarity = cluster_best_similarity
                    best_cluster = cluster

            if best_cluster is None:

                clusters.append(
                    {
                        "topic": title,
                        "records": [record],
                    }
                )

            else:

                best_cluster["records"].append(
                    record
                )

        # ----------------------------------------------------
        # Rank clusters
        # ----------------------------------------------------

        ranked_clusters = []

        for cluster in clusters:

            records = cluster["records"]

            # Pick the strongest headline from the cluster.
            headline = max(
                (
                    record.get("title", "")
                    for record in records
                    if record.get("title", "")
                ),
                key=calculate_base_score,
                default=cluster.get("topic", ""),
            )

            # --------------------------------------------
            # Real source coverage
            # --------------------------------------------

            sources = set()

            for record in records:

                source = (
                    record.get("source")
                    or ""
                ).strip()

                if source:
                    sources.add(
                        source.lower()
                    )

            source_count = len(sources)

            # --------------------------------------------
            # Story coverage
            # --------------------------------------------

            story_count = len(records)

            # --------------------------------------------
            # Base headline score
            # --------------------------------------------

            base_score = calculate_base_score(
                headline
            )

            # --------------------------------------------
            # Find newest publication time
            # --------------------------------------------

            newest_dt = None

            for record in records:

                dt = parse_pubdate(
                    record.get(
                        "published",
                        "",
                    )
                )

                if dt is not None:
                    if (
                        newest_dt is None
                        or dt > newest_dt
                    ):
                        newest_dt = dt

            if newest_dt is not None:

                freshness_points, age_text = (
                    freshness_score(
                        newest_dt.strftime(
                            "%a, %d %b %Y %H:%M:%S +0000"
                        )
                    )
                )

            else:

                freshness_points, age_text = (
                    freshness_score("")
                )

            # --------------------------------------------
            # Source coverage bonus
            # --------------------------------------------

            source_bonus = min(
                source_count * 8,
                32,
            )

            # --------------------------------------------
            # Story repetition bonus
            # --------------------------------------------

            story_bonus = min(
                max(
                    story_count - 1,
                    0,
                ) * 4,
                24,
            )

            # --------------------------------------------
            # Confirmation bonus
            # --------------------------------------------

            confirmation_bonus = 0

            if (
                source_count >= 2
                and freshness_points >= 12
            ):
                confirmation_bonus += 8

            if (
                story_count >= 3
                and freshness_points >= 12
            ):
                confirmation_bonus += 5

            # --------------------------------------------
            # Final score
            # --------------------------------------------

            final_score = (
                base_score
                + source_bonus
                + story_bonus
                + freshness_points
                + confirmation_bonus
            )

            ranked_clusters.append(
                {
                    "headline": headline,
                    "records": records,
                    "source_count": source_count,
                    "story_count": story_count,
                    "base_score": base_score,
                    "freshness_points": freshness_points,
                    "age_text": age_text,
                    "score": final_score,
                }
            )

        ranked_clusters.sort(
            key=lambda item: (
                item["score"],
                item["source_count"],
                item["story_count"],
            ),
            reverse=True,
        )

        if not ranked_clusters:

            return (
                f"{category} latest news"
            )

        # ----------------------------------------------------
        # Selected topic
        # ----------------------------------------------------

        selected_cluster = (
            ranked_clusters[0]
        )

        selected_topic = clean_topic(
            selected_cluster[
                "headline"
            ]
        )

        # ----------------------------------------------------
        # Verify top V3.3 trend candidates
        # ----------------------------------------------------

        verified_cluster, verified_source_count = (
            verify_trend_candidates(
                ranked_clusters,
                max_candidates=5,
            )
        )

        if verified_cluster:
            selected_cluster = verified_cluster

            selected_topic = clean_topic(
                selected_cluster["headline"]
            )

            print()
            print("✅ VERIFIED TREND TOPIC:", selected_topic)
            print(
                "🔎 Verified source count:",
                verified_source_count,
            )
        else:
            print()
            print(
                "⚠️ Verification failed for top candidates."
            )
            print(
                "Keeping V3.3 selected topic:",
                selected_topic,
            )

        # ----------------------------------------------------
        # Console output
        # ----------------------------------------------------

        print()

        print(
            f"Found {len(unique_records)} "
            "unique structured news records."
        )

        print(
            f"Grouped into "
            f"{len(ranked_clusters)} "
            "story clusters."
        )

        print()

        print(
            "TREND POTENTIAL RANKING V3.3"
        )

        print("-" * 100)

        for index, item in enumerate(
            ranked_clusters[:10],
            start=1,
        ):

            topic = clean_topic(
                item["headline"]
            )

            print(
                f"{index:>2}. "
                f"{item['score']:>3} "
                f"| Sources: "
                f"{item['source_count']:<2} "
                f"| Stories: "
                f"{item['story_count']:<2} "
                f"| Fresh: "
                f"{item['age_text']:<7} "
                f"| {topic}"
            )

        print()

        print(
            "🏆 Selected trend topic:",
            selected_topic,
        )

        print(
            "📊 Final trend score:",
            selected_cluster[
                "score"
            ],
        )

        print(
            "📰 Source coverage:",
            selected_cluster[
                "source_count"
            ],
        )

        print(
            "🔗 Story coverage:",
            selected_cluster[
                "story_count"
            ],
        )

        print(
            "⏱ Freshness:",
            selected_cluster[
                "age_text"
            ],
        )

        print("=" * 60)

        return selected_topic

    except ET.ParseError as error:

        print(
            "RSS XML parsing failed:",
            str(error),
        )

        return (
            f"{category} latest news"
        )

    except requests.RequestException as error:

        print(
            "News request failed:",
            str(error),
        )

        return (
            f"{category} latest news"
        )

    except Exception as error:

        print(
            "News search failed:",
            str(error),
        )

        return (
            f"{category} latest news"
        )

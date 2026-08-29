import random
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus


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
        # Select from top headlines
        # ----------------------------------------------------

        candidates = unique_news[
            :min(10, len(unique_news))
        ]

        selected = random.choice(
            candidates
        )

        print()
        print(
            f"Found {len(unique_news)} "
            "news headlines."
        )

        print(
            "Selected:",
            selected,
        )

        print("=" * 60)

        return selected

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

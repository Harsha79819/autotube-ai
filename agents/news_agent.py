import requests
from bs4 import BeautifulSoup
import random


def get_news():

    url = "https://news.google.com/rss"

    try:
        response = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.content, "xml")

        items = soup.find_all("item")

        if not items:
            print("No news found.")
            return "Artificial Intelligence"

        topics = []

        for item in items[:20]:

            title = item.find("title")

            if title:
                topic = title.text.strip()

                if topic not in topics:
                    topics.append(topic)

        topic = random.choice(topics)

        print(f"News Topic: {topic}")

        return topic

    except Exception as e:

        print("News fetch failed:", e)

        return "Artificial Intelligence"
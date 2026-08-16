import os
import re
import time

from dotenv import load_dotenv
from google import genai


# ============================================================
# PROJECT / ENV
# ============================================================

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

ENV_FILE = os.path.join(
    PROJECT_ROOT,
    ".env"
)

load_dotenv(ENV_FILE)

api_key = os.environ.get("GEMINI_API_KEY")

print("ENV FILE:", ENV_FILE)
print(
    "API KEY:",
    "FOUND" if api_key else "MISSING"
)

if not api_key:
    raise ValueError(
        "GEMINI_API_KEY not found in .env"
    )

client = genai.Client(
    api_key=api_key
)


# ============================================================
# MODEL FALLBACK ORDER
# ============================================================

METADATA_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
]


# ============================================================
# PARSE GEMINI RESPONSE
# ============================================================

def parse_metadata(text):

    text = text.strip()

    title = ""
    description = ""
    tags = []

    # TITLE
    if "TITLE:" in text:

        title = (
            text
            .split("TITLE:", 1)[1]
            .split("DESCRIPTION:", 1)[0]
            .strip()
        )

    # DESCRIPTION
    if "DESCRIPTION:" in text:

        description = (
            text
            .split("DESCRIPTION:", 1)[1]
            .split("TAGS:", 1)[0]
            .strip()
        )

    # TAGS
    if "TAGS:" in text:

        tags_text = (
            text
            .split("TAGS:", 1)[1]
            .strip()
        )

        tags_text = (
            tags_text
            .replace("[", "")
            .replace("]", "")
            .replace("'", "")
            .replace('"', "")
        )

        tags = [
            tag.strip()
            for tag in tags_text.split(",")
            if tag.strip()
        ]

    return title, description, tags


# ============================================================
# VALIDATE RESPONSE
# ============================================================

def valid_metadata(title, description, tags):

    if not title:
        return False

    if not description:
        return False

    if not tags:
        return False

    return True


# ============================================================
# LOCAL FALLBACK
# ============================================================

def generate_fallback_metadata(topic, script):

    # Remove Reuters suffix
    clean_topic = re.sub(
        r"\s*-\s*Reuters\s*$",
        "",
        topic,
        flags=re.IGNORECASE
    ).strip()

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = clean_topic

    if len(title) > 95:

        title = title[:92].rstrip()

        if " " in title:
            title = title.rsplit(" ", 1)[0]

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    description = (
        f"{clean_topic}.\n\n"
        f"This video covers the latest developments "
        f"related to this story, including the key facts "
        f"and important context surrounding the event.\n\n"
        f"Watch the full video for the latest update "
        f"and important details."
    )

    # --------------------------------------------------------
    # TAGS
    # --------------------------------------------------------

    words = re.findall(
        r"[A-Za-z0-9]+",
        clean_topic
    )

    tags = []

    for word in words:

        if len(word) >= 3:

            tag = word.lower()

            if tag not in tags:
                tags.append(tag)

    generic_tags = [
        "breaking news",
        "latest news",
        "world news",
        "international news",
        "news update",
        "India news",
    ]

    for tag in generic_tags:

        if tag not in tags:
            tags.append(tag)

    tags = tags[:15]

    return title, description, tags


# ============================================================
# MAIN FUNCTION
# ============================================================

def generate_metadata(topic, script):

    prompt = f"""
You are a professional YouTube SEO expert.

Create metadata for this news video.

TOPIC:
{topic}

SCRIPT:
{script}

Return ONLY this exact format:

TITLE:
[YouTube title under 100 characters]

DESCRIPTION:
[SEO-friendly description in 2-4 paragraphs]

TAGS:
[tag1, tag2, tag3, tag4, tag5, tag6, tag7, tag8, tag9, tag10]

Rules:
- Be factual.
- Do not invent information.
- Do not exaggerate.
- Do not make unsupported claims.
- Make the title interesting but accurate.
- Keep the title under 100 characters.
- Use important keywords naturally.
- Tags must be directly relevant to the topic.
- Do not include unrelated tags.
- Return ONLY TITLE, DESCRIPTION and TAGS.
"""

    print("Generating YouTube metadata...")

    # ========================================================
    # TRY GEMINI MODELS
    # ========================================================

    for model in METADATA_MODELS:

        try:

            print(
                f"Trying metadata model: {model}"
            )

            response = client.models.generate_content(
                model=model,
                contents=prompt
            )

            text = (
                response.text.strip()
                if response.text
                else ""
            )

            title, description, tags = parse_metadata(
                text
            )

            if valid_metadata(
                title,
                description,
                tags
            ):

                print(
                    f"Metadata generated using {model}"
                )

                print(
                    "Metadata generated successfully!"
                )

                return title, description, tags

            print(
                f"Metadata response from {model} "
                "was incomplete."
            )

        except Exception as e:

            print(
                f"Metadata model failed: {model}"
            )

            print(e)

            # Small delay before trying next model
            time.sleep(2)

    # ========================================================
    # ALL MODELS FAILED
    # ========================================================

    print()
    print(
        "WARNING: All Gemini metadata models failed."
    )

    print(
        "Using local metadata fallback..."
    )

    title, description, tags = generate_fallback_metadata(
        topic,
        script
    )

    print(
        "Fallback metadata generated successfully!"
    )

    return title, description, tags


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    test_topic = (
        "UAE says Iran attacked ADNOC vessel "
        "in Hormuz, urges waterway's reopening - Reuters"
    )

    test_script = """
    This is a test news script for AutoTube AI.
    """

    title, description, tags = generate_metadata(
        test_topic,
        test_script
    )

    print()
    print("=" * 60)

    print("TITLE:")
    print(title)

    print()
    print("DESCRIPTION:")
    print(description)

    print()
    print("TAGS:")
    print(tags)

    print("=" * 60)
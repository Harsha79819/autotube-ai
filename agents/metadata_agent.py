import os
import re
import time
import json

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

def load_env_file(path):
    """Load simple KEY=VALUE entries without requiring python-dotenv."""
    if not os.path.isfile(path):
        return

    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key:
                os.environ.setdefault(key, value)


try:
    from agents.env_loader import get_gemini_api_key
except ImportError:
    from env_loader import get_gemini_api_key

api_key = get_gemini_api_key()

client = genai.Client(api_key=api_key) if api_key else None


def get_client():
    """Lazily load or refresh the Gemini client from environment/secrets."""
    global client
    if client is None:
        key = get_gemini_api_key()
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. "
                "Please add it to Hugging Face Space Secrets, Streamlit Secrets, or your .env file."
            )
        client = genai.Client(api_key=key)
    return client


# ============================================================
# MODEL FALLBACK ORDER
# ============================================================

METADATA_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.6-flash",
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
- TITLE CTR RULE: Titles must make it immediately clear what the viewer will learn or see within 2 seconds. Favor concrete specifics (price, key spec, comparison, benchmark) over vague hype words.
- Be factual.
- Do not invent information.
- Do not exaggerate.
- Do not make unsupported claims.
- Make the title interesting, high-CTR, and accurate.
- Keep the title under 100 characters.
- Use important keywords naturally.
- Tags must be directly relevant to the topic.
- Do not include unrelated tags.
- Return ONLY TITLE, DESCRIPTION and TAGS.
"""

    print("Generating YouTube metadata...")

    metadata_file = os.path.join(
        PROJECT_ROOT,
        "output",
        "metadata.json"
    )

    # --------------------------------------------------------
    # GEMINI ATTEMPTS WITH FALLBACK
    # --------------------------------------------------------

    for model in METADATA_MODELS:
        try:
            print(f"Trying metadata model: {model}")

            active_client = get_client()
            response = active_client.models.generate_content(
                model=model,
                contents=prompt
            )

            text = (
                response.text.strip()
                if getattr(response, "text", "")
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
                metadata = {
                    "title": title,
                    "description": description,
                    "tags": tags
                }

                os.makedirs(
                    os.path.dirname(metadata_file),
                    exist_ok=True
                )

                with open(
                    metadata_file,
                    "w",
                    encoding="utf-8"
                ) as f:
                    json.dump(
                        metadata,
                        f,
                        ensure_ascii=False,
                        indent=2
                    )

                print(
                    f"Metadata generated using {model}"
                )
                print(
                    "Metadata generated successfully!"
                )
                print(
                    f"Metadata saved: {metadata_file}"
                )

                return title, description, tags

            print(
                f"Model {model} metadata response was incomplete."
            )

        except Exception as error:
            print(f"Metadata model {model} failed: {error}")
            continue

    # --------------------------------------------------------
    # LOCAL FALLBACK
    # --------------------------------------------------------

    print(
        "Using local metadata fallback..."
    )

    title, description, tags = generate_fallback_metadata(
        topic,
        script
    )

    metadata = {
        "title": title,
        "description": description,
        "tags": tags
    }

    os.makedirs(
        os.path.dirname(metadata_file),
        exist_ok=True
    )

    with open(
        metadata_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            metadata,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        "✅ Local metadata fallback generated."
    )

    print(
        f"Metadata saved: {metadata_file}"
    )

    return title, description, tags


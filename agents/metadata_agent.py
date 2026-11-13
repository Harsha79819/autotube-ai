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
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
]


def _call_gemini_metadata(client, model, prompt, timeout=12.0):
    """Executes a Gemini generate_content call bounded by a strict thread timeout."""
    import concurrent.futures
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(client.models.generate_content, model=model, contents=prompt)
        return future.result(timeout=timeout)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


# ============================================================
# PARSE GEMINI RESPONSE
# ============================================================

def sanitize_metadata_title(title: str) -> str:
    """Auto-corrects common typos and formatting anomalies in YouTube metadata titles."""
    if not title:
        return ""
    replacements = {
        r"\bdubble\b": "double",
        r"\bDUBBLE\b": "DOUBLE",
        r"\bDubble\b": "Double",
        r"\bstandas\b": "standards",
        r"\bSTANDAS\b": "STANDARDS",
        r"\belemination\b": "elimination",
        r"\bELEMINATION\b": "ELIMINATION",
    }
    cleaned = title
    for pat, rep in replacements.items():
        cleaned = re.sub(pat, rep, cleaned)
    return cleaned.strip()


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
        title = sanitize_metadata_title(title)

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

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", 
    "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", 
    "but", "by", "can", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", 
    "doesn't", "doing", "don't", "down", "during", "each", "few", "for", "from", "further", 
    "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", 
    "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", 
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", 
    "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", 
    "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", 
    "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", 
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", 
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're", "they've", 
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", 
    "we", "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when", 
    "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's", 
    "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", 
    "yours", "yourself", "yourselves", "across", "means", "next", "gen", "also", "just", "will",
    "today", "latest", "first", "every", "everyone"
}

def generate_fallback_metadata(topic, script, aspect_ratio="9:16", channel="Channel 1 (Primary)"):

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

    title = sanitize_metadata_title(clean_topic)

    # Smart title boundary: Never slice blind mid-sentence
    if len(title) > 85:
        seps = [":", "?", "!", " - "]
        cut_done = False
        for sep in seps:
            if sep in title[:85]:
                parts = title.split(sep)
                if len(parts[0].strip()) >= 25:
                    title = parts[0].strip() + (sep.strip() if sep in ("?", "!") else "!")
                    cut_done = True
                    break
        if not cut_done:
            trimmed = title[:80].rstrip()
            if " " in trimmed:
                trimmed = trimmed.rsplit(" ", 1)[0]
            if not trimmed.endswith(("?", "!", ".")):
                trimmed += "!"
            title = trimmed

    is_shorts = (aspect_ratio == "9:16")
    if is_shorts and "#shorts" not in title.lower() and len(title) <= 75:
        title = f"{title} #Shorts"

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
    if is_shorts and "#shorts" not in description.lower():
        description += "\n\n#Shorts #Telugu #Viral"

    # --------------------------------------------------------
    # TAGS
    # --------------------------------------------------------

    words = re.findall(
        r"[A-Za-z0-9]+",
        clean_topic
    )

    tags = []
    if is_shorts:
        tags.append("Shorts")

    for word in words:
        w_clean = word.strip().lower()
        if len(w_clean) >= 3 and w_clean not in STOP_WORDS:
            if w_clean not in tags:
                tags.append(w_clean)

    # Domain-specific high-volume search tags
    topic_lower = clean_topic.lower()
    if any(k in topic_lower for k in ("tech", "phone", "mobile", "ai", "gadget", "processor", "camera", "battery", "apple", "samsung", "android")):
        niche_tags = [
            "Telugu Tech", "Tech News Telugu", "Tech Facts Telugu", "Smartphone Tricks Telugu",
            "Smartphones India", "Viral Tech", "Telugu Shorts"
        ]
    elif any(k in topic_lower for k in ("fact", "mystery", "space", "earth", "ocean", "science", "secret", "alien", "pyramid", "temple", "unknown")):
        niche_tags = [
            "Telugu Facts", "Unknown Facts Telugu", "Amazing Facts", "Mysterious Facts",
            "Science Facts Telugu", "Interesting Facts Telugu", "Telugu Shorts"
        ]
    elif any(k in topic_lower for k in ("bigg boss", "bb10", "eviction", "nominations", "elimination", "nagarjuna", "tollywood")):
        niche_tags = [
            "Bigg Boss Telugu 10", "Bigg Boss 10 Telugu", "Bigg Boss Telugu Review",
            "Bigg Boss Telugu Latest", "Telugu Entertainment", "Telugu Shorts"
        ]
    else:
        niche_tags = [
            "Telugu Facts", "Trending Telugu", "Viral Shorts", "Telugu Shorts"
        ]

    for tag in niche_tags:
        if tag not in tags and len(tags) < 15:
            tags.append(tag)

    tags = tags[:15]

    return title, description, tags


def _attach_youtube_chapters(description: str, is_shorts: bool = False, total_duration: float = 0.0) -> str:
    """If output/chapters.json exists, video is long-form (not Shorts), and has >= 3 chapters, appends YouTube clickable timestamps."""
    if not is_shorts and 0 < total_duration < 90.0:
        is_shorts = True

    # Auto-detect Shorts from existing output files if not explicitly specified
    if not is_shorts:
        try:
            v_path = os.path.join(PROJECT_ROOT, "output", "voice.mp3")
            if os.path.exists(v_path):
                import subprocess
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", v_path],
                    capture_output=True, text=True, timeout=3
                )
                if probe.returncode == 0 and probe.stdout.strip():
                    dur = float(probe.stdout.strip())
                    if total_duration <= 0:
                        total_duration = dur
                    if dur < 90.0:
                        is_shorts = True
        except Exception:
            pass

    if is_shorts:
        return description

    chapters_file = os.path.join(PROJECT_ROOT, "output", "chapters.json")
    if not os.path.exists(chapters_file):
        return description

    try:
        with open(chapters_file, "r", encoding="utf-8") as f:
            chapters = json.load(f)
        if isinstance(chapters, list) and len(chapters) >= 3:
            # Filter out chapters beyond video duration if duration is provided
            if total_duration > 0:
                chapters = [c for c in chapters if c.get("start_time", 0.0) < total_duration]
            if len(chapters) < 3:
                return description
            if "00:00" in description:
                return description
            from agents.chapter_engine import format_youtube_chapters_description
            ts_block = format_youtube_chapters_description(chapters)
            if ts_block:
                return description.rstrip() + ts_block
    except Exception as e:
        print(f"⚠️ YouTube chapter timestamp attachment notice: {e}")
    return description


# ============================================================
# MAIN FUNCTION
# ============================================================

def _post_process_metadata(title: str, description: str, tags: list, topic: str, script: str, aspect_ratio: str = "9:16", channel: str = "Channel 1 (Primary)"):
    is_shorts = (aspect_ratio == "9:16")

    # Clean title
    title = sanitize_metadata_title(title)
    if is_shorts and "#shorts" not in title.lower() and len(title) <= 75:
        title = f"{title} #Shorts"

    # Clean description
    if is_shorts and "#shorts" not in description.lower():
        description = description.rstrip() + "\n\n#Shorts #Telugu #Viral"

    # Bigg Boss Telugu 10 sanitization
    if "bigg boss" in topic.lower() or "bigg boss" in script.lower():
        description = re.sub(r"\bBigg Boss [1-9]\b", "Bigg Boss Telugu 10", description, flags=re.IGNORECASE)
        description = description.replace("Rohit Patnaik", "Rohit Patnam").replace("Shalini Damera", "Shalini Patel")

    # Clean tags: eliminate stop words
    clean_tags = []
    if is_shorts:
        clean_tags.append("Shorts")

    for t in tags:
        t_clean = t.strip()
        if "bigg boss" in topic.lower() or "bigg boss" in script.lower():
            t_clean = re.sub(r"\bBigg Boss [1-9]\b", "Bigg Boss Telugu 10", t_clean, flags=re.IGNORECASE)
            t_clean = t_clean.replace("Rohit Patnaik", "Rohit Patnam").replace("Shalini Damera", "Shalini Patel")
        if t_clean.lower() not in STOP_WORDS and len(t_clean) >= 2 and t_clean not in clean_tags:
            clean_tags.append(t_clean)

    # Attach chapters if long-form
    description = _attach_youtube_chapters(description, is_shorts=is_shorts)

    return title, description, clean_tags[:15]


def generate_metadata(topic, script, aspect_ratio="9:16", channel="Channel 1 (Primary)"):

    prompt = f"""
You are a professional YouTube SEO expert.

Create metadata for this news video.

TOPIC:
{topic}

SCRIPT:
{script}

Return ONLY this exact format:

TITLE:
[YouTube title under 80 characters]

DESCRIPTION:
[SEO-friendly description in 2-4 paragraphs]

TAGS:
[tag1, tag2, tag3, tag4, tag5, tag6, tag7, tag8, tag9, tag10]

Rules:
- HIGH-CTR TITLE FORMULAS (PROVEN TOP PERFORMERS):
  * Burning Question (Demands an immediate click): e.g. "NAGARJUNA ROHIT NI TARGET CHESARA?", "Did Prabhas Just Shatter All Records?!"
  * Bold Provocative Statement (Shock/Curiosity): e.g. "House Lo Unna Vallake Dikku Ledu!", "Bigg Boss 10 Biggest Blunder Exposed!"
  * For Telugu Entertainment/Bigg Boss/Cinema: Craft punchy titles in Telugu/Tanglish or English featuring emotional tension and curiosity.
- BIGG BOSS SEASON 10 GROUND TRUTH: If the topic/script discusses Bigg Boss Telugu, the current show is STRICTLY Bigg Boss Telugu 10 (Season 10). NEVER output tags or descriptions for older seasons like Bigg Boss 7, 8, etc. (NEVER write 'Bigg Boss 7 Telugu').
- OFFICIAL CONTESTANT SPELLINGS: Use exact verified contestant names: Rohit Patnam (NOT Rohit Patnaik), Shalini Patel (NOT Shalini Damera), Aman Masud, Sudheer Reddy (Sudheer Talks), Gundeboina Jhansi (Singer Jhansi), Charan Mahadev.
- Keep the title punchy and strictly under 80 characters so it never truncates on mobile screens.
- Be factual to the script, do not invent fake claims, but make the angle irresistible to click.
- Tags: Include core entities, contestant names, movie titles, and high-volume search tags. No stop words like 'are', 'for', 'how', 'this'.
- Return ONLY TITLE, DESCRIPTION and TAGS.
"""

    print("Generating YouTube metadata...")

    metadata_file = os.path.join(
        PROJECT_ROOT,
        "output",
        "metadata.json"
    )

    t_start = time.time()

    # --------------------------------------------------------
    # GEMINI ATTEMPTS WITH FALLBACK
    # --------------------------------------------------------

    for model in METADATA_MODELS:
        if time.time() - t_start > 25.0:
            print("⏱️ Metadata generation exceeded 25s budget, skipping to fallback...")
            break

        try:
            print(f"Trying metadata model: {model}")

            active_client = get_client()
            response = _call_gemini_metadata(
                active_client,
                model,
                prompt,
                timeout=12.0
            )

            resp_text = getattr(response, "text", None)
            text = resp_text.strip() if resp_text else ""

            title, description, tags = parse_metadata(
                text
            )

            if valid_metadata(
                title,
                description,
                tags
            ):
                title, description, tags = _post_process_metadata(
                    title, description, tags, topic, script, aspect_ratio=aspect_ratio, channel=channel
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

    # Multi-provider cascade fallback (Pollinations / Groq / OpenAI)
    if time.time() - t_start <= 25.0:
        try:
            from providers.llm import generate_text_cascade
            print("Trying multi-provider LLM cascade for metadata...")
            cascade_text = generate_text_cascade(prompt, step_name="metadata", per_provider_timeout=8.0)
            c_title, c_desc, c_tags = parse_metadata(cascade_text)
            if valid_metadata(c_title, c_desc, c_tags):
                c_title, c_desc, c_tags = _post_process_metadata(
                    c_title, c_desc, c_tags, topic, script, aspect_ratio=aspect_ratio, channel=channel
                )
                metadata = {
                    "title": c_title,
                    "description": c_desc,
                    "tags": c_tags
                }
                os.makedirs(os.path.dirname(metadata_file), exist_ok=True)
                with open(metadata_file, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
                print("Metadata generated via multi-provider cascade!")
                return c_title, c_desc, c_tags
        except Exception as c_err:
            print(f"⚠️ Cascade metadata notice: {c_err}")

    # --------------------------------------------------------
    # LOCAL FALLBACK
    # --------------------------------------------------------

    print(
        "Using local metadata fallback..."
    )

    title, description, tags = generate_fallback_metadata(
        topic,
        script,
        aspect_ratio=aspect_ratio,
        channel=channel
    )

    title, description, tags = _post_process_metadata(
        title, description, tags, topic, script, aspect_ratio=aspect_ratio, channel=channel
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


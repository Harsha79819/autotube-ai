import os
import re
import mimetypes
from pathlib import Path
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

from google import genai
from agents.news_verifier import verify_news_topic


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in .env file")

client = genai.Client(api_key=API_KEY)

MODELS = [
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
]


# ============================================================
# CLEAN RESPONSE
# ============================================================

def clean_response(text):
    if not text:
        return ""

    text = text.strip()

    text = re.sub(
        r"^```[a-zA-Z0-9_-]*",
        "",
        text
    )

    text = re.sub(
        r"```$",
        "",
        text
    )

    return text.strip()


# ============================================================
# PARSE + SAVE CONTENT PACKAGE
# ============================================================

def clean_script_narration(text):
    """
    Remove accidental subtitle/SRT formatting from Gemini narration.

    output/script.txt must contain narration only.
    """

    if not text:
        return ""

    lines = text.splitlines()
    cleaned = []

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue

        # Remove WEBVTT header
        if line.upper() == "WEBVTT":
            continue

        # Remove subtitle sequence numbers
        if re.fullmatch(r"\d+", line):
            continue

        # Remove SRT timestamp lines
        if re.fullmatch(
            r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+"
            r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}",
            line,
        ):
            continue

        # Remove MM:SS,mmm --> MM:SS,mmm variants
        if re.fullmatch(
            r"\d{1,2}:\d{2}[,.]\d{3}\s+-->\s+"
            r"\d{1,2}:\d{2}[,.]\d{3}",
            line,
        ):
            continue

        cleaned.append(line)

    return "\n".join(cleaned).strip()


def _parse_and_save_package(text):
    """
    Parse Gemini's structured response and save:

        output/script.txt
        output/visual_plan.txt
        output/section_map.txt

    Returns:
        script string

    Returns None if validation fails.
    """

    script_match = re.search(
        r"SCRIPT:\s*(.*?)(?:\n\s*VISUAL_PLAN:|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    visual_match = re.search(
        r"VISUAL_PLAN:\s*(.*?)(?:\n\s*SECTIONS:|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    sections_match = re.search(
        r"SECTIONS:\s*(.*)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not script_match:
        print("Could not parse SCRIPT.")
        return None

    if not visual_match:
        print("Could not parse VISUAL_PLAN.")
        return None

    if not sections_match:
        print("Could not parse SECTIONS.")
        return None

    script = script_match.group(1).strip()

    # Gemini can occasionally return the SCRIPT section
    # in subtitle/SRT format. Never allow that into
    # script.txt or TTS.
    script = clean_script_narration(script)

    if not script:
        print("SCRIPT became empty after narration cleanup.")
        return None

    # --------------------------------------------------------
    # VISUAL PLAN
    # --------------------------------------------------------

    visual_plan = []

    for line in visual_match.group(1).splitlines():

        line = line.strip()

        line = re.sub(
            r"^\d+[\.\)]\s*",
            "",
            line
        )

        if line:
            visual_plan.append(line)

    # --------------------------------------------------------
    # SECTIONS
    # --------------------------------------------------------

    sections = []

    section_text = sections_match.group(1).strip()

    pattern = re.compile(
        r"SECTION\s+(\d+)\s*\|\s*VISUAL\s+(\d+)\s*\n"
        r"(.*?)(?=\n\s*SECTION\s+\d+\s*\|\s*VISUAL\s+\d+|\Z)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    for match in pattern.finditer(section_text):

        section_number = int(match.group(1))
        visual_number = int(match.group(2))
        narration = match.group(3).strip()

        if narration:

            sections.append({
                "section": section_number,
                "visual": visual_number,
                "narration": narration,
            })

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if len(visual_plan) != 8:

        print(
            f"Expected 8 visual concepts, "
            f"got {len(visual_plan)}."
        )

        return None

    if len(sections) != 8:

        print(
            f"Expected 8 narration sections, "
            f"got {len(sections)}."
        )

        return None

    expected_visuals = list(range(1, 9))

    actual_visuals = [
        item["visual"]
        for item in sections
    ]

    if actual_visuals != expected_visuals:

        print(
            "Invalid section-to-visual mapping:"
        )

        print(actual_visuals)

        return None

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    os.makedirs("output", exist_ok=True)

    with open(
        "output/script.txt",
        "w",
        encoding="utf-8"
    ) as file:

        file.write(script)

    with open(
        "output/visual_plan.txt",
        "w",
        encoding="utf-8"
    ) as file:

        for index, visual in enumerate(
            visual_plan,
            start=1
        ):

            file.write(
                f"{index}. {visual}\n"
            )

    with open(
        "output/section_map.txt",
        "w",
        encoding="utf-8"
    ) as file:

        for item in sections:

            file.write(
                f"SECTION {item['section']} | "
                f"VISUAL {item['visual']}\n"
            )

            file.write(
                f"{item['narration']}\n\n"
            )

    print()
    print("=" * 60)
    print("CONTENT PACKAGE SAVED")
    print("=" * 60)
    print()
    print("Script:       output/script.txt")
    print("Visual plan:  output/visual_plan.txt")
    print("Sections:     output/section_map.txt")
    print()
    print(f"Script characters: {len(script)}")
    print(f"Visual concepts:   {len(visual_plan)}")
    print(f"Sections:          {len(sections)}")
    print()

    return script


def _format_news_sources(source_context):
    """
    Convert verified news source data into a clear,
    source-by-source context block for Gemini.
    """

    if not source_context:
        return "No verified news sources supplied."

    articles = source_context.get("articles", [])

    if not articles:
        return "No verified news sources supplied."

    blocks = []

    for index, article in enumerate(articles, start=1):

        headline = str(
            article.get("headline", "")
        ).strip()

        source = str(
            article.get("source", "")
        ).strip()

        published_at = str(
            article.get("published_at", "")
        ).strip()

        url = str(
            article.get("url", "")
        ).strip()

        article_text = str(
            article.get("article_text", "")
        ).strip()

        snippet = str(
            article.get("snippet", "")
        ).strip()

        block = f"""
SOURCE {index}

Headline:
{headline}

Source:
{source}

Published:
{published_at}

Article text:
{article_text}

Snippet:
{snippet}

URL:
{url}
""".strip()

        blocks.append(block)

    return "\n\n".join(blocks)


# ============================================================
# NORMAL TOPIC SCRIPT
# ============================================================

def generate_script(
    topic,
    content_type="News",
    language_style="English news style",
    source_context=None,
):
    """
    Generate a complete content package for a normal topic.

    Creates:

        output/script.txt
        output/visual_plan.txt
        output/section_map.txt
    """

    print()
    print("=" * 60)
    print("AI SCRIPT + VISUAL PLAN GENERATION STARTED")
    print("=" * 60)
    print()
    print("Topic:")
    print(topic)
    print()

    if source_context is None:
        source_context = {}

    # --------------------------------------------------------
    # AUTOMATIC NEWS VERIFICATION
    # --------------------------------------------------------

    if (
        content_type.lower() == "news"
        and not source_context.get("articles")
    ):

        print()
        print("=" * 60)
        print("NEWS VERIFICATION")
        print("=" * 60)
        print()

        try:

            verified = verify_news_topic(
                topic,
                limit=5,
            )

            if verified.get("status") == "SOURCES_FOUND":

                source_context = verified

                print(
                    f"Verified sources: "
                    f"{len(verified.get('articles', []))}"
                )

            else:

                print(
                    "No verified news sources found."
                )

                raise RuntimeError(
                    "News verification failed: no verified "
                    "sources found. Script generation stopped "
                    "to prevent unsupported news claims."
                )

        except Exception as error:

            print(
                f"News verification failed: {error}"
            )

            raise RuntimeError(
                "News verification failed. "
                "Script generation stopped to prevent "
                "unsupported news claims."
            ) from error

    # --------------------------------------------------------
    # DISPLAY SOURCE CONTEXT
    # --------------------------------------------------------

    if source_context.get("articles"):

        print(
            "News source context supplied:"
        )

        print(
            f"Sources: "
            f"{len(source_context.get('articles', []))}"
        )

        print()

    formatted_source_context = _format_news_sources(
        source_context
    )

    prompt = f"""
You are a professional English YouTube script writer
and visual-content planning director.

Create a complete YouTube content package about:

{topic}

Content type:
{content_type}

Style:
{language_style}

NEWS SOURCE CONTEXT:
{formatted_source_context}

SOURCE GROUNDING RULES:

The NEWS SOURCE CONTEXT contains verified source articles.

For a NEWS video, the verified article text is the
primary factual source.

IMPORTANT SOURCE SELECTION RULES:

1. First identify which verified source or sources are
   directly relevant to the requested topic.

2. If the topic asks for a specific news story, build the
   entire narration around that story. Do not combine it
   with unrelated verified articles.

3. If the topic explicitly asks for a roundup, multiple
   stories may be used. In that case, treat each story as
   a separate news item and clearly transition between them.

4. Do NOT create a broad "technology roundup" merely because
   several verified articles contain technology-related words.

5. Do NOT combine separate people, organizations, locations,
   dates, projects, statistics or events into one event.

6. Every factual claim in the narration must be supported by
   the supplied source context, preferably by the full
   Article text field.

7. Headlines and snippets may identify a story, but do not
   use them as evidence for additional facts that are not
   present in the supplied Article text.

8. If Article text is available, prefer it over inference
   from the headline or snippet.

9. If a verified source is older than the topic implies,
   do not describe it as breaking, today's, or newly
   announced news unless the source explicitly supports that.

10. Never invent names, titles, casualty figures, dates,
    quotes, locations, statistics, investments, partnerships,
    announcements or events.

11. Never merge facts from different articles unless the
    relationship between those facts is explicitly supported
    by the source material.

12. If the supplied sources do not contain enough evidence
    to create a factual script about the requested topic,
    state that the available sources are insufficient rather
    than inventing information.

SOURCE PRIORITY:

Use this priority when deciding what information to include:

1. Full verified Article text
2. Verified headline
3. Verified publication date
4. Verified source name
5. Verified snippet
6. URL only for source identification

Do not use outside knowledge to fill missing information.

NEWS ACCURACY:

- Every important factual sentence must be traceable to a
  supplied verified source.
- Keep facts attached to the correct source.
- Do not transfer a fact from SOURCE 1 to SOURCE 2.
- Do not assume that two articles describe the same event.
- Preserve uncertainty when the source itself is uncertain.
- Never present an unverified event as confirmed news.

LANGUAGE:

- English only.
- Never use Telugu.
- Never use Telugu script.
- Never use Romanized Telugu.
- Use natural spoken English.
- Write for an English TTS voice.
- Preserve names, places, organizations, dates and amounts.
- Do not invent facts, quotes or statistics.

SCRIPT:

- Approximately 2 to 4 minutes.
- Start with a strong professional hook.
- Explain the topic clearly.
- Use natural spoken sentences.
- Maintain logical flow.
- For news, remain factual and neutral.
- For education, explain concepts simply.
- For entertainment, remain engaging and original.
- End with a concise conclusion.
- No markdown.
- No bullet points inside the narration.
- No camera directions.
- No sound effects.
- No stage directions.

VISUAL PLAN:

Create EXACTLY 8 visual concepts.

Visual 1 must represent the main subject/opening hook.

Visuals 2 through 7 must represent different
supporting subjects directly discussed in the script.

Visual 8 must be a strong final visual directly related
to the topic.

Every visual must be specific enough for an image-search
or image-generation system.

Do NOT use unrelated people, celebrities, locations,
businesses or events.

Do NOT create generic unrelated stock images.

SECTION MAPPING:

Create EXACTLY 8 narration sections.

Each section must correspond to exactly one visual.

The narration in each section must directly discuss
the subject represented by its visual.

The eight sections together must form one continuous
YouTube narration.

Return EXACTLY this structure:

SCRIPT:
<complete narration>

VISUAL_PLAN:
1. <specific visual concept>
2. <specific visual concept>
3. <specific visual concept>
4. <specific visual concept>
5. <specific visual concept>
6. <specific visual concept>
7. <specific visual concept>
8. <specific visual concept>

SECTIONS:

SECTION 1 | VISUAL 1
<narration>

SECTION 2 | VISUAL 2
<narration>

SECTION 3 | VISUAL 3
<narration>

SECTION 4 | VISUAL 4
<narration>

SECTION 5 | VISUAL 5
<narration>

SECTION 6 | VISUAL 6
<narration>

SECTION 7 | VISUAL 7
<narration>

SECTION 8 | VISUAL 8
<narration>
"""

    for model in MODELS:

        try:

            print(f"Trying model: {model}")

            response = client.models.generate_content(
                model=model,
                contents=prompt
            )

            text = clean_response(
                getattr(response, "text", "")
            )

            if len(text) < 300:

                print(
                    "Generated response is too short."
                )

                continue

            script = _parse_and_save_package(text)

            if script is None:

                print(
                    f"Model {model} returned an "
                    "invalid content package."
                )

                continue

            print()
            print("=" * 60)
            print("NORMAL TOPIC GENERATION SUCCESSFUL")
            print("=" * 60)
            print()

            return script

        except Exception as error:

            print()
            print(f"Model failed: {model}")
            print(error)
            print()

    raise RuntimeError(
        "All Gemini models failed to generate "
        "a valid content package."
    )


# ============================================================
# FLYER / IMAGE SCRIPT
# ============================================================

def generate_script_from_image(
    image_file,
    language_style="English",
):
    """
    Analyze an uploaded flyer/image and create:

        output/script.txt
        output/visual_plan.txt
        output/section_map.txt

    Returns a structured package:

        {
            "script": str,
            "visual_plan": list[str],
            "sections": list[dict]
        }
    """

    print()
    print("=" * 60)
    print("AI FLYER ANALYSIS STARTED")
    print("=" * 60)
    print()
    print("Flyer:")
    print(image_file)
    print()

    mime_type = (
        mimetypes.guess_type(image_file)[0]
        or "image/jpeg"
    )

    with open(image_file, "rb") as file:
        image_part = genai.types.Part.from_bytes(
            data=file.read(),
            mime_type=mime_type,
        )

    prompt = """
You are an expert visual-content analyst and professional
English YouTube script writer.

Carefully inspect the uploaded flyer/image.

The flyer is the primary source of truth.

Identify only information visible or clearly supported
by the flyer.

Create a natural English YouTube narration based on
the flyer.

LANGUAGE:

- English only.
- Never use Telugu.
- Never use Telugu script.
- Never use Romanized Telugu.
- Use natural spoken English.
- Write for an English TTS voice.
- Preserve names, places, organizations, dates
  and important numbers.
- Do not invent unsupported facts.

SCRIPT:

- Approximately 60 to 120 seconds.
- Begin with an engaging introduction.
- Explain what the flyer is about.
- Mention important visible details.
- Explain relevant people, businesses,
  organizations, places or products.
- Do not simply read the flyer word-for-word.
- Make the narration useful and natural.
- End with a suitable conclusion.
- No markdown.
- No camera directions.
- No sound effects.
- No image instructions.

VISUAL PLAN:

Create EXACTLY 8 different visual concepts.

Visual 1 should represent the opening/main subject.

Visuals 2 to 7 should represent different supporting
subjects directly connected to the flyer.

Visual 8 MUST be:
the original flyer.

Do not make all visual concepts copies of the flyer.

SECTION MAPPING:

Create EXACTLY 8 narration sections.

Every visual must have a corresponding narration section.

Each section must directly discuss its assigned visual.

The narration must flow continuously from Section 1
through Section 8.

Return EXACTLY this structure:

SCRIPT:
<complete narration>

VISUAL_PLAN:
1. <specific visual concept>
2. <specific visual concept>
3. <specific visual concept>
4. <specific visual concept>
5. <specific visual concept>
6. <specific visual concept>
7. <specific visual concept>
8. The original flyer.

SECTIONS:

SECTION 1 | VISUAL 1
<narration>

SECTION 2 | VISUAL 2
<narration>

SECTION 3 | VISUAL 3
<narration>

SECTION 4 | VISUAL 4
<narration>

SECTION 5 | VISUAL 5
<narration>

SECTION 6 | VISUAL 6
<narration>

SECTION 7 | VISUAL 7
<narration>

SECTION 8 | VISUAL 8
<narration>
"""

    for model in MODELS:

        try:
            print(f"Trying flyer model: {model}")

            response = client.models.generate_content(
                model=model,
                contents=[
                    prompt,
                    image_part,
                ],
            )

            text = clean_response(
                getattr(response, "text", "")
            )

            if len(text) < 300:
                print("Flyer response is too short.")
                continue

            script = _parse_and_save_package(text)

            if script is None:
                print(
                    f"Model {model} returned an "
                    "invalid flyer package."
                )
                continue

            # ------------------------------------------------
            # READ VISUAL PLAN
            # ------------------------------------------------

            visual_plan = []

            visual_path = Path(
                "output/visual_plan.txt"
            )

            for line in visual_path.read_text(
                encoding="utf-8"
            ).splitlines():

                line = line.strip()

                if not line:
                    continue

                line = re.sub(
                    r"^\d+[\.\)]\s*",
                    "",
                    line,
                )

                visual_plan.append(line)

            # ------------------------------------------------
            # READ STRUCTURED SECTIONS
            # ------------------------------------------------

            sections = []

            section_path = Path(
                "output/section_map.txt"
            )

            section_text = section_path.read_text(
                encoding="utf-8"
            ).strip()

            pattern = re.compile(
                r"SECTION\s+(\d+)\s*\|\s*VISUAL\s+(\d+)\s*\n"
                r"(.*?)(?=\n\s*SECTION\s+\d+\s*\|\s*VISUAL\s+\d+|\Z)",
                flags=re.IGNORECASE | re.DOTALL,
            )

            for match in pattern.finditer(section_text):

                section_number = int(match.group(1))
                visual_number = int(match.group(2))
                narration = match.group(3).strip()

                if narration:
                    sections.append({
                        "section": section_number,
                        "visual": visual_number,
                        "narration": narration,
                    })

            # ------------------------------------------------
            # FINAL RETURN VALIDATION
            # ------------------------------------------------

            if len(visual_plan) != 8:
                raise RuntimeError(
                    f"Return validation failed: "
                    f"expected 8 visuals, got {len(visual_plan)}"
                )

            if len(sections) != 8:
                raise RuntimeError(
                    f"Return validation failed: "
                    f"expected 8 sections, got {len(sections)}"
                )

            expected_visuals = list(range(1, 9))

            actual_visuals = [
                item["visual"]
                for item in sections
            ]

            if actual_visuals != expected_visuals:
                raise RuntimeError(
                    "Return validation failed: "
                    f"invalid visual mapping {actual_visuals}"
                )

            print()
            print("=" * 60)
            print("FLYER ANALYSIS COMPLETED")
            print("=" * 60)
            print()
            print(f"Returned script:  {len(script)} characters")
            print(f"Returned visuals: {len(visual_plan)}")
            print(f"Returned sections:{len(sections)}")
            print()

            return {
                "script": script,
                "visual_plan": visual_plan,
                "sections": sections,
            }

        except Exception as error:

            print()
            print(f"Flyer model failed: {model}")
            print(error)
            print()

    raise RuntimeError(
        "All Gemini models failed to analyze "
        "the flyer."
    )


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
from supervisor import autonomous_recover



# ============================================================
# CONFIG
# ============================================================

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in .env file")

client = genai.Client(api_key=API_KEY)

MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.6-flash",
]


def _call_gemini_with_retry(contents, model, max_retries=2):
    """
    Call Gemini API with automatic reconnection, client refresh,
    and fast failover on quota / load limits.
    """
    global client
    import time

    for attempt in range(1, max_retries + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
            )
        except Exception as error:
            err_str = str(error)
            # If rate limited (429) or overloaded (503), do not loop retry; immediately fail over to next model
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "UNAVAILABLE" in err_str:
                print(f"⚠️ Model {model} rate limited or high demand, falling over to next model...")
                raise

            is_net_err = (
                "nodename nor servname provided" in err_str
                or "ConnectError" in err_str
                or "ConnectionReset" in err_str
                or "RemoteDisconnected" in err_str
                or "Connection refused" in err_str
                or "timeout" in err_str.lower()
                or "temporary failure in name resolution" in err_str.lower()
            )
            if is_net_err and attempt < max_retries:
                backoff = 1.0 * attempt
                print(
                    f"⚠️ Network hiccup with {model} (attempt {attempt}/{max_retries}): {error}. "
                    f"Re-initializing API client and retrying in {backoff:.1f}s..."
                )
                time.sleep(backoff)
                try:
                    client = genai.Client(api_key=API_KEY)
                except Exception:
                    pass
                continue
            raise



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


def _parse_and_save_package(text, default_title=None):
    """
    Parse Gemini's structured response and save:

        output/script.txt
        output/visual_plan.txt
        output/section_map.txt

    Returns:
        script string

    Returns None if validation fails.
    """

    title_match = re.search(
        r"TITLE:\s*(.*?)(?:\n\s*SCRIPT:|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    title = clean_response(title_match.group(1)).strip() if title_match else ""

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
        line = re.sub(r"^(?:\d+[\.\)]|\*|\-)\s*", "", line).strip()
        if line and len(line) > 2:
            visual_plan.append(line)

    # --------------------------------------------------------
    # SECTIONS
    # --------------------------------------------------------

    sections = []
    section_text = sections_match.group(1).strip()

    pattern = re.compile(
        r"(?:\*{1,2}|#{1,3}\s*)?SECTION\s+(\d+)\s*[:\|]\s*VISUAL\s+(\d+)(?:\*{1,2})?:?\s*\n"
        r"(.*?)(?=\n\s*(?:\*{1,2}|#{1,3}\s*)?SECTION\s+\d+\s*[:\|]\s*VISUAL\s+\d+|\Z)",
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

    # If regex missed alternative formatting, try splitting by section headers
    if not sections:
        raw_blocks = re.split(
            r"\n\s*(?:SECTION\s+\d+|###\s*SECTION|\*\*SECTION)",
            section_text,
            flags=re.IGNORECASE,
        )
        sec_idx = 1
        for block in raw_blocks:
            clean_b = block.strip()
            clean_b = re.sub(r"^(?:\|\s*VISUAL\s+\d+|\:\s*VISUAL\s+\d+|\d+)\s*", "", clean_b).strip()
            if len(clean_b) > 20:
                sections.append({
                    "section": sec_idx,
                    "visual": sec_idx,
                    "narration": clean_b,
                })
                sec_idx += 1

    # Strip accidental visual description lines from the start of section narration ONLY if multiple lines exist
    for idx, sec in enumerate(sections):
        if idx < len(visual_plan):
            vis = visual_plan[idx].strip().lower()
            lines = sec["narration"].splitlines()
            if len(lines) > 1:
                first_line = lines[0].strip().lower()
                if (
                    first_line == vis
                    or vis in first_line
                    or first_line in vis
                    or re.match(r"^(?:visual|shot|scene|image)\s*\d*[:\-]", first_line)
                ):
                    cleaned_narr = "\n".join(lines[1:]).strip()
                    if cleaned_narr:
                        sec["narration"] = cleaned_narr

    # Filter out any sections with empty narration and synchronize corresponding visual
    valid_sections = []
    valid_visuals = []
    for idx, sec in enumerate(sections):
        narr = sec.get("narration", "").strip()
        if narr:
            valid_sections.append(sec)
            if idx < len(visual_plan):
                valid_visuals.append(visual_plan[idx])

    if valid_sections:
        sections = valid_sections
        if valid_visuals:
            visual_plan = valid_visuals

    # Reconcile counts gracefully to guarantee exact 1:1 match
    min_count = min(len(visual_plan), len(sections))
    if min_count >= 4:
        visual_plan = visual_plan[:min_count]
        sections = sections[:min_count]

    # Normalize section numbers and visual numbers to 1..N
    for idx, sec in enumerate(sections, start=1):
        sec["section"] = idx
        sec["visual"] = idx

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if len(visual_plan) < 4:
        print(
            f"Visual count too low: "
            f"got {len(visual_plan)} (minimum 4)."
        )
        return None

    if len(sections) != len(visual_plan):
        print(
            f"Section count ({len(sections)}) does not match "
            f"visual-plan count ({len(visual_plan)})."
        )
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

    if not title and default_title:
        candidate_title = str(default_title).strip()
        if len(candidate_title) <= 120 and "\n" not in candidate_title:
            title = candidate_title

    if not title and visual_plan:
        candidate = re.sub(
            r"^(photo|image|picture|illustration|close-up)\s+of\s+",
            "",
            visual_plan[0],
            flags=re.IGNORECASE,
        ).strip()
        if candidate and len(candidate) <= 60:
            title = candidate

    if not title and script:
        first_sent = re.split(r"[.!?\n]", script)[0].strip()
        if len(first_sent) > 60:
            first_sent = first_sent[:57].rsplit(" ", 1)[0] + "..."
        title = first_sent

    if title:
        with open(
            "output/title.txt",
            "w",
            encoding="utf-8"
        ) as file:
            file.write(title)

    print()
    print("=" * 60)
    print("CONTENT PACKAGE SAVED")
    print("=" * 60)
    print()
    if title:
        print(f"Title:        output/title.txt ({title})")
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

@autonomous_recover("script_agent")
def generate_script(
    topic,
    content_type="News",
    language_style="English news style",
    source_context=None,
    default_title=None,
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
    if "\n" in str(topic).strip() or len(str(topic)) > 200:
        print("Processing AI script revision request...")
    else:
        print(f"Topic: {topic.strip()}")
    print()

    if source_context is None:
        source_context = {}

    # --------------------------------------------------------
    # AUTOMATIC NEWS VERIFICATION
    # --------------------------------------------------------

    if (
        content_type.lower() == "news"
        and not source_context.get("articles")
        and len(topic.strip()) < 250
        and "\n" not in topic.strip()
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
                    "⚠️ No verified news sources found. "
                    "Continuing with cautious topic grounding "
                    "to avoid unsupported claims."
                )

                source_context = {
                    "status": "UNVERIFIED",
                    "articles": [],
                }

        except Exception as error:

            print(
                f"⚠️ News verification warning: {error}. "
                "Continuing with cautious topic grounding."
            )

            source_context = {
                "status": "UNVERIFIED",
                "articles": [],
            }

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

CONTENT-TYPE BEHAVIOR:

If Content type is NEWS:
- When verified sources are supplied in NEWS SOURCE CONTEXT, treat them as the primary factual basis.
- If verified news sources are provided, every important factual claim must be grounded in the supplied material.
- If no verified news source context is available, explain the topic objectively, factually, and educationally using established industry knowledge without inventing false quotes or fake announcements.
- Do not invent facts, quotes, dates, statistics, names, events, partnerships or announcements.

If Content type is GENERAL TOPIC:
- Do NOT require NEWS SOURCE CONTEXT.
- Do NOT say that sources are insufficient merely because no news sources were supplied.
- Answer the requested topic normally using your general knowledge.
- Explain educational or general topics clearly and accurately.
- Do not invent highly specific facts, statistics, quotes, dates or claims when you are not confident they are correct.

IMPORTANT SOURCE SELECTION RULES:

1. First identify which verified source or sources are directly relevant to the requested topic.

2. If the topic asks for a specific news story, build the entire narration around that story. Do not combine it with unrelated verified articles.

3. If the topic explicitly asks for a roundup, multiple stories may be used. In that case, treat each story as a separate news item and clearly transition between them.

4. Do NOT create a broad "technology roundup" merely because several verified articles contain technology-related words.

5. Do NOT combine separate people, organizations, locations, dates, projects, statistics or events into one event.

6. For NEWS content, every factual claim in the narration must be supported by the supplied source context when available, preferably by the full Article text field.

7. Headlines and snippets may identify a story, but do not use them as evidence for additional facts that are not present in the supplied Article text.

8. If Article text is available, prefer it over inference from the headline or snippet.

9. If a verified source is older than the topic implies, do not describe it as breaking, today's, or newly announced news unless the source explicitly supports that.

10. Never invent names, titles, casualty figures, dates, quotes, locations, statistics, investments, partnerships, announcements or events.

11. Never merge facts from different articles unless the sources clearly support that connection.

12. For NEWS content, if verified news sources are absent, provide a clear, balanced, and objective overview based on established industry knowledge rather than refusing or halting the script.

13. For GENERAL TOPIC content, absence of news source context is NOT a reason to refuse or shorten the script.

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

VISUAL PLAN & PACING:

Generate a RICH and DYNAMIC visual plan with frequent scene transitions (a new visual every 5 to 10 seconds of speech).
Guidelines for visual count:
- 30–60 second scripts (Shorts): 8–12 dynamic visuals
- 60–120 second scripts: 12–18 dynamic visuals
- 120–240+ second scripts: 18–28 dynamic visuals

Divide your narration into short, engaging sections (1 to 2 sentences per section, around 5 to 10 seconds of speech each).
Every section must have its own dedicated, concrete visual concept in the VISUAL_PLAN!
This ensures the video has frequent, cinematic visual cuts instead of holding on one image for too long.

Visual 1 must represent the main subject/opening hook.
Supporting visuals 2 through N-1 must represent different supporting subjects directly discussed in their corresponding narration section.
Visual N must be a strong concluding visual directly related to the final takeaway.

CRITICAL VISUAL RELEVANCE:
Every visual must describe the EXACT subject being discussed in that section.
Do NOT use generic descriptions (e.g. do not write "AI technology", "India news", "business").
Instead, describe concrete visual scenes (e.g. "Sam Altman presenting model at OpenAI headquarters", "Nvidia Blackwell AI chip with liquid cooling").

SECTION MAPPING:

Create EXACTLY N narration sections, matching the N visuals in your visual plan.
Each section must correspond to exactly one visual (SECTION N | VISUAL N).
The narration in each section must directly discuss the subject represented by its visual.
The N sections together must form one continuous YouTube narration.

Return EXACTLY this structure:

TITLE:
<punchy concise YouTube video title under 60 characters>

SCRIPT:
<complete narration>

VISUAL_PLAN:
1. <specific visual concept>
2. <specific visual concept>
...
N. <specific visual concept>

SECTIONS:

SECTION 1 | VISUAL 1
<narration>

SECTION 2 | VISUAL 2
<narration>

...
SECTION N | VISUAL N
<narration>
"""

    model_errors = []

    for model in MODELS:

        try:

            print(f"Trying model: {model}")

            response = _call_gemini_with_retry(
                contents=prompt,
                model=model,
            )

            text = clean_response(
                getattr(response, "text", "")
            )

            if len(text) < 300:

                print(
                    "Generated response is too short."
                )
                model_errors.append(f"{model}: response too short ({len(text)} chars)")
                continue

            fallback_title = default_title
            if not fallback_title and isinstance(topic, str) and len(topic.strip()) <= 120 and "\n" not in topic:
                fallback_title = topic.strip()

            script = _parse_and_save_package(
                text,
                default_title=fallback_title,
            )

            if script is None:

                print(
                    f"Model {model} returned an "
                    "invalid content package."
                )
                model_errors.append(f"{model}: invalid content package")
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
            model_errors.append(f"{model}: {error}")

    err_summary = "; ".join(model_errors)
    all_network = all(
        ("nodename nor servname provided" in e or "ConnectError" in e or "temporary failure" in e.lower())
        for e in model_errors
    ) if model_errors else False

    if all_network:
        raise RuntimeError(
            "AutoTube AI failed: Network connection error connecting to Gemini API. "
            "Please ensure you are connected to the internet and running outside sandbox restrictions."
        )
    raise RuntimeError(
        f"All Gemini models failed to generate a valid content package ({err_summary})."
    )


# ============================================================
# FLYER / IMAGE SCRIPT
# ============================================================

@autonomous_recover("script_agent")
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

VISUAL PLAN:

Create an appropriate number of visual concepts (typically 5 to 8 concepts) matching the narration.

Visual 1 should represent the opening/main subject.

Visuals 2 through N-1 should represent different supporting
subjects directly connected to the flyer.

Visual N (the final visual) MUST be:
the original flyer.

Do not make all visual concepts copies of the flyer.

SECTION MAPPING:

Create EXACTLY N narration sections matching the N visuals.

Every visual must have a corresponding narration section (SECTION N | VISUAL N).

Each section must directly discuss its assigned visual.

The final section must directly correspond to the original flyer as the concluding call-to-action.

The narration must flow continuously from Section 1 through Section N.

Return EXACTLY this structure:

TITLE:
<catchy, concise headline under 60 characters for this flyer or event>

SCRIPT:
<complete narration>

VISUAL_PLAN:
1. <specific visual concept>
2. <specific visual concept>
...
N. The original flyer.

SECTIONS:

SECTION 1 | VISUAL 1
<narration>

SECTION 2 | VISUAL 2
<narration>

...
SECTION N | VISUAL N
<narration>
"""

    for model in MODELS:

        try:
            print(f"Trying flyer model: {model}")

            response = _call_gemini_with_retry(
                contents=[
                    prompt,
                    image_part,
                ],
                model=model,
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

            if len(visual_plan) < 4:
                raise RuntimeError(
                    f"Return validation failed: "
                    f"expected at least 4 visuals, got {len(visual_plan)}"
                )

            if len(sections) != len(visual_plan):
                raise RuntimeError(
                    f"Return validation failed: "
                    f"expected matching sections ({len(sections)}) and visuals ({len(visual_plan)})"
                )

            expected_visuals = list(range(1, len(visual_plan) + 1))

            actual_visuals = [
                item["visual"]
                for item in sections
            ]

            if actual_visuals != expected_visuals:
                raise RuntimeError(
                    "Return validation failed: "
                    f"invalid visual mapping {actual_visuals}"
                )

            # Ensure the final visual is always designated for the flyer
            visual_plan[-1] = "The original uploaded flyer."

            print()
            print("=" * 60)
            print("FLYER ANALYSIS COMPLETED")
            print("=" * 60)
            print()
            print(f"Returned script:  {len(script)} characters")
            print(f"Returned visuals: {len(visual_plan)}")
            print(f"Returned sections:{len(sections)}")
            print()

            title_path = Path("output/title.txt")
            flyer_title = (
                title_path.read_text(encoding="utf-8").strip()
                if title_path.exists()
                else ""
            )

            return {
                "title": flyer_title,
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


# ============================================================
# USER-PROVIDED SCRIPT PIPELINE (VERBATIM / EXACT PRESERVATION)
# ============================================================

def generate_package_from_user_script(
    user_script,
    title=None,
):
    """
    Process an exact user-provided script:
    1. Preserves the user script 100% byte-for-byte in output/user_script_original.txt
       and output/script.txt.
    2. Prompts Gemini ONLY to segment the exact script into logical sections and
       generate specific, entity-relevant visual descriptions.
    3. Fails if the user script cannot be cleanly segmented.
    """

    user_script = clean_response(user_script).strip()
    if not user_script:
        raise ValueError("User script is empty.")

    os.makedirs("output", exist_ok=True)

    # Save original user script for strict pipeline verification
    original_path = Path("output/user_script_original.txt")
    original_path.write_text(user_script, encoding="utf-8")

    # Script file must be identical
    script_path = Path("output/script.txt")
    script_path.write_text(user_script, encoding="utf-8")

    words = user_script.split()
    word_count = len(words)
    # Estimate ~12-15 words per visual section (scene change every 5-7 seconds)
    suggested_count = max(6, min(26, max(6, round(word_count / 14))))

    print()
    print("=" * 60)
    print("USER SCRIPT VISUAL PLANNING STARTED")
    print("=" * 60)
    print(f"Words: {word_count} | Suggested visual sections: {suggested_count}")

    prompt = f"""You are an expert visual planner and YouTube editor.
A creator has provided their EXACT YouTube script.

CRITICAL REQUIREMENT:
You must NOT modify, rewrite, paraphrase, shorten, or expand the creator's narration text.
Every sentence and word from the script must appear in order across the sections.

Your ONLY job is:
1. Divide the provided narration into approximately {suggested_count} logical narrative sections (between 6 and 26 sections, with scene changes every 5 to 8 seconds).
2. For each section, design a specific, highly relevant visual concept and search query that depicts the EXACT subject, company, person, product, or event being spoken about in that section.
   - Do NOT use generic terms like "AI technology", "business", "news".
   - Describe concrete visual imagery matching the spoken words.

CREATOR'S EXACT SCRIPT:
{user_script}

Return EXACTLY this structure:

TITLE:
{title or "Creator Video"}

SCRIPT:
{user_script}

VISUAL_PLAN:
1. <specific visual concept for section 1>
2. <specific visual concept for section 2>
...
N. <specific visual concept for section N>

SECTIONS:

SECTION 1 | VISUAL 1
<exact verbatim text for first section>

SECTION 2 | VISUAL 2
<exact verbatim text for second section>

...
SECTION N | VISUAL N
<exact verbatim text for concluding section>
"""

    for model in MODELS:
        try:
            print(f"Trying user script visual planner model: {model}")
            response = _call_gemini_with_retry(
                contents=prompt,
                model=model,
            )

            text = clean_response(getattr(response, "text", ""))
            if len(text) < 200:
                continue

            fallback_title = title or "Creator Video"
            result = _parse_and_save_package(
                text,
                default_title=fallback_title,
            )

            if result:
                # Guarantee byte-for-byte script integrity
                script_path.write_text(user_script, encoding="utf-8")
                print("User script visual plan & section mapping created successfully!")
                return user_script

        except Exception as error:
            print(f"User script visual planning error with {model}: {error}")
            continue

    # Fallback: create automated sentence-based sectioning if AI formatting was imperfect
    print("Creating direct sentence-based visual plan fallback for user script...")
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", user_script) if s.strip()]
    if not sentences:
        sentences = [user_script]

    n_sections = max(4, min(len(sentences), suggested_count))
    chunk_size = max(1, len(sentences) // n_sections)
    
    sections = []
    visual_plan = []
    
    for i in range(n_sections):
        start_idx = i * chunk_size
        end_idx = (i + 1) * chunk_size if i < n_sections - 1 else len(sentences)
        chunk_sentences = sentences[start_idx:end_idx]
        chunk_text = " ".join(chunk_sentences).strip()
        if not chunk_text:
            continue
        v_num = len(sections) + 1
        first_few = " ".join(chunk_text.split()[:8])
        visual_plan.append(f"Scene illustrating: {first_few}")
        sections.append({
            "section": v_num,
            "visual": v_num,
            "narration": chunk_text,
        })

    # Save outputs
    with open("output/visual_plan.txt", "w", encoding="utf-8") as f:
        for idx, v in enumerate(visual_plan, 1):
            f.write(f"{idx}. {v}\n")

    with open("output/section_map.txt", "w", encoding="utf-8") as f:
        for item in sections:
            f.write(f"SECTION {item['section']} | VISUAL {item['visual']}\n{item['narration']}\n\n")

    if title:
        Path("output/title.txt").write_text(title, encoding="utf-8")

    script_path.write_text(user_script, encoding="utf-8")
    return user_script


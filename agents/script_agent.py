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


# ============================================================
# NORMAL TOPIC SCRIPT
# ============================================================

def generate_script(
    topic,
    content_type="News",
    language_style="English news style",
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

    prompt = f"""
You are a professional English YouTube script writer
and visual-content planning director.

Create a complete YouTube content package about:

{topic}

Content type:
{content_type}

Style:
{language_style}

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


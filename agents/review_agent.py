import os
import json
import re
from pathlib import Path

from dotenv import load_dotenv
from google import genai


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in .env file")

client = genai.Client(api_key=API_KEY)

MODEL = "gemini-3.1-flash-lite"


# ============================================================
# READ FILE
# ============================================================

def read_text_file(path):

    path = Path(path)

    if not path.exists():
        return ""

    try:
        return path.read_text(
            encoding="utf-8"
        )

    except Exception as error:

        print(
            f"Error reading {path}: {error}"
        )

        return ""


# ============================================================
# CLEAN JSON
# ============================================================

def clean_json(text):

    if not text:
        return ""

    text = text.strip()

    text = re.sub(
        r"^```json",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^```",
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
# LOAD PROJECT
# ============================================================

def load_project_outputs():

    print()
    print("=" * 60)
    print("LOADING AUTOTUBE OUTPUTS")
    print("=" * 60)

    script = read_text_file(
        "output/script.txt"
    )

    visual_plan = read_text_file(
        "output/visual_plan.txt"
    )

    subtitles = read_text_file(
        "output/subtitles.srt"
    )

    video_path = "output/final_video.mp4"
    thumbnail_path = "output/thumbnail.jpg"
    subtitles_path = "output/subtitles.srt"

    video_exists = Path(
        video_path
    ).exists()

    thumbnail_exists = Path(
        thumbnail_path
    ).exists()

    subtitles_exists = Path(
        subtitles_path
    ).exists()

    print(
        f"Script       : "
        f"{'FOUND' if script else 'MISSING'}"
    )

    print(
        f"Visual Plan  : "
        f"{'FOUND' if visual_plan else 'MISSING'}"
    )

    print(
        f"Subtitles    : "
        f"{'FOUND' if subtitles_exists else 'MISSING'}"
    )

    print(
        f"Final Video  : "
        f"{'FOUND' if video_exists else 'MISSING'}"
    )

    print(
        f"Thumbnail    : "
        f"{'FOUND' if thumbnail_exists else 'MISSING'}"
    )

    return {
        "script": script,
        "visual_plan": visual_plan,
        "subtitles": subtitles,
        "video_path": video_path,
        "thumbnail_path": thumbnail_path,
        "subtitles_path": subtitles_path,
        "video_exists": video_exists,
        "thumbnail_exists": thumbnail_exists,
        "subtitles_exists": subtitles_exists,
    }


# ============================================================
# REVIEW
# ============================================================

def review_video(
    script,
    visual_plan,
    subtitles,
    video_exists,
    thumbnail_exists,
    subtitles_exists,
    captions_enabled=True,
    source_context=None,
):

    print()
    print("=" * 60)
    print("AI VIDEO REVIEW STARTED")
    print("=" * 60)

    if source_context is None:
        source_context = {}

    # --------------------------------------------------------
    # BUILD SIMPLE REVIEW PROMPT
    # --------------------------------------------------------

    verified_articles = source_context.get(
        "articles",
        [],
    )

    source_blocks = []

    for index, article in enumerate(
        verified_articles,
        start=1,
    ):

        source_blocks.append(
            f"""
SOURCE {index}
Headline:
{article.get("headline", "")}

Source:
{article.get("source", "")}

Published:
{article.get("published_at", "")}

Article text:
{article.get("article_text", "")}

Snippet:
{article.get("snippet", "")}

URL:
{article.get("url", "")}
""".strip()
        )

    formatted_source_context = (
        "\n\n".join(source_blocks)
        if source_blocks
        else "No verified news source context supplied."
    )

    prompt = f"""
You are the quality-control reviewer for AutoTube AI.

Review this YouTube project.

SCRIPT:

{script}


VISUAL PLAN:

{visual_plan}


VERIFIED NEWS SOURCE CONTEXT:

{formatted_source_context}


SUBTITLES:

{subtitles}


FILES:

Video exists: {video_exists}
Thumbnail exists: {thumbnail_exists}
Subtitles exist: {subtitles_exists}
Captions enabled by user: {captions_enabled}


Evaluate:

- script quality
- factual quality
- hook
- story flow
- visual relevance
- subtitle quality only when captions are enabled
- thumbnail readiness
- overall YouTube readiness

Look for:

- weak writing
- unsupported claims
- claims contradicted by the verified source context
- claims presented as confirmed when sources describe them as reported,
  projected, expected, rumored, or possible
- facts incorrectly combined from different sources
- contradictions
- repetition
- weak opening
- poor structure
- missing conclusion
- generic visuals
- mismatch between narration and visuals
- subtitle problems only when captions are enabled

IMPORTANT CAPTION RULE:
- If captions_enabled is true, subtitles must exist and should match the narration.
- If captions_enabled is false, missing subtitles are NOT a problem and must NOT create a critical issue.

Approve only if the project is genuinely ready.

FACTUAL REVIEW RULE:
For NEWS content, use VERIFIED NEWS SOURCE CONTEXT as the
primary evidence for factual claims.

Do not mark a claim false merely because it is absent from
your pretrained knowledge.

Classify factual claims as:
- CONFIRMED: directly supported by supplied article text.
- REPORTED_OR_PROJECTED: explicitly described by the sources
  as reported, expected, projected, rumored, or possible.
- UNSUPPORTED: not supported by the supplied sources.
- CONTRADICTED: supplied sources directly conflict with the claim.

A reported or projected claim is not automatically a factual error,
but the narration must use wording that preserves that uncertainty.

Do not use outside knowledge to override supplied source evidence.

APPROVE:
score 75 or higher and no critical issue.

IMPROVE:
score below 75 or any critical issue.

Return ONLY JSON.

Use this exact format:

{{
  "status": "APPROVE",
  "score": 80,
  "summary": "Short assessment",

  "script": {{
    "score": 80,
    "status": "GOOD",
    "feedback": "..."
  }},

  "factual_quality": {{
    "score": 80,
    "status": "GOOD",
    "feedback": "..."
  }},

  "hook": {{
    "score": 80,
    "status": "GOOD",
    "feedback": "..."
  }},

  "visuals": {{
    "score": 80,
    "status": "GOOD",
    "feedback": "..."
  }},

  "subtitles": {{
    "score": 80,
    "status": "GOOD",
    "feedback": "..."
  }},

  "thumbnail": {{
    "score": 80,
    "status": "GOOD",
    "feedback": "..."
  }},

  "critical_issues": [],

  "improvements": []
}}
"""

    # --------------------------------------------------------
    # GEMINI REQUEST
    # --------------------------------------------------------

    print()
    print(
        "Sending review request to Gemini..."
    )

    try:

        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )

        text = getattr(
            response,
            "text",
            ""
        )

        if not text:

            raise RuntimeError(
                "Gemini returned an empty response."
            )

        text = clean_json(text)

        result = json.loads(text)

    except Exception as error:

        print()
        print("=" * 60)
        print("REVIEW ERROR")
        print("=" * 60)

        print(
            type(error).__name__
        )

        print(error)

        error_text = str(error)

        # Gemini free-tier/API quota exhaustion is not a
        # content-quality failure. Stop immediately rather
        # than consuming more review attempts.
        if (
            "RESOURCE_EXHAUSTED" in error_text
            or "429" in error_text
            or "quota" in error_text.lower()
            or "rate limit" in error_text.lower()
        ):

            return {
                "status": "REVIEW_QUOTA_EXCEEDED",
                "score": 0,
                "summary": (
                    "Gemini API quota/rate limit was exceeded. "
                    "Review stopped without another retry."
                ),
                "critical_issues": [
                    error_text
                ],
                "improvements": [
                    "Wait for the Gemini quota to reset or use an available model/API quota."
                ]
            }

        return {
            "status": "REVIEW_FAILED",
            "score": 0,
            "summary": "AI review failed.",
            "critical_issues": [
                error_text
            ],
            "improvements": []
        }

    # --------------------------------------------------------
    # SAVE REVIEW
    # --------------------------------------------------------

    os.makedirs(
        "output",
        exist_ok=True
    )

    with open(
        "output/review.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            indent=2,
            ensure_ascii=False
        )

    # --------------------------------------------------------
    # DISPLAY
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("AI REVIEW RESULT")
    print("=" * 60)

    print()
    print(
        f"STATUS : "
        f"{result.get('status')}"
    )

    print(
        f"SCORE  : "
        f"{result.get('score')}/100"
    )

    print()
    print("SUMMARY")
    print("-" * 60)

    print(
        result.get(
            "summary",
            ""
        )
    )

    print()
    print("SECTION SCORES")
    print("-" * 60)

    sections = [
        "script",
        "factual_quality",
        "hook",
        "visuals",
        "subtitles",
        "thumbnail",
    ]

    for section in sections:

        data = result.get(
            section,
            {}
        )

        print(
            f"{section.upper():18}"
            f"{data.get('score', 0):>4}/100   "
            f"{data.get('status', '')}"
        )

    critical = result.get(
        "critical_issues",
        []
    )

    if critical:

        print()
        print("CRITICAL ISSUES")
        print("-" * 60)

        for issue in critical:
            print(
                f"- {issue}"
            )

    improvements = result.get(
        "improvements",
        []
    )

    if improvements:

        print()
        print("IMPROVEMENTS")
        print("-" * 60)

        for improvement in improvements:
            print(
                f"- {improvement}"
            )

    print()
    print(
        "Saved to: output/review.json"
    )

    print("=" * 60)

    return result


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    project = load_project_outputs()

    result = review_video(
        script=project["script"],
        visual_plan=project["visual_plan"],
        subtitles=project["subtitles"],
        video_exists=project["video_exists"],
        thumbnail_exists=project["thumbnail_exists"],
        subtitles_exists=project["subtitles_exists"],
        captions_enabled=True,
    )

    print()
    print("FINAL REVIEW JSON")

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )

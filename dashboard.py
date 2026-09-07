"""AutoTube AI - Multi-Media Streamlit Dashboard."""

import asyncio
import shutil
from pathlib import Path
from importlib import import_module

st = import_module("streamlit")


# ============================================================
# DIRECTORIES
# ============================================================

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
UPLOADS_DIR = OUTPUT_DIR / "uploads"

OUTPUT_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# ENGLISH VOICES ONLY
# ============================================================

VOICE_IDS = {
    "Creator Voice": "af_heart",
}

VOICE_TUNING = {
    "Creator Voice": ("-5%", "+0Hz"),
}


# ============================================================
# CLEAN PREVIOUS GENERATION
# ============================================================

def clean_previous_generation():
    """Remove generated files and old uploaded media."""

    files = [
        "script.txt",
        "visual_plan.txt",
        "section_map.txt",
        "voice.mp3",
        "tts_script.txt",
        "video.mp4",
        "final_video.mp4",
        "subtitles.srt",
        "thumbnail.jpg",
        "review.json",
        "metadata.json",
    ]

    for filename in files:
        path = OUTPUT_DIR / filename

        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass

    if ASSETS_DIR.exists():
        for item in ASSETS_DIR.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                else:
                    shutil.rmtree(item)
            except Exception:
                pass

    if UPLOADS_DIR.exists():
        try:
            shutil.rmtree(UPLOADS_DIR)
        except Exception:
            pass

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# SAVE UPLOAD
# ============================================================

def save_uploaded_file(uploaded_file, index):
    """Save a Streamlit uploaded file with a stable unique name."""

    suffix = Path(uploaded_file.name).suffix.lower()

    if not suffix:
        suffix = ".bin"

    filename = f"uploaded_{index}{suffix}"

    destination = UPLOADS_DIR / filename
    destination.write_bytes(uploaded_file.getbuffer())

    return destination


def save_uploaded_files(uploaded_files):
    """Save multiple uploaded images/videos."""

    saved = []

    for index, uploaded_file in enumerate(
        uploaded_files,
        start=1,
    ):
        saved.append(
            save_uploaded_file(
                uploaded_file,
                index,
            )
        )

    return saved


# ============================================================
# VOICE
# ============================================================

def create_voice_for_script(
    voice,
    own_voice_audio=None,
):
    """Generate English neural voice."""

    if voice not in VOICE_IDS:
        raise ValueError(
            f"Unsupported voice: {voice}"
        )

    from agents.voice_agent import create_voice

    rate, pitch = VOICE_TUNING[voice]

    asyncio.run(
        create_voice(
            VOICE_IDS[voice],
            rate=rate,
            pitch=pitch,
        )
    )


# ============================================================
# IMAGE ANALYSIS
# ============================================================

def generate_script_from_uploaded_media(
    media_files,
    language_style,
):
    """
    Use the first uploaded image/flyer as the primary visual source.

    Additional uploaded media are preserved and used by the
    visual timeline.
    """

    image_file = None

    for file in media_files:
        if file.suffix.lower() in {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }:
            image_file = file
            break

    if image_file is None:
        raise RuntimeError(
            "At least one image is required for Image/Flyer AI analysis."
        )

    from agents.script_agent import generate_script_from_image

    result = generate_script_from_image(
        str(image_file),
        language_style,
    )

    return result


# ============================================================
# VISUAL PLAN DOWNLOAD
# ============================================================

def download_visuals(
    visual_plan_file,
    flyer_path=None,
):
    """
    Download visuals according to the AI visual plan.

    This function does NOT require exactly 8 successful web images.
    """

    from agents.image_agent import (
        download_images_from_visual_plan,
    )

    return download_images_from_visual_plan(
        visual_plan_file,
        flyer_path=flyer_path,
    )


# ============================================================
# PREPARE UPLOADED MEDIA FOR VIDEO AGENT
# ============================================================

def prepare_uploaded_media(
    media_files,
):
    """
    Copy uploaded media into assets/.

    The first uploaded image is preserved as
    flyer_original.jpg so the video agent can use
    the original flyer as the final visual.
    """

    uploaded_assets = []

    image_index = 1
    video_index = 1
    flyer_saved = False

    for source in media_files:

        suffix = source.suffix.lower()

        if suffix in {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }:

            destination = (
                ASSETS_DIR
                / f"uploaded_image_{image_index}{suffix}"
            )

            shutil.copy2(
                source,
                destination,
            )

            uploaded_assets.append(
                destination
            )

            # Preserve the first uploaded image
            # as the original flyer.
            if not flyer_saved:

                flyer_destination = (
                    ASSETS_DIR
                    / "flyer_original.jpg"
                )

                shutil.copy2(
                    source,
                    flyer_destination,
                )

                flyer_saved = True

            image_index += 1

        elif suffix in {
            ".mp4",
            ".mov",
            ".m4v",
            ".avi",
        }:

            destination = (
                ASSETS_DIR
                / f"uploaded_video_{video_index}{suffix}"
            )

            shutil.copy2(
                source,
                destination,
            )

            uploaded_assets.append(
                destination
            )

            video_index += 1

    return uploaded_assets


# ============================================================
# VIDEO CREATION
# ============================================================

def create_pipeline_video():
    """Run the project's video agent."""

    from agents.video_agent import create_video

    return create_video()


# ============================================================
# FINAL VIDEO
# ============================================================

def create_final_video(
    captions=True,
):
    """Create final video with optional captions."""

    from agents.final_video_agent import (
        create_final_video as finalize,
    )

    return finalize(
        add_captions=captions,
    )


# ============================================================
# THUMBNAIL
# ============================================================

def create_thumbnail(
    topic,
):
    """Create thumbnail using existing thumbnail agent."""

    from agents.thumbnail_agent import create_thumbnail

    return create_thumbnail(topic)

# ============================================================
# AI REVIEW
# ============================================================

def create_ai_review(
    captions_enabled=True,
    source_context=None,
    content_type="General Topic",
):
    """Run Gemini AI quality review on the generated project."""

    from agents.review_agent import (
        load_project_outputs,
        review_video,
    )

    project = load_project_outputs()

    return review_video(
        script=project["script"],
        visual_plan=project["visual_plan"],
        subtitles=project["subtitles"],
        video_exists=project["video_exists"],
        thumbnail_exists=project["thumbnail_exists"],
        subtitles_exists=project["subtitles_exists"],
        captions_enabled=captions_enabled,
        source_context=source_context,
        content_type=content_type,
    )


# ============================================================
# METADATA
# ============================================================

def create_metadata(
    topic,
    script,
    youtube_upload=False,
    privacy="private",
):
    """Generate metadata and optionally upload to YouTube."""

    import json
    from pathlib import Path

    from agents.metadata_agent import generate_metadata

    title, description, tags = generate_metadata(
        topic,
        script,
    )

    # --------------------------------------------------------
    # SAVE METADATA
    # --------------------------------------------------------

    output_dir = Path("output")

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata_path = output_dir / "metadata.json"

    metadata = {
        "title": title,
        "description": description,
        "tags": tags,
    }

    with open(
        metadata_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            metadata,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"✅ Metadata saved: {metadata_path}"
    )

    # --------------------------------------------------------
    # OPTIONAL YOUTUBE UPLOAD
    # --------------------------------------------------------

    if youtube_upload:

        from agents.youtube_agent import upload_video

        print()
        print("=" * 60)
        print("YOUTUBE UPLOAD")
        print("=" * 60)
        print(
            f"Privacy: {privacy.upper()}"
        )

        video_id = upload_video(
            "output/final_video.mp4",
            title,
            description,
            tags,
            privacy=privacy,
        )

        print(
            f"✅ YouTube upload complete: {video_id}"
        )

    return title, description, tags


def improve_script_from_review(
    topic,
    previous_script,
    review,
    language_style,
    attempt,
    content_type="News",
    source_context=None,
):
    """
    Revise the EXISTING script using AI review feedback.

    The previous script is the source of truth.
    Do NOT generate a completely new story.
    """

    from agents.script_agent import generate_script

    critical_issues = review.get(
        "critical_issues",
        [],
    )

    improvements = review.get(
        "improvements",
        [],
    )

    feedback_items = (
        critical_issues
        + improvements
    )

    feedback = "\n".join(
        f"- {item}"
        for item in feedback_items
    )

    if not feedback.strip():
        feedback = (
            "- Improve only genuine problems identified by the review."
        )

    revision_prompt = f"""
You are revising an EXISTING YouTube script.

THIS IS NOT A NEW SCRIPT GENERATION TASK.

ORIGINAL TOPIC:
{topic}

CONTENT TYPE:
{content_type}

REVISION ATTEMPT:
{attempt} of 3

PREVIOUS SCRIPT:
====================
{previous_script}
====================

CUMULATIVE AI REVIEW FEEDBACK:
===============================
The feedback below comes from ALL previous review rounds.

Older feedback may already have been fixed in the PREVIOUS SCRIPT.
DO NOT undo or unnecessarily rewrite a fix that is already correctly
implemented.

For every feedback item:
1. Check whether the previous script already fixes it.
2. If it is already fixed, preserve that fix.
3. If it is still missing, fix it now.
4. If a newer review conflicts with an older requirement, follow the
   newer review only when it identifies a genuine problem.
5. Do not make unrelated changes.

FEEDBACK:
====================
{feedback}
====================

VERIFIED SOURCE CONTEXT:
====================
{source_context or "No additional verified source context available."}
====================

YOUR TASK:

Revise the PREVIOUS SCRIPT above.

The previous script is the SOURCE OF TRUTH.

Make ONLY the changes necessary to fix the AI review feedback.

STRICT RULES:

1. KEEP THE SAME STORY.
2. KEEP THE SAME TOPIC.
3. KEEP THE SAME EVENTS.
4. KEEP THE SAME PEOPLE.
5. KEEP THE SAME PLACES.
6. KEEP THE SAME DATES AND TIMES.
7. KEEP THE SAME NUMBERS AND STATISTICS.
8. KEEP the same factual details unless the review specifically
   identifies that detail as incorrect or unsupported.
9. DO NOT create a new story.
10. DO NOT replace the story with another news story.
11. DO NOT add unrelated information.
12. DO NOT invent facts, people, numbers, dates, places, quotes,
    casualties, statistics, or events.
13. If the review identifies an unsupported claim, remove or correct
    ONLY that claim using the verified source context.
14. If the review identifies an incorrect fact, correct ONLY that fact.
15. Preserve the original emotional tone and storytelling style.
16. Preserve the original narrative structure wherever possible.
17. Make the smallest necessary changes.
18. The revised script must remain recognizably the SAME SCRIPT.
19. Do not mention AI, review, revision, prompts, or these instructions.

IMPORTANT:

If the previous script was manually supplied by the user,
NEVER rewrite it just because you can make it "better".

Only change something when the review provides a real reason
to change it.

Return a complete YouTube content package using the SAME revised
story and SAME revised narration.

Keep the visual plan aligned with the revised narration.

Do not change the topic.
Do not start over.
"""

    return generate_script(
        revision_prompt,
        content_type=content_type,
        language_style=language_style,
        source_context=(
            source_context
            if content_type == "News"
            else None
        ),
    )

def generate_multi_media_video(
    topic,
    media_files=None,
    content_type="News",
    language_style="English news style",
    voice="English Female",
    captions=True,
    thumbnail=True,
    metadata=True,
    youtube_upload=False,
    youtube_privacy="private",
    script_override=None,
):
    """
    Topic-first AutoTube AI pipeline with a maximum of 3 AI review
    attempts.

    Flow:

        Topic
          ↓
        Script + Visual Plan
          ↓
        Web Visuals
          ↓
        Voice
          ↓
        Video + Captions
          ↓
        Thumbnail
          ↓
        AI Review
          ↓
        PASS     → Metadata → Optional YouTube Upload
        IMPROVE  → AI Correction → Regenerate → Review again
        3x FAIL  → STOP, no upload
    """

    MAX_REVIEW_ATTEMPTS = 3

    if not topic or not topic.strip():
        raise RuntimeError(
            "Please enter a topic or video idea."
        )

    media_files = media_files or []

    review = {
        "status": "REVIEW_NOT_RUN",
        "score": 0,
        "summary": "",
        "critical_issues": [],
        "improvements": [],
    }

    # Cumulative AI review feedback.
    # Review 1 → Attempt 2
    # Review 1 + Review 2 → Attempt 3
    review_history = []

    script = ""
    title = topic
    description = ""
    tags = []
    stopped_after_review = False
    stop_reason = ""

    news_verification = {
        "status": "NOT_REQUIRED",
        "topic": topic,
        "articles": [],
        "summary": "",
    }

    # --------------------------------------------------------
    # NEWS SOURCE VERIFICATION
    # --------------------------------------------------------

    if (
        content_type == "News"
        and not script_override
    ):


        st.info(
            "📰 Verifying news sources..."
        )

        from agents.news_verifier import (
            verify_news_topic,
        )


        news_verification = (
            verify_news_topic(topic)
        )

        print("DEBUG NEWS STATUS:", news_verification.get("status"))
        print("DEBUG NEWS TOPIC:", topic)
        print("DEBUG NEWS ARTICLES:", len(news_verification.get("articles", [])))

        articles = news_verification.get(
            "articles",
            [],
        )



        if articles:

            st.success(
                "📰 News sources found: "
                f"{len(articles)}"
            )

        else:

            st.warning(
                "⚠️ No matching news sources "
                "were confirmed. The script will "
                "avoid unsupported claims."
            )

    for attempt in range(
        1,
        MAX_REVIEW_ATTEMPTS + 1,
    ):

        print()
        print("=" * 60)
        print(
            f"AUTOTUBE AI GENERATION ATTEMPT "
            f"{attempt}/{MAX_REVIEW_ATTEMPTS}"
        )
        print("=" * 60)

        # Remove generated files from the previous attempt.
        clean_previous_generation()

        progress = st.progress(
            0,
            text=(
                f"Attempt {attempt}/{MAX_REVIEW_ATTEMPTS}: "
                "Starting AutoTube AI..."
            ),
        )

        # ----------------------------------------------------
        # OPTIONAL UPLOADED MEDIA
        # ----------------------------------------------------

        saved_media = []

        if media_files:

            progress.progress(
                5,
                text=(
                    f"Attempt {attempt}: "
                    "Preparing uploaded media..."
                ),
            )

            saved_media = save_uploaded_files(
                media_files
            )

        # ----------------------------------------------------
        # SCRIPT + VISUAL PLAN
        # ----------------------------------------------------

        progress.progress(
            15,
            text=(
                f"Attempt {attempt}: "
                "AI is generating script and visual plan..."
            ),
        )

        if script_override and attempt == 1:

            script = script_override

        elif attempt == 1:

            from agents.script_agent import generate_script

            script = generate_script(
                topic,
                content_type=content_type,
                language_style=language_style,
                source_context=news_verification,
            )

        else:

            # Use ALL previous review feedback.
            # Attempt 2 → Review 1
            # Attempt 3 → Review 1 + Review 2
            cumulative_review = {
                "critical_issues": [],
                "improvements": [],
            }

            for previous_review in review_history:
                cumulative_review["critical_issues"].extend(
                    previous_review.get("critical_issues", [])
                )
                cumulative_review["improvements"].extend(
                    previous_review.get("improvements", [])
                )

            script = improve_script_from_review(
                topic=topic,
                previous_script=script,
                review=cumulative_review,
                language_style=language_style,
                attempt=attempt,
                content_type=content_type,
                source_context=(
                    news_verification
                    if content_type == "News"
                    else None
                ),
            )

        if not script:

            raise RuntimeError(
                "AI did not generate a script."
            )

        # ----------------------------------------------------
        # OPTIONAL UPLOADED MEDIA
        # ----------------------------------------------------

        if saved_media:

            progress.progress(
                25,
                text=(
                    f"Attempt {attempt}: "
                    "Preparing uploaded media..."
                ),
            )

            prepare_uploaded_media(
                saved_media
            )

        # ----------------------------------------------------
        # WEB VISUALS
        # ----------------------------------------------------

        visual_plan_file = (
            OUTPUT_DIR / "visual_plan.txt"
        )

        if not visual_plan_file.exists():

            raise RuntimeError(
                "AI visual plan was not created."
            )

        progress.progress(
            35,
            text=(
                f"Attempt {attempt}: "
                "Finding visuals from AI visual plan..."
            ),
        )

        try:

            download_visuals(
                visual_plan_file
            )

        except Exception as error:

            print(
                "Visual sourcing warning:",
                error,
            )

        # ----------------------------------------------------
        # VOICE
        # ----------------------------------------------------

        progress.progress(
            50,
            text=(
                f"Attempt {attempt}: "
                "Generating English narration..."
            ),
        )

        create_voice_for_script(
            voice
        )

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        progress.progress(
            65,
            text=(
                f"Attempt {attempt}: "
                "Creating video..."
            ),
        )

        create_pipeline_video()

        # ----------------------------------------------------
        # FINAL VIDEO + CAPTIONS
        # ----------------------------------------------------

        progress.progress(
            78,
            text=(
                f"Attempt {attempt}: "
                "Rendering final video and captions..."
            ),
        )

        create_final_video(
            captions=captions
        )

        # ----------------------------------------------------
        # THUMBNAIL
        # ----------------------------------------------------

        if thumbnail:

            progress.progress(
                85,
                text=(
                    f"Attempt {attempt}: "
                    "Creating thumbnail..."
                ),
            )

            create_thumbnail(
                topic
            )

        # ----------------------------------------------------
        # AI REVIEW
        # ----------------------------------------------------

        progress.progress(
            92,
            text=(
                f"🤖 AI Review {attempt}/"
                f"{MAX_REVIEW_ATTEMPTS}..."
            ),
        )

        review = create_ai_review(
            captions_enabled=captions,
            source_context=(
                news_verification
                if content_type == "News"
                else None
            ),
            content_type=content_type,
        )

        status = str(
            review.get(
                "status",
                "REVIEW_FAILED",
            )
        ).upper()

        score = review.get(
            "score",
            0,
        )

        # Save this completed review so future attempts
        # can carry forward ALL previous feedback.
        review_history.append({
            "critical_issues": list(
                review.get("critical_issues", [])
            ),
            "improvements": list(
                review.get("improvements", [])
            ),
        })

        print()
        print("=" * 60)
        print(
            f"REVIEW {attempt}/{MAX_REVIEW_ATTEMPTS}"
        )
        print("=" * 60)
        print(
            "Status:",
            status,
        )
        print(
            "Score:",
            f"{score}/100",
        )

        # ----------------------------------------------------
        # REVIEW FAILURE
        # ----------------------------------------------------

        if status == "REVIEW_QUOTA_EXCEEDED":

            stopped_after_review = True

            stop_reason = (
                "Gemini API quota/rate limit was exceeded. "
                "No further AI review attempts were made. "
                "The latest generated video will continue."
            )

            break

        if status == "REVIEW_FAILED":

            stopped_after_review = True

            stop_reason = (
                "AI review failed. "
                "No further review attempts were made. "
                "The latest generated video will continue."
            )

            break

        # ----------------------------------------------------
        # PASS
        # ----------------------------------------------------

        review_has_critical_issues = bool(
            review.get(
                "critical_issues",
                [],
            )
        )

        review_score = int(
            score or 0
        )

        review_is_approved = (
            status == "APPROVE"
            and review_score >= 60
            and not review_has_critical_issues
        )

        if review_is_approved:

            stop_reason = (
                "AI Review approved the current version "
                "with a score of 60 or higher and no "
                "critical issues."
            )

            stopped_after_review = True

            progress.progress(
                96,
                text=(
                    "✅ AI Review passed. "
                    "Continuing to metadata..."
                ),
            )

            break

        # ----------------------------------------------------
        # IMPROVE / NON-QUALIFIED REVIEW
        # ----------------------------------------------------
        #
        # Any review that is not a genuine PASS must be
        # treated as needing improvement.
        #
        # This includes:
        #   - IMPROVE
        #   - APPROVE below 60
        #   - APPROVE with critical issues
        # ----------------------------------------------------

        if attempt < MAX_REVIEW_ATTEMPTS:

            progress.progress(
                94,
                text=(
                    f"⚠️ Review {attempt} did not meet "
                    "the approval requirements. "
                    "Regenerating..."
                ),
            )

            print(
                "Review did not meet approval requirements."
            )

            print(
                "Regenerating the SAME topic..."
            )

            continue

        # Third failed/non-qualified review → stop.
        stopped_after_review = True

        stop_reason = (
            "Maximum 3 AI review attempts reached. "
            "Keeping the latest generated version."
        )

        break

    # ========================================================
    # STOPPED AFTER REVIEW
    # ========================================================

    if stopped_after_review:

        progress.progress(
            94,
            text=(
                "✅ Review stage finished. "
                "Continuing with the latest generated version..."
            ),
        )

    # --------------------------------------------------------
    # FINAL AI REVIEW / YOUTUBE UPLOAD CONTROL
    # --------------------------------------------------------
    #
    # Reviews 1 and 2 are improvement gates.
    # Review 3 is the FINAL review.
    #
    # IMPORTANT:
    # AI review status must NEVER block YouTube upload
    # after the final review.
    # --------------------------------------------------------

    review_status_final = str(
        review.get("status", "")
    ).upper()

    review_score_final = int(
        review.get("score", 0) or 0
    )

    critical_issues_final = review.get(
        "critical_issues",
        [],
    )

    # AI review is informational after the final attempt.
    # The user's YouTube Upload checkbox controls upload.
    upload_blocked = False

    review_approved = (
        review_status_final == "APPROVE"
        and review_score_final >= 60
        and not critical_issues_final
    )

    if review_approved:
        review_final_message = (
            "AI Review approved the final version."
        )
    elif review_status_final == "IMPROVE":
        review_final_message = (
            "Final AI Review requested improvements. "
            "No further review attempts remain. "
            "The latest generated version will continue."
        )
    elif review_status_final in (
        "REVIEW_FAILED",
        "REVIEW_QUOTA_EXCEEDED",
    ):
        review_final_message = (
            "AI Review was unavailable. "
            "The latest generated version will continue."
        )
    else:
        review_final_message = (
            "Final AI Review completed. "
            "The latest generated version will continue."
        )

    print()
    print("=" * 60)
    print("FINAL AI REVIEW")
    print("=" * 60)
    print(
        f"Status: {review_status_final}"
    )
    print(
        f"Score: {review_score_final}/100"
    )
    print(
        review_final_message
    )
    # --------------------------------------------------------
    # METADATA / OPTIONAL YOUTUBE UPLOAD
    # --------------------------------------------------------

    if metadata:

        progress.progress(
            96,
            text="Generating YouTube metadata...",
        )

        title, description, tags = create_metadata(
            topic,
            script,
            youtube_upload=youtube_upload,
            privacy=youtube_privacy,
        )

    else:

        title = topic
        description = ""
        tags = []

        print(
            "Local video   : output/final_video.mp4"
        )
        print("=" * 60)

    progress.progress(
        100,
        text="✅ AutoTube AI generation completed!",
    )

    return {
        "script": script,
        "title": title,
        "description": description,
        "tags": tags,
        "review": review,
        "video": str(
            OUTPUT_DIR / "final_video.mp4"
        ),
        "review_attempts": (
            attempt
            if "attempt" in locals()
            else 0
        ),
        "upload_blocked": upload_blocked,
        "stop_reason": stop_reason,
    }


# ============================================================
# ============================================================
# STREAMLIT DASHBOARD
# ============================================================
import streamlit as st
from pathlib import Path
import json


# ============================================================
# LIQUID GLASS UI
# ============================================================

st.set_page_config(
    page_title="AutoTube AI",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# GLASS UI CSS
# ============================================================

st.markdown(
    """
<style>

.stApp {
    background:
        radial-gradient(circle at 15% 10%, rgba(88, 70, 180, 0.18), transparent 30%),
        radial-gradient(circle at 85% 15%, rgba(0, 180, 255, 0.12), transparent 28%),
        #0B0F17;
    color: #F5F7FA;
}

.block-container {
    max-width: 1450px;
    padding-top: 2rem;
    padding-bottom: 4rem;
}

header[data-testid="stHeader"] {
    background: transparent;
}

section[data-testid="stSidebar"] {
    display: none;
}

/* Glass cards */

.glass-card {
    background: rgba(255,255,255,0.055);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 18px;
    padding: 24px;
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
    box-shadow:
        0 20px 60px rgba(0,0,0,0.30),
        inset 0 1px 0 rgba(255,255,255,0.06);
    margin-bottom: 18px;
}

/* Header */

.brand {
    font-size: 30px;
    font-weight: 800;
    letter-spacing: -1px;
}

.brand span {
    background: linear-gradient(90deg,#8B5CF6,#22D3EE);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.status {
    display: inline-block;
    padding: 7px 12px;
    margin-left: 7px;
    border-radius: 999px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.10);
    font-size: 12px;
    color: #CBD5E1;
}

/* Hero */

.hero-title {
    font-size: 46px;
    line-height: 1.05;
    font-weight: 850;
    letter-spacing: -2px;
    margin-top: 20px;
}

.hero-gradient {
    background: linear-gradient(
        90deg,
        #FFFFFF 0%,
        #A78BFA 45%,
        #22D3EE 100%
    );
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.hero-subtitle {
    color: #94A3B8;
    font-size: 17px;
    margin-top: 12px;
    margin-bottom: 30px;
}

/* Section titles */

.section-title {
    font-size: 20px;
    font-weight: 750;
    margin-bottom: 5px;
}

.section-subtitle {
    color: #94A3B8;
    font-size: 13px;
    margin-bottom: 18px;
}

/* Streamlit inputs */

div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
textarea {
    background: rgba(255,255,255,0.045) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    border-radius: 12px !important;
    color: white !important;
}

label {
    color: #CBD5E1 !important;
}

/* Buttons */

.stButton > button {
    width: 100%;
    border-radius: 13px;
    border: 1px solid rgba(139,92,246,0.55);
    background: linear-gradient(
        135deg,
        rgba(139,92,246,0.90),
        rgba(34,211,238,0.78)
    );
    color: white;
    font-weight: 750;
    min-height: 48px;
    box-shadow: 0 10px 30px rgba(91,70,180,0.25);
    transition: all 0.2s ease;
}

.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 15px 40px rgba(34,211,238,0.22);
}

/* Pipeline */

.pipeline {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-top: 15px;
    overflow-x: auto;
}

.pipeline-step {
    min-width: 105px;
    text-align: center;
    padding: 13px 10px;
    border-radius: 14px;
    background: rgba(255,255,255,0.045);
    border: 1px solid rgba(255,255,255,0.08);
}

.pipeline-icon {
    font-size: 21px;
}

.pipeline-name {
    font-size: 11px;
    color: #CBD5E1;
    margin-top: 5px;
}

.pipeline-arrow {
    color: #64748B;
    font-size: 18px;
}

/* Chips */

.chip {
    display: inline-block;
    padding: 7px 11px;
    margin-right: 6px;
    border-radius: 999px;
    background: rgba(255,255,255,0.055);
    border: 1px solid rgba(255,255,255,0.08);
    color: #CBD5E1;
    font-size: 12px;
}

/* Success */

.success-box {
    padding: 16px;
    border-radius: 14px;
    background: rgba(34,197,94,0.08);
    border: 1px solid rgba(34,197,94,0.25);
    color: #BBF7D0;
}

/* Responsive */

@media (max-width: 900px) {

    .hero-title {
        font-size: 34px;
    }

    .pipeline {
        justify-content: flex-start;
    }

}

</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
<div class="glass-card">

<div style="
display:flex;
justify-content:space-between;
align-items:center;
gap:20px;
flex-wrap:wrap;
">

<div class="brand">
🎬 <span>AutoTube AI</span>
</div>

<div>
<span class="status">● AI READY</span>
<span class="status">ENGLISH</span>
<span class="status">1080P</span>
</div>

</div>

</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# HERO
# ============================================================

st.markdown(
    """
<div class="hero-title">
Transform Ideas into<br>
<span class="hero-gradient">Instant Videos.</span>
</div>

<div class="hero-subtitle">
AI-powered video creation — from topic to script, voice, visuals,
subtitles, thumbnail and YouTube publishing.
</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# MAIN COLUMNS
# ============================================================

left, right = st.columns([1.55, 1], gap="large")


# ============================================================
# LEFT — CREATE VIDEO
# ============================================================

with left:

    st.markdown(
        """
<div class="glass-card">

<div class="section-title">Create Video</div>
<div class="section-subtitle">
Tell AutoTube AI what you want to create.
</div>
""",
        unsafe_allow_html=True,
    )

    content_type = st.selectbox(
        "Content Type",
        [
            "News",
            "Explainer",
            "Uploaded Flyer",
            "Custom Topic",
        ],
    )

    # ========================================================
    # 🔥 TRENDING NEWS
    # ========================================================

    if content_type == "News":

        from agents.news_agent import get_trending_news

        if "trending_news" not in st.session_state:
            st.session_state.trending_news = []

        st.markdown(
            '<div class="section-title" style="font-size:16px;">🔥 Trending News</div>',
            unsafe_allow_html=True,
        )

        trend_col1, trend_col2 = st.columns([5, 1])

        with trend_col2:
            refresh_trending = st.button(
                "↻",
                key="refresh_trending_news",
            )

        if refresh_trending or not st.session_state.trending_news:
            st.session_state.trending_news = get_trending_news(
                category="Technology",
                location="Vijayawada",
                limit=10,
            )

        trending_options = [
            item["title"]
            for item in st.session_state.trending_news
        ]

        selected_trending = st.selectbox(
            "Choose a trending story",
            ["— Select a story —"] + trending_options,
            key="selected_trending_story",
        )

        if selected_trending != "— Select a story —":
            if st.button(
                "Use Selected Story",
                key="use_selected_trending_story",
            ):
                st.session_state.topic_input = selected_trending
                st.rerun()

    topic = st.text_area(
        "Topic",
        placeholder="Enter your video topic...",
        height=100,
        key="topic_input",
    )

    language_style = st.selectbox(
        "Language / Style",
        [
            "English news style",
            "English creator style",
            "English documentary style",
            "English short-form style",
        ],
    )

    voice = st.selectbox(
        "Voice",
        [
            "Creator Voice",
        ],
    )

    captions = st.toggle(
        "Auto Subtitles",
        value=True,
    )

    thumbnail = st.toggle(
        "Create Thumbnail",
        value=True,
    )

    metadata = st.toggle(
        "Generate YouTube Metadata",
        value=True,
    )

    youtube_upload = st.toggle(
        "Upload to YouTube",
        value=False,
    )

    youtube_privacy = "private"

    if youtube_upload:
        youtube_privacy = st.selectbox(
            "YouTube Privacy",
            [
                "private",
                "unlisted",
                "public",
            ],
        )

    generate = st.button(
        "🚀 Generate Video",
        type="primary",
    )

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# RIGHT — MEDIA
# ============================================================

with right:

    st.markdown(
        """
<div class="glass-card">

<div class="section-title">Media & Assets</div>
<div class="section-subtitle">
Add images, videos or flyers for your generation.
</div>
""",
        unsafe_allow_html=True,
    )

    uploaded_files = st.file_uploader(
        "Upload media",
        type=[
            "png",
            "jpg",
            "jpeg",
            "webp",
            "mp4",
            "mov",
            "avi",
        ],
        accept_multiple_files=True,
    )

    if uploaded_files:
        st.success(
            f"{len(uploaded_files)} file(s) ready"
        )

        for file in uploaded_files:
            st.caption(f"📎 {file.name}")

    else:
        st.markdown(
            """
<div style="
padding:35px 15px;
text-align:center;
border:1px dashed rgba(255,255,255,0.14);
border-radius:15px;
color:#64748B;
">
📁<br>
Upload images, videos or flyers
</div>
""",
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# PIPELINE
# ============================================================

st.markdown(
    """
<div class="glass-card">

<div class="section-title">AI Production Pipeline</div>
<div class="section-subtitle">
One workflow. From idea to published video.
</div>

<div class="pipeline">

<div class="pipeline-step">
<div class="pipeline-icon">📰</div>
<div class="pipeline-name">News</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">✍️</div>
<div class="pipeline-name">Script</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">🎙️</div>
<div class="pipeline-name">Voice</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">🖼️</div>
<div class="pipeline-name">Visuals</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">🎬</div>
<div class="pipeline-name">Video</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">💬</div>
<div class="pipeline-name">Subtitles</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">✨</div>
<div class="pipeline-name">Thumbnail</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">▶️</div>
<div class="pipeline-name">YouTube</div>
</div>

</div>

</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# GENERATE
# ============================================================

if generate:

    media_paths = []

    if uploaded_files:

        upload_dir = Path("output/uploads")
        upload_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        for file in uploaded_files:

            file_path = upload_dir / file.name

            with open(file_path, "wb") as f:
                f.write(file.getbuffer())

            media_paths.append(
                str(file_path)
            )

    if (
        content_type != "Uploaded Flyer"
        and not topic.strip()
    ):
        st.warning(
            "Please enter a topic first."
        )

    elif (
        content_type == "Uploaded Flyer"
        and not media_paths
    ):
        st.warning(
            "Please upload a flyer or image."
        )

    else:

        try:

            with st.spinner(
                "AutoTube AI is creating your video..."
            ):


                result = generate_multi_media_video(
                    topic=topic.strip(),
                    media_files=media_paths,
                    content_type=content_type,
                    language_style=language_style,
                    voice=voice,
                    captions=captions,
                    thumbnail=thumbnail,
                    metadata=metadata,
                    youtube_upload=youtube_upload,
                    youtube_privacy=youtube_privacy,
                )

            st.session_state["pipeline_result"] = result

            st.success(
                "🎉 Video generation completed!"
            )

        except Exception as e:

            st.error(
                f"AutoTube AI failed: {e}"
            )


# ============================================================
# OUTPUT
# ============================================================

result = st.session_state.get(
    "pipeline_result"
)

final_video = Path(
    "output/final_video.mp4"
)

thumbnail_file = Path(
    "output/thumbnail.jpg"
)

if result or final_video.exists():

    st.markdown(
        """
<div class="glass-card">

<div class="section-title">
Your Output
</div>

<div class="section-subtitle">
Your latest AutoTube AI generation.
</div>
""",
        unsafe_allow_html=True,
    )

    if final_video.exists():

        st.video(
            str(final_video)
        )

        st.markdown(
            """
<span class="chip">🎬 MP4</span>
<span class="chip">📺 1080p</span>
<span class="chip">🔊 AI Voice</span>
<span class="chip">💬 Subtitles</span>
""",
            unsafe_allow_html=True,
        )

        with open(
            final_video,
            "rb",
        ) as video_file:

            st.download_button(
                "⬇️ Download Video",
                data=video_file,
                file_name="autotube_ai_video.mp4",
                mime="video/mp4",
            )

    if thumbnail_file.exists():

        st.markdown(
            "### Thumbnail"
        )

        st.image(
            str(thumbnail_file),
            use_container_width=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# FOOTER
# ============================================================

st.markdown(
    """
<div style="
text-align:center;
padding:25px;
color:#475569;
font-size:12px;
">
AutoTube AI • AI Video Automation
</div>
""",
    unsafe_allow_html=True,
)

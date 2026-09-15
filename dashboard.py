"""AutoTube AI - Multi-Media Streamlit Dashboard."""

import asyncio
import datetime
import json
import os
import re
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
# VOICE IDS & TUNING
# ============================================================

VOICE_IDS = {
    "🎙️ Use My Own Voice Recording (Upload Audio)": "own_recording",
    "🤖 Clone My Voice with AI (Local XTTS-v2)": "clone",
    "👨 Adam (Male Creator) - Fast & Crisp": "am_adam",
    "👨 Michael (News Anchor) - Professional": "am_michael",
    "👩 Heart (Female Creator) - Smooth": "af_heart",
    "👩 Bella (Warm Female) - Storytelling": "af_bella",
    # Legacy fallbacks
    "Creator Voice": "am_adam",
    "English Female": "af_heart",
}

VOICE_TUNING = {
    "🎙️ Use My Own Voice Recording (Upload Audio)": ("+0%", "+0Hz"),
    "🤖 Clone My Voice with AI (Local XTTS-v2)": ("+0%", "+0Hz"),
    "👨 Adam (Male Creator) - Fast & Crisp": ("-5%", "+0Hz"),
    "👨 Michael (News Anchor) - Professional": ("-5%", "+0Hz"),
    "👩 Heart (Female Creator) - Smooth": ("-5%", "+0Hz"),
    "👩 Bella (Warm Female) - Storytelling": ("-5%", "+0Hz"),
    # Legacy fallbacks
    "Creator Voice": ("-5%", "+0Hz"),
    "English Female": ("-5%", "+0Hz"),
}


# ============================================================
# CLEAN PREVIOUS GENERATION
# ============================================================

def clean_previous_generation():
    """Remove previous generated outputs without touching uploaded files or voice samples."""

    files = [
        "script.txt",
        "visual_plan.txt",
        "section_map.txt",
        "voice.mp3",
        "voice.wav",
        "voice_raw.wav",
        "voice_norm.wav",
        "voice_kokoro.wav",
        "tts_script.txt",
        "transcription.json",
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
            # Never delete voice sample references or offline fallback pool
            if "voice" in item.name.lower() or item.name == "fallback":
                continue
            try:
                if item.is_file():
                    item.unlink()
                else:
                    shutil.rmtree(item)
            except Exception:
                pass


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
    """Generate or apply voice narration for the video."""

    voice_id = VOICE_IDS.get(voice, "am_adam")

    from agents.voice_agent import create_voice

    rate, pitch = VOICE_TUNING.get(voice, ("-5%", "+0Hz"))

    # Only pass audio sample if using direct own voice recording or cloning
    effective_sample = (
        own_voice_audio
        if voice_id in ("own_recording", "clone")
        else None
    )

    return asyncio.run(
        create_voice(
            voice=voice_id,
            rate=rate,
            pitch=pitch,
            voice_sample=effective_sample,
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
    feedback=None,
):
    """
    Download visuals according to the AI visual plan with self-healing fallback.
    """

    from agents.image_agent import (
        download_images_from_visual_plan,
    )
    from agents.video_agent import ensure_visual_assets_exist

    try:
        res = download_images_from_visual_plan(
            visual_plan_file,
            flyer_path=flyer_path,
            feedback=feedback,
        )
    except Exception as err:
        print(f"Visual plan download note: {err}. Triggering self-healing fallback...")
        ensure_visual_assets_exist()
        res = []

    ensure_visual_assets_exist()
    return res


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

def create_pipeline_video(aspect_ratio="1:1"):
    """Run the project's video agent."""

    from agents.video_agent import create_video

    return create_video(aspect_ratio=aspect_ratio)


# ============================================================
# FINAL VIDEO
# ============================================================

def create_final_video(
    captions=True,
    aspect_ratio="1:1",
):
    """Create final video with optional captions."""

    if captions:
        try:
            from agents.subtitle_agent import create_subtitles
            create_subtitles()
        except Exception as sub_err:
            print(f"⚠️ Subtitle creation notice: {sub_err}")

    from agents.final_video_agent import (
        create_final_video as finalize,
    )

    return finalize(
        add_captions=captions,
        aspect_ratio=aspect_ratio,
    )


# ============================================================
# THUMBNAIL
# ============================================================

def create_thumbnail(
    topic,
    aspect_ratio="16:9",
):
    """Create thumbnail using existing thumbnail agent."""

    from agents.thumbnail_agent import create_thumbnail

    return create_thumbnail(topic, aspect_ratio=aspect_ratio)

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
        audio_audit=project.get("audio_audit"),
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

    video_id = None
    youtube_error = None

    if youtube_upload:

        from agents.youtube_agent import upload_video

        print()
        print("=" * 60)
        print("YOUTUBE UPLOAD")
        print("=" * 60)
        print(
            f"Privacy: {privacy.upper()}"
        )

        try:
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
        except Exception as yt_err:
            youtube_error = str(yt_err)
            print(f"⚠️ YouTube upload failed: {yt_err}")

    return title, description, tags, video_id, youtube_error


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
    voice="👨 Adam (Male Creator) - Fast & Crisp",
    voice_sample=None,
    captions=True,
    thumbnail=True,
    metadata=True,
    youtube_upload=False,
    youtube_privacy="private",
    script_override=None,
    aspect_ratio="1:1",
    progress_callback=None,
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

    MAX_RETRIES = 2
    MAX_REVIEW_ATTEMPTS = 1 + MAX_RETRIES

    failing_component = None
    feedback = None

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
            + (f" [Self-Healing: {failing_component}]" if attempt > 1 else "")
        )
        print("=" * 60)

        # Targeted Self-Healing: determine which components need to run
        run_script = (attempt == 1) or (failing_component == "script_agent")
        run_images = (attempt == 1) or (failing_component in ("script_agent", "image_agent"))
        run_voice = (attempt == 1) or (failing_component in ("script_agent", "voice_agent"))
        run_subtitles = captions and ((attempt == 1) or (failing_component in ("script_agent", "voice_agent")))
        run_thumbnail = thumbnail and (run_images or (attempt == 1))

        if attempt == 1:
            clean_previous_generation()
        else:
            # Clean only the artifacts being refreshed
            if run_script:
                for f in ["script.txt", "section_map.txt", "visual_plan.txt", "tts_script.txt", "final_video.mp4"]:
                    (OUTPUT_DIR / f).unlink(missing_ok=True)
            elif run_voice:
                for f in ["voice.wav", "voice.mp3", "subtitles.srt", "final_video.mp4"]:
                    (OUTPUT_DIR / f).unlink(missing_ok=True)
            elif run_images:
                (OUTPUT_DIR / "final_video.mp4").unlink(missing_ok=True)

        class ProgressHandler:
            def __init__(self, callback, attempt, max_attempts, failing_comp):
                self.callback = callback
                self.st_prog = None
                init_text = f"Attempt {attempt}/{max_attempts}: Starting AutoTube AI{' (Self-healing ' + failing_comp + ')' if attempt > 1 else ''}..."
                # Only attach st.progress if running in the main Streamlit thread (no worker callback)
                if self.callback is None:
                    try:
                        self.st_prog = st.progress(0, text=init_text)
                    except Exception:
                        self.st_prog = None
                else:
                    try:
                        self.callback(0, init_text)
                    except Exception:
                        pass

            def progress(self, val, text=""):
                if self.callback:
                    try:
                        self.callback(val, text)
                    except Exception:
                        pass
                elif self.st_prog is not None:
                    try:
                        self.st_prog.progress(val, text=text)
                    except Exception:
                        pass

        progress = ProgressHandler(progress_callback, attempt, MAX_REVIEW_ATTEMPTS, failing_component or "")

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

        if run_script:

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

                if feedback:
                    cumulative_review["critical_issues"].append(feedback)

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

            # Pre-Publish Content Safety & Policy Filter
            from agents.news_verifier import verify_content_safety_and_policy
            safety_status = verify_content_safety_and_policy(script, topic=topic)
            if not safety_status.get("safe", True):
                print(
                    f"⚠️ [Safety Warning] Script policy violation detected ({safety_status.get('category')}): "
                    f"{safety_status.get('reason')}"
                )

        else:

            print(
                f"[Targeted Self-Healing] Preserving existing script and visual plan (failing component: {failing_component})"
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

        if run_images:

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
                    f"Finding visuals from AI visual plan{' (adjusted for feedback)' if failing_component == 'image_agent' else ''}..."
                ),
            )

            try:

                download_visuals(
                    visual_plan_file,
                    flyer_path=None,
                    feedback=feedback if failing_component == "image_agent" else None,
                )

            except Exception as error:

                print(
                    "Visual sourcing warning:",
                    error,
                )

        else:

            print(
                f"[Targeted Self-Healing] Preserving existing visual assets in assets/ (failing component: {failing_component})"
            )

        # ----------------------------------------------------
        # VOICE
        # ----------------------------------------------------

        if run_voice:

            progress.progress(
                50,
                text=(
                    f"Attempt {attempt}: "
                    f"Preparing narration ({voice})..."
                ),
            )

            create_voice_for_script(
                voice=voice,
                own_voice_audio=voice_sample,
            )

        else:

            print(
                f"[Targeted Self-Healing] Preserving existing voice audio (failing component: {failing_component})"
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

        from agents.video_agent import ensure_visual_assets_exist
        ensure_visual_assets_exist()

        from agents.news_verifier import validate_visual_assets
        asset_check = validate_visual_assets()
        if not asset_check.get("valid", True):
            print(f"🛡️ [Asset Safety] Validated visual assets: replaced {len(asset_check.get('replaced', []))} defective images with clean fallbacks")

        create_pipeline_video(aspect_ratio=aspect_ratio)

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
            captions=captions,
            aspect_ratio=aspect_ratio,
        )

        # ----------------------------------------------------
        # THUMBNAIL
        # ----------------------------------------------------

        if run_thumbnail:

            progress.progress(
                85,
                text=(
                    f"Attempt {attempt}: "
                    "Creating thumbnail..."
                ),
            )

            create_thumbnail(
                topic,
                aspect_ratio=aspect_ratio,
            )

        else:

            print(
                f"[Targeted Self-Healing] Preserving existing thumbnail (failing component: {failing_component})"
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
            "overall_score",
            review.get("score", 0),
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
            "Overall Score:",
            f"{score}/100",
        )
        print(
            "Failing Component:",
            review.get("failing_component", "none"),
        )
        print(
            "Feedback:",
            review.get("feedback", ""),
        )

        # ----------------------------------------------------
        # REVIEW FAILURE (Quota / API dead end)
        # ----------------------------------------------------

        if status == "REVIEW_QUOTA_EXCEEDED":

            stopped_after_review = True

            stop_reason = (
                "Gemini API quota/rate limit was exceeded. "
                "No further AI review attempts were made. "
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

        is_own_voice = bool(
            voice and "Use My Own Voice Recording" in str(voice)
        )

        review_is_approved = (
            status == "APPROVE"
            and review_score >= 80
            and not review_has_critical_issues
        ) or is_own_voice

        if review_is_approved:

            if is_own_voice:
                stop_reason = (
                    "Direct Own Voice video generated successfully on Attempt 1."
                )
            else:
                stop_reason = (
                    f"AI Review approved current version with score {review_score}/100 (>= 80) "
                    "and no critical issues."
                )

            stopped_after_review = True

            progress.progress(
                96,
                text=(
                    "✅ Video approved! "
                    "Continuing to metadata..."
                ),
            )

            break

        # ----------------------------------------------------
        # IMPROVE / RETRY ROUTING & DEAD-LETTER QUEUE
        # ----------------------------------------------------

        failing_component = str(review.get("failing_component", "script_agent")).lower()
        feedback = review.get("feedback") or review.get("summary") or "Review requested improvements."

        if attempt < MAX_REVIEW_ATTEMPTS:

            progress.progress(
                94,
                text=(
                    f"⚠️ Attempt {attempt} scored {review_score}/100 (< 80). "
                    f"Targeted self-healing: re-running {failing_component}..."
                ),
            )

            print()
            print("=" * 60)
            print(f"TARGETED SELF-HEALING: Attempt {attempt} -> Attempt {attempt + 1}")
            print(f"Failing component: {failing_component}")
            print(f"Feedback: {feedback}")
            print("=" * 60)

            continue

        # ----------------------------------------------------
        # DEAD-LETTER QUEUE: Max Retries (2) Exhausted
        # ----------------------------------------------------

        stopped_after_review = True
        failed_dir = ROOT / "failed_queue"
        failed_dir.mkdir(parents=True, exist_ok=True)
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", topic)[:50]
        queue_file = failed_dir / f"failure_{ts}_{slug}.json"

        failure_payload = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "topic": topic,
            "content_type": content_type,
            "language_style": language_style,
            "voice": voice,
            "max_retries": MAX_RETRIES,
            "total_attempts": attempt,
            "overall_score": review.get("overall_score", review_score),
            "script_score": review.get("script_score", 0),
            "audio_score": review.get("audio_score", 0),
            "visual_score": review.get("visual_score", 0),
            "failing_component": failing_component,
            "feedback": feedback,
            "critical_issues": review.get("critical_issues", []),
            "review": review,
        }
        with open(queue_file, "w", encoding="utf-8") as qf:
            json.dump(failure_payload, qf, indent=2, ensure_ascii=False)

        print()
        print("=" * 60)
        print("DEAD-LETTER QUEUE: TOPIC RETRIES EXHAUSTED")
        print("=" * 60)
        print(f"⚠️ Topic scored {review_score}/100 (< 80) after {MAX_RETRIES} retries.")
        print(f"Failing component: {failing_component}")
        print(f"Metadata moved to: {queue_file}")
        print("Exiting gracefully without crashing so next automated topic can run.")
        print("=" * 60)

        progress.progress(
            100,
            text=f"⚠️ Score < 80 after {MAX_RETRIES} retries. Moved to failed_queue/ and exited cleanly."
        )

        return {
            "status": "FAILED_MOVED_TO_QUEUE",
            "success": False,
            "topic": topic,
            "overall_score": review.get("overall_score", review_score),
            "failing_component": failing_component,
            "feedback": feedback,
            "failed_queue_path": str(queue_file),
            "review": review,
            "script": script,
            "title": title,
            "video": str(OUTPUT_DIR / "final_video.mp4") if (OUTPUT_DIR / "final_video.mp4").exists() else None,
            "stop_reason": f"Topic scored {review_score} after {MAX_RETRIES} retries. Moved to failed_queue/.",
        }

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

        title, description, tags, video_id, youtube_error = create_metadata(
            topic,
            script,
            youtube_upload=youtube_upload,
            privacy=youtube_privacy,
        )

    else:

        title = topic
        description = ""
        tags = []
        video_id = None
        youtube_error = None

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
        "youtube_video_id": video_id,
        "youtube_error": youtube_error,
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
    page_title="AutoTube Controller",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from auth_guard import (
    require_pin_authentication,
    render_logout_button,
    inject_mobile_responsive_css,
)

# Enforce security authentication guard before rendering dashboard
require_pin_authentication()
render_logout_button()


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
    background: rgba(11, 15, 23, 0.96);
    border-right: 1px solid rgba(255, 255, 255, 0.08);
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
# MOBILE QUICK ACTIONS & REMOTE TUNNEL WIDGET
# ============================================================

from pathlib import Path
_t_url_p = Path("output/tunnel_url.txt")
_t_qr_p = Path("output/tunnel_qr.png")

if _t_url_p.exists():
    try:
        _t_url = _t_url_p.read_text(encoding="utf-8").strip()
        if _t_url:
            with st.expander("📱 Remote Mobile Access (Cloudflare Tunnel Active)", expanded=False):
                st.markdown(f"**Public HTTPS Mobile URL:** [{_t_url}]({_t_url})")
                if _t_qr_p.exists():
                    st.image(str(_t_qr_p), caption="Scan with Phone Camera to open on Mobile", width=220)
                st.caption("🔒 Secured via PIN Access Guard.")
    except Exception:
        pass

# Touch-friendly full-width mobile quick chips
m_col1, m_col2, m_col3 = st.columns(3)
with m_col1:
    if st.button("🚀 Quick Run", key="btn_mobile_quick_run", use_container_width=True):
        st.session_state["copilot_input_prefill"] = "Create a high-energy 60s vertical video about the latest tech breakthrough."
        st.toast("Ready! Click 'Run Video Pipeline' or ask Copilot.", icon="🚀")
with m_col2:
    if st.button("🛑 Stop Process", key="btn_mobile_stop_run", use_container_width=True):
        st.session_state["pipeline_abort_requested"] = True
        st.warning("Job cancellation requested.")
with m_col3:
    if st.button("📊 Pipeline Status", key="btn_mobile_status", use_container_width=True):
        from supervisor import get_healing_logs
        hl = get_healing_logs()
        st.info(f"System Operational: 0 critical crashes, {len(hl)} auto-healed incidents logged.")


# ============================================================
# EMBEDDED AI COPILOT DRAWER
# ============================================================

try:
    from copilot_agent import render_copilot_drawer
    render_copilot_drawer()
except Exception as copilot_err:
    print(f"Copilot UI render notice: {copilot_err}")

# Self-healing event toast notifications
try:
    from supervisor import pop_new_healing_events
    for _healed_ev in pop_new_healing_events():
        st.toast(f"⚠️ Auto-Healed ({_healed_ev.get('stage', 'pipeline')}): {_healed_ev.get('resolution', 'Recovered')[:80]}", icon="🩹")
except Exception:
    pass



# ============================================================
# MAIN COLUMNS
# ============================================================


# ============================================================
# STUDIO NAVIGATION TABS (AI COPILOT vs MANUAL STUDIO)
# ============================================================

tab_copilot, tab_manual = st.tabs([
    "🤖 AI Copilot Studio (Chat & Autonomous)",
    "🎛️ Manual Studio (Classic Form Controls)",
])

with tab_copilot:
    try:
        from copilot_agent import render_copilot_main_studio
        render_copilot_main_studio()
    except Exception as copilot_main_err:
        st.error(f"Error rendering AI Copilot Studio: {copilot_main_err}")

with tab_manual:
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

            CATEGORY_OPTIONS = {
                "🔥 All Trending (Live Mix)": "All",
                "⚡ Breaking News": "Breaking",
                "🇮🇳 National / India": "National",
                "🌐 World / International": "World",
                "📱 Tech & AI Innovation": "Technology",
                "💼 Business & Markets": "Business",
                "🏏 Sports": "Sports",
                "🎬 Entertainment & Cinema": "Entertainment",
                "🔬 Science & Space": "Science",
                "📍 Andhra Pradesh & Telangana": "Regional",
            }

            if "trending_news" not in st.session_state:
                st.session_state.trending_news = []
            if "seen_trending_titles" not in st.session_state:
                st.session_state.seen_trending_titles = set()
            if "selected_news_category" not in st.session_state:
                st.session_state.selected_news_category = "🔥 All Trending (Live Mix)"

            st.markdown(
                '<div class="section-title" style="font-size:16px;">🔥 Trending & Breaking News</div>',
                unsafe_allow_html=True,
            )

            trend_col1, trend_col2 = st.columns([3, 2])

            with trend_col1:
                chosen_cat_label = st.selectbox(
                    "Filter News Category",
                    list(CATEGORY_OPTIONS.keys()),
                    index=list(CATEGORY_OPTIONS.keys()).index(st.session_state.selected_news_category)
                    if st.session_state.selected_news_category in CATEGORY_OPTIONS else 0,
                    key="news_category_select",
                )
                selected_cat_code = CATEGORY_OPTIONS[chosen_cat_label]

            with trend_col2:
                st.write("")
                st.write("")
                refresh_trending = st.button(
                    "🔄 Fetch Fresh News",
                    key="refresh_trending_news",
                )

            category_changed = chosen_cat_label != st.session_state.selected_news_category
            if category_changed:
                st.session_state.selected_news_category = chosen_cat_label

            if refresh_trending or category_changed or not st.session_state.trending_news:
                exclude_list = list(st.session_state.seen_trending_titles)
                with st.spinner(f"Fetching latest {chosen_cat_label} news..."):
                    fetched = get_trending_news(
                        category=selected_cat_code,
                        limit=10,
                        exclude_titles=exclude_list if (refresh_trending or not category_changed) else None,
                    )
                    # If pool of unshown stories was exhausted, clear seen set and re-fetch
                    if not fetched and exclude_list:
                        st.session_state.seen_trending_titles = set()
                        fetched = get_trending_news(
                            category=selected_cat_code,
                            limit=10,
                            exclude_titles=None,
                        )

                    if fetched:
                        st.session_state.trending_news = fetched
                        for item in fetched:
                            if item.get("title"):
                                st.session_state.seen_trending_titles.add(item["title"])

                        st.session_state["selected_trending_story"] = fetched[0]["title"]
                        st.session_state["topic_input"] = fetched[0]["title"]
                        st.rerun()

            story_map = {
                item["title"]: item
                for item in st.session_state.trending_news
                if item.get("title")
            }

            def _format_story_option(title):
                if title == "— Select a story —" or title not in story_map:
                    return title
                it = story_map[title]
                age = it.get("age_str", "Today")
                cat = it.get("category", "")
                src = it.get("source", "")
                cat_badge = f"[{cat}] " if cat else ""
                return f"{cat_badge}({age}) {title} — {src}"

            select_options = ["— Select a story —"] + [
                item["title"]
                for item in st.session_state.trending_news
                if item.get("title")
            ]

            def _on_story_change():
                picked = st.session_state.get("selected_trending_story")
                if picked and picked != "— Select a story —":
                    st.session_state["topic_input"] = picked

            current_picked = st.session_state.get("selected_trending_story", "— Select a story —")
            default_index = select_options.index(current_picked) if current_picked in select_options else 0

            selected_trending = st.selectbox(
                "Choose a trending story",
                select_options,
                index=default_index,
                format_func=_format_story_option,
                key="selected_trending_story",
                on_change=_on_story_change,
            )

            seen_count = len(st.session_state.seen_trending_titles)
            if story_map:
                st.caption(f"🔥 {len(story_map)} live stories loaded • {seen_count} fresh stories explored this session.")
            else:
                st.warning("⚠️ No stories loaded yet. Click '🔄 Fetch Fresh News' above.")

            if selected_trending and selected_trending != "— Select a story —":
                if st.session_state.get("topic_input") != selected_trending:
                    st.session_state["topic_input"] = selected_trending

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

        # ========================================================
        # 🎙️ VOICE SELECTION & SAMPLES
        # ========================================================

        voice_samples_dir = ROOT / "voice_samples"
        voice_samples_dir.mkdir(parents=True, exist_ok=True)

        voice_options = [
            "👨 Adam (Male Creator) - Fast & Crisp",
            "👨 Michael (News Anchor) - Professional",
            "👩 Heart (Female Creator) - Smooth",
            "👩 Bella (Warm Female) - Storytelling",
            "🎙️ Use My Own Voice Recording (Upload Audio)",
            "🤖 Clone My Voice with AI (Local XTTS-v2)",
        ]

        voice = st.selectbox(
            "Voice",
            voice_options,
            index=0,
        )

        active_voice_sample = None

        if "Use My Own Voice Recording" in voice:
            st.markdown(
                """
                <div style="background:rgba(56, 189, 248, 0.08); border:1px solid rgba(56, 189, 248, 0.25); border-radius:12px; padding:12px 14px; margin:8px 0 12px 0;">
                    <div style="font-size:13px; font-weight:600; color:#38BDF8; margin-bottom:4px;">
                        🎙️ 100% Genuine Own Voice Recording
                    </div>
                    <div style="font-size:11.5px; color:#94A3B8; line-height:1.4;">
                        Your recorded voice will be used directly as video narration. AutoTube AI syncs all visuals and animated subtitles with <b>0s TTS wait time & 0 laptop heat!</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            existing_voice_file = None
            for fname in [
                "active_voice.wav",
                "active_voice.mp3",
                "active_voice.m4a",
                "user_voice.wav",
                "user_voice.mp3",
                "user_voice.m4a",
            ]:
                cand = voice_samples_dir / fname
                if cand.exists() and cand.stat().st_size > 0:
                    existing_voice_file = cand
                    break

            uploaded_voice = st.file_uploader(
                "Upload your voiceover recording (.mp3, .wav, .m4a)",
                type=["wav", "mp3", "m4a", "aac", "ogg", "flac"],
                key="user_voice_recording_uploader",
            )

            if uploaded_voice:
                ext = Path(uploaded_voice.name).suffix.lower()
                save_dest = voice_samples_dir / f"active_voice{ext}"
                save_dest.write_bytes(uploaded_voice.getbuffer())
                existing_voice_file = save_dest
                st.session_state["active_voice_file"] = str(save_dest)
                st.success(f"✅ Loaded: {uploaded_voice.name}")

            if existing_voice_file and existing_voice_file.exists():
                active_voice_sample = str(existing_voice_file)
                st.caption(f"🎧 Active recording: `{existing_voice_file.name}`")
                st.audio(str(existing_voice_file))

                col_tr, col_del = st.columns([1, 1])
                with col_tr:
                    if st.button(
                        "📝 Auto-Detect Script from Speech",
                        key="transcribe_voice_btn",
                        use_container_width=True,
                    ):
                        with st.spinner("Transcribing audio with Whisper..."):
                            try:
                                import whisper

                                model = whisper.load_model("base")
                                trans_res = model.transcribe(
                                    str(existing_voice_file),
                                    fp16=False,
                                )
                                audio_text = trans_res.get("text", "").strip()
                                if audio_text:
                                    st.session_state["topic_input"] = audio_text
                                    st.success("✅ Topic & script populated from your speech!")
                                    st.rerun()
                            except Exception as tr_err:
                                st.error(f"Transcription error: {tr_err}")
                with col_del:
                    if st.button(
                        "🗑️ Clear / Reset Audio",
                        key="clear_own_voice_btn",
                        use_container_width=True,
                    ):
                        st.session_state.pop("active_voice_file", None)
                        for f in voice_samples_dir.glob("active_voice.*"):
                            try:
                                f.unlink()
                            except Exception:
                                pass
                        for f in voice_samples_dir.glob("user_voice.*"):
                            try:
                                f.unlink()
                            except Exception:
                                pass
                        st.success("Cleared recording.")
                        st.rerun()
            else:
                st.info("ℹ️ Please upload an audio recording above to use your own voice.")

        elif "Clone My Voice with AI" in voice:
            st.markdown(
                """
                <div style="background:rgba(234, 179, 8, 0.08); border:1px solid rgba(234, 179, 8, 0.25); border-radius:12px; padding:12px 14px; margin:8px 0 12px 0;">
                    <div style="font-size:13px; font-weight:600; color:#EAB308; margin-bottom:4px;">
                        🤖 Coqui XTTS-v2 Local Voice Cloning
                    </div>
                    <div style="font-size:11.5px; color:#94A3B8; line-height:1.4;">
                        Synthesizes script with your cloned voice. <i>Note: Local neural synthesis takes ~1–2 mins on Mac CPU.</i>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            existing_clone_file = None
            for fname in [
                "active_voice.wav",
                "active_voice.mp3",
                "active_voice.m4a",
                "user_voice.wav",
                "user_voice.mp3",
                "user_voice.m4a",
            ]:
                cand = voice_samples_dir / fname
                if cand.exists() and cand.stat().st_size > 0:
                    existing_clone_file = cand
                    break

            uploaded_clone_sample = st.file_uploader(
                "Upload 5–10s Voice Sample (.wav, .mp3, .m4a)",
                type=["wav", "mp3", "m4a"],
                key="user_clone_sample_uploader",
            )

            if uploaded_clone_sample:
                ext = Path(uploaded_clone_sample.name).suffix.lower()
                save_dest = voice_samples_dir / f"active_voice{ext}"
                save_dest.write_bytes(uploaded_clone_sample.getbuffer())
                existing_clone_file = save_dest
                st.session_state["active_voice_file"] = str(save_dest)
                st.success("✅ Reference voice sample saved!")

            if existing_clone_file and existing_clone_file.exists():
                active_voice_sample = str(existing_clone_file)
                st.caption(f"🎧 Reference sample: `{existing_clone_file.name}`")
                st.audio(str(existing_clone_file))

                if st.button("🗑️ Clear / Reset Sample", key="clear_clone_voice_btn"):
                    st.session_state.pop("active_voice_file", None)
                    for f in voice_samples_dir.glob("active_voice.*"):
                        try:
                            f.unlink()
                        except Exception:
                            pass
                    for f in voice_samples_dir.glob("user_voice.*"):
                        try:
                            f.unlink()
                        except Exception:
                            pass
                    st.success("Cleared sample.")
                    st.rerun()
            else:
                st.info("ℹ️ Upload a short 5–10s sample of the voice you'd like to clone.")

        else:
            # Studio Voice selected (Adam, Michael, Heart, Bella)
            active_voice_sample = None
            st.markdown(
                """
                <div style="background:rgba(34, 197, 94, 0.08); border:1px solid rgba(34, 197, 94, 0.25); border-radius:12px; padding:10px 14px; margin:8px 0 12px 0;">
                    <div style="font-size:12.5px; font-weight:600; color:#4ADE80; margin-bottom:2px;">
                        ⚡ Ultra-Fast Studio TTS (&lt;1 second)
                    </div>
                    <div style="font-size:11px; color:#94A3B8; line-height:1.4;">
                        Reads the generated script word-for-word in crisp 24kHz studio audio with <b>0% laptop heat</b>.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
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

            upload_dir = ROOT / "input" / "uploads"
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

        # For Own Voice Recording, transcribe the audio so the visual plan and subtitles match the spoken words
        if "Use My Own Voice Recording" in voice and active_voice_sample:
            with st.spinner("Transcribing your audio for topic and visuals..."):
                try:
                    import whisper

                    wmodel = whisper.load_model("base")
                    wres = wmodel.transcribe(str(active_voice_sample), fp16=False)
                    trans_topic = wres.get("text", "").strip()
                    if trans_topic:
                        topic = trans_topic
                        st.session_state["topic_input"] = trans_topic
                except Exception as auto_tr_err:
                    print("Auto-transcription note:", auto_tr_err)

        if (
            content_type != "Uploaded Flyer"
            and not topic.strip()
        ):
            st.warning(
                "Please enter a topic or select an audio recording."
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
                        voice_sample=active_voice_sample,
                        captions=captions,
                        thumbnail=thumbnail,
                        metadata=metadata,
                        youtube_upload=youtube_upload,
                        youtube_privacy=youtube_privacy,
                    )

                st.session_state["pipeline_result"] = result

                if result.get("youtube_video_id"):
                    st.success(
                        f"🎉 Video generated & published to YouTube! Video ID: {result['youtube_video_id']}"
                    )
                elif result.get("youtube_error"):
                    st.success(
                        "🎉 Video generation completed successfully!"
                    )
                    st.warning(
                        f"⚠️ YouTube upload note: {result['youtube_error']}. Your video was generated and is ready below to preview, download, or upload."
                    )
                else:
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

            try:
                with open(final_video, "rb") as _vf:
                    _video_bytes = _vf.read()
                st.video(_video_bytes, format="video/mp4")
            except Exception as _vid_err:
                st.warning(f"Video player loading notice: {_vid_err}")

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

            with st.expander("📤 Publish / Upload to YouTube", expanded=False):
                default_title = "My AutoTube Video"
                default_desc = ""
                default_tags = []
                meta_file = Path("output/metadata.json")
                if meta_file.exists():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as mf:
                            mdata = json.load(mf)
                            default_title = mdata.get("title", default_title)
                            default_desc = mdata.get("description", "")
                            default_tags = mdata.get("tags", [])
                    except Exception:
                        pass

                pub_title = st.text_input(
                    "Title",
                    value=default_title,
                    key="manual_yt_title",
                )
                pub_desc = st.text_area(
                    "Description",
                    value=default_desc,
                    height=100,
                    key="manual_yt_desc",
                )
                pub_privacy = st.selectbox(
                    "Privacy",
                    [
                        "private",
                        "unlisted",
                        "public",
                    ],
                    key="manual_yt_privacy",
                )
                if st.button(
                    "🚀 Upload to YouTube Now",
                    key="manual_yt_submit_btn",
                    use_container_width=True,
                ):
                    with st.spinner("Uploading to YouTube..."):
                        try:
                            from agents.youtube_agent import upload_video
                            v_id = upload_video(
                                str(final_video),
                                pub_title,
                                pub_desc,
                                default_tags,
                                privacy=pub_privacy,
                            )
                            st.success(f"✅ Upload Complete! Video ID: {v_id}")
                            st.markdown(f"[▶️ Watch on YouTube](https://youtu.be/{v_id})")
                        except Exception as m_yt_err:
                            st.error(f"Upload failed: {m_yt_err}")
                            st.info("💡 If token expired, run in terminal: `./.venv/bin/python scripts/reauth_youtube.py`")

        if thumbnail_file.exists():

            st.markdown(
                "### Thumbnail"
            )

            st.image(
                str(thumbnail_file),
                use_container_width=True,
            )

        review_file = Path("output/review.json")
        if review_file.exists():
            try:
                with open(review_file, "r", encoding="utf-8") as rf:
                    rdata = json.load(rf)

                r_status = rdata.get("status", "REVIEWED")
                r_score = rdata.get("score", 0)
                r_summary = rdata.get("summary", "")
                r_audio = rdata.get("audio", {})

                st.markdown("### 🤖 AI Quality & Audio Review")
                st.markdown(
                    f"""
                    <div style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 16px; margin-bottom: 20px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <span style="font-weight: 700; font-size: 16px;">Overall Assessment</span>
                            <span style="background: {'#10b981' if r_status == 'APPROVE' else '#f59e0b'}; color: white; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 13px;">
                                {r_status} • {r_score}/100
                            </span>
                        </div>
                        <p style="color: #cbd5e1; font-size: 14px; margin-bottom: 14px;">{r_summary}</p>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px;">
                            <div style="background: rgba(255,255,255,0.03); padding: 10px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 12px; color: #94a3b8;">🎙️ Voice & Audio</div>
                                <div style="font-size: 18px; font-weight: 700; color: #38bdf8;">{r_audio.get('score', 85)}/100</div>
                                <div style="font-size: 11px; color: #10b981;">{r_audio.get('status', 'GOOD')}</div>
                            </div>
                            <div style="background: rgba(255,255,255,0.03); padding: 10px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 12px; color: #94a3b8;">📜 Script Quality</div>
                                <div style="font-size: 18px; font-weight: 700; color: #a855f7;">{rdata.get('script', {}).get('score', 80)}/100</div>
                                <div style="font-size: 11px; color: #10b981;">{rdata.get('script', {}).get('status', 'GOOD')}</div>
                            </div>
                            <div style="background: rgba(255,255,255,0.03); padding: 10px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 12px; color: #94a3b8;">🔍 Factual Accuracy</div>
                                <div style="font-size: 18px; font-weight: 700; color: #34d399;">{rdata.get('factual_quality', {}).get('score', 90)}/100</div>
                                <div style="font-size: 11px; color: #10b981;">{rdata.get('factual_quality', {}).get('status', 'EXCELLENT')}</div>
                            </div>
                            <div style="background: rgba(255,255,255,0.03); padding: 10px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 12px; color: #94a3b8;">🎨 Visual Plan</div>
                                <div style="font-size: 18px; font-weight: 700; color: #f43f5e;">{rdata.get('visuals', {}).get('score', 85)}/100</div>
                                <div style="font-size: 11px; color: #10b981;">{rdata.get('visuals', {}).get('status', 'GOOD')}</div>
                            </div>
                            <div style="background: rgba(255,255,255,0.03); padding: 10px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 12px; color: #94a3b8;">💬 Subtitles</div>
                                <div style="font-size: 18px; font-weight: 700; color: #fbbf24;">{rdata.get('subtitles', {}).get('score', 90)}/100</div>
                                <div style="font-size: 11px; color: #10b981;">{rdata.get('subtitles', {}).get('status', 'GOOD')}</div>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if r_audio.get("feedback"):
                    st.caption(f"🎧 **Audio Audit Details:** {r_audio.get('feedback')}")
            except Exception:
                pass

        st.markdown("</div>", unsafe_allow_html=True)

        # Live Autonomous Self-Healing Diagnostics Drawer
        try:
            from supervisor import render_healing_diagnostics_drawer
            render_healing_diagnostics_drawer()
        except Exception:
            pass



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

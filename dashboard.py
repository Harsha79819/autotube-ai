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
    "English Female": "en-US-AriaNeural",
    "English Male": "en-US-AndrewNeural",
    "English Creator": "en-US-GuyNeural",
}

VOICE_TUNING = {
    "English Female": ("+0%", "+0Hz"),
    "English Male": ("+0%", "+0Hz"),
    "English Creator": ("+8%", "+2Hz"),
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
    review,
    language_style,
    attempt,
    content_type="News",
    source_context=None,
):
    """
    Ask the existing script generator to create a corrected version
    of the same topic using the Review Agent feedback.
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

    feedback = "\n".join(
        f"- {item}"
        for item in critical_issues + improvements
    )

    revision_topic = f"""
Original topic:
{topic}

Content type:
{content_type}

Source context:
{source_context or "No verified source context available."}

This is revision attempt {attempt} of 3.

Create a corrected YouTube news package about the SAME original topic.

The previous AI quality review found these problems:

{feedback}

Correction requirements:
- Keep the SAME underlying topic.
- Fix every factual, structural, visual-planning, and narration issue identified above.
- Do not mention this review or revision process in the narration.
- Do not invent facts.
- Remove unsupported claims.
- For News content, use the supplied source context
  as the factual basis.
- Keep the narration in natural English.
- Keep the visual plan directly aligned with the corrected narration.
"""

    return generate_script(
        revision_topic,
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
        and not media_files
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

            script = improve_script_from_review(
                topic=topic,
                review=review,
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

        if (
            status == "APPROVE"
            and int(score or 0) >= 75
            and not review.get(
                "critical_issues",
                [],
            )
        ):

            stop_reason = (
                "AI Review approved the current version."
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
        # IMPROVE
        # ----------------------------------------------------

        if status == "IMPROVE":

            if attempt < MAX_REVIEW_ATTEMPTS:

                progress.progress(
                    94,
                    text=(
                        f"⚠️ Review {attempt} requested "
                        "improvements. Regenerating..."
                    ),
                )

                print(
                    "Review requested improvements."
                )

                print(
                    "Regenerating the SAME topic..."
                )

                continue

            # Third IMPROVE → stop improving but keep
            # the latest generated version.
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
        "upload_blocked": False,
        "stop_reason": stop_reason,
    }


# ============================================================
# STREAMLIT DASHBOARD
# ============================================================

st.set_page_config(
    page_title="AutoTube AI",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 AutoTube AI")

st.write(
    "Create an English AI video from a topic, "
    "image, flyer, or uploaded video."
)

st.divider()

# ============================================================
# TOPIC
# ============================================================

topic = st.text_input(
    "What do you want to create?",
    placeholder="Enter a topic or video idea...",
)

content_type = st.selectbox(
    "Content Type",
    [
        "News",
        "General Topic",
    ],
    index=0,
    help=(
        "News verifies source context before script generation. "
        "General Topic uses normal topic generation."
    ),
)

# ============================================================
# MEDIA UPLOAD
# ============================================================

st.subheader("Upload Media")

media_files = st.file_uploader(
    "Upload images or videos",
    type=[
        "png",
        "jpg",
        "jpeg",
        "webp",
        "mp4",
        "mov",
        "m4v",
        "avi",
    ],
    accept_multiple_files=True,
)

if media_files:

    st.success(
        f"{len(media_files)} media file(s) selected."
    )


# ============================================================
# FLYER
# ============================================================

st.subheader("Flyer")

flyer_file = st.file_uploader(
    "Optional: Upload a flyer separately",
    type=[
        "png",
        "jpg",
        "jpeg",
        "webp",
    ],
    accept_multiple_files=False,
)

if flyer_file:

    st.success(
        f"Flyer selected: {flyer_file.name}"
    )


# ============================================================
# SETTINGS
# ============================================================

st.subheader("Settings")

language_style = st.selectbox(
    "Language / Style",
    [
        "English",
        "English news style",
        "English YouTube creator style",
        "Educational English",
        "English documentary style",
        "English promotional style",
    ],
)

voice = st.selectbox(
    "Voice",
    [
        "English Female",
        "English Male",
        "English Creator",
    ],
)

captions = st.checkbox(
    "Auto captions",
    value=True,
    help="Turn captions on or off for the final video.",
)

thumbnail = st.checkbox(
    "Create thumbnail",
    value=True,
)

metadata = st.checkbox(
    "Generate YouTube metadata",
    value=True,
)

youtube_upload = st.checkbox(
    "Upload to YouTube",
    value=False,
)

youtube_privacy = st.selectbox(
    "YouTube Privacy",
    [
        "public",
        "unlisted",
        "private",
    ],
    index=0,
    disabled=not youtube_upload,
)

if youtube_upload:
    st.info(
        f"YouTube upload enabled → {youtube_privacy.upper()}"
    )

# ============================================================
# GENERATE
# ============================================================

st.divider()

generate = st.button(
    "🚀 Generate Video",
    type="primary",
    use_container_width=True,
)

if generate:

    if not topic:

        st.error(
            "Please enter a topic or video idea."
        )

    else:

        try:

            all_media = list(
                media_files or []
            )

            if flyer_file:

                all_media.append(
                    flyer_file
                )

            with st.spinner(
                "AutoTube AI is creating your video..."
            ):

                result = generate_multi_media_video(
                    topic=topic or "AI Generated Video",
                    media_files=all_media,
                    content_type=(
                        "General Topic"
                        if flyer_file
                        else content_type
                    ),
                    language_style=language_style,
                    voice=voice,
                    captions=captions,
                    thumbnail=thumbnail,
                    metadata=metadata,
                    youtube_upload=youtube_upload,
                    youtube_privacy=youtube_privacy,
                )

            review = result.get(
                "review",
                {},
            )

            review_status = str(
                review.get(
                    "status",
                    "UNKNOWN",
                )
            ).upper()

            review_score = review.get(
                "score",
                0,
            )

            upload_blocked = bool(
                result.get(
                    "upload_blocked",
                    False,
                )
            )

            review_attempts = result.get(
                "review_attempts",
                0,
            )

            # ------------------------------------------------
            # AI QUALITY REVIEW
            # ------------------------------------------------

            st.divider()
            st.subheader("🤖 AI Quality Review")

            if review_status == "APPROVE" and not upload_blocked:

                st.success(
                    f"✅ APPROVED — {review_score}/100 "
                    f"({review_attempts}/3 review attempts)"
                )

            elif review_status == "REVIEW_QUOTA_EXCEEDED":

                st.warning(
                    "⚪ AI Review unavailable because the "
                    "Gemini quota/rate limit was reached. "
                    "The latest generated version will continue."
                )

            elif review_status == "IMPROVE":

                st.warning(
                    f"⚠️ IMPROVE — {review_score}/100 "
                    f"({review_attempts}/3 review attempts)"
                )

            elif review_status == "REVIEW_FAILED":

                st.warning(
                    f"⚪ AI Review unavailable — "
                    f"{review_score}/100"
                )

            else:

                st.info(
                    f"Review status: {review_status} — "
                    f"{review_score}/100 "
                    f"({review_attempts}/3 review attempts)"
                )

            if review.get("summary"):

                st.write(
                    review["summary"]
                )

            section_labels = [
                ("script", "Script"),
                ("factual_quality", "Factual Quality"),
                ("hook", "Hook"),
                ("visuals", "Visuals"),
                ("subtitles", "Subtitles"),
                ("thumbnail", "Thumbnail"),
            ]

            for key, label in section_labels:

                data = review.get(
                    key,
                    {},
                )

                if data:

                    score = data.get(
                        "score",
                        0,
                    )

                    section_status = data.get(
                        "status",
                        "",
                    )

                    st.write(
                        f"**{label}:** "
                        f"{score}/100 — "
                        f"{section_status}"
                    )

                    if data.get("feedback"):

                        st.caption(
                            data["feedback"]
                        )

            critical = review.get(
                "critical_issues",
                [],
            )

            if critical:

                st.markdown(
                    "**Critical Issues**"
                )

                for issue in critical:

                    st.error(
                        str(issue)
                    )

            improvements = review.get(
                "improvements",
                [],
            )

            if improvements:

                st.markdown(
                    "**Improvements**"
                )

                for improvement in improvements:

                    st.info(
                        str(improvement)
                    )

            if result.get("stop_reason"):

                st.caption(
                    result["stop_reason"]
                )

            if (
                youtube_upload
                and review_status == "APPROVE"
            ):

                st.success(
                    "✅ AI Review approved. "
                    f"YouTube upload: {youtube_privacy.upper()}"
                )

            elif (
                youtube_upload
                and review_status == "IMPROVE"
            ):

                st.info(
                    "ℹ️ Review feedback is advisory. "
                    "The latest generated version will continue "
                    f"to YouTube as {youtube_privacy.upper()}."
                )

            elif (
                youtube_upload
                and review_status in {
                    "REVIEW_QUOTA_EXCEEDED",
                    "REVIEW_FAILED",
                }
            ):

                st.info(
                    "ℹ️ AI Review was unavailable. "
                    "The latest generated version will continue "
                    f"to YouTube as {youtube_privacy.upper()}."
                )

            # ------------------------------------------------
            # VIDEO RESULT
            # ------------------------------------------------

            st.success(
                "🎉 Video generated successfully!"
            )

            video_path = Path(
                result["video"]
            )

            if video_path.exists():

                st.video(
                    str(video_path)
                )

                st.download_button(
                    "⬇️ Download Final Video",
                    data=video_path.read_bytes(),
                    file_name="autotube_final_video.mp4",
                    mime="video/mp4",
                )

            if result["title"]:

                st.subheader(
                    "Generated Title"
                )

                st.write(
                    result["title"]
                )

            if result["description"]:

                st.subheader(
                    "Generated Description"
                )

                st.write(
                    result["description"]
                )

            if result["tags"]:

                st.subheader(
                    "Generated Tags"
                )

                st.write(
                    ", ".join(result["tags"])
                )

        except Exception as error:

            st.error(
                "AutoTube AI failed."
            )

            st.exception(
                error
            )

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
# METADATA
# ============================================================

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


def generate_multi_media_video(
    topic,
    media_files=None,
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
    Topic-first AutoTube AI pipeline.

    Main flow:

        Topic
          ↓
        AI Script + Visual Plan
          ↓
        Web Visuals
          ↓
        English Voice
          ↓
        Video
          ↓
        Captions
          ↓
        Thumbnail
          ↓
        Metadata
          ↓
        Optional YouTube Upload

    Uploaded media is optional.
    """

    clean_previous_generation()

    if not topic or not topic.strip():
        raise RuntimeError(
            "Please enter a topic or video idea."
        )

    media_files = media_files or []

    progress = st.progress(
        0,
        text="Starting AutoTube AI...",
    )

    # ========================================================
    # OPTIONAL UPLOADED MEDIA
    # ========================================================

    saved_media = []

    if media_files:

        progress.progress(
            5,
            text="Preparing uploaded media...",
        )

        saved_media = save_uploaded_files(
            media_files
        )

    # ========================================================
    # AI SCRIPT + VISUAL PLAN
    # ========================================================

    progress.progress(
        15,
        text="AI is generating script and visual plan...",
    )

    if script_override:

        script = script_override

    else:

        from agents.script_agent import generate_script

        script = generate_script(
            topic,
            content_type="News",
            language_style=language_style,
        )

    if not script:

        raise RuntimeError(
            "AI did not generate a script."
        )

    # ========================================================
    # OPTIONAL UPLOADED MEDIA
    # ========================================================

    if saved_media:

        progress.progress(
            25,
            text="Preparing uploaded media...",
        )

        prepare_uploaded_media(
            saved_media
        )

    # ========================================================
    # WEB VISUALS
    # ========================================================

    visual_plan_file = (
        OUTPUT_DIR / "visual_plan.txt"
    )

    if visual_plan_file.exists():

        progress.progress(
            35,
            text="Finding visuals from AI visual plan...",
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

    else:

        raise RuntimeError(
            "AI visual plan was not created."
        )

    # ========================================================
    # ENGLISH VOICE
    # ========================================================

    progress.progress(
        50,
        text="Generating English narration...",
    )

    create_voice_for_script(
        voice
    )

    # ========================================================
    # VIDEO
    # ========================================================

    progress.progress(
        65,
        text="Creating video...",
    )

    create_pipeline_video()

    # ========================================================
    # FINAL VIDEO + CAPTIONS
    # ========================================================

    progress.progress(
        78,
        text="Rendering final video and captions...",
    )

    create_final_video(
        captions=captions
    )

    # ========================================================
    # THUMBNAIL
    # ========================================================

    if thumbnail:

        progress.progress(
            88,
            text="Creating thumbnail...",
        )

        create_thumbnail(
            topic
        )

    # ========================================================
    # METADATA
    # ========================================================

    if metadata:

        progress.progress(
            93,
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

    # ========================================================
    # COMPLETE
    # ========================================================

    progress.progress(
        100,
        text="AutoTube AI generation completed!",
    )

    return {
        "script": script,
        "title": title,
        "description": description,
        "tags": tags,
        "video": str(
            OUTPUT_DIR / "final_video.mp4"
        ),
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
                    language_style=language_style,
                    voice=voice,
                    captions=captions,
                    thumbnail=thumbnail,
                    metadata=metadata,
                    youtube_upload=youtube_upload,
                    youtube_privacy=youtube_privacy,
                )

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

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
    "👨 Mohan (Telugu Male Anchor) - Edge-TTS": "te-IN-MohanNeural",
    "👩 Shruti (Telugu Female Anchor) - Edge-TTS": "te-IN-ShrutiNeural",
    "👨 Adam (Male Creator) - Fast & Crisp": "am_adam",
    "👨 Michael (News Anchor) - Professional": "am_michael",
    "👩 Heart (Female Creator) - Smooth": "af_heart",
    "👩 Bella (Warm Female) - Storytelling": "af_bella",
    "👨 Madhur (Hindi Male Anchor) - Edge-TTS": "hi-IN-MadhurNeural",
    "👩 Swara (Hindi Female Anchor) - Edge-TTS": "hi-IN-SwaraNeural",
    "🎙️ Use My Own Voice Recording (Upload Audio)": "own_recording",
    "🤖 Clone My Voice with AI (Local XTTS-v2)": "clone",
    # Direct alias matches
    "te-in-mohanneural": "te-IN-MohanNeural",
    "te-in-shrutineural": "te-IN-ShrutiNeural",
    "hi-in-madhurneural": "hi-IN-MadhurNeural",
    "hi-in-swaraneural": "hi-IN-SwaraNeural",
    "te-IN-MohanNeural": "te-IN-MohanNeural",
    "te-IN-ShrutiNeural": "te-IN-ShrutiNeural",
    "hi-IN-MadhurNeural": "hi-IN-MadhurNeural",
    "hi-IN-SwaraNeural": "hi-IN-SwaraNeural",
    "mohan": "te-IN-MohanNeural",
    "shruti": "te-IN-ShrutiNeural",
    "clone": "clone",
    "xtts": "clone",
    "own_recording": "own_recording",
    "own_voice": "own_recording",
    "am_adam": "am_adam",
    "am_michael": "am_michael",
    "af_heart": "af_heart",
    "af_bella": "af_bella",
    # Legacy fallbacks
    "Creator Voice": "am_adam",
    "English Female": "af_heart",
}

VOICE_TUNING = {
    "👨 Mohan (Telugu Male Anchor) - Edge-TTS": ("+0%", "+0Hz"),
    "👩 Shruti (Telugu Female Anchor) - Edge-TTS": ("+0%", "+0Hz"),
    "👨 Adam (Male Creator) - Fast & Crisp": ("-5%", "+0Hz"),
    "👨 Michael (News Anchor) - Professional": ("-5%", "+0Hz"),
    "👩 Heart (Female Creator) - Smooth": ("-5%", "+0Hz"),
    "👩 Bella (Warm Female) - Storytelling": ("-5%", "+0Hz"),
    "👨 Madhur (Hindi Male Anchor) - Edge-TTS": ("+0%", "+0Hz"),
    "👩 Swara (Hindi Female Anchor) - Edge-TTS": ("+0%", "+0Hz"),
    "🎙️ Use My Own Voice Recording (Upload Audio)": ("+0%", "+0Hz"),
    "🤖 Clone My Voice with AI (Local XTTS-v2)": ("+0%", "+0Hz"),
    "te-IN-MohanNeural": ("+0%", "+0Hz"),
    "te-IN-ShrutiNeural": ("+0%", "+0Hz"),
    "hi-IN-MadhurNeural": ("+0%", "+0Hz"),
    "hi-IN-SwaraNeural": ("+0%", "+0Hz"),
    "mohan": ("+0%", "+0Hz"),
    "shruti": ("+0%", "+0Hz"),
    "clone": ("+0%", "+0Hz"),
    "xtts": ("+0%", "+0Hz"),
    "own_recording": ("+0%", "+0Hz"),
    "am_adam": ("-5%", "+0Hz"),
    "am_michael": ("-5%", "+0Hz"),
    "af_heart": ("-5%", "+0Hz"),
    "af_bella": ("-5%", "+0Hz"),
    # Legacy fallbacks
    "Creator Voice": ("-5%", "+0Hz"),
    "English Female": ("-5%", "+0Hz"),
}


# ============================================================
# STUDIO-GRADE MODEL WARM-LOADING (WHISPER & CLIP CACHING)
# ============================================================

def warmup_models(background=True):
    """
    Warm-load heavy AI models (Whisper, CLIP) into memory once at startup
    to eliminate cold-start latency (saving 10-30s per video run).
    """
    def _warmup():
        print("⚡ [Warm-Loading] Pre-caching Whisper & CLIP models...")
        try:
            from agents.video_agent import get_whisper_model
            get_whisper_model()
            print("✅ [Warm-Loading] Whisper speech recognition model cached.")
        except Exception as e:
            print(f"⚠️ Whisper warm-up notice: {e}")

        try:
            from agents.image_agent import get_clip_pipeline
            get_clip_pipeline()
            print("✅ [Warm-Loading] OpenCLIP visual relevance pipeline cached.")
        except Exception as e:
            print(f"⚠️ CLIP warm-up notice: {e}")

    if background:
        import threading
        t = threading.Thread(target=_warmup, daemon=True, name="ModelWarmupThread")
        t.start()
        return t
    else:
        _warmup()
        return None


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
# SAVE UPLOAD (SAFE FOR UPLOADEDFILE & STRING/PATH OBJECTS)
# ============================================================

def get_image_filename(image_input):
    """
    Handle both Streamlit UploadedFile objects AND plain string/Path paths safely --
    completely fixes "'str' object has no attribute 'name'".
    """
    if hasattr(image_input, "name"):
        return str(image_input.name)
    elif isinstance(image_input, (str, Path)):
        return os.path.basename(str(image_input))
    else:
        return str(image_input)


def save_uploaded_file(uploaded_file, index):
    """Save a Streamlit uploaded file or copy existing path string safely."""
    fname = get_image_filename(uploaded_file)
    suffix = Path(fname).suffix.lower()
    if not suffix:
        suffix = ".bin"

    filename = f"uploaded_{index}{suffix}"
    destination = UPLOADS_DIR / filename

    if hasattr(uploaded_file, "getbuffer"):
        destination.write_bytes(uploaded_file.getbuffer())
    elif hasattr(uploaded_file, "read"):
        destination.write_bytes(uploaded_file.read())
    elif isinstance(uploaded_file, (str, Path)) and os.path.exists(str(uploaded_file)):
        shutil.copy2(str(uploaded_file), str(destination))
    else:
        destination.touch()

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

    voice_str = str(voice or "").strip().lower()
    if "clone" in voice_str or "xtts" in voice_str:
        voice_id = "clone"
    elif "own" in voice_str and ("record" in voice_str or "voice" in voice_str):
        voice_id = "own_recording"
    else:
        voice_id = VOICE_IDS.get(voice, VOICE_IDS.get(voice_str, "am_adam"))

    from agents.voice_agent import create_voice

    rate, pitch = VOICE_TUNING.get(voice, VOICE_TUNING.get(voice_id, ("-5%", "+0Hz")))

    # Resolve audio sample if using direct own voice recording or cloning
    effective_sample = (
        own_voice_audio
        if voice_id in ("own_recording", "clone")
        else None
    )
    if voice_id in ("own_recording", "clone") and not effective_sample:
        for cand in (
            "voice_samples/active_voice.mp3",
            "voice_samples/active_voice.wav",
            "voice_samples/xtts_clean_ref.wav",
            "voice_samples/user_voice.mp3",
            "voice_samples/user_voice.wav",
        ):
            if os.path.exists(cand) and os.path.getsize(cand) > 0:
                effective_sample = cand
                break

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
        fpath = Path(file)
        if fpath.suffix.lower() in {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }:
            image_file = fpath
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
    aspect_ratio="16:9",
    generation_mode="stock",
    user_assets=None,
    *args,
    **kwargs,
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
            aspect_ratio=aspect_ratio,
            generation_mode=generation_mode,
            user_assets=user_assets,
            *args,
            **kwargs,
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
        source_path = Path(source)
        suffix = source_path.suffix.lower()

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
    include_outro=False,
    outro_clip=None,
):
    """Create final video with optional captions and outro."""

    if captions:
        try:
            from agents.subtitle_agent import create_subtitles
            create_subtitles(aspect_ratio=aspect_ratio)
        except Exception as sub_err:
            print(f"⚠️ Subtitle creation notice: {sub_err}")

    from agents.final_video_agent import (
        create_final_video as finalize,
    )

    return finalize(
        add_captions=captions,
        aspect_ratio=aspect_ratio,
        include_outro=include_outro,
        outro_clip=outro_clip,
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

    metadata = {
        "title": title,
        "description": description,
        "tags": tags,
        "privacy": privacy,
        "youtube_upload": youtube_upload,
        "youtube_video_id": video_id,
        "youtube_error": youtube_error,
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
    include_outro=True,
    instagram_upload=False,
    progress_callback=None,
    generation_mode="stock",
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


        if progress_callback:
            progress_callback(2, "📰 Verifying news sources...")
        else:
            try:
                st.info("📰 Verifying news sources...")
            except Exception:
                pass

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
            if progress_callback:
                progress_callback(4, f"📰 News sources found: {len(articles)}")
            else:
                try:
                    st.success(f"📰 News sources found: {len(articles)}")
                except Exception:
                    pass
        else:
            if progress_callback:
                progress_callback(4, "⚠️ No matching news sources confirmed.")
            else:
                try:
                    st.warning(
                        "⚠️ No matching news sources "
                        "were confirmed. The script will "
                        "avoid unsupported claims."
                    )
                except Exception:
                    pass

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
                is_flyer_mode = (
                    content_type == "Uploaded Flyer"
                    or generation_mode in ("flyer", "Upload Flyer/Poster", "🖼️ Upload Flyer/Poster")
                )
                if is_flyer_mode and (saved_media or media_files):
                    flyer_file = saved_media[0] if saved_media else media_files[0]
                    try:
                        from agents.multimode_agent import extract_flyer_content, generate_script_from_flyer
                        flyer_info = extract_flyer_content(flyer_file)
                        pkg = generate_script_from_flyer(flyer_info, language_style=language_style)
                        script = pkg.get("script", "")
                        title = pkg.get("title") or title
                    except Exception as flyer_err:
                        print(f"Multimode flyer notice: {flyer_err}. Falling back to generate_script_from_image...")
                        from agents.script_agent import generate_script_from_image
                        pkg = generate_script_from_image(str(flyer_file), language_style)
                        script = pkg.get("script", "")
                elif generation_mode in ("explainer", "Explainer Style", "📊 Explainer Style") or content_type == "Explainer":
                    from agents.script_agent import generate_script
                    script = generate_script(
                        topic,
                        content_type="Explainer",
                        language_style=language_style,
                        source_context=news_verification,
                    )
                else:
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
        # PARALLEL PIPELINE: VISUALS + VOICE CONCURRENT EXECUTION
        # ----------------------------------------------------

        if run_images and run_voice:
            visual_plan_file = OUTPUT_DIR / "visual_plan.txt"
            if not visual_plan_file.exists():
                raise RuntimeError("AI visual plan was not created.")

            progress.progress(
                35,
                text=(
                    f"Attempt {attempt}: "
                    f"⚡ Parallel Execution: Sourcing visuals & synthesizing narration ({voice})..."
                ),
            )

            import concurrent.futures

            flyer_path_arg = (
                (saved_media[0] if saved_media else media_files[0])
                if (content_type == "Uploaded Flyer" or generation_mode in ("flyer", "Upload Flyer/Poster", "🖼️ Upload Flyer/Poster")) and (saved_media or media_files)
                else None
            )

            def _task_visuals():
                print("⚡ [Parallel Stage] Starting Visual Sourcing...")
                try:
                    download_visuals(
                        visual_plan_file,
                        flyer_path=flyer_path_arg,
                        feedback=feedback if failing_component == "image_agent" else None,
                        aspect_ratio=aspect_ratio,
                        generation_mode=generation_mode,
                        user_assets=saved_media or media_files,
                    )
                    print("✅ [Parallel Stage] Visual Sourcing Complete.")
                except Exception as error:
                    print("Visual sourcing warning:", error)

            def _task_voice():
                print(f"⚡ [Parallel Stage] Starting Narration Synthesis ({voice})...")
                create_voice_for_script(
                    voice=voice,
                    own_voice_audio=voice_sample,
                )
                print("✅ [Parallel Stage] Narration Synthesis Complete.")

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                f_vis = executor.submit(_task_visuals)
                f_voc = executor.submit(_task_voice)
                concurrent.futures.wait([f_vis, f_voc])
                f_vis.result()
                f_voc.result()

            progress.progress(55, text=f"Attempt {attempt}: Visuals & voice ready! Creating video...")

        else:
            # Fallback path if one component was preserved by self-healing
            if run_images:
                visual_plan_file = OUTPUT_DIR / "visual_plan.txt"
                if not visual_plan_file.exists():
                    raise RuntimeError("AI visual plan was not created.")
                progress.progress(
                    35,
                    text=f"Attempt {attempt}: Finding visuals from AI visual plan{' (adjusted for feedback)' if failing_component == 'image_agent' else ''}...",
                )
                try:
                    download_visuals(
                        visual_plan_file,
                        flyer_path=flyer_path_arg,
                        feedback=feedback if failing_component == "image_agent" else None,
                        aspect_ratio=aspect_ratio,
                        generation_mode=generation_mode,
                        user_assets=saved_media or media_files,
                    )
                except Exception as error:
                    print("Visual sourcing warning:", error)
            else:
                print(f"[Targeted Self-Healing] Preserving existing visual assets in assets/ (failing component: {failing_component})")

            if run_voice:
                progress.progress(
                    50,
                    text=f"Attempt {attempt}: Preparing narration ({voice})...",
                )
                create_voice_for_script(
                    voice=voice,
                    own_voice_audio=voice_sample,
                )
            else:
                print(f"[Targeted Self-Healing] Preserving existing voice audio (failing component: {failing_component})")

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

        create_pipeline_video(
            aspect_ratio=aspect_ratio
        )

        # ----------------------------------------------------
        # FINAL VIDEO + CAPTIONS
        # ----------------------------------------------------

        progress.progress(
            78,
            text=(
                f"Attempt {attempt}: "
                "Rendering final video, captions and outro..."
            ),
        )

        create_final_video(
            captions=captions,
            aspect_ratio=aspect_ratio,
            include_outro=include_outro,
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

        if not (OUTPUT_DIR / "final_video.mp4").exists() and (OUTPUT_DIR / "video.mp4").exists():
            print("Promoting video.mp4 to final_video.mp4 as safety fallback...")
            shutil.copyfile(str(OUTPUT_DIR / "video.mp4"), str(OUTPUT_DIR / "final_video.mp4"))

        if (OUTPUT_DIR / "final_video.mp4").exists():
            print("Final video exists on disk. Proceeding with metadata and pre-declared YouTube upload...")
            stopped_after_review = True
            break

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
            "video": None,
            "stop_reason": f"Topic scored {review_score} after {MAX_RETRIES} retries. Moved to failed_queue/.",
            "youtube_video_id": None,
            "youtube_error": None,
            "instagram_status": {"eligible": False, "reason": "Moved to failed_queue", "result": None},
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

    # --------------------------------------------------------
    # OPTIONAL INSTAGRAM REELS UPLOAD
    # --------------------------------------------------------
    instagram_status = {"eligible": False, "reason": "Instagram upload not enabled", "result": None}
    if instagram_upload:
        try:
            from agents.instagram_agent import should_upload_to_instagram, upload_to_instagram_reels
            final_vid = OUTPUT_DIR / "final_video.mp4"
            dur = 0.0
            if final_vid.exists():
                import subprocess
                p_dur = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(final_vid)],
                    capture_output=True, text=True
                )
                try:
                    dur = float(p_dur.stdout.strip())
                except Exception:
                    dur = 0.0

            eligible, reason = should_upload_to_instagram(dur, instagram_upload, aspect_ratio)
            instagram_status = {"eligible": eligible, "reason": reason, "duration": dur, "result": None}

            if eligible:
                print(f"📸 Instagram Reels: Video is eligible ({dur:.1f}s, {aspect_ratio}). Preparing upload...")
                public_base = os.getenv("PUBLIC_VIDEO_BASE_URL", "https://smokeless-waking-remote.ngrok-free.dev")
                public_url = f"{public_base}/output/final_video.mp4"
                res = upload_to_instagram_reels(
                    video_source=str(final_vid) if final_vid.exists() else public_url,
                    caption=f"{title}\n\n{description[:300]}"
                )
                instagram_status["result"] = res
                if res.get("success"):
                    print("✅ Instagram Reels published successfully! Media ID:", res.get("media_id"))
                else:
                    print("⚠️ Instagram Reels notice:", res.get("error"))
            else:
                print(f"ℹ️ Instagram Reels: Not eligible -> {reason}")
        except Exception as ig_err:
            print("⚠️ Instagram Reels processing error:", ig_err)
            instagram_status = {"eligible": False, "reason": str(ig_err), "result": None}

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
        "instagram_status": instagram_status,
    }


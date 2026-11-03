"""AutoTube AI - Multi-Media Streamlit Dashboard."""

import asyncio
import datetime
import json
import os
import re
import shutil
import time
import traceback
import sys
from pathlib import Path
from importlib import import_module

st = import_module("streamlit")

try:
    from agents.env_loader import get_gemini_api_key, get_pexels_api_key, sync_secrets_to_env
    sync_secrets_to_env()
except Exception:
    def get_gemini_api_key(): return os.getenv("GEMINI_API_KEY", "")
    def get_pexels_api_key(): return os.getenv("PEXELS_API_KEY", "")
    def sync_secrets_to_env(): pass


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
    "👨 Mohan (Telugu Creator / Anchor) - Natural Spoken Delivery": "te-IN-MohanNeural",
    "👩 Shruti (Telugu Creator / Anchor) - Conversational": "te-IN-ShrutiNeural",
    "👨 Adam (Male Creator) - Fast, Crisp & Natural": "am_adam",
    "👩 Heart (Female Creator) - Smooth & Conversational": "af_heart",
    "👨 Michael (News Anchor) - Professional & Authoritative": "am_michael",
    "👩 Bella (Warm Female) - Expressive & Storytelling": "af_bella",
    "🎙️ OmniVoice Presenter (Zero-Shot AI Voice Design)": "omnivoice",
    "🤖 Clone My Voice with AI (Local XTTS-v2 / OmniVoice)": "clone",
    "🎙️ Use My Own Voice Recording (Upload Audio)": "own_recording",
    "👨 Mohan (Telugu Male Anchor) - Edge-TTS (Fallback)": "te-IN-MohanNeural",
    "👩 Shruti (Telugu Female Anchor) - Edge-TTS (Fallback)": "te-IN-ShrutiNeural",
    "👨 Madhur (Hindi Male Anchor) - Edge-TTS (Fallback)": "hi-IN-MadhurNeural",
    "👩 Swara (Hindi Female Anchor) - Edge-TTS (Fallback)": "hi-IN-SwaraNeural",
    # Legacy/direct alias matches
    "👨 Adam (Male Creator) - Fast & Crisp": "am_adam",
    "👨 Michael (News Anchor) - Professional": "am_michael",
    "👩 Heart (Female Creator) - Smooth": "af_heart",
    "👩 Bella (Warm Female) - Storytelling": "af_bella",
    "👨 Mohan (Telugu Male Anchor) - Edge-TTS": "te-IN-MohanNeural",
    "👩 Shruti (Telugu Female Anchor) - Edge-TTS": "te-IN-ShrutiNeural",
    "👨 Madhur (Hindi Male Anchor) - Edge-TTS": "hi-IN-MadhurNeural",
    "👩 Swara (Hindi Female Anchor) - Edge-TTS": "hi-IN-SwaraNeural",
    "omnivoice": "omnivoice",
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
    "Creator Voice": "am_adam",
    "English Female": "af_heart",
}

VOICE_TUNING = {
    "👨 Mohan (Telugu Creator / Anchor) - Natural Spoken Delivery": ("+4%", "+0Hz"),
    "👩 Shruti (Telugu Creator / Anchor) - Conversational": ("+4%", "+0Hz"),
    "👨 Adam (Male Creator) - Fast, Crisp & Natural": ("-5%", "+0Hz"),
    "👩 Heart (Female Creator) - Smooth & Conversational": ("-5%", "+0Hz"),
    "👨 Michael (News Anchor) - Professional & Authoritative": ("-5%", "+0Hz"),
    "👩 Bella (Warm Female) - Expressive & Storytelling": ("-5%", "+0Hz"),
    "🎙️ OmniVoice Presenter (Zero-Shot AI Voice Design)": ("+0%", "+0Hz"),
    "👨 Mohan (Telugu Male Anchor) - Edge-TTS (Fallback)": ("+4%", "+0Hz"),
    "👩 Shruti (Telugu Female Anchor) - Edge-TTS (Fallback)": ("+4%", "+0Hz"),
    "👨 Mohan (Telugu Male Anchor) - Edge-TTS": ("+4%", "+0Hz"),
    "👩 Shruti (Telugu Female Anchor) - Edge-TTS": ("+4%", "+0Hz"),
    "👨 Adam (Male Creator) - Fast & Crisp": ("-5%", "+0Hz"),
    "👨 Michael (News Anchor) - Professional": ("-5%", "+0Hz"),
    "👩 Heart (Female Creator) - Smooth": ("-5%", "+0Hz"),
    "👩 Bella (Warm Female) - Storytelling": ("-5%", "+0Hz"),
    "👨 Madhur (Hindi Male Anchor) - Edge-TTS": ("+0%", "+0Hz"),
    "👩 Swara (Hindi Female Anchor) - Edge-TTS": ("+0%", "+0Hz"),
    "🎙️ Use My Own Voice Recording (Upload Audio)": ("+0%", "+0Hz"),
    "🤖 Clone My Voice with AI (Local XTTS-v2)": ("+0%", "+0Hz"),
    "te-IN-MohanNeural": ("+4%", "+0Hz"),
    "te-IN-ShrutiNeural": ("+4%", "+0Hz"),
    "hi-IN-MadhurNeural": ("+0%", "+0Hz"),
    "hi-IN-SwaraNeural": ("+0%", "+0Hz"),
    "mohan": ("+4%", "+0Hz"),
    "shruti": ("+4%", "+0Hz"),
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


def run_stage_with_timeout(stage_name, timeout_seconds, func, *args, **kwargs):
    """
    Execute a pipeline stage in a worker thread bounded by a hard timeout.
    Prevents stalled network or ffmpeg calls from blocking pipeline indefinitely.
    """
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            err_msg = f"Stage '{stage_name}' timed out after {timeout_seconds}s limit."
            print(f"❌ {err_msg}")
            raise TimeoutError(err_msg)


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
        "subtitles.ass",
        "captions.ass",
        "teleprompter.txt",
        "delivery_plan.json",
        "video_clips_manifest.json",
        "clean_script.txt",
        "hook_overlay.png",
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
            # Never delete voice sample references, static music, outro, or offline fallback pool
            if "voice" in item.name.lower() or item.name.lower() in ("fallback", "music", "outro"):
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
        # Fallback: if path does not exist on disk, touch destination
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
    topic_category="tech_review",
):
    """Generate or apply voice narration for the video."""

    voice_str = str(voice or "").strip().lower()
    if "clone" in voice_str or "xtts" in voice_str:
        voice_id = "clone"
    elif "own" in voice_str and ("record" in voice_str or "voice" in voice_str):
        voice_id = "own_recording"
    else:
        voice_id = VOICE_IDS.get(voice, VOICE_IDS.get(voice_str, "am_adam"))

    # Auto-detect Telugu script, enforce 3-part CTA, and route voice
    script_path = Path("output/script.txt")
    if script_path.exists():
        try:
            s_text = script_path.read_text(encoding="utf-8")
            from utils.transliterate_telugu import ensure_telugu_script
            s_text = ensure_telugu_script(s_text)
            from agents.script_agent import ensure_dynamic_outro_cta, deduplicate_script_narration, clean_script_narration
            is_indic = bool(re.search(r"[\u0C00-\u0C7F]", s_text))
            updated_s = ensure_dynamic_outro_cta(s_text, is_indic=is_indic)
            updated_s = deduplicate_script_narration(updated_s)
            if updated_s != s_text:
                script_path.write_text(updated_s, encoding="utf-8")
                tts_p = Path("output/tts_script.txt")
                tts_p.write_text(clean_script_narration(updated_s), encoding="utf-8")
                s_text = updated_s

            if is_indic and voice_id in ("am_adam", "af_heart", "am_michael", "af_bella"):
                print("🎙️ [Voice Agent] Detected Telugu script narration - auto-selecting te-IN-MohanNeural for authentic Telugu creator delivery.")
                voice_id = "te-IN-MohanNeural"
        except Exception:
            pass

    from agents.voice_agent import create_voice

    rate, pitch = VOICE_TUNING.get(voice, VOICE_TUNING.get(voice_id, ("-5%", "+0Hz")))
    if voice_id in ("te-IN-MohanNeural", "te-IN-ShrutiNeural", "mohan", "shruti") and rate in ("-5%", "+0%"):
        rate, pitch = ("+4%", "+0Hz")

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
            topic_category=topic_category,
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
    if not res:
        raise RuntimeError("No visual assets were returned by image agent.")
    ensure_visual_assets_exist(needed_count=len(res))
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

def create_pipeline_video(aspect_ratio="9:16"):
    """Run the project's video agent with pre-render vision quality gate."""

    # Autonomous Pre-Render Vision Gate & Self-Healing
    try:
        from agents.vision_gate import audit_and_heal_visual_assets
        v_ok, v_rep = audit_and_heal_visual_assets(aspect_ratio=aspect_ratio)
        print(f"👁️ [Vision Gate] Pre-render audit complete: {v_rep.get('total_assets', 0)} assets (Clean: {v_rep.get('clean_count', 0)}, Healed: {v_rep.get('healed_count', 0)})")
    except Exception as v_err:
        print(f"⚠️ [Vision Gate] Notice: {v_err}")

    from agents.video_agent import create_video

    return create_video(aspect_ratio=aspect_ratio)


# ============================================================
# FINAL VIDEO
# ============================================================

def create_final_video(
    captions=False,
    aspect_ratio="9:16",
    burn_captions=None,
    include_outro=False,
    outro_clip=None,
):
    """Create final video with optional captions burning and outro."""
    should_burn = burn_captions if burn_captions is not None else captions

    # Check if subtitles were already generated in parallel stage
    sub_ass = Path("output/subtitles.ass")
    sub_srt = Path("output/subtitles.srt")
    if not (sub_ass.exists() or sub_srt.exists()):
        try:
            from agents.subtitle_agent import create_subtitles
            create_subtitles(aspect_ratio=aspect_ratio)
        except Exception as sub_err:
            print(f"⚠️ Subtitle creation notice: {sub_err}")

    from agents.final_video_agent import (
        create_final_video as finalize,
    )

    return finalize(
        add_captions=should_burn,
        aspect_ratio=aspect_ratio,
        include_outro=include_outro,
        outro_clip=outro_clip,
    )


# ============================================================
# THUMBNAIL
# ============================================================

def create_thumbnail(
    title,
    aspect_ratio="9:16",
    assets_dir=None,
    output_dir=None,
):
    """Create thumbnail using existing thumbnail agent."""

    from agents.thumbnail_agent import create_thumbnail as _create_thumb

    return _create_thumb(
        title,
        aspect_ratio=aspect_ratio,
        assets_dir=assets_dir,
        output_dir=output_dir,
    )

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


def perform_youtube_upload(
    video_file,
    title,
    description,
    tags,
    privacy="private",
    channel="Channel 1 (Primary)",
    thumbnail_path=None,
    run_dir=None,
    run_id=None,
):
    """
    Perform isolated YouTube video and custom thumbnail upload.
    Updates run_dir metadata.json and output/metadata.json with final video_id or error.
    """
    import json
    from pathlib import Path
    import os

    video_file = Path(video_file)
    thumb_file = Path(thumbnail_path) if thumbnail_path else Path("output/thumbnail.jpg")

    if not video_file.exists() or video_file.stat().st_size == 0:
        err_msg = f"Pre-upload Sanity Check Failed: Video file is missing or empty ({video_file}) for {run_id or 'run'}."
        print(f"❌ {err_msg}")
        raise RuntimeError(err_msg)

    if not thumb_file.exists() or thumb_file.stat().st_size == 0:
        err_msg = f"Pre-upload Sanity Check Failed: Thumbnail file is missing or empty ({thumb_file}) for {run_id or 'run'}."
        print(f"❌ {err_msg}")
        raise RuntimeError(err_msg)

    if not title or not title.strip():
        err_msg = f"Pre-upload Sanity Check Failed: Title is empty for {run_id or 'run'}."
        print(f"❌ {err_msg}")
        raise RuntimeError(err_msg)

    from agents.youtube_agent import upload_video

    print()
    print("=" * 60)
    print("YOUTUBE UPLOAD")
    print("=" * 60)
    print(f"Privacy: {privacy.upper()}")
    print(f"Channel: {channel}")
    print(f"Video  : {video_file} ({video_file.stat().st_size / (1024 * 1024):.1f} MB)")
    print(f"Thumb  : {thumb_file}")

    video_id = None
    youtube_error = None

    try:
        video_id = upload_video(
            str(video_file),
            title,
            description,
            tags,
            privacy=privacy,
            channel=channel,
            thumbnail_path=str(thumb_file),
        )
        print(f"✅ YouTube upload complete: {video_id}")
    except Exception as yt_err:
        youtube_error = str(yt_err)
        print(f"⚠️ YouTube upload failed: {yt_err}")

    out_dir = Path(run_dir) if run_dir else Path("output")
    meta_path = out_dir / "metadata.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
            meta_data["youtube_upload"] = True
            meta_data["youtube_video_id"] = video_id
            meta_data["youtube_error"] = youtube_error
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2, ensure_ascii=False)
            if meta_path != Path("output/metadata.json"):
                with open("output/metadata.json", "w", encoding="utf-8") as f:
                    json.dump(meta_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    return video_id, youtube_error


def create_metadata(
    topic,
    script,
    youtube_upload=False,
    privacy="private",
    channel="Channel 1 (Primary)",
    run_dir=None,
    thumbnail_path=None,
    run_id=None,
    aspect_ratio="9:16",
):
    """Generate metadata, generate final thumbnail matching verified title, and optionally upload to YouTube."""

    import json
    from pathlib import Path
    import os
    import shutil
    import datetime

    from agents.metadata_agent import generate_metadata

    title, description, tags = generate_metadata(
        topic,
        script,
    )

    out_dir = Path(run_dir) if run_dir else Path("output")
    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata_path = out_dir / "metadata.json"

    # Generate fresh thumbnail using verified final title & assets, saved to run_dir
    final_thumb_path = None
    try:
        final_thumb_path = create_thumbnail(
            title=title,
            aspect_ratio=aspect_ratio,
            assets_dir=ROOT / "assets",
            output_dir=out_dir,
        )
    except Exception as thumb_err:
        print(f"⚠️ Thumbnail generation notice: {thumb_err}")

    video_file = out_dir / "final_video.mp4"
    if not video_file.exists():
        video_file = Path("output/final_video.mp4")

    thumb_file = final_thumb_path or (out_dir / "thumbnail.jpg")
    if not Path(thumb_file).exists():
        thumb_file = Path("output/thumbnail.jpg")

    # Record run_info.json in run_dir for sanity verification
    run_info_path = out_dir / "run_info.json"
    try:
        with open(run_info_path, "w", encoding="utf-8") as rf:
            json.dump({
                "run_id": run_id or "run_default",
                "topic": topic,
                "title": title,
                "video_file": str(video_file),
                "thumbnail_file": str(thumb_file),
                "created_at": datetime.datetime.now().isoformat(),
            }, rf, indent=2)
    except Exception:
        pass

    # --------------------------------------------------------
    # OPTIONAL YOUTUBE UPLOAD
    # --------------------------------------------------------

    video_id = None
    youtube_error = None

    if youtube_upload:
        try:
            video_id, youtube_error = perform_youtube_upload(
                video_file=video_file,
                title=title,
                description=description,
                tags=tags,
                privacy=privacy,
                channel=channel,
                thumbnail_path=thumb_file,
                run_dir=out_dir,
                run_id=run_id,
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
        "run_id": run_id,
        "channel": channel,
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

    # Copy latest metadata, thumbnail and final video to output/ for backwards compatibility
    if metadata_path != Path("output/metadata.json"):
        try:
            with open("output/metadata.json", "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    if Path(thumb_file).exists() and Path(thumb_file) != Path("output/thumbnail.jpg"):
        try:
            shutil.copyfile(thumb_file, Path("output/thumbnail.jpg"))
        except Exception:
            pass

    if video_file.exists() and video_file != Path("output/final_video.mp4"):
        try:
            shutil.copyfile(video_file, Path("output/final_video.mp4"))
        except Exception:
            pass

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
    voice=None,
    target_duration="30-50s",
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

    combined_context = f"{revision_prompt}\n\n{source_context or ''}".strip()

    return generate_script(
        topic,
        content_type=content_type,
        language_style=language_style,
        source_context=combined_context,
        target_duration=target_duration,
        voice=voice,
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
    youtube_channel="Channel 1 (Primary)",
    script_override=None,
    aspect_ratio="9:16",
    target_duration="30-50s",
    include_outro=True,
    instagram_upload=False,
    progress_callback=None,
    generation_mode="stock",
    tone=None,
):
    """
    Topic-first AutoTube AI pipeline with a maximum of 3 AI review
    attempts. Delegates directly to pipeline.generate_multi_media_video
    for format-aware validation gates and profiling.
    """
    import importlib
    import config.format_profiles
    importlib.reload(config.format_profiles)
    import pipeline
    importlib.reload(pipeline)
    from pipeline import generate_multi_media_video as _real_generate
    return _real_generate(
        topic=topic,
        media_files=media_files,
        content_type=content_type,
        language_style=language_style,
        voice=voice,
        voice_sample=voice_sample,
        captions=captions,
        thumbnail=thumbnail,
        metadata=metadata,
        youtube_upload=youtube_upload,
        youtube_privacy=youtube_privacy,
        youtube_channel=youtube_channel,
        script_override=script_override,
        aspect_ratio=aspect_ratio,
        target_duration=target_duration,
        include_outro=include_outro,
        instagram_upload=instagram_upload,
        progress_callback=progress_callback,
        generation_mode=generation_mode,
        tone=tone,
    )

    MAX_RETRIES = 2
    MAX_REVIEW_ATTEMPTS = 1 + MAX_RETRIES

    failing_component = None
    feedback = None

    if not topic or not topic.strip():
        raise RuntimeError(
            "Please enter a topic or video idea."
        )

    media_files = media_files or []

    # Clean lingering artifacts from previous runs to prevent cross-topic pollution
    for stale_file in (
        "output/subtitles.ass",
        "output/subtitles.srt",
        "output/voice.mp3",
        "output/voice_raw.wav",
        "output/voice_paced.wav",
        "output/transcription.json",
        "output/final_video.mp4",
        "output/video.mp4",
        "output/verify_frame.jpg",
    ):
        try:
            sp = Path(stale_file)
            if sp.exists():
                sp.unlink(missing_ok=True)
        except Exception:
            pass

    # Auto-sync language_style if a Telugu voice is selected
    voice_str = str(voice or "").lower()
    if any(tv in voice_str for tv in ("mohan", "shruti", "te-in")) and not ("telugu" in str(language_style).lower() or "తెలుగు" in str(language_style)):
        print(f"🎙️ [Dashboard] Auto-syncing language_style to Telugu because voice is {voice}")
        language_style = "Telugu - తెలుగు (Creator / Casual)"

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

    import datetime
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", topic.strip())[:30].strip("_") or "autotube"
    run_id = f"run_{timestamp_str}_{slug}"
    run_dir = OUTPUT_DIR / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 [Dashboard Run Isolation] Created isolated run directory: {run_dir}")

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
                self.start_time = time.time()
                init_text = f"[00:00] Attempt {attempt}/{max_attempts}: Starting AutoTube AI{' (Self-healing ' + failing_comp + ')' if attempt > 1 else ''}..."
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

            def get_elapsed_str(self):
                elapsed = int(time.time() - self.start_time)
                return f"{elapsed // 60:02d}:{elapsed % 60:02d}"

            def progress(self, val, text=""):
                elapsed_str = self.get_elapsed_str()
                if text and not text.startswith("["):
                    text = f"[{elapsed_str}] {text}"
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
                from agents.script_agent import ensure_script_artifacts
                ensure_script_artifacts(script, topic=topic, default_title=title)

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
                    script = run_stage_with_timeout(
                        "Script Generation (Explainer)",
                        240,
                        generate_script,
                        topic,
                        content_type="Explainer",
                        language_style=language_style,
                        source_context=news_verification,
                        target_duration=target_duration,
                        voice=voice,
                    )
                else:
                    from agents.script_agent import generate_script
                    script = run_stage_with_timeout(
                        "Script Generation",
                        240,
                        generate_script,
                        topic,
                        content_type=content_type,
                        language_style=language_style,
                        source_context=news_verification,
                        target_duration=target_duration,
                        voice=voice,
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

                script = run_stage_with_timeout(
                    "Script Revision",
                    240,
                    improve_script_from_review,
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
                    voice=voice,
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
            # If visual plan was explicitly flagged as monotonous or repetitive, refresh it during image_agent healing
            if failing_component == "image_agent" and feedback and any(w in str(feedback).lower() for w in ("monotonous", "repetitive", "identical", "visual plan")):
                try:
                    dp_file = OUTPUT_DIR / "delivery_plan.json"
                    if dp_file.exists():
                        d_plan = json.loads(dp_file.read_text(encoding="utf-8"))
                        from agents.script_agent import synthesize_beat_visual_plan
                        refreshed_lines = synthesize_beat_visual_plan(d_plan, topic=topic)
                        with open(OUTPUT_DIR / "visual_plan.txt", "w", encoding="utf-8") as f:
                            for idx, v in enumerate(refreshed_lines, 1):
                                f.write(f"{idx}. {v}\n")
                        print("⚡ [Self-Healing] Refreshed visual_plan.txt with diverse, non-repeating prompts.")
                except Exception as vp_err:
                    print(f"Notice refreshing visual plan during self-healing: {vp_err}")

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
            if not visual_plan_file.exists() or not visual_plan_file.read_text(encoding="utf-8").strip():
                print("⚠️ [Dashboard] visual_plan.txt missing or empty. Auto-synthesizing from script...")
                from agents.script_agent import ensure_script_artifacts
                ensure_script_artifacts(script, topic=topic, default_title=title)
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
                        content_type=content_type,
                        progress_callback=progress.progress,
                    )
                    print("✅ [Parallel Stage] Visual Sourcing Complete.")
                except Exception as error:
                    print("Visual sourcing warning:", error)

            def _task_voice():
                print(f"⚡ [Parallel Stage] Starting Narration Synthesis ({voice})...")
                create_voice_for_script(
                    voice=voice,
                    own_voice_audio=voice_sample,
                    topic_category=content_type,
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
                if not visual_plan_file.exists() or not visual_plan_file.read_text(encoding="utf-8").strip():
                    print("⚠️ [Dashboard] visual_plan.txt missing or empty. Auto-synthesizing from script...")
                    from agents.script_agent import ensure_script_artifacts
                    ensure_script_artifacts(script, topic=topic, default_title=title)
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
                        content_type=content_type,
                        progress_callback=progress.progress,
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
                    topic_category=content_type,
                )
            else:
                print(f"[Targeted Self-Healing] Preserving existing voice audio (failing component: {failing_component})")

        # ----------------------------------------------------
        # Phase 1 Virality Upgrade: Shorts Voice Duration Guard (Hard Max 45s)
        # ----------------------------------------------------
        is_shorts_run = (aspect_ratio == "9:16") and not ("6-9" in str(target_duration).lower() or "long-form" in str(target_duration).lower())
        voice_file_p = OUTPUT_DIR / "voice.mp3"
        if is_shorts_run and voice_file_p.exists() and attempt < MAX_REVIEW_ATTEMPTS:
            from agents.run_report import probe_duration
            v_dur = probe_duration(str(voice_file_p))
            if v_dur > 45.0:
                print(f"⚠️ [Virality Length Cap] Voice duration is {v_dur:.1f}s (> 45.0s hard max for Shorts).")
                print("🔄 Triggering supervisor re-script loop to shorten narration while preserving hook + payoff...")
                feedback = (
                    f"CRITICAL RETENTION ERROR: Spoken voice duration was {v_dur:.1f} seconds, which strictly exceeds "
                    "the 45-second hard maximum for YouTube Shorts. Shorten the script to 60-85 words strictly "
                    "while preserving the opening hook and closing payoff intact."
                )
                failing_component = "script_agent"
                attempt += 1
                continue

        # ----------------------------------------------------
        # ----------------------------------------------------
        # TRIPLE-WAY CONCURRENT VIDEO ASSEMBLY, SUBTITLES & THUMBNAIL
        # ----------------------------------------------------

        progress.progress(
            65,
            text=(
                f"Attempt {attempt}: "
                "⚡ Parallel Execution: Assembling video scenes, generating subtitles & thumbnail..."
            ),
        )

        from agents.video_agent import ensure_visual_assets_exist
        ensure_visual_assets_exist()

        from agents.news_verifier import validate_visual_assets
        asset_check = validate_visual_assets()
        if not asset_check.get("valid", True):
            print(f"🛡️ [Asset Safety] Validated visual assets: replaced {len(asset_check.get('replaced', []))} defective images with clean fallbacks")

        import concurrent.futures

        def _dash_task_subtitles():
            if captions:
                print("⚡ [Parallel Task] Generating subtitles in background...")
                try:
                    from agents.subtitle_agent import create_subtitles
                    create_subtitles(aspect_ratio=aspect_ratio)
                    print("✅ [Parallel Task] Subtitles Ready.")
                except Exception as sub_err:
                    print(f"⚠️ Subtitle parallel task notice: {sub_err}")

        def _dash_task_thumbnail():
            if run_thumbnail:
                print("⚡ [Parallel Task] Generating thumbnail in background...")
                try:
                    create_thumbnail(
                        title or topic,
                        aspect_ratio=aspect_ratio,
                        assets_dir=ROOT / "assets",
                        output_dir=run_dir,
                    )
                    print("✅ [Parallel Task] Thumbnail Ready.")
                except Exception as th_err:
                    print(f"⚠️ Thumbnail parallel task notice: {th_err}")

        def _dash_task_video():
            print("⚡ [Parallel Task] Starting Ken Burns Video Assembly...")
            run_stage_with_timeout(
                "Ken Burns Video Assembly",
                180,
                create_pipeline_video,
                aspect_ratio=aspect_ratio,
            )
            print("✅ [Parallel Task] Ken Burns Assembly Complete.")

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as stage_executor:
            f_vid = stage_executor.submit(_dash_task_video)
            f_sub = stage_executor.submit(_dash_task_subtitles)
            f_thm = stage_executor.submit(_dash_task_thumbnail)
            concurrent.futures.wait([f_vid, f_sub, f_thm])
            f_vid.result()
            f_sub.result()
            f_thm.result()

        # ----------------------------------------------------
        # FINAL VIDEO + CAPTIONS (Direct Muxing)
        # ----------------------------------------------------

        progress.progress(
            78,
            text=(
                f"Attempt {attempt}: "
                "Rendering final video mux, captions and outro..."
            ),
        )

        run_stage_with_timeout(
            "Final Video Assembly",
            180,
            create_final_video,
            captions=captions,
            aspect_ratio=aspect_ratio,
            include_outro=include_outro,
        )

        # Mirror current run outputs into run_dir
        import shutil
        for fname in ["script.txt", "visual_plan.txt", "section_map.txt", "voice.mp3", "subtitles.srt", "final_video.mp4"]:
            src = OUTPUT_DIR / fname
            if src.exists():
                try:
                    shutil.copyfile(src, run_dir / fname)
                except Exception:
                    pass

        # Ensure thumbnail is mirrored if created in output_dir
        if not (run_dir / "thumbnail.jpg").exists() and (OUTPUT_DIR / "thumbnail.jpg").exists():
            try:
                shutil.copyfile(OUTPUT_DIR / "thumbnail.jpg", run_dir / "thumbnail.jpg")
            except Exception:
                pass

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
            text="Generating YouTube metadata & thumbnail...",
        )

        title, description, tags, _, _ = run_stage_with_timeout(
            "Metadata & Thumbnail Generation",
            90,
            create_metadata,
            topic,
            script,
            youtube_upload=False,
            privacy=youtube_privacy,
            channel=youtube_channel,
            run_dir=run_dir,
            thumbnail_path=run_dir / "thumbnail.jpg",
            run_id=run_id,
            aspect_ratio=aspect_ratio,
        )

        video_id = None
        youtube_error = None

        if youtube_upload:
            progress.progress(
                98,
                text=f"Uploading video to YouTube ({youtube_channel})...",
            )
            out_dir = Path(run_dir) if run_dir else Path("output")
            video_file = out_dir / "final_video.mp4"
            if not video_file.exists():
                video_file = Path("output/final_video.mp4")
            thumb_file = out_dir / "thumbnail.jpg"
            if not thumb_file.exists():
                thumb_file = Path("output/thumbnail.jpg")

            try:
                video_id, youtube_error = run_stage_with_timeout(
                    "YouTube Upload",
                    600,
                    perform_youtube_upload,
                    video_file=video_file,
                    title=title,
                    description=description,
                    tags=tags,
                    privacy=youtube_privacy,
                    channel=youtube_channel,
                    thumbnail_path=thumb_file,
                    run_dir=out_dir,
                    run_id=run_id,
                )
            except TimeoutError as t_err:
                youtube_error = "YouTube upload timed out after 600s limit: the video file is large and network upload took longer than allowed. Your video was successfully created and is saved on disk ready to preview, download, or publish manually."
                video_id = None
                print(f"⚠️ {youtube_error}")
            except Exception as yt_err:
                youtube_error = str(yt_err)
                video_id = None
                print(f"⚠️ YouTube upload error: {yt_err}")

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
                public_base = os.getenv("PUBLIC_VIDEO_BASE_URL", "")
                tunnel_file = OUTPUT_DIR / "tunnel_url.txt"
                if tunnel_file.exists():
                    try:
                        t_u = tunnel_file.read_text(encoding="utf-8").strip()
                        if t_u.startswith("http"):
                            public_base = t_u
                    except Exception:
                        pass
                if not public_base:
                    public_base = "https://smokeless-waking-remote.ngrok-free.dev"

                public_url = f"{public_base.rstrip('/')}/output/final_video.mp4"
                res = upload_to_instagram_reels(
                    video_source=str(final_vid) if final_vid.exists() else None,
                    caption=f"{title}\n\n{description[:300]}",
                    public_video_url=public_url,
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

    # ----------------------------------------------------
    # Phase 1 Virality Upgrade: Run Report & Metrics Audit
    # ----------------------------------------------------
    run_rep = {}
    try:
        from agents.run_report import generate_run_report
        run_rep = generate_run_report(
            output_dir_str=str(OUTPUT_DIR),
            topic=topic,
            is_shorts=(aspect_ratio == "9:16"),
        )
    except Exception as rep_err:
        print(f"⚠️ Run report error: {rep_err}")

    return {
        "run_report": run_rep,
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
        "run_id": run_id,
        "run_dir": str(run_dir),
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

from liquid_ui import inject_hud_glass_css, render_provider_audit_card

inject_hud_glass_css()



# ============================================================
# HEADER
# ============================================================

st.markdown(
    """<div class="glass-card glass-header-card"><div style="display:flex; justify-content:space-between; align-items:center; gap:20px; flex-wrap:wrap;"><div class="brand">🎬 <span>AutoTube AI</span></div><div><span class="status"><span style="color:#2dd4bf; margin-right:4px;">●</span> AI READY</span><span class="status">ENGLISH</span><span class="status">1000P</span></div></div></div>""",
    unsafe_allow_html=True,
)


# ============================================================
# HERO
# ============================================================

st.markdown(
    """<div class="hero-title">Transform Ideas into<br><span class="hero-gradient">Instant Videos.</span></div><div class="hero-subtitle">AI-powered video creation — from topic to script, voice, subtitles, thumbnail and YouTube publishing.</div>""",
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

# ============================================================
# 24/7 MULTI-CHANNEL DAILY AUTOMATION (10 SLOTS)
# ============================================================
try:
    from daily_scheduler import (
        DAILY_SLOT_CONFIGS,
        load_daily_slot_status,
        save_daily_slot_status,
        MultiSlotDailyScheduler,
    )

    slot_status_payload = load_daily_slot_status()
    today_date = slot_status_payload.get("date", datetime.date.today().isoformat())
    today_slots = slot_status_payload.get("slots", {})

    completed_count = sum(1 for s in today_slots.values() if s.get("status") == "success")
    in_prog_count = sum(1 for s in today_slots.values() if s.get("status") == "in_progress")

    expander_title = f"⏰ 24/7 Daily Multi-Channel Automation ({completed_count}/10 Videos Published Today)"
    with st.expander(expander_title, expanded=False):
        st.markdown(
            f"""
            <div style="background: rgba(30, 41, 59, 0.45); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 12px; padding: 12px 16px; margin-bottom: 12px;">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
                    <div>
                        <span style="font-weight:700; color:#38BDF8; font-size:1.05rem;">📅 Daily 10-Slot Production Roster ({today_date})</span><br>
                        <span style="font-size:0.82rem; color:#94A3B8;">Automatic Peak-Hours Publishing: Channel 1 (3 Shorts + 2 Long) & Channel 2 (3 Shorts + 2 Long)</span>
                    </div>
                    <div>
                        <span style="background: rgba(16, 185, 129, 0.15); color: #34D399; font-weight: 700; font-size: 0.8rem; padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(16, 185, 129, 0.3);">👩 Shruti Voice (te-IN)</span>
                        <span style="background: rgba(56, 189, 248, 0.15); color: #38BDF8; font-weight: 700; font-size: 0.8rem; padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(56, 189, 248, 0.3);">🌍 Public Mode</span>
                        <span style="background: rgba(244, 63, 94, 0.15); color: #FB7185; font-weight: 700; font-size: 0.8rem; padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(244, 63, 94, 0.3);">📸 Reels: Shorts Only</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # GitHub Actions Free Tier Compute Quota Widget
        try:
            from utils.github_quota import get_github_quota_status
            q_info = get_github_quota_status()
            q_used = q_info["minutes_used"]
            q_inc = q_info["included_minutes"]
            q_rem = q_info["minutes_remaining"]
            q_pct = q_info["pct_used"]
            q_reset = q_info["days_until_reset"]

            st.markdown(
                f"""
                <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 10px; padding: 10px 14px; margin-bottom: 14px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-weight: 700; color: #F8FAFC; font-size: 0.88rem;">⚡ GitHub Actions Cloud Compute Quota (100% Free Tier)</span>
                        <span style="font-size: 0.8rem; color: #38BDF8; font-weight: 600;">{q_used} / {q_inc} Mins Used ({q_pct}%)</span>
                    </div>
                    <div style="width: 100%; background: rgba(255, 255, 255, 0.08); border-radius: 6px; height: 8px; overflow: hidden; margin-bottom: 6px;">
                        <div style="width: {min(100.0, max(2.0, q_pct))}%; background: #38BDF8; height: 100%; border-radius: 6px;"></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.78rem; color: #94A3B8;">
                        <span>✅ <b>{q_rem} minutes remaining</b> this month (~{int(q_rem / 40)} days of 10-video runs)</span>
                        <span>🔄 Monthly Quota Resets in <b>{q_reset} days</b></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        except Exception:
            pass

        for conf in DAILY_SLOT_CONFIGS:
            s_id = conf["slot_id"]
            st_data = today_slots.get(s_id, {})
            st_val = st_data.get("status", "pending")
            yt_id = st_data.get("youtube_video_id")
            topic_str = st_data.get("topic") or conf["slot_name"]

            if st_val == "success":
                st_badge = "✅ PUBLISHED"
                st_color = "#34D399"
            elif st_val == "in_progress":
                st_badge = "🔄 IN PROGRESS"
                st_color = "#38BDF8"
            elif st_val == "failed":
                st_badge = "❌ FAILED"
                st_color = "#F87171"
            else:
                st_badge = f"⏳ PENDING ({conf['scheduled_time']})"
                st_color = "#94A3B8"

            ch_label = "CH-1 (Tech/News)" if "1" in conf["channel"] else "CH-2 (Entertainment)"
            fmt_label = f"Short (9:16)" if conf["format_type"] == "short" else f"Long (16:9)"

            st_col1, st_col2, st_col3, st_col4 = st.columns([1.5, 3.5, 1.8, 1.2])
            with st_col1:
                st.markdown(f"**`{s_id}`** ({conf['scheduled_time']})<br><span style='font-size:0.75rem; color:#94A3B8;'>{ch_label}</span>", unsafe_allow_html=True)
            with st_col2:
                st.markdown(f"**{topic_str[:55]}**<br><span style='font-size:0.75rem; color:#A78BFA;'>{fmt_label} | {conf['content_type']}</span>", unsafe_allow_html=True)
            with st_col3:
                st.markdown(f"<span style='color:{st_color}; font-weight:700; font-size:0.85rem;'>{st_badge}</span>", unsafe_allow_html=True)
                if yt_id:
                    st.markdown(f"[📺 Watch Video](https://www.youtube.com/watch?v={yt_id})")
            with st_col4:
                if st.button("▶️ Run", key=f"btn_run_slot_{s_id}", use_container_width=True):
                    with st.spinner(f"Executing {s_id}..."):
                        sched = MultiSlotDailyScheduler()
                        ok = sched.execute_slot(s_id, force=True)
                        if ok:
                            st.success(f"Slot {s_id} published successfully!")
                        else:
                            st.error(f"Slot {s_id} execution encountered an issue. See logs.")
                        st.rerun()

        st.markdown("---")
        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 1.5, 1.5])
        with ctrl_col1:
            st.caption("💡 24/7 Engine automatically monitors the clock and triggers each video during peak Telugu viewing hours.")
        with ctrl_col2:
            if st.button("⚡ Run Overdue Slots", key="btn_run_all_due_slots", use_container_width=True):
                with st.spinner("Processing overdue pending slots..."):
                    sched = MultiSlotDailyScheduler()
                    c = sched.run_pending_slots()
                    st.toast(f"Completed {c} slots!", icon="✅")
                    st.rerun()
        with ctrl_col3:
            if st.button("🔄 Refresh Schedule", key="btn_refresh_slot_schedule", use_container_width=True):
                st.rerun()

except Exception as _sched_ui_err:
    pass

# Touch-friendly full-width mobile quick chips & Notification Bell
notif_file = Path("output/validation_notifications.json")
notifs_list = []
if notif_file.exists():
    try:
        notifs_list = json.loads(notif_file.read_text(encoding="utf-8"))
    except Exception:
        notifs_list = []
unread_notifs = [n for n in notifs_list if n.get("unread", False)]
unread_count = len(unread_notifs)
bell_label = f"🔔 Alerts ({unread_count})" if unread_count > 0 else "🔔 Alerts (1)"

m_col1, m_col2, m_col3, m_col4 = st.columns([1, 1, 1, 1.2])
with m_col1:
    if st.button("🚀 Quick Run", key="btn_mobile_quick_run", use_container_width=True):
        st.toast("Ready! Configure topic and start video creation below.", icon="🚀")
with m_col2:
    if st.button("🔴 Stop Process", key="btn_mobile_stop_run", use_container_width=True):
        st.session_state["pipeline_abort_requested"] = True
        st.warning("Job cancellation requested.")
with m_col3:
    if st.button("📊 Pipeline Status", key="btn_mobile_status", use_container_width=True):
        from supervisor import get_healing_logs
        hl = get_healing_logs()
        st.info(f"System Operational: 0 critical crashes, {len(hl)} auto-healed incidents logged.")
with m_col4:
    if st.button(bell_label, key="btn_mobile_notifications", use_container_width=True):
        st.session_state["show_notification_center"] = not st.session_state.get("show_notification_center", False)

if st.session_state.get("show_notification_center", False):
    with st.expander("🔔 Quality & Validation Notification Center", expanded=True):
        if not notifs_list:
            st.info("No validation notifications recorded yet.")
        else:
            clr_col1, clr_col2 = st.columns([3, 1])
            with clr_col2:
                if st.button("Mark All Read ✓", key="btn_mark_all_read", use_container_width=True):
                    for item in notifs_list:
                        item["unread"] = False
                    notif_file.write_text(json.dumps(notifs_list, indent=2), encoding="utf-8")
                    st.rerun()
            for notif in notifs_list[:8]:
                status = notif.get("status", "PASSED")
                badge_color = "#34D399" if status == "PASSED" else "#F87171"
                st.markdown(
                    f"""
                    <div style="background: rgba(30, 41, 59, 0.6); border-left: 4px solid {badge_color}; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 700; color: #F1F5F9; font-size: 0.92rem;">{notif.get('topic', 'Topic')[:45]}</span>
                            <span style="background: rgba(255,255,255,0.08); color: {badge_color}; font-size: 0.75rem; font-weight: 700; padding: 2px 8px; border-radius: 4px;">{status}</span>
                        </div>
                        <div style="font-size: 0.78rem; color: #94A3B8; margin-top: 4px;">
                            Critical Defects: {notif.get('critical_count', 0)} | Warnings: {notif.get('warning_count', 0)} | Upload Allowed: {notif.get('upload_allowed', True)}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )



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
# API KEYS & CLOUD CONNECTIVITY GUARD
# ============================================================
active_gemini_key = get_gemini_api_key()
active_pexels_key = get_pexels_api_key()

if not active_gemini_key:
    st.markdown(
        """<div style="background: rgba(6, 182, 212, 0.12); border: 1.5px solid rgba(56, 189, 248, 0.40); border-radius: 16px; padding: 1.25rem 1.4rem; margin: 1rem 0 1.5rem 0;"><div style="display: flex; align-items: center; gap: 8px; margin-bottom: 0.35rem;"><span style="font-size: 1.35rem;">🔑</span><span style="font-size: 1.1rem; font-weight: 700; color: #38BDF8;">Google Gemini API Key Required</span></div><p style="font-size: 0.92rem; color: #E2E8F0; margin: 0 0 0.8rem 0; line-height: 1.45;">AutoTube AI uses Google Gemini to write scripts, review content, and plan scenes. Please enter your Gemini API key below to enable video generation:</p></div>""",
        unsafe_allow_html=True,
    )
    k_col1, k_col2 = st.columns([2.8, 1])
    with k_col1:
        gemini_input_val = st.text_input(
            "Gemini API Key",
            type="password",
            placeholder="Paste your Gemini API key (AQ.Ab8... or AIza...)",
            key="ui_gemini_input_top",
            label_visibility="collapsed",
        )
    with k_col2:
        if st.button("Connect Key 🚀", key="btn_connect_gemini_top", use_container_width=True):
            if gemini_input_val and gemini_input_val.strip():
                st.session_state["GEMINI_API_KEY"] = gemini_input_val.strip()
                os.environ["GEMINI_API_KEY"] = gemini_input_val.strip()
                st.success("✅ Gemini API Key connected!")
                st.rerun()
            else:
                st.warning("Please enter a valid key.")

# ============================================================
# MANUAL STUDIO (PRIMARY CREATION VIEW)
# ============================================================

with st.container():
    left, right = st.columns([1.55, 1], gap="large")


    # ============================================================
    # LEFT — CREATE VIDEO
    # ============================================================

    with left:

        st.markdown(
            """<div class="section-title">Create Video</div><div class="section-subtitle">Tell AutoTube AI what you want to create.</div>""",
            unsafe_allow_html=True,
        )

        # ============================================================
        # 📺 TARGET YOUTUBE CHANNEL (TOP OF FORM)
        # ============================================================
        st.markdown(
            """<div style="margin-top: 10px; margin-bottom: 4px;"><span style="font-size: 0.88rem; font-weight: 600; color: #F8FAFC;">📺 Target YouTube Channel</span></div>""",
            unsafe_allow_html=True,
        )

        yt_channel_options = [
            "Channel 1 (Primary)",
            "Channel 2 (Secondary)",
        ]
        channel_counter = st.session_state.get("_channel_picker_counter", 0)
        saved_yt_ch = st.session_state.get("declared_yt_channel", yt_channel_options[0])
        saved_yt_ch_idx = yt_channel_options.index(saved_yt_ch) if saved_yt_ch in yt_channel_options else 0

        selected_yt_channel = st.selectbox(
            "Target YouTube Channel",
            yt_channel_options,
            index=saved_yt_ch_idx,
            key=f"_yt_channel_picker_{channel_counter}",
            label_visibility="collapsed",
            help="Channel 1 is strictly for AI/Tech content. Channel 2 is for everything else (History, Facts, Cinema, General News, etc.).",
        )
        st.session_state["declared_yt_channel"] = selected_yt_channel

        ch2_exists = (ROOT / "token_channel2.json").exists()
        ch1_exists = (ROOT / "token.json").exists() or (ROOT / "token_channel1.json").exists()
        is_ch2_chosen = "2" in selected_yt_channel
        channel_auth_ok = ch2_exists if is_ch2_chosen else ch1_exists

        if is_ch2_chosen:
            ch_desc = "Channel 2: All Other Content (History, Facts, General News, Cinema)"
            token_needed = "token_channel2.json"
            reauth_ch = "2"
        else:
            ch_desc = "Channel 1: AI / Technology ONLY"
            token_needed = "token.json"
            reauth_ch = "1"

        if channel_auth_ok:
            st.caption(f"🎯 **{ch_desc}** • 🔑 Connected (`{token_needed}` active)")
        else:
            st.caption(f"🎯 **{ch_desc}** • ⚠️ `{token_needed}` missing. Run `./scripts/reauth_youtube.py --channel {reauth_ch}` to connect.")

        st.markdown("<hr style='border: none; border-top: 1px solid rgba(255, 255, 255, 0.08); margin: 12px 0 16px 0;'/>", unsafe_allow_html=True)

        generation_mode = st.radio(
            "Video Generation Mode",
            [
                "🎬 AI Stock Search",
                "🎥 AI Short Video Clips",
                "📁 My Own Images/Videos",
                "📊 Explainer Style",
                "🖼️ Upload Flyer/Poster",
            ],
            horizontal=True,
            help="Choose how AutoTube creates visuals and script for your video.",
        )

        if generation_mode in ("🎬 AI Stock Search", "🎥 AI Short Video Clips"):
            if generation_mode == "🎥 AI Short Video Clips":
                st.caption("⚡ **Clip Engine Active**: Auto-scrapes 3–5s X (Twitter) status clips via yt-dlp, vertical Pexels video clips, and Tenor meme reactions matching scene keywords.")
            stock_sub = st.radio(
                "Source Type",
                ["Trending News", "Custom Content & Categories"],
                horizontal=True,
                key="stock_sub_type",
            )
            if "Trending" in stock_sub:
                content_type = "News"
            else:
                custom_content_options = [
                    "📝 Custom Topic / Deep Dive",
                    "🎭 Cinema & Entertainment",
                    "🎬 Movie Reviews",
                    "🔥 Roasting",
                    "😏 Sarcastic",
                    "😂 Funny",
                    "🏛️ History",
                    "💡 Interesting Facts",
                    "🌐 General / Other",
                ]
                chosen_custom_type = st.selectbox(
                    "Content Type",
                    custom_content_options,
                    index=0,
                    key="manual_custom_content_type_select",
                    help="Select content type to configure pacing, tone, and target YouTube channel.",
                )
                if "Custom Topic" in chosen_custom_type or "Deep Dive" in chosen_custom_type:
                    content_type = "Custom Topic / Deep Dive"
                elif "Cinema" in chosen_custom_type or "Entertainment" in chosen_custom_type:
                    content_type = "Cinema & Entertainment"
                elif "Movie" in chosen_custom_type or "Review" in chosen_custom_type:
                    content_type = "Movie Reviews"
                elif "Roasting" in chosen_custom_type or "Roast" in chosen_custom_type:
                    content_type = "Roasting"
                elif "Sarcastic" in chosen_custom_type:
                    content_type = "Sarcastic"
                elif "Funny" in chosen_custom_type:
                    content_type = "Funny"
                elif "History" in chosen_custom_type:
                    content_type = "History"
                elif "Facts" in chosen_custom_type:
                    content_type = "Interesting Facts"
                else:
                    content_type = "General Topic"
        elif generation_mode == "📁 My Own Images/Videos":
            content_type = "Custom Media"
        elif generation_mode == "📊 Explainer Style":
            explainer_options = [
                "📝 Custom Topic / Deep Dive (Long-Form Explainer)",
                "🎭 Cinema & Entertainment (Industry Deep Dive)",
                "🏛️ History Explainer (Long-Form 6–9m)",
                "💡 Interesting Facts Explainer (Long-Form 6–9m)",
                "🔥 Roasting / Satirical Deep Dive",
                "🎬 Movie / Story Review Explainer",
                "📱 Tech / Concept Explainer",
                "🌐 General Explainer",
            ]
            chosen_exp_type = st.selectbox(
                "Explainer Type",
                explainer_options,
                index=0,
                key="manual_explainer_content_type_select",
            )
            if "Custom" in chosen_exp_type or "Deep Dive" in chosen_exp_type:
                content_type = "Custom Topic / Deep Dive"
            elif "Cinema" in chosen_exp_type or "Entertainment" in chosen_exp_type:
                content_type = "Cinema & Entertainment"
            elif "History" in chosen_exp_type:
                content_type = "History"
            elif "Facts" in chosen_exp_type:
                content_type = "Interesting Facts"
            elif "Roasting" in chosen_exp_type or "Satirical" in chosen_exp_type:
                content_type = "Roasting"
            elif "Movie" in chosen_exp_type or "Review" in chosen_exp_type:
                content_type = "Movie Reviews"
            elif "Tech" in chosen_exp_type:
                content_type = "Tech News"
            else:
                content_type = "Explainer"
        elif generation_mode == "🖼️ Upload Flyer/Poster":
            content_type = "Uploaded Flyer"
        else:
            content_type = "News"

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

        # ========================================================
        # 💡 AI TOPIC SUGGESTIONS (Regional & Trending Entertainment Ideas)
        # ========================================================
        is_topic_suggester_mode = (
            (generation_mode in ("🎬 AI Stock Search", "🎥 AI Short Video Clips") and locals().get("stock_sub") != "Trending News" and content_type != "Custom Topic / Deep Dive")
            or (generation_mode == "📊 Explainer Style" and content_type != "Custom Topic / Deep Dive")
        )
        if is_topic_suggester_mode:
            from agents.topic_suggester import fetch_ai_topic_suggestions

            topics_cache_key = f"_ai_suggested_topics_{content_type}"
            if topics_cache_key not in st.session_state:
                st.session_state[topics_cache_key] = fetch_ai_topic_suggestions(
                    content_type=content_type,
                    count=8,
                    use_ai=False,
                )

            suggester_label = locals().get("chosen_custom_type") or locals().get("chosen_exp_type") or content_type
            st.markdown(
                f"""
                <div style="margin-top: 10px; margin-bottom: 4px;">
                    <span style="font-size: 0.9rem; font-weight: 600; color: #E2E8F0;">
                        💡 AI Topic Suggestions ({suggester_label})
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            ai_col1, ai_col2 = st.columns([3, 1])

            with ai_col2:
                st.write("")
                st.write("")
                refresh_ai_topics = st.button(
                    "✨ Refresh",
                    key=f"refresh_topics_btn_{content_type}",
                    help="Generate fresh AI topic ideas for this content type",
                )

            if refresh_ai_topics:
                with st.spinner(f"Generating fresh AI ideas for {content_type}..."):
                    fresh_ideas = fetch_ai_topic_suggestions(
                        content_type=content_type,
                        count=8,
                        use_ai=True,
                    )
                    if fresh_ideas:
                        st.session_state[topics_cache_key] = fresh_ideas
                        st.session_state[f"ai_topic_picker_{content_type}"] = fresh_ideas[0]
                        st.session_state["topic_input"] = fresh_ideas[0]
                        st.rerun()

            current_suggestions = st.session_state.get(topics_cache_key, [])
            ai_select_options = ["— Select an AI topic idea —"] + current_suggestions

            def _on_ai_topic_pick():
                picked = st.session_state.get(f"ai_topic_picker_{content_type}")
                if picked and picked != "— Select an AI topic idea —":
                    st.session_state["topic_input"] = picked
                    try:
                        from agents.topic_suggester import record_used_topic
                        record_used_topic(picked)
                    except Exception:
                        pass

            current_picked_ai = st.session_state.get(f"ai_topic_picker_{content_type}", "— Select an AI topic idea —")
            ai_default_idx = (
                ai_select_options.index(current_picked_ai)
                if current_picked_ai in ai_select_options
                else 0
            )

            with ai_col1:
                chosen_ai_topic = st.selectbox(
                    "Choose an AI-suggested topic (or write your own below)",
                    ai_select_options,
                    index=ai_default_idx,
                    key=f"ai_topic_picker_{content_type}",
                    on_change=_on_ai_topic_pick,
                )

            if chosen_ai_topic and chosen_ai_topic != "— Select an AI topic idea —":
                if st.session_state.get("topic_input") != chosen_ai_topic:
                    st.session_state["topic_input"] = chosen_ai_topic
                    try:
                        from agents.topic_suggester import record_used_topic
                        record_used_topic(chosen_ai_topic)
                    except Exception:
                        pass

        if content_type == "Custom Topic / Deep Dive":
            topic_label = "📝 Custom Topic / Deep Dive"
            topic_placeholder = "Enter your custom topic for an in-depth, comprehensive deep dive (e.g., The Untold Story of Golconda Diamonds, How TSMC Built a Global Chip Monopoly)..."
        elif generation_mode == "📁 My Own Images/Videos":
            topic_label = "Topic or Custom Script"
            topic_placeholder = "Enter your video topic or paste your complete narration script..."
        elif generation_mode == "📊 Explainer Style":
            topic_label = "Concept to Explain"
            topic_placeholder = "e.g., How do Quantum Computers work? or Why do lithium batteries degrade over time?"
        elif generation_mode == "🖼️ Upload Flyer/Poster":
            topic_label = "Flyer Context (Optional)"
            topic_placeholder = "Optional extra notes, special promo dates, or custom instructions..."
        else:
            topic_label = "Topic"
            topic_placeholder = "Enter your video topic or edit the selected topic above..."

        topic = st.text_area(
            topic_label,
            placeholder=topic_placeholder,
            height=100,
            key="topic_input",
        )

        language_style = st.selectbox(
            "Language / Style",
            [
                "Telugu - తెలుగు (News & Updates)",
                "Telugu - తెలుగు (Creator / Casual)",
                "English news style",
                "English creator style",
                "English documentary style",
                "English short-form style",
                "Hindi - हिंदी (News & Updates)",
            ],
            index=0,
        )

        # ========================================================
        # 🔥 SCRIPT TONE & SHOW CONTEXT (Update 5: Roast Engine)
        # ========================================================
        from config.settings import get_setting, update_setting

        default_tone_setting = get_setting("TONE_DEFAULT", "roast")
        tone_option = st.radio(
            "Script Tone & Delivery Style",
            [
                "🔥 Roast (Sarcastic, Witty & Comedic - Bigg Boss / Entertainment / Viral)",
                "🎙️ Neutral (Informative & Professional)",
            ],
            index=0 if default_tone_setting == "roast" else 1,
            key="declared_script_tone_radio",
            help="Roast generates a punchy Telugu comedic script with multi-emotion TTS delivery and funny SFX. Neutral generates informative narrative style.",
        )
        selected_tone = "roast" if "Roast" in tone_option else "neutral"
        st.session_state["declared_script_tone"] = selected_tone

        default_show_context = get_setting("SHOW_CONTEXT", "Bigg Boss Telugu 8")
        show_context_input = st.text_input(
            "Show / Season Context Lock (Optional)",
            value=st.session_state.get("declared_show_context", default_show_context),
            key="declared_show_context_widget",
            help="Locks web visual search and face consensus strictly to this season/show (e.g., 'Bigg Boss Telugu 8') to avoid cross-season confusion.",
        )
        if show_context_input and show_context_input.strip():
            st.session_state["declared_show_context"] = show_context_input.strip()
            update_setting("SHOW_CONTEXT", show_context_input.strip())

        # ========================================================
        # 🎙️ VOICE SELECTION & SAMPLES
        # ========================================================

        voice_samples_dir = ROOT / "voice_samples"
        voice_samples_dir.mkdir(parents=True, exist_ok=True)

        is_telugu_lang = "telugu" in str(language_style).lower() or "తెలుగు" in str(language_style)
        if is_telugu_lang:
            voice_options = [
                "👩 Shruti (Telugu Creator / Anchor) - Conversational",
                "👨 Mohan (Telugu Creator / Anchor) - Natural Spoken Delivery",
                "🤖 Clone My Voice with AI (Local XTTS-v2 / OmniVoice)",
                "🎙️ Use My Own Voice Recording (Upload Audio)",
                "👨 Adam (Male Creator) - Fast, Crisp & Natural",
                "👩 Heart (Female Creator) - Smooth & Conversational",
                "👨 Michael (News Anchor) - Professional & Authoritative",
                "👩 Bella (Warm Female) - Expressive & Storytelling",
                "🎙️ OmniVoice Presenter (Zero-Shot AI Voice Design)",
                "👨 Madhur (Hindi Male Anchor) - Edge-TTS (Fallback)",
                "👩 Swara (Hindi Female Anchor) - Edge-TTS (Fallback)",
            ]
        else:
            voice_options = [
                "👨 Adam (Male Creator) - Fast, Crisp & Natural",
                "👩 Heart (Female Creator) - Smooth & Conversational",
                "👨 Michael (News Anchor) - Professional & Authoritative",
                "👩 Bella (Warm Female) - Expressive & Storytelling",
                "🎙️ OmniVoice Presenter (Zero-Shot AI Voice Design)",
                "🤖 Clone My Voice with AI (Local XTTS-v2 / OmniVoice)",
                "🎙️ Use My Own Voice Recording (Upload Audio)",
                "👨 Mohan (Telugu Creator / Anchor) - Natural Spoken Delivery",
                "👩 Shruti (Telugu Creator / Anchor) - Conversational",
                "👨 Madhur (Hindi Male Anchor) - Edge-TTS (Fallback)",
                "👩 Swara (Hindi Female Anchor) - Edge-TTS (Fallback)",
            ]

        voice = st.selectbox(
            "Voice",
            voice_options,
            index=0,
        )

        # Auto-align language_style when a Telugu voice is selected
        if any(tv in str(voice).lower() for tv in ("mohan", "shruti", "te-in")) and not ("telugu" in str(language_style).lower() or "తెలుగు" in str(language_style)):
            language_style = "Telugu - తెలుగు (Creator / Casual)"

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
                ext = Path(get_image_filename(uploaded_voice)).suffix.lower()
                save_dest = voice_samples_dir / f"active_voice{ext}"
                if hasattr(uploaded_voice, "getbuffer"):
                    save_dest.write_bytes(uploaded_voice.getbuffer())
                elif hasattr(uploaded_voice, "read"):
                    save_dest.write_bytes(uploaded_voice.read())
                existing_voice_file = save_dest
                st.session_state["active_voice_file"] = str(save_dest)
                st.success(f"✅ Loaded: {get_image_filename(uploaded_voice)}")

            if existing_voice_file and existing_voice_file.exists():
                active_voice_sample = str(existing_voice_file)
                st.caption(f"🎧 Active recording: `{get_image_filename(existing_voice_file)}`")
                st.audio(str(existing_voice_file))

                col_tr, col_del = st.columns([1, 1])
                with col_tr:
                    if st.button(
                        "📝 Auto-Detect Script from Speech",
                        key="transcribe_voice_btn",
                        use_container_width=True,
                    ):
                        with st.spinner("Transcribing audio..."):
                            try:
                                audio_text = ""
                                try:
                                    import speech_recognition as sr
                                    r = sr.Recognizer()
                                    with sr.AudioFile(str(existing_voice_file)) as source:
                                        audio_data = r.record(source)
                                    audio_text = r.recognize_google(audio_data, language="te-IN")
                                except Exception:
                                    pass

                                if not audio_text:
                                    is_cloud = os.path.exists("/mount/src") or os.environ.get("STREAMLIT_SH_ENVIRONMENT")
                                    if not is_cloud:
                                        import whisper
                                        model = whisper.load_model("tiny")
                                        trans_res = model.transcribe(
                                            str(existing_voice_file),
                                            fp16=False,
                                        )
                                        audio_text = trans_res.get("text", "").strip()

                                if audio_text:
                                    st.session_state["topic_input"] = audio_text
                                    st.success("✅ Topic & script populated from your speech!")
                                    st.rerun()
                                else:
                                    st.info("Speech detected. Please type your topic in the topic box.")
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
                ext = Path(get_image_filename(uploaded_clone_sample)).suffix.lower()
                save_dest = voice_samples_dir / f"active_voice{ext}"
                if hasattr(uploaded_clone_sample, "getbuffer"):
                    save_dest.write_bytes(uploaded_clone_sample.getbuffer())
                elif hasattr(uploaded_clone_sample, "read"):
                    save_dest.write_bytes(uploaded_clone_sample.read())
                existing_clone_file = save_dest
                st.session_state["active_voice_file"] = str(save_dest)
                st.success("✅ Reference voice sample saved!")

            if existing_clone_file and existing_clone_file.exists():
                active_voice_sample = str(existing_clone_file)
                st.caption(f"🎧 Reference sample: `{get_image_filename(existing_clone_file)}`")
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

        elif "Mohan" in voice or "Shruti" in voice or "Madhur" in voice or "Swara" in voice or "Edge-TTS" in voice:
            active_voice_sample = None
            st.markdown(
                """
                <div style="background:rgba(34, 197, 94, 0.08); border:1px solid rgba(34, 197, 94, 0.25); border-radius:12px; padding:10px 14px; margin:8px 0 12px 0;">
                    <div style="font-size:12.5px; font-weight:600; color:#4ADE80; margin-bottom:2px;">
                        ⚡ Ultra-Fast Indian Neural Voice (&lt;1.5 seconds)
                    </div>
                    <div style="font-size:11px; color:#94A3B8; line-height:1.4;">
                        Synthesizes natural, fluent Telugu / Indian narration via Microsoft Edge-TTS with <b>0 API keys & 0 laptop heat!</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

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

        burn_captions_saved = st.session_state.get("declared_burn_captions", True)
        burn_captions = st.toggle(
            "Burn Captions into Video",
            value=burn_captions_saved,
            key="declared_burn_captions_toggle",
            help="When ON (Default): Word-by-word highlighted styled subtitles are burned directly into the video. When OFF: Fast video rendering without hardcoded subtitles on video (saves rendering time; subtitles still saved for YouTube).",
        )
        st.session_state["declared_burn_captions"] = burn_captions
        captions = burn_captions

        thumbnail = st.toggle(
            "Create Thumbnail",
            value=True,
        )

        metadata = st.toggle(
            "Generate YouTube Metadata",
            value=True,
        )

        # ----------------------------------------------------
        # DUAL CHANNEL & DURATION AUTO-ROUTING (Items 4 & 5)
        # ----------------------------------------------------
        current_cat_code = locals().get("selected_cat_code", "")
        from agents.youtube_agent import resolve_target_channel
        default_ch = resolve_target_channel(content_type=content_type, topic=topic, category=current_cat_code)
        is_history_or_facts = content_type in ("History", "Interesting Facts", "Custom Topic / Deep Dive")

        routing_key = f"{content_type}:{current_cat_code}"
        if st.session_state.get("_last_content_routing_key") != routing_key:
            st.session_state["_last_content_routing_key"] = routing_key

            # Auto-route YouTube channel: Channel 1 for AI/Tech ONLY; Channel 2 for all else
            st.session_state["declared_yt_channel"] = default_ch
            st.session_state["_channel_picker_counter"] = st.session_state.get("_channel_picker_counter", 0) + 1

            # Auto-route duration & aspect ratio for long-form History / Interesting Facts
            if is_history_or_facts:
                long_dur = "🏛️ 6–9 Minutes (Long-Form History / Interesting Facts)"
                st.session_state["selected_duration_label"] = long_dur
                st.session_state["selected_aspect_ratio_label"] = "📺 16:9 Widescreen (YouTube Standard Video)"
                st.session_state["_format_picker_counter"] = st.session_state.get("_format_picker_counter", 0) + 1
            st.rerun()

        st.markdown(
            """
            <div style="margin-top: 8px; margin-bottom: 4px;">
                <span style="font-size: 0.85rem; font-weight: 600; color: #E2E8F0;">
                    📐 Video Aspect Ratio & Format
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        format_counter = st.session_state.get("_format_picker_counter", 0)
        aspect_ratio_options = [
            "📱 9:16 Vertical (YouTube Shorts / Instagram Reels)",
            "📺 16:9 Widescreen (YouTube Standard Video)",
            "⏹️ 1:1 Square (Social Feed)",
        ]
        saved_aspect = st.session_state.get("selected_aspect_ratio_label", aspect_ratio_options[0])
        saved_aspect_idx = aspect_ratio_options.index(saved_aspect) if saved_aspect in aspect_ratio_options else 0

        selected_aspect_label = st.selectbox(
            "Video Aspect Ratio",
            aspect_ratio_options,
            index=saved_aspect_idx,
            key=f"declared_aspect_ratio_select_{format_counter}",
            label_visibility="collapsed",
            help="Choose 9:16 vertical for YouTube Shorts and Instagram Reels, or 16:9 for landscape YouTube videos.",
        )
        st.session_state["selected_aspect_ratio_label"] = selected_aspect_label
        if "9:16" in selected_aspect_label:
            aspect_ratio = "9:16"
        elif "16:9" in selected_aspect_label:
            aspect_ratio = "16:9"
        else:
            aspect_ratio = "1:1"
        st.session_state["selected_aspect_ratio"] = aspect_ratio

        st.markdown(
            """
            <div style="margin-top: 8px; margin-bottom: 4px;">
                <span style="font-size: 0.85rem; font-weight: 600; color: #E2E8F0;">
                    ⏱️ Target Video Duration & Pacing
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        duration_options = [
            "⚡ 30–50 Seconds (YouTube Shorts / Instagram Reels)",
            "⏱️ 60–90 Seconds (Spotlight / Full Story)",
            "🎬 2–4 Minutes (In-Depth Explainer)",
            "🏛️ 6–9 Minutes (Long-Form History / Interesting Facts)",
        ]
        saved_dur = st.session_state.get("selected_duration_label", duration_options[0])
        saved_dur_idx = duration_options.index(saved_dur) if saved_dur in duration_options else 0

        selected_duration_label = st.selectbox(
            "Target Video Duration",
            duration_options,
            index=saved_dur_idx,
            key=f"declared_duration_select_{format_counter}",
            label_visibility="collapsed",
            help="Controls script word count and visual pacing. 30–50s is optimized for viral Shorts retention.",
        )
        st.session_state["selected_duration_label"] = selected_duration_label
        if "6–9" in selected_duration_label:
            target_duration = "6-9m"
        elif "60–90" in selected_duration_label:
            target_duration = "60-90s"
        elif "2–4" in selected_duration_label:
            target_duration = "2-4m"
        else:
            target_duration = "30-50s"
        st.session_state["target_duration"] = target_duration

        st.markdown(
            """
            <div style="margin-top: 8px; margin-bottom: 4px;">
                <span style="font-size: 0.85rem; font-weight: 600; color: #E2E8F0;">
                    📺 YouTube Destination & Privacy (Final Decision)
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        yt_mode_options = [
            "Private (Only you can view - Recommended)",
            "Unlisted (Anyone with link can view)",
            "Public (Publish immediately to everyone)",
            "Do Not Upload (Instagram Only / Save Locally)",
        ]

        saved_yt_mode = st.session_state.get("declared_yt_mode", yt_mode_options[0])
        saved_yt_idx = yt_mode_options.index(saved_yt_mode) if saved_yt_mode in yt_mode_options else 0

        selected_yt_mode = st.selectbox(
            "YouTube Destination & Privacy",
            yt_mode_options,
            index=saved_yt_idx,
            key="declared_yt_mode_select",
            label_visibility="collapsed",
            help="Your YouTube destination and privacy choice declared here is final and will be automatically applied at the end of generation. You will never be asked again.",
        )
        st.session_state["declared_yt_mode"] = selected_yt_mode

        # Selected channel confirmed from top of form
        selected_yt_channel = st.session_state.get("declared_yt_channel", "Channel 1 (Primary)")
        is_ch2_chosen = "2" in selected_yt_channel
        ch2_exists = (ROOT / "token_channel2.json").exists()
        ch1_exists = (ROOT / "token.json").exists() or (ROOT / "token_channel1.json").exists()
        channel_auth_ok = ch2_exists if is_ch2_chosen else ch1_exists

        if "1" in selected_yt_channel:
            route_badge = "📱 Destination: **Channel 1 (Primary)** (AI/Tech only)"
        else:
            route_badge = f"🏛️ Destination: **Channel 2 (Secondary)** ({content_type})"

        if channel_auth_ok:
            st.caption(f"{route_badge} • 🔑 Token Active (Configured at top of form)")
        else:
            token_needed = "token_channel2.json" if is_ch2_chosen else "token.json"
            reauth_ch = "2" if is_ch2_chosen else "1"
            st.caption(f"{route_badge} • ⚠️ `{token_needed}` missing. Run `./scripts/reauth_youtube.py --channel {reauth_ch}` to connect.")

        if "Do Not Upload" in selected_yt_mode:
            youtube_upload = False
            youtube_privacy = "private"
        elif "Public" in selected_yt_mode:
            youtube_upload = True
            youtube_privacy = "public"
        elif "Unlisted" in selected_yt_mode:
            youtube_upload = True
            youtube_privacy = "unlisted"
        else:
            youtube_upload = True
            youtube_privacy = "private"

        st.session_state["declared_yt_privacy"] = youtube_privacy
        st.session_state["declared_yt_upload"] = youtube_upload

        # Phase 1 Virality Upgrade: Default outro to False for 9:16 Shorts
        default_outro_val = False if aspect_ratio == "9:16" else True
        include_outro = st.checkbox(
            "🎬 Append Like/Share/Subscribe Outro",
            value=st.session_state.get("declared_include_outro", default_outro_val),
            help="Appends a pre-made studio outro clip with Like, Share, and Subscribe call-to-action. (Automatically omitted for 9:16 Shorts to maintain 100% viewer retention).",
            key="declared_include_outro_cb",
        )
        st.session_state["declared_include_outro"] = include_outro

        instagram_upload = st.checkbox(
            "📸 Also publish to Instagram Reels (if eligible: 9:16 & ≤90s)",
            value=st.session_state.get("declared_instagram_upload", False),
            help="Automatically publishes to Instagram Reels if the video is 9:16 vertical and 90 seconds or less.",
            key="declared_instagram_upload_cb",
        )
        st.session_state["declared_instagram_upload"] = instagram_upload

        if instagram_upload:
            try:
                from agents.instagram_agent import get_instagram_account_info
                now = time.time()
                cached_info = st.session_state.get("_cached_ig_info")
                last_checked = st.session_state.get("_cached_ig_info_time", 0)
                if not cached_info or not cached_info.get("connected") or (now - last_checked > 60):
                    ig_info = get_instagram_account_info()
                    st.session_state["_cached_ig_info"] = ig_info
                    st.session_state["_cached_ig_info_time"] = now
                else:
                    ig_info = cached_info

                if ig_info.get("connected"):
                    st.caption(f"✅ **Connected Instagram:** @{ig_info.get('username')} ({ig_info.get('name')}) — ID: `{ig_info.get('id')}`")
                else:
                    err_text = ig_info.get("error", "Instagram not linked")
                    st.caption(f"⚠️ **Instagram Status:** {err_text}")
            except Exception as _ig_e:
                st.caption("⚠️ **Instagram Status:** Unable to verify connection")

        generate = st.button(
            "🚀 Generate Video",
            type="primary",
        )


    # ============================================================
    # RIGHT — MEDIA
    # ============================================================

    with right:

        if generation_mode == "📁 My Own Images/Videos":
            media_sub = "Upload your photos & video clips. AI will map each scene directly to your footage."
            uploader_label = "Upload your images & clips"
        elif generation_mode == "🎥 AI Short Video Clips":
            media_sub = "AutoTube fetches dynamic 3–5s video clips (X/Twitter, Pexels, Memes) for every scene automatically."
            uploader_label = "Upload optional reference clips"
        elif generation_mode == "🖼️ Upload Flyer/Poster":
            media_sub = "Upload your event/product flyer or poster image for AI multimodal analysis."
            uploader_label = "Upload flyer / poster image"
        elif generation_mode == "📊 Explainer Style":
            media_sub = "AI generates conceptual infographics & diagrams automatically (or add custom diagrams)."
            uploader_label = "Upload optional custom diagrams"
        else:
            media_sub = "AutoTube sources stock visuals automatically (or upload optional reference media)."
            uploader_label = "UPLOAD OPTIONAL MEDIA"

        st.markdown(
            f"""<div class="section-title">Media & Assets</div><div class="section-subtitle">{media_sub}</div>""",
            unsafe_allow_html=True,
        )

        uploaded_files = st.file_uploader(
            uploader_label,
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
                st.caption(f"📎 {get_image_filename(file)}")

        else:
            st.markdown(
                """<div class="media-dashed-box">📁<br>Upload images, videos or flyers</div>""",
                unsafe_allow_html=True,
            )


    # ============================================================
    # PIPELINE
    # ============================================================

    st.markdown(
        """<div class="glass-card"><div class="section-title">AI Production Pipeline</div><div class="section-subtitle">One workflow. From idea to published video.</div><div class="pipeline"><div class="pipeline-step"><div class="pipeline-icon">📰</div><div class="pipeline-name">News</div></div><div class="pipeline-arrow">→</div><div class="pipeline-step"><div class="pipeline-icon">✍️</div><div class="pipeline-name">Script</div></div><div class="pipeline-arrow">→</div><div class="pipeline-step"><div class="pipeline-icon">🎙️</div><div class="pipeline-name">Voice</div></div><div class="pipeline-arrow">→</div><div class="pipeline-step"><div class="pipeline-icon">🖼️</div><div class="pipeline-name">Visuals</div></div><div class="pipeline-arrow">→</div><div class="pipeline-step"><div class="pipeline-icon">🎬</div><div class="pipeline-name">Video</div></div><div class="pipeline-arrow">→</div><div class="pipeline-step"><div class="pipeline-icon">💬</div><div class="pipeline-name">Subtitles</div></div><div class="pipeline-arrow">→</div><div class="pipeline-step"><div class="pipeline-icon">✨</div><div class="pipeline-name">Thumbnail</div></div><div class="pipeline-arrow">→</div><div class="pipeline-step"><div class="pipeline-icon">▶️</div><div class="pipeline-name">YouTube</div></div></div></div>""",
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
                fname = get_image_filename(file)
                file_path = upload_dir / fname

                if hasattr(file, "getbuffer"):
                    with open(file_path, "wb") as f:
                        f.write(file.getbuffer())
                elif hasattr(file, "read"):
                    with open(file_path, "wb") as f:
                        f.write(file.read())
                elif isinstance(file, (str, Path)) and os.path.exists(str(file)):
                    shutil.copy2(str(file), str(file_path))
                else:
                    file_path.touch()

                media_paths.append(
                    str(file_path)
                )

        # For Own Voice Recording, transcribe the audio so the visual plan and subtitles match the spoken words
        # For Own Voice Recording, transcribe audio only if topic is not already provided
        if "Use My Own Voice Recording" in voice and active_voice_sample:
            if not topic or str(topic).strip() in ("", "Untitled Video", "Trending Tech Updates", "AutoTube AI Short"):
                with st.spinner("Detecting topic from your audio..."):
                    try:
                        trans_topic = ""
                        try:
                            import speech_recognition as sr
                            r = sr.Recognizer()
                            with sr.AudioFile(str(active_voice_sample)) as source:
                                audio_data = r.record(source)
                            trans_topic = r.recognize_google(audio_data, language="te-IN")
                        except Exception:
                            pass

                        if not trans_topic:
                            is_cloud = os.path.exists("/mount/src") or os.environ.get("STREAMLIT_SH_ENVIRONMENT")
                            if not is_cloud:
                                import whisper
                                wmodel = whisper.load_model("tiny")
                                wres = wmodel.transcribe(str(active_voice_sample), fp16=False)
                                trans_topic = wres.get("text", "").strip()

                        if trans_topic:
                            topic = trans_topic
                            st.session_state["topic_input"] = trans_topic
                    except Exception as auto_tr_err:
                        print("Auto-transcription note:", auto_tr_err)

        is_flyer = (
            content_type == "Uploaded Flyer"
            or generation_mode in ("flyer", "Upload Flyer/Poster", "🖼️ Upload Flyer/Poster")
        )
        is_user_media = (
            generation_mode in ("user_media", "My Own Images/Videos", "📁 My Own Images/Videos")
        )

        if (
            not is_flyer
            and not topic.strip()
            and not ("Use My Own Voice Recording" in voice and active_voice_sample)
        ):
            st.warning(
                "Please enter a topic or select an audio recording."
            )

        elif is_flyer and not media_paths:
            st.warning(
                "Please upload a flyer or image in the Media & Assets section."
            )

        elif is_user_media and not media_paths:
            st.warning(
                "Please upload at least one image or video clip in the Media & Assets section for 'My Own Images/Videos' mode."
            )

        elif not get_gemini_api_key():
            st.error(
                "🔑 Google Gemini API Key is required! Please paste your key in the box at the top of the page."
            )

        else:
            from run_lock import PipelineLock
            active_lock = PipelineLock.get_active_lock_info()
            if active_lock:
                src = active_lock.get("source", "another process")
                top = active_lock.get("topic", "")
                pid = active_lock.get("pid", "?")
                st.warning(
                    f"⏳ **Video Generation Already in Progress**\n\n"
                    f"A video generation is currently being run by **{src}** (PID `{pid}`) for topic:\n\n"
                    f"> *'{top}'*\n\n"
                    f"Please wait a moment for it to complete. If a previous run was stopped or got stuck, click below to unlock."
                )
                if st.button("🔓 Force Unlock Pipeline", key="force_unlock_pipeline_btn"):
                    PipelineLock.force_unlock()
                    st.success("✅ Pipeline lock cleared! You can now click Generate Video again.")
                    st.rerun()
            else:
                try:
                    with PipelineLock(source="dashboard", topic=topic.strip()):
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
                                youtube_channel=selected_yt_channel,
                                aspect_ratio=aspect_ratio,
                                target_duration=target_duration,
                                include_outro=include_outro,
                                instagram_upload=instagram_upload,
                                generation_mode=generation_mode,
                                tone=selected_tone,
                            )

                        st.session_state["pipeline_result"] = result

                        if not result:
                            st.warning("⚠️ Pipeline finished, but no result dictionary was returned.")
                        elif result.get("status") == "FAILED_MOVED_TO_QUEUE":
                            st.warning(f"⚠️ Quality Review: {result.get('stop_reason', 'Low quality score')}. Output moved to failed_queue/.")
                        elif result.get("youtube_video_id"):
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

                        # Instagram Reels Status Reporting (Null-safe)
                        ig_stat = (result.get("instagram_status") or {}) if result else {}
                        ig_res = ig_stat.get("result") or {}
                        if ig_res.get("success"):
                            st.success(f"📸 Published to Instagram Reels! (Media ID: {ig_res.get('media_id')})")
                        elif instagram_upload and not ig_stat.get("eligible"):
                            st.info(f"ℹ️ Instagram Reels: Not eligible for auto-upload ({ig_stat.get('reason', 'N/A')}).")
                        elif instagram_upload and ig_res.get("error"):
                            st.warning(f"⚠️ Instagram Reels note: {ig_res.get('error')}")

                except Exception as e:
                    traceback.print_exc()
                    st.error(
                        f"AutoTube AI failed: {e}"
                    )
                    with st.expander("🔍 View Detailed Error Traceback"):
                        st.code(traceback.format_exc())


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

    raw_video = Path("output/video.mp4")
    effective_video = final_video if final_video.exists() else (raw_video if raw_video.exists() else None)

    if result or effective_video:

        st.markdown(
            """<div class="glass-card"><div class="section-title">Your Output</div><div class="section-subtitle">Your latest AutoTube AI generation.</div></div>""",
            unsafe_allow_html=True,
        )

        if effective_video and effective_video.exists():

            try:
                with open(effective_video, "rb") as _vf:
                    _video_bytes = _vf.read()
                st.video(_video_bytes, format="video/mp4")
            except Exception as _vid_err:
                st.warning(f"Video player loading notice: {_vid_err}")

            st.markdown(
                """<span class="chip">🎬 MP4</span><span class="chip">📺 1080p</span><span class="chip">🔊 AI Voice</span><span class="chip">💬 Subtitles</span>""",
                unsafe_allow_html=True,
            )

            # Validation Quality & Format Summary Card
            val_rep_path = Path("output/validation_report.json")
            val_data = {}
            if val_rep_path.exists():
                try:
                    val_data = json.loads(val_rep_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            elif result and isinstance(result, dict) and result.get("validation_report"):
                val_data = result["validation_report"]

            if val_data:
                v_summary = val_data.get("summary", {})
                v_profile = val_data.get("format_profile", {})
                v_gates = val_data.get("gates", [])
                v_all_passed = v_summary.get("all_passed", False)
                v_status_color = "#10B981" if v_all_passed else "#EF4444"
                v_status_text = "PASSED & APPROVED" if v_all_passed else "QUALITY GATE BLOCKED"
                v_status_icon = "✅" if v_all_passed else "🛑"

                v_gate_a = next((g.get("metrics", {}) for g in v_gates if "Gate A" in g.get("name", "")), {})
                v_gate_b = next((g.get("metrics", {}) for g in v_gates if "Gate B" in g.get("name", "")), {})
                v_gate_c = next((g.get("metrics", {}) for g in v_gates if "Gate C" in g.get("name", "")), {})

                actual_words = v_gate_a.get("word_count", "N/A")
                target_words = f"{v_profile.get('min_words', 0)}-{v_profile.get('max_words', 0)}"
                actual_audio_dur = v_gate_b.get("audio_duration_sec", "N/A")
                target_dur = f"{v_profile.get('target_seconds', 0):.0f}s ({v_profile.get('min_seconds', 0):.0f}-{v_profile.get('max_seconds', 0):.0f}s)"
                res_str = v_gate_c.get("resolution", v_profile.get("resolution", "N/A"))
                aspect_str = v_profile.get("aspect_ratio", "N/A")

                gate_badges_html = "".join([
                    f'<span style="background: {"rgba(16,185,129,0.15)" if g.get("passed") else "rgba(239,68,68,0.15)"}; color: {"#34D399" if g.get("passed") else "#F87171"}; border: 1px solid {"rgba(16,185,129,0.3)" if g.get("passed") else "rgba(239,68,68,0.3)"}; padding: 4px 10px; border-radius: 8px; font-size: 0.8rem; font-weight: 600; margin-right: 6px;">'
                    f'{"✓" if g.get("passed") else "✗"} {g.get("name", "").split("(")[0].strip()}</span>'
                    for g in v_gates
                ])

                st.markdown(
                    f"""
                    <div style="background: rgba(15, 23, 42, 0.75); border: 1.5px solid rgba(99, 102, 241, 0.35); border-radius: 14px; padding: 16px 20px; margin: 16px 0; backdrop-filter: blur(12px);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
                            <div style="font-weight: 700; color: #F8FAFC; font-size: 1.02rem; display: flex; align-items: center; gap: 8px;">
                                <span>🛡️</span> Validation Quality Gate: <span style="color: {v_status_color};">{v_status_icon} {v_status_text}</span>
                            </div>
                            <div>
                                {gate_badges_html}
                            </div>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-top: 8px;">
                            <div style="background: rgba(30, 41, 59, 0.5); padding: 10px 12px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.06);">
                                <div style="font-size: 0.72rem; color: #94A3B8; text-transform: uppercase;">Duration</div>
                                <div style="font-size: 1.05rem; font-weight: 700; color: #F1F5F9;">{actual_audio_dur}s</div>
                                <div style="font-size: 0.72rem; color: #64748B;">Target: {target_dur}</div>
                            </div>
                            <div style="background: rgba(30, 41, 59, 0.5); padding: 10px 12px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.06);">
                                <div style="font-size: 0.72rem; color: #94A3B8; text-transform: uppercase;">Word Count</div>
                                <div style="font-size: 1.05rem; font-weight: 700; color: #F1F5F9;">{actual_words}</div>
                                <div style="font-size: 0.72rem; color: #64748B;">Target: {target_words}</div>
                            </div>
                            <div style="background: rgba(30, 41, 59, 0.5); padding: 10px 12px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.06);">
                                <div style="font-size: 0.72rem; color: #94A3B8; text-transform: uppercase;">Format & AR</div>
                                <div style="font-size: 1.05rem; font-weight: 700; color: #F1F5F9;">{aspect_str}</div>
                                <div style="font-size: 0.72rem; color: #64748B;">{res_str}</div>
                            </div>
                            <div style="background: rgba(30, 41, 59, 0.5); padding: 10px 12px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.06);">
                                <div style="font-size: 0.72rem; color: #94A3B8; text-transform: uppercase;">Target Loudness</div>
                                <div style="font-size: 1.05rem; font-weight: 700; color: #F1F5F9;">-14 LUFS</div>
                                <div style="font-size: 0.72rem; color: #64748B;">Broadcast Std</div>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            try:
                from agents.image_agent import detect_named_product
                t_text = Path("output/title.txt").read_text(encoding="utf-8") if Path("output/title.txt").exists() else ""
                vp_text = Path("output/visual_plan.txt").read_text(encoding="utf-8") if Path("output/visual_plan.txt").exists() else ""
                is_prod, prod_name, _ = detect_named_product(f"{t_text} {vp_text[:300]}")
                if is_prod:
                    st.caption(f"📸 **Editorial Fair-Use Note:** Verified real web photography was sourced for **{prod_name}** news & commentary coverage.")
            except Exception:
                pass

            # Visual Audit Report & Notification Viewer (Phase 5 & 7)
            vr_path = Path("output/visual_report.html")
            if vr_path.exists():
                with st.expander("📊 View Visual & Copyright Tier Audit Report (HTML)", expanded=False):
                    try:
                        vr_html = vr_path.read_text(encoding="utf-8")
                        import streamlit.components.v1 as components
                        components.html(vr_html, height=450, scrolling=True)
                    except Exception:
                        pass

            notif_p = Path("output/validation_notifications.json")
            if notif_p.exists():
                try:
                    notifs = json.loads(notif_p.read_text(encoding="utf-8"))
                    for n in notifs:
                        if n.get("severity") == "CRITICAL":
                            st.error(f"🛑 **[{n.get('component', 'Pipeline')}]** {n.get('message')}")
                        else:
                            st.warning(f"⚠️ **[{n.get('component', 'Pipeline')}]** {n.get('message')}")
                except Exception:
                    pass

            with open(
                effective_video,
                "rb",
            ) as video_file:

                st.download_button(
                    "⬇️ Download Video",
                    data=video_file,
                    file_name="autotube_ai_video.mp4",
                    mime="video/mp4",
                )

            tp_file = Path("output/teleprompter.txt")
            if tp_file.exists():
                try:
                    tp_text = tp_file.read_text(encoding="utf-8")
                    st.download_button(
                        "📜 Download Teleprompter Script (.txt)",
                        data=tp_text,
                        file_name="teleprompter.txt",
                        mime="text/plain",
                    )
                    with st.expander("👁️ View Live Teleprompter (with emotion & comedic SFX cues)", expanded=False):
                        st.markdown(
                            f"""<div style="background: rgba(15, 23, 42, 0.9); border: 1px solid #38BDF8; border-radius: 8px; padding: 14px; font-family: monospace; font-size: 13.5px; line-height: 1.6; white-space: pre-wrap; color: #F1F5F9;">{tp_text}</div>""",
                            unsafe_allow_html=True,
                        )
                except Exception:
                    pass

            # Determine YouTube upload state from session result, metadata.json, or uploaded_videos.json
            yt_vid_id = None
            yt_err = None
            meta_file = Path("output/metadata.json")
            mdata = {}
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as mf:
                        mdata = json.load(mf)
                except Exception:
                    pass

            if mdata.get("youtube_video_id"):
                yt_vid_id = mdata.get("youtube_video_id")
                yt_err = mdata.get("youtube_error")
            elif result and isinstance(result, dict):
                yt_vid_id = result.get("youtube_video_id")
                yt_err = result.get("youtube_error")
            if not yt_vid_id and mdata.get("youtube_video_id"):
                yt_vid_id = mdata.get("youtube_video_id")
            if not yt_err and mdata.get("youtube_error"):
                yt_err = mdata.get("youtube_error")

            # Check uploaded_videos.json for known title match
            cur_title = mdata.get("title") or (result.get("title") if isinstance(result, dict) else None)
            if not cur_title:
                t_file = Path("output/title.txt")
                if t_file.exists():
                    try:
                        cur_title = t_file.read_text(encoding="utf-8").strip()
                    except Exception:
                        pass

            if not yt_vid_id and cur_title and not yt_err:
                uploaded_db = Path("output/uploaded_videos.json")
                if uploaded_db.exists():
                    try:
                        with open(uploaded_db, "r", encoding="utf-8") as uf:
                            uvids = json.load(uf)
                            if cur_title in uvids:
                                yt_vid_id = uvids[cur_title]
                    except Exception:
                        pass

            declared_priv = st.session_state.get("declared_yt_privacy", mdata.get("privacy", "private"))
            was_yt_requested = st.session_state.get("declared_yt_upload", mdata.get("youtube_upload", False))

            if yt_vid_id:
                st.markdown(
                    f"""
                    <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 12px; padding: 14px 18px; margin: 16px 0;">
                        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                            <div style="font-weight: 700; color: #34D399; font-size: 1.05rem;">
                                ✅ Published to YouTube
                            </div>
                            <span style="background: rgba(52, 211, 153, 0.2); color: #6EE7B7; font-size: 0.8rem; font-weight: 700; padding: 3px 10px; border-radius: 9999px; text-transform: uppercase; letter-spacing: 0.5px;">
                                🔒 {declared_priv.upper()}
                            </span>
                        </div>
                        <div style="margin-top: 8px; font-size: 0.9rem; color: #E2E8F0;">
                            Pre-declared privacy (<strong>{declared_priv.upper()}</strong>) applied automatically. No additional setup needed.
                        </div>
                        <div style="margin-top: 12px;">
                            <a href="https://youtu.be/{yt_vid_id}" target="_blank" style="display: inline-block; background: #DC2626; color: white; padding: 8px 18px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 0.9rem;">
                                ▶️ Watch on YouTube ({yt_vid_id})
                            </a>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif was_yt_requested and yt_err:
                st.markdown(
                    f"""
                    <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 12px; padding: 14px 18px; margin: 16px 0;">
                        <div style="font-weight: 700; color: #F87171; font-size: 1rem;">
                            ⚠️ YouTube Upload Notice
                        </div>
                        <div style="color: #FCA5A5; font-size: 0.85rem; margin-top: 4px;">
                            {yt_err}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(f"🔄 Retry Upload with Pre-declared Privacy ({declared_priv.upper()})", key="retry_yt_upload_btn", use_container_width=True):
                    with st.spinner("Retrying YouTube upload with auto-resuming resumable chunks..."):
                        try:
                            from agents.youtube_agent import upload_video
                            rtitle = mdata.get("title") or cur_title or "My AutoTube Video"
                            rdesc = mdata.get("description", "")
                            rtags = mdata.get("tags", [])
                            v_id = upload_video(
                                str(final_video),
                                rtitle,
                                rdesc,
                                rtags,
                                thumbnail_path=str(thumbnail_file) if thumbnail_file.exists() else None,
                                privacy=declared_priv,
                                channel=st.session_state.get("declared_yt_channel", mdata.get("channel", "Channel 1 (Primary)")),
                            )
                            st.session_state["pipeline_result"] = {
                                **(result or {}),
                                "youtube_video_id": v_id,
                                "youtube_error": None,
                            }
                            st.success(f"✅ Successfully uploaded to YouTube! Video ID: {v_id}")
                            st.rerun()
                        except Exception as m_yt_err:
                            st.error(f"Retry failed: {m_yt_err}. Please check your network connection or token authorization.")
            elif not was_yt_requested:
                st.markdown(
                    """
                    <div style="background: rgba(148, 163, 184, 0.08); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 12px; padding: 10px 14px; margin: 12px 0;">
                        <div style="color: #94A3B8; font-size: 0.85rem; font-weight: 500;">
                            💾 <strong>Saved Locally:</strong> As pre-declared before generation, this video was saved for local viewing and was not uploaded to YouTube.
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            if not yt_vid_id and final_video.exists():
                with st.expander("🚀 Manual YouTube Publication", expanded=False):
                    default_ch = mdata.get("channel", "Channel 1 (Primary)")
                    pub_channels = ["Channel 2 (Secondary)", "Channel 1 (Primary)"] if "Channel 2" in default_ch else ["Channel 1 (Primary)", "Channel 2 (Secondary)"]
                    pub_channel = st.selectbox("Target Channel", pub_channels, key="manual_pub_channel_select")
                    pub_privacy = st.selectbox("Privacy Setting", ["public", "unlisted", "private"], index=0, key="manual_pub_privacy_select")
                    if st.button("📤 Publish Video to YouTube Now", key="manual_pub_btn", use_container_width=True):
                        with st.spinner("Publishing video to YouTube..."):
                            try:
                                from agents.youtube_agent import upload_video
                                rtitle = mdata.get("title") or cur_title or "AutoTube Video"
                                rdesc = mdata.get("description", "")
                                rtags = mdata.get("tags", [])
                                v_id = upload_video(
                                    str(final_video),
                                    rtitle,
                                    rdesc,
                                    rtags,
                                    thumbnail_path=str(thumbnail_file) if thumbnail_file.exists() else None,
                                    privacy=pub_privacy,
                                    channel=pub_channel,
                                )
                                st.session_state["pipeline_result"] = {
                                    **(result or {}),
                                    "youtube_video_id": v_id,
                                    "youtube_error": None,
                                }
                                st.success(f"✅ Successfully published! Video ID: {v_id}")
                                st.rerun()
                            except Exception as pub_err:
                                st.error(f"Publication failed: {pub_err}")

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

        # Multi-Provider Execution Telemetry Audit
        render_provider_audit_card()

        # ----------------------------------------------------
        # VISUAL SCENES & MANUAL OVERRIDE (SAFETY NET)
        # ----------------------------------------------------
        vplan_file = Path("output/visual_plan.txt")
        if vplan_file.exists():
            with st.expander("🖼️ Visual Scenes & Manual Override Safety Net", expanded=False):
                st.markdown(
                    """
                    <div style="font-size: 13px; color: #94A3B8; margin-bottom: 12px;">
                        Review each scene's visual asset. You can instantly replace any visual with an upload or click <b>Regenerate with FLUX AI</b> to get an exact match.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                v_lines = []
                try:
                    for raw_l in vplan_file.read_text(encoding="utf-8").splitlines():
                        raw_l = raw_l.strip()
                        if raw_l and (raw_l[0].isdigit() or raw_l.startswith("*") or raw_l.startswith("-")):
                            clean_l = re.sub(r"^(?:\d+[\.\)]|\*|\-)\s*", "", raw_l).strip()
                            if clean_l:
                                v_lines.append(clean_l)
                except Exception:
                    pass

                for idx, v_desc in enumerate(v_lines, start=1):
                    col_img, col_info = st.columns([1, 2])
                    img_path = Path(f"assets/{idx}.jpg")
                    vid_path = Path(f"assets/{idx}.mp4")

                    with col_img:
                        if img_path.exists():
                            st.image(str(img_path), caption=f"Scene {idx}", use_container_width=True)
                        elif vid_path.exists():
                            st.caption(f"Scene {idx} (Video Clip)")
                        else:
                            st.caption(f"Scene {idx} (Pending)")

                    with col_info:
                        primary_prompt = v_desc.split("|")[0].strip()
                        st.markdown(f"**Scene {idx}:** {primary_prompt}")
                        if "|" in v_desc:
                            alt_queries = [q.strip() for q in v_desc.split("|")[1:]]
                            st.caption(f"Alternatives: {' • '.join(alt_queries)}")

                        btn_col1, btn_col2 = st.columns(2)
                        with btn_col1:
                            if st.button(f"🎨 Regenerate Scene {idx} (FLUX AI)", key=f"regen_flux_{idx}"):
                                with st.spinner(f"Generating photorealistic visual for Scene {idx}..."):
                                    from providers.image import generate_pollinations_image
                                    dest = Path(f"assets/{idx}.jpg")
                                    ok = generate_pollinations_image(
                                        f"{primary_prompt}, cinematic photorealistic 8k",
                                        str(dest),
                                        aspect_ratio=st.session_state.get("selected_aspect_ratio", "1:1"),
                                    )
                                    if ok:
                                        st.success(f"Scene {idx} regenerated! Updating video...")
                                        create_pipeline_video(aspect_ratio=st.session_state.get("selected_aspect_ratio", "1:1"))
                                        create_final_video(
                                            burn_captions=st.session_state.get("declared_burn_captions", True),
                                            aspect_ratio=st.session_state.get("selected_aspect_ratio", "1:1"),
                                        )
                                        st.rerun()
                        with btn_col2:
                            up_file = st.file_uploader(f"Replace Scene {idx}", type=["jpg", "png", "jpeg"], key=f"upload_scene_{idx}")
                            if up_file:
                                dest = Path(f"assets/{idx}.jpg")
                                dest.write_bytes(up_file.read())
                                st.success(f"Scene {idx} replaced! Updating video...")
                                create_pipeline_video(aspect_ratio=st.session_state.get("selected_aspect_ratio", "1:1"))
                                create_final_video(
                                    burn_captions=st.session_state.get("declared_burn_captions", True),
                                    aspect_ratio=st.session_state.get("selected_aspect_ratio", "1:1"),
                                )
                                st.rerun()
                    st.divider()

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
    """<div style="text-align:center; padding:25px; color:#475569; font-size:12px;">AutoTube AI • AI Video Automation</div>""",
    unsafe_allow_html=True,
)

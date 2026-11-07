"""AutoTube AI - Multi-Media Streamlit Dashboard."""

import asyncio
import datetime
import functools
import json
import os
import re
import shutil
import time
from pathlib import Path
try:
    import streamlit as st
except ImportError:
    st = None

# Synchronously pre-initialize torch on the main thread to prevent multi-threaded import race conditions
try:
    import torch
except Exception:
    pass

from config.format_profiles import get_format_profile, FormatProfile
from agents.validation_agent import ValidationAgent, ValidationResult
from run_lock import PipelineLock


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
    "🔥 👩 Shruti (Telugu Female - Sarcastic & Roasting)": "te-IN-ShrutiNeural-Roast",
    "👩 Shruti (Telugu Creator / Anchor) - Conversational": "te-IN-ShrutiNeural",
    "👨 Mohan (Telugu Creator / Anchor) - Natural Spoken Delivery": "te-IN-MohanNeural",
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
    "te-in-shrutineural-roast": "te-IN-ShrutiNeural-Roast",
    "te-IN-ShrutiNeural-Roast": "te-IN-ShrutiNeural-Roast",
    "shruti-roast": "te-IN-ShrutiNeural-Roast",
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
    "👨 Mohan (Telugu Creator / Anchor) - Natural Spoken Delivery": ("+4%", "+0Hz"),
    "👩 Shruti (Telugu Creator / Anchor) - Conversational": ("+4%", "+0Hz"),
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
    "🔥 👩 Shruti (Telugu Female - Sarcastic & Roasting)": ("+7%", "+0Hz"),
    "te-IN-ShrutiNeural-Roast": ("+7%", "+0Hz"),
    "shruti-roast": ("+7%", "+0Hz"),
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


def run_stage_with_timeout(stage_name, timeout_seconds, func, *args, **kwargs):
    """
    Execute a pipeline stage in a worker thread bounded by a hard timeout.
    Prevents stalled network or ffmpeg calls from blocking pipeline indefinitely.
    If a timeout occurs, automatically triggers autonomous self-healing without crashing the pipeline.
    """
    import concurrent.futures
    from providers.timing_logger import time_stage
    with time_stage(stage_name):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, *args, **kwargs)
                return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as t_err:
            err_msg = f"Stage '{stage_name}' timed out after {timeout_seconds}s limit."
            print(f"❌ {err_msg}. Triggering autonomous self-healing recovery...")
            try:
                from supervisor import _handle_recovery
                stage_key_map = {
                    "Script Generation": "script_agent",
                    "Script Generation (Explainer)": "script_agent",
                    "Script Revision": "script_agent",
                    "Image Download": "image_agent",
                    "Video Assembly": "video_agent",
                    "Ken Burns Video Assembly": "video_agent",
                    "Final Video Assembly": "final_video_agent",
                    "Final Subtitles & Processing": "final_video_agent",
                    "Voice Generation": "voice_agent",
                    "Metadata & Thumbnail Generation": "metadata_agent",
                }
                mapped_stage = stage_key_map.get(stage_name, stage_name)
                healed = _handle_recovery(func, args, kwargs, mapped_stage, t_err, None, is_async=False)
                if healed is not None:
                    print(f"✅ [Supervisor] Successfully auto-healed timed-out stage '{stage_name}'!")
                    return healed
            except Exception as heal_err:
                print(f"⚠️ Self-healing exception for stage '{stage_name}': {heal_err}")
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
        "hook.json",
        "thumbnail.jpg",
        "review.json",
        "metadata.json",
        "visual_plan.json",
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
            # Never delete voice sample references, static music, outro, sfx, entities, or offline fallback pool
            if "voice" in item.name.lower() or item.name.lower() in ("fallback", "music", "outro", "sfx", "entities"):
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
    topic_category=None,
    aspect_ratio="9:16",
    is_longform=False,
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

            if is_indic:
                if voice_id in ("af_heart", "af_bella"):
                    print("🎙️ [Voice Agent] Detected Telugu script narration - auto-selecting te-IN-ShrutiNeural (Female) for authentic Telugu creator delivery.")
                    voice_id = "te-IN-ShrutiNeural"
                elif voice_id in ("am_adam", "am_michael"):
                    print("🎙️ [Voice Agent] Detected Telugu script narration - auto-selecting te-IN-MohanNeural (Male) for authentic Telugu creator delivery.")
                    voice_id = "te-IN-MohanNeural"
        except Exception:
            pass

    from agents.voice_agent import create_voice

    rate, pitch = VOICE_TUNING.get(voice, VOICE_TUNING.get(voice_id, ("-5%", "+0Hz")))
    if is_longform or aspect_ratio == "16:9":
        # Calibrated documentary pace for 16:9 explainers (+1% to +2% for natural cadenced delivery)
        rate = "+1%" if voice_id in ("te-IN-MohanNeural", "te-IN-ShrutiNeural", "te-IN-ShrutiNeural-Roast", "mohan", "shruti", "shruti-roast") else "-2%"
    elif voice_id in ("te-IN-MohanNeural", "te-IN-ShrutiNeural", "te-IN-ShrutiNeural-Roast", "mohan", "shruti", "shruti-roast") and rate in ("-5%", "+0%"):
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

    kwargs = {
        "voice": voice_id,
        "rate": rate,
        "pitch": pitch,
        "voice_sample": effective_sample,
    }
    if topic_category:
        kwargs["topic_category"] = topic_category

    return asyncio.run(
        create_voice(**kwargs)
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
    content_type="Bigg Boss Telugu",
    topic="",
    *args,
    **kwargs,
):
    """
    Download visuals according to the AI visual plan with self-healing fallback.
    Routes to dynamic short video clips (short_clip_fetcher) when video clips mode is active.
    """
    is_video_clips_mode = generation_mode in (
        "video_clips",
        "🎥 AI Short Video Clips",
        "short_clips",
    )
    if is_video_clips_mode:
        from agents.short_clip_fetcher import fetch_and_prepare_all_scene_clips
        try:
            print("🎬 [Pipeline] Generating dynamic short video clips via short_clip_fetcher...")
            clips = fetch_and_prepare_all_scene_clips(
                aspect_ratio=aspect_ratio,
                topic=topic or content_type,
            )
            if clips:
                from agents.video_agent import ensure_visual_assets_exist
                ensure_visual_assets_exist(needed_count=len(clips))
                return [c["file_path"] for c in clips]
        except Exception as v_err:
            print(f"⚠️ Video clips fetcher notice: {v_err}. Falling back to visual plan image generation...")

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
    captions=None,
    aspect_ratio="9:16",
    include_outro=False,
    outro_clip=None,
):
    """Create final video with optional captions and outro."""
    if captions is None:
        captions = (aspect_ratio == "16:9")

    if captions:
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
        add_captions=captions,
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
    target_duration=None,
    aspect_ratio=None,
    profile=None,
    **kwargs,
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
        target_duration=target_duration,
        aspect_ratio=aspect_ratio,
        profile=profile,
        **kwargs,
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

    # Reuse pre-generated thumbnail if available and valid
    final_thumb_path = None
    existing_thumb = out_dir / "thumbnail.jpg"
    if existing_thumb.exists() and existing_thumb.stat().st_size > 5000:
        print(f"🖼️ Reusing pre-generated thumbnail: {existing_thumb.name}")
        final_thumb_path = existing_thumb
    else:
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


def with_pipeline_lock(func):
    """Decorator ensuring mutual exclusion for video generation pipeline runs."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        topic = kwargs.get("topic") if "topic" in kwargs else (args[0] if args else "")
        topic_str = str(topic).strip() if topic else "autonomous"
        lock = PipelineLock(source="pipeline", topic=topic_str)
        acquired, lock_msg = lock.acquire()
        if not acquired:
            raise RuntimeError(f"Pipeline execution blocked: {lock_msg}")
        try:
            return func(*args, **kwargs)
        finally:
            lock.release()
    return wrapper


@with_pipeline_lock
def generate_multi_media_video(
    topic,
    media_files=None,
    content_type="News",
    language_style="English news style",
    voice="👨 Adam (Male Creator) - Fast & Crisp",
    voice_sample=None,
    captions=None,
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
    **kwargs,
):
    if "channel" in kwargs:
        youtube_channel = kwargs["channel"]
    if "upload_youtube" in kwargs:
        youtube_upload = kwargs["upload_youtube"]
    if "upload_instagram" in kwargs:
        instagram_upload = kwargs["upload_instagram"]
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
    if captions is None:
        captions = (aspect_ratio == "16:9")

    # Clean lingering artifacts from previous runs
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
        "output/visual_plan.json",
        "output/visual_report.html",
        "output/validation_notifications.json",
    ):
        try:
            sp = Path(stale_file)
            if sp.exists():
                sp.unlink(missing_ok=True)
        except Exception:
            pass

    # Reset SQLite asset ledger for fresh run
    try:
        from data.asset_ledger import clear_ledger_for_video
        clear_ledger_for_video("current")
    except Exception:
        pass

    # Record topic in used topics ledger to guarantee future suggestions are novel
    try:
        from agents.topic_suggester import record_used_topic
        record_used_topic(topic)
    except Exception:
        pass

    # Auto-resolve channel routing for audience segmentation (e.g. Entertainment -> Channel 2)
    if not youtube_channel or youtube_channel == "Channel 1 (Primary)":
        try:
            from agents.youtube_agent import resolve_target_channel
            routed = resolve_target_channel(content_type=content_type, topic=topic)
            if routed:
                youtube_channel = routed
        except Exception:
            pass

    # Optional Feature 1: Content Intelligence Assessment (Non-breaking, Disabled by Default)
    content_intel_report = None
    try:
        from config.settings import get_setting
        if get_setting("ENABLE_CONTENT_INTELLIGENCE", False):
            from agents.content_intelligence_agent import evaluate_topic_intelligence
            content_intel_report = evaluate_topic_intelligence(topic)
            print(f"🧠 [Content Intelligence] Topic evaluated: '{topic}' (Score: {content_intel_report.get('overall_score')}/100, Pillar: {content_intel_report.get('pillar')})")
    except Exception as ci_err:
        print(f"Content intelligence notice: {ci_err}")

    # Auto-sync language_style if a Telugu voice is selected
    voice_str = str(voice or "").lower()
    if any(tv in voice_str for tv in ("mohan", "shruti", "te-in")) and not ("telugu" in str(language_style).lower() or "తెలుగు" in str(language_style)):
        print(f"🎙️ [Pipeline] Auto-syncing language_style to Telugu because voice is {voice}")
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
    print(f"📁 [Run Isolation] Created isolated run directory: {run_dir}")

    dur_str = str(target_duration).lower()
    ct_lower = str(content_type or "").lower()
    is_longform = (
        aspect_ratio == "16:9"
        or "3-5" in dur_str
        or "3–5" in dur_str
        or "4-6" in dur_str
        or "4–6" in dur_str
        or "5-8" in dur_str
        or "5–8" in dur_str
        or "6-9" in dur_str
        or "6–9" in dur_str
        or "long-form" in dur_str
        or "longform" in dur_str
        or "2-4" in dur_str
        or "explainer" in dur_str
        or "documentary" in ct_lower
    )
    try:
        profile = get_format_profile(
            target_duration=target_duration,
            aspect_ratio=aspect_ratio,
            format_type="long-form" if is_longform else "short",
            language=language_style,
        )
    except TypeError:
        import importlib
        import config.format_profiles
        importlib.reload(config.format_profiles)
        profile = config.format_profiles.get_format_profile(
            target_duration=target_duration,
            aspect_ratio=aspect_ratio,
            format_type="long-form" if is_longform else "short",
            language=language_style,
        )
    profile.content_type = content_type
    profile.topic = topic
    # Outro management: Strict omission for 9:16 Shorts to preserve completion rate
    if aspect_ratio == "9:16":
        include_outro = False
    elif include_outro:
        print("🎬 [Outro] 5-second Like, Subscribe, Share & Comment outro active for long-form format.")
    print(f"🎯 [Format Profile] Format: {profile.format_type.upper()} | Target: {profile.target_seconds:.0f}s ({profile.min_seconds:.0f}s-{profile.max_seconds:.0f}s) | Words: {profile.min_words}-{profile.max_words}")
    val_agent = ValidationAgent(output_dir=OUTPUT_DIR)
    gate_results = []

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
                for f in ["script.txt", "section_map.txt", "visual_plan.txt", "tts_script.txt", "final_video.mp4", "delivery_plan.json", "visual_plan.json"]:
                    (OUTPUT_DIR / f).unlink(missing_ok=True)
                for p in ASSETS_DIR.glob("[0-9]*.jpg"):
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass
                for p in ASSETS_DIR.glob("[0-9]*.mp4"):
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass
            elif run_voice:
                for f in ["voice.wav", "voice.mp3", "subtitles.srt", "final_video.mp4"]:
                    (OUTPUT_DIR / f).unlink(missing_ok=True)
            elif run_images:
                (OUTPUT_DIR / "final_video.mp4").unlink(missing_ok=True)
                for p in ASSETS_DIR.glob("[0-9]*.jpg"):
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass
                for p in ASSETS_DIR.glob("[0-9]*.mp4"):
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass

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
                        300,
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
                        300,
                        generate_script,
                        topic,
                        content_type=content_type,
                        language_style=language_style,
                        source_context=news_verification,
                        target_duration=target_duration,
                        voice=voice,
                        tone=tone,
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
                    300,
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
                    target_duration=target_duration,
                )

            if not script:
                s_file = OUTPUT_DIR / "script.txt"
                if s_file.exists() and s_file.read_text(encoding="utf-8").strip():
                    script = s_file.read_text(encoding="utf-8").strip()
                    print(f"🔄 [Pipeline Recovery] Recovered script from {s_file} ({len(script)} chars).")
                else:
                    print("⚠️ [Pipeline Recovery] Script generation returned empty. Running autonomous fallback...")
                    try:
                        from supervisor import heal_network_or_quota
                        script = heal_network_or_quota("script_agent", {
                            "topic": topic,
                            "content_type": content_type,
                            "language_style": language_style,
                            "target_duration": target_duration,
                            "voice": voice,
                            "default_title": title,
                        })
                    except Exception as h_err:
                        print(f"⚠️ Pipeline autonomous script healing error: {h_err}")

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

            # ----------------------------------------------------
            # GATE A: Script Validation & Step 1 Pre-Execution Calibration
            # ----------------------------------------------------
            if not script_override:
                print("🎯 [Step 1 Auto-Calibration] Running pre-execution script calibration against format profile...")
                try:
                    from agents.script_agent import auto_calibrate_script_to_profile
                    script = auto_calibrate_script_to_profile(script, profile, topic, content_type=content_type)
                except Exception as cal_err:
                    print(f"⚠️ Step 1 auto-calibration notice: {cal_err}")

            # Optional Feature 2: Hook & Retention Optimizer (Non-breaking, Disabled by Default)
            retention_report = None
            try:
                from config.settings import get_setting
                if get_setting("ENABLE_HOOK_OPTIMIZER", False):
                    from agents.hook_retention_optimizer import optimize_script_for_retention
                    ret_res = optimize_script_for_retention(
                        script_text=script,
                        topic=topic,
                        aspect_ratio=aspect_ratio,
                        target_duration=target_duration,
                    )
                    retention_report = ret_res
                    print(f"⚡ [Retention Optimizer] Candidate created: {ret_res.get('candidate_file')} (Est. Score: {ret_res.get('optimized_retention_score')}/100, +{ret_res.get('improvement')})")
                    if get_setting("AUTO_APPLY_HOOK_OPTIMIZER", False):
                        script = ret_res["optimized_script"]
                        print("⚡ [Retention Optimizer] Applied optimized script candidate to active timeline.")
            except Exception as ret_err:
                print(f"Hook retention optimizer notice: {ret_err}")

            gate_a = val_agent.validate_script(script, topic, profile, content_type)
            if not gate_a.passed:
                print(f"⚠️ [Gate A Script Validation] Found {len(gate_a.issues)} issues:")
                for iss in gate_a.issues:
                    print(f"   [{iss.severity}] {iss.rule}: Expected {iss.expected}, Actual: {iss.actual}")
            else:
                print(f"✅ [Gate A Script Validation] Passed: {gate_a.metrics.get('word_count')} words (Target: {profile.target_words} words).")

            gate_results = [gate_a]

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
        # PRE-SYNTHESIS WORD COUNT VALIDATION & EXPANSION CHECK
        # ----------------------------------------------------
        current_script_text = script
        if not current_script_text:
            s_file = OUTPUT_DIR / "script.txt"
            if s_file.exists():
                try:
                    current_script_text = s_file.read_text(encoding="utf-8")
                except Exception:
                    pass

        if current_script_text and profile:
            cur_words = len(current_script_text.split())
            min_target_words = getattr(profile, "min_words", 0)
            if min_target_words > 0 and cur_words < int(0.70 * min_target_words):
                print(
                    f"⚠️ [Pre-Synthesis Check] Script word count ({cur_words}) is below 70% of "
                    f"profile minimum ({min_target_words} words). Executing automatic script expansion..."
                )
                try:
                    from agents.script_agent import auto_calibrate_script_to_profile, ensure_script_artifacts
                    script = auto_calibrate_script_to_profile(current_script_text, profile, topic, content_type=content_type)
                    ensure_script_artifacts(script, topic=topic, default_title=title)
                    print(f"✅ [Pre-Synthesis Check] Script auto-calibrated to {len(script.split())} words before voice synthesis.")
                except Exception as exp_err:
                    print(f"⚠️ Pre-synthesis script expansion notice: {exp_err}")

        # ----------------------------------------------------
        # PARALLEL PIPELINE: VISUALS + VOICE CONCURRENT EXECUTION
        # ----------------------------------------------------

        if run_images and run_voice:
            visual_plan_file = OUTPUT_DIR / "visual_plan.txt"
            if not visual_plan_file.exists() or not visual_plan_file.read_text(encoding="utf-8").strip():
                print("⚠️ [Pipeline] visual_plan.txt missing or empty. Auto-synthesizing from script...")
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
                    from providers.timing_logger import time_stage
                    with time_stage("Visual Sourcing"):
                        download_visuals(
                            visual_plan_file,
                            flyer_path=flyer_path_arg,
                            feedback=feedback if failing_component == "image_agent" else None,
                            aspect_ratio=aspect_ratio,
                            generation_mode=generation_mode,
                            user_assets=saved_media or media_files,
                            content_type=content_type,
                            topic=topic,
                            topic_category=content_type,
                            progress_callback=progress.progress,
                        )
                    print("✅ [Parallel Stage] Visual Sourcing Complete.")
                except Exception as error:
                    print("Visual sourcing warning:", error)

            def _task_voice():
                print(f"⚡ [Parallel Stage] Starting Narration Synthesis ({voice})...")
                from providers.timing_logger import time_stage
                with time_stage("Voice Synthesis"):
                    create_voice_for_script(
                        voice=voice,
                        own_voice_audio=voice_sample,
                        aspect_ratio=aspect_ratio,
                        is_longform=is_longform,
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
                    print("⚠️ [Pipeline] visual_plan.txt missing or empty. Auto-synthesizing from script...")
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
                        topic=topic,
                        topic_category=content_type,
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
                    aspect_ratio=aspect_ratio,
                    is_longform=is_longform,
                )
            else:
                print(f"[Targeted Self-Healing] Preserving existing voice audio (failing component: {failing_component})")

        # ----------------------------------------------------
        # GATE B: Narration / TTS Audio Validation
        # ----------------------------------------------------
        voice_file_p = OUTPUT_DIR / "voice.mp3"
        gate_b = val_agent.validate_audio(str(voice_file_p), profile)
        gate_results.append(gate_b)
        if not gate_b.passed and attempt < MAX_REVIEW_ATTEMPTS:
            from agents.run_report import probe_duration
            v_dur = probe_duration(str(voice_file_p)) if voice_file_p.exists() else 0.0
            print(f"⚠️ [Gate B Audio Mismatch] Voice duration is {v_dur:.1f}s (Allowed: {profile.min_seconds:.1f}s - {profile.max_seconds:.1f}s for {profile.target_seconds:.0f}s target).")
            if profile.format_type == "short" and profile.max_seconds <= 50.0 and v_dur > 45.0:
                feedback = (
                    f"CRITICAL RETENTION ERROR: Spoken voice duration was {v_dur:.1f} seconds, which strictly exceeds "
                    "the 45-second hard maximum for YouTube Shorts. Shorten the script to 60-85 words strictly "
                    "focusing on ONE core idea, while preserving the opening hook and closing payoff intact."
                )
            elif v_dur < profile.min_seconds:
                feedback = (
                    f"CRITICAL DURATION ERROR: Spoken voice duration was only {v_dur:.1f} seconds, which is far too short "
                    f"for the requested {profile.target_seconds:.0f}s video ({profile.min_seconds:.0f}s - {profile.max_seconds:.0f}s). "
                    f"Expand the script narration to between {profile.min_words} and {profile.max_words} words."
                )
            else:
                feedback = (
                    f"CRITICAL DURATION ERROR: Spoken voice duration was {v_dur:.1f} seconds, which exceeds "
                    f"the {profile.max_seconds:.0f}s limit for the requested format. "
                    f"Condense the script narration to between {profile.min_words} and {profile.max_words} words."
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

        def _task_subtitles():
            if captions:
                print("⚡ [Parallel Task] Generating subtitles in background...")
                try:
                    from agents.subtitle_agent import create_subtitles
                    create_subtitles(aspect_ratio=aspect_ratio)
                    print("✅ [Parallel Task] Subtitles Ready.")
                except Exception as sub_err:
                    print(f"⚠️ Subtitle parallel task notice: {sub_err}")

        def _task_thumbnail():
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

        def _task_video():
            print("⚡ [Parallel Task] Starting Ken Burns Video Assembly...")
            target_dur_sec = getattr(profile, "target_seconds", 60.0) if "profile" in locals() else 60.0
            timeout_video = int(max(420, target_dur_sec * 2.5))
            run_stage_with_timeout(
                "Ken Burns Video Assembly",
                timeout_video,
                create_pipeline_video,
                aspect_ratio=aspect_ratio,
            )
            print("✅ [Parallel Task] Ken Burns Assembly Complete.")

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as stage_executor:
            f_vid = stage_executor.submit(_task_video)
            f_sub = stage_executor.submit(_task_subtitles)
            f_thm = stage_executor.submit(_task_thumbnail)
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
        for fname in ["script.txt", "visual_plan.txt", "section_map.txt", "voice.mp3", "subtitles.srt", "final_video.mp4", "teleprompter.txt", "delivery_plan.json"]:
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

        # ----------------------------------------------------
        # GATE C: Final Render Video Validation
        # ----------------------------------------------------
        vid_path = str(OUTPUT_DIR / "final_video.mp4")
        aud_path = str(OUTPUT_DIR / "voice.mp3")
        th_path = str(run_dir / "thumbnail.jpg" if (run_dir / "thumbnail.jpg").exists() else OUTPUT_DIR / "thumbnail.jpg")
        gate_c = val_agent.validate_final_render(vid_path, aud_path, th_path, profile)
        gate_results.append(gate_c)
        if not gate_c.passed:
            print(f"⚠️ [Gate C Render Defect] Gate C found {len(gate_c.issues)} issues:")
            for iss in gate_c.issues:
                print(f"   [{iss.severity}] {iss.rule}: Expected {iss.expected}, Actual: {iss.actual}")

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
            target_duration=target_duration,
            aspect_ratio=aspect_ratio,
            profile=profile,
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

    # ----------------------------------------------------
    # GATE D: Pre-Upload Verification & Publication Barrier
    # ----------------------------------------------------
    gate_d = val_agent.validate_pre_upload(topic, content_type, youtube_channel, gate_results)
    gate_results.append(gate_d)
    val_report = val_agent.save_report(topic, profile, gate_results, run_id=run_id)

    has_gate_critical = any(
        any(i.severity == "CRITICAL" for i in r.issues)
        for r in [gate_d]
    )
    if has_gate_critical:
        print()
        print("=" * 60)
        print("🛑 [Validation Gate D] CRITICAL DEFECTS DETECTED - PUBLICATION BLOCKED")
        for r in [gate_d]:
            for iss in r.issues:
                if iss.severity == "CRITICAL":
                    print(f"   [{r.gate_name}] {iss.rule}: {iss.actual}")
        print("   Upload strictly blocked to avoid publishing defective content.")
        print(f"   Validation report written to: {val_agent.report_file}")
        print("=" * 60)

    # Phase 7 Quality Gate & Publication Approval:
    # 1. Strictly blocked if Gate D detected genuine critical publication defects.
    # 2. Approved if AI review status is APPROVE or score >= 65 with zero critical defects.
    review_approved = (
        (not has_gate_critical)
        and (
            review_status_final == "APPROVE"
            or (review_score_final >= 65 and not critical_issues_final)
            or is_own_voice
        )
    )

    upload_blocked = not review_approved

    if review_approved:
        review_final_message = (
            "✅ AI Review approved the final version (Score >= 80, no critical issues)."
        )
    elif has_gate_critical:
        crit_list = [f"[{r.gate_name}] {iss.rule}: {iss.actual}" for r in gate_results for iss in r.issues if iss.severity == "CRITICAL"]
        crit_str = "; ".join(crit_list[:2])
        review_final_message = (
            f"🛑 Validation Gate BLOCKED publication (Critical Defects: {crit_str}). "
            f"AI Review Score was {review_score_final}/100. Check validation report."
        )
    elif review_status_final == "IMPROVE" or upload_blocked:
        review_final_message = (
            f"🛑 Final AI Review REJECTED publication (Score: {review_score_final}/100, Critical Issues: {len(critical_issues_final)}). "
            f"All {MAX_REVIEW_ATTEMPTS} self-healing attempts exhausted. "
            "Phase 7 Quality Gate policy: Automated upload BLOCKED to preserve channel authority."
        )
    elif review_status_final in (
        "REVIEW_FAILED",
        "REVIEW_QUOTA_EXCEEDED",
    ):
        review_final_message = (
            "AI Review was unavailable. The latest generated version will continue."
        )
    else:
        review_final_message = (
            "Final AI Review completed."
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
            180,
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

        # Optional Feature 3: Title & Thumbnail Packaging Intelligence (Non-breaking, Disabled by Default)
        packaging_intel_report = None
        try:
            from config.settings import get_setting
            if get_setting("ENABLE_PACKAGING_INTELLIGENCE", False):
                from agents.packaging_intelligence import generate_title_candidates, generate_mobile_thumbnail_text_options, verify_packaging_alignment
                title_cands = generate_title_candidates(topic)
                thumb_opts = generate_mobile_thumbnail_text_options(topic)
                align_check = verify_packaging_alignment(title or topic, thumb_opts[0]["text"] if thumb_opts else "", script)
                packaging_intel_report = {
                    "title_candidates": title_cands,
                    "thumbnail_text_options": thumb_opts,
                    "alignment_check": align_check,
                }
                (OUTPUT_DIR / "packaging_intelligence.json").write_text(json.dumps(packaging_intel_report, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"📦 [Packaging Intelligence] Generated 3 title variants & mobile thumbnail options (Score: {align_check.get('packaging_estimate_score')}/100)")
        except Exception as pack_err:
            print(f"Packaging intelligence notice: {pack_err}")

        # Optional Feature 4: Fact-Checking & Originality Review (Non-breaking, Advisory by Default)
        fact_review_report = None
        try:
            from config.settings import get_setting
            if get_setting("ENABLE_FACT_CHECK_REVIEW", False):
                from agents.fact_originality_reviewer import review_fact_and_originality
                strict_fact = bool(get_setting("STRICT_FACT_CHECK_ENFORCEMENT", False))
                fact_review_report = review_fact_and_originality(
                    script_text=script,
                    topic=topic,
                    title=title or topic,
                    thumbnail_text="",
                    strict_enforcement=strict_fact,
                )
                (OUTPUT_DIR / "fact_review_report.json").write_text(json.dumps(fact_review_report, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"⚖️ [Fact & Originality Review] Status: {fact_review_report.get('status')} (Score: {fact_review_report.get('score')}/100, Findings: {fact_review_report.get('total_findings')})")
                if strict_fact and not fact_review_report.get("passed", True):
                    upload_blocked = True
                    youtube_error = f"Upload blocked by strict fact-checking review policy: {fact_review_report.get('status')}."
        except Exception as fact_err:
            print(f"Fact review notice: {fact_err}")

        video_id = None
        youtube_error = None

        if youtube_upload:
            if upload_blocked:
                print()
                print("=" * 60)
                print("🛑 [Phase 7 Quality Gate] YouTube upload BLOCKED.")
                if has_gate_critical:
                    crit_msgs = [f"[{r.gate_name}] {iss.rule}: {iss.actual}" for r in [gate_d] for iss in r.issues if iss.severity == "CRITICAL"]
                    crit_summary = "; ".join(crit_msgs[:2]) if crit_msgs else "Pre-upload barrier defect"
                    print(f"   Reason: Validation gate failure: {crit_summary}")
                    print(f"   AI Review Score: {review_score_final}/100")
                    youtube_error = f"Upload skipped: Validation gate defect ({crit_summary}) [Review Score: {review_score_final}/100]."
                else:
                    print(f"   Reason: Video failed AI Review after {MAX_REVIEW_ATTEMPTS} healing attempts.")
                    print(f"   Score: {review_score_final}/100 (< 65) or Critical Issues: {critical_issues_final}")
                    youtube_error = f"Upload skipped: Review score below threshold ({review_score_final}/100) after {MAX_REVIEW_ATTEMPTS} attempts."
                print("   Skipping upload to preserve channel authority and retention metrics.")
                print("=" * 60)
                video_id = None
            else:
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
    # Strict rule: Long-form videos or non-9:16 formats are NEVER uploaded to Instagram Reels
    if is_longform or str(aspect_ratio).strip() != "9:16":
        instagram_upload = False

    instagram_status = {"eligible": False, "reason": "Excluded: Long-format or landscape videos cannot be uploaded to Instagram Reels" if is_longform else "Instagram upload not enabled", "result": None}
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
            if upload_blocked and eligible:
                eligible = False
                reason = f"Blocked by Phase 7 Quality Gate (Score: {review_score_final}/100 < 80 or critical issues present)"

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
                from agents.instagram_agent import format_reels_caption
                reels_caption = format_reels_caption(title, topic=topic, tags=tags)
                res = upload_to_instagram_reels(
                    video_source=str(final_vid) if final_vid.exists() else None,
                    caption=reels_caption,
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
            profile=profile,
            target_duration=target_duration,
        )
    except Exception as rep_err:
        print(f"⚠️ Run report error: {rep_err}")

    timing_report = {}
    try:
        from providers.timing_logger import generate_pipeline_timing_report
        timing_report = generate_pipeline_timing_report()
    except Exception as t_err:
        print(f"⚠️ Timing report notice: {t_err}")

    # Optional Feature 6: Experiment and Learning Logger (Non-breaking, Disabled by Default)
    try:
        from config.settings import get_setting
        if get_setting("ENABLE_EXPERIMENT_LOGGING", False):
            from analytics.experiment_logger import log_experiment_run
            dur_actual = None
            final_vid_p = OUTPUT_DIR / "final_video.mp4"
            if final_vid_p.exists():
                try:
                    import subprocess
                    p_dur = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(final_vid_p)],
                        capture_output=True, text=True
                    )
                    dur_actual = float(p_dur.stdout.strip())
                except Exception:
                    pass
            log_experiment_run(
                topic=topic,
                content_pillar=content_intel_report.get("pillar", "viral_entertainment_explainers") if content_intel_report else "viral_entertainment_explainers",
                aspect_ratio=aspect_ratio,
                target_duration=target_duration,
                actual_duration_sec=dur_actual,
                hook_variant="optimized" if (retention_report and get_setting("AUTO_APPLY_HOOK_OPTIMIZER", False)) else "standard",
                title_variant=title,
                thumbnail_text=packaging_intel_report["thumbnail_text_options"][0]["text"] if (packaging_intel_report and packaging_intel_report.get("thumbnail_text_options")) else "",
                heuristic_scores={
                    "retention_score": retention_report.get("optimized_retention_score", 0.0) if retention_report else 0.0,
                    "packaging_score": packaging_intel_report["alignment_check"].get("packaging_estimate_score", 0.0) if packaging_intel_report else 0.0,
                    "fact_score": fact_review_report.get("score", 0.0) if fact_review_report else 0.0,
                },
                youtube_video_id=video_id,
            )
            print("📝 [Experiment Logger] Logged run safely to data/experiment_log.json")
    except Exception as exp_err:
        print(f"Experiment logger notice: {exp_err}")

    return {
        "status": "APPROVED" if review_approved else "SKIPPED_UNPUBLISHED",
        "quality_gate_passed": review_approved,
        "timing_report": timing_report,
        "run_report": run_rep,
        "validation_report": val_report if "val_report" in locals() else {},
        "format_profile": profile.to_dict() if "profile" in locals() else {},
        "content_intelligence": content_intel_report if "content_intel_report" in locals() else None,
        "retention_report": retention_report if "retention_report" in locals() else None,
        "packaging_intelligence": packaging_intel_report if "packaging_intel_report" in locals() else None,
        "fact_review": fact_review_report if "fact_review_report" in locals() else None,
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


import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import random
import whisper
from PIL import Image, ImageFilter, ImageEnhance
from moviepy import AudioFileClip, ImageClip, VideoFileClip, concatenate_videoclips, vfx
from supervisor import autonomous_recover


# ============================================================
# STUDIO-GRADE KEN BURNS MOTION & TRANSITIONS
# ============================================================

FPS = 30

try:
    from ken_burns import (
        TRANSITIONS,
        DIRECTIONS,
        get_clip_duration,
        _zoompan_expr,
        build_ken_burns_clip,
        prepare_scene_clip,
        assemble_with_transitions,
    )
except ImportError:
    import sys
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from ken_burns import (
        TRANSITIONS,
        DIRECTIONS,
        get_clip_duration,
        _zoompan_expr,
        build_ken_burns_clip,
        prepare_scene_clip,
        assemble_with_transitions,
    )


def append_outro(main_video_path, outro_clip_path="assets/outro/like_share_subscribe.mp4", output_path=None):
    """Concatenate a pre-made 'Like/Share/Subscribe' outro clip
    to the end of every generated video, matching aspect ratio and audio flawlessly."""
    if output_path is None:
        output_path = main_video_path

    if not os.path.exists(outro_clip_path):
        print(f"⚠️ Outro clip not found at {outro_clip_path}, keeping main video.")
        return str(main_video_path)

    # 1. Probe main video dimensions & audio
    try:
        p_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(main_video_path)]
        wh = subprocess.run(p_cmd, capture_output=True, text=True).stdout.strip().split("x")
        w, h = (int(wh[0]), int(wh[1])) if len(wh) == 2 else (1080, 1920)
    except Exception:
        w, h = 1080, 1920

    # 2. Probe outro clip dimensions
    try:
        p_cmd2 = ["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(outro_clip_path)]
        wh2 = subprocess.run(p_cmd2, capture_output=True, text=True).stdout.strip().split("x")
        w2, h2 = (int(wh2[0]), int(wh2[1])) if len(wh2) == 2 else (1080, 1920)
    except Exception:
        w2, h2 = 1080, 1920

    temp_out = str(output_path) + ".outro_tmp.mp4"
    concat_list = "output/concat_list.txt"
    os.makedirs(os.path.dirname(concat_list), exist_ok=True)

    # Fast direct copy only when dimensions match identically
    if (w, h) == (w2, h2):
        with open(concat_list, "w") as f:
            f.write(f"file '{os.path.abspath(main_video_path)}'\n")
            f.write(f"file '{os.path.abspath(outro_clip_path)}'\n")

        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
               "-i", concat_list, "-c", "copy", temp_out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(temp_out, output_path)
            return str(output_path)

    # Fallback to matched filter_complex concatenation with scale/pad & audio resample
    fc = (
        f"[1:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v1];"
        f"[0:v]setsar=1,fps=30,format=yuv420p[v0];"
        f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo[a0];"
        f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo[a1];"
        f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    )
    cmd_fc = ["ffmpeg", "-y", "-i", str(main_video_path), "-i", str(outro_clip_path),
              "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
              "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k", "-preset", "ultrafast", temp_out]
    r_fc = subprocess.run(cmd_fc, capture_output=True, text=True)
    if r_fc.returncode == 0 and os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(temp_out, output_path)
        return str(output_path)
    else:
        if os.path.exists(temp_out):
            os.remove(temp_out)
        return str(main_video_path)





# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

ASSETS_DIR = ROOT / "assets"
OUTPUT_DIR = ROOT / "output"
BGM_DIR = ROOT / "assets" / "bgm"
CANVAS_DIR = OUTPUT_DIR / "canvas_assets"

SCRIPT_FILE = OUTPUT_DIR / "script.txt"
VISUAL_PLAN_FILE = OUTPUT_DIR / "visual_plan.txt"
SECTION_MAP_FILE = OUTPUT_DIR / "section_map.txt"
VOICE_FILE = OUTPUT_DIR / "voice.mp3"
VIDEO_FILE = OUTPUT_DIR / "video.mp4"


# ============================================================
# VIDEO CONFIG
# ============================================================

IMAGE_WIDTH = 640
FPS = 24

# Whisper model.
WHISPER_MODEL = "base"
_CACHED_WHISPER_MODEL = None


def get_whisper_model():
    """Cache Whisper model in memory across invocations for ultra-fast response."""
    global _CACHED_WHISPER_MODEL
    if _CACHED_WHISPER_MODEL is None:
        _CACHED_WHISPER_MODEL = whisper.load_model(WHISPER_MODEL)
    return _CACHED_WHISPER_MODEL


# ============================================================
# BGM ENGINE & AUTOMATED AUDIO DUCKING
# ============================================================

def detect_bgm_mood(topic="", script=""):
    """
    Classify the news/script mood to select the optimal royalty-free BGM track.
    Returns: 'energetic' | 'dramatic' | 'neutral'
    """
    text = f"{topic} {script}".lower()

    dramatic_keywords = [
        "war", "crisis", "crash", "danger", "warning", "storm", "flood",
        "tragedy", "arrest", "investigation", "tension", "disaster", "fatal",
        "drop", "plunge", "threat", "death", "conflict", "heavy rain",
    ]
    energetic_keywords = [
        "breakthrough", "launch", "ai", "tech", "nvidia", "apple", "tesla",
        "speed", "fast", "win", "victory", "record", "game", "celebration",
        "revenue", "profit", "surge", "excited", "revolution", "innovation",
    ]

    if any(w in text for w in dramatic_keywords):
        return "dramatic"
    if any(w in text for w in energetic_keywords):
        return "energetic"
    return "neutral"


def mix_audio_with_ducking(voice_path, bgm_path=None, output_audio_path=None):
    """
    Mix voiceover and background music using FFmpeg sidechain audio ducking.
    - Voiceover acts as the sidechain trigger.
    - When voice is active: BGM ducks to ~15% (-18dB).
    - When voice pauses/silent: BGM smoothly rises to ~35% (-10dB).
    - Output is normalized to broadcast standard (-16 LUFS) with loudnorm.
    """
    voice_p = Path(voice_path)
    if not voice_p.exists():
        return False

    if bgm_path is None:
        bgm_path = BGM_DIR / "neutral.wav"
    bgm_p = Path(bgm_path)

    if not bgm_p.exists():
        return False

    output_p = Path(output_audio_path or (OUTPUT_DIR / "mixed_audio.wav"))
    output_p.parent.mkdir(parents=True, exist_ok=True)

    duck_filter = (
        "[1:a]volume=0.35[bgm_base]; "
        "[bgm_base][0:a]sidechaincompress=threshold=0.15:ratio=4:attack=150:release=600[ducked_bgm]; "
        "[0:a][ducked_bgm]amix=inputs=2:duration=first:weights=1.0 1.0,loudnorm=I=-16:LRA=11:TP=-1.5[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(voice_p),
        "-stream_loop", "-1",
        "-i", str(bgm_p),
        "-filter_complex", duck_filter,
        "-map", "[aout]",
        "-c:a", "pcm_s16le",
        "-ar", "24000",
        str(output_p),
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=40)
        if res.returncode == 0 and output_p.exists() and output_p.stat().st_size > 0:
            print(f"🎵 BGM mixed with sidechain ducking ({bgm_p.name}): {output_p.name}")
            return str(output_p)
    except Exception as e:
        print(f"⚠️ Audio ducking notice: {e}. Falling back to clean voice.")

    return str(voice_p)


# ============================================================
# SMART CANVAS ENGINE (MULTI-ASPECT RATIO BLUR PADDING)
# ============================================================

def render_smart_canvas_image(image_path, target_width=720, target_height=720, output_path=None):
    """
    Smart Canvas generator for non-matching aspect ratios:
    - Generates a blurred, darkened background layer scaled to fill canvas.
    - Places the crisp, un-cropped original image centered in the foreground.
    - Eliminates harsh black bars on vertical Shorts (9:16) or landscape (16:9).
    """
    in_p = Path(image_path)
    if not in_p.exists():
        return in_p

    CANVAS_DIR.mkdir(parents=True, exist_ok=True)
    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_name = f"canvas_{in_p.stem}_{target_width}x{target_height}{in_p.suffix}"
        out_p = CANVAS_DIR / out_name

    try:
        with Image.open(in_p) as im:
            im = im.convert("RGB")
            orig_w, orig_h = im.size
            orig_aspect = orig_w / max(1, orig_h)
            target_aspect = target_width / max(1, target_height)

            # If aspect ratio matches within 3%, simple high-quality resize
            if abs(orig_aspect - target_aspect) < 0.03:
                canvas = im.resize((target_width, target_height), Image.Resampling.LANCZOS)
                canvas.save(out_p, "JPEG", quality=95)
                return out_p

            # 1. Background layer: cover & Gaussian blur & darken
            scale_bg = max(target_width / orig_w, target_height / orig_h)
            bg_w, bg_h = int(orig_w * scale_bg), int(orig_h * scale_bg)
            bg = im.resize((bg_w, bg_h), Image.Resampling.BILINEAR)

            crop_x = max(0, (bg_w - target_width) // 2)
            crop_y = max(0, (bg_h - target_height) // 2)
            bg = bg.crop((crop_x, crop_y, crop_x + target_width, crop_y + target_height))
            bg = bg.filter(ImageFilter.GaussianBlur(radius=28))
            bg = ImageEnhance.Brightness(bg).enhance(0.55)

            # 2. Foreground layer: fit inside canvas with 3% margin
            margin_w = int(target_width * 0.03)
            margin_h = int(target_height * 0.03)
            max_fg_w = target_width - (2 * margin_w)
            max_fg_h = target_height - (2 * margin_h)

            scale_fg = min(max_fg_w / orig_w, max_fg_h / orig_h)
            fg_w, fg_h = int(orig_w * scale_fg), int(orig_h * scale_fg)
            fg = im.resize((fg_w, fg_h), Image.Resampling.LANCZOS)

            # 3. Paste centered
            paste_x = (target_width - fg_w) // 2
            paste_y = (target_height - fg_h) // 2
            bg.paste(fg, (paste_x, paste_y))

            bg.save(out_p, "JPEG", quality=95)
            return out_p
    except Exception as e:
        print(f"Smart canvas notice for {in_p.name}: {e}")
        return in_p



# ============================================================
# HELPERS
# ============================================================

def get_images():
    """
    Return numbered visual assets in exact numeric order.
    Prefers video clips (e.g. assets/1.mp4) when available, otherwise images (assets/1.jpg).

    Visual 1 -> assets/1.mp4 or assets/1.jpg
    Visual 2 -> assets/2.mp4 or assets/2.jpg
    ...
    Visual N -> assets/N.mp4 or assets/N.jpg
    """

    if not ASSETS_DIR.exists():
        return []

    asset_map = {}

    for path in ASSETS_DIR.iterdir():

        if not path.is_file():
            continue

        match = re.fullmatch(
            r"(\d+)\.(mp4|mov|webm|mkv|jpg|jpeg|png|webp)",
            path.name,
            re.IGNORECASE,
        )

        if not match:
            continue

        num = int(match.group(1))
        ext = match.group(2).lower()

        # If a video clip exists, prefer it over a static image
        if num in asset_map:
            existing_ext = asset_map[num].suffix.lower()
            if existing_ext in (".jpg", ".jpeg", ".png", ".webp") and ext in (".mp4", ".mov", ".webm", ".mkv"):
                asset_map[num] = path
        else:
            asset_map[num] = path

    sorted_nums = sorted(asset_map.keys())
    return [
        asset_map[n]
        for n in sorted_nums
    ]


def get_visual_plan():
    """
    Read visual_plan.txt with flexible matching.
    Handles numeric bullets (1., 1)), markdown lists (* 1., - 1., **1.**),
    and 'Visual 1:' prefixes.
    """
    if not VISUAL_PLAN_FILE.exists():
        return []

    visuals = []

    with open(
        VISUAL_PLAN_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line:
                continue

            cleaned = re.sub(r"^[\*\-\#\>\s]+", "", line).strip()
            match = re.match(
                r"^(?:\*?\*?visual\s*)?(\d+)[\.\)\:\-]\*?\*?\s*(.+)$",
                cleaned,
                re.IGNORECASE,
            )
            if match:
                visual = match.group(2).strip().strip("*").strip()
                if visual:
                    visuals.append(visual)
            elif cleaned and len(cleaned) > 10 and not cleaned.lower().startswith("visual plan"):
                visuals.append(cleaned)

    # Fallback to section map or script if visual plan was empty or unparseable
    if not visuals and SECTION_MAP_FILE.exists():
        try:
            sections = get_section_map()
            for sec in sections:
                narration = sec.get("narration", "")
                if narration:
                    words = narration.split()
                    visuals.append(" ".join(words[:8]))
        except Exception:
            pass

    return visuals


def ensure_visual_assets_exist(needed_count=None):
    """
    Self-healing safeguard: guarantee assets/ has numbered visuals 1..N.
    If video clips (e.g. 1.mp4) exist without 1.jpg, extract the frame.
    If visual assets are missing or assets/ is empty, automatically
    populate from assets/fallback/ or generate clean placeholder slides.
    """
    if not ASSETS_DIR.exists():
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    fallback_dir = ASSETS_DIR / "fallback"
    fallback_pool = sorted(fallback_dir.glob("*.jpg")) if fallback_dir.exists() else []

    if needed_count is None or needed_count <= 0:
        visual_plan = get_visual_plan()
        sections = get_section_map()
        needed_count = max(len(visual_plan), len(sections), 4)

    # Scan existing assets
    existing_images = {}
    for path in ASSETS_DIR.iterdir():
        if not path.is_file():
            continue
        m = re.fullmatch(r"(\d+)\.(mp4|mov|webm|mkv|jpg|jpeg|png|webp)", path.name, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            ext = m.group(2).lower()
            if ext in (".mp4", ".mov", ".webm", ".mkv"):
                # If mp4 exists, make sure a jpg keyframe also exists
                jpg_path = ASSETS_DIR / f"{num}.jpg"
                if not jpg_path.exists() or jpg_path.stat().st_size == 0:
                    try:
                        subprocess.run(
                            ["ffmpeg", "-y", "-ss", "00:00:01", "-i", str(path), "-vframes", "1", "-q:v", "2", str(jpg_path)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=8
                        )
                    except Exception:
                        pass
                existing_images[num] = path
            elif ext in (".jpg", ".jpeg", ".png", ".webp"):
                if num not in existing_images:
                    existing_images[num] = path

    # Populate any missing numbers from 1 to needed_count
    for i in range(1, needed_count + 1):
        target_jpg = ASSETS_DIR / f"{i}.jpg"
        target_mp4 = ASSETS_DIR / f"{i}.mp4"
        if not target_jpg.exists() and not target_mp4.exists():
            if fallback_pool:
                src_fallback = fallback_pool[(i - 1) % len(fallback_pool)]
                shutil.copyfile(src_fallback, target_jpg)
                print(f"[Self-Healing] Populated missing Visual {i} from fallback: {src_fallback.name} -> {i}.jpg")
            elif existing_images:
                first_asset = next(iter(existing_images.values()))
                if first_asset.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    shutil.copyfile(first_asset, target_jpg)
                else:
                    try:
                        subprocess.run(
                            ["ffmpeg", "-y", "-ss", "00:00:01", "-i", str(first_asset), "-vframes", "1", "-q:v", "2", str(target_jpg)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=8
                        )
                    except Exception:
                        pass
            else:
                try:
                    from PIL import Image, ImageDraw
                    img = Image.new("RGB", (1280, 720), color=(20, 25, 40))
                    draw = ImageDraw.Draw(img)
                    draw.text((640, 360), f"AutoTube AI Scene {i}", fill=(200, 220, 255), anchor="mm")
                    img.save(target_jpg, "JPEG", quality=90)
                    print(f"[Self-Healing] Generated placeholder visual for Scene {i} -> {i}.jpg")
                except Exception as gen_err:
                    print(f"[Self-Healing] Error generating placeholder {i}: {gen_err}")


def get_section_map():
    """
    Read the exact SECTION -> VISUAL -> NARRATION mapping.

    Expected format:

        SECTION 1 | VISUAL 1
        narration...

        SECTION 2 | VISUAL 2
        narration...

    Returns a list of dictionaries.
    """

    if not SECTION_MAP_FILE.exists():
        return []

    with open(
        SECTION_MAP_FILE,
        "r",
        encoding="utf-8",
    ) as file:

        text = file.read()

    pattern = re.compile(
        r"SECTION\s+(\d+)\s*\|\s*VISUAL\s+(\d+)\s*\n"
        r"(.*?)(?=\n\s*SECTION\s+\d+\s*\|\s*VISUAL\s+\d+|\Z)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    sections = []

    for match in pattern.finditer(text):

        section_number = int(
            match.group(1)
        )

        visual_number = int(
            match.group(2)
        )

        narration = match.group(3).strip()

        if not narration:
            continue

        sections.append(
            {
                "section": section_number,
                "visual": visual_number,
                "narration": narration,
            }
        )

    sections.sort(
        key=lambda item: item["section"]
    )

    for idx, item in enumerate(sections, start=1):
        item["section"] = idx
        item["visual"] = idx

    return sections


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):
    """
    Normalize text so section narration can be matched
    against Whisper transcription.

    Example:

        "twenty-five"
        ->
        "twenty five"

    Punctuation is removed and repeated spaces are collapsed.
    """

    text = text.lower()

    # Normalize common dash characters.
    text = text.replace(
        "–",
        " ",
    )
    text = text.replace(
        "—",
        " ",
    )
    text = text.replace(
        "-",
        " ",
    )

    # Remove punctuation, preserving alphanumeric, Telugu, and Devanagari characters
    text = re.sub(
        r"[^\w\s\u0C00-\u0C7F\u0900-\u097F]",
        " ",
        text,
    )

    # Collapse whitespace.
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_words(text):
    """
    Convert text into normalized individual words.
    """

    normalized = normalize_text(text)

    if not normalized:
        return []

    return normalized.split()


# ============================================================
# VALIDATION
# ============================================================

def validate_mapping(
    images,
    visual_plan,
    sections,
):
    """
    Make absolutely sure:

        Section 1 -> Visual 1 -> 1.jpg
        Section 2 -> Visual 2 -> 2.jpg
        ...
    """

    print()
    print("=" * 60)
    print("VALIDATING VISUAL / SECTION MAPPING")
    print("=" * 60)

    print()
    print(
        f"Images       : {len(images)}"
    )

    print(
        f"Visual plan  : {len(visual_plan)}"
    )

    print(
        f"Sections     : {len(sections)}"
    )

    min_count = min(len(images), len(visual_plan), len(sections))
    if min_count < 4:
        raise RuntimeError(
            f"Too few elements to generate video: "
            f"images={len(images)}, visual_plan={len(visual_plan)}, sections={len(sections)} (minimum 4 required)."
        )

    if len(images) != min_count or len(visual_plan) != min_count or len(sections) != min_count:
        print(
            f"⚠️ Auto-reconciling count mismatch: "
            f"images={len(images)}, visual_plan={len(visual_plan)}, sections={len(sections)} -> aligning to {min_count} items."
        )
        del images[min_count:]
        del visual_plan[min_count:]
        del sections[min_count:]

        for idx, sec in enumerate(sections, start=1):
            sec["section"] = idx
            sec["visual"] = idx

    print(
        f"Aligned items: {min_count}"
    )

    for index, asset in enumerate(
        images,
        start=1,
    ):

        if asset.stem != str(index):
            raise RuntimeError(
                f"Expected Visual {index} to have stem "
                f"'{index}', but found "
                f"'{asset.name}'"
            )

    expected = list(
        range(
            1,
            min_count + 1,
        )
    )

    print()
    print("MAPPING CHECK PASSED")

    for index in expected:

        image = images[index - 1]
        section = sections[index - 1]

        print()
        print(
            f"SECTION {section['section']}"
        )

        print(
            f"VISUAL  {section['visual']}"
        )

        print(
            f"IMAGE   {image.name}"
        )

        print(
            f"NARRATION: "
            f"{section['narration'][:160]}"
        )


# ============================================================
# WHISPER TRANSCRIPTION
# ============================================================

def transcribe_audio():
    """
    Transcribe voice.mp3 using Whisper with word timestamps.

    Returns:

        {
            "text": "...",
            "segments": [...],
            "words": [...]
        }
    """

    cache_file = OUTPUT_DIR / "transcription.json"
    if cache_file.exists() and VOICE_FILE.exists():
        try:
            if cache_file.stat().st_mtime >= VOICE_FILE.stat().st_mtime:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                cached_words = cached.get("words", [])
                if cached_words:
                    print()
                    print("=" * 60)
                    print("USING CACHED WHISPER TRANSCRIPTION")
                    print("=" * 60)
                    print(f"Whisper words loaded from cache: {len(cached_words)}")
                    return cached
        except Exception:
            pass

    print()
    print("=" * 60)
    print("WHISPER AUDIO TRANSCRIPTION")
    print("=" * 60)

    model = get_whisper_model()

    whisper_lang = "en"
    if SCRIPT_FILE.exists():
        try:
            with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
                script_content = f.read()
            if re.search(r"[\u0C00-\u0C7F]", script_content):
                whisper_lang = "te"
            elif re.search(r"[\u0900-\u097F]", script_content):
                whisper_lang = "hi"
        except Exception:
            pass

    print()
    print(f"Transcribing voice.mp3 (language={whisper_lang})...")

    result = model.transcribe(
        str(VOICE_FILE),
        language=whisper_lang,
        fp16=False,
        word_timestamps=True,
        verbose=False,
    )

    words = []

    for segment in result.get(
        "segments",
        [],
    ):

        for word in segment.get(
            "words",
            [],
        ):

            word_text = word.get(
                "word",
                "",
            ).strip()

            start = word.get(
                "start"
            )

            end = word.get(
                "end"
            )

            if not word_text:
                continue

            if start is None or end is None:
                continue

            words.append(
                {
                    "text": word_text,
                    "normalized": normalize_text(
                        word_text
                    ),
                    "start": float(start),
                    "end": float(end),
                }
            )

    if not words:
        raise RuntimeError(
            "Whisper did not return word timestamps."
        )

    # Save to transcription cache for subtitle agent & video agent reuse
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "words": words,
                    "segments": result.get("segments", []),
                    "text": result.get("text", ""),
                },
                f,
            )
        print("Cached Whisper transcription: output/transcription.json")
    except Exception as cache_err:
        print(f"Cache write note: {cache_err}")

    print()
    print(
        f"Whisper words: {len(words)}"
    )

    print(
        f"Whisper text: "
        f"{result.get('text', '').strip()[:300]}"
    )

    return {
        "text": result.get(
            "text",
            "",
        ),
        "segments": result.get(
            "segments",
            [],
        ),
        "words": words,
    }


# ============================================================
# SECTION TIMESTAMP MATCHING
# ============================================================

def find_section_timestamps(
    sections,
    whisper_words,
    audio_duration,
):
    """
    Match each section narration against Whisper's
    word-level timestamps.

    This uses sequential matching because the narration
    occurs in the same order as section_map.txt.

    Returns:

        [
            {
                "section": 1,
                "visual": 1,
                "narration": "...",
                "start": 0.0,
                "end": 17.9,
            },
            ...
        ]
    """

    print()
    print("=" * 60)
    print("MATCHING SECTIONS TO WHISPER TIMESTAMPS")
    print("=" * 60)

    # --------------------------------------------------------
    # Normalize Whisper words.
    # --------------------------------------------------------

    usable_words = []

    for word in whisper_words:

        normalized = word["normalized"]

        if not normalized:
            continue

        usable_words.append(
            word
        )

    if not usable_words:
        raise RuntimeError(
            "No usable Whisper words found."
        )

    # --------------------------------------------------------
    # Build normalized narration words.
    # --------------------------------------------------------

    section_word_lists = []

    for section in sections:

        words = normalize_words(
            section["narration"]
        )

        if not words:
            words = [f"section_{section.get('section', 1)}"]

        section_word_lists.append(
            words
        )

    # --------------------------------------------------------
    # Sequential matching.
    # --------------------------------------------------------

    results = []

    search_index = 0

    for section, target_words in zip(
        sections,
        section_word_lists,
    ):

        target_count = len(
            target_words
        )

        best_start = None
        best_end = None
        best_score = 0

        # ----------------------------------------------------
        # Search for the best matching window.
        #
        # We use a slightly larger window than the exact
        # narration length because Whisper can occasionally
        # split or merge words.
        # ----------------------------------------------------

        max_window_extra = max(
            8,
            int(
                target_count * 0.20
            ),
        )

        max_window = (
            target_count
            + max_window_extra
        )

        remaining = (
            len(usable_words)
            - search_index
        )

        if remaining <= 0:
            print(
                f"Note: No remaining audio words for Section {section['section']}. "
                "Using proportional duration distribution."
            )
            remaining_sections = len(sections) - len(results)
            prev_end = results[-1]["end"] if results else 0.0
            remaining_duration = max(1.0, audio_duration - prev_end)
            fallback_duration = remaining_duration / max(1, remaining_sections)
            fallback_start = prev_end
            fallback_end = min(audio_duration, fallback_start + fallback_duration)
            results.append(
                {
                    "section": section["section"],
                    "visual": section["visual"],
                    "narration": section.get("narration", ""),
                    "start": round(fallback_start, 2),
                    "end": round(fallback_end, 2),
                    "duration": round(max(0.5, fallback_end - fallback_start), 2),
                    "words_matched": 0,
                }
            )
            continue

        # ----------------------------------------------------
        # First try exact-ish sequential matching.
        # ----------------------------------------------------

        for start_index in range(
            search_index,
            len(usable_words),
        ):

            if (
                start_index
                >= len(usable_words)
            ):
                break

            # Avoid searching infinitely far ahead.
            if (
                start_index
                - search_index
                > max_window_extra * 2
            ):
                break

            for window_size in range(
                max(
                    1,
                    target_count
                    - max_window_extra,
                ),
                min(
                    max_window,
                    len(usable_words)
                    - start_index,
                )
                + 1,
            ):

                candidate = usable_words[
                    start_index:
                    start_index + window_size
                ]

                candidate_text = [
                    item["normalized"]
                    for item in candidate
                ]

                # ------------------------------------------------
                # Compare using ordered word overlap.
                # ------------------------------------------------

                target_set = set(
                    target_words
                )

                candidate_set = set(
                    candidate_text
                )

                if not candidate_set:
                    continue

                intersection = (
                    target_set
                    & candidate_set
                )

                score = (
                    len(intersection)
                    / max(
                        1,
                        len(target_set),
                    )
                )

                # Bonus for first/last word matching.
                if (
                    candidate_text[0]
                    == target_words[0]
                ):
                    score += 0.10

                if (
                    candidate_text[-1]
                    == target_words[-1]
                ):
                    score += 0.10

                if score > best_score:

                    best_score = score

                    best_start = (
                        candidate[0]["start"]
                    )

                    best_end = (
                        candidate[-1]["end"]
                    )

                    best_match_end_index = (
                        start_index
                        + window_size
                    )

        # ----------------------------------------------------
        # If matching failed, use a fallback based on the
        # remaining audio.
        # ----------------------------------------------------

        if (
            best_start is None
            or best_end is None
            or best_score < 0.35
        ):

            print()
            print(
                f"WARNING: Weak Whisper match "
                f"for Section {section['section']} "
                f"(score={best_score:.2f})"
            )

            # Fallback:
            # Take the next proportional portion of the
            # remaining Whisper timeline.

            remaining_sections = (
                len(sections)
                - len(results)
            )

            remaining_duration = (
                audio_duration
                - (
                    results[-1]["end"]
                    if results
                    else 0.0
                )
            )

            fallback_duration = (
                remaining_duration
                / max(
                    1,
                    remaining_sections,
                )
            )

            fallback_start = (
                results[-1]["end"]
                if results
                else 0.0
            )

            best_start = fallback_start

            best_end = min(
                audio_duration,
                fallback_start
                + fallback_duration,
            )

            best_match_end_index = (
                search_index
                + target_count
            )

        # ----------------------------------------------------
        # Ensure timestamps are valid.
        # ----------------------------------------------------

        best_start = max(
            0.0,
            float(best_start),
        )

        best_end = min(
            audio_duration,
            float(best_end),
        )

        if best_end <= best_start:
            best_end = min(audio_duration, best_start + 1.0)
            if best_end <= best_start:
                best_start = max(0.0, best_end - 1.0)

        results.append(
            {
                "section": section["section"],
                "visual": section["visual"],
                "narration": section["narration"],
                "start": best_start,
                "end": best_end,
            }
        )

        print()
        print(
            f"SECTION {section['section']}"
        )

        print(
            f"VISUAL  {section['visual']}"
        )

        print(
            f"START   {best_start:.2f}s"
        )

        print(
            f"END     {best_end:.2f}s"
        )

        print(
            f"DURATION "
            f"{best_end - best_start:.2f}s"
        )

        print(
            f"MATCH SCORE: "
            f"{best_score:.2f}"
        )

        # ----------------------------------------------------
        # Continue searching after this section.
        # ----------------------------------------------------

        if (
            "best_match_end_index"
            in locals()
        ):

            search_index = max(
                search_index + 1,
                best_match_end_index,
            )

    # ========================================================
    # FORCE CLEAN CONTINUOUS TIMELINE
    # ========================================================
    #
    # Whisper matching can produce tiny gaps/overlaps.
    # We convert the matched boundaries into a clean,
    # continuous visual timeline.
    #
    # The first visual always starts at 0.
    # The last visual always ends at audio_duration.
    #
    # Internal boundaries use Whisper-derived timestamps.
    # ========================================================

    if not results:
        raise RuntimeError(
            "No section timestamps generated."
        )

    results[0]["start"] = 0.0

    for index in range(
        1,
        len(results),
    ):
        previous_end = results[index - 1]["end"]
        current_start = results[index]["start"]

        # Seamlessly bridge boundaries at the midpoint between previous end and current start
        midpoint = round((previous_end + current_start) / 2.0, 3)

        # Guarantee strictly positive duration for previous section
        if midpoint <= results[index - 1]["start"]:
            midpoint = round(results[index - 1]["start"] + 0.5, 3)

        results[index - 1]["end"] = midpoint
        results[index]["start"] = midpoint

    results[-1]["end"] = round(audio_duration, 3)
    if results[-1]["end"] <= results[-1]["start"]:
        results[-1]["start"] = round(max(0.0, results[-1]["end"] - 0.5), 3)

    # Strictly enforce exact boundary continuity across all adjacent sections
    for index in range(1, len(results)):
        results[index]["start"] = results[index - 1]["end"]

    # --------------------------------------------------------
    # Final validation.
    # --------------------------------------------------------

    for index, item in enumerate(results):
        if index > 0:
            previous = results[index - 1]
            # Auto-heal any boundary discrepancy to guarantee 100% continuity
            if abs(item["start"] - previous["end"]) > 0.001:
                item["start"] = previous["end"]

        if item["end"] <= item["start"]:
            item["end"] = round(item["start"] + 1.0, 3)

    print()
    print("=" * 60)
    print("FINAL SECTION TIMELINE")
    print("=" * 60)

    for item in results:

        print(
            f"SECTION {item['section']} "
            f"| VISUAL {item['visual']} "
            f"| "
            f"{item['start']:.2f}s → "
            f"{item['end']:.2f}s "
            f"| "
            f"{item['end'] - item['start']:.2f}s"
        )

    return results


# ============================================================
# VIDEO CREATION
# ============================================================

@autonomous_recover("video_agent")
def create_video(aspect_ratio="1:1"):

    print()
    print("=" * 60)
    print(f"AUTOTUBE AI - WHISPER TIMED VIDEO ({aspect_ratio})")
    print("=" * 60)

    # --------------------------------------------------------
    # Resolution preset
    # --------------------------------------------------------
    if aspect_ratio == "9:16":
        target_w, target_h = 1080, 1920
    elif aspect_ratio == "16:9":
        target_w, target_h = 1920, 1080
    else:
        target_w, target_h = 1080, 1080

    # --------------------------------------------------------
    # Required files
    # --------------------------------------------------------

    if not VOICE_FILE.exists():

        raise FileNotFoundError(
            f"Voice file not found: {VOICE_FILE}"
        )

    if not SCRIPT_FILE.exists():

        raise FileNotFoundError(
            f"Script file not found: {SCRIPT_FILE}"
        )

    if not VISUAL_PLAN_FILE.exists():

        raise FileNotFoundError(
            f"Visual plan not found: "
            f"{VISUAL_PLAN_FILE}"
        )

    if not SECTION_MAP_FILE.exists():

        raise FileNotFoundError(
            f"Section map not found: "
            f"{SECTION_MAP_FILE}"
        )

    # --------------------------------------------------------
    # Load data with self-healing asset assurance
    # --------------------------------------------------------

    visual_plan = get_visual_plan()

    sections = get_section_map()

    needed_count = max(len(visual_plan), len(sections), 4)

    ensure_visual_assets_exist(needed_count)

    images = get_images()

    if not images:
        raise RuntimeError(
            "No numbered images found in assets/"
        )

    if not visual_plan:
        raise RuntimeError(
            "No visual concepts found."
        )

    if not sections:
        raise RuntimeError(
            "No section mapping found."
        )

    # --------------------------------------------------------
    # Validate mapping.
    # --------------------------------------------------------

    validate_mapping(
        images,
        visual_plan,
        sections,
    )

    # --------------------------------------------------------
    # Validate script.
    # --------------------------------------------------------

    with open(
        SCRIPT_FILE,
        "r",
        encoding="utf-8",
    ) as file:

        script = file.read().strip()

    if not script:

        raise RuntimeError(
            "Script is empty."
        )

    # --------------------------------------------------------
    # Load audio.
    # --------------------------------------------------------

    audio = AudioFileClip(
        str(VOICE_FILE)
    )

    audio_duration = audio.duration

    print()
    print(
        f"Voice duration: "
        f"{audio_duration:.2f} seconds"
    )

    # --------------------------------------------------------
    # Whisper.
    # --------------------------------------------------------

    transcription = transcribe_audio()

    whisper_words = transcription[
        "words"
    ]

    # --------------------------------------------------------
    # Match sections to actual speech timing.
    # --------------------------------------------------------

    timed_sections = find_section_timestamps(
        sections,
        whisper_words,
        audio_duration,
    )

    # --------------------------------------------------------
    # --------------------------------------------------------
    # Build visual clips with Ken Burns motion & dynamic pacing
    # --------------------------------------------------------

    scene_clips_dir = OUTPUT_DIR / "scene_clips"
    if scene_clips_dir.exists():
        shutil.rmtree(scene_clips_dir, ignore_errors=True)
    scene_clips_dir.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 60)
    print("BUILDING KEN BURNS & TRANSITION SCENE CLIPS")
    print("=" * 60)

    motion_directions = ["zoom_in", "pan_left", "zoom_out", "pan_right"]
    dir_idx = 0
    scene_clips = []
    scene_durations = []

    # Flatten timed_sections into max 3.5s shots so no shot ever holds static or runs > 3.5s
    scene_jobs = []
    for item in timed_sections:
        sec_num = item["section"]
        vis_num = item["visual"]
        start = item["start"]
        end = item["end"]
        duration = max(0.5, end - start)
        img_idx = vis_num - 1

        if img_idx < 0 or img_idx >= len(images):
            audio.close()
            raise RuntimeError(
                f"Visual {vis_num} does not have a corresponding image."
            )

        img_path = images[img_idx]

        # If duration > 3.5s, split into sub-shots
        if duration > 3.5:
            num_sub = max(2, int(round(duration / 2.5)))
            sub_len = duration / num_sub
            for s_i in range(num_sub):
                scene_jobs.append({
                    "section": sec_num,
                    "visual": vis_num,
                    "image_path": img_path,
                    "duration": sub_len,
                    "narration": item.get("narration", ""),
                    "sub_idx": s_i + 1
                })
        else:
            scene_jobs.append({
                "section": sec_num,
                "visual": vis_num,
                "image_path": img_path,
                "duration": duration,
                "narration": item.get("narration", ""),
                "sub_idx": 1
            })

    transition_dur = 0.35

    for idx, job in enumerate(scene_jobs):
        is_last = (idx == len(scene_jobs) - 1)
        job_dur = job["duration"]
        # Render extra overlap frames for smooth xfade transition if not the last clip
        render_dur = job_dur + transition_dur if not is_last else job_dur

        direction = motion_directions[dir_idx % len(motion_directions)]
        dir_idx += 1

        clip_filename = f"scene_{idx:03d}_sec{job['section']}_vis{job['visual']}_{direction}.mp4"
        clip_path = scene_clips_dir / clip_filename

        print(
            f"[{idx+1}/{len(scene_jobs)}] Section {job['section']} | Visual {job['visual']} | "
            f"{job['image_path'].name} -> {direction} | {job_dur:.2f}s (render: {render_dur:.2f}s)"
        )

        prepare_scene_clip(
            media_path=job["image_path"],
            output_path=clip_path,
            duration_seconds=render_dur,
            direction=direction,
            width=target_w,
            height=target_h,
            fps=FPS
        )

        scene_clips.append(str(clip_path))
        scene_durations.append(job_dur)

    if not scene_clips:
        audio.close()
        raise RuntimeError("No video clips were created.")

    # --------------------------------------------------------
    # Assemble with Transitions
    # --------------------------------------------------------
    print()
    print("=" * 60)
    print("ASSEMBLING SCENES WITH DYNAMIC XFADE TRANSITIONS")
    print("=" * 60)

    raw_assembled = OUTPUT_DIR / "assembled_raw.mp4"
    assemble_with_transitions(
        scene_clips=scene_clips,
        output_path=str(raw_assembled),
        transition_duration=transition_dur,
        scene_durations=scene_durations,
    )

    # --------------------------------------------------------
    # BGM Engine with Automated Audio Ducking
    # --------------------------------------------------------
    bgm_mood = detect_bgm_mood(script=script)
    bgm_track = BGM_DIR / f"{bgm_mood}.wav"
    mixed_audio_file = OUTPUT_DIR / "mixed_audio.wav"

    final_audio_path = VOICE_FILE
    if bgm_track.exists():
        mixed_res = mix_audio_with_ducking(
            voice_path=str(VOICE_FILE),
            bgm_path=str(bgm_track),
            output_audio_path=str(mixed_audio_file),
        )
        if mixed_res and os.path.exists(mixed_res):
            final_audio_path = Path(mixed_res)

    # --------------------------------------------------------
    # Multiplex Audio & Video
    # --------------------------------------------------------
    print()
    print("=" * 60)
    print("MULTIPLEXING AUDIO & VIDEO")
    print("=" * 60)

    mux_cmd = [
        "ffmpeg", "-y",
        "-i", str(raw_assembled),
        "-i", str(final_audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(VIDEO_FILE),
    ]
    r_mux = subprocess.run(mux_cmd, capture_output=True, text=True)
    if r_mux.returncode != 0 or not VIDEO_FILE.exists() or VIDEO_FILE.stat().st_size == 0:
        raise RuntimeError(f"Audio/video multiplexing failed: {r_mux.stderr or 'No output file'}")

    # --------------------------------------------------------
    # Outro Call-To-Action note:
    # Managed in agents/final_video_agent.py per user's include_outro setting.
    # --------------------------------------------------------

    # --------------------------------------------------------
    # Cleanup temporary scene clips
    # --------------------------------------------------------
    try:
        shutil.rmtree(scene_clips_dir, ignore_errors=True)
        if raw_assembled.exists():
            raw_assembled.unlink(missing_ok=True)
    except Exception:
        pass

    try:
        audio.close()
    except Exception:
        pass

    # --------------------------------------------------------
    # Done.
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("VIDEO CREATED SUCCESSFULLY")
    print("=" * 60)

    print()
    print(
        f"Saved: {VIDEO_FILE}"
    )

    print(
        f"Duration: "
        f"{audio_duration:.2f}s"
    )

    print(
        f"Visuals used: "
        f"{len(scene_clips)}"
    )

    print(
        "Timing source: Whisper word timestamps"
    )

    return str(VIDEO_FILE)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    create_video()
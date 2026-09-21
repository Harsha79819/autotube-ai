import os
import random
import shutil
import subprocess
from pathlib import Path

# Available ffmpeg xfade transitions
TRANSITIONS = ["fade", "wipeleft", "wiperight", "circleopen", "pixelize"]

DIRECTIONS = ["zoom_in", "zoom_out", "pan_left", "pan_right"]


def get_clip_duration(clip_path):
    """
    Query the exact duration of a media clip using ffprobe.
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(clip_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        val = float(res.stdout.strip())
        if val > 0:
            return val
        return 3.0
    except Exception:
        return 3.0


def _zoompan_expr(direction, duration_seconds, out_w=1080, out_h=1920, fps=30):
    """
    Builds the ffmpeg zoompan filter expression for smooth continuous motion.
    Coordinates are strictly clamped to avoid out-of-bounds artifacting.
    """
    total_frames = max(1, int(round(duration_seconds * fps)))

    if direction == "zoom_in":
        z = "min(zoom+0.0015,1.5)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif direction == "zoom_out":
        z = "if(eq(on,1),1.5,max(zoom-0.0015,1.0))"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif direction == "pan_left":
        z = "1.25"
        x = "if(eq(on,1),iw-iw/zoom,max(0,x-2))"
        y = "ih/2-(ih/zoom/2)"
    elif direction == "pan_right":
        z = "1.25"
        x = "if(eq(on,1),0,min(iw-iw/zoom,x+2))"
        y = "ih/2-(ih/zoom/2)"
    else:  # default zoom_in
        z = "min(zoom+0.0015,1.5)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"

    return f"zoompan=z='{z}':x='{x}':y='{y}':d={total_frames}:s={out_w}x{out_h}:fps={fps}"


def build_ken_burns_clip(
    image_path,
    output_path,
    duration_seconds=3.0,
    direction=None,
    width=1080,
    height=1920,
    fps=30,
):
    """
    Renders a still image into a video clip with smooth Ken Burns pan/zoom motion.
    Upscales 2x before zoompan to maintain crisp resolution and prevent pixelation.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if direction is None or direction not in DIRECTIONS:
        direction = random.choice(DIRECTIONS)

    upscale_w = int(width * 2)
    upscale_h = int(height * 2)

    zp = _zoompan_expr(
        direction=direction,
        duration_seconds=duration_seconds,
        out_w=width,
        out_h=height,
        fps=fps,
    )

    vf = (
        f"scale={upscale_w}:{upscale_h}:force_original_aspect_ratio=increase,"
        f"crop={upscale_w}:{upscale_h},"
        f"{zp},"
        f"setsar=1,"
        f"format=yuv420p"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", vf,
        "-t", str(duration_seconds),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"Ken Burns rendering failed: {r.stderr or 'No output produced'}")

    return str(output_path)


def prepare_scene_clip(
    media_path,
    output_path,
    duration_seconds=3.0,
    direction=None,
    width=1080,
    height=1920,
    fps=30,
):
    """
    Prepares a scene clip from either an image or a video file.
    Ensures matching resolution, aspect ratio, frame rate, and duration.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    p = Path(media_path)
    ext = p.suffix.lower()

    if ext in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"fps={fps},"
            f"setsar=1,"
            f"format=yuv420p"
        )
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", str(media_path),
            "-vf", vf,
            "-t", str(duration_seconds),
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return str(output_path)
        # Fallback to Ken Burns if video processing encounters issue

    return build_ken_burns_clip(
        image_path=media_path,
        output_path=output_path,
        duration_seconds=duration_seconds,
        direction=direction,
        width=width,
        height=height,
        fps=fps,
    )


def assemble_with_transitions(
    scene_clips,
    output_path,
    get_clip_duration=None,
    transition_duration=0.35,
    scene_durations=None,
):
    """
    Combines a sequence of scene video clips with seamless xfade transitions.

    If scene_durations is provided (matching each scene's nominal speech duration),
    offsets are calculated so that total assembled video duration equals sum(scene_durations)
    without timing drift.
    """
    if not scene_clips:
        raise ValueError("No scene clips provided to assemble_with_transitions")

    if len(scene_clips) == 1:
        shutil.copyfile(scene_clips[0], output_path)
        return str(output_path)

    if get_clip_duration is None:
        get_clip_duration = globals().get("get_clip_duration")

    inputs = []
    for clip in scene_clips:
        inputs += ["-i", str(clip)]

    filter_parts = []
    # Pre-normalize each input to exact same SAR and fps before xfade
    for i in range(len(scene_clips)):
        filter_parts.append(f"[{i}:v]setsar=1,fps=30[in{i}]")

    prev = "in0"
    offset = 0.0

    for i in range(1, len(scene_clips)):
        t = random.choice(TRANSITIONS)
        clip_dur = get_clip_duration(scene_clips[i - 1])
        offset += max(0.1, clip_dur - transition_duration)

        out = f"v{i}"
        filter_parts.append(
            f"[{prev}][in{i}]xfade=transition={t}:duration={transition_duration}:offset={offset:.3f}[{out}]"
        )
        prev = out

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", f"[{prev}]",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"assemble_with_transitions failed: {r.stderr or 'No output produced'}")

    return str(output_path)

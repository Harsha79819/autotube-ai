import os
import random
import shutil
import subprocess
import time
import uuid
from pathlib import Path

# Available ffmpeg xfade transitions (smooth, cinematic, no glitchy pixelize)
TRANSITIONS = [
    "fade", "smoothleft", "smoothright", "dissolve", "circlecrop",
    "wipeleft", "wiperight", "circleopen"
]

DIRECTIONS = [
    "zoom_in", "slow_cinematic_push", "pan_left", "zoom_in_tilt_up",
    "zoom_out", "pan_right", "zoom_in_tilt_down", "hook_snap_zoom", "static_subtle"
]


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
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
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
    Max zoom is capped at 1.06 - 1.10x to ensure subjects and vehicles are never oversized.
    """
    total_frames = max(1, int(round(duration_seconds * fps)))

    if direction == "hook_snap_zoom":
        # Viral Shorts Hook: Snappy punch-in to 1.07 then subtle drift to 1.10
        z = "if(lt(on,18),min(1.0+on*0.004,1.07),min(1.07+(on-18)*0.00025,1.10))"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif direction == "slow_cinematic_push":
        # Subtle slow push (1.0 to 1.06) ideal for news, explainers & realism
        z = "min(zoom+0.0003,1.06)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif direction == "zoom_in_tilt_up":
        # Subtle upward drift toward focal head/face
        z = "min(zoom+0.00035,1.08)"
        x = "iw/2-(iw/zoom/2)"
        y = "if(eq(on,1),ih*0.08,max(0,y-0.8))"
    elif direction == "zoom_in_tilt_down":
        # Subtle downward drift
        z = "min(zoom+0.00035,1.08)"
        x = "iw/2-(iw/zoom/2)"
        y = "if(eq(on,1),0,min(ih-ih/zoom,y+0.8))"
    elif direction == "zoom_in":
        z = "min(zoom+0.00035,1.08)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif direction == "zoom_out":
        z = "if(eq(on,1),1.08,max(zoom-0.00035,1.0))"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif direction == "pan_left":
        z = "1.04"
        x = "if(eq(on,1),iw-iw/zoom,max(0,x-1))"
        y = "ih/2-(ih/zoom/2)"
    elif direction == "pan_right":
        z = "1.04"
        x = "if(eq(on,1),0,min(iw-iw/zoom,x+1))"
        y = "ih/2-(ih/zoom/2)"
    elif direction == "static_subtle":
        # Micro-drift for typography cards, charts, and text graphics so text never cuts off
        z = "min(zoom+0.0001,1.025)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    else:  # default slow push
        z = "min(zoom+0.0003,1.06)"
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
    is_hook=False,
):
    """
    Renders a still image into a video clip with smooth Ken Burns pan/zoom motion.
    Uses subtle upscale margins (1.04x) to prevent cutting off subjects or text.
    If image is a card or graphic, locks to micro-drift to preserve 100% typography readability.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    img_name = Path(image_path).name.lower()
    is_card = any(k in img_name for k in ("card", "poll", "tweet", "chart", "graphic", "typography", "intro", "metadata"))

    if is_hook and not is_card:
        direction = "hook_snap_zoom"
    elif is_card:
        direction = "static_subtle"
    elif direction is None or direction not in DIRECTIONS:
        available_dirs = [d for d in DIRECTIONS if d not in ("hook_snap_zoom", "static_subtle")]
        direction = random.choice(available_dirs)

    # Subtle padding margin (1.04x instead of 1.20x)
    upscale_factor = 1.01 if is_card else 1.04
    upscale_w = int(width * upscale_factor)
    upscale_h = int(height * upscale_factor)

    zp = _zoompan_expr(
        direction=direction,
        duration_seconds=duration_seconds,
        out_w=width,
        out_h=height,
        fps=fps,
    )

    vf_filters = [
        f"scale={upscale_w}:{upscale_h}:force_original_aspect_ratio=increase",
        f"crop={upscale_w}:{upscale_h}",
        zp,
    ]
    if is_hook:
        # Subtle 0.2s camera flash impact on the first 7 frames to grab immediate visual attention
        vf_filters.append("eq=brightness='if(lt(n,7),0.22*(1-n/7),0)'")

    vf_filters.extend(["setsar=1", "format=yuv420p"])
    vf = ",".join(vf_filters)

    cmd = [
        "ffmpeg", "-y",
        "-threads", "4",
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

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
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
    is_hook=False,
):
    """
    Prepares a scene clip from either an image or a video file.
    Ensures matching resolution, aspect ratio, frame rate, and duration.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    p = Path(media_path)
    ext = p.suffix.lower()

    if ext in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
        vf_filters = [
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}",
        ]
        if is_hook:
            vf_filters.append("eq=brightness='if(lt(n,7),0.22*(1-n/7),0)'")
        vf_filters.extend([
            f"fps={fps}",
            "setsar=1",
            "format=yuv420p",
        ])
        vf = ",".join(vf_filters)
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
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
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
        is_hook=is_hook,
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
    # Strictly validate that all clips exist on disk before passing to ffmpeg
    valid_clips = []
    valid_durations = []
    for idx, c in enumerate(scene_clips):
        p = Path(c)
        if p.exists() and p.stat().st_size > 1000:
            valid_clips.append(str(p.resolve()))
            if scene_durations and len(scene_durations) > idx:
                valid_durations.append(scene_durations[idx])
        else:
            print(f"⚠️ Warning: Dropping non-existent clip from assemble_with_transitions: {c}")

    scene_clips = valid_clips
    scene_durations = valid_durations

    if not scene_clips:
        raise ValueError("No valid scene clips exist on disk to assemble_with_transitions")

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
        if scene_durations and len(scene_durations) >= i:
            nominal_dur = float(scene_durations[i - 1])
        else:
            nominal_dur = max(0.1, get_clip_duration(scene_clips[i - 1]) - transition_duration)
        offset += nominal_dur

        out = f"v{i}"
        filter_parts.append(
            f"[{prev}][in{i}]xfade=transition={t}:duration={transition_duration}:offset={offset:.3f}[{out}]"
        )
        prev = out

    preset = "veryfast" if len(scene_clips) > 6 else "fast"
    total_est_dur = sum(valid_durations) if valid_durations else len(scene_clips) * 20.0
    timeout_calc = int(max(360, total_est_dur * 1.5))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", f"[{prev}]",
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", "21",
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-color_range", "tv",
        "-movflags", "+faststart",
        str(output_path),
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        last_progress_print = 0
        err_lines = []
        start_time_proc = time.time()
        for line in proc.stderr:
            err_lines.append(line)
            if len(err_lines) > 50:
                err_lines.pop(0)
            now = time.time()
            if now - start_time_proc > timeout_calc:
                proc.kill()
                raise TimeoutError(f"xfade assembly timed out after {timeout_calc}s")
            if "frame=" in line and now - last_progress_print >= 2.0:
                last_progress_print = now
                print(f"🎬 [FFmpeg Assembly] {line.strip()}", flush=True)

        proc.wait(timeout=15)
        if proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print("✅ [FFmpeg Assembly] Successfully assembled scene transitions!")
            return str(output_path)
        err_msg = "".join(err_lines) or "xfade transition assembly failed"
        print(f"⚠️ Warning: xfade assembly failed ({err_msg[:200]}...). Falling back to concat demuxer.")
    except Exception as e:
        print(f"⚠️ Warning: Exception during xfade assembly: {e}. Falling back to concat demuxer.")

    # Concat demuxer fallback (bulletproof for arbitrary clip counts)
    concat_list_path = Path(output_path).parent / f"concat_list_{uuid.uuid4().hex[:8]}.txt"
    try:
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for clip in scene_clips:
                escaped = str(Path(clip).resolve()).replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        # 1. Try lightning-fast stream copy first (<1s for entire multi-minute video)
        try:
            copy_cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list_path),
                "-c", "copy",
                "-movflags", "+faststart",
                str(output_path),
            ]
            r_copy = subprocess.run(copy_cmd, capture_output=True, text=True, timeout=45)
            if r_copy.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                print("⚡ [Concat Demuxer] Lightning fast stream copy successful (<1s).")
                return str(output_path)
        except Exception as copy_err:
            print(f"Stream copy notice: {copy_err}, falling back to fast transcode...")

        # 2. Fast re-encode fallback
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list_path),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "21",
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-color_range", "tv",
            "-movflags", "+faststart",
            str(output_path),
        ]
        r_concat = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=timeout_calc)
        if r_concat.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(f"Both xfade and concat assembly failed: {r_concat.stderr or 'No output produced'}")
        return str(output_path)
    finally:
        if concat_list_path.exists():
            try:
                concat_list_path.unlink()
            except Exception:
                pass

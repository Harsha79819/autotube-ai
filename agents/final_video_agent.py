"""
AutoTube AI - Final Video Rendering Agent (agents/final_video_agent.py)

Combines video scenes, burns subtitles (libass or SRT), overlays Frame-0
viral hook cards for Shorts, and applies mobile-optimized MP4 encoding (+faststart).

Phase 1 Upgrades:
  1. Strict Outro Removal for Shorts (9:16): Eliminates the 2-second drop-off outro.
  2. Frame 0 Hook Text Overlay: Burns output/hook_overlay.png onto Frame 0 for the
     first ~2.0 seconds (t=0.0s to t=2.0s) so viewers immediately see the visual hook.
"""

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from supervisor import autonomous_recover

OUTPUT_DIR = Path("output")


@autonomous_recover("final_video_agent")
def create_final_video(
    add_captions=None,
    aspect_ratio="9:16",
    burn_captions=None,
    captions=None,
    include_outro=False,
    outro_clip=None,
    input_video=None,
    output_video=None,
):
    if burn_captions is not None:
        add_captions = burn_captions
    elif captions is not None:
        add_captions = captions
    elif add_captions is None:
        add_captions = True

    if input_video is None:
        input_video = "output/video.mp4"
    if output_video is None:
        output_video = "output/final_video.mp4"
    ass_subtitles = "output/subtitles.ass"
    srt_subtitles = "output/subtitles.srt"

    if not os.path.exists(input_video):
        print("Input video not found:", input_video)
        return None

    if os.path.exists(output_video):
        try:
            os.remove(output_video)
        except Exception:
            pass

    if aspect_ratio == "9:16":
        target_w, target_h = 1080, 1920
    elif aspect_ratio == "16:9":
        target_w, target_h = 1920, 1080
    else:
        target_w, target_h = 1080, 1080

    # --------------------------------------------------------
    # Universal Outro: Active for all video formats (9:16 Shorts & 16:9 Long-form)
    # --------------------------------------------------------
    is_shorts = (aspect_ratio == "9:16")

    # --------------------------------------------------------
    # Phase 1 Virality Upgrade: Frame 0 Viral Hook Text Overlay
    # --------------------------------------------------------
    hook_overlay_path = str(Path(output_video).parent / "hook_overlay.png")
    has_hook_overlay = False
    if is_shorts and add_captions:
        if not os.path.exists(hook_overlay_path):
            hook_txt = ""
            if os.path.exists("output/hook.json"):
                try:
                    import json
                    h_data = json.loads(Path("output/hook.json").read_text(encoding="utf-8"))
                    hook_txt = h_data.get("chosen_hook", "")
                except Exception:
                    pass
            if not hook_txt and os.path.exists("output/script.txt"):
                try:
                    s_lines = [
                        l.strip()
                        for l in Path("output/script.txt").read_text(encoding="utf-8").splitlines()
                        if l.strip() and not l.startswith("#")
                    ]
                    if s_lines:
                        hook_txt = s_lines[0]
                except Exception:
                    pass
            if not hook_txt:
                hook_txt = "Watch Till End! 🔥"
            try:
                from agents.hook_card import generate_hook_card
                generate_hook_card(hook_txt, output_path=hook_overlay_path, width=target_w, height=target_h)
            except Exception as e:
                print(f"⚠️ Hook card generation notice: {e}")

        has_hook_overlay = bool(
            os.path.exists(hook_overlay_path) and os.path.getsize(hook_overlay_path) > 500
        )

    print("=" * 60)
    print("FINAL VIDEO RENDERING")
    print("=" * 60)
    print("Input:                    ", input_video)
    print("Output:                   ", output_video)
    print(f"Target:                   {target_w}x{target_h} ({aspect_ratio})")
    print("Burn Captions:            ", add_captions)
    print("Frame 0 Hook Overlay:     ", "YES (t=0.0s to 2.0s)" if has_hook_overlay else "NO")
    print("Include Outro:            ", "YES" if include_outro else "NO (Omitted for Shorts retention)")

    # Check if input video has an audio stream
    probe_cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1",
        input_video
    ]
    p_res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=8)
    video_has_audio = bool(p_res.stdout.strip())
    audio_source = "output/mixed_audio.wav" if os.path.exists("output/mixed_audio.wav") else "output/voice.mp3"

    target_dir = Path(output_video).parent
    cand_poster = target_dir / "thumbnail_916_poster.png"
    if not cand_poster.exists():
        cand_poster = Path(input_video).parent / "thumbnail_916_poster.png"
    if not cand_poster.exists() and (target_dir.resolve() == OUTPUT_DIR.resolve() or target_dir == Path(".")):
        cand_poster = OUTPUT_DIR / "thumbnail_916_poster.png"
    poster_overlay_path = str(cand_poster)
    has_poster_overlay = bool(
        is_shorts and cand_poster.exists() and cand_poster.stat().st_size > 1000
    )

    # Fast copy optimization ONLY when NO captions, NO hook overlay, and NO poster overlay are needed
    if not add_captions and not has_hook_overlay and not has_poster_overlay and video_has_audio:
        if aspect_ratio == "9:16":
            print("⏩ 9:16 Vertical Export: Re-encoding stream for Instagram Reels compliance (+faststart, 44.1kHz)...")
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-i", input_video,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                    "-shortest", "-movflags", "+faststart",
                    output_video
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=90)
                return output_video
            except Exception:
                pass
        else:
            print("⏩ Burn Captions & Hook Overlay OFF: Copying stream with +faststart...")
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-i", input_video,
                    "-c", "copy", "-movflags", "+faststart",
                    output_video
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=60)
            except Exception:
                shutil.copyfile(input_video, output_video)
            return output_video

    # Build Filter Chain
    fonts_dir = os.path.abspath("fonts").replace("\\", "/")
    use_ass = False
    if add_captions and os.path.exists(ass_subtitles) and os.path.getsize(ass_subtitles) > 50:
        use_ass = True

    # Assemble inputs and filter graph
    cmd = ["ffmpeg", "-y", "-i", input_video]
    overlay_input_idx = -1
    poster_input_idx = -1
    audio_input_idx = -1

    current_input_idx = 1
    if has_poster_overlay:
        cmd.extend(["-i", poster_overlay_path])
        poster_input_idx = current_input_idx
        current_input_idx += 1

    if has_hook_overlay:
        cmd.extend(["-i", hook_overlay_path])
        overlay_input_idx = current_input_idx
        current_input_idx += 1

    if not video_has_audio and os.path.exists(audio_source):
        cmd.extend(["-i", audio_source])
        audio_input_idx = current_input_idx
        current_input_idx += 1

    filter_steps = []
    # 1. Base scale + letterbox pad
    filter_steps.append(
        f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2[scaled]"
    )
    last_v = "scaled"

    # 1b. Poster overlay on Frame 0 for first 0.35s (Guarantees YouTube Shorts mobile auto-picker displays Prasad Tech cover)
    if has_poster_overlay:
        filter_steps.append(
            f"[{last_v}][{poster_input_idx}:v]overlay=0:0:enable='between(t,0,0.35)'[v_poster]"
        )
        last_v = "v_poster"

    # 2. Hook overlay banner on Frame 0 for first 2.0s
    if has_hook_overlay:
        filter_steps.append(
            f"[{last_v}][{overlay_input_idx}:v]overlay=0:0:enable='between(t,0,2.0)'[v_hook]"
        )
        last_v = "v_hook"

    # 3. Captions
    if add_captions:
        if use_ass:
            sub_p = os.path.abspath(ass_subtitles).replace("\\", "/").replace(":", "\\:")
            filter_steps.append(f"[{last_v}]ass={sub_p}:fontsdir={fonts_dir}[v_out]")
            last_v = "v_out"
            print("Subtitle file: output/subtitles.ass (Karaoke Highlight)")
        elif os.path.exists(srt_subtitles):
            sub_p = os.path.abspath(srt_subtitles).replace("\\", "/").replace(":", "\\:")
            srt_content = ""
            try:
                with open(srt_subtitles, "r", encoding="utf-8") as sf:
                    srt_content = sf.read()
            except Exception:
                pass
            is_telugu = bool(re.search(r"[\u0C00-\u0C7F]", srt_content))
            is_hindi = bool(re.search(r"[\u0900-\u097F]", srt_content))
            font_family = "Kohinoor Telugu" if is_telugu else ("Kohinoor Devanagari" if is_hindi else "Helvetica")

            if aspect_ratio == "9:16":
                style = (
                    f"force_style='FontName={font_family},FontSize=42,Bold=1,"
                    "PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,"
                    "BorderStyle=1,Outline=3.5,Shadow=1.5,Alignment=2,"
                    "MarginV=240,MarginR=50,MarginL=50'"
                )
            elif aspect_ratio == "16:9":
                style = (
                    f"force_style='FontName={font_family},FontSize=22,Bold=1,"
                    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                    "BorderStyle=1,Outline=2.5,Shadow=1.5,Alignment=2,"
                    "MarginV=40,MarginR=50,MarginL=50'"
                )
            else:
                style = (
                    f"force_style='FontName={font_family},FontSize=20,Bold=1,"
                    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                    "BorderStyle=1,Outline=2.5,Shadow=1.5,Alignment=2,"
                    "MarginV=35,MarginR=35,MarginL=35'"
                )
            filter_steps.append(f"[{last_v}]subtitles={sub_p}:fontsdir={fonts_dir}:{style}[v_out]")
            last_v = "v_out"
            print("Subtitle file: output/subtitles.srt (Standard)")

    filter_complex_str = ";".join(filter_steps)
    cmd.extend(["-filter_complex", filter_complex_str])
    cmd.extend(["-map", f"[{last_v}]"])

    if video_has_audio:
        cmd.extend(["-map", "0:a:0"])
    elif audio_input_idx > 0:
        print(f"🎵 Guaranteeing audio track: Attaching narration audio from input {audio_input_idx}...")
        cmd.extend(["-map", f"{audio_input_idx}:a:0"])

    audio_sample_rate = "44100" if aspect_ratio == "9:16" else "48000"

    # For 9:16 Shorts, strictly cap duration to exact audio length (+0.20s pad) to prevent dead-air outro
    if is_shorts:
        try:
            a_probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_source],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5
            )
            a_dur = float(a_probe.stdout.strip())
            if a_dur > 0:
                cmd.extend(["-t", f"{a_dur + 0.20:.2f}"])
        except Exception:
            pass

    cmd.extend([
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-color_range", "tv",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", audio_sample_rate,
        "-ac", "2",
        "-shortest",
        "-movflags", "+faststart",
        output_video,
    ])

    print()
    print("Running FFmpeg Final Assembly...")
    print()

    # Adaptive timeout based on input video duration
    in_dur = 60.0
    try:
        dur_probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", input_video
        ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=8)
        raw_dur = (dur_probe.stdout or "").strip()
        if raw_dur:
            in_dur = float(raw_dur)
    except Exception:
        in_dur = 60.0
    final_timeout = int(max(420, in_dur * 2.5))

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        last_log = 0
        out_lines = []
        st_proc = time.time()
        for line in proc.stdout:
            out_lines.append(line)
            if len(out_lines) > 50:
                out_lines.pop(0)
            now = time.time()
            if now - st_proc > final_timeout:
                proc.kill()
                raise TimeoutError(f"Final assembly timed out after {final_timeout}s")
            if "frame=" in line and now - last_log >= 2.5:
                last_log = now
                print(f"🎬 [Final Assembly Progress] {line.strip()}", flush=True)

        proc.wait(timeout=15)
        if proc.returncode == 0 and os.path.exists(output_video) and os.path.getsize(output_video) > 1000:
            if include_outro and not is_shorts:
                from agents.video_agent import append_outro
                outro_path = outro_clip or "assets/outro/like_subscribe_share_comment.mp4"
                if not os.path.exists(outro_path):
                    outro_path = "assets/outro/like_share_subscribe.mp4"
                print("🎬 Appending 5-second Like, Subscribe, Share & Comment outro...")
                append_outro(output_video, outro_clip_path=outro_path, output_path=output_video)
            elif is_shorts and include_outro:
                print("ℹ️ Shorts (9:16) strict retention: Outro omitted to maximize audience completion and loops.")

            print("=" * 60)
            print("FINAL VIDEO CREATED!")
            print(f"{target_w}x{target_h} ({aspect_ratio})")
            print(output_video)
            print("=" * 60)
            return output_video
        else:
            err_snip = "".join(out_lines)
            print(f"⚠️ FFmpeg final assembly notice: {err_snip[:200]}. Trying clean fallback...")
    except Exception as render_err:
        print(f"⚠️ FFmpeg final assembly exception: {render_err}. Trying clean fallback...")

    if os.path.exists(input_video):
        print(f"⚡ [Safety Fallback] Promoting {input_video} directly to {output_video}...")
        shutil.copyfile(input_video, output_video)
        return output_video

    raise RuntimeError(
        f"FFmpeg encoding failed with exit code {result.returncode}: {result.stdout[-300:] if result.stdout else 'unknown error'}"
    )

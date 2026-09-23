import os
import re
import shutil
import subprocess
from supervisor import autonomous_recover


@autonomous_recover("final_video_agent")
def create_final_video(add_captions=False, aspect_ratio="1:1", burn_captions=None, captions=None, include_outro=False, outro_clip=None):
    if burn_captions is not None:
        add_captions = burn_captions
    elif captions is not None:
        add_captions = captions

    input_video = "output/video.mp4"
    subtitles = "output/subtitles.srt"
    output_video = "output/final_video.mp4"

    ass_subtitles = "output/subtitles.ass"
    srt_subtitles = "output/subtitles.srt"

    if not os.path.exists(input_video):
        print("Input video not found:", input_video)
        return None

    if add_captions and not os.path.exists(srt_subtitles) and not os.path.exists(ass_subtitles):
        print("⚠️ Subtitle file not found. Falling back to clean video without burned subtitles.")
        add_captions = False

    if os.path.exists(output_video):
        os.remove(output_video)

    if aspect_ratio == "9:16":
        target_w, target_h = 1080, 1920
    elif aspect_ratio == "16:9":
        target_w, target_h = 1920, 1080
    else:
        target_w, target_h = 1080, 1080

    print("=" * 60)
    print("FINAL VIDEO RENDERING")
    print("=" * 60)
    print("Input:", input_video)
    print("Output:", output_video)
    print(f"Target: {target_w}x{target_h} ({aspect_ratio})")
    print("Burn Captions into Video:", add_captions)

    # Check if input video has an audio stream
    probe_cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1",
        input_video
    ]
    p_res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    video_has_audio = bool(p_res.stdout.strip())
    audio_source = "output/mixed_audio.wav" if os.path.exists("output/mixed_audio.wav") else "output/voice.mp3"

    # Optimization: When burn_captions is OFF, skip re-encoding if video already has audio!
    if not add_captions and video_has_audio:
        print("⏩ Burn Captions is OFF: Video already has audio and smart canvas. Copying directly (instant processing)!")
        import shutil
        shutil.copyfile(input_video, output_video)
        if include_outro:
            from agents.video_agent import append_outro
            outro_path = outro_clip or "assets/outro/like_share_subscribe.mp4"
            print("🎬 Appending Like/Share/Subscribe outro...")
            append_outro(output_video, outro_clip_path=outro_path, output_path=output_video)
        print("=" * 60)
        print("FINAL VIDEO CREATED (INSTANT CLEAN VIDEO)!")
        print(f"{target_w}x{target_h} ({aspect_ratio})")
        print(output_video)
        print("=" * 60)
        return output_video

    # --------------------------------------------------------
    # FFmpeg filter
    # Preserve original aspect ratio.
    # --------------------------------------------------------

    video_filter = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2"
    )

    if add_captions:
        fonts_dir = os.path.abspath("fonts").replace("\\", "/")
        if os.path.exists(ass_subtitles) and os.path.getsize(ass_subtitles) > 50:
            subtitle_path = os.path.abspath(ass_subtitles).replace("\\", "/").replace(":", "\\:")
            video_filter = (
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,"
                f"ass={subtitle_path}:fontsdir={fonts_dir}"
            )
            print("Subtitle file: output/subtitles.ass (Word-Level Karaoke Highlight via libass)")
        else:
            subtitle_path = os.path.abspath(srt_subtitles).replace("\\", "/").replace(":", "\\:")
            srt_content = ""
            try:
                if os.path.exists(srt_subtitles):
                    with open(srt_subtitles, "r", encoding="utf-8") as sf:
                        srt_content = sf.read()
            except Exception:
                pass
            is_telugu = bool(re.search(r"[\u0C00-\u0C7F]", srt_content))
            is_hindi = bool(re.search(r"[\u0900-\u097F]", srt_content))
            font_family = "Kohinoor Telugu" if is_telugu else ("Kohinoor Devanagari" if is_hindi else "Helvetica")

            if aspect_ratio == "9:16":
                style = (
                    f"force_style='FontName={font_family},FontSize=24,Bold=1,"
                    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                    "BorderStyle=1,Outline=2.5,Shadow=1.5,Alignment=2,"
                    "MarginV=150,MarginR=80,MarginL=80'"
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

            video_filter = (
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,"
                f"subtitles={subtitle_path}:fontsdir={fonts_dir}:{style}"
            )
            print("Subtitle file: output/subtitles.srt (Standard)")

    print("Video filter:")
    print(video_filter)

    # Ensure input video audio is preserved or attached from voice.mp3
    probe_cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1",
        input_video
    ]
    p_res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    video_has_audio = bool(p_res.stdout.strip())

    audio_source = "output/mixed_audio.wav" if os.path.exists("output/mixed_audio.wav") else "output/voice.mp3"

    command = [
        "ffmpeg",
        "-y",
        "-i",
        input_video,
    ]

    if not video_has_audio and os.path.exists(audio_source):
        print(f"🎵 Guaranteeing audio track: Attaching narration audio from {audio_source}...")
        command.extend(["-i", audio_source])
        command.extend([
            "-vf", video_filter,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            output_video,
        ])
    else:
        command.extend([
            "-vf", video_filter,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            output_video,
        ])

    print()
    print("Running FFmpeg...")
    print()

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    print(result.stdout)

    if result.returncode == 0 and os.path.exists(output_video):
        if include_outro:
            from agents.video_agent import append_outro
            outro_path = outro_clip or "assets/outro/like_share_subscribe.mp4"
            print("🎬 Appending Like/Share/Subscribe outro...")
            append_outro(output_video, outro_clip_path=outro_path, output_path=output_video)

        print("=" * 60)
        print("FINAL VIDEO CREATED!")
        print(f"{target_w}x{target_h} ({aspect_ratio})")
        print(output_video)
        print("=" * 60)

        return output_video

    print("=" * 60)
    print("FFmpeg failed with subtitles. Falling back to clean video without burned subtitles...")
    print("=" * 60)

    if os.path.exists(input_video):
        shutil.copyfile(input_video, output_video)
        print(f"✅ Generated fallback video from {input_video} -> {output_video}")
        return output_video

    raise RuntimeError(f"FFmpeg encoding failed with exit code {result.returncode}: {result.stdout[-300:] if result.stdout else 'unknown error'}")



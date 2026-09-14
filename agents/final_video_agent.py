import os
import subprocess
from supervisor import autonomous_recover


@autonomous_recover("final_video_agent")
def create_final_video(add_captions=True, aspect_ratio="1:1"):
    input_video = "output/video.mp4"
    subtitles = "output/subtitles.srt"
    output_video = "output/final_video.mp4"

    if not os.path.exists(input_video):
        print("Input video not found:", input_video)
        return None

    if add_captions and not os.path.exists(subtitles):
        print("Subtitle file not found:", subtitles)
        return None

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
    print("Captions:", add_captions)

    # --------------------------------------------------------
    # FFmpeg filter
    # Preserve original aspect ratio.
    # --------------------------------------------------------

    video_filter = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2"
    )

    if add_captions:
        subtitle_path = subtitles.replace("\\", "/")
        subtitle_path = subtitle_path.replace(":", "\\:")

        if aspect_ratio == "9:16":
            # Safe zone for vertical shorts: avoid bottom 260px (channel UI) and right 160px (action buttons)
            style = (
                "force_style='FontName=Helvetica,FontSize=24,Bold=1,"
                "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                "BorderStyle=1,Outline=2.5,Shadow=1.5,Alignment=2,"
                "MarginV=260,MarginR=160,MarginL=80'"
            )
        elif aspect_ratio == "16:9":
            style = (
                "force_style='FontName=Helvetica,FontSize=22,Bold=1,"
                "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                "BorderStyle=1,Outline=2.5,Shadow=1.5,Alignment=2,"
                "MarginV=55,MarginR=60,MarginL=60'"
            )
        else:
            style = (
                "force_style='FontName=Helvetica,FontSize=20,Bold=1,"
                "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                "BorderStyle=1,Outline=2.5,Shadow=1.5,Alignment=2,"
                "MarginV=45,MarginR=40,MarginL=40'"
            )

        video_filter = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,"
            f"subtitles={subtitle_path}:{style}"
        )

        print("Subtitle file:", subtitles)

    print("Video filter:")
    print(video_filter)

    command = [
        "ffmpeg",
        "-y",
        "-i",
        input_video,
        "-vf",
        video_filter,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        output_video,
    ]

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
        print("=" * 60)
        print("FINAL VIDEO CREATED!")
        print(f"{target_w}x{target_h} ({aspect_ratio})")
        print(output_video)
        print("=" * 60)

        return output_video

    print("=" * 60)
    print("FFmpeg failed.")
    print("=" * 60)

    raise RuntimeError(f"FFmpeg encoding failed with exit code {result.returncode}: {result.stdout[-300:] if result.stdout else 'unknown error'}")


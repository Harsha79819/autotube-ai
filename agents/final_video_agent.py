import os
import subprocess


def create_final_video(add_captions=True):
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

    print("=" * 60)
    print("FINAL VIDEO RENDERING")
    print("=" * 60)
    print("Input:", input_video)
    print("Output:", output_video)
    print("Target: 1080x1080")
    print("Captions:", add_captions)

    # --------------------------------------------------------
    # FFmpeg filter
    # Preserve original aspect ratio.
    # --------------------------------------------------------

    video_filter = (
        "scale=1080:1080:force_original_aspect_ratio=decrease:flags=lanczos,"
        "pad=1080:1080:(ow-iw)/2:(oh-ih)/2"
    )

    if add_captions:
        subtitle_path = subtitles.replace("\\", "/")
        subtitle_path = subtitle_path.replace(":", "\\:")

        video_filter = (
            "scale=1080:1080:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=1080:1080:(ow-iw)/2:(oh-ih)/2,"
            f"subtitles={subtitle_path}"
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
        "medium",
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
        print("1080x1080")
        print(output_video)
        print("=" * 60)

        return output_video

    print("=" * 60)
    print("FFmpeg failed.")
    print("=" * 60)

    return None

import os
import subprocess


def create_final_video():
    input_video = "output/video.mp4"
    subtitles = "output/subtitles.srt"
    output_video = "output/final_video.mp4"

    # Delete old final video if it exists
    if os.path.exists(output_video):
        os.remove(output_video)

    result = subprocess.run([
        "ffmpeg",
        "-y",
        "-i", input_video,
        "-vf", f"subtitles={subtitles}",
        "-c:v", "libx264",
        "-c:a", "copy",
        output_video
    ])

    if result.returncode == 0:
        print("Final video created!")
        return output_video
    else:
        print("FFmpeg failed.")
        return None
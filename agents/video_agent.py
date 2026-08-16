import glob
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips


def create_video():

    print("Creating Video with Fresh Images...")

    images = sorted(
        glob.glob("assets/*.jpg")
        + glob.glob("assets/*.jpeg")
        + glob.glob("assets/*.png")
    )

    if not images:
        raise Exception("No images found in assets folder.")

    print(f"Using {len(images)} images")

    audio = AudioFileClip("output/voice.mp3")

    # Divide audio equally between all images
    duration = audio.duration / len(images)

    clips = []

    for index, img in enumerate(images, start=1):

        print(f"Adding image {index}/{len(images)}")

        clip = (
            ImageClip(img)
            .resized(width=640)
            .with_duration(duration)
        )

        clips.append(clip)

    video = concatenate_videoclips(
        clips,
        method="compose"
    )

    video = video.with_audio(audio)

    video.write_videofile(
        "output/video.mp4",
        fps=10,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=1
    )

    audio.close()

    print("Video Created Successfully!")


if __name__ == "__main__":
    create_video()
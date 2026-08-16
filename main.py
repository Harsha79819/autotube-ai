
from agents.news_agent import get_news
from agents.script_agent import generate_script
from agents.voice_agent import create_voice
from agents.image_agent import download_images
from agents.video_agent import create_video
from agents.metadata_agent import generate_metadata
from agents.youtube_agent import upload_video, load_uploaded_videos

import asyncio
import subprocess
import os
import json
import sys

print("=" * 50)
print("AutoTube AI Started")
print("=" * 50)

os.makedirs("output", exist_ok=True)

# ============================================================
# 1. GET FRESH NEWS
# ============================================================

print("Getting fresh news...")

topic = get_news()

print("News Topic:", topic)

# ============================================================
# 2. GENERATE SCRIPT
# ============================================================

print("Generating Script...")

script = generate_script(topic)

with open("output/script.txt", "w", encoding="utf-8") as f:
    f.write(script)

print("Script Saved")

# ============================================================
# 3. CREATE VOICE
# ============================================================

print("Creating Voice...")

asyncio.run(create_voice())

print("Voice Created")

# ============================================================
# 4. DOWNLOAD FRESH IMAGES
# ============================================================

print("Downloading Fresh Images...")

download_images(topic)

print("Images Downloaded")

# ============================================================
# 5. CREATE VIDEO
# ============================================================

print("Creating Video...")

create_video()

print("Video Created")

# ============================================================
# 6. CREATE SUBTITLES
# ============================================================

print("Creating Subtitles...")

subprocess.run(
    [sys.executable, "agents/subtitle_agent.py"],
    check=True
)

print("Subtitles Created")

# ============================================================
# 7. ADD SUBTITLES
# ============================================================

print("Adding Subtitles...")

subprocess.run(
    [sys.executable, "agents/final_video_agent.py"],
    check=True
)

print("Final Video Created")

# ============================================================
# 8. GENERATE YOUTUBE METADATA
# ============================================================

print("Generating YouTube Metadata...")

title, description, tags = generate_metadata(
    topic,
    script
)

print("=" * 50)
print("TITLE:")
print(title)

print("\nDESCRIPTION:")
print(description)

print("\nTAGS:")
print(tags)

print("=" * 50)

# ============================================================
# 9. CHECK DUPLICATE VIDEO
# ============================================================

print("Checking upload history...")

uploaded_videos = load_uploaded_videos()

if title in uploaded_videos:

    existing_video_id = uploaded_videos[title]

    print("=" * 50)
    print("VIDEO ALREADY UPLOADED")
    print("Existing Video ID:", existing_video_id)
    print("Skipping YouTube upload.")
    print("=" * 50)

else:

    # ========================================================
    # 10. UPLOAD TO YOUTUBE
    # ========================================================

    print("Uploading to YouTube...")

    video_id = upload_video(
        video_file="output/final_video.mp4",
        title=title,
        description=description,
        tags=tags,
        privacy="private"
    )

    print("=" * 50)
    print("YouTube Upload Successful")
    print("Video ID:", video_id)
    print("=" * 50)

# ============================================================
# FINISHED
# ============================================================

print("=" * 50)
print("AutoTube AI Finished")
print("=" * 50)
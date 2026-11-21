"""
Generate 16:9 Swetha Naidu Bigg Boss Exit Comedy Roast Video.
Runs pipeline with verified authentic reference assets and full-bleed 16:9 visuals.
"""
import sys
import os
from pathlib import Path

# Set root
root_dir = Path(__file__).resolve().parent.parent
os.chdir(root_dir)
sys.path.insert(0, str(root_dir))

from pipeline import generate_multi_media_video

def main():
    topic = "Bigg Boss Telugu 10 Swetha Naidu Viral Exit Roast"
    print(f"🎬 Starting 16:9 generation for: '{topic}'...")

    result = generate_multi_media_video(
        topic=topic,
        content_type="Entertainment",
        language_style="Telugu - తెలుగు (Creator / Casual)",
        voice="te-IN-ShrutiNeural",
        captions=True,
        aspect_ratio="16:9",
        target_duration="60-90s",
        include_outro=True,
        generation_mode="social_first",
        tone="roast",
        youtube_upload=False,
        youtube_channel="Channel 2 (Secondary)",
    )

    print("\n" + "="*60)
    print("PIPELINE RESULT:")
    print("="*60)
    print(f"Status: {result.get('status')}")
    print(f"Video File: {result.get('video')}")
    print(f"Run Dir: {result.get('run_dir')}")
    print(f"Run ID: {result.get('run_id')}")

if __name__ == "__main__":
    main()

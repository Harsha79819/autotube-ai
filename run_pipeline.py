#!/usr/bin/env python3
"""
AutoTube AI - CLI Pipeline Runner (run_pipeline.py)
Direct command-line interface to execute the full video generation pipeline.

Usage:
    python3 run_pipeline.py --topic "Review: DNK Movie" --voice "te-IN-MohanNeural"
    python3 run_pipeline.py --topic "Bigg Boss Telugu 10 Update" --content-type "Entertainment" --target-duration "60s"
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="AutoTube AI - CLI Video Generation Pipeline")
    parser.add_argument("--topic", "-t", required=True, help="Topic or title for video generation")
    parser.add_argument("--voice", "-v", default="te-IN-MohanNeural", help="Voice model (default: te-IN-MohanNeural)")
    parser.add_argument("--content-type", "-c", default=None, help="Content type (News, Entertainment, Movie Review, etc.)")
    parser.add_argument("--language-style", "-l", default="Telugu", help="Language style (default: Telugu)")
    parser.add_argument("--target-duration", "-d", default="30-50s", help="Target duration: 30-50s, 60s, etc.")
    parser.add_argument("--aspect-ratio", "-a", default="9:16", help="Aspect ratio (9:16 for Shorts/Reels, 16:9 for YouTube)")
    parser.add_argument("--upload", action="store_true", help="Auto-upload to YouTube if configured")
    parser.add_argument("--tone", default=None, help="Script tone (roast, dramatic, witty, informative)")

    args = parser.parse_args()

    topic = args.topic.strip()
    voice = args.voice
    language_style = args.language_style
    duration = args.target_duration
    aspect = args.aspect_ratio

    # Auto-detect content type if not explicitly passed
    content_type = args.content_type
    if not content_type:
        t_low = topic.lower()
        if any(w in t_low for w in ("review", "movie", "cinema", "film", "trailer", "teaser", "actor", "dnk", "bigg boss")):
            content_type = "Movie Review" if ("review" in t_low or "movie" in t_low or "film" in t_low) else "Entertainment"
        else:
            content_type = "News"

    print("=" * 60)
    print("🎬 AUTOTUBE AI - CLI PIPELINE EXECUTION")
    print(f"📌 Topic:          {topic}")
    print(f"📂 Content Type:   {content_type}")
    print(f"🗣️ Voice:          {voice}")
    print(f"🌐 Language Style: {language_style}")
    print(f"⏱️ Duration:       {duration}")
    print(f"📐 Aspect Ratio:   {aspect}")
    print("=" * 60)

    from pipeline import generate_multi_media_video

    result = generate_multi_media_video(
        topic=topic,
        content_type=content_type,
        language_style=language_style,
        voice=voice,
        tone=args.tone,
        captions=True,
        thumbnail=True,
        metadata=True,
        youtube_upload=args.upload,
        aspect_ratio=aspect,
        target_duration=duration,
        generation_mode="stock",
    )

    print()
    print("=" * 60)
    if result and result.get("video") and os.path.exists(result.get("video")):
        print(f"✅ VIDEO GENERATION SUCCESSFUL!")
        print(f"📹 Output Video: {result.get('video')}")
        if result.get("title"):
            print(f"🏷️ Title: {result.get('title')}")
    else:
        print("⚠️ Pipeline finished with warnings or quality gate hold.")
        print(f"Status: {(result or {}).get('status')}")
    print("=" * 60)


if __name__ == "__main__":
    main()

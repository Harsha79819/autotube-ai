#!/usr/bin/env python3
"""
Direct YouTube Publication Utility for AutoTube AI.
Uploads a completed video and thumbnail from a specific run to YouTube.

Usage:
    ./.venv/bin/python scripts/upload_pending_run.py
    ./.venv/bin/python scripts/upload_pending_run.py --run_id run_20261006_230923_Nagarjuna_s_Target_Practice_Wh
    ./.venv/bin/python scripts/upload_pending_run.py --channel "Channel 2 (Secondary)" --privacy public
"""

import sys
import os
import json
import argparse
from pathlib import Path

# Ensure root directory is on PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
os.chdir(ROOT_DIR)

from dashboard import perform_youtube_upload


def main():
    parser = argparse.ArgumentParser(description="Upload a pending or blocked run to YouTube.")
    parser.add_argument(
        "--run_id",
        type=str,
        default="run_20261006_230923_Nagarjuna_s_Target_Practice_Wh",
        help="Run ID directory name inside output/runs/",
    )
    parser.add_argument(
        "--channel",
        type=str,
        default=None,
        help="Target YouTube channel ('Channel 1 (Primary)' or 'Channel 2 (Secondary)')",
    )
    parser.add_argument(
        "--privacy",
        type=str,
        default=None,
        help="YouTube privacy status: public, unlisted, or private",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Validate assets and metadata without actual network upload",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow re-uploading even if video was previously published",
    )
    args = parser.parse_args()

    if args.force:
        os.environ["ALLOW_REUPLOAD"] = "true"

    run_dir = ROOT_DIR / "output" / "runs" / args.run_id
    if not run_dir.exists():
        # Try latest run
        runs_dir = ROOT_DIR / "output" / "runs"
        if runs_dir.exists():
            all_runs = sorted([d for d in runs_dir.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
            if all_runs:
                run_dir = all_runs[0]
                print(f"ℹ️ Run directory {args.run_id} not found. Using latest run: {run_dir.name}")
            else:
                print(f"❌ No runs found in {runs_dir}")
                sys.exit(1)
        else:
            print(f"❌ output/runs directory not found.")
            sys.exit(1)

    print("=" * 60)
    print(f"AutoTube AI — Uploading Run: {run_dir.name}")
    print("=" * 60)

    video_file = run_dir / "final_video.mp4"
    thumb_file = run_dir / "thumbnail.jpg"
    meta_file = run_dir / "metadata.json"

    if not video_file.exists() or video_file.stat().st_size == 0:
        print(f"❌ Video file missing or empty: {video_file}")
        sys.exit(1)

    if not thumb_file.exists() or thumb_file.stat().st_size == 0:
        print(f"⚠️ Thumbnail file missing: {thumb_file}. Looking for fallback...")
        alt_thumb = ROOT_DIR / "output" / "thumbnail.jpg"
        if alt_thumb.exists():
            thumb_file = alt_thumb
        else:
            print(f"❌ No valid thumbnail found.")
            sys.exit(1)

    mdata = {}
    if meta_file.exists():
        with open(meta_file, "r", encoding="utf-8") as mf:
            mdata = json.load(mf)

    title = mdata.get("title") or "AutoTube Video"
    desc = mdata.get("description", "")
    tags = mdata.get("tags", [])
    channel = args.channel or mdata.get("channel") or "Channel 2 (Secondary)"
    privacy = args.privacy or mdata.get("privacy") or "public"

    print(f"📹 Video File  : {video_file} ({video_file.stat().st_size / (1024*1024):.1f} MB)")
    print(f"🖼️ Thumbnail   : {thumb_file} ({thumb_file.stat().st_size / 1024:.1f} KB)")
    print(f"📝 Title       : {title}")
    print(f"📺 Channel     : {channel}")
    print(f"🔒 Privacy     : {privacy.upper()}")
    print(f"🏷️ Tags        : {len(tags)} tags")

    if args.dry_run:
        print("\n✅ Pre-upload validation passed (DRY RUN). Ready to upload.")
        return

    print("\n🚀 Starting YouTube upload...")
    video_id, yt_error = perform_youtube_upload(
        video_file=video_file,
        title=title,
        description=desc,
        tags=tags,
        privacy=privacy,
        channel=channel,
        thumbnail_path=thumb_file,
        run_dir=run_dir,
        run_id=run_dir.name,
    )

    if video_id:
        print("\n" + "=" * 60)
        print("🎉 PUBLICATION SUCCESSFUL!")
        print(f"   Video ID: {video_id}")
        print(f"   URL     : https://youtu.be/{video_id}")
        print("=" * 60)
    else:
        print(f"\n❌ Upload encountered an issue: {yt_error}")
        sys.exit(1)


if __name__ == "__main__":
    main()

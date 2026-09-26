"""
YouTube OAuth Re-authentication Utility for AutoTube AI.

Run this script directly whenever YouTube token has expired or revoked:
    ./.venv/bin/python scripts/reauth_youtube.py
"""

import os
import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

def reauth(channel=1):
    print("=" * 60)
    print(f"AutoTube AI — YouTube OAuth Re-authentication (Channel {channel})")
    print("=" * 60)

    is_ch2 = (channel == 2 or str(channel).lower() in ("2", "channel 2", "channel2", "secondary"))
    if is_ch2:
        token_path = Path("token_channel2.json")
        candidate_secrets = [
            Path("client_secret 2.json"),
            Path("client_secret_channel2.json"),
            Path("client_secret.json"),
            Path(__file__).parent.parent / "client_secret 2.json",
            Path(__file__).parent.parent / "client_secret.json",
        ]
    else:
        token_path = Path("token.json")
        candidate_secrets = [
            Path("client_secret.json"),
            Path("client_secret 2.json"),
            Path(__file__).parent.parent / "client_secret.json",
        ]

    secret_file = None
    for cand in candidate_secrets:
        if cand.exists():
            secret_file = cand
            break

    if not secret_file:
        print(f"❌ Error: Client secret file not found for Channel {channel}!")
        print("Please place client_secret.json or client_secret 2.json in the project root directory.")
        return False

    print(f"📺 Target Token: {token_path}")
    print(f"📄 Using credentials config: {secret_file}")

    # Remove expired or stale token
    if token_path.exists():
        try:
            token_path.unlink()
            print(f"🗑️ Removed expired {token_path}")
        except Exception as e:
            print(f"⚠️ Could not remove {token_path}: {e}")

    print()
    print("🌐 Launching browser for Google authentication...")
    print(f"👉 Please select your Google account for Channel {channel} and click 'Continue' / 'Allow'...")
    print()

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(secret_file),
            SCOPES,
        )
        creds = flow.run_local_server(port=0)

        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        print(f"✅ New {token_path} saved successfully!")

        # Verify access
        try:
            youtube = build("youtube", "v3", credentials=creds)
            channels = youtube.channels().list(part="snippet", mine=True).execute()
            items = channels.get("items", [])
            if items:
                title = items[0]["snippet"]["title"]
                print(f"🎉 Connected to YouTube Channel: '{title}'")
            else:
                print("✅ Authenticated successfully with YouTube!")
        except Exception as ver_err:
            print(f"⚠️ Channel check notice: {ver_err}")

        print("=" * 60)
        print(f"YouTube authentication complete for Channel {channel}! You can now publish videos.")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return False


if __name__ == "__main__":
    ch = 1
    if len(sys.argv) > 1:
        for i, arg in enumerate(sys.argv[1:], 1):
            if arg in ("--channel", "-c") and i < len(sys.argv) - 1:
                try:
                    ch = int(sys.argv[i + 1])
                except ValueError:
                    ch = sys.argv[i + 1]
            elif arg in ("1", "2"):
                ch = int(arg)
            elif "channel2" in arg.lower() or "channel-2" in arg.lower():
                ch = 2
    reauth(channel=ch)

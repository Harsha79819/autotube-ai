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

def reauth():
    print("=" * 60)
    print("AutoTube AI — YouTube OAuth Re-authentication")
    print("=" * 60)

    # Look for client_secret.json in current directory or project root
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
        print("❌ Error: 'client_secret.json' not found!")
        print("Please place client_secret.json in the project root directory.")
        return False

    print(f"📄 Using credentials config: {secret_file}")

    # Remove expired or stale token.json
    token_path = Path("token.json")
    if token_path.exists():
        try:
            token_path.unlink()
            print("🗑️ Removed expired token.json")
        except Exception as e:
            print(f"⚠️ Could not remove token.json: {e}")

    print()
    print("🌐 Launching browser for Google authentication...")
    print("👉 Please select your Google account and click 'Continue' / 'Allow'...")
    print()

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(secret_file),
            SCOPES,
        )
        creds = flow.run_local_server(port=0)

        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        print("✅ New token.json saved successfully!")

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
        print("YouTube authentication complete! You can now publish videos.")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return False


if __name__ == "__main__":
    reauth()

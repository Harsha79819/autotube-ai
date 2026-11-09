"""
AutoTube AI - GitHub Secrets Helper (scripts/print_github_secrets.py)
Prepares Base64-encoded credentials for zero-card GitHub Actions cloud execution.
"""

import os
import base64
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

def get_b64(filepath: Path) -> str:
    if filepath.exists():
        return base64.b64encode(filepath.read_bytes()).decode("utf-8")
    return ""

def main():
    print("=" * 70)
    print("🔐 AUTOTUBE AI — GITHUB REPOSITORY SECRETS HELPER")
    print("=" * 70)
    print("Go to your GitHub Repository -> Settings -> Secrets and variables -> Actions")
    print("Add the following Repository Secrets:")
    print("=" * 70)

    secrets = {
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
        "PEXELS_API_KEY": os.getenv("PEXELS_API_KEY", ""),
        "INSTAGRAM_ACCESS_TOKEN": os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
        "INSTAGRAM_USER_ID": os.getenv("INSTAGRAM_USER_ID", ""),
        "YOUTUBE_TOKEN_JSON_B64": get_b64(ROOT / "token.json"),
        "YOUTUBE_TOKEN_CH2_JSON_B64": get_b64(ROOT / "token_channel2.json"),
        "CLIENT_SECRET_JSON_B64": get_b64(ROOT / "client_secret.json"),
    }

    if "--export" in sys.argv:
        print("\n=== RAW SECRETS FOR GITHUB (COPY-PASTE) ===\n")
        for name, val in secrets.items():
            print(f"--- [ {name} ] ---")
            print(val)
            print()
        return

    for name, val in secrets.items():
        if val:
            display_val = val if len(val) <= 60 else f"{val[:25]}...{val[-15:]} (Length: {len(val)})"
            print(f"✅ {name:<28}: [CONFIGURED] {display_val}")
        else:
            print(f"⚠️ {name:<28}: [MISSING]")

    print("=" * 70)
    print("💡 To output raw values for easy copy-pasting into GitHub, run:")
    print("   .venv/bin/python scripts/print_github_secrets.py --export")
    print("=" * 70)

if __name__ == "__main__":
    main()

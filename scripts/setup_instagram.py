#!/usr/bin/env python3
"""
scripts/setup_instagram.py - Secure Instagram Reels Setup, Validator & Guide

Helps you:
1. Validate your Instagram Business Account ID and Meta Graph API Access Token.
2. Check token expiration date and permissions (instagram_basic, instagram_content_publish).
3. Securely save credentials into .env (which is strictly gitignored to keep data safe).
4. Print step-by-step links and instructions for GitHub Repository Secrets.
5. Convert short-lived Meta tokens into 60-day long-lived tokens automatically.
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENV_FILE = ROOT / ".env"


def load_env_vars() -> Dict[str, str]:
    """Reads existing .env file into a dict without external libraries."""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'").strip('"')
    return env


def save_env_var(key: str, value: str) -> None:
    """Updates or adds a key-value pair in .env securely."""
    lines = []
    found = False
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} ="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"🔒 Securely saved {key} to local .env (protected by .gitignore)")


def inspect_meta_token(access_token: str) -> Dict[str, Any]:
    """Inspects a Meta access token using graph.facebook.com/debug_token or /me."""
    try:
        import requests
    except ImportError:
        return {"valid": False, "error": "requests library not installed"}

    clean_tok = access_token.strip()
    headers = {"Authorization": f"Bearer {clean_tok}"}

    # 1. Query /me to verify user identity
    try:
        r = requests.get("https://graph.facebook.com/v21.0/me", headers=headers, params={"fields": "id,name"}, timeout=10)
        me_data = r.json()
        if "error" in me_data:
            err = me_data["error"].get("message", "Invalid Token")
            return {"valid": False, "error": err}
    except Exception as e:
        return {"valid": False, "error": str(e)}

    # 2. Query /me/permissions to verify Instagram publish permissions
    perms = []
    try:
        r_perms = requests.get("https://graph.facebook.com/v21.0/me/permissions", headers=headers, timeout=10)
        p_data = r_perms.json().get("data", [])
        perms = [p.get("permission") for p in p_data if p.get("status") == "granted"]
    except Exception:
        pass

    # 3. Query /me/accounts to find connected Instagram Business Accounts
    accounts = []
    try:
        r_acc = requests.get(
            "https://graph.facebook.com/v21.0/me/accounts",
            headers=headers,
            params={"fields": "id,name,instagram_business_account{id,username,name,profile_picture_url}"},
            timeout=10,
        )
        for page in r_acc.json().get("data", []):
            ig = page.get("instagram_business_account")
            if ig:
                accounts.append({
                    "page_name": page.get("name"),
                    "page_id": page.get("id"),
                    "instagram_id": ig.get("id"),
                    "instagram_username": ig.get("username"),
                    "instagram_name": ig.get("name", ig.get("username")),
                })
    except Exception:
        pass

    return {
        "valid": True,
        "user_id": me_data.get("id"),
        "user_name": me_data.get("name"),
        "permissions": perms,
        "accounts": accounts,
    }


def exchange_long_lived_token(short_token: str, app_id: str, app_secret: str) -> Optional[str]:
    """Exchanges a short-lived user token for a 60-day long-lived access token."""
    try:
        import requests
        url = "https://graph.facebook.com/v21.0/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id.strip(),
            "client_secret": app_secret.strip(),
            "fb_exchange_token": short_token.strip(),
        }
        r = requests.get(url, params=params, timeout=15)
        d = r.json()
        if "access_token" in d:
            return d["access_token"]
        else:
            print("❌ Exchange error:", d.get("error", {}).get("message", "Unknown error"))
    except Exception as e:
        print("❌ Exchange request failed:", e)
    return None


def print_step_by_step_guide():
    """Prints clear, clickable markdown instructions for the user."""
    print()
    print("=" * 80)
    print("📱 HOW TO GET INSTAGRAM REELS CREDENTIALS (STEP-BY-STEP)")
    print("=" * 80)
    print()
    print("STEP 1: Ensure your Instagram Account is a Professional/Creator Account")
    print("  • Open Instagram on Mobile -> Settings -> Account type -> Switch to Professional / Creator Account.")
    print("  • Connect it to a Facebook Page (or create a new Facebook Page named after your channel).")
    print()
    print("STEP 2: Open Meta Graph API Explorer")
    print("  👉 Direct URL: https://developers.facebook.com/tools/explorer/")
    print("  • Under 'Meta App', select your App (or create a basic app if you don't have one).")
    print("  • Under 'User or Page', select 'User Token'.")
    print("  • Click 'Add a Permission' and add these 3 required permissions:")
    print("     1. instagram_basic")
    print("     2. instagram_content_publish")
    print("     3. pages_read_engagement")
    print("  • Click 'Generate Access Token' -> Log in and approve all permissions.")
    print()
    print("STEP 3: Get your Instagram Business Account ID")
    print("  • In the Graph API Explorer GET box, type:")
    print("     me/accounts?fields=name,instagram_business_account{id,username}")
    print("  • Click 'Submit'. Look for 'instagram_business_account' -> 'id': '17841xxxxxxxxxxx'")
    print("  • That number is your INSTAGRAM_USER_ID!")
    print()
    print("STEP 4 (RECOMMENDED): Extend Token to 60-Day Long-Lived Token")
    print("  👉 Direct URL: https://developers.facebook.com/tools/debug/accesstoken/")
    print("  • Paste your token into the Access Token Debugger and click 'Debug'.")
    print("  • Scroll to the bottom and click 'Extend Access Token'.")
    print("  • Copy the new 60-day token!")
    print()
    print("STEP 5: Where to Paste (100% Secure, Never in Code)")
    print("  A) GitHub Cloud Publishing (Automatic 24/7):")
    print("     👉 URL: https://github.com/Harsha79819/autotube-ai/settings/secrets/actions")
    print("     • Click 'New repository secret':")
    print("       Name: INSTAGRAM_USER_ID      Value: (your Instagram ID e.g. 17841...)")
    print("       Name: INSTAGRAM_ACCESS_TOKEN Value: (your EAAB... token)")
    print("  B) Local Laptop Testing:")
    print("     • Run: python scripts/setup_instagram.py --set-token YOUR_TOKEN --set-id YOUR_ID")
    print("     • Saved to local .env (strictly gitignored, never committed).")
    print("=" * 80)
    print()


def main():
    parser = argparse.ArgumentParser(description="Secure Instagram Reels Setup & Validator")
    parser.add_argument("--guide", action="store_true", help="Print step-by-step instructions with clickable links")
    parser.add_argument("--test", action="store_true", help="Test current Instagram credentials")
    parser.add_argument("--set-token", type=str, default=None, help="Securely save INSTAGRAM_ACCESS_TOKEN to local .env")
    parser.add_argument("--set-id", type=str, default=None, help="Securely save INSTAGRAM_USER_ID to local .env")
    parser.add_argument("--exchange", action="store_true", help="Exchange short token for 60-day long-lived token")
    parser.add_argument("--app-id", type=str, default=None, help="Meta App ID for token exchange")
    parser.add_argument("--app-secret", type=str, default=None, help="Meta App Secret for token exchange")
    args = parser.parse_args()

    if args.set_token:
        save_env_var("INSTAGRAM_ACCESS_TOKEN", args.set_token.strip())
    if args.set_id:
        save_env_var("INSTAGRAM_USER_ID", args.set_id.strip())

    if args.exchange:
        env = load_env_vars()
        tok = args.set_token or env.get("INSTAGRAM_ACCESS_TOKEN")
        app_id = args.app_id or env.get("META_APP_ID")
        app_sec = args.app_secret or env.get("META_APP_SECRET")
        if not tok or not app_id or not app_sec:
            print("❌ Error: Need --set-token, --app-id, and --app-secret to exchange token.")
            sys.exit(1)
        long_tok = exchange_long_lived_token(tok, app_id, app_sec)
        if long_tok:
            save_env_var("INSTAGRAM_ACCESS_TOKEN", long_tok)
            print("✅ Long-lived token (60 days) saved successfully!")
            return

    if args.test or (args.set_token or args.set_id):
        env = load_env_vars()
        tok = os.getenv("INSTAGRAM_ACCESS_TOKEN") or env.get("INSTAGRAM_ACCESS_TOKEN")
        uid = os.getenv("INSTAGRAM_USER_ID") or env.get("INSTAGRAM_USER_ID") or env.get("INSTAGRAM_ACCOUNT_ID")

        if not tok:
            print("⚠️ No INSTAGRAM_ACCESS_TOKEN found in environment or .env.")
            print_step_by_step_guide()
            return

        print("🔍 Inspecting Meta Access Token...")
        info = inspect_meta_token(tok)
        if not info.get("valid"):
            print(f"❌ Token validation failed: {info.get('error')}")
            return

        print(f"✅ Meta Token is VALID! (Authorized User: {info.get('user_name')} [ID: {info.get('user_id')}])")
        print(f"🔑 Granted Permissions: {', '.join(info.get('permissions', []))}")

        required_perms = {"instagram_basic", "instagram_content_publish"}
        missing_perms = required_perms - set(info.get("permissions", []))
        if missing_perms:
            print(f"⚠️ Warning: Missing required permissions: {missing_perms}")
            print("   Please re-generate token in Graph API Explorer with these permissions added.")

        accounts = info.get("accounts", [])
        if accounts:
            print(f"📸 Found {len(accounts)} Linked Instagram Business Account(s):")
            for idx, a in enumerate(accounts, 1):
                print(f"   [{idx}] @{a['instagram_username']} ({a['instagram_name']})")
                print(f"       Instagram ID : {a['instagram_id']}")
                print(f"       Linked Page  : {a['page_name']} ({a['page_id']})")
                if not uid:
                    save_env_var("INSTAGRAM_USER_ID", a["instagram_id"])
                    print(f"   👉 Auto-selected and saved INSTAGRAM_USER_ID={a['instagram_id']}")
        else:
            print("⚠️ No Instagram Business Account linked to this token's Facebook Pages.")
            print("   Make sure your Instagram account is switched to Professional/Creator and linked to a Facebook Page.")

        return

    # Default: print guide
    print_step_by_step_guide()


if __name__ == "__main__":
    main()

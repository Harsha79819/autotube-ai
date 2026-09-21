import os
import time
import requests


# ============================================================
# INSTAGRAM CREDENTIAL HELPERS
# ============================================================

def get_instagram_credentials():
    """
    Retrieve Instagram Graph API credentials from environment or Streamlit secrets.
    Supports:
      - INSTAGRAM_ACCOUNT_ID / INSTAGRAM_USER_ID / IG_USER_ID / IG_ACCOUNT_ID
      - INSTAGRAM_ACCESS_TOKEN / IG_ACCESS_TOKEN
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except Exception:
        pass

    ig_user_id = (
        os.getenv("INSTAGRAM_ACCOUNT_ID")
        or os.getenv("INSTAGRAM_USER_ID")
        or os.getenv("IG_USER_ID")
        or os.getenv("IG_ACCOUNT_ID")
    )
    access_token = (
        os.getenv("INSTAGRAM_ACCESS_TOKEN")
        or os.getenv("IG_ACCESS_TOKEN")
    )

    if not ig_user_id or not access_token:
        try:
            import streamlit as st
            if hasattr(st, "secrets"):
                ig_user_id = (
                    ig_user_id
                    or st.secrets.get("INSTAGRAM_ACCOUNT_ID")
                    or st.secrets.get("INSTAGRAM_USER_ID")
                    or st.secrets.get("IG_USER_ID")
                )
                access_token = (
                    access_token
                    or st.secrets.get("INSTAGRAM_ACCESS_TOKEN")
                    or st.secrets.get("IG_ACCESS_TOKEN")
                )
        except Exception:
            pass

    return ig_user_id, access_token


# ============================================================
# ACCOUNT INFO & IDENTIFIER RESOLVER
# ============================================================

def get_instagram_account_info():
    """
    Fetch connected Instagram business account info (username, name, ID)
    using the configured Meta access token.
    """
    uid, tok = get_instagram_credentials()
    if not tok:
        return {"connected": False, "error": "No INSTAGRAM_ACCESS_TOKEN found in .env"}

    # 1. Check if configured UID is valid
    if uid:
        try:
            r = requests.get(
                f"https://graph.facebook.com/v21.0/{uid}",
                params={"fields": "id,username,name,profile_picture_url", "access_token": tok},
                timeout=10,
            )
            d = r.json()
            if "username" in d:
                return {
                    "connected": True,
                    "id": d["id"],
                    "username": d["username"],
                    "name": d.get("name", d["username"]),
                    "profile_picture": d.get("profile_picture_url"),
                }
        except Exception:
            pass

    # 2. Check Facebook Pages for linked Instagram accounts
    try:
        r = requests.get(
            "https://graph.facebook.com/v21.0/me/accounts",
            params={"fields": "id,name,instagram_business_account{id,username,name,profile_picture_url}", "access_token": tok},
            timeout=10,
        )
        data = r.json()
        if "error" in data:
            return {"connected": False, "error": data["error"].get("message")}
        for p in data.get("data", []):
            ig = p.get("instagram_business_account")
            if ig:
                return {
                    "connected": True,
                    "id": ig["id"],
                    "username": ig["username"],
                    "name": ig.get("name", ig["username"]),
                    "page_name": p.get("name"),
                    "page_id": p.get("id"),
                    "profile_picture": ig.get("profile_picture_url"),
                }
        pages = [p.get("name") for p in data.get("data", [])]
        return {
            "connected": False,
            "error": "Instagram account not linked to Facebook page",
            "facebook_pages": pages,
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


# ============================================================
# ELIGIBILITY CHECKER
# ============================================================

def should_upload_to_instagram(video_duration_seconds, user_enabled_instagram, aspect_ratio):
    """
    Validate whether a video is eligible for automatic Instagram Reels upload.
    Constraints:
      1. User explicitly opted in via dashboard toggle.
      2. Video duration <= 90 seconds (Reels API max limit).
      3. Aspect ratio is strictly 9:16 vertical.
    """
    if not user_enabled_instagram:
        return False, "User did not opt in"
    if video_duration_seconds > 90:
        return False, "Video exceeds 90s Reels limit"
    if str(aspect_ratio).strip() != "9:16":
        return False, "Reels requires 9:16 vertical format"
    return True, "Eligible for Instagram upload"


# ============================================================
# GRAPH API REELS UPLOAD
# ============================================================

def upload_to_instagram_reels(video_source=None, caption="", ig_user_id=None, access_token=None, public_video_url=None):
    """
    Upload and publish a video to Instagram Reels using the Meta Graph API v21.0.

    Supports:
      - Direct local file upload via Meta Resumable Upload protocol (fast & reliable, no public web server needed)
      - Public HTTP/HTTPS video URL fallback
    """
    source = video_source or public_video_url
    if not source:
        return {"success": False, "error": "No video source provided"}

    if not ig_user_id or not access_token:
        c_id, c_tok = get_instagram_credentials()
        ig_user_id = ig_user_id or c_id
        access_token = access_token or c_tok

    if not ig_user_id or not access_token:
        return {
            "success": False,
            "error": "Instagram credentials missing. Set INSTAGRAM_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN in .env or secrets."
        }

    source_str = str(source)
    is_local_file = os.path.isfile(source_str)

    try:
        if is_local_file:
            print(f"📤 Uploading local video directly to Instagram Reels: {source_str} ({os.path.getsize(source_str)} bytes)")
            # Step 1: Initialize Resumable Upload container
            init_resp = requests.post(
                f"https://graph.facebook.com/v21.0/{ig_user_id}/media",
                data={
                    "upload_type": "resumable",
                    "media_type": "REELS",
                    "caption": caption,
                    "share_to_feed": "true",
                    "access_token": access_token,
                },
                timeout=30,
            )
            init_data = init_resp.json()
            if "id" not in init_data or "uri" not in init_data:
                return {"success": False, "error": f"Failed to initialize Reels upload container: {init_data}"}

            creation_id = init_data["id"]
            upload_uri = init_data["uri"]

            # Step 2: Upload binary bytes to Meta rupload endpoint
            with open(source_str, "rb") as vf:
                video_bytes = vf.read()

            upload_headers = {
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(len(video_bytes)),
            }
            upload_resp = requests.post(
                upload_uri,
                headers=upload_headers,
                data=video_bytes,
                timeout=120,
            )
            if upload_resp.status_code not in (200, 201):
                return {"success": False, "error": f"Binary video upload to Meta failed ({upload_resp.status_code}): {upload_resp.text}"}
        else:
            print(f"🌐 Creating Reels container from public video URL: {source_str}")
            container_resp = requests.post(
                f"https://graph.facebook.com/v21.0/{ig_user_id}/media",
                data={
                    "media_type": "REELS",
                    "video_url": source_str,
                    "caption": caption,
                    "share_to_feed": "true",
                    "access_token": access_token,
                },
                timeout=30,
            )
            c_data = container_resp.json()
            if "id" not in c_data:
                return {"success": False, "error": f"Failed to create media container: {c_data}"}

            creation_id = c_data["id"]

        # Step 3: Poll status until FINISHED (Meta processes the video)
        finished = False
        for attempt in range(30):
            time.sleep(5)
            status_resp = requests.get(
                f"https://graph.facebook.com/v21.0/{creation_id}",
                params={"fields": "status_code", "access_token": access_token},
                timeout=15,
            )
            s_data = status_resp.json()
            status_code = s_data.get("status_code")
            if status_code == "FINISHED":
                finished = True
                break
            elif status_code == "ERROR":
                return {"success": False, "error": f"Media container error: {s_data}"}

        if not finished:
            return {"success": False, "error": "Timed out waiting for Instagram media container to finish processing."}

        # Step 4: Publish container
        publish_resp = requests.post(
            f"https://graph.facebook.com/v21.0/{ig_user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": access_token},
            timeout=30,
        )
        p_data = publish_resp.json()
        if "id" in p_data:
            return {"success": True, "media_id": p_data["id"], "raw": p_data}
        return {"success": False, "error": f"Publish failed: {p_data}"}

    except Exception as e:
        return {"success": False, "error": str(e)}

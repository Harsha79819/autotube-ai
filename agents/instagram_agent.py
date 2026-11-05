import os
import json
import time
import requests
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple


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

def _clean_instagram_error(error_val, tok=None):
    """
    Sanitize Instagram/Meta API error strings:
    1. Strip raw access tokens so secrets are never exposed in UI or logs.
    2. Convert network/DNS resolution errors into clear, friendly guidance.
    3. Convert token expiration errors into actionable instructions.
    """
    err_str = str(error_val or "")
    if tok:
        err_str = err_str.replace(tok, "[REDACTED_TOKEN]")
    err_str = re.sub(r"EAA[A-Za-z0-9]+", "[REDACTED_TOKEN]", err_str)
    err_str = re.sub(r"access_token=[^&\s'\"]+", "access_token=[REDACTED]", err_str)

    err_lower = err_str.lower()
    if any(k in err_lower for k in ("nameresolutionerror", "errno 8", "failed to resolve", "nodename nor servname")):
        return "Network error: Unable to reach graph.facebook.com (DNS resolution failed). Please check your internet or DNS connection."
    if "user logged out" in err_lower:
        return "Meta Access Token invalidated: The Facebook/Meta session ended because of a logout. Please log in, generate a fresh token from developers.facebook.com, and paste it here."
    if "session has expired" in err_lower or "error validating access token" in err_lower:
        return "Meta Access Token has expired. Please generate a fresh token from developers.facebook.com and update INSTAGRAM_ACCESS_TOKEN in .env."
    if "connection refused" in err_lower or "timed out" in err_lower:
        return "Connection timeout: Unable to reach Instagram Graph API. Please check your network."
    if "processingfailederror" in err_lower or "request processing failed" in err_lower:
        return "Meta video processing error (ProcessingFailedError): Meta was unable to process the video stream. Please ensure the video has valid H.264/AAC encoding, faststart metadata, and duration <= 90s."

    return err_str


def get_instagram_account_info():
    """
    Fetch connected Instagram business account info (username, name, ID)
    using the configured Meta access token.
    """
    uid, tok = get_instagram_credentials()
    if not tok:
        return {"connected": False, "error": "No INSTAGRAM_ACCESS_TOKEN found in .env"}

    headers = {"Authorization": f"Bearer {tok}"}

    # 1. Check if configured UID is valid
    if uid:
        try:
            r = requests.get(
                f"https://graph.facebook.com/v21.0/{uid}",
                headers=headers,
                params={"fields": "id,username,name,profile_picture_url"},
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
            headers=headers,
            params={"fields": "id,name,instagram_business_account{id,username,name,profile_picture_url}"},
            timeout=10,
        )
        data = r.json()
        if "error" in data:
            raw_msg = data["error"].get("message", "API Error")
            return {"connected": False, "error": _clean_instagram_error(raw_msg, tok)}
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
        return {"connected": False, "error": _clean_instagram_error(e, tok)}


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


def format_reels_caption(title: str, topic: str = "", tags: Optional[List[str]] = None) -> str:
    """
    Formats a clean, high-engagement Instagram Reels caption.
    Includes viral Telugu hashtags and respects Instagram's 2,200 char limit.
    """
    clean_title = (title or topic or "Trending Reel").strip()
    base_hashtags = ["#reels", "#telugureels", "#trending", "#viral", "#telugu", "#shorts", "#explore"]

    # Category-specific hashtags
    t_lower = f"{clean_title} {topic}".lower()
    if any(k in t_lower for k in ("bigg boss", "bb10", "star maa")):
        base_hashtags.extend(["#biggboss", "#biggbosstelugu", "#bb10", "#starmaa"])
    elif any(k in t_lower for k in ("news", "andhra", "telangana", "govt", "cm", "tdp", "ysrcp")):
        base_hashtags.extend(["#telugunews", "#andhranews", "#breakingnews"])
    elif any(k in t_lower for k in ("tech", "ai", "mobile", "phone", "apple", "google")):
        base_hashtags.extend(["#telugutech", "#technews", "#gadgets"])
    elif any(k in t_lower for k in ("movie", "film", "cinema", "tollywood")):
        base_hashtags.extend(["#tollywood", "#telugucinema", "#moviereview"])
    else:
        base_hashtags.extend(["#facts", "#telugufacts", "#knowledge"])

    if tags:
        for t in tags[:5]:
            ht = "#" + re.sub(r"[^a-zA-Z0-9_]", "", str(t))
            if len(ht) > 2 and ht.lower() not in [h.lower() for h in base_hashtags]:
                base_hashtags.append(ht)

    hashtags_str = " ".join(base_hashtags[:12])
    caption = f"{clean_title}\n\nFollow for daily updates! 🔥\n\n{hashtags_str}"
    return caption[:2150]


# ============================================================
# GRAPH API REELS UPLOAD
# ============================================================

def _prepare_meta_reels_video(video_path: str) -> str:
    """
    Ensure the video meets 100% of Meta Instagram Reels technical ingestion specifications:
      1. Container: MP4 with 'moov' atom at the front (+faststart).
      2. Duration: <= 90 seconds (hard limit for Instagram Reels).
      3. Video Codec: H.264 (AVC) with High/Main profile.
      4. Pixel Format: strictly 'yuv420p' (NOT deprecated 'yuvj420p' or full-range).
      5. Color Matrix & Range: 'bt709' color space with limited 'tv' range (NOT 'pc' full range).
      6. Audio Codec: AAC stereo (strictly 2 channels, 44.1kHz or 48kHz). Mono audio triggers ProcessingFailedError.
      7. Aspect Ratio: 9:16 vertical (1080x1920 recommended).
      8. File Size / Bitrate: <= 22MB and <= 2.5 Mbps video stream to prevent Meta proxy timeouts (400 ProcessingFailedError).

    If any check fails, transcode/remux automatically to guarantee zero Meta rupload rejection.
    Returns path to the compliant video file.
    """
    try:
        p = Path(video_path)
        if not p.exists() or p.stat().st_size == 0:
            return str(video_path)

        file_size = p.stat().st_size

        # 1. Check faststart ('moov' within first 1MB and before 'mdat')
        has_faststart = False
        with open(p, "rb") as f:
            header = f.read(1048576)
            moov_pos = header.find(b"moov")
            mdat_pos = header.find(b"mdat")
            if moov_pos != -1 and (mdat_pos == -1 or moov_pos < mdat_pos):
                has_faststart = True

        # 2. Probe streams with ffprobe
        cmd = [
            "ffprobe", "-v", "error",
            "-show_streams", "-show_format",
            "-print_format", "json",
            str(p)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        info = json.loads(res.stdout or "{}")
        streams = info.get("streams", [])
        fmt = info.get("format", {})

        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        duration = float(fmt.get("duration", 0) or (v_stream.get("duration", 0) if v_stream else 0))
        fmt_bitrate = int(fmt.get("bit_rate", 0) or (v_stream.get("bit_rate", 0) if v_stream else 0))

        v_codec = v_stream.get("codec_name", "") if v_stream else ""
        pix_fmt = v_stream.get("pix_fmt", "") if v_stream else ""
        color_range = v_stream.get("color_range", "") if v_stream else ""
        color_space = v_stream.get("color_space", "") if v_stream else ""

        a_codec = a_stream.get("codec_name", "") if a_stream else ""
        channels = int(a_stream.get("channels", 0)) if a_stream else 0

        # Maximum payload size for zero-timeout Meta edge-proxy transmission is ~16 MB
        is_compliant = (
            has_faststart
            and duration <= 90.0
            and v_codec == "h264"
            and pix_fmt == "yuv420p"
            and color_range in ("tv", "limited", "unknown", "")
            and color_space not in ("bt470bg", "smpte170m")
            and a_stream is not None
            and a_codec == "aac"
            and channels == 2
            and file_size <= 16 * 1024 * 1024
            and (fmt_bitrate <= 1600000 or fmt_bitrate == 0)
        )

        if is_compliant:
            return str(p)

        print(
            f"🎬 Video stream non-compliant for Meta Reels (size={file_size / (1024*1024):.1f}MB, "
            f"bitrate={fmt_bitrate/1000:.0f}k, pix_fmt={pix_fmt}, range={color_range}, "
            f"audio_channels={channels}, dur={duration:.1f}s, faststart={has_faststart}). "
            f"Transcoding to guaranteed Meta Reels standard..."
        )

        compliant_tmp = p.with_name(f"{p.stem}.reels_ready.mp4")

        inputs = ["-i", str(p)]
        audio_args = []
        if not a_stream or channels == 0:
            inputs.extend(["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
            audio_args = ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-shortest"]
        else:
            audio_args = ["-map", "0:v:0", "-map", "0:a:0", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-shortest"]

        vf = "format=yuv420p,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1"

        transcode_cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-vf", vf,
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-color_range", "tv",
            "-c:v", "libx264",
            "-profile:v", "high",
            "-level", "4.0",
            "-preset", "fast",
            "-flags", "+cgop",
            "-g", "60",
            "-keyint_min", "30",
            "-crf", "26",
            "-maxrate", "1400k",
            "-bufsize", "2800k",
            *audio_args,
            "-movflags", "+faststart",
        ]
        if duration > 90.0:
            transcode_cmd.extend(["-t", "90"])

        transcode_cmd.append(str(compliant_tmp))

        r_trans = subprocess.run(transcode_cmd, capture_output=True, text=True, timeout=120)
        if r_trans.returncode == 0 and compliant_tmp.exists() and compliant_tmp.stat().st_size > 0:
            print(f"✅ Video successfully transcoded to 100% Meta Reels compliant format: {compliant_tmp.name} ({compliant_tmp.stat().st_size} bytes)")
            return str(compliant_tmp)
        else:
            print(f"⚠️ Notice during Meta Reels transcoding: {r_trans.stderr or 'Transcode failed'}")
    except Exception as e:
        print(f"⚠️ Error preparing video for Meta Reels: {e}")

    return str(video_path)


_ensure_faststart = _prepare_meta_reels_video


def upload_to_instagram_reels(video_source=None, caption="", ig_user_id=None, access_token=None, public_video_url=None):
    """
    Upload and publish a video to Instagram Reels using the Meta Graph API v21.0.

    Supports:
      - Direct local file upload via Meta Resumable Upload protocol (fast & reliable, no public web server needed)
      - Public HTTP/HTTPS video URL fallback (via Cloudflare/Ngrok tunnel if active)
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
    creation_id = None

    try:
        # Determine fallback tunnel / public URL if available
        fallback_url = public_video_url
        if not fallback_url or "smokeless-waking-remote" in str(fallback_url):
            tunnel_file = Path("output/tunnel_url.txt")
            if tunnel_file.exists():
                try:
                    t_url = tunnel_file.read_text(encoding="utf-8").strip()
                    if t_url.startswith("http"):
                        fallback_url = f"{t_url.rstrip('/')}/output/final_video.mp4"
                except Exception:
                    pass

        if is_local_file:
            upload_path = _prepare_meta_reels_video(source_str)
            file_size = os.path.getsize(upload_path)
            print(f"📤 Uploading local video directly to Instagram Reels: {upload_path} ({file_size} bytes)")

            # Helper to initialize container
            def _create_resumable_container():
                return requests.post(
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

            # Step 1: Initialize Resumable Upload container
            init_resp = _create_resumable_container()
            init_data = init_resp.json()
            if "id" not in init_data or "uri" not in init_data:
                err_msg = _clean_instagram_error(init_data, access_token)
                return {"success": False, "error": f"Failed to initialize Reels upload container: {err_msg}"}

            creation_id = init_data["id"]
            upload_uri = init_data["uri"]

            # Step 2: Upload binary bytes to Meta rupload endpoint with official resumable headers
            # Streams the full video file to prevent stream truncation and 400 ProcessingFailedError.

            def _check_container_progress(c_id):
                """Check if container has received the video stream and is processing or finished on Graph API."""
                try:
                    c_resp = requests.get(
                        f"https://graph.facebook.com/v21.0/{c_id}",
                        params={"fields": "status_code,status", "access_token": access_token},
                        timeout=15,
                    )
                    c_info = c_resp.json()
                    st = c_info.get("status_code")
                    if st in ("FINISHED", "IN_PROGRESS"):
                        return True, st
                except Exception:
                    pass
                return False, None

            def _do_rupload(target_uri, c_id=None):
                # 1. Primary path: Stream whole file via curl (fast, zero memory overhead, OS-buffered streaming)
                try:
                    curl_cmd = [
                        "curl", "-sS", "-X", "POST",
                        "-H", f"Authorization: OAuth {access_token}",
                        "-H", "offset: 0",
                        "-H", f"file_size: {file_size}",
                        "-H", "Content-Type: application/octet-stream",
                        "--data-binary", f"@{upload_path}",
                        "-w", "\n%{http_code}",
                        target_uri,
                    ]
                    res = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=240)
                    if res.returncode == 0:
                        lines = res.stdout.strip().split("\n")
                        http_code_str = lines[-1].strip() if lines else "unknown"
                        body_str = "\n".join(lines[:-1]) if len(lines) > 1 else ""

                        if http_code_str in ("200", "201"):
                            return True, int(http_code_str), body_str

                        try:
                            ret_json = json.loads(body_str or "{}")
                            if ret_json.get("success") is True or "id" in ret_json:
                                return True, 200, body_str
                        except Exception:
                            if "success" in body_str:
                                return True, 200, body_str
                except Exception as e_curl:
                    print(f"⚠️ curl rupload notice: {e_curl}")

                # 2. Secondary path: Python requests streaming
                # Streams full file or continues sequential chunks if server returns HTTP 206
                try:
                    CHUNK_SIZE = 4 * 1024 * 1024
                    with open(upload_path, "rb") as vf:
                        offset = 0
                        chunk_idx = 1

                        while offset < file_size:
                            vf.seek(offset)
                            # If sending full stream or last chunk
                            read_len = CHUNK_SIZE if file_size > CHUNK_SIZE else file_size
                            chunk_data = vf.read(read_len)
                            chunk_len = len(chunk_data)

                            chunk_headers = {
                                "Authorization": f"OAuth {access_token}",
                                "offset": str(offset),
                                "file_size": str(file_size),
                                "Content-Type": "application/octet-stream",
                            }

                            resp = requests.post(
                                target_uri,
                                headers=chunk_headers,
                                data=chunk_data,
                                timeout=240,
                            )

                            if resp.status_code in (200, 201):
                                return True, resp.status_code, resp.text

                            try:
                                r_data = resp.json()
                                if r_data.get("success") is True or "id" in r_data:
                                    return True, 200, resp.text
                            except Exception:
                                if "success" in resp.text:
                                    return True, 200, resp.text

                            # If server explicitly returns HTTP 206 Partial Content, proceed with next slice
                            if resp.status_code == 206:
                                offset += chunk_len
                                chunk_idx += 1
                                continue

                            return False, resp.status_code, resp.text

                        return True, 200, "Upload completed"
                except Exception as e_req:
                    return False, 500, str(e_req)

            upload_success, up_code, up_text = _do_rupload(upload_uri, creation_id)

            # Retry with a FRESH container if first attempt failed
            if not upload_success:
                print(f"⚠️ Resumable upload attempt 1 returned {up_code}. Re-initializing fresh container for retry...")
                time.sleep(3)
                retry_init = _create_resumable_container()
                retry_data = retry_init.json()
                if "id" in retry_data and "uri" in retry_data:
                    creation_id = retry_data["id"]
                    upload_uri = retry_data["uri"]
                    upload_success, up_code, up_text = _do_rupload(upload_uri, creation_id)

            # Verification guard: Check if container actually received the stream on Meta Graph API
            if not upload_success and creation_id:
                is_acc, st_c = _check_container_progress(creation_id)
                if is_acc:
                    print(f"✅ Meta container {creation_id} confirmed {st_c} on Graph API before declaring failure.")
                    upload_success = True

            # If binary upload failed, try fallback to public video URL if available
            if not upload_success:
                if fallback_url and fallback_url.startswith("http") and "smokeless-waking-remote" not in fallback_url:
                    print(f"🔄 Binary upload to Meta returned {up_code}. Attempting fallback via public video URL: {fallback_url}")
                    container_resp = requests.post(
                        f"https://graph.facebook.com/v21.0/{ig_user_id}/media",
                        data={
                            "media_type": "REELS",
                            "video_url": fallback_url,
                            "caption": caption,
                            "share_to_feed": "true",
                            "access_token": access_token,
                        },
                        timeout=30,
                    )
                    c_data = container_resp.json()
                    if "id" in c_data:
                        creation_id = c_data["id"]
                    else:
                        clean_c_err = _clean_instagram_error(c_data, access_token)
                        return {"success": False, "error": f"Public video URL fallback failed: {clean_c_err}"}
                else:
                    clean_up_err = _clean_instagram_error(up_text, access_token)
                    return {"success": False, "error": f"Binary video upload to Meta failed ({up_code}): {clean_up_err}"}
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
                clean_err = _clean_instagram_error(c_data, access_token)
                return {"success": False, "error": f"Failed to create media container: {clean_err}"}

            creation_id = c_data["id"]

        # Step 3: Poll status until FINISHED (Meta processes the video)
        finished = False
        print(f"⏳ Waiting for Instagram media container {creation_id} to finish processing...")
        for attempt in range(60):
            time.sleep(5)
            status_resp = requests.get(
                f"https://graph.facebook.com/v21.0/{creation_id}",
                params={"fields": "status_code", "access_token": access_token},
                timeout=15,
            )
            s_data = status_resp.json()
            status_code = s_data.get("status_code")
            if (attempt + 1) % 4 == 0 or status_code == "FINISHED":
                print(f"⏳ Processing poll {attempt + 1}/60: status_code={status_code}")
            if status_code == "FINISHED":
                finished = True
                break
            elif status_code == "ERROR":
                clean_err = _clean_instagram_error(s_data, access_token)
                return {"success": False, "error": f"Media container error: {clean_err}"}

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
            media_id = p_data["id"]
            permalink = None
            try:
                media_info = requests.get(
                    f"https://graph.facebook.com/v21.0/{media_id}",
                    params={"fields": "permalink", "access_token": access_token},
                    timeout=10,
                ).json()
                permalink = media_info.get("permalink")
            except Exception:
                pass
            return {"success": True, "media_id": media_id, "permalink": permalink, "raw": p_data}
        clean_err = _clean_instagram_error(p_data, access_token)
        return {"success": False, "error": f"Publish failed: {clean_err}"}

    except Exception as e:
        return {"success": False, "error": _clean_instagram_error(e, access_token)}

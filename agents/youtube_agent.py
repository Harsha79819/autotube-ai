import os
import json
import importlib
import re
from supervisor import autonomous_recover



SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

UPLOAD_LOG = "output/uploaded_videos.json"


# ============================================================
# UPLOAD LOG
# ============================================================

def load_uploaded_videos():

    if os.path.exists(UPLOAD_LOG):

        try:

            with open(
                UPLOAD_LOG,
                "r",
                encoding="utf-8",
            ) as f:

                return json.load(f)

        except Exception:

            return {}

    return {}


def save_uploaded_videos(data):

    os.makedirs(
        "output",
        exist_ok=True,
    )

    with open(
        UPLOAD_LOG,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False,
        )


# ============================================================
# TITLE NORMALIZATION
# ============================================================

def normalize_title(title):

    title = title.lower()

    # Remove punctuation
    title = re.sub(
        r"[^a-z0-9\s]",
        " ",
        title,
    )

    # Normalize whitespace
    title = re.sub(
        r"\s+",
        " ",
        title,
    ).strip()

    return title


# ============================================================
# SIMILAR TITLE DETECTION
# ============================================================

def is_similar_title(
    title1,
    title2,
    threshold=0.45,
):

    words1 = set(
        normalize_title(title1).split()
    )

    words2 = set(
        normalize_title(title2).split()
    )

    if not words1 or not words2:

        return False

    intersection = words1 & words2

    union = words1 | words2

    similarity = (
        len(intersection)
        / len(union)
    )

    return similarity >= threshold


# ============================================================
# HASHTAGS
# ============================================================

def create_hashtags(
    title,
    tags,
):

    hashtags = []

    # Title words
    title_words = re.findall(
        r"[A-Za-z0-9]+",
        title,
    )

    if title_words:

        # Keep only useful title keywords
        stop_words = {
            "the",
            "a",
            "an",
            "in",
            "on",
            "of",
            "to",
            "for",
            "and",
            "due",
            "with",
            "how",
            "why",
            "is",
            "are",
        }

        useful_words = [
            word
            for word in title_words
            if word.lower() not in stop_words
        ]

        if useful_words:

            hashtag = (
                "#"
                + "".join(useful_words[:4])
            )

            hashtags.append(hashtag)

    # Tags
    for tag in tags or []:

        words = re.findall(
            r"[A-Za-z0-9]+",
            str(tag),
        )

        if not words:
            continue

        hashtag = (
            "#"
            + "".join(words[:4])
        )

        if hashtag.lower() not in {
            h.lower()
            for h in hashtags
        }:

            hashtags.append(hashtag)

        if len(hashtags) >= 5:
            break

    return hashtags[:5]


# ============================================================
# ADD HASHTAGS TO DESCRIPTION
# ============================================================

def add_hashtags_to_description(
    description,
    title,
    tags,
):

    description = (
        description or ""
    ).strip()

    hashtags = create_hashtags(
        title,
        tags,
    )

    if not hashtags:

        return description

    hashtag_text = " ".join(
        hashtags
    )

    # Don't duplicate hashtags
    existing = description.lower()

    new_hashtags = [
        hashtag
        for hashtag in hashtags
        if hashtag.lower() not in existing
    ]

    if not new_hashtags:

        return description

    if description:

        return (
            description
            + "\n\n"
            + " ".join(new_hashtags)
        )

    return " ".join(
        new_hashtags
    )


# ============================================================
# YOUTUBE PROCESSING STATUS
# ============================================================

def get_video_status(
    youtube,
    video_id,
):

    try:

        response = youtube.videos().list(
            part="status,processingDetails",
            id=video_id,
        ).execute()

        items = response.get(
            "items",
            [],
        )

        if not items:

            return None

        item = items[0]

        status = item.get(
            "status",
            {},
        )

        processing = item.get(
            "processingDetails",
            {},
        )

        return {
            "privacyStatus": status.get(
                "privacyStatus"
            ),
            "uploadStatus": status.get(
                "uploadStatus"
            ),
            "license": status.get(
                "license"
            ),
            "embeddable": status.get(
                "embeddable"
            ),
            "processingStatus": processing.get(
                "processingStatus"
            ),
            "processingFailureReason": processing.get(
                "processingFailureReason"
            ),
            "processingFailureDetail": processing.get(
                "processingFailureDetail"
            ),
        }

    except Exception as exc:

        print(
            "⚠️ Could not read YouTube processing status:"
        )

        print(exc)

        return None


# ============================================================
# PRINT YOUTUBE STATUS
# ============================================================

def print_video_status(
    youtube,
    video_id,
):

    status = get_video_status(
        youtube,
        video_id,
    )

    if not status:

        return

    print()
    print("=" * 60)
    print("YOUTUBE VIDEO STATUS")
    print("=" * 60)

    print(
        "Video ID:",
        video_id,
    )

    print(
        "Privacy:",
        status.get(
            "privacyStatus"
        ),
    )

    print(
        "Upload status:",
        status.get(
            "uploadStatus"
        ),
    )

    print(
        "Processing:",
        status.get(
            "processingStatus"
        ),
    )

    print(
        "License:",
        status.get(
            "license"
        ),
    )

    failure_reason = status.get(
        "processingFailureReason"
    )

    if failure_reason:

        print(
            "Processing failure:",
            failure_reason,
        )

    failure_detail = status.get(
        "processingFailureDetail"
    )

    if failure_detail:

        print(
            "Failure detail:",
            failure_detail,
        )

    print("=" * 60)
    print()


def get_channel_credential_paths(channel="Channel 1 (Primary)"):
    """
    Resolve token and client secret file paths based on YouTube channel choice.
    Supports Dual-Channel setups:
      - Channel 1 (Primary): token.json (or token_channel1.json), client_secret.json
      - Channel 2 (Secondary): token_channel2.json, client_secret 2.json / client_secret_channel2.json
    """
    ch_str = str(channel).lower()
    is_ch2 = ("channel 2" in ch_str) or ("secondary" in ch_str) or (ch_str == "2")

    if is_ch2:
        token_path = "token_channel2.json"
        candidate_secrets = [
            "client_secret 2.json",
            "client_secret_channel2.json",
            "client_secret.json",
        ]
    else:
        token_path = "token.json" if os.path.exists("token.json") or not os.path.exists("token_channel1.json") else "token_channel1.json"
        candidate_secrets = [
            "client_secret.json",
            "client_secret_channel1.json",
        ]

    secret_path = None
    for cand in candidate_secrets:
        if os.path.exists(cand):
            secret_path = cand
            break

    if not secret_path:
        secret_path = "client_secret.json"

    return token_path, secret_path


# ============================================================
# UPLOAD VIDEO
# ============================================================

@autonomous_recover("youtube_agent")
def upload_video(
    video_file,
    title,
    description,
    tags,
    privacy="public",
    channel="Channel 1 (Primary)",
):

    uploaded_videos = (
        load_uploaded_videos()
    )

    # --------------------------------------------------------
    # VALIDATE PRIVACY
    # --------------------------------------------------------

    allowed_privacy = {
        "public",
        "private",
        "unlisted",
    }

    if privacy not in allowed_privacy:

        raise ValueError(
            "privacy must be public, private, or unlisted"
        )

    # --------------------------------------------------------
    # DUPLICATE CHECK
    # --------------------------------------------------------

    if title in uploaded_videos:

        print()
        print(
            "Video already uploaded."
        )

        print(
            "Existing Video ID:",
            uploaded_videos[title],
        )

        return uploaded_videos[title]

    # Similar title / same-story detection
    for (
        previous_title,
        previous_video_id,
    ) in uploaded_videos.items():

        if is_similar_title(
            title,
            previous_title,
        ):

            print()
            print(
                "⚠️ POSSIBLE DUPLICATE STORY DETECTED"
            )

            print(
                "New title     :",
                title,
            )

            print(
                "Previous title:",
                previous_title,
            )

            print(
                "Existing ID   :",
                previous_video_id,
            )

            print()
            print(
                "Upload skipped."
            )

            return previous_video_id

    # --------------------------------------------------------
    # IMPORT GOOGLE LIBRARIES
    # --------------------------------------------------------

    try:

        Credentials = importlib.import_module(
            "google.oauth2.credentials"
        ).Credentials

        Request = importlib.import_module(
            "google.auth.transport.requests"
        ).Request

    except ImportError as exc:

        raise ImportError(
            "google-auth is required for YouTube uploads. "
            "Install it with: pip install google-auth"
        ) from exc

    try:

        build = importlib.import_module(
            "googleapiclient.discovery"
        ).build

    except ImportError as exc:

        raise ImportError(
            "google-api-python-client is required for YouTube uploads. "
            "Install it with: pip install google-api-python-client"
        ) from exc

    try:

        MediaFileUpload = importlib.import_module(
            "googleapiclient.http"
        ).MediaFileUpload

    except ImportError as exc:

        raise ImportError(
            "google-api-python-client is required for YouTube uploads. "
            "Install it with: pip install google-api-python-client"
        ) from exc

    # --------------------------------------------------------
    # HASHTAGS
    # --------------------------------------------------------

    description = (
        add_hashtags_to_description(
            description,
            title,
            tags,
        )
    )

    # --------------------------------------------------------
    # AUTHENTICATION
    # --------------------------------------------------------

    token_path, secret_path = get_channel_credential_paths(channel)
    print(f"📺 Target YouTube Channel: {channel} (Token: {token_path}, Secret: {secret_path})")

    creds = None

    if os.path.exists(token_path):
        creds = (
            Credentials.from_authorized_user_file(
                token_path,
                SCOPES,
            )
        )

    if not creds or not creds.valid:

        if (
            creds
            and creds.expired
            and creds.refresh_token
        ):
            try:
                creds.refresh(
                    Request()
                )
            except Exception as ref_err:
                print(f"⚠️ YouTube token refresh failed for {channel}: {ref_err}")
                creds = None
                if os.path.exists(token_path):
                    try:
                        os.remove(token_path)
                    except OSError:
                        pass

        if not creds or not creds.valid:

            try:

                InstalledAppFlow = (
                    importlib.import_module(
                        "google_auth_oauthlib.flow"
                    ).InstalledAppFlow
                )

            except ImportError as exc:

                raise ImportError(
                    "google-auth-oauthlib is required for "
                    "YouTube authentication. "
                    "Install it with: "
                    "pip install google-auth-oauthlib"
                ) from exc

            if not os.path.exists(secret_path):
                raise FileNotFoundError(
                    f"{secret_path} not found. Cannot authenticate YouTube for {channel}."
                )

            flow = (
                InstalledAppFlow.from_client_secrets_file(
                    secret_path,
                    SCOPES,
                )
            )

            creds = flow.run_local_server(
                port=0
            )

        if creds and creds.valid:
            with open(
                token_path,
                "w",
                encoding="utf-8",
            ) as token:

                token.write(
                    creds.to_json()
                )

    # --------------------------------------------------------
    # YOUTUBE CLIENT
    # --------------------------------------------------------

    youtube = build(
        "youtube",
        "v3",
        credentials=creds,
    )

    # --------------------------------------------------------
    # UPLOAD
    # --------------------------------------------------------

    request = youtube.videos().insert(

        part="snippet,status",

        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "25",
            },

            "status": {
                "privacyStatus": privacy,
            },
        },

        media_body=MediaFileUpload(
            video_file,
            chunksize=-1,
            resumable=True,
        ),
    )

    print()
    print("=" * 60)
    print("YOUTUBE UPLOAD")
    print("=" * 60)

    print(
        "Title:",
        title,
    )

    print(
        "Privacy:",
        privacy,
    )

    print(
        "Hashtags:",
        " ".join(
            create_hashtags(
                title,
                tags,
            )
        ),
    )

    print()
    print("Uploading...")

    response = None

    while response is None:

        status, response = (
            request.next_chunk()
        )

        if status:

            print(
                f"{int(status.progress() * 100)}% Uploaded"
            )

    video_id = response["id"]

    print()
    print(
        "Upload Complete!"
    )

    print(
        "Video ID:",
        video_id,
    )

    print(
        "Privacy:",
        privacy,
    )

    # --------------------------------------------------------
    # CUSTOM THUMBNAIL
    # --------------------------------------------------------

    thumbnail_file = (
        "output/thumbnail.jpg"
    )

    if os.path.exists(
        thumbnail_file
    ):

        try:

            thumbnail_request = (
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(
                        thumbnail_file,
                        mimetype="image/jpeg",
                    ),
                )
            )

            thumbnail_request.execute()

            print(
                "✅ Custom thumbnail uploaded."
            )

        except Exception as exc:

            print(
                "⚠️ Thumbnail upload failed:"
            )

            print(exc)

    else:

        print(
            "⚠️ Thumbnail file not found:",
            thumbnail_file,
        )

    # --------------------------------------------------------
    # SAVE UPLOAD RECORD
    # --------------------------------------------------------

    uploaded_videos[title] = (
        video_id
    )

    save_uploaded_videos(
        uploaded_videos
    )

    print(
        "Upload record saved."
    )

    # --------------------------------------------------------
    # RETURNING-VIEWER CTA / END-SCREEN LINKING (ROADMAP ITEM 10)
    # --------------------------------------------------------
    link_end_screen_or_related_video(
        youtube,
        video_id,
        current_title=title,
        current_tags=tags,
        current_description=description,
    )

    # --------------------------------------------------------
    # CHECK YOUTUBE PROCESSING
    # --------------------------------------------------------

    print()
    print(
        "Checking YouTube processing status..."
    )

    print_video_status(
        youtube,
        video_id,
    )

    return video_id


# ============================================================
# PROGRAMMATIC END-SCREEN / RETURNING-VIEWER LINKING
# ============================================================

def link_end_screen_or_related_video(
    youtube,
    video_id,
    current_title="",
    current_tags=None,
    current_description="",
):
    """
    Item 10: Returning-Viewer CTA / End-Screen Linking.
    Programmatically links the channel's most recent or related past video
    to improve returning viewer retention (CTR / AVD).

    1. Discovers the channel's most recent / related past video via YouTube Data API
       (or local upload registry fallback).
    2. Updates the uploaded video's description with 'Watch Next / Related Video' CTA.
    3. Programmatically attempts to place a pinned top-level comment linking to the past video.
    4. Handles Shorts limitations (where interactive 20-second end-screen elements are
       restricted by YouTube) with clean, non-blocking fallbacks.
    """
    print()
    print("=" * 60)
    print("RETURNING-VIEWER CTA / END-SCREEN LINKING")
    print("=" * 60)

    related_video_id = None
    related_video_title = None

    # Step 1: Query YouTube API for channel's recent uploads
    try:
        if youtube is not None:
            res = youtube.search().list(
                part="snippet",
                forMine=True,
                type="video",
                order="date",
                maxResults=10,
            ).execute()

            for item in res.get("items", []):
                cand_id = item.get("id", {}).get("videoId")
                if cand_id and cand_id != video_id:
                    related_video_id = cand_id
                    related_video_title = item.get("snippet", {}).get("title", "")
                    print(f"🎯 Found recent channel video via API: {related_video_id} ('{related_video_title}')")
                    break
    except Exception as api_err:
        print(f"ℹ️ YouTube API search check: {api_err}")

    # Step 2: Fallback to uploaded_videos registry if API didn't return a past video
    if not related_video_id:
        uploaded_records = load_uploaded_videos()
        for prev_t, prev_id in reversed(list(uploaded_records.items())):
            if prev_id != video_id:
                related_video_id = prev_id
                related_video_title = prev_t
                print(f"📁 Found recent channel video via local registry: {related_video_id} ('{related_video_title}')")
                break

    if not related_video_id:
        print("ℹ️ No previous uploaded videos found to link as returning-viewer CTA.")
        return {"status": "none"}

    watch_url = f"https://youtu.be/{related_video_id}"
    print(f"🔗 Linking Returning-Viewer CTA: {watch_url}")

    # Step 3: Update video description with Returning-Viewer / End-Screen Watch Next link
    if youtube is not None:
        try:
            vid_resp = youtube.videos().list(part="snippet", id=video_id).execute()
            items = vid_resp.get("items", [])
            if items:
                snippet = items[0]["snippet"]
                desc = snippet.get("description", "")
                cta_line = f"\n\n👉 Watch Next / Related: {watch_url}\n🔔 Don't forget to Like & Subscribe for more Telugu Tech updates!\n"
                if watch_url not in desc:
                    snippet["description"] = desc.strip() + cta_line
                    youtube.videos().update(
                        part="snippet",
                        body={
                            "id": video_id,
                            "snippet": snippet,
                        },
                    ).execute()
                    print("✅ Updated video description with Watch Next link.")
        except Exception as desc_err:
            print(f"ℹ️ Video description update notice: {desc_err}")

        # Step 4: Add engaging pinned comment with related video link
        try:
            comment_text = (
                f"🔥 Loved this video? Watch our next recommended video here: {watch_url}\n"
                f"👍 Like, Share & Subscribe for daily Telugu Tech updates!"
            )
            youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {
                                "textOriginal": comment_text
                            }
                        }
                    }
                }
            ).execute()
            print("✅ Added returning-viewer CTA top-level comment.")
        except Exception as cmt_err:
            print(f"ℹ️ Returning-viewer comment notice (Shorts or API permissions restricted): {cmt_err}")

    return {
        "status": "success",
        "related_video_id": related_video_id,
        "related_video_title": related_video_title,
        "watch_url": watch_url,
    }


from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import os
import json

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

UPLOAD_LOG = "output/uploaded_videos.json"


def load_uploaded_videos():

    if os.path.exists(UPLOAD_LOG):

        try:
            with open(UPLOAD_LOG, "r", encoding="utf-8") as f:
                return json.load(f)

        except Exception:
            return {}

    return {}


def save_uploaded_videos(data):

    os.makedirs("output", exist_ok=True)

    with open(UPLOAD_LOG, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def upload_video(video_file, title, description, tags, privacy="private"):

    uploaded_videos = load_uploaded_videos()

    # Prevent duplicate upload based on title
    if title in uploaded_videos:

        print("Video already uploaded.")
        print("Existing Video ID:", uploaded_videos[title])

        return uploaded_videos[title]

    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json",
            SCOPES
        )

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:

            creds.refresh(Request())

        else:

            flow = InstalledAppFlow.from_client_secrets_file(
                "client_secret.json",
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        with open("token.json", "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    youtube = build(
        "youtube",
        "v3",
        credentials=creds
    )

    request = youtube.videos().insert(

        part="snippet,status",

        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "25"
            },

            "status": {
                "privacyStatus": privacy
            }
        },

        media_body=MediaFileUpload(
            video_file,
            chunksize=-1,
            resumable=True
        )
    )

    print("Uploading...")

    response = None

    while response is None:

        status, response = request.next_chunk()

        if status:
            print(
                f"{int(status.progress() * 100)}% Uploaded"
            )

    video_id = response["id"]

    print("Upload Complete!")
    print("Video ID:", video_id)

    # Save upload record
    uploaded_videos[title] = video_id

    save_uploaded_videos(uploaded_videos)

    print("Upload record saved.")

    return video_id
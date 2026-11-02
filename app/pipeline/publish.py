"""Stage 7: publish the final MP4 to YouTube via the Data API v3."""
from __future__ import annotations

from pathlib import Path

from ..config import get_settings
from ..logging_setup import log

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def upload_to_youtube(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str] | None = None,
    thumbnail: Path | None = None,
) -> dict:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    settings = get_settings()
    flow = InstalledAppFlow.from_client_secrets_file(
        str(settings.youtube_secrets_path), SCOPES
    )
    credentials = flow.run_local_server(port=0)
    youtube = build("youtube", "v3", credentials=credentials)

    body = {
        "snippet": {
            "title": title[:95],
            "description": description[:4900],
            "tags": tags or ["education", "flowchart", "tutorial", "automation"],
            "categoryId": "27",  # Education
        },
        "status": {"privacyStatus": settings.youtube_privacy},
    }

    media = MediaFileUpload(
        str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4"
    )
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )
    response = request.execute()
    video_id = response["id"]

    # Best-effort custom thumbnail. Requires the account to be verified and the
    # broader youtube.force-ssl scope; if it isn't granted we don't want to fail
    # the whole publish, so we log and continue.
    thumbnail_set = False
    if thumbnail is not None and Path(thumbnail).exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail)),
            ).execute()
            thumbnail_set = True
        except Exception as e:  # noqa: BLE001
            log.bind(task="publish").warning(f"thumbnail not set: {e}")

    return {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "privacy": settings.youtube_privacy,
        "thumbnail_set": thumbnail_set,
    }

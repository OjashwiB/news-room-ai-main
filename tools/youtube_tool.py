from langchain.tools import tool
from typing import Optional, List
import logging
import json
import os
from pathlib import Path
from config.settings import settings

logger = logging.getLogger(__name__)


def _get_youtube_service():
    """Build an authenticated YouTube API service using OAuth2."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        import pickle

        # youtube.force-ssl covers uploads, thumbnails, and playlist management.
        # If you have an existing credentials/youtube_token.pickle, delete it and
        # re-authenticate once — the new scope requires a fresh token.
        SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
        token_path = Path("credentials/youtube_token.pickle")
        creds = None

        if token_path.exists():
            with open(token_path, "rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    settings.YOUTUBE_CLIENT_SECRETS_PATH, SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(token_path, "wb") as f:
                pickle.dump(creds, f)

        return build("youtube", "v3", credentials=creds)

    except Exception as e:
        raise RuntimeError(f"Failed to authenticate with YouTube: {e}")


@tool
def youtube_upload_video(
    video_file_path: str,
    title: str,
    description: str,
    tags: Optional[str] = None,
    category_id: Optional[str] = "25",
    privacy_status: Optional[str] = "unlisted",
) -> str:
    """
    Upload a video file to YouTube.

    Args:
        video_file_path: Local path to the MP4 file
        title: YouTube video title (max 100 chars)
        description: YouTube video description
        tags: Comma-separated list of tags (e.g. "news,iran,shipping")
        category_id: YouTube category ID — 25 = News & Politics (default)
        privacy_status: "public", "unlisted", or "private" (default: unlisted)

    Returns:
        JSON string with youtube_video_id and youtube_url, or error
    """
    try:
        from googleapiclient.http import MediaFileUpload

        if not Path(video_file_path).exists():
            return json.dumps({"error": f"Video file not found: {video_file_path}"})

        youtube = _get_youtube_service()

        tag_list = [t.strip() for t in tags.split(",")] if tags else []

        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tag_list,
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            video_file_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024 * 8,  # 8MB chunks
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        logger.info(f"[youtube_upload] Uploading: {title}")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"[youtube_upload] Progress: {int(status.progress() * 100)}%")

        video_id = response.get("id")
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info(f"[youtube_upload] Complete: {youtube_url}")

        return json.dumps({
            "youtube_video_id": video_id,
            "youtube_url": youtube_url,
            "title": title,
            "privacy_status": privacy_status,
        })

    except Exception as e:
        logger.error(f"[youtube_upload] Error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


@tool
def youtube_set_thumbnail(
    video_id: str,
    thumbnail_url: str,
) -> str:
    """
    Set a thumbnail on a YouTube video by downloading it from a URL.

    Args:
        video_id: The YouTube video ID
        thumbnail_url: URL of the thumbnail image to use

    Returns:
        Success message or error
    """
    import requests as req
    import tempfile

    try:
        youtube = _get_youtube_service()

        # Download the thumbnail to a temp file
        img_response = req.get(thumbnail_url, timeout=15)
        if not img_response.ok:
            return f"Error downloading thumbnail: HTTP {img_response.status_code}"

        # Determine MIME type from URL extension — CDN may return binary/octet-stream
        url_lower = thumbnail_url.lower().split("?")[0]
        if url_lower.endswith(".png"):
            mime_type = "image/png"
            suffix = ".png"
        elif url_lower.endswith(".webp"):
            mime_type = "image/webp"
            suffix = ".webp"
        else:
            mime_type = "image/jpeg"
            suffix = ".jpg"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(img_response.content)
            tmp_path = tmp.name

        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(tmp_path, mimetype=mime_type)
        youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
        os.unlink(tmp_path)

        logger.info(f"[youtube_thumbnail] Set thumbnail for video {video_id}")
        return json.dumps({"success": True, "video_id": video_id, "thumbnail_set": True})

    except Exception as e:
        logger.error(f"[youtube_thumbnail] Error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


def add_video_to_playlist(video_id: str, playlist_id: str) -> dict:
    """
    Add a YouTube video to a playlist.
    Returns {"success": True, "playlist_id": ..., "video_id": ...} or {"error": ...}.
    Called directly (not as a langchain tool) — playlist management is infrastructure,
    not an LLM decision.
    """
    try:
        youtube = _get_youtube_service()
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        logger.info(f"[youtube_playlist] Added {video_id} to playlist {playlist_id}")
        return {"success": True, "playlist_id": playlist_id, "video_id": video_id}
    except Exception as e:
        logger.warning(f"[youtube_playlist] Failed to add {video_id} to {playlist_id}: {e}")
        return {"error": str(e), "playlist_id": playlist_id}

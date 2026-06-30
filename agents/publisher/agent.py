import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import asyncio
import json
import logging
import re
from langchain.agents import create_openai_functions_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from agents.registry import BaseAgent, AgentInfo
from agents.publisher.prompts import PUBLISHER_PROMPT
from tools.file_operations_tool import file_operations_tool
from config.settings import settings

logger = logging.getLogger(__name__)

_MEDIA_DIR_DEFAULT = "./output/media"


class Agent(BaseAgent):
    """Publisher — reads the video package, uploads to YouTube exactly once, sets thumbnail."""

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.1, openai_api_key=settings.OPENAI_API_KEY)
        # LLM only gets file_operations_tool to read the package — no upload tool
        self.tools = [file_operations_tool]
        prompt = ChatPromptTemplate.from_messages([
            ("system", PUBLISHER_PROMPT),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        agent = create_openai_functions_agent(self.llm, self.tools, prompt)
        self.executor = AgentExecutor(agent=agent, tools=self.tools, verbose=True, max_iterations=5)
        logger.info("Publisher agent initialized")

    def get_info(self) -> AgentInfo:
        return AgentInfo(
            name="publisher",
            display_name="Publisher",
            description="Uploads finished video to YouTube and sets title, description, thumbnail",
            version="1.0.0",
            module_path="agents.publisher.agent",
            parent_agent="executive_producer",
        )

    def _parse_media_dir(self, message: str) -> str:
        m = re.search(r"MEDIA_DIR:\s*(\S+)", message)
        return m.group(1) if m else _MEDIA_DIR_DEFAULT

    def _parse_show_name(self, message: str) -> str:
        m = re.search(r"SHOW_NAME:\s*(.+?)(?:\n|$)", message)
        return m.group(1).strip() if m else ""

    def _upload_sync(self, video_file: str, title: str, description: str,
                     tags: list, privacy: str) -> dict:
        """Synchronous YouTube upload — called via asyncio.to_thread."""
        from googleapiclient.http import MediaFileUpload
        from tools.youtube_tool import _get_youtube_service

        if not Path(video_file).exists():
            return {"error": f"Video file not found: {video_file}"}

        youtube = _get_youtube_service()
        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags,
                "categoryId": "25",  # News & Politics
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(video_file, mimetype="video/mp4", resumable=True,
                                chunksize=1024 * 1024 * 8)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        logger.info(f"[publisher] Uploading: {title}")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"[publisher] Upload progress: {int(status.progress() * 100)}%")

        video_id = response.get("id")
        url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info(f"[publisher] Upload complete: {url}")
        return {"youtube_video_id": video_id, "youtube_url": url}

    def _add_to_playlists_sync(self, video_id: str, playlist_ids: list[str]) -> list[dict]:
        """Add the video to each playlist. Best-effort — failures are logged but don't stop publishing."""
        from tools.youtube_tool import add_video_to_playlist
        results = []
        for pid in playlist_ids:
            result = add_video_to_playlist(video_id, pid)
            results.append(result)
        return results

    def _set_thumbnail_sync(self, video_id: str, thumbnail_url: str) -> dict:
        """Synchronous thumbnail set — called via asyncio.to_thread."""
        import requests as req
        import tempfile
        import os
        from googleapiclient.http import MediaFileUpload
        from tools.youtube_tool import _get_youtube_service

        try:
            img_response = req.get(thumbnail_url, timeout=15)
            if not img_response.ok:
                return {"error": f"HTTP {img_response.status_code} downloading thumbnail"}

            url_lower = thumbnail_url.lower().split("?")[0]
            if url_lower.endswith(".png"):
                mime_type, suffix = "image/png", ".png"
            elif url_lower.endswith(".webp"):
                mime_type, suffix = "image/webp", ".webp"
            else:
                mime_type, suffix = "image/jpeg", ".jpg"

            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(img_response.content)
                tmp_path = tmp.name

            youtube = _get_youtube_service()
            media = MediaFileUpload(tmp_path, mimetype=mime_type)
            youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
            os.unlink(tmp_path)
            logger.info(f"[publisher] Thumbnail set for {video_id}")
            return {"success": True}
        except Exception as e:
            logger.warning(f"[publisher] Thumbnail error: {e}")
            return {"error": str(e)}

    async def process_message(self, message: str, context: dict = None) -> dict:
        try:
            media_dir = self._parse_media_dir(message)
            show_name = self._parse_show_name(message)

            # Guard: bail out early if this package was already uploaded
            pkg_path = Path(media_dir) / "video_package.json"
            if pkg_path.exists():
                try:
                    existing = json.loads(pkg_path.read_text(encoding="utf-8"))
                    if existing.get("youtube_video_id"):
                        yt_id = existing["youtube_video_id"]
                        url = f"https://www.youtube.com/watch?v={yt_id}"
                        logger.info(f"[publisher] Already uploaded — skipping. {url}")
                        return {
                            "success": True,
                            "response": f"Already uploaded to YouTube — skipping duplicate upload.\nURL: {url}\nVideo ID: {yt_id}",
                            "agent": "publisher",
                            "youtube_url": url,
                            "youtube_video_id": yt_id,
                        }
                except Exception:
                    pass

            # Step 1: LLM reads video_package.json and returns structured metadata as JSON
            result = await asyncio.to_thread(
                self.executor.invoke,
                {"input": message + f"\n\nRead video_package.json from directory: {media_dir}\nReturn the upload metadata as JSON with keys: video_file, title, description, tags (list), privacy_status, thumbnail_url.", "chat_history": []}
            )
            llm_output = result.get("output", "")

            # Step 2: Parse metadata from LLM output
            metadata = self._extract_metadata(llm_output, media_dir=media_dir)
            if "error" in metadata:
                return {"success": False, "response": f"Publisher failed to read package: {metadata['error']}", "agent": "publisher"}

            # Title = story subject only — strip any newsroom name or show-type prefix
            raw = metadata.get("title", "News Video")
            newsroom = settings.NEWSROOM_NAME
            bare = raw[len(newsroom):].lstrip(" |:—-").strip() if raw.startswith(newsroom) else raw
            bare = re.sub(
                r'^(?:Breaking News|Special Report|Morning Report|Evening News|'
                r'Weekend Roundup|Entertainment Weekly)\s*[:|—\-]\s*',
                '', bare, flags=re.IGNORECASE,
            ).strip()
            metadata["title"] = bare or "News Video"

            video_file = metadata.get("video_file", "")
            title = metadata.get("title", "Defy Logic News Video")
            description = metadata.get("description", "")
            tags = metadata.get("tags", [])
            privacy = metadata.get("privacy_status", "unlisted")
            thumbnail_url = metadata.get("thumbnail_url", "")

            # Step 3: Upload exactly once — native Python, not LLM
            upload_result = await asyncio.to_thread(
                self._upload_sync, video_file, title, description, tags, privacy
            )

            if "error" in upload_result:
                return {"success": False, "response": f"YouTube upload failed: {upload_result['error']}", "agent": "publisher"}

            youtube_url = upload_result["youtube_url"]
            youtube_video_id = upload_result["youtube_video_id"]

            # Mark the package as uploaded so re-runs don't duplicate it
            try:
                pkg_path = Path(media_dir) / "video_package.json"
                if pkg_path.exists():
                    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
                    pkg["youtube_video_id"] = youtube_video_id
                    pkg["youtube_url"] = youtube_url
                    pkg_path.write_text(json.dumps(pkg, indent=2), encoding="utf-8")
            except Exception as e:
                logger.warning(f"[publisher] Could not mark package as uploaded: {e}")

            # Step 4: Set thumbnail (best-effort)
            thumb_result = {}
            if thumbnail_url:
                thumb_result = await asyncio.to_thread(
                    self._set_thumbnail_sync, youtube_video_id, thumbnail_url
                )

            # Step 5: Add to playlists (best-effort)
            playlist_ids = self._parse_playlist_ids(message)
            playlist_results: list[dict] = []
            if playlist_ids:
                playlist_results = await asyncio.to_thread(
                    self._add_to_playlists_sync, youtube_video_id, playlist_ids
                )

            thumb_note = "" if thumb_result.get("success") else f" (thumbnail not set: {thumb_result.get('error', 'unknown')})"

            added = [r["playlist_id"] for r in playlist_results if r.get("success")]
            failed = [r["playlist_id"] for r in playlist_results if "error" in r]
            playlist_note = ""
            if added:
                playlist_note = f"\nPlaylists: added to {len(added)} playlist(s)"
            if failed:
                playlist_note += f" ({len(failed)} failed)"

            return {
                "success": True,
                "response": (
                    f"Published to YouTube successfully.\n"
                    f"Title: {title}\n"
                    f"URL: {youtube_url}\n"
                    f"Video ID: {youtube_video_id}\n"
                    f"Privacy: {privacy}{thumb_note}{playlist_note}"
                ),
                "agent": "publisher",
                "youtube_url": youtube_url,
                "youtube_video_id": youtube_video_id,
                "playlists_added": added,
            }

        except Exception as e:
            logger.error(f"Publisher error: {e}", exc_info=True)
            return {"success": False, "response": f"Publishing failed: {str(e)}", "agent": "publisher"}

    def _parse_playlist_ids(self, message: str) -> list[str]:
        """Extract PLAYLIST_IDS from the step input injected by the Executive Producer."""
        import re
        m = re.search(r"PLAYLIST_IDS:\s*(\[.*?\])", message)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        return []

    def _extract_metadata(self, text: str, media_dir: str = _MEDIA_DIR_DEFAULT) -> dict:
        """Extract upload metadata from LLM output — tries JSON blocks first, then reads package directly."""
        for pattern in [r"```json\s*(\{.*?\})\s*```", r"```\s*(\{.*?\})\s*```", r"(\{[^{}]*\"video_file\"[^{}]*\})"]:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    pass

        # Fallback: read video_package.json directly
        try:
            pkg_path = Path(media_dir) / "video_package.json"
            if pkg_path.exists():
                pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
                return {
                    "video_file": pkg.get("video_file", ""),
                    "title": pkg.get("title", "News Video"),
                    "description": pkg.get("description", "") + f"\n\n{settings.NEWSROOM_NAME}",
                    "tags": pkg.get("tags", []),
                    "privacy_status": "unlisted",
                    "thumbnail_url": pkg.get("thumbnail_url", ""),
                }
        except Exception as e:
            logger.warning(f"[publisher] Fallback package read failed: {e}")

        return {"error": "Could not extract upload metadata from LLM output or video_package.json"}

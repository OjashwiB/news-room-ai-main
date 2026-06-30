import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import asyncio
import json
import re
import logging
import requests
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from agents.registry import BaseAgent, AgentInfo
from tools.heygen_tool import get_heygen_credits, generate_video_multiscene, delete_heygen_asset, prepare_enhanced_background
from config.overlays import get_background_layers
from config.settings import settings

logger = logging.getLogger(__name__)

HEYGEN_BASE_URL = "https://api.heygen.com"
POLL_INTERVAL_SECONDS = 30
MAX_POLL_ATTEMPTS = 120  # 60 minutes max

_active_polls: dict[str, asyncio.Task] = {}


def cancel_poll(video_id: str) -> bool:
    """Cancel an in-progress poll for video_id. Returns True if a task was found and cancelled."""
    task = _active_polls.get(video_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


class Agent(BaseAgent):
    """
    Anchor — cleans the script, resolves [BROLL:] markers to image URLs,
    submits a single- or multi-scene video to HeyGen, then polls until complete.
    """

    def __init__(self):
        from agents.anchor.prompts import ANCHOR_PROMPT
        self._system_prompt = ANCHOR_PROMPT
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.1, openai_api_key=settings.OPENAI_API_KEY)
        logger.info("Anchor agent initialized")

    def get_info(self) -> AgentInfo:
        return AgentInfo(
            name="anchor",
            display_name="Anchor",
            description="Generates AI news anchor video from broadcast script using HeyGen",
            version="2.0.0",
            module_path="agents.anchor.agent",
            parent_agent="executive_producer",
        )

    # ── Script cleaning ──────────────────────────────────────────────────────

    def _clean_script_sync(self, message: str) -> str:
        """Use LLM to strip [GRAPHIC:] / [PAUSE] markers while preserving [BROLL:] markers."""
        response = self.llm.invoke([
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=message),
        ])
        text = response.content.strip()
        # Strip markdown formatting characters that TTS would read aloud.
        # Preserve [BROLL:...] markers verbatim — their URLs contain underscores
        # that must not be stripped by the _+ part of the regex.
        broll_markers: list[str] = []
        def _stash_broll(m: re.Match) -> str:
            broll_markers.append(m.group(0))
            return f"\x00BROLL{len(broll_markers)-1}\x00"
        text = re.sub(r'\[BROLL:[^\]]*\]', _stash_broll, text, flags=re.IGNORECASE)
        text = re.sub(r'\*+|_+|`+|#{1,6}\s*', '', text)
        # Strip any remaining [...] content — catches pronunciation guides like [shee jeen-PEENG],
        # [GRAPHIC:] or [PAUSE] the LLM missed. HeyGen TTS reads brackets literally.
        text = re.sub(r'\[[^\]]*\]', '', text)
        # Remove duplicate newsroom datelines — keep the first and the sign-off (after "I'm").
        # Multi-story scripts can end up with the station name opening each story segment.
        if settings.NEWSROOM_NAME:
            _pat = re.escape(settings.NEWSROOM_NAME)
            _first = [False]
            _snap = text
            def _dedup(m):
                preceding = _snap[:m.start()].strip()[-40:]
                if re.search(r"I'?m\b", preceding, re.IGNORECASE):
                    return m.group(0)  # sign-off — keep
                if not _first[0]:
                    _first[0] = True
                    return m.group(0)  # first dateline — keep
                return ''  # duplicate dateline — strip
            text = re.sub(_pat, _dedup, text, flags=re.IGNORECASE)
        for i, marker in enumerate(broll_markers):
            text = text.replace(f"\x00BROLL{i}\x00", marker)
        return text

    def _regex_clean_script(self, script: str) -> str:
        """Pure-regex cleaner. Strips broadcast-direction markers while preserving [BROLL:] markers exactly."""
        broll_markers: list[str] = []
        def _stash(m: re.Match) -> str:
            broll_markers.append(m.group(0))
            return f"\x00BROLL{len(broll_markers)-1}\x00"
        text = re.sub(r'\[BROLL:[^\]]*\]', _stash, script, flags=re.IGNORECASE)

        # Remove standalone markdown heading lines BEFORE stripping markers, so the text
        # "Introduction" / "Background and Context" etc. is deleted entirely rather than
        # left as a spoken word after the ** or # characters are stripped.
        # Matches lines whose entire content is a markdown heading or bold phrase.
        text = re.sub(r'(?m)^\s*#{1,6}[^\n]+\n?', '', text)           # # Heading
        text = re.sub(r'(?m)^\s*\*\*[^*\n]+\*\*\s*\n?', '', text)     # **Bold heading**

        text = re.sub(r'\[PAUSE\]', ', ', text, flags=re.IGNORECASE)
        text = re.sub(r'\[GRAPHIC:[^\]]*\]', '', text, flags=re.IGNORECASE)
        # Remove any remaining [...] — pronunciation guides, missed directives, etc.
        text = re.sub(r'\[[^\]]*\]', '', text)
        text = re.sub(r'\*+|_+|`+|#{1,6}\s*', '', text)
        text = re.sub(r'  +', ' ', text)
        text = re.sub(r' ,', ',', text)
        text = re.sub(r',,+', ',', text)

        for i, marker in enumerate(broll_markers):
            text = text.replace(f"\x00BROLL{i}\x00", marker)
        return text.strip()

    # ── B-roll parsing ───────────────────────────────────────────────────────

    def _parse_segments(self, script: str) -> list[dict]:
        """
        Split on [BROLL:] markers. Each anchor text segment AFTER a marker is
        paired with that marker's media. Marker content can be:
          "https://... | description"         — pre-sourced image URL
          "https://... | description | video" — pre-sourced video clip URL
          "search query"                      — fallback: anchor will search for an image
        """
        parts = re.split(r'\[BROLL:\s*([^\]]+)\]', script, flags=re.IGNORECASE)
        segments = []
        pending_url = None
        pending_desc = None
        pending_media_type = "image"
        for i, part in enumerate(parts):
            if i % 2 == 1:
                content = part.strip()
                fields = [f.strip() for f in content.split('|')]
                url_part = fields[0]
                desc_part = fields[1] if len(fields) > 1 else ""
                type_hint = fields[2].lower() if len(fields) > 2 else "image"
                if url_part.startswith('http'):
                    pending_url = url_part
                    pending_desc = desc_part or None
                    pending_media_type = "video" if type_hint == "video" else "image"
                else:
                    pending_url = None
                    # When there's no URL, use the description field as the Tavily
                    # search query if it exists — it's more specific than the first field,
                    # which the script writer often fills with literal placeholder text.
                    pending_desc = desc_part if desc_part else url_part
                    pending_media_type = "image"
            else:
                text = part.strip()
                if text:
                    segments.append({
                        "type": "anchor",
                        "script": text,
                        "broll_description": pending_desc,
                        "image_url": pending_url if pending_media_type == "image" else None,
                        "video_url": pending_url if pending_media_type == "video" else None,
                    })
                pending_url = None
                pending_desc = None
                pending_media_type = "image"
        return segments

    _IMAGE_MAGIC = {
        b"\xff\xd8\xff": "jpeg",
        b"\x89PNG": "png",
        b"GIF8": "gif",
        b"RIFF": "webp",  # RIFF....WEBP
        b"\x00\x00\x00": "heic",
    }

    def _is_image_url(self, url: str) -> bool:
        """Confirm the URL points to an actual image via HEAD, then partial GET as fallback."""
        if self._is_placeholder_url(url):
            return False
        hdrs = {"User-Agent": "Mozilla/5.0"}
        try:
            resp = requests.head(url, timeout=6, headers=hdrs, allow_redirects=True)
            ct = resp.headers.get("Content-Type", "").split(";")[0].strip()
            if ct.startswith("image/"):
                return True
            # Some CDNs (Euronews, AP, etc.) return text/html or no type on HEAD.
            # Try a partial GET to read the first few bytes and check magic numbers.
            if resp.status_code in (200, 206, 301, 302, 403, 404):
                pass  # continue to partial-GET below only on uncertain responses
            if resp.status_code == 404:
                return False
        except Exception:
            pass
        try:
            resp = requests.get(
                url, timeout=8, headers={**hdrs, "Range": "bytes=0-511"},
                allow_redirects=True, stream=True,
            )
            if not resp.ok:
                return False
            ct = resp.headers.get("Content-Type", "").split(";")[0].strip()
            if ct.startswith("image/"):
                return True
            # Check magic bytes
            chunk = b""
            for data in resp.iter_content(chunk_size=512):
                chunk += data
                break
            return any(chunk.startswith(magic) for magic in self._IMAGE_MAGIC)
        except Exception:
            return False

    _BLOCKED_DOMAINS = (
        "lookaside.instagram.com", "lookaside.fbsbx.com", "facebook.com",
        "instagram.com", "twitter.com", "x.com", "tiktok.com",
    )

    def _is_placeholder_url(self, url: str) -> bool:
        """Return True if the URL is a hallucinated placeholder or a blocked social-media domain."""
        low = url.lower()
        if any(tok in low for tok in (
            "example", "placeholder", "your-url", "insert-url", "sample-url",
            "exact-url", "from-tool", "url-here", "image-url", "video-url",
        )):
            return True
        return any(domain in low for domain in self._BLOCKED_DOMAINS)

    def _is_video_url(self, url: str) -> bool:
        """HEAD request to confirm the URL points to a downloadable video file."""
        if self._is_placeholder_url(url):
            return False
        try:
            hdrs = {"User-Agent": "Mozilla/5.0"}
            if "pixabay.com" in url:
                hdrs["Referer"] = "https://pixabay.com/"
            resp = requests.head(url, timeout=8, headers=hdrs, allow_redirects=True)
            if not resp.ok:
                logger.debug(f"[anchor] _is_video_url HEAD {resp.status_code}: {url[:80]}")
                return False
            ct = resp.headers.get("Content-Type", "").split(";")[0].strip()
            if ct.startswith("video/") or ct == "application/octet-stream":
                return True
            # Some CDNs return generic content-type; trust extension only on 2xx
            path = url.split("?")[0].lower()
            return any(path.endswith(ext) for ext in (".mp4", ".mov", ".webm", ".avi"))
        except Exception:
            return False

    def _search_image_sync(self, query: str, exclude: set[str] | None = None) -> str | None:
        """Fetch the first usable image URL for a query via Tavily, skipping excluded URLs."""
        if not settings.TAVILY_API_KEY:
            return None
        try:
            payload = {
                "api_key": settings.TAVILY_API_KEY,
                "query": query,
                "topic": "news",
                "search_depth": "basic",
                "include_images": True,
                "include_image_descriptions": False,
                "max_results": 5,
            }
            resp = requests.post("https://api.tavily.com/search", json=payload, timeout=15)
            if not resp.ok:
                return None
            images = resp.json().get("images", [])
            for img in images:
                url = img.get("url") if isinstance(img, dict) else img
                if url and not self._is_placeholder_url(url) and url not in (exclude or set()):
                    return url
            return None
        except Exception as e:
            logger.warning(f"[anchor] Image search failed for '{query}': {e}")
            return None

    async def _resolve_broll_media(self, segments: list[dict]) -> list[dict]:
        """
        Validate every b-roll segment's media URL.
        - Video URLs: validated via HEAD request / extension check.
        - Image URLs: validated via HEAD or partial-GET; invalid ones fall back to Tavily search.
        - Description-only segments: Tavily image search.
        Tracks already-assigned image URLs to avoid returning the same photo for every segment.
        """
        resolved = []
        used_image_urls: set[str] = set()

        for seg in segments:
            desc = seg.get("broll_description")
            video_url = seg.get("video_url")
            image_url = seg.get("image_url")

            if video_url:
                valid = await asyncio.to_thread(self._is_video_url, video_url)
                if valid:
                    logger.info(f"[anchor] B-roll video OK: '{desc}' → {video_url[:80]}")
                else:
                    logger.warning(f"[anchor] Video URL invalid — falling back to image search: {video_url[:80]}")
                    seg["video_url"] = None
                    video_url = None

            if not video_url and image_url:
                valid = await asyncio.to_thread(self._is_image_url, image_url)
                if valid:
                    logger.info(f"[anchor] B-roll image OK: '{desc}' → {image_url[:80]}")
                    used_image_urls.add(image_url)
                else:
                    logger.warning(f"[anchor] Image URL invalid — falling back to search: {image_url[:80]}")
                    seg["image_url"] = None
                    image_url = None

            if not video_url and not image_url and desc:
                found = await asyncio.to_thread(self._search_image_sync, desc, used_image_urls)
                if found:
                    seg["image_url"] = found
                    used_image_urls.add(found)
                    logger.info(f"[anchor] B-roll image searched: '{desc}' → {found}")
                else:
                    logger.warning(f"[anchor] No media found for '{desc}' — using studio background")

            resolved.append(seg)
        return resolved

    # ── HeyGen param extraction ──────────────────────────────────────────────

    def _extract_heygen_params(self, message: str) -> tuple[str, str, str, str, str, str, str, str]:
        """Parse HeyGen params injected by the executive producer."""
        def find(pattern):
            m = re.search(pattern, message, re.IGNORECASE)
            return m.group(1).strip() if m else ""

        avatar_id     = find(r'AVATAR ID[ \t]*:[ \t]*([^\n]+)')
        voice_id      = find(r'VOICE ID[ \t]*:[ \t]*([^\n]+)')
        bg_id         = find(r'BACKGROUND ASSET ID[ \t]*:[ \t]*([^\n]+)')
        voice_emotion = find(r'VOICE EMOTION[ \t]*:[ \t]*([^\n]+)')
        talking_style = find(r'TALKING STYLE[ \t]*:[ \t]*([^\n]+)')
        expression    = find(r'EXPRESSION[ \t]*:[ \t]*([^\n]+)')
        pip_position  = find(r'PIP POSITION[ \t]*:[ \t]*([^\n]+)') or "left"
        desk_slug     = find(r'DESK_SLUG[ \t]*:[ \t]*([^\n]+)')

        return (
            avatar_id     or settings.HEYGEN_AVATAR_ID,
            voice_id      or settings.HEYGEN_VOICE_ID,
            bg_id         or "f6fa4085043140deaba8258a96233036",
            voice_emotion,
            talking_style,
            expression,
            pip_position,
            desk_slug,
        )

    # ── HeyGen polling ───────────────────────────────────────────────────────

    def _check_status_sync(self, video_id: str) -> dict:
        try:
            response = requests.get(
                f"{HEYGEN_BASE_URL}/v1/video_status.get",
                headers={"x-api-key": settings.HEYGEN_API_KEY},
                params={"video_id": video_id},
                timeout=30,
            )
            if not response.ok:
                return {"error": f"HTTP {response.status_code}: {response.text[:200]}"}
            data = response.json().get("data", {})
            return {
                "video_id": video_id,
                "status": data.get("status", "unknown"),
                "video_url": data.get("video_url"),
                "thumbnail_url": data.get("thumbnail_url"),
            }
        except Exception as e:
            logger.error(f"[heygen] status check error: {e}", exc_info=True)
            return {"error": str(e)}

    async def _poll_until_complete(self, video_id: str) -> dict:
        logger.info(f"[heygen] Waiting 15s before first status check for {video_id}...")
        await asyncio.sleep(15)

        consecutive_errors = 0
        for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
            logger.info(f"[heygen] Poll {attempt}/{MAX_POLL_ATTEMPTS} for {video_id}")
            result = await asyncio.to_thread(self._check_status_sync, video_id)

            if "error" in result:
                consecutive_errors += 1
                logger.warning(f"[heygen] Poll error ({consecutive_errors}/5): {result['error']}")
                if consecutive_errors >= 5:
                    return result
                if attempt < MAX_POLL_ATTEMPTS:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            consecutive_errors = 0
            status = result.get("status", "unknown")
            logger.info(f"[heygen] Video {video_id} status: {status}")

            if status == "completed":
                return result
            if status == "failed":
                return {"error": f"HeyGen video generation failed for {video_id}", "video_id": video_id}

            if attempt < MAX_POLL_ATTEMPTS:
                logger.info(f"[heygen] Status '{status}', waiting {POLL_INTERVAL_SECONDS}s...")
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

        return {"error": f"Timed out waiting for video {video_id} after {MAX_POLL_ATTEMPTS} attempts"}

    # ── Main entry point ─────────────────────────────────────────────────────

    async def process_message(self, message: str, context: dict = None) -> dict:
        try:
            # Step 0: Credit check
            credits_before = None
            try:
                credits_before = await asyncio.to_thread(get_heygen_credits)
                minimum = settings.HEYGEN_CREDIT_MINIMUM
                logger.info(f"[anchor] HeyGen credits: {credits_before} (min: {minimum})")
                if credits_before < minimum:
                    msg = (
                        f"HeyGen credit balance too low: {credits_before} remaining "
                        f"(minimum: {minimum}). Please top up your HeyGen account."
                    )
                    logger.error(f"[anchor] {msg}")
                    return {"success": False, "response": msg, "agent": "anchor"}
            except Exception as credit_err:
                logger.warning(f"[anchor] Could not verify HeyGen credits: {credit_err}")

            # Step 1: Extract HeyGen params from the message
            avatar_id, voice_id, bg_id, voice_emotion, talking_style, expression, pip_position, desk_slug = self._extract_heygen_params(message)

            # Step 1b: Apply background layers to the studio background
            bg_layers = get_background_layers(desk_slug)
            enhanced_bg_id, enhanced_bg_bytes, enhanced_bg_fresh, enhanced_bg_cache = await asyncio.to_thread(
                prepare_enhanced_background, bg_id, bg_layers
            )
            if enhanced_bg_id != bg_id:
                logger.info(f"[anchor] Enhanced background ready: {enhanced_bg_id}")
            bg_id = enhanced_bg_id  # use for all scenes going forward

            # Step 2: Extract the broadcast script from EP context, then clean it.
            # Stop extraction before the HeyGen params / "Now perform your role" instruction
            # so the LLM cleaner only sees the script text and doesn't hallucinate.
            _script_boundary = r'(?=\n\nNow perform your role|\n\nANCHOR NAME:|\n\nAVATAR ID:|===|\Z)'
            script_match = re.search(
                r'=== SCRIPT ===\s*(.*?)' + _script_boundary,
                message, re.DOTALL | re.IGNORECASE,
            )
            if not script_match:
                script_match = re.search(
                    r'=== SCRIPT_WRITER OUTPUT ===\s*(.*?)' + _script_boundary,
                    message, re.DOTALL | re.IGNORECASE,
                )
            script_to_clean = script_match.group(1).strip() if script_match else message
            if script_match:
                logger.info(f"[anchor] Extracted script ({len(script_to_clean)} chars): {script_to_clean[:120]!r}")
            else:
                logger.warning("[anchor] No script section found — using full message")
            cleaned = self._regex_clean_script(script_to_clean)
            logger.info(f"[anchor] Cleaned script ({len(cleaned)} chars): {cleaned[:120]!r}")

            # Step 3: Parse [BROLL:] markers into segments
            segments = self._parse_segments(cleaned)
            has_broll = any(s.get("broll_description") for s in segments)
            n_studio = sum(1 for s in segments if not s.get("broll_description"))
            n_images = sum(1 for s in segments if s.get("image_url"))
            n_videos = sum(1 for s in segments if s.get("video_url"))
            n_search = sum(1 for s in segments if s.get("broll_description") and not s.get("image_url") and not s.get("video_url"))
            logger.info(f"[anchor] Segments: {len(segments)} ({n_studio} studio, {n_images} image b-roll, {n_videos} video b-roll, {n_search} to search)")

            # Step 4: Resolve b-roll media URLs
            if has_broll:
                segments = await self._resolve_broll_media(segments)

            # Step 5: Submit to HeyGen
            title = re.search(r'TOPIC[ \t]*:[ \t]*([^\n]+)', message, re.IGNORECASE)
            title = title.group(1).strip() if title else "News Segment"

            submit_result = await asyncio.to_thread(
                generate_video_multiscene,
                segments, avatar_id, voice_id, bg_id, title,
                voice_emotion, talking_style, expression, pip_position,
                enhanced_bg_bytes,
            )

            if not submit_result.get("video_id"):
                err = submit_result.get("error", "Unknown error submitting to HeyGen")
                logger.error(f"[anchor] Submit failed: {err}")
                return {"success": False, "response": f"Anchor FAILED: {err}", "agent": "anchor"}

            video_id = submit_result["video_id"]
            scene_count = submit_result.get("scene_count", 1)
            logger.info(f"[anchor] Submitted. video_id={video_id}, scenes={scene_count}. Polling...")

            # Step 6: Poll until complete
            poll_task = asyncio.create_task(self._poll_until_complete(video_id))
            _active_polls[video_id] = poll_task
            try:
                poll_result = await poll_task
            except asyncio.CancelledError:
                logger.info(f"[anchor] Poll for {video_id} cancelled")
                return {
                    "success": False,
                    "response": f"Polling cancelled for video {video_id}. It may still be rendering in HeyGen.",
                    "agent": "anchor",
                    "video_id": video_id,
                }
            finally:
                _active_polls.pop(video_id, None)

            if "error" in poll_result:
                return {
                    "success": False,
                    "response": f"Anchor video polling FAILED: {poll_result['error']}",
                    "agent": "anchor",
                    "video_id": video_id,
                }

            # Step 7: Clean up temporary composite assets from HeyGen
            uploaded_composites = list(submit_result.get("uploaded_composites", []))
            if enhanced_bg_fresh and enhanced_bg_cache:
                # Asset cache is cleared so next render re-uploads; bytes cache is kept
                # so FFmpeg compositing only runs once.
                uploaded_composites.append({"asset_id": enhanced_bg_id, "cache_path": enhanced_bg_cache})
            if uploaded_composites:
                logger.info(f"[anchor] Cleaning up {len(uploaded_composites)} uploaded composite asset(s)...")
                for entry in uploaded_composites:
                    aid = entry.get("asset_id")
                    cpath = entry.get("cache_path")
                    if aid:
                        deleted = await asyncio.to_thread(delete_heygen_asset, aid)
                        if deleted and cpath:
                            try:
                                from pathlib import Path as _Path
                                _Path(cpath).unlink(missing_ok=True)
                                logger.info(f"[anchor] Removed composite cache: {cpath}")
                            except Exception:
                                pass

            video_url = poll_result.get("video_url", "")
            thumbnail_url = poll_result.get("thumbnail_url", "")

            # Log credit cost
            credits_used_str = ""
            if credits_before is not None:
                try:
                    credits_after = await asyncio.to_thread(get_heygen_credits)
                    credits_used = credits_before - credits_after
                    logger.info(f"[anchor] Credits used: {credits_used} (before: {credits_before}, after: {credits_after})")
                    credits_used_str = f"\ncredits_used: {credits_used} (balance: {credits_after} remaining)"
                except Exception:
                    pass

            logger.info(f"[anchor] Video ready: {video_url}")

            return {
                "success": True,
                "response": (
                    f"Anchor video generation complete.\n"
                    f"video_id: {video_id}\n"
                    f"video_url: {video_url}\n"
                    f"thumbnail_url: {thumbnail_url}\n"
                    f"scenes: {scene_count}"
                    f"{credits_used_str}"
                ),
                "agent": "anchor",
                "video_id": video_id,
                "video_url": video_url,
                "thumbnail_url": thumbnail_url,
            }

        except Exception as e:
            logger.error(f"Anchor error: {e}", exc_info=True)
            return {"success": False, "response": f"Anchor video generation FAILED: {str(e)}", "agent": "anchor"}

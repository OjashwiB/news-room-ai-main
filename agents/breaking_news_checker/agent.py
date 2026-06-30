"""
Breaking News Checker — polls current headlines every 30 minutes and fires an
emergency production if a qualifying story is found that hasn't been covered recently.

Triggered via the [BREAK-CHECK] prefix routed through the newsroom /produce endpoint.
"""

import asyncio
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from agents.registry import BaseAgent, AgentInfo
from agents.breaking_news_checker.prompts import BREAKING_NEWS_SYSTEM_PROMPT, BREAKING_NEWS_EVAL_PROMPT
from config.settings import settings
from tools.breaking_news_log import get_recent_for_dedup, within_cooldown, record

logger = logging.getLogger(__name__)

_LAST_BROADCAST_PATH = Path("./output/last_broadcast.json")
_ANCHOR_HANDOFF_MINUTES = 60   # use last show's anchor team if they aired within this window


class Agent(BaseAgent):
    """Breaking News Checker — monitors headlines and triggers emergency productions."""

    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.1,
            openai_api_key=settings.OPENAI_API_KEY,
        )
        logger.info("Breaking News Checker initialized")

    def get_info(self) -> AgentInfo:
        return AgentInfo(
            name="breaking_news_checker",
            display_name="Breaking News Checker",
            description="Monitors current headlines and triggers emergency productions for qualifying breaking news",
            version="1.0.0",
            module_path="agents.breaking_news_checker.agent",
            parent_agent=None,
        )

    async def _fetch_headlines(self) -> str:
        """Search for top current headlines using Tavily."""
        try:
            from langchain_community.tools.tavily_search import TavilySearchResults
            tavily = TavilySearchResults(
                max_results=15,
                tavily_api_key=settings.TAVILY_API_KEY,
            )
            results = await asyncio.to_thread(
                tavily.invoke,
                "breaking news today major events top stories"
            )
            if isinstance(results, list):
                lines = []
                for r in results:
                    title = r.get("title", "")
                    content = r.get("content", "")[:200]
                    source = r.get("url", "")
                    lines.append(f"- {title}\n  {content}\n  Source: {source}")
                return "\n\n".join(lines)
            return str(results)
        except Exception as e:
            logger.error(f"[breaking_news] Headline fetch failed: {e}")
            return ""

    def _determine_show_slug(self) -> str:
        """
        Return the show slug to use for this production.
        If a regular scheduled broadcast ran within ANCHOR_HANDOFF_MINUTES, adopt that
        show's anchor team (they're already 'on set'). Otherwise use the dedicated
        breaking-news off-hours anchor team.
        """
        try:
            if _LAST_BROADCAST_PATH.exists():
                lb = json.loads(_LAST_BROADCAST_PATH.read_text(encoding="utf-8"))
                last_ts = lb.get("ts_unix", 0)
                elapsed_min = (datetime.now(timezone.utc).timestamp() - last_ts) / 60
                last_slug = lb.get("show_slug", "")
                # Don't hand off to entertainment-weekly or another breaking-news
                if elapsed_min <= _ANCHOR_HANDOFF_MINUTES and last_slug not in (
                    "breaking-news", "entertainment-weekly", ""
                ):
                    logger.info(
                        f"[breaking_news] '{last_slug}' aired {elapsed_min:.0f}min ago "
                        f"— using its anchor team"
                    )
                    return last_slug
        except Exception as e:
            logger.warning(f"[breaking_news] Could not read last_broadcast.json: {e}")
        logger.info("[breaking_news] Using dedicated breaking-news anchor team")
        return "breaking-news"

    def _format_recent_log(self, entries: list[dict]) -> str:
        if not entries:
            return "None — no breaking news covered in the last 24 hours."
        lines = []
        for e in entries:
            ts = e.get("ts", "")[:16].replace("T", " ")
            kw = ", ".join(e.get("keywords", []))
            lines.append(f"[{ts} UTC] {e.get('headline', '')}  |  keywords: {kw}")
        return "\n".join(lines)

    async def process_message(self, message: str, context: dict = None) -> dict:
        logger.info("[breaking_news] Starting breaking news check")

        # Cooldown guard — don't fire again if a production was triggered recently
        if within_cooldown():
            logger.info("[breaking_news] Within cooldown window — skipping")
            return {
                "success": True,
                "response": "Breaking news check skipped — within 30-minute cooldown from a recent production.",
                "agent": "breaking_news_checker",
                "breaking_news_found": False,
            }

        # Fetch current headlines
        headlines = await self._fetch_headlines()
        if not headlines:
            return {
                "success": False,
                "response": "Breaking news check failed — could not fetch headlines.",
                "agent": "breaking_news_checker",
                "breaking_news_found": False,
            }

        # Build dedup context from recent breaking news log
        recent_entries = get_recent_for_dedup()
        recent_log_text = self._format_recent_log(recent_entries)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # LLM evaluation
        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=BREAKING_NEWS_SYSTEM_PROMPT),
                HumanMessage(content=BREAKING_NEWS_EVAL_PROMPT.format(
                    current_datetime=now_str,
                    headlines=headlines,
                    recent_log=recent_log_text,
                )),
            ])
            content = response.content.strip()
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
            parsed = json.loads(content)
        except Exception as e:
            logger.error(f"[breaking_news] LLM evaluation failed: {e}", exc_info=True)
            return {
                "success": False,
                "response": f"Breaking news evaluation error: {e}",
                "agent": "breaking_news_checker",
                "breaking_news_found": False,
            }

        breaking_found = parsed.get("breaking_news_found", False)
        confidence   = parsed.get("confidence", "low").lower()
        topic        = parsed.get("topic", "")
        headline     = parsed.get("headline", "")
        reason       = parsed.get("reason", "")
        keywords     = parsed.get("keywords", [])
        prod_message = parsed.get("production_message", "")

        logger.info(f"[breaking_news] found={breaking_found} confidence={confidence} | {reason[:120]}")

        if not breaking_found:
            return {
                "success": True,
                "response": f"No breaking news. {reason}",
                "agent": "breaking_news_checker",
                "breaking_news_found": False,
            }

        # Low confidence — story doesn't clearly meet the threshold; do not produce
        if confidence == "low":
            logger.info(f"[breaking_news] Low confidence — suppressing production. {reason}")
            return {
                "success": True,
                "response": f"Potential story found but confidence too low to produce. {reason}",
                "agent": "breaking_news_checker",
                "breaking_news_found": False,
                "confidence": "low",
            }

        # Code-level same-story suppression — LLM dedup is unreliable for repeat fires.
        # Tiered gap: 3h required after 2+ fires, 6h after 4+ fires in the last 24h.
        from tools.breaking_news_log import same_story_fire_count, same_story_last_fired_seconds
        count_24h = same_story_fire_count(keywords, since_hours=24.0)
        last_fired_secs = same_story_last_fired_seconds(keywords)
        if count_24h >= 4:
            required_gap_secs = 6 * 3600
        elif count_24h >= 2:
            required_gap_secs = 3 * 3600
        else:
            required_gap_secs = 0

        if required_gap_secs and last_fired_secs < required_gap_secs:
            logger.info(
                f"[breaking_news] Same-story suppression: '{topic}' fired {count_24h}x in 24h, "
                f"last {last_fired_secs/3600:.1f}h ago (need {required_gap_secs/3600:.0f}h gap) — suppressed"
            )
            return {
                "success": True,
                "response": (
                    f"Same-story suppression: '{topic}' has been covered {count_24h}x in the last 24h "
                    f"and last aired {last_fired_secs/60:.0f} minutes ago. "
                    f"Required gap: {required_gap_secs//3600}h."
                ),
                "agent": "breaking_news_checker",
                "breaking_news_found": False,
            }

        # Determine anchor team: last show's crew if aired recently, else dedicated BN team
        show_slug = self._determine_show_slug()

        # Record BEFORE firing so a crash or re-check won't double-produce
        record(topic=topic, headline=headline, keywords=keywords, show_slug=show_slug)

        # Start production via /produce/async so Jarvis can track and notify when done
        logger.info(f"[breaking_news] Starting production: show={show_slug} | {topic}")
        production_job_id = ""
        try:
            import requests as _req
            resp = _req.post(
                "http://localhost:8091/produce/async",
                json={"request": prod_message, "show_slug": show_slug},
                timeout=15,
            )
            if resp.ok:
                production_job_id = resp.json().get("job_id", "")
                logger.info(f"[breaking_news] Production job started: {production_job_id}")
            else:
                logger.error(f"[breaking_news] /produce/async returned {resp.status_code}")
        except Exception as e:
            logger.error(f"[breaking_news] Failed to start production: {e}", exc_info=True)

        response_text = (
            f"Breaking news detected — production started.\n"
            f"Story: {headline}\n"
            f"Confidence: {confidence}\n"
            f"Anchor team: {show_slug}\n"
            f"Reason: {reason}"
        )
        if production_job_id:
            response_text += f"\nPRODUCTION_JOB_ID: {production_job_id}"

        return {
            "success": True,
            "response": response_text,
            "agent": "breaking_news_checker",
            "breaking_news_found": True,
            "confidence": confidence,
            "topic": topic,
            "headline": headline,
            "show_slug": show_slug,
        }

"""
agents/earthquake_monitor/agent.py

Background agent that polls for earthquakes every 60 seconds and
automatically triggers a breaking news broadcast when one is detected.

Works similarly to the existing breaking_news_checker agent — runs
as a background task and calls POST /produce/async on the local server
to kick off the full news pipeline.
"""

import json
import asyncio
import logging
import httpx
from datetime import datetime, timezone
from pathlib import Path

# Import our earthquake detection tool
import sys
sys.path.append(str(Path(__file__).resolve().parents[2]))
from tools.earthquake_tool import get_earthquake_alert

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

POLL_INTERVAL_SECONDS = 60          # Check every 60 seconds (respect rate limits)
LOCAL_API_URL = "http://localhost:8091/produce/async"
ALERT_LOG_PATH = Path("./output/earthquake_alert_log.json")

# Cooldown: don't re-broadcast the same earthquake within this many minutes
SAME_QUAKE_COOLDOWN_MINUTES = 60


# ── Alert log helpers ──────────────────────────────────────────────────────────

def _load_alert_log():
    """Load the log of previously broadcast earthquakes."""
    if ALERT_LOG_PATH.exists():
        try:
            return json.loads(ALERT_LOG_PATH.read_text())
        except Exception:
            return []
    return []


def _save_alert_log(log):
    """Save the alert log to disk."""
    ALERT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERT_LOG_PATH.write_text(json.dumps(log, indent=2))


def _already_broadcast(quake_id, log):
    """
    Returns True if we've already broadcast this earthquake recently
    (within SAME_QUAKE_COOLDOWN_MINUTES).
    """
    now = datetime.now(timezone.utc).timestamp()
    for entry in log:
        if entry.get("quake_id") == quake_id:
            age_minutes = (now - entry.get("timestamp", 0)) / 60
            if age_minutes < SAME_QUAKE_COOLDOWN_MINUTES:
                return True
    return False


def _log_broadcast(quake_id, log):
    """Add a new entry to the alert log."""
    log.append({
        "quake_id": quake_id,
        "timestamp": datetime.now(timezone.utc).timestamp(),
        "broadcast_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    })
    # Only keep the last 100 entries
    _save_alert_log(log[-100:])


# ── Main monitor loop ──────────────────────────────────────────────────────────

async def run_earthquake_monitor():
    """
    Async loop that:
    1. Checks for qualifying earthquakes every 60 seconds
    2. Cross-references with occupancy data
    3. Triggers a breaking news broadcast if a new quake is detected
    """
    logger.info("[earthquake_monitor] Starting — polling every %ds for M5.0+ earthquakes near Sacramento", POLL_INTERVAL_SECONDS)

    while True:
        try:
            # Run the blocking earthquake check in a thread so it doesn't
            # block the async event loop
            alert = await asyncio.get_event_loop().run_in_executor(
                None, get_earthquake_alert
            )

            if alert:
                quake = alert["earthquake"]
                quake_id = quake["id"]
                alert_log = _load_alert_log()

                if _already_broadcast(quake_id, alert_log):
                    logger.info(
                        "[earthquake_monitor] Quake %s already broadcast recently — skipping.",
                        quake_id
                    )
                else:
                    logger.warning(
                        "[earthquake_monitor] NEW EARTHQUAKE DETECTED — M%s near %s. "
                        "%d people at risk across %d locations. Triggering broadcast...",
                        quake["magnitude"],
                        quake["location"],
                        alert["total_people_at_risk"],
                        alert["total_locations_affected"],
                    )

                    # Trigger the full news pipeline
                    await _trigger_broadcast(alert["broadcast_summary"], quake_id)

                    # Log it so we don't re-broadcast the same quake
                    _log_broadcast(quake_id, alert_log)

            else:
                logger.info("[earthquake_monitor] No qualifying earthquakes detected.")

        except Exception as e:
            logger.error("[earthquake_monitor] Unexpected error during check: %s", e)

        # Wait before checking again
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _trigger_broadcast(broadcast_summary, quake_id):
    """
    Sends the earthquake alert to the local newsroom API
    to kick off the full breaking news pipeline.
    """
    payload = {
        "request": broadcast_summary,
        "client_datetime": datetime.now(timezone.utc).strftime(
            "%A, %B %-d, %Y, %I:%M %p UTC"
        ),
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(LOCAL_API_URL, json=payload)
            response.raise_for_status()
            result = response.json()
            logger.info(
                "[earthquake_monitor] Broadcast triggered successfully. Job ID: %s",
                result.get("job_id", "unknown"),
            )
    except httpx.RequestError as e:
        logger.error(
            "[earthquake_monitor] Failed to trigger broadcast for quake %s: %s",
            quake_id, e
        )

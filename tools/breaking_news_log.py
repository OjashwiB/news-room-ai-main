"""
Breaking news coverage log — persists recently covered breaking stories to prevent
the same story being re-broadcast without a significant new development.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_LOG_PATH = Path("./output/breaking_news_log.json")
_MAX_ENTRIES = 100
_DEDUP_WINDOW_HOURS = 24.0   # was 6 — ongoing conflicts must stay visible for a full day
_COOLDOWN_MINUTES = 60       # was 30 — minimum gap between any two breaking news productions


def _load() -> list[dict]:
    if _LOG_PATH.exists():
        try:
            return json.loads(_LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(entries: list[dict]) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        _LOG_PATH.write_text(json.dumps(entries[-_MAX_ENTRIES:], indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[breaking_news_log] Could not save: {e}")


def get_recent_for_dedup() -> list[dict]:
    """Return entries from the last DEDUP_WINDOW_HOURS for LLM dedup evaluation."""
    cutoff = datetime.now(timezone.utc).timestamp() - (_DEDUP_WINDOW_HOURS * 3600)
    return [e for e in _load() if e.get("ts_unix", 0) >= cutoff]


def within_cooldown() -> bool:
    """Return True if a breaking news production fired in the last COOLDOWN_MINUTES."""
    cutoff = datetime.now(timezone.utc).timestamp() - (_COOLDOWN_MINUTES * 60)
    return any(e.get("ts_unix", 0) >= cutoff for e in _load())


def same_story_fire_count(keywords: list[str], since_hours: float = 24.0) -> int:
    """Count log entries in the last since_hours that share 2+ keywords with the given list."""
    cutoff = datetime.now(timezone.utc).timestamp() - (since_hours * 3600)
    kw_set = {k.lower() for k in keywords}
    count = 0
    for e in _load():
        if e.get("ts_unix", 0) < cutoff:
            continue
        e_kw = {k.lower() for k in e.get("keywords", [])}
        if len(kw_set & e_kw) >= 2:
            count += 1
    return count


def same_story_last_fired_seconds(keywords: list[str]) -> float:
    """Return seconds since the most recent log entry sharing 2+ keywords. Returns inf if none."""
    now = datetime.now(timezone.utc).timestamp()
    kw_set = {k.lower() for k in keywords}
    most_recent = 0.0
    for e in _load():
        e_kw = {k.lower() for k in e.get("keywords", [])}
        if len(kw_set & e_kw) >= 2 and e.get("ts_unix", 0) > most_recent:
            most_recent = e["ts_unix"]
    return (now - most_recent) if most_recent else float("inf")


def record(topic: str, headline: str, keywords: list[str], show_slug: str) -> None:
    """Log a triggered breaking news production to prevent immediate re-fire."""
    entries = _load()
    now = datetime.now(timezone.utc)
    entries.append({
        "topic": topic,
        "headline": headline,
        "keywords": keywords,
        "show_slug": show_slug,
        "ts": now.isoformat(),
        "ts_unix": now.timestamp(),
    })
    _save(entries)
    logger.info(f"[breaking_news_log] Recorded: {headline[:80]}")

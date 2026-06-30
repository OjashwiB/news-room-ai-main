"""
Round-robin look rotation for news anchors, plus per-show stand-in rotation.
State is persisted in tools/anchor_rotation_state.json (look rotation) and
tools/show_anchor_rotation_state.json (stand-in rotation).
"""

import json
import logging
from pathlib import Path

from config.anchors import Anchor

logger = logging.getLogger(__name__)

_STATE_FILE = Path(__file__).parent / "anchor_rotation_state.json"
_SHOW_ANCHOR_STATE_FILE = Path(__file__).parent / "show_anchor_rotation_state.json"


def _load_state() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    try:
        _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[anchor_rotation] Could not save state: {e}")


def _load_show_anchor_state() -> dict:
    if _SHOW_ANCHOR_STATE_FILE.exists():
        try:
            return json.loads(_SHOW_ANCHOR_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_show_anchor_state(state: dict) -> None:
    try:
        _SHOW_ANCHOR_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[show_anchor_rotation] Could not save state: {e}")


def get_show_anchor_name(show_slug: str, assignment) -> str:
    """
    Return the anchor name to use for this show+desk assignment.
    If assignment.alt_anchor_name is set and alt_every > 0, rotates in
    the stand-in every alt_every productions (keyed by show + main anchor).
    """
    if not getattr(assignment, "alt_anchor_name", "") or not getattr(assignment, "alt_every", 0):
        return assignment.anchor_name

    state = _load_show_anchor_state()
    key = f"{show_slug}:{assignment.anchor_name}"
    count = state.get(key, 0)

    use_alt = (count % assignment.alt_every) == (assignment.alt_every - 1)
    state[key] = count + 1
    _save_show_anchor_state(state)

    chosen = assignment.alt_anchor_name if use_alt else assignment.anchor_name
    logger.info(
        f"[show_anchor_rotation] {show_slug}/{assignment.anchor_name}: "
        f"production #{count + 1}, alt_every={assignment.alt_every} "
        f"→ {chosen}{' (stand-in)' if use_alt else ''}"
    )
    return chosen


def get_next_look(anchor: Anchor, preference: str = "", desk: str = "") -> str:
    """
    Return the next avatar_id for this anchor, advancing the rotation index.
    If preference is set (e.g. "formal", "casual", "sitting"), only looks whose
    description contains that keyword are included in the rotation pool.
    Falls back to all looks if no look matches the preference keyword.
    """
    if not anchor.avatars:
        logger.warning(f"[anchor_rotation] {anchor.name} has no avatars configured")
        return "", "center"

    pref = preference.lower().strip() if preference else ""
    if pref:
        pool = [lk for lk in anchor.avatars if pref in lk.description.lower()]
        if not pool:
            logger.info(
                f"[anchor_rotation] {anchor.name}: preference '{preference}' matched no looks "
                f"— using all {len(anchor.avatars)} look(s)"
            )
            pool = anchor.avatars
    else:
        pool = anchor.avatars

    if len(pool) == 1:
        selected = pool[0]
        logger.info(
            f"[anchor_rotation] {anchor.name} ({desk or 'desk?'}): "
            f"only 1 look — avatar={selected.avatar_id[:20]}… [{selected.description[:60]}]"
        )
        return selected.avatar_id, "center"

    state = _load_state()
    key = anchor.name
    current_idx = state.get(key, 0)
    next_idx = current_idx % len(pool)
    selected = pool[next_idx]
    state[key] = next_idx + 1
    _save_state(state)
    logger.info(
        f"[anchor_rotation] {anchor.name} ({desk or 'desk?'}): "
        f"look {next_idx + 1}/{len(pool)} — avatar={selected.avatar_id[:20]}… "
        f"[{selected.description[:60]}]"
    )
    return selected.avatar_id, "center"

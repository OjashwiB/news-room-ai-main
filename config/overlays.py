"""
Overlay layer configuration for video compositing.

Background layers (Layer 2) are composited onto the studio background video
before upload to HeyGen — visible in all scenes, behind the avatar.

Foreground layers (Layer 5) are composited onto the fully rendered HeyGen
video in post-processing — visible in all scenes, in front of the avatar.

GLOBAL_* lists apply to every desk.
DESK_*_LAYERS dicts map desk slugs to additional layers (appended to globals).

VideoLayer fields:
    source  — path to the asset file, relative to the project root
    x, y    — top-left pixel position in the 1280×720 frame
    width   — target width in pixels (height auto-scales to preserve AR if omitted)
    height  — target height in pixels (width auto-scales to preserve AR if omitted)
              If both are given, the image is stretched to that exact size.
              If neither is given, the original size is used.
"""

from dataclasses import dataclass


@dataclass
class VideoLayer:
    source: str
    x: int
    y: int
    width: int | None = None
    height: int | None = None


# ── Background layers (always visible, behind avatar) ────────────────────────
GLOBAL_BACKGROUND_LAYERS: list[VideoLayer] = []

# plant_1.png: 522×800 RGBA — scaled to 220×337, lower-right beside the anchor desk
_PLANT1 = VideoLayer("assets/plant_1.png", x=1280, y=600, width=220)
_PLANT2 = VideoLayer("assets/plant_2.png", x=1260, y=620, width=220)

# Per-desk background layers (appended to globals) — entertainment excluded
DESK_BACKGROUND_LAYERS: dict[str, list[VideoLayer]] = {
    "national":       [],
    "politics":       [],
    "foreign":        [],
    "business":       [],
    "health_science": [],
    "investigative":  [],
}

# ── Foreground layers (in front of avatar, applied post-HeyGen) ──────────────
GLOBAL_FOREGROUND_LAYERS: list[VideoLayer] = []

# Per-desk foreground layers (appended to globals)
DESK_FOREGROUND_LAYERS: dict[str, list[VideoLayer]] = {
    "national":       [],
    "politics":       [],
    "foreign":        [],
    "business":       [],
    "health_science": [],
    "investigative":  [],
}


# ── Accessors ─────────────────────────────────────────────────────────────────

def get_background_layers(desk_slug: str = "") -> list[VideoLayer]:
    return GLOBAL_BACKGROUND_LAYERS + DESK_BACKGROUND_LAYERS.get(desk_slug, [])


def get_foreground_layers(desk_slug: str = "") -> list[VideoLayer]:
    return GLOBAL_FOREGROUND_LAYERS + DESK_FOREGROUND_LAYERS.get(desk_slug, [])

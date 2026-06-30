"""
Editorial desk configuration.
Each desk owns a beat and has a preferred anchor. The Executive Producer
uses this to route stories to the right correspondent and tone.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Desk:
    slug: str                       # machine-readable identifier
    name: str                       # display name, e.g. "Foreign Desk"
    beat: str                       # topics this desk covers
    preferred_anchors: list[str]    # anchor names in priority order
    prompt_style: str               # tone/depth guidance injected into script_writer
    background_asset_id: str        # HeyGen video background asset ID
    pip_position: str = "left"      # b-roll PiP corner: "left" or "right"


DESKS: list[Desk] = [
    Desk(
        slug="national",
        name="National Desk",
        beat="Domestic US news, general hard news, lead stories, breaking national events",
        preferred_anchors=["Daniel Mercer", "Nicholas Stavros"],
        prompt_style="Authoritative, straight-down-the-middle hard news. Lead with impact.",
        background_asset_id="686cdaf404de4e2a967cfc075903d830",
        pip_position="left",        
    ),
    Desk(
        slug="politics",
        name="Politics & White House Desk",
        beat="Domestic politics, elections, Congress, presidential coverage, executive branch, policy",
        preferred_anchors=["Dominic Fairchild", "Shawn Green", "Victor Marinos"],
        prompt_style="Sharp, precise political reporting. Cite sources and policy details. Strictly neutral tone.",
        background_asset_id="271f7177f2244bebbf5eeab5aca0db71",
        pip_position="left",        
    ),
    Desk(
        slug="foreign",
        name="Foreign Desk",
        beat="International news, foreign affairs, overseas conflicts, diplomacy, geopolitics",
        preferred_anchors=["Shawn Green"],
        prompt_style="Measured, globally-informed delivery. Always provide geographic and political context.",
        background_asset_id="686cdaf404de4e2a967cfc075903d830",
        pip_position="left",        
    ),
    Desk(
        slug="business",
        name="Business & Finance Desk",
        beat="Markets, economy, corporate news, trade, financial policy, economic indicators",
        preferred_anchors=["Brandon Jones"],
        prompt_style="Clear, data-driven reporting. Define financial terms for a general audience.",
        background_asset_id="271f7177f2244bebbf5eeab5aca0db71",
        pip_position="right",
    ),
    Desk(
        slug="entertainment",
        name="Entertainment Desk",
        beat="Entertainment industry, celebrity news, film, music, television, arts and culture",
        preferred_anchors=["Karoline Faye", "Alexa Chen", "Zayne Carter", "Monica Hayes", "Valerie Brooks"],
        prompt_style="Warm, conversational, and engaging. Lighter tone — factual but not stiff.",
        background_asset_id="8906f7fc43274606b3d56c7b9170c9fd",
        pip_position="left",
    ),
    Desk(
        slug="health_science",
        name="Health & Science Desk",
        beat="Medical news, public health, scientific research, technology breakthroughs, environment",
        preferred_anchors=["Darlene Smith"],
        prompt_style="Accessible and calm. Translate technical findings clearly for general viewers.",
        background_asset_id="686cdaf404de4e2a967cfc075903d830",
        pip_position="left",        
    ),
    Desk(
        slug="investigative",
        name="Investigative Desk",
        beat="Long-form accountability journalism, government oversight, corporate wrongdoing, systemic issues",
        preferred_anchors=["Alister Blackwood"],
        prompt_style="Deliberate, serious, and weighty. Build the story methodically. Every claim must be sourced.",
        background_asset_id="271f7177f2244bebbf5eeab5aca0db71",
        pip_position="right",
    ),
]

_DESK_MAP: dict[str, Desk] = {d.slug: d for d in DESKS}


def get_desk(slug: str) -> Optional[Desk]:
    """Return a Desk by slug, or None if not found."""
    return _DESK_MAP.get(slug)


def list_desks() -> list[dict]:
    """Return desk roster as a list of dicts (safe to serialize or inject into prompts)."""
    return [
        {
            "slug": d.slug,
            "name": d.name,
            "beat": d.beat,
            "preferred_anchors": d.preferred_anchors,
        }
        for d in DESKS
    ]

"""
Show definitions — maps named broadcasts to anchor/look assignments per desk.

Each show specifies which anchor covers which editorial desk for that program,
plus a look preference (e.g. "formal", "casual") used by the rotation system.
The Executive Producer auto-detects the current show from time of day,
or accepts an explicit show_slug from the scheduler.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DeskAssignment:
    anchor_name: str
    look_preference: str = ""   # keyword fed to anchor rotation: "formal", "casual", "sitting", etc.
                                # empty string = rotate freely through all looks
    alt_anchor_name: str = ""   # optional stand-in anchor name
    alt_every: int = 0          # use stand-in every N productions (0 = never)


@dataclass
class Show:
    name: str
    slug: str
    description: str
    tone: str                                              # injected into EP/script_writer prompts
    desk_anchors: dict[str, DeskAssignment] = field(default_factory=dict)
    background_asset_id: str = ""                          # overrides desk background when set

    def anchor_for_desk(self, desk_slug: str) -> Optional[DeskAssignment]:
        """Return the desk assignment, or None if the desk isn't listed for this show."""
        return self.desk_anchors.get(desk_slug)

    def for_prompt(self) -> str:
        """Format show info for injection into the EP analysis prompt."""
        lines = [
            f"Current broadcast: {self.name}",
            f"Tone: {self.tone}",
            f"Context: {self.description}",
            "Anchor assignments for this show (use these — do not pick a different anchor):",
        ]
        for desk, a in self.desk_anchors.items():
            pref = f"  [prefer {a.look_preference} look]" if a.look_preference else ""
            lines.append(f"  {desk}: {a.anchor_name}{pref}")
        return "\n".join(lines)


# ── Show definitions ───────────────────────────────────────────────────────────

SHOWS: dict[str, Show] = {

    "morning-report": Show(
        name="Morning Report",
        slug="morning-report",
        description=(
            "Weekday morning broadcast. Energetic, informative, and accessible. "
            "Slightly lighter tone than the evening news — leads with top stories "
            "but keeps pacing brisk for the morning audience."
        ),
        tone="conversational and upbeat",
        desk_anchors={
            "national":       DeskAssignment("Daniel Mercer",    "casual", alt_anchor_name="Alexa Chen",    alt_every=3),
            "politics":       DeskAssignment("Daniel Mercer",    "casual", alt_anchor_name="Alexa Chen",    alt_every=3),
            "foreign":        DeskAssignment("Daniel Mercer",    "casual", alt_anchor_name="Alexa Chen",    alt_every=3),
            "entertainment":  DeskAssignment("Monica Hayes",     ""),
            "business":       DeskAssignment("Brandon Jones",    ""),
            "health_science": DeskAssignment("Darlene Smith",    ""),
            "investigative":  DeskAssignment("Alister Blackwood",""),
        },
    ),

    "evening-news": Show(
        name="Evening News",
        slug="evening-news",
        description=(
            "Flagship weekday evening broadcast. Authoritative, comprehensive, and serious. "
            "The day's most important stories covered in depth. "
            "Formal tone — anchors dressed for the main desk."
        ),
        tone="serious and authoritative",
        desk_anchors={
            "national":       DeskAssignment("Nicholas Stavros", "formal", alt_anchor_name="Daniel Mercer",  alt_every=3),
            "politics":       DeskAssignment("Shawn Green",      "formal", alt_anchor_name="Victor Marinos", alt_every=3),
            "foreign":        DeskAssignment("Shawn Green",      "formal", alt_anchor_name="Victor Marinos", alt_every=3),
            "entertainment":  DeskAssignment("Alexa Chen",       ""),
            "business":       DeskAssignment("Brandon Jones",    ""),
            "health_science": DeskAssignment("Darlene Smith",    ""),
            "investigative":  DeskAssignment("Alister Blackwood",""),
        },
    ),

    "weekend-roundup": Show(
        name="Weekend Roundup",
        slug="weekend-roundup",
        description=(
            "Weekend news summary. Broader perspective, longer features, "
            "and more reflective pacing. Covers the week's major developments "
            "and previews the week ahead."
        ),
        tone="measured and reflective",
        desk_anchors={
            "national":       DeskAssignment("Alister Blackwood",""),
            "politics":       DeskAssignment("Alister Blackwood",""),
            "foreign":        DeskAssignment("Alister Blackwood",""),
            "entertainment":  DeskAssignment("Valerie Brooks",   ""),
            "business":       DeskAssignment("Brandon Jones",    ""),
            "health_science": DeskAssignment("Darlene Smith",    ""),
            "investigative":  DeskAssignment("Alister Blackwood",""),
        },
    ),

    "entertainment-weekly": Show(
        name="Entertainment Weekly",
        slug="entertainment-weekly",
        description=(
            "Weekly entertainment roundup. Upbeat, culture-forward, and personality-driven. "
            "Celebrity news, film, music, arts, and pop culture."
        ),
        tone="upbeat and conversational",
        desk_anchors={
            "entertainment":  DeskAssignment("Alexa Chen",   ""),            
            "national":       DeskAssignment("Dominic Fairchild","casual"),
            "politics":       DeskAssignment("Dominic Fairchild","casual"),
            "business":       DeskAssignment("Brandon Jones",    ""),
            "health_science": DeskAssignment("Darlene Smith",    ""),
        },
    ),

    "special-report": Show(
        name="Special Report",
        slug="special-report",
        description=(
            "Long-form in-depth special report on a single topic. Thorough, analytical, and "
            "comprehensive — covers background, context, multiple perspectives, expert analysis, "
            "and implications. Not bound by the regular broadcast schedule."
        ),
        tone="measured, thorough, and authoritative. Build the story methodically with full context and analysis.",
        background_asset_id="ac28ab03ec26464e8adc88458bdd2fec",   # foreign desk bg — replace when custom bg is ready
        desk_anchors={
            "national":       DeskAssignment("Shawn Green", ""),
            "politics":       DeskAssignment("Shawn Green", ""),
            "foreign":        DeskAssignment("Shawn Green", ""),
            "business":       DeskAssignment("Shawn Green", ""),
            "health_science": DeskAssignment("Shawn Green", ""),
            "investigative":  DeskAssignment("Shawn Green", ""),
            "entertainment":  DeskAssignment("Shawn Green", ""),
        },
    ),

    "breaking-news": Show(
        name="Breaking News",
        slug="breaking-news",
        description=(
            "Unscheduled breaking news alert. Reserved for significant developing stories "
            "that cannot wait for the next scheduled broadcast. Leads immediately with the "
            "breaking development — no preamble, no recap of older news."
        ),
        tone="urgent and direct. Lead immediately with the breaking development. No preamble.",
        background_asset_id="e81b39b787274f149b3f6aaf313e7050",   # foreign desk bg — replace when custom bg is ready
         desk_anchors={
            "national":       DeskAssignment("Nicholas Stavros", "formal"),
            "politics":       DeskAssignment("Victor Marinos",   "formal"),
            "foreign":        DeskAssignment("Shawn Green",      "formal"),
            "business":       DeskAssignment("Brandon Jones",    "formal"),
            "health_science": DeskAssignment("Darlene Smith",    "formal"),
            "investigative":  DeskAssignment("Alister Blackwood","formal"),
            "entertainment":  DeskAssignment("Alexa Chen",       "formal"),
        },
    ),
}


# ── Lookup helpers ─────────────────────────────────────────────────────────────

def get_show(slug: str) -> Optional[Show]:
    return SHOWS.get(slug)


def detect_show() -> Show:
    """
    Auto-detect the appropriate show from the current day and time.
    Entertainment Weekly is not auto-detected — it must be scheduled explicitly.
    """
    now = datetime.now()
    is_weekend = now.weekday() >= 5   # Saturday=5, Sunday=6
    hour = now.hour

    if is_weekend:
        return SHOWS["weekend-roundup"]
    elif hour < 13:       # midnight–12:59pm weekday → morning
        return SHOWS["morning-report"]
    else:                 # 1pm–midnight weekday → evening
        return SHOWS["evening-news"]

"""
News desk anchor roster.
Add or remove anchors here. Each anchor has a list of AvatarLooks so the
Executive Producer can choose the most appropriate appearance for each story.
To find IDs: GET https://api.heygen.com/v2/avatars and /v2/voices
"""

from dataclasses import dataclass
from typing import Optional
import random


@dataclass
class AvatarLook:
    avatar_id: str
    description: str    # e.g. "formal suit at news desk", "casual blazer standing", "outdoor live shot"


@dataclass
class Anchor:
    name: str                       # On-air name used in scripts
    avatars: list[AvatarLook]       # Ordered list — first is the default look
    voice_id: str                   # HeyGen voice ID
    desk: str                       # Desk slug this anchor belongs to (see config/desks.py)
    bio: str                        # Short description for script-writer context (tone, style)
    voice_emotion: Optional[str] = None   # "Excited" | "Friendly" | "Serious" | "Soothing" | "Broadcaster"
    talking_style: Optional[str] = None  # "stable" | "expressive" (talking_photo avatars only)
    expression: Optional[str] = None     # "default" | "happy" (talking_photo avatars only)

    @property
    def default_avatar_id(self) -> str:
        return self.avatars[0].avatar_id if self.avatars else ""

    def get_avatar_id(self, description: Optional[str] = None) -> str:
        """Return avatar_id by partial description match, or default if not found."""
        if not description or not self.avatars:
            return self.default_avatar_id
        desc_lower = description.lower()
        for look in self.avatars:
            if desc_lower in look.description.lower() or any(
                word in look.description.lower() for word in desc_lower.split()
            ):
                return look.avatar_id
        return self.default_avatar_id

    def list_looks(self) -> list[dict]:
        return [{"avatar_id": lk.avatar_id, "description": lk.description} for lk in self.avatars]


# ── Anchor Roster ─────────────────────────────────────────────────────────────

ANCHORS: list[Anchor] = [

    Anchor(
        name="Shawn Green",
        avatars=[
            AvatarLook("Shawn_Suit_Front_public", "formal suit, neutral backdrop, Standing — international affairs and geopolitics"),           # HeyGen: "Shawn Suit Front"
            AvatarLook("Shawn_Sitting_Front_public", "formal suit, neutral backdrop, Sitting — international affairs and geopolitics"),            # HeyGen: "Shawn Sitting Front"
            AvatarLook("Shawn_Casual_Sitting_Front_public", "casual, neutral backdrop, Sitting — international affairs and geopolitics"),           # HeyGen: "Shawn Casual Sitting Front"
            # AvatarLook("<avatar_id>", "field jacket, outdoor — war zone and conflict reporting"),
            # AvatarLook("<avatar_id>", "business casual — diplomatic and economic foreign stories"),
        ],
        voice_id="e1a429dbe823406dbae5fa7c3612314d",
        desk="politics, national",
        bio="Chief Foreign Correspondent. Measured and globally-informed. Covers international affairs and geopolitics.",
        voice_emotion="Broadcaster",
        talking_style="stable",
    ),    
    Anchor(
        name="Dominic Fairchild",
        avatars=[
            AvatarLook("f7bd87b360d143faadb4ded248f86299", "informal shirt at entertainment desk — Entertainment, celebrity, culture, breaking stories"),  # HeyGen: "Man in the Sport Coat"
            # AvatarLook("<avatar_id>", "standing in front of Capitol backdrop — election night and major votes"),
        ],
        voice_id="d60b050b12d9478493d0bd689ee7547b",
        desk="politics, national",
        bio="Chief Political Correspondent. Sharp and precise. Covers the White House, Congress, and elections.",
        voice_emotion="Friendly",
        talking_style="expressive",
        expression="happy",
    ),
    Anchor(
        name="Alexa Chen", # Alexa
        avatars=[
            AvatarLook("a5454d8b999d4e5f87f486605465aae4", "Informal sweater , Entertainment news, entertainment and lifestyle stories"),  # HeyGen: "Alexa"
            # AvatarLook("<avatar_id>", "standing in front of Capitol backdrop — election night and major votes"),
        ],
        voice_id="8901bf9a88a24f7c8b22bfe28e4bcc5b",
        desk="entertainment",
        bio="Chief Entertainment Correspondent. Sharp and precise. Covers entertainment, celebrity, and lifestyle stories.",
        voice_emotion="Friendly",
        talking_style="expressive",
        expression="happy",
    ),
    Anchor(
        name="Zayne Carter", # Zayne
        avatars=[
            AvatarLook("5c71aeacd9fc4b4f91c50312180f189b", "dress shirt , Entertainment news, entertainment and lifestyle stories"),  # HeyGen: "Zayne"
            AvatarLook("1751694ccea0415eb8155ff49ce76255", "black suite , Entertainment news, entertainment and lifestyle stories"),  # HeyGen: "Zayne"
              
            # AvatarLook("<avatar_id>", "standing in front of Capitol backdrop — election night and major votes"),
        ],
        voice_id="82aa66b207d641bdbfacca4174cfa326",
        desk="entertainment",
        bio="Chief Entertainment Correspondent. Sharp and precise. Covers entertainment, celebrity, and lifestyle stories.",
        voice_emotion="Friendly",
        talking_style="expressive",
        expression="happy",
    ),    
    Anchor(
        name="Monica Hayes", # Saskia
        avatars=[
            AvatarLook("Saskia_public_1", "Blue Blazer, Morning news, entertainment and lifestyle stories"),   # HeyGen: "Saskia in Blue blazer"
            AvatarLook("Saskia_public_3", "Gray Vest, Morning news, entertainment and lifestyle stories"),    # HeyGen: "Saskia in Grey vest"
            AvatarLook("Saskia_public_4", "Green Blazer, Morning news, entertainment and lifestyle stories"), # HeyGen: "Saskia in Green blazer"
             
            # AvatarLook("<avatar_id>", "standing in front of Capitol backdrop — election night and major votes"),
        ],
        voice_id="a4a6df6d4fc248829f72edde5529defa",
        desk="entertainment",
        bio="Chief Political Correspondent. Sharp and precise. Covers the White House, Congress, and elections.",
        voice_emotion="Friendly",
        talking_style="expressive",
        expression="happy",
    ),    
    Anchor(
        name="Valerie Brooks", # Candace
        avatars=[
            AvatarLook("Candace_Beige_Dress_Front", "Beige Dress, Morning news, entertainment and lifestyle stories"),  # HeyGen: "Candace in Beige Dress (Front)"
            AvatarLook("Candace_Pink_Blazer_Front", "Pink Blazer, Morning news, entertainment and lifestyle stories"),  # HeyGen: "Candace in Pink Blazer (Front)"
             
            # AvatarLook("<avatar_id>", "standing in front of Capitol backdrop — election night and major votes"),
        ],
        voice_id="c7c398ea067c4f43a9d2e15dd7c59cf4",
        desk="entertainment",
        bio="Chief Entertainment Correspondent. Sharp and precise. Covers entertainment, celebrity, and lifestyle stories.",
        voice_emotion="Friendly",
        talking_style="expressive",
        expression="happy",
    ),        
    Anchor(
        name="Nicholas Stavros",
        avatars=[
            AvatarLook("3581241b5df64bd9a331bebda862a637", "Blue Suit, Evening news, entertainment and lifestyle stories"),  # HeyGen: "Kurt" ⚠️ different actor than the on-air name

            # AvatarLook("<avatar_id>", "standing in front of Capitol backdrop — election night and major votes"),
        ],
        voice_id="1ed58c9742c64f2aac00b10a4b0c32a9",
        desk="national",
        bio="Chief Political Correspondent. Sharp and precise. Covers the White House, Congress, and elections.",
        voice_emotion="Friendly",
        talking_style="expressive",
        expression="happy",
    ),     
    Anchor(
        name="Victor Marinos", # Ricardo
        avatars=[
            AvatarLook("fecbc666fa2d4c4ba1c3d0b85cb4c6e5", "Black Suit, Morning news, entertainment and lifestyle stories"),  # HeyGen: "Ricardo"
            AvatarLook("f3de1e1f0d1f48619660b9efe90eddb7", "Black Suit, Morning news, entertainment and lifestyle stories"),  # HeyGen: "Ricardo"
            AvatarLook("5154fcc7f8c045e386676d834d7f4b2e", "Blue suit, Morning news, entertainment and lifestyle stories"),   # HeyGen: "Ricardo"

            # AvatarLook("<avatar_id>", "standing in front of Capitol backdrop — election night and major votes"),
        ],
        voice_id="e809f6ab08a847acac0d043eddfe0078",
        desk="politics",
        bio="Chief Political Correspondent. Sharp and precise. Covers the White House, Congress, and elections.",
        voice_emotion="Friendly",
        talking_style="expressive",
        expression="happy",
    ),         
    Anchor(
        name="Daniel Mercer",
        avatars=[
            AvatarLook("cbc2c423747542eda390ffaeb269202c", "formal suit standing in the main studio — hard news, breaking stories"),  # HeyGen: "Daniel Mercer"
            # AvatarLook("<avatar_id>", "casual blazer, standing — feature stories and human interest"),
            # AvatarLook("<avatar_id>", "outdoor live shot — field reports and on-location coverage"),
        ],
        voice_id="PJXRwHpW7osOhD6GiW1M",
        desk="politics, national",
        bio="Lead anchor. Authoritative and composed. Delivers hard news with calm gravitas.",
        voice_emotion="Broadcaster",
        talking_style="stable",
    ),    
    Anchor(
        name="Karoline Faye",
        avatars=[
            AvatarLook("f48550dcc6f648adacc6593f1d315234", "casual studio look, sitting — entertainment, celebrity, culture"),  # HeyGen: "Brooklyn"
            AvatarLook("ee21a3956e23413d8ac349901f8184d9", "casual look, standing — entertainment, celebrity, culture"),         # HeyGen: "Brooklyn"
        ],
        voice_id="5eb15f7ed1254e658faccf14e67f2cd9",
        desk="entertainment",
        bio="Entertainment Reporter. Warm and conversational. Covers culture, celebrity, film, and the arts.",
        voice_emotion="Friendly",
        talking_style="expressive",
        expression="happy",
    ),
    Anchor(
        name="Brandon Jones",
        avatars=[
            AvatarLook("Brandon_expressive2_public", "business suit, expressive — markets, earnings, economic news"),  # HeyGen: "Brandon in Grey Suit"
            # AvatarLook("<avatar_id>", "casual blazer — startup and tech business stories"),
        ],
        voice_id="3787b4ab93174952a3ad649209f1029a",
        desk="business",
        bio="Business & Finance Correspondent. Clear and data-driven. Covers markets, economy, and corporate news.",
        voice_emotion="Serious",
        talking_style="stable",
    ),
    Anchor(
        name="Alister Blackwood",
        avatars=[
            AvatarLook("Dexter_Suit_Front_public", "dark formal suit, serious — investigative and accountability journalism"),  # HeyGen: "Dexter Suit Front"
            # AvatarLook("<avatar_id>", "casual, no tie — long-form documentary style"),
        ],
        voice_id="088da045d8114ca39add4a75df8ed9a0",
        desk="investigative",
        bio="Senior Investigative Correspondent. Deliberate and serious. Covers accountability journalism and systemic issues.",
        voice_emotion="Serious",
        talking_style="stable",
    ),
    Anchor(
        name="Darlene Smith",
        avatars=[
            AvatarLook("cae4682f73324118b402da17dcbb1b68", "clean studio look — health, medicine, and science reporting"),  # HeyGen: "Crystal Veil"
            # AvatarLook("<avatar_id>", "lab or clinical backdrop — medical research and public health"),
        ],
        voice_id="d6a657274b184772ac28a6146f729d3a",
        desk="health_science",
        bio="Health & Science Correspondent. Calm and accessible. Covers medicine, public health, and scientific research.",
        voice_emotion="Excited",
        talking_style="expressive",
        expression="happy",
    ),

    # Add more anchors below:
    # Anchor(
    #     name="Jordan Lee",
    #     avatars=[
    #         AvatarLook("<avatar_id>", "warm casual look — human interest and feature stories"),
    #         AvatarLook("<avatar_id>", "formal studio — breaking news fill-in"),
    #     ],
    #     voice_id="<voice_id>",
    #     desk="national",
    #     bio="Warm and conversational. Strong on feature stories and human interest.",
    # ),
]

# ── Desk-indexed lookup ────────────────────────────────────────────────────────
_DESK_MAP: dict[str, list[Anchor]] = {}
for _a in ANCHORS:
    _DESK_MAP.setdefault(_a.desk, []).append(_a)


def get_anchor(name: Optional[str] = None, desk: Optional[str] = None) -> "Anchor":
    """
    Return an anchor by name (case-insensitive partial match), by desk slug,
    or randomly if neither is specified. Falls back to first anchor if not found.
    """
    if not ANCHORS:
        raise ValueError("No anchors configured in config/anchors.py")

    if name:
        name_lower = name.lower()
        for anchor in ANCHORS:
            if name_lower in anchor.name.lower():
                return anchor
        return ANCHORS[0]

    if desk:
        desk_anchors = _DESK_MAP.get(desk)
        if desk_anchors:
            return desk_anchors[0]
        return ANCHORS[0]

    return random.choice(ANCHORS)


def list_anchors() -> list[dict]:
    """Return anchor roster as a list of dicts (safe to serialize)."""
    return [{"name": a.name, "desk": a.desk, "bio": a.bio, "looks": a.list_looks()} for a in ANCHORS]


def list_anchors_for_prompt() -> str:
    """
    Return a formatted string describing each anchor and their available looks.
    Used in the Executive Producer analysis prompt so the LLM can choose the best look.
    """
    lines = []
    for a in ANCHORS:
        looks = " | ".join(f'"{lk.description}"' for lk in a.avatars)
        lines.append(f"  {a.name} ({a.desk}) — looks: {looks}")
    return "\n".join(lines)

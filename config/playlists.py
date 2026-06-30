"""
YouTube Playlist configuration.

Three automatic assignment layers per upload:
  1. Desk playlist    — matches the story's editorial desk
  2. Anchor playlist  — matches the on-air correspondent
  3. Format playlist  — matches the production workflow type
  4. Series playlists — keyword-matched against the story topic (opt-in)

Fill in youtube_playlist_id values after creating the playlists in YouTube Studio.
Any entry with an empty playlist_id is silently skipped — the system works with
zero, some, or all playlists configured.

To find a playlist ID: YouTube Studio → Content → Playlists → click a playlist →
the URL will contain "list=PLxxxxxxxx" — copy everything after "list=".
"""

from dataclasses import dataclass, field


@dataclass
class Playlist:
    name: str
    youtube_playlist_id: str    # Empty until created on YouTube
    description: str = ""


# ── Desk Playlists ─────────────────────────────────────────────────────────────
# Keys match desk slugs in config/desks.py

DESK_PLAYLISTS: dict[str, Playlist] = {
    "national":      Playlist("National News",          "PL-27fCQ8W5Ein0zujx1ZSKQwepV9zh7cu", "Domestic US news and breaking national stories"),
    "politics":      Playlist("Politics",               "PL-27fCQ8W5Ej_cmvXfSnKn5Eosif18PZe", "White House, Congress, elections and policy"),
    "foreign":       Playlist("World News",             "PL-27fCQ8W5EjABR_07qS4Xb779VSt-7-0", "International affairs and geopolitics"),
    "business":      Playlist("Business & Markets",     "PL-27fCQ8W5Ei8kC6rOHg0oYL5LviDQXhj", "Markets, economy and corporate news"),
    "entertainment": Playlist("Entertainment",          "PL-27fCQ8W5Eikb7T89_RafdW4ZIjuav7Z", "Celebrity news, film, music and culture"),
    "health_science":Playlist("Health & Science",       "PL-27fCQ8W5EjajGmc87pZrjMKiQPs7KAJ", "Medical news, public health and research"),
    "investigative": Playlist("Investigative Reports",  "PL-27fCQ8W5EgjSN-1V2G00xxg_WEtgJvb", "Accountability journalism and deep dives"),
    "breaking":      Playlist("Breaking News",          "PL-27fCQ8W5Egt-ZDt4tADLfkgZY5q8Syn", "Latest breaking news stories"),    
    "daily":         Playlist("Daily Briefing",         "PL-27fCQ8W5Egt-ZDt4tADLfkgZY5q8Syn", "Concise, structured roundup of the most important news stories of the day"),    
}

# ── Anchor Playlists ───────────────────────────────────────────────────────────
# Keys match anchor names in config/anchors.py

ANCHOR_PLAYLISTS: dict[str, Playlist] = {
    "Alex Morgan":      Playlist("Alex Morgan Reports",             "", ""),
    "Rick Johnson":     Playlist("Rick Johnson on Politics",        "", ""),
    "Karoline Faye":    Playlist("Karoline's Culture Desk",         "", ""),
    "Caroline Levitt":  Playlist("Caroline Levitt",                 "", ""),
    "Shawn Green":      Playlist("Shawn Green — World Report",      "", ""),
    "Brandon Jones":    Playlist("Brandon Jones — Business",        "", ""),
    "Alister Blackwood":Playlist("Alister Blackwood Investigates",  "", ""),
    "Darlene Smith":    Playlist("Darlene Smith — Health & Science","", ""),
}

# ── Show Playlists ─────────────────────────────────────────────────────────────
# Keys match show slugs in config/shows.py.
# Fill in youtube_playlist_id values after creating them in YouTube Studio.

SHOW_PLAYLISTS: dict[str, Playlist] = {
    "breaking-news":       Playlist("Breaking News",         "PL-27fCQ8W5Egt-ZDt4tADLfkgZY5q8Syn", "Breaking news alerts"),
    "special-report":      Playlist("Special Reports",       "", "In-depth special reports"),
    "morning-report":      Playlist("Morning Report",        "", "Morning broadcast"),
    "evening-news":        Playlist("Evening News",          "", "Evening broadcast"),
    "weekend-roundup":     Playlist("Weekend Roundup",       "", "Weekend news roundup"),
    "entertainment-weekly":Playlist("Entertainment Weekly",  "", "Entertainment news"),
}

# ── Format Playlists ───────────────────────────────────────────────────────────
# Keys match workflow names in the Executive Producer.
# Only video-producing workflows are listed — article-only runs don't get a format playlist.

FORMAT_PLAYLISTS: dict[str, Playlist] = {
    "BROADCAST_VIDEO":   Playlist("Full Segments",    "", "Complete broadcast video segments"),
    "VIDEO_FROM_SCRIPT": Playlist("Full Segments",    "", ""),   # same playlist as above
}

# ── Series Playlists ───────────────────────────────────────────────────────────
# Each entry is (keywords, Playlist). If any keyword appears in the story topic
# (case-insensitive) the video is added to that series playlist.
# Add entries here as ongoing stories develop.

SERIES_PLAYLISTS: list[tuple[list[str], Playlist]] = [
    # (["election", "vote", "ballot", "midterm"],   Playlist("Election Coverage",   "", "Ongoing election coverage")),
    # (["fed", "federal reserve", "interest rate"],  Playlist("Fed Watch",           "", "Federal Reserve coverage")),
    # (["AI", "artificial intelligence"],            Playlist("AI & Society",        "", "Artificial intelligence coverage")),
    # (["climate", "environment", "emissions"],      Playlist("Climate Coverage",    "", "")),
]


# ── Resolver ───────────────────────────────────────────────────────────────────

def resolve_playlist_ids(
    desk: str,
    anchor_name: str,
    workflow: str,
    topic: str,
    show_slug: str = "",
) -> list[str]:
    """
    Return the deduplicated list of YouTube playlist IDs that apply to this
    production. Entries with an empty playlist_id are skipped automatically.
    """
    candidates: list[str] = []

    show_pl = SHOW_PLAYLISTS.get(show_slug)
    if show_pl and show_pl.youtube_playlist_id:
        candidates.append(show_pl.youtube_playlist_id)

    desk_pl = DESK_PLAYLISTS.get(desk)
    if desk_pl and desk_pl.youtube_playlist_id:
        candidates.append(desk_pl.youtube_playlist_id)

    anchor_pl = ANCHOR_PLAYLISTS.get(anchor_name)
    if anchor_pl and anchor_pl.youtube_playlist_id:
        candidates.append(anchor_pl.youtube_playlist_id)

    format_pl = FORMAT_PLAYLISTS.get(workflow)
    if format_pl and format_pl.youtube_playlist_id:
        candidates.append(format_pl.youtube_playlist_id)

    topic_lower = topic.lower()
    for keywords, playlist in SERIES_PLAYLISTS:
        if playlist.youtube_playlist_id and any(kw.lower() in topic_lower for kw in keywords):
            candidates.append(playlist.youtube_playlist_id)

    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for pid in candidates:
        if pid not in seen:
            seen.add(pid)
            result.append(pid)
    return result


def list_choosable_for_prompt() -> str:
    """
    Format the playlists the EP can explicitly select, for use in the analysis prompt.
    Includes all DESK_PLAYLISTS (standard desks + specials like 'breaking', 'daily')
    and any configured SERIES_PLAYLISTS. Skips entries with no playlist ID.
    Anchor and format playlists are omitted — those are resolved automatically.
    """
    lines = []
    for key, pl in DESK_PLAYLISTS.items():
        if pl.youtube_playlist_id:
            desc = f" — {pl.description}" if pl.description else ""
            lines.append(f'  "{key}" → {pl.name}{desc}')
    for i, (keywords, pl) in enumerate(SERIES_PLAYLISTS):
        if pl.youtube_playlist_id:
            desc = f" — {pl.description}" if pl.description else ""
            lines.append(f'  "series_{i}" → {pl.name} (keywords: {", ".join(keywords)}){desc}')
    return "\n".join(lines) if lines else "  (none configured yet)"


def get_ids_by_keys(keys: list[str]) -> list[str]:
    """
    Resolve a list of playlist keys (as chosen by the EP) to YouTube playlist IDs.
    Looks up DESK_PLAYLISTS by key, SERIES_PLAYLISTS by series_N index.
    Skips unknown keys or entries with empty IDs.
    """
    ids: list[str] = []
    for key in keys:
        if key.startswith("series_"):
            try:
                idx = int(key.split("_", 1)[1])
                _, pl = SERIES_PLAYLISTS[idx]
                if pl.youtube_playlist_id:
                    ids.append(pl.youtube_playlist_id)
            except (ValueError, IndexError):
                pass
        else:
            pl = DESK_PLAYLISTS.get(key)
            if pl and pl.youtube_playlist_id:
                ids.append(pl.youtube_playlist_id)
    return ids


def list_playlists() -> list[dict]:
    """Return all configured playlists as a flat list (safe to serialize)."""
    rows: list[dict] = []
    for key, pl in DESK_PLAYLISTS.items():
        rows.append({"category": "desk", "key": key, "name": pl.name, "playlist_id": pl.youtube_playlist_id})
    for key, pl in ANCHOR_PLAYLISTS.items():
        rows.append({"category": "anchor", "key": key, "name": pl.name, "playlist_id": pl.youtube_playlist_id})
    for key, pl in FORMAT_PLAYLISTS.items():
        rows.append({"category": "format", "key": key, "name": pl.name, "playlist_id": pl.youtube_playlist_id})
    for keywords, pl in SERIES_PLAYLISTS:
        rows.append({"category": "series", "keywords": keywords, "name": pl.name, "playlist_id": pl.youtube_playlist_id})
    return rows

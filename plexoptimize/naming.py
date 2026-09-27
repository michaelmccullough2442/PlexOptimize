"""Plex's recommended folder and file naming.

Movies:   Movies/Title (Year) {tmdb-603}/Title (Year) {tmdb-603}.mkv
TV:       TV Shows/Show (Year) {tmdb-1396}/Season 01/Show (Year) - s01e02 - Episode Title.mkv
The {tmdb-ID} tag makes Plex match exactly, so it can never mis-identify the file again.
"""
import re
from pathlib import Path

ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe(name, limit=120):
    name = ILLEGAL.sub(" ", str(name))
    name = name.replace("  ", " ").strip().rstrip(".")
    return name[:limit].strip() or "Unknown"


def movie_path(root, m, ext, edition=None, part=None):
    base = safe(f"{m['title']} ({m['year']})" if m.get("year") else m["title"])
    folder = f"{base} {{tmdb-{m['tmdb_id']}}}"
    fname = folder
    if edition:
        fname += f" {{edition-{safe(edition, 60)}}}"
    if part:
        fname += f" - pt{part}"
    return Path(root, folder, fname + ext)


def episode_path(root, m, season, episode, ext, episode_title=None):
    show = safe(f"{m['title']} ({m['year']})" if m.get("year") else m["title"])
    folder = f"{show} {{tmdb-{m['tmdb_id']}}}"
    season_dir = "Specials" if season == 0 else f"Season {season:02d}"
    if isinstance(episode, list):
        ep = f"s{season:02d}e{episode[0]:02d}-e{episode[-1]:02d}"
    else:
        ep = f"s{season:02d}e{episode:02d}"
    fname = f"{show} - {ep}"
    if episode_title:
        fname += f" - {safe(episode_title, 80)}"
    return Path(root, folder, season_dir, fname + ext)

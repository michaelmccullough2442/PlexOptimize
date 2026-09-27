"""Work out what a file probably is from its name, its folders and its metadata.

Badly named files are the norm, so we build several candidate search queries
(filename, parent folder, grandparent folder, embedded title tag) and let the
TMDB matcher pick whichever one finds a confident hit.
"""
import re
from pathlib import Path

from guessit import guessit

JUNK_FOLDERS = re.compile(
    r"^(movies?|films?|tv|tv shows?|shows?|series|videos?|downloads?|complete|completed|"
    r"new folder( \(\d+\))?|media|plex|torrents?|misc|stuff|to sort|unsorted|temp|"
    r"season \d+|s\d{1,2}|disc ?\d|cd ?\d|extras?|featurettes?|[a-z]:)$",
    re.IGNORECASE,
)
JUNK_TITLE = re.compile(r"^(\d+|[a-f0-9]{8,}|title\s*\d*|track\s*\d*|video\s*\d*|untitled|movie|)$",
                        re.IGNORECASE)
EXTRA_WORDS = re.compile(
    r"\b(sample|trailer|featurette|behind the scenes|deleted scenes?|interview|making of)\b",
    re.IGNORECASE,
)


def _clean(title):
    if not title:
        return None
    title = re.sub(r"[._]+", " ", str(title)).strip(" -")
    return None if JUNK_TITLE.match(title) else title


def guess(path, probe=None):
    p = Path(path)
    parts = [x for x in p.parent.parts[-2:] if not JUNK_FOLDERS.match(x.strip())]
    rel = "/".join(parts + [p.name])
    g = dict(guessit(rel))
    g_file = dict(guessit(p.name))

    kind = g.get("type", "movie")
    # guessit sees "S01E02" / "1x02" in the name; a folder named "Season 1" also means TV.
    if g_file.get("episode") is not None or re.search(r"(^|[\\/])season ?\d+", str(p.parent), re.I):
        kind = "episode"

    candidates = []

    def add(title, year=None, source=""):
        title = _clean(title)
        if title and (title.lower(), year) not in [(c["title"].lower(), c["year"]) for c in candidates]:
            candidates.append({"title": title, "year": year, "source": source})

    add(g.get("title"), g.get("year"), "path")
    add(g_file.get("title"), g_file.get("year"), "filename")
    for folder in reversed(p.parent.parts[-3:]):
        if JUNK_FOLDERS.match(folder.strip()):
            continue
        fg = dict(guessit(folder))
        add(fg.get("title"), fg.get("year"), f"folder:{folder}")
    if probe and probe.get("title_tag"):
        tg = dict(guessit(probe["title_tag"]))
        add(tg.get("title"), tg.get("year"), "embedded title tag")

    episode = g.get("episode", g_file.get("episode"))
    season = g.get("season", g_file.get("season"))
    if kind == "episode" and season is None and episode is not None:
        m = re.search(r"season ?(\d+)", str(p.parent), re.I)
        season = int(m.group(1)) if m else 1

    return {
        "kind": kind,
        "candidates": candidates,
        "season": season,
        "episode": episode,
        "episode_title": g_file.get("episode_title"),
        "edition": g.get("edition"),
        "part": g.get("part") or g.get("cd"),
        "is_extra": bool(EXTRA_WORDS.search(p.stem)),
        "language": str(g_file["subtitle_language"]) if g_file.get("subtitle_language") else None,
    }


def subtitle_suffix(path):
    """Return the '.en.forced' style suffix Plex understands for a subtitle file."""
    stem_parts = Path(path).stem.split(".")
    tail = []
    for piece in reversed(stem_parts[1:]):
        low = piece.lower()
        if re.fullmatch(r"[a-z]{2,3}(-[a-z]{2})?", low) or low in {"forced", "sdh", "cc", "default"}:
            tail.insert(0, low)
        elif low in {"english", "eng"}:
            tail.insert(0, "en")
        else:
            break
    return ("." + ".".join(tail)) if tail else ""

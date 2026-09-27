"""Consolidate a music collection: one copy of every song, in one Plex-style folder tree.

Duplicates are found two ways:
  identical   byte-for-byte the same file (same size + same content fingerprint)
  same song   same artist + album + title (from tags, or the filename/folders when tags are
              missing) with a length within 3 seconds, e.g. an MP3 and a FLAC of one track
The best copy is kept (lossless beats lossy, then higher bitrate) and moved to
    Music/<Album Artist>/<Album>/<NN> - <Title>.ext
Every other copy goes to _PlexOptimize/ToDelete, like every other delete in this tool.

A live version, remix, or the same song on a different album is NOT treated as a duplicate.
Your own recordings (voice memos, call recordings...) are never touched.
"""
import re
from collections import defaultdict
from pathlib import Path

from . import dupes, naming, parse
from .planner import staging
from .tmdb import norm

LOSSLESS = {"flac", "alac", "wavpack", "ape", "tta", "mlp", "truehd"}
TRACK_PREFIX = re.compile(r"^\s*(?:\d{1,2}[-.])?\d{1,3}\s*[-._)]\s*")


def _lossless(codec):
    return bool(codec) and (codec in LOSSLESS or codec.startswith("pcm_") or codec.startswith("dsd_"))


GENERIC_DIRS = re.compile(
    r"^(music|my music|mp3s?|flac|songs?|audio|itunes|itunes media|itunes music|media|"
    r"unknown artist|unknown album|various artists?|compilations?)$", re.IGNORECASE)


def _meaningful(folder):
    name = folder.name.strip()
    return bool(name) and folder.parent != folder and not GENERIC_DIRS.match(name) \
        and not parse.JUNK_FOLDERS.match(name)


def tags(row):
    """Artist / album / title / track, from tags first, then from the path."""
    a = ((row.get("probe") or {}).get("audio")) or {}
    p = Path(row["path"])
    stem = p.stem
    info = {
        "artist": a.get("album_artist") or a.get("artist"),
        "track_artist": a.get("artist") or a.get("album_artist"),
        "album": a.get("album"),
        "title": a.get("title"),
        "track": a.get("track"),
        "disc": a.get("disc"),
        "year": a.get("year"),
        "from_path": False,
    }
    if not info["title"] or not info["track_artist"]:
        m = re.match(r"^\s*(\d{1,3})?\s*[-._]?\s*(.+?)\s+-\s+(.+)$", stem)
        track_no = TRACK_PREFIX.match(stem)
        if m and not info["track_artist"]:  # "01 - Artist - Title" / "Artist - Title"
            info["track_artist"] = info["artist"] = info["artist"] or m.group(2).strip()
            info["title"] = info["title"] or m.group(3).strip()
        info["title"] = info["title"] or TRACK_PREFIX.sub("", stem).strip() or stem
        if track_no and not info["track"]:
            digits = re.findall(r"\d+", track_no.group(0))
            info["track"] = int(digits[-1]) if digits else None
        # Music/<Artist>/<Album>/song.mp3 layout - only trust folders with real-looking names.
        album_dir, artist_dir = p.parent, p.parent.parent
        if not info["album"] and _meaningful(album_dir):
            info["album"] = album_dir.name
            if not info["artist"] and _meaningful(artist_dir):
                info["artist"] = artist_dir.name
                info["track_artist"] = info["track_artist"] or artist_dir.name
        info["from_path"] = True
    return info


def quality(row, music_root):
    a = ((row.get("probe") or {}).get("audio")) or {}
    t = tags(row)
    in_root = row["path"].lower().startswith(str(Path(music_root)).lower())
    complete = sum(bool(t[k]) for k in ("artist", "album", "title", "track")) - t["from_path"]
    return (_lossless(a.get("codec")), a.get("bitrate") or 0, a.get("sample_rate") or 0,
            complete, in_root, row["size"])


def destination(root, t, ext):
    artist = naming.safe(t["artist"], 80)
    album = naming.safe(f"{t['album']} ({t['year']})" if t.get("year") else t["album"], 100)
    name = naming.safe(t["title"], 100)
    if t.get("track"):
        num = f"{t['track']:02d}"
        if t.get("disc") and t["disc"] > 1:
            num = f"{t['disc']}-{num}"
        name = f"{num} - {name}"
    return Path(root, artist, album, name + ext.lower())


def build(inv, music_root, keep="best", log=print):
    songs = inv.all("audio")
    rows = []

    def row(r, action, dest="", group="", notes="", t=None):
        t = t or {}
        rows.append(dict(action=action, source=r["path"], destination=str(dest), group=group,
                         size_mb=round((r["size"] or 0) / 2**20, 1), title=t.get("title") or "",
                         year=t.get("year") or "", health=r["health"], notes=notes,
                         confidence="", tmdb_id="", season="", episode=""))

    candidates = []
    for r in songs:
        if r["personal"]:
            row(r, "skip", notes=f"personal recording ({r['personal_note']})")
        elif r["health"] == "broken":
            row(r, "quarantine", staging(r["path"], "Broken"), notes=r["health_note"])
        else:
            candidates.append(r)

    # 1. Identical files, whatever their names or tags.
    by_size = defaultdict(list)
    for r in candidates:
        by_size[r["size"]].append(r)
    unique = []
    exact_losers = {}
    for same_size in by_size.values():
        if len(same_size) == 1:
            unique.extend(same_size)
            continue
        by_hash = defaultdict(list)
        for r in same_size:
            h = r["quick_hash"]
            if not h:
                try:
                    h = dupes.quick_hash(r["path"], r["size"])
                except OSError:
                    continue
                inv.upsert(r["path"], quick_hash=h)
            by_hash[h].append(r)
        for group in by_hash.values():
            group.sort(key=lambda r: quality(r, music_root), reverse=True)
            unique.append(group[0])
            for loser in group[1:]:
                exact_losers[loser["path"]] = group[0]["path"]
    inv.commit()

    # 2. Same song in different files (formats, bitrates, re-rips).
    buckets = defaultdict(list)
    untagged = []
    for r in unique:
        t = tags(r)
        if not (t["artist"] and t["album"] and t["title"]):
            untagged.append((r, t))
            continue
        key = (norm(t["track_artist"]), norm(t["album"]), norm(TRACK_PREFIX.sub("", t["title"])))
        buckets[key].append((r, t))

    placed = {}
    for (artist, album, title), items in buckets.items():
        # Split one key into clusters by length, so a 3:40 edit and 7:10 extended mix stay separate.
        items.sort(key=lambda x: (x[0].get("probe") or {}).get("duration") or 0)
        clusters = []
        for it in items:
            d = (it[0].get("probe") or {}).get("duration") or 0
            if clusters and abs(d - clusters[-1][-1][2]) <= 3:
                clusters[-1].append((*it, d))
            else:
                clusters.append([(*it, d)])
        for cluster in clusters:
            cluster.sort(key=lambda x: quality(x[0], music_root), reverse=(keep == "best"))
            best, bt, _ = cluster[0]
            gid = f"song-{artist[:20]}-{title[:30]}".replace(" ", "_") if len(cluster) > 1 else ""
            dest = destination(music_root, bt, Path(best["path"]).suffix)
            n, base = 2, dest
            while str(dest).lower() in placed:  # e.g. album + live version with the same title
                dest = base.with_name(f"{base.stem} ({n}){base.suffix}")
                n += 1
            placed[str(dest).lower()] = best["path"]
            same_place = Path(best["path"]) == dest
            row(best, "skip" if same_place else "move", "" if same_place else dest, gid,
                "already in place" if same_place else ("tags from folder/filename - check" if bt["from_path"] else ""),
                bt)
            for r, t, _ in cluster[1:]:
                a = (r.get("probe") or {}).get("audio") or {}
                row(r, "delete", staging(r["path"], "ToDelete"), gid,
                    f"other copy of same song ({a.get('codec')}, {int((a.get('bitrate') or 0) / 1000)} kbps); "
                    f"kept {best['path']}", t)

    for r, t in untagged:
        row(r, "review", group="", t=t,
            notes="missing artist/album - tag it (e.g. MusicBrainz Picard) and rescan, or leave it")

    # Identical copies go last so they point at the keeper.
    for path, kept in exact_losers.items():
        r = inv.get(path)
        row(r, "delete", staging(path, "ToDelete"), "identical", f"identical copy of {kept}", tags(r))

    order = {"review": 0, "quarantine": 1, "delete": 2, "move": 3, "skip": 4}
    rows.sort(key=lambda x: (order.get(x["action"], 9), x["group"], x["source"]))
    return rows

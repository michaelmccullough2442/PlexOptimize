"""Identify files and build a reviewable plan (a CSV you can open in Excel).

Plan actions:
  move        rename/move into the clean Plex library
  review      could not identify confidently - fix with `plexopt fix` or edit the row
  quarantine  broken file - moved to _PlexOptimize/Broken (not deleted)
  delete      duplicate / lower quality copy / sample - moved to _PlexOptimize/ToDelete
  skip        leave alone (your personal media, already in place, etc.)
  keep        the copy that is kept from a duplicate group
"""
import csv
import os
from collections import defaultdict
from pathlib import Path

from . import naming, parse

FIELDS = ["action", "confidence", "source", "destination", "size_mb", "group", "title", "year",
          "tmdb_id", "season", "episode", "health", "notes"]


def identify(inv, tmdb, min_confidence=0, only_missing=True, log=print):
    rows = [r for r in inv.all("video") if r["health"] != "broken" and not r["personal"]]
    todo = [r for r in rows if not (only_missing and r["match"])]
    log(f"Identifying {len(todo)} videos with TMDB...")
    for i, r in enumerate(todo, 1):
        g = parse.guess(r["path"], r["probe"])
        m = tmdb.match(g, r["probe"]) if g["candidates"] else None
        if m and m["type"] == "tv" and g.get("season") is not None and isinstance(g.get("episode"), int):
            m["episode_title"] = tmdb.episode_title(m["tmdb_id"], g["season"], g["episode"])
        inv.upsert(r["path"], guess=g, match=m or {"confidence": 0})
        if i % 25 == 0:
            inv.commit()
            log(f"  ...{i}/{len(todo)}")
    inv.commit()


def quality(r):
    p = r["probe"] or {}
    codec_bonus = 1 if p.get("vcodec") in ("hevc", "h265", "av1") else 0
    return ((p.get("height") or 0), r["health"] == "ok", codec_bonus, p.get("bitrate") or 0, r["size"])


def staging(path, bucket):
    """_PlexOptimize/<bucket>/... on the SAME drive, so moves are instant renames."""
    p = Path(path).absolute()
    root = drive_root(p)
    return root / "_PlexOptimize" / bucket / p.relative_to(root)


def drive_root(path):
    """D:\\ on Windows; the mount point (e.g. /mnt/media) on Linux/Mac."""
    p = Path(path).absolute()
    if p.drive:
        return Path(p.anchor)
    while not os.path.ismount(p) and p.parent != p:
        p = p.parent
    return p


def build(inv, movies_root, tv_root, min_confidence=75, keep="best"):
    plan = []
    placed = defaultdict(list)  # destination key -> [(row, dest, match)]
    videos = inv.all("video")

    for r in videos:
        base = dict(source=r["path"], size_mb=round((r["size"] or 0) / 2**20),
                    health=r["health"], confidence="", destination="", group="",
                    title="", year="", tmdb_id="", season="", episode="", notes="")
        if r["personal"]:
            plan.append({**base, "action": "skip", "notes": f"personal media ({r['personal_note']})"})
            continue
        if r["health"] == "broken":
            plan.append({**base, "action": "quarantine",
                         "destination": str(staging(r["path"], "Broken")), "notes": r["health_note"]})
            continue
        g = r["guess"] or parse.guess(r["path"], r["probe"])
        m = r["override"] or r["match"] or {}
        if g.get("is_extra") and "sample" in Path(r["path"]).name.lower() and base["size_mb"] < 300:
            plan.append({**base, "action": "delete", "destination": str(staging(r["path"], "ToDelete")),
                         "notes": "sample clip"})
            continue
        conf = 100 if r["override"] else m.get("confidence", 0)
        base.update(confidence=conf, title=m.get("title", ""), year=m.get("year") or "",
                    tmdb_id=m.get("tmdb_id", ""))
        if not m.get("tmdb_id") or conf < min_confidence:
            guess_txt = ", ".join(f"{c['title']} ({c['year']})" if c["year"] else c["title"]
                                  for c in g.get("candidates", [])[:3])
            plan.append({**base, "action": "review",
                         "notes": f"low confidence; tried: {guess_txt or 'nothing usable in name'}"})
            continue
        ext = Path(r["path"]).suffix.lower()
        if m["type"] == "tv":
            season = m.get("season", g.get("season"))
            episode = m.get("episode", g.get("episode"))
            if season is None or episode is None:
                plan.append({**base, "action": "review", "notes": "TV show found but no season/episode in name"})
                continue
            dest = naming.episode_path(tv_root, m, int(season), episode, ext, m.get("episode_title"))
            base.update(season=season, episode=episode)
            key = (m["tmdb_id"], "tv", season, str(episode))
        else:
            dest = naming.movie_path(movies_root, m, ext, g.get("edition"), g.get("part"))
            key = (m["tmdb_id"], "movie", g.get("edition"), g.get("part"))
        placed[key].append((r, dest, base))

    # Several files claim the same slot -> keep one, mark others for deletion.
    for key, items in placed.items():
        items.sort(key=lambda x: quality(x[0]), reverse=(keep == "best"))
        gid = f"title-{key[0]}-{key[2] or ''}-{key[3] or ''}".rstrip("-")
        for i, (r, dest, base) in enumerate(items):
            if i == 0:
                same = Path(r["path"]) == dest
                plan.append({**base, "action": "skip" if same else "move",
                             "destination": "" if same else str(dest),
                             "group": gid if len(items) > 1 else "",
                             "notes": "already correctly named" if same else ""})
            else:
                p = r["probe"] or {}
                plan.append({**base, "action": "delete", "group": gid,
                             "destination": str(staging(r["path"], "ToDelete")),
                             "notes": f"other copy of same title ({p.get('height') or '?'}p, "
                                      f"{base['size_mb']} MB); kept {items[0][0]['path']}"})

    # Subtitles follow the video they belong to.
    moves = {Path(p["source"]): p for p in plan if p["action"] in ("move", "quarantine", "delete")}
    for s in inv.all("subtitle"):
        sp = Path(s["path"])
        for vpath, vrow in moves.items():
            if vpath.parent == sp.parent and sp.name.lower().startswith(vpath.stem.lower()):
                dest = Path(vrow["destination"])
                suffix = parse.subtitle_suffix(sp)
                plan.append(dict(action=vrow["action"], confidence=vrow["confidence"], source=str(sp),
                                 destination=str(dest.with_name(dest.stem + suffix + sp.suffix.lower())),
                                 size_mb=0, group=vrow["group"], title=vrow["title"], year=vrow["year"],
                                 tmdb_id=vrow["tmdb_id"], season=vrow["season"], episode=vrow["episode"],
                                 health="ok", notes=f"subtitle for {vpath.name}"))
                break
    order = {"review": 0, "quarantine": 1, "delete": 2, "move": 3, "keep": 4, "skip": 5}
    plan.sort(key=lambda p: (order.get(p["action"], 9), p["source"]))
    return plan


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def summary(rows):
    counts = defaultdict(lambda: [0, 0])
    for r in rows:
        counts[r["action"]][0] += 1
        counts[r["action"]][1] += int(float(r.get("size_mb") or 0))
    return "\n".join(f"  {a:<11} {n:>6} files  {mb / 1024:>9.1f} GB" for a, (n, mb) in sorted(counts.items()))

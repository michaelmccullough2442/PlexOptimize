"""Find media that the normal scan can't see or might be misjudging.

`plexopt scan` only looks at files with known video/audio/picture extensions and skips system,
program and hidden folders. This walks *everything* and reports what might be hiding:

  disc-image     .iso / .img / .bin disc images (often a whole movie or DVD)
  dvd-rip        VIDEO_TS folders (DVD rips: one movie split into many .VOB files)
  bluray-rip     BDMV folders (Blu-ray rips: the movie is the biggest .m2ts in STREAM)
  archive        big .rar / .zip / .7z files, which often hold a movie or an album
  incomplete     unfinished downloads (.part, .!qb, .crdownload ...)
  no-extension   big files with a missing or wrong extension that are really video/audio
  other-audio    audiobooks (.m4b) and odd audio formats the music scan ignores
  skipped-folder media inside folders the scan skips (hidden, AppData, Program Files ...)
  long-personal  "personal" videos over an hour long - maybe a movie the scan mistook for yours
  unidentified   videos that couldn't be matched to a movie or show yet

Nothing is moved or changed; it writes audit.csv and prints a summary.
"""
import csv
import os
from collections import Counter, defaultdict
from pathlib import Path

from . import scanner

DISC_EXT = {".iso", ".img", ".bin", ".nrg", ".mdf", ".cue"}
ARCHIVE_EXT = {".rar", ".zip", ".7z", ".tar", ".gz", ".r00", ".001"}
INCOMPLETE_EXT = {".part", ".!qb", ".!ut", ".crdownload", ".partial", ".download", ".tmp", ".bc!", ".opdownload"}
OTHER_AUDIO_EXT = {".m4b", ".aa", ".aax", ".mid", ".midi", ".amr", ".3ga", ".caf", ".mpc", ".ra", ".ram",
                   ".au", ".mod", ".xm", ".spx", ".m4r"}
SYSTEM_DIRS = {"windows", "$recycle.bin", "system volume information", "node_modules", ".git"}
FIELDS = ["finding", "path", "size_mb", "detail"]
BIG = 50 * 2**20


def _sniff(path):
    """Ask ffprobe what a file with a strange extension really is."""
    raw, _ = scanner.ffprobe(path, timeout=30)
    if not raw:
        return None
    info = scanner.summarize(raw)
    if info["vcodec"] and (info["duration"] or 0) > 60:
        return f"really a video: {info['vcodec']} {info['width']}x{info['height']}, {int(info['duration'] / 60)} min"
    if info.get("audio") and (info["duration"] or 0) > 30:
        return f"really audio: {info['audio']['codec']}, {int(info['duration'] / 60)} min"
    return None


def run(inv, roots, out="audit.csv", log=print):
    findings = []

    def add(kind, path, size, detail=""):
        findings.append({"finding": kind, "path": str(path), "size_mb": round(size / 2**20), "detail": detail})

    skipped_media = defaultdict(lambda: [0, 0])
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            here = Path(dirpath)
            low = here.name.lower()
            if low in SYSTEM_DIRS:
                dirnames[:] = []
                continue
            # Folders `scan` skips: still look inside for media, but just count it.
            skipped = any(part.lower() in scanner.SKIP_DIRS or (part.startswith(".") and len(part) > 1)
                          for part in here.relative_to(root).parts)
            if low == "video_ts":
                size = sum(f.stat().st_size for f in here.glob("*.[vV][oO][bB]"))
                add("dvd-rip", here.parent, size, "DVD rip - convert to one .mkv (e.g. MakeMKV / HandBrake)")
            if low == "bdmv":
                streams = list((here / "STREAM").glob("*.m2ts"))
                if streams:
                    main = max(streams, key=lambda f: f.stat().st_size)
                    add("bluray-rip", here.parent, sum(f.stat().st_size for f in streams),
                        f"Blu-ray rip - main movie is probably {main.name}; remux to .mkv with MakeMKV")
            for name in filenames:
                p = here / name
                ext = p.suffix.lower()
                try:
                    size = p.stat().st_size
                except OSError:
                    continue
                kind = scanner.classify(name)
                if skipped:
                    if kind in ("video", "audio") and size > 1 * 2**20:
                        skipped_media[str(here)][0] += 1
                        skipped_media[str(here)][1] += size
                    continue
                if ext in DISC_EXT and size > BIG:
                    add("disc-image", p, size, "disc image - mount it or rip to .mkv; Plex can't play it")
                elif ext in ARCHIVE_EXT and size > BIG:
                    add("archive", p, size, "compressed archive - may contain a movie, show or album")
                elif ext in INCOMPLETE_EXT and size > BIG:
                    add("incomplete", p, size, "unfinished download - re-download or delete")
                elif ext in OTHER_AUDIO_EXT:
                    add("other-audio", p, size, "audiobook" if ext in {".m4b", ".aa", ".aax"} else f"{ext} audio")
                elif kind is None and size > 100 * 2**20 and ext not in DISC_EXT | ARCHIVE_EXT | INCOMPLETE_EXT \
                        and ext not in {".exe", ".msi", ".dll", ".sys", ".vhd", ".vhdx", ".vmdk", ".pst", ".db",
                                        ".sqlite", ".dmg", ".pkg", ".apk", ".pak", ".bak", ".log"}:
                    what = _sniff(p)
                    if what:
                        add("no-extension", p, size, what + " - give it the right extension and rescan")

    for folder, (n, size) in skipped_media.items():
        add("skipped-folder", folder, size, f"{n} video/audio files in a folder the scan skips")

    for r in inv.all("video"):
        dur = (r["probe"] or {}).get("duration") or 0
        if r["personal"] and dur > 3600:
            add("long-personal", r["path"], r["size"],
                f"{int(dur / 60)} min, flagged personal because: {r['personal_note']} - movie or your own?")
        m = r["match"]
        if not r["personal"] and r["health"] != "broken" and (m is None or not m.get("tmdb_id")):
            add("unidentified", r["path"], r["size"],
                "not looked up yet - run identify" if m is None else "no TMDB match")

    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(findings, key=lambda x: (x["finding"], -x["size_mb"])))

    counts = Counter(x["finding"] for x in findings)
    sizes = Counter()
    for x in findings:
        sizes[x["finding"]] += x["size_mb"]
    kinds = Counter(r["kind"] for r in inv.all())
    log(f"Already in inventory: {kinds.get('video', 0)} videos, {kinds.get('audio', 0)} songs, "
        f"{kinds.get('photo', 0)} pictures")
    log("Possibly missed or misjudged:" if findings else "Nothing missed - the scan saw everything.")
    for k, n in sorted(counts.items()):
        log(f"  {k:<15} {n:>6}  ({sizes[k] / 1024:.1f} GB)")
    log(f"Details: {out}")
    return findings

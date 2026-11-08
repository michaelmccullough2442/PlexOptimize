"""Gather everything worth keeping from old backup drives onto one big drive, without duplicates.

    plexopt collect E:\\ F:\\ --dest G:\\        ->  collect.csv  (then: plexopt apply collect.csv)

Sources are only ever COPIED from. Nothing on a backup drive is moved, renamed or deleted.

What it looks for, and where it goes on the destination drive:

  Steam games     <dest>\\SteamLibrary\\steamapps\\common\\<game>  (+ its appmanifest, so Steam
                  recognises it: Steam > Settings > Storage > Add drive > pick <dest>\\SteamLibrary)
  PC games        <dest>\\Games\\PC\\<game folder or installer>   GOG installers, repacks,
                  anything inside a Games / PC Games / GOG folder
  Disc images     <dest>\\Disc Images\\...   marked REVIEW: an .iso may be a game, a movie or software
  Audiobooks      <dest>\\Audiobooks\\<book folder>               .m4b/.aa/.aax, or audio in an
                  "Audiobooks" folder (one book = one folder, copied whole)
  Ebooks          <dest>\\Books\\<folders as on the backup>      .epub .mobi .azw3 .cbz .cbr ...
  PDFs            <dest>\\PDFs\\<backup name>\\<folders as on the backup>
  Movies/TV/music are NOT copied here: they go through the normal scan -> identify -> plan / music
                  pipeline, which renames them for Plex and picks the best copy (see the guide).

Duplicates: a file is skipped when the destination (or another backup) already has the identical
file. Games are matched by Steam app id, or by folder name + size within 2%.
"""
import csv
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path

from . import dupes, scanner
from .planner import FIELDS

EBOOK_EXT = {".epub", ".mobi", ".azw", ".azw3", ".kfx", ".fb2", ".cbz", ".cbr", ".cb7", ".djvu", ".lit", ".prc"}
AUDIOBOOK_EXT = {".m4b", ".aa", ".aax"}
DISC_EXT = {".iso", ".nrg", ".mdf", ".img", ".cue"}
GAME_DIR = re.compile(r"^(games?|pc|pc games?|gog( games)?|game installers?|installers?|repacks?|gaming|"
                      r"my games|roms?|emulators?)$", re.IGNORECASE)
BOOK_DIR = re.compile(r"(audio ?books?|audible)", re.IGNORECASE)
APP_DIR = re.compile(r"(steamapps|program files|windows|appdata|\$recycle\.bin|system volume information|"
                     r"_plexoptimize|node_modules|\.git)", re.IGNORECASE)
GOG_INSTALLER = re.compile(r"^setup_.+\.(exe|bin)$", re.IGNORECASE)


def _size(path):
    p = Path(path)
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _norm(name):
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def read_acf(path):
    """Steam appmanifest_*.acf -> {"appid", "name", "installdir"}."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    out = {}
    for key in ("appid", "name", "installdir"):
        m = re.search(rf'"{key}"\s+"([^"]*)"', text, re.IGNORECASE)
        if m:
            out[key] = m.group(1)
    return out


def find_items(root):
    """Everything collectable on one drive, as (category, path, title) tuples."""
    root = Path(root)
    items = []
    claimed = set()  # folders already taken whole (games, audiobooks)

    def inside_claimed(p):
        return any(str(p).startswith(c + os.sep) or str(p) == c for c in claimed)

    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
        here = Path(dirpath)
        if here.name.lower() == "steamapps":
            for acf in here.glob("appmanifest_*.acf"):
                info = read_acf(acf)
                game = here / "common" / info.get("installdir", "")
                if info.get("installdir") and game.is_dir():
                    items.append(("steam", game, info.get("name") or game.name, info.get("appid"), acf))
                    claimed.add(str(game))
            dirnames[:] = []  # don't descend: the games are handled above
            continue
        if inside_claimed(here) or (APP_DIR.fullmatch(here.name) and here != root):
            dirnames[:] = []
            continue
        if GAME_DIR.match(here.name):
            containers = []
            for d in list(dirnames):
                if GAME_DIR.match(d) or d.lower() in ("pc", "steam", "epic", "origin", "ubisoft"):
                    containers.append(d)  # e.g. Games\PC\... - look one level deeper
                    continue
                items.append(("game", here / d, d, None, None))
                claimed.add(str(here / d))
            for f in filenames:
                p = here / f
                if p.suffix.lower() in DISC_EXT | {".exe", ".zip", ".rar", ".7z"}:
                    items.append(("game", p, p.stem, None, None))
            dirnames[:] = containers
            continue
        if BOOK_DIR.search(here.name):
            # Each subfolder is one book; loose audio files at this level are single-file books.
            for d in list(dirnames):
                items.append(("audiobook", here / d, d, None, None))
                claimed.add(str(here / d))
            for f in filenames:
                p = here / f
                if scanner.classify(f) == "audio" or p.suffix.lower() in AUDIOBOOK_EXT:
                    items.append(("audiobook", p, p.stem, None, None))
            dirnames[:] = []
            continue
        gog = [f for f in filenames if GOG_INSTALLER.match(f)]
        if gog:  # a folder holding a GOG installer (setup_x.exe + setup_x-1.bin ...) is one game
            items.append(("game", here, here.name, None, None))
            claimed.add(str(here))
            dirnames[:] = []
            continue
        for f in filenames:
            p = here / f
            ext = p.suffix.lower()
            if ext in AUDIOBOOK_EXT:
                items.append(("audiobook", p, p.stem, None, None))
            elif ext in EBOOK_EXT:
                items.append(("ebook", p, p.stem, None, None))
            elif ext == ".pdf":
                items.append(("pdf", p, p.stem, None, None))
            elif ext in DISC_EXT and p.stat().st_size > 50 * 2**20:
                items.append(("disc", p, p.stem, None, None))
            elif scanner.classify(f) in ("video", "audio"):
                items.append(("media", p, p.stem, None, None))
    return items


def destination(dest, cat, path, title, source_root):
    dest = Path(dest)
    rel = Path(path).relative_to(source_root)
    label = Path(source_root).name or Path(source_root).drive.rstrip(":") or "backup"
    if cat == "steam":
        return dest / "SteamLibrary" / "steamapps" / "common" / Path(path).name
    if cat == "game":
        return dest / "Games" / "PC" / Path(path).name
    if cat == "audiobook":
        return dest / "Audiobooks" / Path(path).name
    if cat == "ebook":
        return dest / "Books" / rel
    if cat == "pdf":
        return dest / "PDFs" / label / rel
    if cat == "disc":
        return dest / "Disc Images" / Path(path).name
    return None


def build(sources, dest, log=print):
    dest = Path(dest)
    log(f"Indexing what {dest} already has...")
    have = find_items(dest) if dest.exists() else []
    have_steam = {appid for c, _p, _t, appid, _a in have if c == "steam" and appid}
    have_folders = defaultdict(list)  # normalized name -> sizes (games/audiobooks)
    have_files = defaultdict(list)    # size -> paths
    for c, p, title, appid, _ in have:
        if Path(p).is_dir():
            have_folders[(c, _norm(Path(p).name))].append(_size(p))
        else:
            have_files[Path(p).stat().st_size].append(p)
    if dest.exists():  # media already on the destination counts too
        for path, kind in scanner.walk([str(dest)]):
            try:
                have_files[path.stat().st_size].append(path)
            except OSError:
                pass

    hash_cache = {}

    def qh(p):
        p = str(p)
        if p not in hash_cache:
            try:
                hash_cache[p] = dupes.quick_hash(p, os.path.getsize(p))
            except OSError:
                hash_cache[p] = None
        return hash_cache[p]

    rows = []
    media = defaultdict(int)
    chosen_files = {}  # (size, hash) -> dest of the first copy planned this run
    chosen_folders = {}
    for src_root in sources:
        src_root = Path(src_root)
        log(f"Looking through {src_root}...")
        for cat, path, title, appid, acf in find_items(src_root):
            if cat == "media":
                media[scanner.classify(path.name)] += 1
                continue
            try:
                size = _size(path)
            except OSError:
                continue
            row = dict(action="copy", source=str(path), destination="", size_mb=round(size / 2**20),
                       group=cat, title=title, year="", health="", notes="", confidence="",
                       tmdb_id=appid or "", season="", episode="")
            target = destination(dest, cat, path, title, src_root)
            if path.is_dir():
                key = (cat, _norm(path.name))
                same = [s for s in have_folders.get(key, []) if abs(s - size) <= max(s, size) * 0.02]
                if (cat == "steam" and appid in have_steam) or same:
                    rows.append({**row, "action": "skip", "notes": "already on destination"})
                    continue
                if key in chosen_folders:
                    prev = chosen_folders[key]
                    if size > float(prev["size_mb"]) * 2**20 * 1.02:  # this copy is more complete
                        prev.update(action="skip", notes=f"smaller copy than {path}")
                    else:
                        rows.append({**row, "action": "skip", "notes": f"same as {prev['source']}"})
                        continue
                chosen_folders[key] = row
            else:
                h = qh(path)
                if any(qh(p) == h for p in have_files.get(size, [])):
                    rows.append({**row, "action": "skip", "notes": "identical file already on destination"})
                    continue
                if (size, h) in chosen_files:
                    rows.append({**row, "action": "skip", "notes": f"identical to {chosen_files[(size, h)]}"})
                    continue
                chosen_files[(size, h)] = str(path)
            n, base = 2, target
            while target.exists():  # a different item with the same name is already there
                target = base.with_name(f"{base.stem} ({n}){base.suffix}")
                n += 1
            row["destination"] = str(target)
            if cat == "disc":
                row.update(action="review", notes="disc image: game, movie or software? set action to copy to keep it")
            if cat == "steam":
                row["notes"] = f"Steam app {appid}; manifest copied too"
                rows.append(row)
                rows.append(dict(row, source=str(acf), title=f"{title} (Steam manifest)", size_mb=0,
                                 destination=str(dest / "SteamLibrary" / "steamapps" / Path(acf).name),
                                 notes="lets Steam recognise the game"))
                continue
            rows.append(row)

    order = {"review": 0, "copy": 1, "skip": 2}
    rows.sort(key=lambda r: (order.get(r["action"], 9), r["group"], r["source"]))
    return rows, media


def write(rows, out):
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def summary(rows, media, dest):
    by = defaultdict(lambda: [0, 0, 0, 0])  # copy n, copy MB, skip n, review n
    for r in rows:
        b = by[r["group"]]
        if r["action"] == "copy":
            b[0] += 1
            b[1] += float(r["size_mb"])
        elif r["action"] == "skip":
            b[2] += 1
        else:
            b[3] += 1
    names = {"steam": "Steam games", "game": "PC games", "audiobook": "Audiobooks", "ebook": "Ebooks",
             "pdf": "PDFs", "disc": "Disc images"}
    lines = [f"  {'':<13}{'new':>7}{'GB':>9}{'dupes':>8}{'review':>8}"]
    total = 0
    for g, (n, mb, sk, rv) in sorted(by.items()):
        lines.append(f"  {names.get(g, g):<13}{n:>7}{mb / 1024:>9.1f}{sk:>8}{rv:>8}")
        total += mb
    lines.append(f"  Total to copy: {total / 1024:.1f} GB")
    try:
        free = shutil.disk_usage(dest).free / 2**30
        lines.append(f"  Free on {dest}: {free:.1f} GB" + ("  !! NOT ENOUGH ROOM" if free < total / 1024 else ""))
    except OSError:
        pass
    if media:
        lines.append(f"  Also found {media.get('video', 0)} videos and {media.get('audio', 0)} music files: "
                     "add those with scan -> identify -> plan / music (see guide 'Importing from backups').")
    return "\n".join(lines)

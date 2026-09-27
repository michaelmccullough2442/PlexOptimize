"""Consolidate your photos (and phone/camera videos) into one dated folder tree, minus duplicates.

    Pictures/2019/2019-07/IMG_1234.jpg

The date comes from the camera's EXIF "date taken", the video's recorded date, or a date
in the filename (IMG_20190704_..., Screenshot_2019-07-04..., IMG-20190704-WA0001...).
Anything with no date goes to Pictures/Undated/<the folder it came from>/.

Duplicates removed:
  identical      byte-for-byte the same file; one copy is kept
  smaller copy   the same picture saved at a lower resolution (what WhatsApp, Facebook,
                 email and "export for web" produce); the full-size original is kept

NOT treated as duplicates: burst shots, edits, crops, filters, RAW + JPEG pairs, and
Live Photo stills + their video clip. Those are all kept.
Removed copies go to _PlexOptimize/ToDelete like everything else - nothing is gone until purge.
"""
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import dupes
from .planner import staging

try:
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = None
except ImportError:  # pragma: no cover
    Image = None
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

RAW_EXT = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2", ".raf"}
ARTWORK = {"poster", "fanart", "folder", "cover", "banner", "backdrop", "thumb", "landscape",
           "clearlogo", "logo", "front", "back", "albumart", "albumartsmall", "disc", "cd"}
NAME_DATE = re.compile(r"(?<!\d)((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?!\d)")
MIN_SIDE = 300       # smaller than this is an icon/thumbnail, not a photo
NEAR_BITS = 2        # max difference in the 64-bit picture fingerprint for a "smaller copy"


def _date_from_name(name):
    m = NAME_DATE.search(name)
    if not m:
        return None
    try:
        d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    return d if datetime(1990, 1, 1) <= d <= datetime.now() else None


def _parse_dt(text):
    if not text:
        return None
    text = str(text).strip().replace("\x00", "")
    for fmt, n in (("%Y:%m:%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d %H:%M:%S", 19),
                   ("%Y:%m:%d", 10), ("%Y-%m-%d", 10)):
        try:
            d = datetime.strptime(text[:n], fmt)
        except ValueError:
            continue
        return d if datetime(1990, 1, 1) <= d <= datetime.now() else None
    return None


def dhash(img):
    small = img.convert("L").resize((9, 8), Image.LANCZOS)
    px = small.tobytes()
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return bits


def inspect(path):
    """Width, height, date taken and picture fingerprint of one image."""
    if Image is None:
        raise SystemExit("Pillow is missing: pip install -e . again")
    if Path(path).suffix.lower() in RAW_EXT:
        return {"raw": True}
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            w, h = img.size
            if exif.get(0x0112) in (5, 6, 7, 8):  # rotated 90 degrees
                w, h = h, w
            taken = exif.get_ifd(0x8769).get(36867) or exif.get(306)
            img.draft("RGB", (256, 256))  # fast JPEG decode at reduced size
            fp = dhash(ImageOps.exif_transpose(img))
        d = _parse_dt(taken)
        return {"w": w, "h": h, "taken": d.isoformat() if d else None, "dhash": fp}
    except Exception as e:  # noqa: BLE001 - any decode failure means "can't read"
        return {"error": str(e)[:200]}


def _uf_find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def build(inv, photos_root, include_videos=True, log=print):
    root = Path(photos_root)
    rows = []

    def row(r, action, dest="", group="", notes="", taken=None):
        rows.append(dict(action=action, source=r["path"], destination=str(dest), group=group,
                         size_mb=round((r["size"] or 0) / 2**20, 2), title=Path(r["path"]).name,
                         year=taken.year if taken else "", health=r["health"], notes=notes,
                         confidence="", tmdb_id="", season="", episode=""))

    # Folders that hold movies/shows/music: their images are artwork, not your photos.
    media_dirs = {str(Path(r["path"]).parent) for k in ("video", "audio") for r in inv.all(k)
                  if not r["personal"]}

    photos = inv.all("photo")
    items = []
    todo = [r for r in photos if r["probe"] is None]
    if todo:
        log(f"Reading dates and fingerprints for {len(todo)} pictures...")
    for i, r in enumerate(todo, 1):
        r["probe"] = inspect(r["path"])
        inv.upsert(r["path"], probe=r["probe"])
        if i % 200 == 0:
            inv.commit()
            log(f"  ...{i}/{len(todo)}")
    inv.commit()

    for r in photos:
        p = Path(r["path"])
        info = r["probe"] or {}
        if p.stem.lower() in ARTWORK or not r["personal"]:
            row(r, "skip", notes="artwork, not a photo")
        elif str(p.parent) in media_dirs:
            row(r, "skip", notes="image inside a movie/TV/music folder")
        elif info.get("error"):
            row(r, "review", notes=f"can't open - may be damaged or an unusual format ({info['error'][:80]})")
        elif not info.get("raw") and min(info.get("w") or 0, info.get("h") or 0) < MIN_SIDE:
            row(r, "skip", notes=f"tiny image {info.get('w')}x{info.get('h')} (icon/thumbnail)")
        else:
            items.append(r)
    if include_videos:
        items += [r for r in inv.all("video") if r["personal"]]

    # Dates, shared between same-name siblings (RAW+JPEG, Live Photo still+clip).
    def own_date(r):
        info = r["probe"] or {}
        return (_parse_dt(info.get("taken")) or _parse_dt(info.get("creation_time"))
                or _date_from_name(Path(r["path"]).name))
    sibling_date = {}
    for r in items:
        d = own_date(r)
        key = str(Path(r["path"]).with_suffix("")).lower()
        if d and key not in sibling_date:
            sibling_date[key] = d
    dates = {r["path"]: own_date(r) or sibling_date.get(str(Path(r["path"]).with_suffix("")).lower())
             for r in items}

    # 1. Identical files.
    by_size = defaultdict(list)
    for r in items:
        by_size[r["size"]].append(r)
    unique, losers = [], {}
    for same in by_size.values():
        if len(same) == 1:
            unique += same
            continue
        by_hash = defaultdict(list)
        for r in same:
            h = r["quick_hash"]
            if not h:
                try:
                    h = dupes.quick_hash(r["path"], r["size"])
                except OSError:
                    continue
                inv.upsert(r["path"], quick_hash=h)
            by_hash[h].append(r)
        for group in by_hash.values():
            group.sort(key=lambda r: dupes.keeper_rank(r, [photos_root]))
            unique.append(group[0])
            for loser in group[1:]:
                losers[loser["path"]] = (group[0]["path"], "identical copy")
    inv.commit()

    # 2. Smaller copies of the same picture. Pigeonhole: two 64-bit fingerprints within
    #    NEAR_BITS differ in at most NEAR_BITS of the four 16-bit quarters, so they share one.
    pics = [r for r in unique if (r["probe"] or {}).get("dhash") is not None]
    idx = {r["path"]: i for i, r in enumerate(pics)}
    parent = list(range(len(pics)))
    buckets = defaultdict(list)
    for i, r in enumerate(pics):
        fp = r["probe"]["dhash"]
        for q in range(4):
            buckets[(q, (fp >> (16 * q)) & 0xFFFF)].append(i)

    def near(a, b):
        pa, pb = a["probe"], b["probe"]
        if bin(pa["dhash"] ^ pb["dhash"]).count("1") > NEAR_BITS:
            return False
        ra, rb = pa["w"] / pa["h"], pb["w"] / pb["h"]
        return abs(ra - rb) / max(ra, rb) < 0.01  # same shape: not a crop

    for members in buckets.values():
        if len(members) > 400:  # e.g. thousands of blank/black frames; close pairs share another quarter
            continue
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                i, j = members[x], members[y]
                if near(pics[i], pics[j]):
                    parent[_uf_find(parent, i)] = _uf_find(parent, j)
    clusters = defaultdict(list)
    for i in range(len(pics)):
        clusters[_uf_find(parent, i)].append(pics[i])
    for cluster in clusters.values():
        if len(cluster) < 2:
            continue
        cluster.sort(key=lambda r: (r["probe"]["w"] * r["probe"]["h"], r["size"]), reverse=True)
        best = cluster[0]
        best_px = best["probe"]["w"] * best["probe"]["h"]
        for r in cluster[1:]:
            px = r["probe"]["w"] * r["probe"]["h"]
            # Only a clearly lower-resolution copy of the keeper. Same-size look-alikes
            # (burst shots, near-identical frames) are kept.
            if px < best_px * 0.9 and near(best, r):
                losers[r["path"]] = (best["path"], f"smaller copy ({r['probe']['w']}x{r['probe']['h']} vs "
                                                   f"{best['probe']['w']}x{best['probe']['h']})")
                # Carry a date the copy knows about but the original doesn't.
                dates[best["path"]] = dates.get(best["path"]) or dates.get(r["path"])

    # Point every removed copy at the file that is actually kept.
    for path, (kept, why) in list(losers.items()):
        seen = set()
        while kept in losers and kept not in seen:
            seen.add(kept)
            kept = losers[kept][0]
        losers[path] = (kept, why)

    # 3. Everything that survives goes into the dated tree.
    placed = set()
    for r in items:
        src = Path(r["path"])
        d = dates.get(r["path"])
        if r["path"] in losers:
            kept, why = losers[r["path"]]
            row(r, "delete", staging(src, "ToDelete"), "photo-dupe", f"{why} of {kept}", d)
            continue
        folder = root / f"{d:%Y}" / f"{d:%Y-%m}" if d else root / "Undated" / (src.parent.name or "misc")
        dest = folder / src.name
        n = 2
        while str(dest).lower() in placed or (dest.exists() and dest != src):
            dest = folder / f"{src.stem} ({n}){src.suffix}"
            n += 1
        placed.add(str(dest).lower())
        if dest == src:
            row(r, "skip", notes="already in place", taken=d)
        else:
            row(r, "move", dest, notes="" if d else "no date found - put in Undated", taken=d)

    order = {"review": 0, "delete": 1, "move": 2, "skip": 3}
    rows.sort(key=lambda x: (order.get(x["action"], 9), x["source"]))
    return rows

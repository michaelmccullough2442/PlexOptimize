"""Find duplicate files across all scanned drives.

Two kinds:
  exact    byte-identical copies (same size + same content fingerprint)
  same-title  different files of the same movie/episode (handled in planner.py)

Safety rules, always applied:
  * Your own photos/videos (camera, phone, GoPro, screen recordings...) are never
    marked for deletion.
  * At least one copy of every file is always kept.
  * "Deleting" moves files into a _PlexOptimize/ToDelete folder on the same drive.
    Nothing is gone until you run `plexopt purge` after checking.
"""
import hashlib
from collections import defaultdict
from pathlib import Path

CHUNK = 1 << 20  # 1 MiB


def quick_hash(path, size):
    h = hashlib.blake2b(digest_size=16)
    h.update(str(size).encode())
    with open(path, "rb") as f:
        for offset in {0, max(0, size // 2 - CHUNK // 2), max(0, size - CHUNK)}:
            f.seek(offset)
            h.update(f.read(CHUNK))
    return h.hexdigest()


def full_hash(path):
    h = hashlib.blake2b(digest_size=20)
    with open(path, "rb") as f:
        while chunk := f.read(8 * CHUNK):
            h.update(chunk)
    return h.hexdigest()


def keeper_rank(row, library_roots):
    p = row["path"].lower()
    in_library = any(p.startswith(str(Path(r)).lower()) for r in library_roots)
    in_junk = any(w in p for w in ("download", "temp", "new folder", "copy", "backup", "old"))
    return (not in_library, in_junk, row["personal"] == 0, len(p))


def find_exact(inv, min_size_mb=100, full=False, library_roots=(), log=print):
    min_size = int(min_size_mb * 1024 * 1024)
    by_size = defaultdict(list)
    for row in inv.all():
        if row["size"] and row["size"] >= min_size and row["kind"] in ("video", "photo"):
            by_size[row["size"]].append(row)

    groups = []
    candidates = [rows for rows in by_size.values() if len(rows) > 1]
    log(f"Fingerprinting {sum(len(r) for r in candidates)} files that share a size with another file...")
    for rows in candidates:
        by_hash = defaultdict(list)
        for row in rows:
            key = row["quick_hash"]
            if not key:
                try:
                    key = quick_hash(row["path"], row["size"])
                except OSError:
                    continue
                inv.upsert(row["path"], quick_hash=key)
            if full:
                fkey = row["full_hash"]
                if not fkey:
                    try:
                        fkey = full_hash(row["path"])
                    except OSError:
                        continue
                    inv.upsert(row["path"], full_hash=fkey)
                key = fkey
            by_hash[key].append(row)
        for same in by_hash.values():
            if len(same) > 1:
                same.sort(key=lambda r: keeper_rank(r, library_roots))
                groups.append(same)
        inv.commit()
    return groups


def exact_rows(groups):
    """Turn duplicate groups into plan rows: first of each group is kept."""
    rows = []
    for gid, group in enumerate(groups, 1):
        keep = group[0]
        rows.append(dict(action="keep", source=keep["path"], destination="",
                         size_mb=round(keep["size"] / 2**20), group=f"exact-{gid}",
                         notes="kept copy"))
        for r in group[1:]:
            protected = r["personal"] == 1 or keep["personal"] == 1
            rows.append(dict(
                action="skip" if protected else "delete",
                source=r["path"], destination="",
                size_mb=round(r["size"] / 2**20), group=f"exact-{gid}",
                notes=("PROTECTED personal media (" + (r["personal_note"] or keep["personal_note"] or "") + ")")
                if protected else f"identical copy of {keep['path']}",
            ))
    return rows

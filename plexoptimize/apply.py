"""Carry out a plan CSV. Dry run unless --execute. Every change is journaled for `plexopt undo`."""
import json
import os
import shutil
import time
from pathlib import Path

from .planner import drive_root, staging

ACTIONS = {"move", "quarantine", "delete"}


def _transfer(src, dst, mode):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if mode == "hardlink":
        os.link(src, dst)
    elif mode == "copy":
        shutil.copy2(src, dst)
    else:
        try:
            os.rename(src, dst)  # same drive: instant
        except OSError:
            shutil.copy2(src, dst)  # different drive: copy, verify, then remove
            if dst.stat().st_size != src.stat().st_size:
                dst.unlink()
                raise OSError("size mismatch after copy; source left untouched")
            src.unlink()


def run(rows, execute=False, mode="move", journal="plexoptimize-journal.jsonl", log=print):
    done = skipped = failed = 0
    jf = open(journal, "a", encoding="utf-8") if execute else None
    try:
        for r in rows:
            action = (r.get("action") or "").strip().lower()
            if action not in ACTIONS:
                continue
            src = Path(r["source"])
            dst = Path(r["destination"]) if r.get("destination") else None
            if dst is None:
                if action == "move":
                    continue
                dst = staging(src, "Broken" if action == "quarantine" else "ToDelete")
            # Duplicate deletes always go to staging; library moves honour --mode.
            how = mode if action == "move" else "move"
            if not src.exists():
                skipped += 1
                log(f"  gone     {src}")
                continue
            if dst.exists():
                skipped += 1
                log(f"  exists   {dst}  (not overwriting)")
                continue
            log(f"  {action:<9}{src}\n        -> {dst}")
            if not execute:
                done += 1
                continue
            try:
                _transfer(src, dst, how)
                jf.write(json.dumps({"t": time.time(), "action": action, "mode": how,
                                     "src": str(src), "dst": str(dst)}) + "\n")
                jf.flush()
                done += 1
                _prune_empty(src.parent)
            except OSError as e:
                failed += 1
                log(f"  FAILED   {src}: {e}")
    finally:
        if jf:
            jf.close()
    verb = "done" if execute else "would be done (dry run - add --execute to do it)"
    log(f"\n{done} {verb}, {skipped} skipped, {failed} failed.")


def _prune_empty(folder, depth=3):
    """Remove folders left with nothing but junk (.nfo, .txt, .jpg thumbnails from release groups)."""
    junk = {".nfo", ".txt", ".url", ".sfv", ".md5", ".exe", ".db", ".ini", ".website", ".lnk"}
    for _ in range(depth):
        try:
            entries = list(folder.iterdir())
        except OSError:
            return
        if any(e.is_dir() or e.suffix.lower() not in junk for e in entries):
            return
        for e in entries:
            e.unlink()
        folder.rmdir()
        folder = folder.parent


def undo(journal="plexoptimize-journal.jsonl", log=print):
    lines = Path(journal).read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        e = json.loads(line)
        src, dst = Path(e["src"]), Path(e["dst"])
        if e["mode"] == "move" and dst.exists() and not src.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))
            log(f"  restored {src}")
        elif e["mode"] in ("copy", "hardlink") and dst.exists():
            dst.unlink()
            log(f"  removed  {dst}")
    Path(journal).rename(f"{journal}.undone-{int(time.time())}")


def purge(roots, log=print, execute=False):
    """Permanently delete everything in _PlexOptimize/ToDelete on the given drives."""
    total = 0
    for root in roots:
        target = drive_root(root) / "_PlexOptimize" / "ToDelete"
        if not target.exists():
            continue
        size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
        total += size
        log(f"  {target}: {size / 2**30:.1f} GB")
        if execute:
            shutil.rmtree(target)
    log(f"{'Freed' if execute else 'Would free'} {total / 2**30:.1f} GB"
        + ("" if execute else " (add --execute to permanently delete)"))

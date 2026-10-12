"""Look closely at audio files with no artist or album and decide what they really are.

For each one it gathers the evidence: length, mono/stereo, bitrate, any tags at all, the folder
it sits in, and its neighbours. It gives a verdict:

  song            looks like real music (2-12 min, stereo, music-grade bitrate)
  probably song   music-like but something is unusual (short, long, low bitrate)
  long mix/album  20+ minutes of stereo audio: a DJ mix, concert, or a whole album in one file
  audiobook/podcast  long, mono or low bitrate: spoken word
  recording       mono, low bitrate, phone/recorder style: likely your own recording
  sound effect    under 15 seconds: game/app/notification sounds, ringtones, samples
  damaged         won't play properly

With an AcoustID key (free: https://acoustid.org/new-application) and `fpcalc` installed
(Chromaprint: https://acoustid.org/chromaprint), every file is also fingerprinted and looked up,
which names the real artist/title/album of genuine songs even when the filename is junk.

Nothing is changed; it writes music-check.csv.
"""
import csv
import json
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from . import scanner
from .music import tags

FIELDS = ["verdict", "path", "minutes", "channels", "kbps", "codec", "tags_found", "folder",
          "identified_artist", "identified_title", "identified_album", "match_score", "why"]
GAME_DIRS = re.compile(r"(^|[\\/])(steam|steamapps|games?|sounds?|sfx|samples?|ringtones?|notifications?|"
                       r"alarms?|system sounds|media\\windows|loops?|stems?|fl studio|ableton|presets?)([\\/]|$)",
                       re.IGNORECASE)
SPOKEN_DIRS = re.compile(r"(audiobooks?|podcasts?|books?|lectures?|sermons?|chapters?)", re.IGNORECASE)


def needs_check(row):
    if row["personal"] or row["kind"] != "audio":
        return False
    a = (row.get("probe") or {}).get("audio") or {}
    return not (a.get("artist") or a.get("album_artist")) or not a.get("album")


def verdict(row):
    p = Path(row["path"])
    probe = row.get("probe") or {}
    a = probe.get("audio") or {}
    dur = probe.get("duration") or 0
    mins = dur / 60
    ch = a.get("channels")
    kbps = (a.get("bitrate") or probe.get("bitrate") or 0) / 1000
    lossless = a.get("codec") in ("flac", "alac", "wavpack", "ape") or str(a.get("codec", "")).startswith("pcm_")
    folder = str(p.parent)
    if row["health"] == "broken":
        return "damaged", row["health_note"] or "won't play"
    if dur < 15:
        return "sound effect", f"only {dur:.0f} seconds long"
    if GAME_DIRS.search(folder):
        return "sound effect", "sits in a game/app/sample folder"
    if SPOKEN_DIRS.search(folder) or p.suffix.lower() == ".m4b":
        return "audiobook/podcast", "folder name says audiobook/podcast"
    if ch == 1 and kbps and kbps <= 96 and mins < 20:
        return "recording", f"mono, {kbps:.0f} kbps - phone/voice recorder style"
    if mins >= 20 and (ch == 1 or (kbps and kbps <= 96 and not lossless)):
        return "audiobook/podcast", f"{mins:.0f} min of {'mono' if ch == 1 else f'{kbps:.0f} kbps'} audio - spoken word"
    if mins >= 20:
        return "long mix/album", f"{mins:.0f} min of stereo music-quality audio"
    if 1.5 <= mins <= 12 and (ch or 2) >= 2 and (lossless or kbps >= 128 or not kbps):
        return "song", f"{mins:.1f} min, stereo, {'lossless' if lossless else f'{kbps:.0f} kbps'}"
    return "probably song", f"{mins:.1f} min, {ch or '?'} ch, {kbps:.0f} kbps - unusual for music"


class AcoustID:
    API = "https://api.acoustid.org/v2/lookup"

    def __init__(self, key):
        self.key = key
        self.last = 0.0

    def identify(self, path):
        try:
            out = subprocess.run(["fpcalc", "-json", str(path)], capture_output=True, text=True, timeout=60)
            fp = json.loads(out.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return None
        wait = 0.34 - (time.time() - self.last)  # AcoustID allows 3 requests a second
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()
        body = urllib.parse.urlencode({"client": self.key, "meta": "recordings releasegroups compress",
                                       "duration": int(fp["duration"]), "fingerprint": fp["fingerprint"]})
        try:
            with urllib.request.urlopen(urllib.request.Request(self.API, data=body.encode()), timeout=20) as r:
                data = json.loads(r.read())
        except (OSError, json.JSONDecodeError):
            return None
        for res in sorted(data.get("results", []), key=lambda x: -x.get("score", 0)):
            for rec in res.get("recordings", []):
                if rec.get("title"):
                    groups = rec.get("releasegroups") or [{}]
                    album = next((g.get("title") for g in groups if g.get("type") == "Album"), groups[0].get("title"))
                    return {"artist": ", ".join(a["name"] for a in rec.get("artists", [])),
                            "title": rec["title"], "album": album, "score": round(res["score"], 2)}
        return None


def run(inv, acoustid_key=None, out="music-check.csv", log=print):
    rows = [r for r in inv.all("audio") if needs_check(r)]
    log(f"{len(rows)} audio files have no artist or album tag. Examining them...")
    fp = None
    if acoustid_key:
        if shutil.which("fpcalc"):
            fp = AcoustID(acoustid_key)
        else:
            log("  (fpcalc not found - skipping audio fingerprinting; install Chromaprint to enable it)")
    report = []
    for i, r in enumerate(rows, 1):
        if r["probe"] and "channels" not in ((r["probe"].get("audio")) or {"channels": 0}):
            raw, _ = scanner.ffprobe(r["path"], timeout=30)  # scanned before channels were recorded
            if raw:
                r["probe"] = scanner.summarize(raw)
                inv.upsert(r["path"], probe=r["probe"])
        v, why = verdict(r)
        t = tags(r)
        probe = r["probe"] or {}
        a = probe.get("audio") or {}
        found = {k: a.get(k) for k in ("artist", "album", "title", "genre") if a.get(k)}
        hit = fp.identify(r["path"]) if fp and v in ("song", "probably song", "long mix/album") else None
        if hit and hit["score"] >= 0.8 and v == "probably song":
            v, why = "song", why + "; audio fingerprint matched a known recording"
        report.append({
            "verdict": v, "path": r["path"], "minutes": round((probe.get("duration") or 0) / 60, 1),
            "channels": a.get("channels") or "", "kbps": int((a.get("bitrate") or probe.get("bitrate") or 0) / 1000),
            "codec": a.get("codec") or "", "tags_found": json.dumps(found) if found else "none",
            "folder": str(Path(r["path"]).parent),
            "identified_artist": (hit or {}).get("artist", ""), "identified_title": (hit or {}).get("title", ""),
            "identified_album": (hit or {}).get("album", ""), "match_score": (hit or {}).get("score", ""),
            "why": why if not t["from_path"] or v != "song" else why + f"; filename suggests '{t['title']}'",
        })
        if i % 100 == 0:
            inv.commit()
            log(f"  ...{i}/{len(rows)}")
    inv.commit()

    order = {"song": 0, "probably song": 1, "long mix/album": 2, "audiobook/podcast": 3, "recording": 4,
             "sound effect": 5, "damaged": 6}
    report.sort(key=lambda x: (order.get(x["verdict"], 9), x["folder"], x["path"]))
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(report)

    counts = Counter(x["verdict"] for x in report)
    for k in order:
        if counts.get(k):
            log(f"  {k:<18} {counts[k]:>6}")
    named = sum(1 for x in report if x["identified_title"])
    if fp:
        log(f"  Audio fingerprint identified {named} of them by sound.")
    folders = Counter(x["folder"] for x in report)
    log("Folders with the most unknowns:")
    for folder, n in folders.most_common(10):
        log(f"  {n:>5}  {folder}")
    log(f"Details: {out}")
    return report

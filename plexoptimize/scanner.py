"""Walk drives, probe every media file with ffprobe, and grade its health.

Health grades:
  ok       plays fine as far as we can tell
  suspect  opens, but something is off (tiny bitrate, decode errors mid-file)
  broken   will not open, has no video, zero length, or is truncated
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

VIDEO_EXT = {
    ".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".mpg", ".mpeg", ".ts", ".m2ts",
    ".mts", ".webm", ".flv", ".vob", ".divx", ".3gp", ".ogm", ".rmvb", ".asf",
}
AUDIO_EXT = {
    ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wma", ".wav", ".aiff", ".aif",
    ".alac", ".ape", ".wv", ".mka", ".dsf", ".dff",
}
SUB_EXT = {".srt", ".ass", ".ssa", ".sub", ".idx", ".vtt", ".sup", ".smi"}
PHOTO_EXT = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".bmp", ".tif", ".tiff", ".webp",
    ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2", ".raf",
}

SKIP_DIRS = {
    "$recycle.bin", "system volume information", ".trash", ".trashes", ".spotlight-v100",
    ".fseventsd", "windows", "program files", "program files (x86)", "programdata",
    "appdata", "plex media server", "node_modules", ".git", "_plexoptimize",
}

# Filenames produced by phones, cameras, drones, screen recorders and chat apps.
PERSONAL_NAME = re.compile(
    r"^(img|vid|mov|mvi|dsc|dscn|dscf|dcim|pxl|gopr|gp\d|gh\d|gx\d|dji|p\d{7}|"
    r"screen[ _-]?record|screenshot|signal-|whatsapp|pxl_|mvimg|burst|"
    r"\d{8}[_-]\d{6}|\d{4}-\d{2}-\d{2}[ _]\d{2}[.\-]\d{2})",
    re.IGNORECASE,
)
PERSONAL_DIR = re.compile(
    r"(^|[\\/])(dcim|camera|camera roll|my pictures|pictures|photos|google photos|"
    r"icloud photos|takeout|home videos?|family|gopro|phone backup|snapchat|whatsapp)([\\/]|$)",
    re.IGNORECASE,
)
# Metadata tags cameras and phones write but movie rips basically never have.
PERSONAL_TAGS = (
    "com.apple.quicktime.make", "com.apple.quicktime.model", "com.apple.quicktime.location.iso6709",
    "location", "location-eng", "com.android.version", "com.android.capture.fps", "make", "model",
)
# Voice memos, call and phone recordings, WhatsApp voice notes: your own audio.
PERSONAL_AUDIO = re.compile(
    r"^(voice|new recording|recording|rec[_ -]?\d|memo|aud-|ptt-|call[_ -]|audio_\d|\d{8}[_ -]\d{6})",
    re.IGNORECASE,
)
PERSONAL_AUDIO_DIR = re.compile(
    r"(^|[\\/])(voice memos?|recordings?|call recordings?|whatsapp audio|whatsapp voice notes|"
    r"sound recordings?|voicemail)([\\/]|$)",
    re.IGNORECASE,
)


def have_ffprobe():
    return shutil.which("ffprobe") is not None and shutil.which("ffmpeg") is not None


def classify(path):
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in SUB_EXT:
        return "subtitle"
    if ext in PHOTO_EXT:
        return "photo"
    return None


def walk(roots, exclude=()):
    exclude = [str(Path(e).resolve()).lower() for e in exclude]
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            here = str(Path(dirpath).resolve()).lower()
            dirnames[:] = [
                d for d in dirnames
                if d.lower() not in SKIP_DIRS
                and not d.startswith(".")
                and not any(str(Path(dirpath, d).resolve()).lower().startswith(e) for e in exclude)
            ]
            if any(here.startswith(e) for e in exclude):
                continue
            for name in filenames:
                kind = classify(name)
                if kind:
                    yield Path(dirpath, name), kind


def ffprobe(path, timeout=120):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
             str(path)],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, "ffprobe timed out"
    if out.returncode != 0 or not out.stdout.strip():
        return None, (out.stderr.strip().splitlines() or ["ffprobe could not read file"])[-1][:300]
    try:
        return json.loads(out.stdout), None
    except json.JSONDecodeError:
        return None, "ffprobe returned garbage"


def summarize(raw):
    fmt = raw.get("format", {})
    streams = raw.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and s.get("disposition", {}).get("attached_pic") != 1), None)
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    subs = [s for s in streams if s.get("codec_type") == "subtitle"]
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    for s in streams:
        for k, v in (s.get("tags") or {}).items():
            tags.setdefault(k.lower(), v)

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    return {
        "container": fmt.get("format_name"),
        "duration": num(fmt.get("duration")) or (num(video.get("duration")) if video else None),
        "bitrate": num(fmt.get("bit_rate")),
        "vcodec": video.get("codec_name") if video else None,
        "width": video.get("width") if video else None,
        "height": video.get("height") if video else None,
        "acodecs": [a.get("codec_name") for a in audio],
        "alangs": [(a.get("tags") or {}).get("language") for a in audio],
        "sublangs": [(s.get("tags") or {}).get("language") for s in subs],
        "title_tag": tags.get("title"),
        "creation_time": tags.get("creation_time"),
        "encoder": tags.get("encoder"),
        "camera_tags": sorted(k for k in tags if k in PERSONAL_TAGS),
        "audio": _audio_info(audio, tags) if audio else None,
    }


def _audio_info(audio, tags):
    a = audio[0]

    def num(x):
        try:
            return int(str(x).split("/")[0])
        except (TypeError, ValueError):
            return None

    return {
        "codec": a.get("codec_name"),
        "bitrate": int(a["bit_rate"]) if str(a.get("bit_rate", "")).isdigit() else None,
        "sample_rate": int(a["sample_rate"]) if str(a.get("sample_rate", "")).isdigit() else None,
        "bits": a.get("bits_per_raw_sample") or a.get("bits_per_sample"),
        "artist": tags.get("artist"),
        "album_artist": tags.get("album_artist") or tags.get("albumartist") or tags.get("album artist"),
        "album": tags.get("album"),
        "title": tags.get("title"),
        "track": num(tags.get("track")),
        "disc": num(tags.get("disc")),
        "year": (tags.get("date") or tags.get("year") or "")[:4] or None,
        "genre": tags.get("genre"),
    }


def spot_decode(path, duration, timeout=60):
    """Decode a few seconds at 5%, 50% and 95% through the file.

    Catches the most common broken-download case: a file whose header says it is
    two hours long but whose data stops halfway.
    """
    problems = []
    for frac in (0.05, 0.5, 0.95):
        start = max(0.0, duration * frac)
        try:
            out = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{start:.1f}", "-i", str(path), "-t", "3",
                 "-map", "0:v:0?", "-f", "null", "-"],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            problems.append(f"decode at {int(frac * 100)}% timed out")
            continue
        err = [l for l in out.stderr.splitlines() if l.strip()]
        if out.returncode != 0 or len(err) > 5:
            problems.append(f"decode errors at {int(frac * 100)}%: {(err or ['?'])[-1][:120]}")
    return problems


def grade(size, info, err, decode_problems):
    if size == 0:
        return "broken", "file is empty (0 bytes)"
    if info is None:
        return "broken", err or "unreadable"
    if not info["vcodec"]:
        return "broken", "no video stream"
    if not info["duration"] or info["duration"] < 1:
        return "broken", "no duration (header damaged or incomplete download)"
    expected_min = info["duration"] * 100_000 / 8  # 100 kbit/s floor
    if size < expected_min:
        return "broken", "file is far smaller than its runtime needs (truncated)"
    if len(decode_problems) >= 2 or any("95%" in p for p in decode_problems):
        return "broken", "; ".join(decode_problems)
    if decode_problems:
        return "suspect", "; ".join(decode_problems)
    if info["bitrate"] and info["bitrate"] < 250_000 and (info["height"] or 0) >= 360:
        return "suspect", f"very low bitrate ({int(info['bitrate'] / 1000)} kbit/s)"
    return "ok", ""


def grade_audio(size, info, err):
    if size == 0:
        return "broken", "file is empty (0 bytes)"
    if info is None:
        return "broken", err or "unreadable"
    if not info.get("audio"):
        return "broken", "no audio stream"
    if not info["duration"] or info["duration"] < 1:
        return "broken", "no duration (damaged or incomplete)"
    if size < info["duration"] * 32_000 / 8 * 0.5:  # well under 32 kbit/s = truncated
        return "broken", "file is far smaller than its length needs (truncated)"
    return "ok", ""


def looks_personal_audio(path):
    p = Path(path)
    reasons = []
    if PERSONAL_AUDIO.match(p.name):
        reasons.append("recording-style filename")
    if PERSONAL_AUDIO_DIR.search(str(p.parent)):
        reasons.append("in a recordings/voice memo folder")
    return bool(reasons), "; ".join(reasons)


def looks_personal(path, info=None):
    """True for media you shot yourself (phone, camera, GoPro, drone, screen recording)."""
    p = Path(path)
    reasons = []
    if PERSONAL_NAME.match(p.name):
        reasons.append("camera-style filename")
    if PERSONAL_DIR.search(str(p.parent)):
        reasons.append("in a photos/camera folder")
    if info and info.get("camera_tags"):
        reasons.append("camera metadata: " + ", ".join(info["camera_tags"][:3]))
    return bool(reasons), "; ".join(reasons)


def scan(inv, roots, exclude=(), deep=True, rescan=False, log=print):
    if not have_ffprobe():
        raise SystemExit("ffprobe/ffmpeg not found on PATH. Install ffmpeg first (see README).")
    seen = 0
    probed = 0
    for path, kind in walk(roots, exclude):
        seen += 1
        try:
            st = path.stat()
        except OSError:
            continue
        prev = inv.get(path)
        if prev and not rescan and prev["size"] == st.st_size and prev["mtime"] == st.st_mtime:
            continue
        fields = dict(kind=kind, size=st.st_size, mtime=st.st_mtime, quick_hash=None, full_hash=None,
                      match=None, guess=None)
        if kind == "video":
            raw, err = ffprobe(path) if st.st_size else (None, None)
            info = summarize(raw) if raw else None
            problems = []
            if deep and info and info["duration"] and info["vcodec"]:
                problems = spot_decode(path, info["duration"])
            health, note = grade(st.st_size, info, err, problems)
            personal, pnote = looks_personal(path, info)
            fields.update(probe=info, health=health, health_note=note,
                          personal=int(personal), personal_note=pnote)
            probed += 1
            if health != "ok":
                log(f"  [{health}] {path}  ({note})")
        elif kind == "audio":
            raw, err = ffprobe(path, timeout=30) if st.st_size else (None, None)
            info = summarize(raw) if raw else None
            health, note = grade_audio(st.st_size, info, err)
            personal, pnote = looks_personal_audio(path)
            fields.update(probe=info, health=health, health_note=note,
                          personal=int(personal), personal_note=pnote)
            probed += 1
            if health != "ok":
                log(f"  [{health}] {path}  ({note})")
        elif kind == "photo":
            personal, pnote = looks_personal(path)
            # A photo is personal unless it is obviously Plex artwork (poster/fanart).
            art = path.stem.lower() in {"poster", "fanart", "folder", "cover", "banner", "backdrop",
                                        "thumb", "landscape", "clearlogo", "logo"}
            fields.update(personal=0 if art else 1,
                          personal_note="artwork" if art else (pnote or "photo"), health="ok")
        else:
            fields.update(health="ok")
        inv.upsert(path, **fields)
        if seen % 50 == 0:
            inv.commit()
            log(f"  ...{seen} files seen, {probed} videos/songs probed")
    # Drop rows for files that no longer exist under the scanned roots.
    root_prefixes = [str(Path(r).resolve()) for r in roots]
    for row in inv.all():
        if any(row["path"].startswith(r) for r in root_prefixes) and not os.path.exists(row["path"]):
            inv.delete(row["path"])
    inv.commit()
    log(f"Scan done: {seen} media files seen, {probed} videos/songs probed.")

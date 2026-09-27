"""Music consolidation on generated songs. Needs ffmpeg."""
import shutil
import subprocess
from pathlib import Path

import pytest

from plexoptimize import apply, music, scanner
from plexoptimize.db import Inventory

pytestmark = pytest.mark.skipif(not scanner.have_ffprobe(), reason="ffmpeg not installed")


def song(path, seconds=20, freq=440, codec=None, **tags):
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = []
    for k, v in tags.items():
        meta += ["-metadata", f"{k}={v}"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}",
                    "-t", str(seconds), *meta, *(["-c:a", codec] if codec else []), str(path)],
                   check=True)


def test_music_consolidation(tmp_path):
    d, e = tmp_path / "D", tmp_path / "E"
    tags = dict(artist="Daft Punk", album_artist="Daft Punk", album="Discovery", title="One More Time",
                track="1", date="2001")
    song(d / "old plex" / "Music" / "Daft Punk" / "Discovery" / "01 One More Time.mp3", **tags)
    song(e / "backup" / "music" / "one more time.flac", **tags)
    (e / "Downloads").mkdir(parents=True)
    shutil.copy(d / "old plex" / "Music" / "Daft Punk" / "Discovery" / "01 One More Time.mp3",
                e / "Downloads" / "copy of track.mp3")
    # Same title, much longer: a different version, must not be treated as a duplicate.
    song(d / "stuff" / "omt-live.flac", seconds=40, freq=300, **tags)
    song(d / "Voice Memos" / "New Recording 3.m4a", codec="aac")
    song(d / "Downloads" / "track.mp3", freq=500)  # no tags at all
    (d / "Downloads" / "dead.mp3").write_bytes(b"\xff\xfb" + b"\x00" * 50)

    inv = Inventory(tmp_path / "lib.db")
    scanner.scan(inv, [str(d), str(e)], log=lambda *a: None)
    root = tmp_path / "Plex" / "Music"
    rows = music.build(inv, str(root), log=lambda *a: None)
    by = {Path(r["source"]).name: r for r in rows}

    assert by["one more time.flac"]["action"] == "move"  # lossless wins
    assert by["one more time.flac"]["destination"].endswith(
        str(Path("Daft Punk", "Discovery (2001)", "01 - One More Time.flac")))
    assert by["01 One More Time.mp3"]["action"] == "delete"
    assert by["copy of track.mp3"]["action"] == "delete"
    assert by["omt-live.flac"]["action"] == "move"
    assert by["omt-live.flac"]["destination"].endswith("01 - One More Time (2).flac")
    assert by["New Recording 3.m4a"]["action"] == "skip"
    assert by["track.mp3"]["action"] == "review"
    assert by["dead.mp3"]["action"] == "quarantine"

    apply.run(rows, execute=True, journal=str(tmp_path / "j.jsonl"), log=lambda *a: None)
    assert (root / "Daft Punk" / "Discovery (2001)" / "01 - One More Time.flac").exists()
    assert (d / "Voice Memos" / "New Recording 3.m4a").exists()
    apply.undo(str(tmp_path / "j.jsonl"), log=lambda *a: None)
    assert (e / "backup" / "music" / "one more time.flac").exists()

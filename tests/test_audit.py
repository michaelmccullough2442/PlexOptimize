"""Audit and unknown-music check on generated files. Needs ffmpeg."""
import subprocess
from pathlib import Path

import pytest

from plexoptimize import audit, music_check, scanner
from plexoptimize.db import Inventory

pytestmark = pytest.mark.skipif(not scanner.have_ffprobe(), reason="ffmpeg not installed")


def audio(path, seconds, channels=2, bitrate="192k", freq=440, **tags):
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = [x for k, v in tags.items() for x in ("-metadata", f"{k}={v}")]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}", "-t", str(seconds),
                    "-ac", str(channels), "-b:a", bitrate, *meta, str(path)], check=True)


def test_music_check_verdicts(tmp_path):
    d = tmp_path / "D"
    audio(d / "Downloads" / "track07.mp3", 200)
    audio(d / "Downloads" / "lecture.mp3", 1500, channels=1, bitrate="64k")
    audio(d / "Games" / "Sounds" / "coin.mp3", 2)
    audio(d / "misc" / "untitled 3.mp3", 90, channels=1, bitrate="48k")
    audio(d / "misc" / "mix.mp3", 1500, bitrate="192k")
    audio(d / "Music" / "Tagged" / "fine.mp3", 200, artist="A", album="B", title="C")
    inv = Inventory(tmp_path / "lib.db")
    scanner.scan(inv, [str(d)], log=lambda *a: None)
    rep = {Path(r["path"]).name: r for r in music_check.run(inv, out=str(tmp_path / "mc.csv"), log=lambda *a: None)}
    assert rep["track07.mp3"]["verdict"] == "song"
    assert rep["lecture.mp3"]["verdict"] == "audiobook/podcast"
    assert rep["coin.mp3"]["verdict"] == "sound effect"
    assert rep["untitled 3.mp3"]["verdict"] == "recording"
    assert rep["mix.mp3"]["verdict"] == "long mix/album"
    assert "fine.mp3" not in rep


def test_audit_finds_hidden_media(tmp_path):
    d = tmp_path / "D"
    vts = d / "Old DVDs" / "SOME_MOVIE" / "VIDEO_TS"
    vts.mkdir(parents=True)
    (vts / "VTS_01_1.VOB").write_bytes(b"\0" * 1024)
    (d / "isos").mkdir()
    with open(d / "isos" / "film.iso", "wb") as f:
        f.truncate(60 * 2**20)
    (d / "dl").mkdir()
    with open(d / "dl" / "show.mkv.part", "wb") as f:
        f.truncate(60 * 2**20)
    audio(d / "AppData" / "Roaming" / "Player" / "cache.mp3", 90)
    audio(d / "books" / "novel.m4b", 5)
    inv = Inventory(tmp_path / "lib.db")
    found = {(f["finding"], Path(f["path"]).name) for f in
             audit.run(inv, [str(d)], out=str(tmp_path / "a.csv"), log=lambda *a: None)}
    assert ("dvd-rip", "SOME_MOVIE") in found
    assert ("disc-image", "film.iso") in found
    assert ("incomplete", "show.mkv.part") in found
    assert ("other-audio", "novel.m4b") in found
    assert ("skipped-folder", "Player") in found

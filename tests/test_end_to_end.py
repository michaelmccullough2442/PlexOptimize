"""End-to-end run on generated clips. Needs ffmpeg; TMDB is faked so no network is used."""
import shutil
import subprocess
from pathlib import Path

import pytest

from plexoptimize import apply, dupes, planner, scanner
from plexoptimize.db import Inventory

pytestmark = pytest.mark.skipif(not scanner.have_ffprobe(), reason="ffmpeg not installed")


def clip(path, seconds=30, size="640x360"):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=24",
                    "-f", "lavfi", "-i", "sine", "-t", str(seconds), "-c:v", "libx264", "-b:v", "1500k",
                    "-c:a", "aac", str(path)], check=True)


class FakeTMDB:
    DB = {
        "the matrix": {"type": "movie", "tmdb_id": 603, "title": "The Matrix", "year": 1999},
        "breaking bad": {"type": "tv", "tmdb_id": 1396, "title": "Breaking Bad", "year": 2008},
    }

    def match(self, g, probe):
        for c in g["candidates"]:
            hit = self.DB.get(c["title"].lower())
            if hit:
                return {**hit, "confidence": 95, "from": c["source"]}
        return None

    def episode_title(self, *a):
        return "Pilot"


@pytest.fixture
def drives(tmp_path):
    d1, d2 = tmp_path / "D", tmp_path / "E"
    clip(d1 / "Downloads" / "the.matrix.1999.1080p.bluray.x264-GRP" / "tm-grp.mkv", size="1280x720")
    clip(d2 / "old plex" / "Movies" / "matrix copy" / "The Matrix (1999).mp4")
    clip(d1 / "new folder" / "Breaking.Bad.S01E01.720p.mkv")
    (d1 / "new folder" / "Breaking.Bad.S01E01.720p.en.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nhi\n")
    clip(d1 / "Phone" / "VID_20190704_201512.mp4")
    shutil.copy(d1 / "Phone" / "VID_20190704_201512.mp4", d2 / "VID_20190704_201512.mp4")
    good = d1 / "new folder" / "Breaking.Bad.S01E01.720p.mkv"
    shutil.copy(good, d2 / "bb-dupe.mkv")
    # Truncated download: header claims 30s, data stops early.
    data = good.read_bytes()
    (d1 / "broken" / "Some.Movie.2004.mkv").parent.mkdir(parents=True)
    (d1 / "broken" / "Some.Movie.2004.mkv").write_bytes(data[: len(data) // 5])
    (d1 / "broken" / "garbage.avi").write_bytes(b"<html>not a video</html>" * 100)
    (d1 / "zzz1234.mkv").write_bytes(b"")
    return tmp_path, d1, d2


def test_full_pipeline(drives):
    tmp, d1, d2 = drives
    inv = Inventory(tmp / "lib.db")
    scanner.scan(inv, [str(d1), str(d2)], log=lambda *a: None)
    by = {Path(r["path"]).name: r for r in inv.all()}

    assert by["tm-grp.mkv"]["health"] == "ok"
    assert by["garbage.avi"]["health"] == "broken"
    assert by["zzz1234.mkv"]["health"] == "broken"
    assert by["Some.Movie.2004.mkv"]["health"] == "broken"
    assert by["VID_20190704_201512.mp4"]["personal"] == 1

    # Exact duplicates: personal copies are protected, the episode copy is deletable.
    rows = dupes.exact_rows(dupes.find_exact(inv, min_size_mb=0, log=lambda *a: None))
    acts = {(Path(r["source"]).name, r["action"]) for r in rows}
    assert ("VID_20190704_201512.mp4", "delete") not in acts
    assert ("VID_20190704_201512.mp4", "skip") in acts
    assert any(a == "delete" for n, a in acts if n in ("bb-dupe.mkv", "Breaking.Bad.S01E01.720p.mkv"))

    planner.identify(inv, FakeTMDB(), log=lambda *a: None)
    movies, tv = tmp / "Plex" / "Movies", tmp / "Plex" / "TV Shows"
    plan = planner.build(inv, str(movies), str(tv))
    act = {Path(r["source"]).name: r for r in plan}

    assert act["tm-grp.mkv"]["action"] == "move"  # 720p beats 360p copy
    assert act["tm-grp.mkv"]["destination"].endswith(
        str(Path("The Matrix (1999) {tmdb-603}", "The Matrix (1999) {tmdb-603}.mkv")))
    assert act["The Matrix (1999).mp4"]["action"] == "delete"
    assert act["VID_20190704_201512.mp4"]["action"] == "skip"
    assert act["garbage.avi"]["action"] == "quarantine"
    sub = act["Breaking.Bad.S01E01.720p.en.srt"]
    assert sub["destination"].endswith("Breaking Bad (2008) - s01e01 - Pilot.en.srt")

    planner.write_csv(plan, tmp / "plan.csv")
    rows = planner.read_csv(tmp / "plan.csv")
    apply.run(rows, execute=False, log=lambda *a: None)
    assert (d1 / "Downloads" / "the.matrix.1999.1080p.bluray.x264-GRP" / "tm-grp.mkv").exists()

    journal = tmp / "j.jsonl"
    apply.run(rows, execute=True, journal=str(journal), log=lambda *a: None)
    assert (movies / "The Matrix (1999) {tmdb-603}" / "The Matrix (1999) {tmdb-603}.mkv").exists()
    assert not (d1 / "Downloads" / "the.matrix.1999.1080p.bluray.x264-GRP").exists()  # emptied folder pruned
    assert (d1 / "Phone" / "VID_20190704_201512.mp4").exists()

    apply.undo(str(journal), log=lambda *a: None)
    assert (d1 / "Downloads" / "the.matrix.1999.1080p.bluray.x264-GRP" / "tm-grp.mkv").exists()
    assert (d2 / "old plex" / "Movies" / "matrix copy" / "The Matrix (1999).mp4").exists()

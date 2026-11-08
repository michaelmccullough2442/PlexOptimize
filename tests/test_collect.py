"""Collecting from backup drives onto one destination drive. No ffmpeg needed."""
from pathlib import Path

from plexoptimize import apply, collect


def put(path, data=b"x" * 2048):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def steam_game(lib, appid, name, data):
    put(lib / "steamapps" / f"appmanifest_{appid}.acf",
        f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n\t"installdir"\t\t"{name}"\n}}\n'.encode())
    put(lib / "steamapps" / "common" / name / "game.exe", data)


def test_collect_from_backups(tmp_path):
    e, f, g = tmp_path / "E", tmp_path / "F", tmp_path / "G"
    # Already on the big drive.
    steam_game(g / "SteamLibrary", 400, "Portal", b"p" * 5000)
    put(g / "Books" / "Dune.epub", b"dune" * 1000)
    put(g / "Games" / "PC" / "Doom" / "doom.exe", b"d" * 3000)
    # Backup E.
    steam_game(e / "Program Files (x86)" / "Steam", 400, "Portal", b"p" * 5000)      # dupe
    steam_game(e / "SteamLibrary", 620, "Portal 2", b"q" * 8000)                     # new
    put(e / "Old Stuff" / "Books" / "Dune.epub", b"dune" * 1000)                       # dupe
    put(e / "Old Stuff" / "Books" / "Neuromancer.epub", b"neuro" * 1000)               # new
    put(e / "Audiobooks" / "The Hobbit" / "01.mp3", b"h" * 9000)                       # new book folder
    put(e / "Downloads" / "Project Hail Mary.m4b", b"m" * 9000)                        # new
    put(e / "Games" / "Doom" / "doom.exe", b"d" * 3000)                                # dupe
    put(e / "Games" / "Half-Life" / "hl.exe", b"h" * 3000)                             # new
    put(e / "Taxes" / "2019 return.pdf", b"%PDF" + b"t" * 500)                         # new
    put(e / "Movies" / "Heat.mkv")                                                     # left to plex pipeline
    # Backup F repeats some of E.
    put(f / "Backup" / "Books" / "Neuromancer.epub", b"neuro" * 1000)                  # same as E's
    put(f / "GOG" / "Witcher" / "setup_witcher.exe", b"w" * 4000)                      # new
    with open(put(f / "ISOs" / "mystery.iso"), "wb") as fh:
        fh.truncate(60 * 2**20)

    rows, media = collect.build([str(e), str(f)], str(g), log=lambda *a: None)
    act = {(r["group"], Path(r["source"]).name): r for r in rows}

    assert act[("steam", "Portal")]["action"] == "skip"
    assert act[("steam", "Portal 2")]["action"] == "copy"
    assert act[("steam", "appmanifest_620.acf")]["action"] == "copy"
    assert act[("ebook", "Dune.epub")]["action"] == "skip"
    neuro = [r for r in rows if r["source"].endswith("Neuromancer.epub")]
    assert sorted(r["action"] for r in neuro) == ["copy", "skip"]
    assert act[("audiobook", "The Hobbit")]["action"] == "copy"
    assert act[("audiobook", "Project Hail Mary.m4b")]["action"] == "copy"
    assert act[("game", "Doom")]["action"] == "skip"
    assert act[("game", "Half-Life")]["action"] == "copy"
    assert act[("game", "Witcher")]["action"] == "copy"
    assert act[("pdf", "2019 return.pdf")]["action"] == "copy"
    assert act[("disc", "mystery.iso")]["action"] == "review"
    assert media["video"] == 1

    apply.run(rows, execute=True, journal=str(tmp_path / "j.jsonl"), log=lambda *a: None)
    assert (g / "SteamLibrary" / "steamapps" / "common" / "Portal 2" / "game.exe").exists()
    assert (g / "SteamLibrary" / "steamapps" / "appmanifest_620.acf").exists()
    assert (g / "Audiobooks" / "The Hobbit" / "01.mp3").exists()
    assert (g / "Games" / "PC" / "Half-Life" / "hl.exe").exists()
    assert (e / "Games" / "Half-Life" / "hl.exe").exists()  # backups untouched
    assert not (g / "Disc Images" / "mystery.iso").exists()  # review rows are not copied

    # Running it again finds nothing new.
    again, _ = collect.build([str(e), str(f)], str(g), log=lambda *a: None)
    assert [r for r in again if r["action"] == "copy"] == []

    apply.undo(str(tmp_path / "j.jsonl"), log=lambda *a: None)
    assert not (g / "Games" / "PC" / "Half-Life").exists()
    assert (e / "Games" / "Half-Life" / "hl.exe").exists()

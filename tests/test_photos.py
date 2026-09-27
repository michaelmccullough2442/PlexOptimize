"""Photo consolidation on generated pictures. No ffmpeg needed."""
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from plexoptimize import apply, photos, scanner
from plexoptimize.db import Inventory


def picture(path, size=(1600, 1200), seed=0, taken=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, (20 + seed * 40 % 200, 90, 160))
    d = ImageDraw.Draw(img)
    w, h = size
    for k in range(6):
        x = (seed * 97 + k * 131) % w
        d.ellipse([x, h * k // 8, x + w // 5, h * k // 8 + h // 4], fill=(250 - k * 30, k * 40, 90))
    exif = Image.Exif()
    if taken:
        exif.get_ifd(0x8769)[36867] = taken
    img.save(path, quality=92, exif=exif)


def test_photo_consolidation(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, "have_ffprobe", lambda: True)
    d, e = tmp_path / "D", tmp_path / "E"
    picture(d / "DCIM" / "Camera" / "IMG_1001.jpg", seed=1, taken="2019:07:04 20:15:12")
    (e / "Backup").mkdir(parents=True)
    shutil.copy(d / "DCIM" / "Camera" / "IMG_1001.jpg", e / "Backup" / "IMG_1001.jpg")
    # WhatsApp-style shrunken copy, EXIF stripped.
    with Image.open(d / "DCIM" / "Camera" / "IMG_1001.jpg") as im:
        (d / "WhatsApp Images").mkdir()
        im.resize((800, 600)).save(d / "WhatsApp Images" / "IMG-20190705-WA0003.jpg", quality=70)
    # Burst shot: same size, slightly different - must be kept.
    picture(d / "DCIM" / "Camera" / "IMG_1002.jpg", seed=2, taken="2019:07:04 20:15:13")
    picture(d / "Pictures" / "scan.png", seed=3)  # no date anywhere
    picture(d / "Movies" / "Heat (1995)" / "poster.jpg", seed=4)
    (d / "Pictures" / "broken.jpg").write_bytes(b"\xff\xd8\xff\xe0 not really")
    picture(d / "Pictures" / "icon.png", size=(64, 64), seed=5)

    inv = Inventory(tmp_path / "lib.db")
    scanner.scan(inv, [str(d), str(e)], log=lambda *a: None)
    root = tmp_path / "Pictures"
    rows = photos.build(inv, str(root), log=lambda *a: None)
    by = {(Path(r["source"]).parent.name, Path(r["source"]).name): r for r in rows}

    kept = by[("Camera", "IMG_1001.jpg")]
    assert kept["action"] == "move"
    assert kept["destination"].endswith(str(Path("2019", "2019-07", "IMG_1001.jpg")))
    assert by[("Backup", "IMG_1001.jpg")]["action"] == "delete"
    assert by[("WhatsApp Images", "IMG-20190705-WA0003.jpg")]["action"] == "delete"
    assert "smaller copy" in by[("WhatsApp Images", "IMG-20190705-WA0003.jpg")]["notes"]
    assert by[("Camera", "IMG_1002.jpg")]["action"] == "move"
    assert by[("Pictures", "scan.png")]["destination"].endswith(str(Path("Undated", "Pictures", "scan.png")))
    assert by[("Heat (1995)", "poster.jpg")]["action"] == "skip"
    assert by[("Pictures", "broken.jpg")]["action"] == "review"
    assert by[("Pictures", "icon.png")]["action"] == "skip"

    apply.run(rows, execute=True, journal=str(tmp_path / "j.jsonl"), log=lambda *a: None)
    assert (root / "2019" / "2019-07" / "IMG_1001.jpg").exists()
    assert (root / "2019" / "2019-07" / "IMG_1002.jpg").exists()
    apply.undo(str(tmp_path / "j.jsonl"), log=lambda *a: None)
    assert (e / "Backup" / "IMG_1001.jpg").exists()

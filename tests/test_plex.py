"""Plex-side checks against a fake Plex server (no real Plex or network needed)."""
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from plexoptimize import companions
from plexoptimize.plex import Plex, index_report, rematch, tune

SECTIONS = [
    {"key": "1", "title": "Movies", "type": "movie", "agent": "tv.plex.agents.movie", "refreshing": False,
     "Location": [{"path": "/nonexistent/Movies"}]},
    {"key": "2", "title": "TV Shows", "type": "show", "agent": "tv.plex.agents.series", "refreshing": True,
     "Location": [{"path": "/nonexistent/TV"}]},
    {"key": "3", "title": "Home Videos", "type": "movie", "agent": "com.plexapp.agents.none",
     "Location": [{"path": "/nonexistent/Home"}]},
]


def movie(rk, title, guid, tmdb, file):
    return {"ratingKey": rk, "title": title, "year": 1999, "guid": guid,
            "Guid": [{"id": f"tmdb://{tmdb}"}] if tmdb else [],
            "Media": [{"Part": [{"file": file}]}]}


ITEMS = {
    "1": [movie("10", "The Matrix", "plex://movie/a", 603, "/M/The Matrix (1999) {tmdb-603}/x.mkv"),
          movie("11", "The Matrix Reloaded", "plex://movie/b", 604, "/M/Heat (1995) {tmdb-949}/x.mkv"),
          movie("12", "abc123", "local://12", None, "/M/Alien (1979) {tmdb-348}/x.mkv"),
          movie("13", "Old Thing", "plex://movie/c", 1, "/M/old thing.avi")],
    "2": [{"ratingKey": "20", "title": "Breaking Bad", "guid": "plex://show/x", "Guid": [{"id": "tmdb://1396"}]}],
}
PREFS = [{"id": "FSEventLibraryUpdatesEnabled", "value": False}, {"id": "autoEmptyTrash", "value": True},
         {"id": "HardwareAcceleratedCodecs", "value": True},
         {"id": "GenerateIntroMarkerBehavior", "value": "never", "enumValues": "never:never|asap:asap"},
         {"id": "MusicAnalysisThing", "label": "Analyze audio tracks for sonic features", "value": "never",
          "enumValues": "never:never|scheduled:as a scheduled task|asap:when added"}]


@pytest.fixture
def plex():
    calls = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_PUT(self):
            calls.append(("PUT", self.path))
            self._send({})

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            assert q.get("X-Plex-Token") == ["tok"]
            p = u.path
            if p == "/library/sections":
                return self._send({"MediaContainer": {"Directory": SECTIONS}})
            if p == "/:/prefs":
                return self._send({"MediaContainer": {"Setting": PREFS}})
            if p == "/activities":
                return self._send({"MediaContainer": {"Activity": [{"title": "Scanning", "progress": 40}]}})
            if p.startswith("/library/sections/") and p.endswith("/all"):
                k = p.split("/")[3]
                if "X-Plex-Container-Size" in q:
                    return self._send({"MediaContainer": {"totalSize": 7}})
                return self._send({"MediaContainer": {"Metadata": ITEMS.get(k, [])}})
            if p == "/library/metadata/20":
                return self._send({"MediaContainer": {"Metadata": [
                    {"Location": [{"path": "/TV/Breaking Bad (2008) {tmdb-1396}"}]}]}})
            self.send_response(404)
            self.end_headers()

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    p = Plex(f"http://127.0.0.1:{srv.server_address[1]}", "tok")
    p.calls = calls
    yield p
    srv.shutdown()


def test_index_report_finds_wrong_and_unmatched(plex):
    out = []
    problems = index_report(plex, log=out.append)
    by = {r["title"]: r for r in problems}
    assert by["The Matrix Reloaded"]["status"] == "mismatch"
    assert "tmdb-949" in by["The Matrix Reloaded"]["note"]
    assert by["abc123"]["status"] == "unmatched"
    assert by["Old Thing"]["status"] == "untagged"
    assert "The Matrix" not in by and "Breaking Bad" not in by
    text = "\n".join(out)
    assert "Folder not found: /nonexistent/Movies" in text
    assert "Scan my library automatically' is OFF" in text
    assert "scanning now" in text
    assert "7 items (only movie/TV" in text  # Home Videos only counted, never checked

    rematch(plex, problems, execute=False, log=lambda *a: None)
    assert plex.calls == []
    rematch(plex, problems, execute=True, log=lambda *a: None)
    paths = [c[1].split("?")[0] for c in plex.calls]
    assert paths == ["/library/metadata/11/unmatch", "/library/metadata/11/refresh",
                     "/library/metadata/12/refresh"]


def test_tune_is_dry_run_by_default(plex):
    assert tune(plex, log=lambda *a: None) == {"FSEventLibraryUpdatesEnabled": "1", "autoEmptyTrash": "0",
                                               "MusicAnalysisThing": "scheduled"}
    # GenerateIntroMarkerBehavior: "scheduled" isn't one of this server's options -> left alone
    assert plex.calls == []
    tune(plex, execute=True, log=lambda *a: None)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(plex.calls[0][1]).query)
    assert q["FSEventLibraryUpdatesEnabled"] == ["1"] and q["autoEmptyTrash"] == ["0"]
    assert "GenerateBIFBehavior" not in q  # server doesn't have it -> not touched


def test_companions_skip_personal_libraries(tmp_path):
    out = companions.write(tmp_path / "c", SECTIONS, "SECRET123", "key", tz="America/Chicago", log=lambda *a: None)
    cfg = (out / "kometa" / "config.yml").read_text()
    assert '"Movies":' in cfg and '"TV Shows":' in cfg
    assert "Home Videos" not in cfg
    assert "default: franchise" in cfg and "default: network" in cfg
    assert '# overlay_files' in cfg
    dc = (out / "docker-compose.yml").read_text()
    assert "plex-auto-languages" in dc and "plextraktsync" in dc
    assert "SECRET123" not in dc  # secrets live in .env, not the compose file
    env = (out / ".env").read_text()
    assert "TZ=America/Chicago" in env and "PLEX_TOKEN=SECRET123" in env
    (out / "kometa" / "config.yml").write_text("my edits")
    companions.write(out, SECTIONS, "tok", "key", log=lambda *a: None)
    assert (out / "kometa" / "config.yml").read_text() == "my edits"


def test_compose_is_valid_yaml(tmp_path):
    yaml = pytest.importorskip("yaml")
    out = companions.write(tmp_path, SECTIONS, "tok", "key", log=lambda *a: None)
    svc = yaml.safe_load((out / "docker-compose.yml").read_text())["services"]
    assert set(svc) == {"tautulli", "kometa", "plex-auto-languages", "plextraktsync"}
    assert svc["plextraktsync"]["restart"] == "unless-stopped"  # anchor merged in
    assert yaml.safe_load((out / "kometa" / "config.yml").read_text())["plex"]["token"] == "tok"

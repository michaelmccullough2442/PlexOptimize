"""SQLite inventory shared by every command.

One row per file found on your drives. Scanning is resumable: files whose size
and modification time are unchanged are not re-probed.
"""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path        TEXT PRIMARY KEY,
    kind        TEXT,      -- video | subtitle | photo
    size        INTEGER,
    mtime       REAL,
    probe       TEXT,      -- ffprobe summary (json)
    health      TEXT,      -- ok | suspect | broken
    health_note TEXT,
    personal    INTEGER DEFAULT 0,  -- 1 = looks like your own camera/phone media
    personal_note TEXT,
    guess       TEXT,      -- parsed name info (json)
    match       TEXT,      -- TMDB match (json)
    override    TEXT,      -- manual override (json) set with `plexopt fix`
    quick_hash  TEXT,
    full_hash   TEXT
);
CREATE TABLE IF NOT EXISTS tmdb_cache (
    url  TEXT PRIMARY KEY,
    body TEXT
);
"""

JSON_COLS = ("probe", "guess", "match", "override")


class Inventory:
    def __init__(self, path="library.db"):
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def get(self, path):
        row = self.conn.execute("SELECT * FROM files WHERE path = ?", (str(path),)).fetchone()
        return self._decode(row) if row else None

    def upsert(self, path, **fields):
        for col in JSON_COLS:
            if col in fields and fields[col] is not None and not isinstance(fields[col], str):
                fields[col] = json.dumps(fields[col])
        fields["path"] = str(path)
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        updates = ", ".join(f"{c} = excluded.{c}" for c in fields if c != "path")
        self.conn.execute(
            f"INSERT INTO files ({cols}) VALUES ({marks}) ON CONFLICT(path) DO UPDATE SET {updates}",
            tuple(fields.values()),
        )

    def delete(self, path):
        self.conn.execute("DELETE FROM files WHERE path = ?", (str(path),))

    def all(self, kind=None):
        if kind:
            rows = self.conn.execute("SELECT * FROM files WHERE kind = ? ORDER BY path", (kind,))
        else:
            rows = self.conn.execute("SELECT * FROM files ORDER BY path")
        return [self._decode(r) for r in rows]

    def commit(self):
        self.conn.commit()

    def cache_get(self, url):
        row = self.conn.execute("SELECT body FROM tmdb_cache WHERE url = ?", (url,)).fetchone()
        return json.loads(row["body"]) if row else None

    def cache_put(self, url, body):
        self.conn.execute(
            "INSERT OR REPLACE INTO tmdb_cache (url, body) VALUES (?, ?)", (url, json.dumps(body))
        )

    @staticmethod
    def _decode(row):
        d = dict(row)
        for col in JSON_COLS:
            if d.get(col):
                d[col] = json.loads(d[col])
        return d

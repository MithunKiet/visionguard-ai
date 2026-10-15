"""Bounded, single-process edge journal. SQLite commits precede acknowledgments."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import threading
import time


class JournalFull(RuntimeError):
    pass


class EdgeJournal:
    def __init__(self, directory, identity, *, max_events=10000, max_bytes=512 * 1024 * 1024,
                 min_free_bytes=64 * 1024 * 1024):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        self.path = self.directory / "events.sqlite3"
        self.max_events, self.max_bytes, self.min_free_bytes = max_events, max_bytes, min_free_bytes
        self._mutex = threading.RLock()
        self._closed = False
        self._lock = os.open(self.directory / "owner.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self._lock)
            raise RuntimeError("Edge journal already has an active owner") from None
        try:
            # Create with restrictive permissions before sqlite opens the file.
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            os.chmod(self.path, 0o600)
            with self._db() as db:
                db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                db.execute("""CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,
                    routing_key TEXT NOT NULL, payload TEXT NOT NULL, snapshot BLOB,
                    event_sent INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL,
                    event_due REAL NOT NULL DEFAULT 0, evidence_due REAL NOT NULL DEFAULT 0,
                    event_attempts INTEGER NOT NULL DEFAULT 0, evidence_attempts INTEGER NOT NULL DEFAULT 0)""")
                owner = json.dumps(identity, sort_keys=True)
                old = db.execute("SELECT value FROM metadata WHERE key='identity'").fetchone()
                if old and old[0] != owner:
                    raise RuntimeError("Edge journal belongs to a different worker or enterprise")
                db.execute("INSERT OR IGNORE INTO metadata VALUES ('identity', ?)", (owner,))
        except BaseException:
            self.close()
            raise

    @contextmanager
    def _db(self):
        with self._mutex:
            if self._closed:
                raise RuntimeError("Edge journal is closed")
            db = sqlite3.connect(self.path, timeout=5)
            db.row_factory = sqlite3.Row
            try:
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("PRAGMA synchronous=FULL")
                page_size = db.execute("PRAGMA page_size").fetchone()[0]
                db.execute(f"PRAGMA max_page_count={max(16, self.max_bytes // page_size)}")
                with db:
                    yield db
            finally:
                db.close()

    def close(self):
        with self._mutex:
            if not self._closed:
                self._closed = True
                os.close(self._lock)

    def enqueue(self, routing_key, payload, snapshot=None):
        encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False)
        incoming = len(encoded.encode()) + len(snapshot or b"")
        with self._db() as db:
            existing = db.execute("SELECT payload FROM events WHERE event_id=?", (payload["event_id"],)).fetchone()
            if existing:
                if existing[0] != encoded:
                    raise ValueError("Conflicting event ID")
                return
            count, used = db.execute("SELECT count(*), coalesce(sum(length(CAST(payload AS BLOB))+coalesce(length(snapshot),0)),0) FROM events").fetchone()
            if count >= self.max_events or used + incoming > self.max_bytes:
                raise JournalFull("Edge journal capacity exhausted; event not accepted")
            if shutil.disk_usage(self.directory).free < self.min_free_bytes + incoming:
                raise JournalFull("Edge journal free disk reserve exhausted; event not accepted")
            db.execute("INSERT INTO events(event_id,routing_key,payload,snapshot,created) VALUES(?,?,?,?,?)",
                       (payload["event_id"], routing_key, encoded, snapshot, time.time()))

    def next_due(self, channel):
        if channel not in {"event", "evidence"}:
            raise ValueError("Unknown delivery channel")
        predicate = "event_sent=0" if channel == "event" else "snapshot IS NOT NULL"
        with self._db() as db:
            row = db.execute(f"SELECT * FROM events WHERE {predicate} AND {channel}_due<=? ORDER BY seq LIMIT 1",
                             (time.time(),)).fetchone()
            return dict(row) if row else None

    def succeeded(self, event_id, channel):
        with self._db() as db:
            if channel == "event":
                db.execute("UPDATE events SET event_sent=1 WHERE event_id=?", (event_id,))
            elif channel == "evidence":
                db.execute("UPDATE events SET snapshot=NULL WHERE event_id=?", (event_id,))
            else:
                raise ValueError("Unknown delivery channel")
            db.execute("DELETE FROM events WHERE event_id=? AND event_sent=1 AND snapshot IS NULL", (event_id,))

    def failed(self, event_id, channel):
        if channel not in {"event", "evidence"}:
            raise ValueError("Unknown delivery channel")
        with self._db() as db:
            row = db.execute(f"SELECT {channel}_attempts FROM events WHERE event_id=?", (event_id,)).fetchone()
            if row:
                delay = min(60, 2 ** min(row[0], 6))
                db.execute(f"UPDATE events SET {channel}_attempts={channel}_attempts+1,{channel}_due=? WHERE event_id=?",
                           (time.time() + delay, event_id))

    def stats(self):
        with self._db() as db:
            row = db.execute("""SELECT count(*),coalesce(sum(length(CAST(payload AS BLOB))+coalesce(length(snapshot),0)),0),
                min(created),coalesce(sum(event_sent=0),0),coalesce(sum(snapshot IS NOT NULL),0) FROM events""").fetchone()
            return {"rows": row[0], "bytes": row[1], "oldest_age": max(0, time.time() - row[2]) if row[2] else 0,
                    "events": row[3], "evidence": row[4]}

    def cache_revision(self):
        with self._db() as db:
            row = db.execute("SELECT value FROM metadata WHERE key='cache_revision'").fetchone()
            return int(row[0]) if row else 0

    def save_cache(self, cameras, authorization, revision=None):
        value = json.dumps({"saved_at": time.time(), "authorization": authorization, "cameras": cameras}, allow_nan=False)
        if len(value.encode()) > 8 * 1024 * 1024:
            raise ValueError("Assignment cache too large")
        with self._db() as db:
            row = db.execute("SELECT value FROM metadata WHERE key='cache_revision'").fetchone()
            if revision is not None and revision != (int(row[0]) if row else 0):
                return False
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('assignments', ?)", (value,))
            return True

    def clear_cache(self):
        with self._db() as db:
            db.execute("DELETE FROM metadata WHERE key='assignments'")
            db.execute("INSERT INTO metadata VALUES ('cache_revision','1') ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")

    def load_cache(self, max_age, authorization):
        with self._db() as db:
            row = db.execute("SELECT value FROM metadata WHERE key='assignments'").fetchone()
            if not row:
                return []
            record = json.loads(row[0])
            age = time.time() - record["saved_at"]
            if max_age <= 0 or not 0 <= age < max_age or record["authorization"] != authorization:
                return []
            return record["cameras"]

import json
import os
import sqlite3
from pathlib import Path
from datetime import timedelta

from .model import iso


class Suppressed(Exception):
    pass


class Ledger:
    """Atomic reservations survive restarts and concurrent connector processes.

    Every attempted submission consumes a local slot, including ambiguous
    failures. The count is deliberately stricter than completed-summary quota.
    """
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        path.chmod(0o600)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS attempts (
              event_id TEXT PRIMARY KEY, camera_id TEXT NOT NULL,
              reserved_at TEXT NOT NULL, day TEXT NOT NULL,
              status TEXT NOT NULL, trigger_json TEXT NOT NULL,
              remote_event_id TEXT, detail TEXT);
            CREATE TABLE IF NOT EXISTS controls (key TEXT PRIMARY KEY, value TEXT);
        """)

    def close(self):
        self.db.close()

    def contains(self, event_id):
        return bool(self.db.execute("SELECT 1 FROM attempts WHERE event_id=?", (event_id,)).fetchone())

    def check_ready(self, event_id):
        if self.contains(event_id):
            raise Suppressed("duplicate")
        if self.db.execute("SELECT 1 FROM controls WHERE key='halt'").fetchone():
            raise Suppressed("halted_pending_operator_review")
        if self.db.execute("SELECT 1 FROM attempts WHERE status='reserved'").fetchone():
            raise Suppressed("unfinished_attempt_pending_operator_review")

    def reserve(self, trigger, now, *, daily_cap=10, cooldown=120):
        if type(daily_cap) is not int or type(cooldown) is not int or not 1 <= daily_cap <= 50 or cooldown < 30:
            raise ValueError("Test cap must be 1..50 and cooldown at least 30 seconds")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.check_ready(trigger.event_id)
            if self.db.execute("SELECT 1 FROM attempts WHERE camera_id=? AND reserved_at>?",
                               (trigger.camera_id, iso(now-timedelta(seconds=cooldown)))).fetchone():
                raise Suppressed("camera_cooldown")
            count = self.db.execute("SELECT count(*) FROM attempts WHERE day=?",
                                    (now.date().isoformat(),)).fetchone()[0]
            if count >= daily_cap:
                raise Suppressed("daily_test_cap")
            self.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,NULL,NULL)",
                            (trigger.event_id, trigger.camera_id, iso(now),
                             now.date().isoformat(), "reserved", json.dumps(trigger.record())))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def finish(self, event_id, status, remote_id=None, detail=None, halt=False):
        with self.db:
            self.db.execute("UPDATE attempts SET status=?,remote_event_id=?,detail=? WHERE event_id=?",
                            (status, remote_id, detail, event_id))
            if halt:
                self.db.execute("INSERT OR REPLACE INTO controls VALUES ('halt',?)", (detail,))

    def resume(self):
        with self.db:
            self.db.execute("DELETE FROM controls WHERE key='halt'")
            self.db.execute("UPDATE attempts SET status='reviewed_unknown' WHERE status='reserved'")

    def report(self):
        return {"attempts": [dict(r) for r in self.db.execute(
                    "SELECT event_id,camera_id,reserved_at,status,remote_event_id,detail FROM attempts ORDER BY reserved_at")],
                "halted": bool(self.db.execute("SELECT 1 FROM controls WHERE key='halt'").fetchone()),
                "hafnia_completed_summaries": "unverified; inspect gateway history and quota"}

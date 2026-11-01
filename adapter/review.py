"""Local operator cases from scoped native camera review events; no remote writes."""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from .model import UTC, guid, iso
from .stream import event_metadata


class ReviewQueue:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        Path(path).chmod(0o600)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS cases (
            id TEXT PRIMARY KEY, camera TEXT NOT NULL, event_time TEXT NOT NULL,
            scenario TEXT NOT NULL, priority INTEGER NOT NULL, status TEXT NOT NULL,
            received_at TEXT NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS audit (
            sequence INTEGER PRIMARY KEY, case_id TEXT NOT NULL,
            at TEXT NOT NULL, action TEXT NOT NULL, note TEXT NOT NULL)""")
        self.db.commit()

    def ingest(self, message, config):
        if "id" not in message:
            return message
        e = event_metadata(message)
        if (e["source"] != "cameras/" + guid(config["camera_id"]) or
                e["type"] not in {guid(t) for t in config["watch_event_type_ids"]} or
                e["type"] == guid(config["trigger_event_type_id"])):
            return {"status": "ignored", "reason": "not_a_scoped_review_event"}
        now = iso(datetime.now(UTC))
        priority = 1 if config["scenario"] in ("school_gate_break_in_night", "person_on_railway_tracks") else 2
        with self.db:
            added = self.db.execute("INSERT OR IGNORE INTO cases VALUES (?,?,?,?,?,?,?)",
                (e["id"], e["source"], e["time"], config["scenario"], priority, "new", now)).rowcount
            if added:
                self.db.execute("INSERT INTO audit(case_id,at,action,note) VALUES (?,?,?,?)",
                    (e["id"], now, "created", "Native review event; verify AI bookmark and recording"))
        return {"status": "case_created" if added else "duplicate", "case_id": e["id"]}

    def transition(self, case_id, action, note="", *, footage_reviewed=False):
        case_id = guid(case_id)
        if not isinstance(note, str) or len(note) > 1000:
            raise ValueError("Note must be at most 1000 characters")
        with self.db:
            row = self.db.execute("SELECT status FROM cases WHERE id=?", (case_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown case")
            allowed = {"acknowledge": ({"new"}, "reviewing"),
                       "follow_up": ({"reviewing"}, "follow_up"),
                       "close": ({"reviewing", "follow_up"}, "closed")}
            if action not in allowed or row[0] not in allowed[action][0]:
                raise ValueError("Invalid review transition")
            if action in {"follow_up", "close"} and not note.strip():
                raise ValueError("Record the evidence and next action")
            if action == "close" and not footage_reviewed:
                raise ValueError("Review the recording before closing")
            status = allowed[action][1]
            changed = self.db.execute("UPDATE cases SET status=? WHERE id=? AND status=?",
                                      (status, case_id, row[0])).rowcount
            if changed != 1:
                raise ValueError("Case changed; refresh before acting")
            self.db.execute("INSERT INTO audit(case_id,at,action,note) VALUES (?,?,?,?)",
                (case_id, iso(datetime.now(UTC)), action, note.strip()))
        return {"case_id": case_id, "status": status}

    def report(self):
        return {"cases": [dict(r) for r in self.db.execute(
            "SELECT * FROM cases ORDER BY CASE WHEN status='closed' THEN 1 ELSE 0 END, priority, received_at")],
            "audit": [dict(r) for r in self.db.execute("SELECT * FROM audit ORDER BY sequence")],
            "scope": "Local review queue; does not change XProtect alarm state"}

    def close(self):
        self.db.close()

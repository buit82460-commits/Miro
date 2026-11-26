"""SQLite storage layer with migrations."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_request_id ON tasks(request_id);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    sequence INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    type TEXT NOT NULL,
    data_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(task_id, sequence)
);
"""


class TaskStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self._db.executescript(SCHEMA_V1)
        row = self._db.execute("SELECT MAX(version) v FROM schema_version").fetchone()
        if row["v"] is None:
            self._db.execute("INSERT INTO schema_version(version) VALUES (1)")
            self._db.commit()

    def upsert_task(self, record: dict) -> None:
        self._db.execute(
            "INSERT INTO tasks(id, request_id, fingerprint, status, revision, record_json, created_at, updated_at)"
            " VALUES(?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status, revision=excluded.revision,"
            " record_json=excluded.record_json, updated_at=excluded.updated_at",
            (record["id"], record["request_id"], record["fingerprint"], record["status"],
             record["revision"], json.dumps(record, ensure_ascii=False),
             record["created_at"], record["updated_at"]),
        )
        self._db.commit()

    def get_by_id(self, task_id: str) -> dict | None:
        row = self._db.execute("SELECT record_json FROM tasks WHERE id=?", (task_id,)).fetchone()
        return json.loads(row["record_json"]) if row else None

    def get_by_request_id(self, request_id: str) -> dict | None:
        row = self._db.execute("SELECT record_json FROM tasks WHERE request_id=?", (request_id,)).fetchone()
        return json.loads(row["record_json"]) if row else None

    def append_event(self, task_id: str, sequence: int, timestamp: str, type: str, data: dict) -> int:
        cur = self._db.execute(
            "INSERT INTO events(task_id, sequence, timestamp, type, data_json) VALUES(?,?,?,?,?)",
            (task_id, sequence, timestamp, type, json.dumps(data, ensure_ascii=False)),
        )
        self._db.commit()
        return cur.lastrowid

    def find_active_by_dedupe(self, dedupe_key: str) -> dict | None:
        """Job cu dang active co cung dedupe-key (T2: port A _start_render dedupe).

        Chi xet queued/running/stop_requested; terminal/needs_attention khong
        dedupe de timeline moi luon tao job moi. Tra ve ban cu nhat.
        """
        rows = self._db.execute(
            "SELECT record_json FROM tasks"
            " WHERE status IN ('queued','running','stop_requested')"
            " ORDER BY created_at").fetchall()
        for row in rows:
            record = json.loads(row["record_json"])
            if record.get("dedupe_key") == dedupe_key:
                return record
        return None

    def events(self, task_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT id, task_id, sequence, timestamp, type, data_json FROM events"
            " WHERE task_id=? ORDER BY sequence", (task_id,)).fetchall()
        return [{"id": r["id"], "task_id": r["task_id"], "sequence": r["sequence"],
                 "timestamp": r["timestamp"], "type": r["type"],
                 "data": json.loads(r["data_json"])} for r in rows]

    def recent(self, limit: int = 20) -> list[dict]:
        """Task moi nhat de UI doc lap liet ke (read-only, khong doi state)."""
        try:
            n = max(1, min(int(limit), 100))
        except (TypeError, ValueError):
            n = 20
        rows = self._db.execute(
            "SELECT record_json FROM tasks ORDER BY created_at DESC LIMIT ?",
            (n,)).fetchall()
        return [json.loads(r["record_json"]) for r in rows]

    def close(self) -> None:
        self._db.close()

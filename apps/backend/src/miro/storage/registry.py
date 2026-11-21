"""Persistent stores for renders + publications (SQLite).

Thay dict RAM o routers/renders.py + routers/publisher.py: restart BE
khong mat du lieu, E2E chay lai van dung semantics idempotent.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path


def _db_path(name: str) -> Path:
    root = Path(os.environ.get("MIRO_BE_DB_DIR", r"C:\Miro\var"))
    root.mkdir(parents=True, exist_ok=True)
    return root / name


class RenderStore:
    """request_id PK, render_id deterministic rnd_<request_id>."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS renders (
        request_id TEXT PRIMARY KEY,
        render_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        expected_revision INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        spec_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'queued',
        created_at REAL NOT NULL
    );
    """

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else _db_path("renders.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(self.path), check_same_thread=False)
        db.executescript(self.SCHEMA)
        db.commit()
        self._db = db

    def create(self, request_id: str, project_id: str, expected_revision: int,
               content_hash: str, spec: dict) -> tuple[dict, bool]:
        row = self._db.execute(
            "SELECT render_id, project_id, expected_revision, content_hash, status"
            " FROM renders WHERE request_id=?", (request_id,)).fetchone()
        if row:
            rid, pid, rev, ch, status = row
            if pid == project_id and rev == expected_revision and ch == content_hash:
                return {"render_id": rid, "status": status, "replayed": True}, True
            raise KeyError(rid)  # 409: request_id da dung voi noi dung khac
        rid = f"rnd_{request_id}"
        self._db.execute(
            "INSERT INTO renders(request_id, render_id, project_id, expected_revision,"
            " content_hash, spec_json, status, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (request_id, rid, project_id, expected_revision, content_hash,
             json.dumps(spec or {}, ensure_ascii=False), "queued", time.time()))
        self._db.commit()
        return {"render_id": rid, "status": "queued", "replayed": False}, False

    def get(self, render_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT render_id, status FROM renders WHERE render_id=?",
            (render_id,)).fetchone()
        if not row:
            return None
        return {"render_id": row[0], "status": row[1], "replayed": False}


class PublicationStore:
    """Khoa luy dang = cap (publication_id, attempt_id)."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS publications (
        publication_id TEXT NOT NULL,
        attempt_id TEXT NOT NULL,
        render_id TEXT NOT NULL,
        channel TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        created_at REAL NOT NULL,
        PRIMARY KEY (publication_id, attempt_id)
    );
    """

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else _db_path("publications.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(self.path), check_same_thread=False)
        db.executescript(self.SCHEMA)
        db.commit()
        self._db = db

    def publish(self, publication_id: str, attempt_id: str,
                render_id: str, channel: str) -> tuple[dict, bool]:
        row = self._db.execute(
            "SELECT publication_id, attempt_id, status FROM publications"
            " WHERE publication_id=? AND attempt_id=?",
            (publication_id, attempt_id)).fetchone()
        if row:
            return {"publication_id": row[0], "attempt_id": row[1],
                    "status": row[2], "replayed": True}, True
        self._db.execute(
            "INSERT INTO publications(publication_id, attempt_id, render_id,"
            " channel, status, created_at) VALUES(?,?,?,?,?,?)",
            (publication_id, attempt_id, render_id, channel, "queued", time.time()))
        self._db.commit()
        return {"publication_id": publication_id, "attempt_id": attempt_id,
                "status": "queued", "replayed": False}, False

    def list_by_publication(self, publication_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT publication_id, attempt_id, status FROM publications"
            " WHERE publication_id=? ORDER BY created_at",
            (publication_id,)).fetchall()
        return [{"publication_id": r[0], "attempt_id": r[1],
                 "status": r[2], "replayed": False} for r in rows]

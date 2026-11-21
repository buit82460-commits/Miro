"""LibraryStore — SQLite persistence cho asset/collection/quan he su dung."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'video',
    size INTEGER NOT NULL DEFAULT 0,
    tags_json TEXT NOT NULL DEFAULT '[]',
    collections_json TEXT NOT NULL DEFAULT '[]',
    archived INTEGER NOT NULL DEFAULT 0,
    missing INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_assets_sha ON assets(sha256);
CREATE TABLE IF NOT EXISTS collections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    asset_ids_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS asset_renders (
    asset_id TEXT NOT NULL,
    render_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    at REAL NOT NULL,
    PRIMARY KEY (asset_id, render_id)
);
CREATE TABLE IF NOT EXISTS render_posts (
    render_id TEXT NOT NULL,
    publication_id TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (render_id, publication_id)
);
"""


class LibraryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.path))
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    # ---- assets ----
    def upsert_asset(self, asset: dict) -> None:
        self._db.execute(
            "INSERT INTO assets(id, sha256, path, name, kind, size, tags_json,"
            " collections_json, archived, missing) VALUES(?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET path=excluded.path, name=excluded.name,"
            " kind=excluded.kind, size=excluded.size, tags_json=excluded.tags_json,"
            " collections_json=excluded.collections_json, archived=excluded.archived,"
            " missing=excluded.missing",
            (asset["id"], asset["sha256"], asset["path"], asset["name"],
             asset.get("kind", "video"), asset.get("size", 0),
             json.dumps(asset.get("tags", []), ensure_ascii=False),
             json.dumps(asset.get("collections", []), ensure_ascii=False),
             1 if asset.get("archived") else 0, 1 if asset.get("missing") else 0),
        )
        self._db.commit()

    def get_by_id(self, asset_id: str) -> dict | None:
        row = self._db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
        return self._row_asset(row) if row else None

    def get_by_sha(self, sha256: str) -> dict | None:
        row = self._db.execute("SELECT * FROM assets WHERE sha256=?", (sha256,)).fetchone()
        return self._row_asset(row) if row else None

    def list_assets(self, include_archived: bool = False) -> list[dict]:
        sql = "SELECT * FROM assets" if include_archived else "SELECT * FROM assets WHERE archived=0"
        return [self._row_asset(r) for r in self._db.execute(sql).fetchall()]

    def delete_asset(self, asset_id: str) -> None:
        self._db.execute("DELETE FROM assets WHERE id=?", (asset_id,))
        self._db.execute("DELETE FROM asset_renders WHERE asset_id=?", (asset_id,))
        self._db.commit()

    @staticmethod
    def _row_asset(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"], "sha256": row["sha256"], "path": row["path"],
            "name": row["name"], "kind": row["kind"], "size": row["size"],
            "tags": json.loads(row["tags_json"]), "collections": json.loads(row["collections_json"]),
            "archived": bool(row["archived"]), "missing": bool(row["missing"]),
        }

    # ---- collections ----
    def save_collection(self, col_id: str, name: str, asset_ids: list[str]) -> None:
        self._db.execute(
            "INSERT INTO collections(id, name, asset_ids_json) VALUES(?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET name=excluded.name, asset_ids_json=excluded.asset_ids_json",
            (col_id, name, json.dumps(asset_ids, ensure_ascii=False)),
        )
        self._db.commit()

    def get_collection(self, col_id: str) -> dict | None:
        row = self._db.execute("SELECT * FROM collections WHERE id=?", (col_id,)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "name": row["name"], "asset_ids": json.loads(row["asset_ids_json"])}

    # ---- usage links ----
    def link_render(self, asset_id: str, render_id: str, project_id: str = "") -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO asset_renders(asset_id, render_id, project_id, at) VALUES(?,?,?,?)",
            (asset_id, render_id, project_id, time.time()),
        )
        self._db.commit()

    def link_post(self, render_id: str, publication_id: str, platform: str = "", url: str = "") -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO render_posts(render_id, publication_id, platform, url) VALUES(?,?,?,?)",
            (render_id, publication_id, platform, url),
        )
        self._db.commit()

    def renders_for_asset(self, asset_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT render_id, project_id FROM asset_renders WHERE asset_id=?", (asset_id,)).fetchall()
        return [{"render_id": r["render_id"], "project_id": r["project_id"]} for r in rows]

    def assets_for_render(self, render_id: str) -> list[str]:
        rows = self._db.execute(
            "SELECT asset_id FROM asset_renders WHERE render_id=?", (render_id,)).fetchall()
        return [r["asset_id"] for r in rows]

    def posts_for_render(self, render_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT publication_id, platform, url FROM render_posts WHERE render_id=?", (render_id,)).fetchall()
        return [{"publication_id": r["publication_id"], "platform": r["platform"], "url": r["url"]} for r in rows]

    def posts_for_asset(self, asset_id: str) -> list[dict]:
        out: list[dict] = []
        for link in self.renders_for_asset(asset_id):
            out.extend(self.posts_for_render(link["render_id"]))
        return out

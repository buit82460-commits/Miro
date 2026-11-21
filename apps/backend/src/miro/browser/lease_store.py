"""SQLite lease store: single-owner, fence/token/TTL. Stdlib only.

Rút gọn từ dubtool shared/browser_contracts.py (SharedStore):
- 1 resource đúng 1 owner tại 1 thời điểm (BEGIN IMMEDIATE + PRIMARY KEY).
- Mỗi lần acquire tăng fence; token_hash xác thực chủ lease.
- Hết TTL -> lease coi như hết hiệu lực, owner mới được acquire (fence+1).
- validate/renew/release đều kiểm tra fence + token, sai -> LeaseLost.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from pathlib import Path

from miro.browser.errors import LeaseBusy, LeaseLost, RegistryError

SCHEMA = """
CREATE TABLE IF NOT EXISTS records(kind TEXT NOT NULL, id TEXT NOT NULL,
    data TEXT NOT NULL, PRIMARY KEY(kind, id));
CREATE TABLE IF NOT EXISTS leases(resource TEXT PRIMARY KEY, fence INTEGER NOT NULL,
    owner TEXT NOT NULL, token_hash TEXT, expires REAL NOT NULL, state TEXT NOT NULL);
"""


def tab_resource(instance_id: str, target_id: str) -> str:
    return f"tab:{instance_id}:{target_id}"


class LeaseStore:
    def __init__(self, file: str | Path, *, clock=time.time) -> None:
        self.file = Path(file)
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise RegistryError("REGISTRY_UNAVAILABLE: storage directory unavailable") from None
        self.clock = clock
        try:
            db = sqlite3.connect(str(self.file), timeout=5)
            try:
                db.executescript(SCHEMA)
                db.commit()
            finally:
                db.close()
        except (sqlite3.Error, OSError):
            raise RegistryError("REGISTRY_UNAVAILABLE: cannot open lease store") from None

    @contextlib.contextmanager
    def transaction(self):
        try:
            db = sqlite3.connect(str(self.file), timeout=5, isolation_level=None)
        except (sqlite3.Error, OSError):
            raise RegistryError("REGISTRY_UNAVAILABLE: cannot open lease store") from None
        try:
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except (sqlite3.Error, OSError) as error:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise RegistryError("REGISTRY_UNAVAILABLE: " + type(error).__name__) from None
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    # -- records ----------------------------------------------------------
    def put(self, kind: str, identifier: str, value: dict) -> dict:
        with self.transaction() as db:
            db.execute("INSERT OR REPLACE INTO records VALUES(?,?,?)",
                       (kind, identifier, json.dumps(value, ensure_ascii=False)))
        return value

    def get(self, kind: str, identifier: str) -> dict | None:
        with self.transaction() as db:
            row = db.execute("SELECT data FROM records WHERE kind=? AND id=?",
                             (kind, identifier)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind: str) -> list[dict]:
        with self.transaction() as db:
            rows = db.execute("SELECT data FROM records WHERE kind=? ORDER BY id", (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    # -- leases -----------------------------------------------------------
    def acquire(self, resource: str, owner: str, ttl: int = 300) -> dict:
        if not isinstance(owner, str) or not 1 <= len(owner) <= 200 or not 1 <= ttl <= 1800:
            raise RegistryError("INVALID_LEASE_REQUEST")
        now, token = self.clock(), secrets.token_urlsafe(32)
        with self.transaction() as db:
            prev = db.execute(
                "SELECT fence, owner, expires, state FROM leases WHERE resource=?", (resource,)).fetchone()
            fence = (prev[0] + 1) if prev else 1
            if prev and prev[3] == "active" and prev[2] > now:
                raise LeaseBusy("TAB_LEASE_BUSY: " + prev[1])
            db.execute("INSERT OR REPLACE INTO leases VALUES(?,?,?,?,?,?)",
                       (resource, fence, owner,
                        hashlib.sha256(token.encode()).hexdigest(), now + ttl, "active"))
        return {"resource": resource, "owner": owner, "fence": fence,
                "token": token, "expires": now + ttl}

    def _check(self, db, lease: dict) -> None:
        row = db.execute("SELECT fence, token_hash, expires, state FROM leases WHERE resource=?",
                         (lease["resource"],)).fetchone()
        actual = hashlib.sha256(str(lease.get("token", "")).encode()).hexdigest()
        if (not row or row[0] != lease["fence"] or not row[1]
                or not hmac.compare_digest(row[1], actual)
                or row[3] != "active" or row[2] <= self.clock()):
            raise LeaseLost("LEASE_LOST: stale, expired or released authority")

    def validate(self, lease: dict) -> None:
        with self.transaction() as db:
            self._check(db, lease)

    def renew(self, lease: dict, ttl: int = 300) -> dict:
        if not 1 <= ttl <= 1800:
            raise RegistryError("INVALID_LEASE_TTL")
        with self.transaction() as db:
            self._check(db, lease)
            expires = self.clock() + ttl
            db.execute("UPDATE leases SET expires=? WHERE resource=?", (expires, lease["resource"]))
        return {**lease, "expires": expires}

    def release(self, lease: dict) -> None:
        with self.transaction() as db:
            row = db.execute("SELECT fence, token_hash FROM leases WHERE resource=?",
                             (lease["resource"],)).fetchone()
            actual = hashlib.sha256(str(lease.get("token", "")).encode()).hexdigest()
            if (not row or row[0] != lease["fence"] or not row[1]
                    or not hmac.compare_digest(row[1], actual)):
                raise LeaseLost("LEASE_LOST")
            db.execute("UPDATE leases SET state='released', token_hash=NULL, expires=0 WHERE resource=?",
                       (lease["resource"],))

    def active_leases(self) -> list[dict]:
        with self.transaction() as db:
            rows = db.execute("SELECT resource, fence, owner, expires, state FROM leases").fetchall()
        now = self.clock()
        return [{"resource": r[0], "fence": r[1], "owner": r[2], "expires": r[3], "state": r[4],
                 "expired": r[3] <= now} for r in rows]

    def is_locked(self, resource: str) -> bool:
        return any(item["resource"] == resource and item["state"] == "active" and not item["expired"]
                   for item in self.active_leases())

    def invalidate(self, resource: str) -> None:
        with self.transaction() as db:
            db.execute("UPDATE leases SET state='invalidated', token_hash=NULL, expires=0 WHERE resource=?",
                       (resource,))

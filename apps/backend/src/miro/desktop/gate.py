"""Job ownership gate: epoch-based dispatch check (Miro unified).

Port of C:/dubtool/shared/desktop_gate.py — stdlib only so the Miro
backend has no dubtool dependency.

Rule: a worker may issue a desktop command only when its epoch equals
the job's current epoch. Transferring a job bumps the epoch; the old
holder's late commands are denied even after the desktop lease is free.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def _safe_job(job_id) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(job_id))


def _load(path: Path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def _save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def owner_path(base_dir, job_id=None) -> Path:
    base = Path(base_dir)
    primary = base / "job_owner.json"
    if job_id is None:
        return primary
    existing = _load(primary)
    if existing is None or existing.get("job_id") == job_id:
        return primary
    return base / "owners" / f"{_safe_job(job_id)}.json"


def init_job(base_dir, job_id, holder="A"):
    path = owner_path(base_dir, job_id)
    state = {"job_id": job_id, "epoch": 1, "holder": holder}
    _save(path, state)
    return state


def current_epoch(base_dir, job_id) -> int | None:
    state = _load(owner_path(base_dir, job_id))
    if not state or state.get("job_id") != job_id:
        return None
    return int(state.get("epoch", 0))


def transfer_job(base_dir, job_id, new_holder, lock_path=None):
    """Bump epoch and move ownership. Caller should hold the dispatch lock."""
    from miro.desktop.dispatch import DispatchLock

    base = Path(base_dir)
    lock = lock_path or (base / "dispatch.lock")
    with DispatchLock(lock):
        path = owner_path(base, job_id)
        state = _load(path)
        if not state or state.get("job_id") != job_id:
            raise ValueError("JOB_MISMATCH")
        state["epoch"] = int(state.get("epoch", 0)) + 1
        state["holder"] = new_holder
        _save(path, state)
        return state


def gate(base_dir, job_id, worker, worker_epoch):
    """Return (allowed, detail). Deny stale epochs before touching backend."""
    state = _load(owner_path(base_dir, job_id))
    if not state or state.get("job_id") != job_id:
        return False, {"reason": "JOB_MISMATCH"}
    current = int(state.get("epoch", 0))
    if int(worker_epoch) != current:
        return False, {"reason": "STALE_EPOCH", "worker": worker,
                       "worker_epoch": int(worker_epoch),
                       "current_epoch": current,
                       "current_holder": state.get("holder")}
    return True, {"worker": worker, "epoch": current}

"""Central dispatch: epoch check + backend call under one file lock.

Port of C:/dubtool/shared/desktop_dispatch.py.

Rule: no worker calls backend mutations directly. Every mutating op goes
through dispatch(), which under an exclusive file lock:
  1. re-reads job_owner.json (fresh epoch, never a cached `allowed`),
  2. denies if worker epoch != current epoch,
  3. runs the backend op,
  4. writes a per-run receipt (job_id + run_id, never overwritten).
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from miro.desktop import gate as gate_mod


class DispatchLock:
    """Exclusive inter-process lock on the first byte (Windows/msvcrt)."""

    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self):
        import os

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self.handle = open(self.path, "r+b")
        import os as _os

        if _os.name == "nt":
            import msvcrt

            deadline = time.time() + 60
            while True:
                try:
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.time() > deadline:
                        self.handle.close()
                        raise TimeoutError("DISPATCH_LOCK_BUSY")
                    time.sleep(0.05)
        self.handle.seek(0)
        try:
            self.handle.write(b"lock")
            self.handle.flush()
        except OSError:
            pass
        return self

    def __exit__(self, *exc):
        import os as _os

        try:
            if _os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self.handle.close()


def _save_receipt(base: Path, name: str, payload: dict) -> None:
    from miro.desktop.gate import _save

    _save(base / name, payload)


def dispatch(base_dir, job_id, worker, worker_epoch, op, *args,
             hold_before_op=None, **kwargs):
    """Run op(*args) only if worker_epoch == current epoch, under lock."""
    base = Path(base_dir)
    run_id = uuid.uuid4().hex[:8]
    with DispatchLock(base / "dispatch.lock"):
        allowed, detail = gate_mod.gate(base, job_id, worker, worker_epoch)
        if not allowed:
            _save_receipt(base, f"denied-{run_id}.json",
                          {"job": job_id, "worker": worker, "run": run_id,
                           "denied": detail, "at": time.time()})
            return False, {"denied": detail, "run": run_id}
        if hold_before_op is not None:
            hold_before_op(base)
            allowed, detail = gate_mod.gate(base, job_id, worker, worker_epoch)
            if not allowed:
                _save_receipt(base, f"denied-{run_id}.json",
                              {"job": job_id, "worker": worker, "run": run_id,
                               "denied": detail, "at": time.time(),
                               "note": "denied-after-hold"})
                return False, {"denied": detail, "run": run_id}
        result = op(*args, **kwargs)
        _save_receipt(base, f"receipt-{run_id}.json",
                      {"job": job_id, "worker": worker, "run": run_id,
                       "result": result, "at": time.time()})
        return True, {"run": run_id, "result": result}


def _window_lock_name(window_id) -> str:
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(window_id))
    return f"window-{safe}.lock"


def dispatch_window(base_dir, window_id, job_id, worker, worker_epoch, op,
                    *args, hold_before_op=None, window_lock_dir=None, **kwargs):
    """Like dispatch() but serialized on the WINDOW across all jobs/bases.

    Two jobs sharing one Notepad window interact through the same selected
    tab; a per-job lock would not stop job A from switching tabs while job B
    writes. Lock order: base/dispatch.lock -> window lock dir. transfer_job()
    only takes base/dispatch.lock, so no deadlock cycle.
    """
    base = Path(base_dir)
    lock_dir = Path(window_lock_dir) if window_lock_dir else (base / "window-locks")
    run_id = uuid.uuid4().hex[:8]
    with DispatchLock(base / "dispatch.lock"), \
            DispatchLock(lock_dir / _window_lock_name(window_id)):
        entered_at = time.time()
        allowed, detail = gate_mod.gate(base, job_id, worker, worker_epoch)
        if not allowed:
            _save_receipt(base, f"denied-{run_id}.json",
                          {"job": job_id, "worker": worker, "run": run_id,
                           "window": window_id, "denied": detail, "at": time.time()})
            return False, {"denied": detail, "run": run_id}
        if hold_before_op is not None:
            hold_before_op(base)
            allowed, detail = gate_mod.gate(base, job_id, worker, worker_epoch)
            if not allowed:
                _save_receipt(base, f"denied-{run_id}.json",
                              {"job": job_id, "worker": worker, "run": run_id,
                               "window": window_id, "denied": detail,
                               "at": time.time(), "note": "denied-after-hold"})
                return False, {"denied": detail, "run": run_id}
        result = op(*args, **kwargs)
        if not (isinstance(result, dict) and result.get("cache_stale")):
            _save_receipt(base, f"receipt-{run_id}.json",
                          {"job": job_id, "worker": worker, "run": run_id,
                           "window": window_id, "result": result,
                           "entered_at": entered_at, "at": time.time()})
        return True, {"run": run_id, "result": result}

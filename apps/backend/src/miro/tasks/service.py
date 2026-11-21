"""Unified task service: idempotent submit, write-ahead steps, stop/restart semantics.

Port JARVIS jobs/runner.py + manager.py (M3 §9):
- workerOwner {pid, created_at} moi job; restart: chu cu con song -> BLOCKED/OWNERSHIP_UNKNOWN.
- Retry chi TRANSIENT + buoc read-only/idempotent, ngan sach 3 lan backoff; mutation -> BLOCKED.
- Stop 2 pha idempotent + watchdog: worker khong thoat sau grace -> buoc STOPPED.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import time
import uuid

from ..permissions.store import PermissionStore
from ..storage.db import TaskStore
from .models import TaskError, TaskItem, TaskRecord, TaskStatus, TaskSubmitRequest, utc_now_iso


class TaskConflictError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# Ma TRANSIENT duoc retry (JARVIS execution_policy.py): mang/429/502/503/504/lease busy.
TRANSIENT_CODES = frozenset({
    "REMOTE_TIMEOUT", "CONNECTION_ERROR", "TAB_LEASE_BUSY", "DEPENDENCY_UNAVAILABLE",
    "REMOTE_RATE_LIMITED", "REMOTE_502", "REMOTE_503", "REMOTE_504",
})

# Buoc read-only/idempotent duoc retry; mutation (apply/render) khong replay.
SAFE_RETRY_STEPS = frozenset({"import", "track", "assemble"})

MAX_ATTEMPTS = 3  # JARVIS execution_policy maxAttempts


def _current_owner() -> dict:
    """workerOwner hien tai: pid + create_time (JARVIS runner workerOwner={pid, createdAt})."""
    pid = os.getpid()
    try:
        import psutil
        created_at = float(psutil.Process(pid).create_time())
    except Exception:
        created_at = float(time.time())
    return {"pid": pid, "created_at": created_at}


def _owner_alive(owner: dict | None) -> bool:
    """Chu cu con song? Fail-closed: khong xac minh duoc -> coi nhu con song."""
    if not owner:
        return False
    try:
        import psutil
    except Exception:
        return True
    try:
        proc = psutil.Process(int(owner["pid"]))
        return bool(proc.is_running()) and float(proc.create_time()) == float(owner["created_at"])
    except Exception as exc:
        # NoSuchProcess -> da chet; con lai fail-closed (AccessDenied/KeyError/...) -> con song.
        return "NoSuchProcess" not in type(exc).__name__


class FakeRemote:
    """In-memory Dubtool stand-in for tests: revision-checked project."""

    def __init__(self):
        self.revision = 1
        self.calls: list[str] = []
        self.fail_unknown_on: str | None = None
        # step -> {"code": str, "times": int}: loi TRANSIENT de test retry co ngan sach.
        self.fail_transient: dict[str, dict] = {}

    def mutate(self, step: str, expected_revision: int) -> dict:
        if expected_revision != self.revision:
            raise TaskConflictError("PROJECT_CHANGED", "Project changed; re-review before applying.")
        if self.fail_unknown_on == step:
            raise TaskConflictError("REMOTE_RESULT_UNKNOWN", "Response lost after mutation.")
        spec = self.fail_transient.get(step)
        if spec and int(spec.get("times", 0)) > 0:
            spec["times"] = int(spec["times"]) - 1
            raise TaskConflictError(str(spec.get("code", "REMOTE_TIMEOUT")), "Transient failure; safe to retry.")
        self.calls.append(step)
        self.revision += 1
        return {"revision": self.revision}


class TaskService:
    STEPS = ("import", "track", "assemble", "apply", "render")

    def __init__(self, store: TaskStore, permissions: PermissionStore | None = None,
                 remote: FakeRemote | None = None, stop_grace_seconds: float = 10.0):
        self.store = store
        self.permissions = permissions or PermissionStore()
        self.remote = remote or FakeRemote()
        self.stop_grace_seconds = float(stop_grace_seconds)
        self._seq: dict[str, int] = {}

    # ---- events ----
    def _emit(self, record: dict, type: str, data: dict | None = None) -> None:
        seq = self._seq.get(record["id"], 0) + 1
        self._seq[record["id"]] = seq
        self.store.append_event(record["id"], seq, utc_now_iso(), type, data or {})

    # ---- submit (idempotent on request_id) ----
    def submit(self, payload: TaskSubmitRequest) -> dict:
        raw = payload.model_dump(mode="json")
        fingerprint = hashlib.sha256(
            json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        existing = self.store.get_by_request_id(payload.request_id)
        if existing is not None:
            if existing["fingerprint"] != fingerprint:
                raise TaskConflictError("REQUEST_ID_CONFLICT", "request_id reused with different content.")
            return existing
        record = TaskRecord(
            id="task-" + uuid.uuid4().hex[:12],
            request_id=payload.request_id,
            fingerprint=fingerprint,
            status=TaskStatus.QUEUED,
            items=[TaskItem(title=v.title, project_id=v.project_id) for v in payload.videos],
        ).model_dump(mode="json")
        record["request"] = raw
        record["worker_owner"] = _current_owner()
        record["retry_count"] = 0
        record["stop_grace_seconds"] = self.stop_grace_seconds
        self.store.upsert_task(record)
        self._emit(record, "task_created", {"request_id": payload.request_id})
        return copy.deepcopy(record)

    def get(self, task_id: str) -> dict:
        record = self.store.get_by_id(task_id)
        if record is None:
            raise TaskConflictError("TASK_NOT_FOUND", "Task not found.")
        return record

    # ---- run one item through write-ahead steps ----
    def _step(self, record: dict, index: str | int, step: str) -> None:
        item = record["items"][index]
        if step in item["checkpoints"]:
            return
        record["pending_mutation"] = {"item": index, "step": step}
        self._save(record)
        if step == "apply":
            self.permissions.check(record["id"], index, scope="edit",
                                   revision=self.remote.revision)
        attempts = 0
        while True:
            try:
                result = self.remote.mutate(step, self.remote.revision)
                break
            except TaskConflictError as exc:
                retryable = (exc.code in TRANSIENT_CODES and step in SAFE_RETRY_STEPS
                             and attempts + 1 < MAX_ATTEMPTS)
                if not retryable:
                    raise
                attempts += 1
                record["retry_count"] = int(record.get("retry_count", 0)) + 1
                self._save(record)
                self._emit(record, "step_retry", {"item": index, "step": step,
                                                  "code": exc.code, "attempt": attempts})
                delay = min(2 ** (attempts - 1), 30)
                time.sleep(delay)
        item["checkpoints"][step] = {"step": step, "revision": result["revision"], "result": result}
        record["pending_mutation"] = None
        self._save(record)
        self._emit(record, "step_completed", {"item": index, "step": step})

    def _save(self, record: dict) -> None:
        record["updated_at"] = utc_now_iso()
        self.store.upsert_task(record)

    async def run(self, task_id: str) -> dict:
        record = self.get(task_id)
        if record["status"] not in (TaskStatus.QUEUED, TaskStatus.RUNNING):
            raise TaskConflictError("TASK_NOT_RUNNABLE", f"Cannot run from {record['status']}.")
        record["status"] = TaskStatus.RUNNING
        record["worker_owner"] = _current_owner()
        self._save(record)
        self._emit(record, "task_started", {})
        try:
            for i in range(len(record["items"])):
                if self.get(task_id)["status"] == TaskStatus.STOP_REQUESTED:
                    break
                for step in self.STEPS:
                    await asyncio.sleep(0)
                    record = self.get(task_id)
                    if record["status"] == TaskStatus.STOP_REQUESTED:
                        break
                    self._step(record, i, step)
                record = self.get(task_id)
                record["items"][i]["status"] = "completed"
                self._save(record)
            record = self.get(task_id)
            if record["status"] == TaskStatus.STOP_REQUESTED:
                return record
            record["status"] = TaskStatus.COMPLETED
            self._save(record)
            self._emit(record, "task_completed", {})
            return self.get(task_id)
        except TaskConflictError as exc:
            record = self.get(task_id)
            record["status"] = TaskStatus.NEEDS_ATTENTION
            record["error"] = {"code": exc.code, "message": exc.message}
            self._save(record)
            self._emit(record, "task_blocked", {"code": exc.code})
            return self.get(task_id)
        except Exception as exc:
            # Exception la: khong de task treo khong trang thai -> NEEDS_ATTENTION + persist.
            record = self.get(task_id)
            record["status"] = TaskStatus.NEEDS_ATTENTION
            record["error"] = {"code": "AGENT_EXECUTION_ERROR",
                               "message": f"{type(exc).__name__}"}
            record["pending_mutation"] = None
            self._save(record)
            self._emit(record, "task_blocked", {"code": "AGENT_EXECUTION_ERROR"})
            return self.get(task_id)

    # ---- stop: requested vs worker-stopped are distinct ----
    def request_stop(self, task_id: str) -> dict:
        record = self.get(task_id)
        if record["status"] in (TaskStatus.STOPPED, TaskStatus.COMPLETED, TaskStatus.AWAITING_REVIEW):
            raise TaskConflictError("TASK_NOT_STOPPABLE", f"Cannot stop from {record['status']}.")
        if record["status"] == TaskStatus.STOP_REQUESTED:
            return record
        record["status"] = TaskStatus.STOP_REQUESTED
        record["worker_stopped"] = False
        record["stop_requested_at"] = utc_now_iso()
        self._save(record)
        self._emit(record, "stop_requested", {"worker_stopped": False})
        return self.get(task_id)

    def acknowledge_worker_stopped(self, task_id: str, *, force: bool = False) -> dict:
        """Called when the worker process actually exits. Distinct from the request."""
        record = self.get(task_id)
        if record["status"] != TaskStatus.STOP_REQUESTED:
            raise TaskConflictError("STOP_NOT_REQUESTED", "No pending stop request.")
        record["status"] = TaskStatus.STOPPED
        record["worker_stopped"] = True
        self._save(record)
        self._emit(record, "worker_stopped", {"worker_stopped": True, "forced": bool(force)})
        return self.get(task_id)

    async def wait_stop(self, task_id: str, grace_seconds: float | None = None) -> dict:
        """Watchdog stop: doi worker thoat trong grace; het grace -> buoc STOPPED.

        Port JARVIS runner stop watchdog (stop_grace_seconds). Idempotent: da STOPPED
        thi tra ve ngay; khong co request treo thi 409.
        """
        record = self.get(task_id)
        if record["status"] == TaskStatus.STOPPED:
            return record
        if record["status"] != TaskStatus.STOP_REQUESTED:
            raise TaskConflictError("STOP_NOT_REQUESTED", "No pending stop request.")
        if grace_seconds is None:
            grace_seconds = record.get("stop_grace_seconds") or self.stop_grace_seconds
        deadline = time.monotonic() + max(float(grace_seconds), 0.0)
        while time.monotonic() < deadline:
            record = self.get(task_id)
            if record["status"] == TaskStatus.STOPPED or record.get("worker_stopped"):
                record["status"] = TaskStatus.STOPPED
                record["worker_stopped"] = True
                self._save(record)
                return self.get(task_id)
            await asyncio.sleep(0.05)
        record = self.get(task_id)
        if record["status"] == TaskStatus.STOP_REQUESTED:
            record = self.acknowledge_worker_stopped(task_id, force=True)
        return record

    # ---- restart: rehydrate; in-flight becomes needs_attention, terminal unchanged ----
    def restart(self, task_id: str) -> dict:
        record = self.get(task_id)
        if record["status"] in (TaskStatus.STOPPED, TaskStatus.COMPLETED, TaskStatus.AWAITING_REVIEW):
            return record
        owner = record.get("worker_owner")
        if owner and _owner_alive(owner) and record["status"] in (
                TaskStatus.RUNNING, TaskStatus.STOP_REQUESTED):
            # Chu cu van song: khong replay mu, BLOCKED/OWNERSHIP_UNKNOWN (JARVIS recover_pending).
            record["status"] = TaskStatus.NEEDS_ATTENTION
            record["error"] = {"code": "OWNERSHIP_UNKNOWN",
                               "message": "Previous worker still owns this task; reconcile before resuming."}
        elif record["pending_mutation"]:
            record["status"] = TaskStatus.NEEDS_ATTENTION
            record["error"] = {"code": "REMOTE_RESULT_UNKNOWN",
                               "message": "A mutation has an unknown result; reconcile before resuming."}
        elif record["status"] in (TaskStatus.RUNNING, TaskStatus.QUEUED, TaskStatus.STOP_REQUESTED):
            record["status"] = TaskStatus.NEEDS_ATTENTION
            record["error"] = {"code": "RESTARTED",
                               "message": "Service restarted; resume to continue observation."}
        self._save(record)
        self._emit(record, "task_restarted", {"status": record["status"]})
        return self.get(task_id)

    def resume(self, task_id: str) -> dict:
        record = self.get(task_id)
        if record["pending_mutation"]:
            raise TaskConflictError("REMOTE_RESULT_UNKNOWN", "Unknown mutation result; reconcile first.")
        if record["status"] != TaskStatus.NEEDS_ATTENTION:
            raise TaskConflictError("TASK_NOT_RESUMABLE", "Only needs_attention tasks resume.")
        record["status"] = TaskStatus.QUEUED
        record["error"] = None
        self._save(record)
        self._emit(record, "task_resumed", {})
        return self.get(task_id)

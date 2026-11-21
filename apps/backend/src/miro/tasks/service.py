"""Unified task service: idempotent submit, write-ahead steps, stop/restart semantics."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import uuid

from ..permissions.store import PermissionStore
from ..storage.db import TaskStore
from .models import TaskError, TaskItem, TaskRecord, TaskStatus, TaskSubmitRequest, utc_now_iso


class TaskConflictError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class FakeRemote:
    """In-memory Dubtool stand-in for tests: revision-checked project."""

    def __init__(self):
        self.revision = 1
        self.calls: list[str] = []
        self.fail_unknown_on: str | None = None

    def mutate(self, step: str, expected_revision: int) -> dict:
        if expected_revision != self.revision:
            raise TaskConflictError("PROJECT_CHANGED", "Project changed; re-review before applying.")
        if self.fail_unknown_on == step:
            raise TaskConflictError("REMOTE_RESULT_UNKNOWN", "Response lost after mutation.")
        self.calls.append(step)
        self.revision += 1
        return {"revision": self.revision}


class TaskService:
    STEPS = ("import", "track", "assemble", "apply", "render")

    def __init__(self, store: TaskStore, permissions: PermissionStore | None = None,
                 remote: FakeRemote | None = None):
        self.store = store
        self.permissions = permissions or PermissionStore()
        self.remote = remote or FakeRemote()
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
        self.store.upsert_task(record)
        self._emit(record, "task_created", {"request_id": payload.request_id})
        return copy.deepcopy(record)

    def get(self, task_id: str) -> dict:
        record = self.store.get_by_id(task_id)
        if record is None:
            raise TaskConflictError("TASK_NOT_FOUND", "Task not found.")
        return record

    # ---- run one item through write-ahead steps ----
    def _step(self, record: dict, index: int, step: str) -> None:
        item = record["items"][index]
        if step in item["checkpoints"]:
            return
        record["pending_mutation"] = {"item": index, "step": step}
        self._save(record)
        if step == "apply":
            self.permissions.check(record["id"], index, scope="edit",
                                   revision=self.remote.revision)
        result = self.remote.mutate(step, self.remote.revision)
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

    # ---- stop: requested vs worker-stopped are distinct ----
    def request_stop(self, task_id: str) -> dict:
        record = self.get(task_id)
        if record["status"] in (TaskStatus.STOPPED, TaskStatus.COMPLETED, TaskStatus.AWAITING_REVIEW):
            raise TaskConflictError("TASK_NOT_STOPPABLE", f"Cannot stop from {record['status']}.")
        if record["status"] == TaskStatus.STOP_REQUESTED:
            return record
        record["status"] = TaskStatus.STOP_REQUESTED
        record["worker_stopped"] = False
        self._save(record)
        self._emit(record, "stop_requested", {"worker_stopped": False})
        return self.get(task_id)

    def acknowledge_worker_stopped(self, task_id: str) -> dict:
        """Called when the worker process actually exits. Distinct from the request."""
        record = self.get(task_id)
        if record["status"] != TaskStatus.STOP_REQUESTED:
            raise TaskConflictError("STOP_NOT_REQUESTED", "No pending stop request.")
        record["status"] = TaskStatus.STOPPED
        record["worker_stopped"] = True
        self._save(record)
        self._emit(record, "worker_stopped", {"worker_stopped": True})
        return self.get(task_id)

    # ---- restart: rehydrate; in-flight becomes needs_attention, terminal unchanged ----
    def restart(self, task_id: str) -> dict:
        record = self.get(task_id)
        if record["pending_mutation"]:
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

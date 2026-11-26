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

from ..permissions.store import PermissionError, PermissionStore
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
                 remote: FakeRemote | None = None, stop_grace_seconds: float = 10.0,
                 bridge=None):
        self.store = store
        self.permissions = permissions or PermissionStore()
        self.remote = remote or FakeRemote()
        self.stop_grace_seconds = float(stop_grace_seconds)
        # Production Bridge caller config (Slice 01): khong mac dinh session/
        # token/backend_key trong code — caller truyen vao tu env/secret.
        # task_id/lease owner chi de truy vet, KHONG thay HTTP auth.
        self.bridge = bridge or {}
        self._seq: dict[str, int] = {}

    def _emit(self, record: dict, type: str, data: dict | None = None) -> None:
        import sqlite3

        known = self._seq.get(record["id"], 0)
        stored = max((e["sequence"] for e in self.store.events(record["id"])), default=0)
        seq = max(known, stored) + 1
        self._seq[record["id"]] = seq
        try:
            self.store.append_event(record["id"], seq, utc_now_iso(), type, data or {})
        except sqlite3.IntegrityError:
            # Instance moi recover tren cung DB: seq da ton tai (UNIQUE).
            # Doc lai max tu DB de khong vo idempotency.
            stored = max((e["sequence"] for e in self.store.events(record["id"])), default=0)
            seq = max(seq, stored) + 1
            self._seq[record["id"]] = seq
            self.store.append_event(record["id"], seq, utc_now_iso(), type, data or {})

    # ---- submit (idempotent on request_id) ----
    @staticmethod
    def _project_ids(videos: list) -> list[str]:
        return sorted([(v.get("project_id") or v.get("source") or "") for v in videos])

    def _dedupe_key(self, raw: dict) -> str:
        """Khoa dedupe revision-level (port A _start_render): cung project +
        cung revision + cung che do preview -> cung job, ke ca khac request_id."""
        return hashlib.sha256(json.dumps({
            "projects": self._project_ids(raw.get("videos", [])),
            "revision": self.remote.revision,
            "preview": bool(raw.get("handoff", False)),
        }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def _snapshot_signature(self, record: dict) -> str:
        """Chu ky checkpoint (port A project_snapshot): project + timeline
        revision hien tai. Resume so sanh de phat hien CHECKPOINT_STALE."""
        ids = sorted([(item.get("project_id") or "") for item in record.get("items", [])])
        return hashlib.sha256(json.dumps({
            "projects": ids,
            "revision": self.remote.revision,
        }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def submit(self, payload: TaskSubmitRequest) -> dict:
        raw = payload.model_dump(mode="json")
        fingerprint = hashlib.sha256(
            json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        existing = self.store.get_by_request_id(payload.request_id)
        if existing is not None:
            if existing["fingerprint"] != fingerprint:
                raise TaskConflictError("REQUEST_ID_CONFLICT", "request_id reused with different content.")
            return existing
        # T2: dedupe revision-level — job active trung (project, revision,
        # preview) duoc tra ve thay vi tao job render song song (A _start_render).
        dedupe_key = self._dedupe_key(raw)
        active = self.store.find_active_by_dedupe(dedupe_key)
        if active is not None:
            return active
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
        record["dedupe_key"] = dedupe_key
        record["snapshot_signature"] = self._snapshot_signature(record)
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
            try:
                self.permissions.check(record["id"], index, scope="edit",
                                       revision=self.remote.revision)
            except PermissionError as exc:
                # Tu choi quyen: chua co mutation nao xay ra -> xoa marker,
                # giu nguyen code goc de run() ghi NEEDS_ATTENTION dung ma.
                record["pending_mutation"] = None
                self._save(record)
                raise TaskConflictError(exc.code, exc.message) from None
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

    # ---- Slice 01 message routing: user message -> job_type ----
    # Reviewer A (COMPLETION): chung minh Miro HIEU yeu cau, khong chi chay
    # job da dinh san. route_message() doc message tieng Viet tu nhien,
    # tra job_type + params. run_task_message() la production entry point
    # user-facing: message -> route -> run_browser_actor_check.
    BROWSER_ACTOR_PATTERNS = (
        "tai khoan tiktok", "tiktok dang nhap", "dang nhap tiktok",
        "tai khoan dang nhap", "profile 20", "chrome profile",
        "kiem tra tai khoan", "tai khoan nao",
    )

    # Slice 02 search: tu khoa bat ky + so luong bat ky (khong hardcode).
    BROWSER_SEARCH_PATTERNS = (
        "tim kiem tiktok", "tim tiktok", "search tiktok",
        "tong hop video", "thu thap video", "tim video",
    )

    @classmethod
    def route_message(cls, message: str) -> dict:
        """Dinh tuyen message tu nhien -> job. Khong NLP nang, khong Planner.
        Tra {"job_type": "browser_actor_check" | "browser_search", ...} hoac
        {"job_type": "unsupported", "reason": ...}.
        """
        import re
        text = str(message or "").strip().lower()
        if not text:
            return {"job_type": "unsupported", "reason": "EMPTY_MESSAGE"}
        hits = [p for p in cls.BROWSER_ACTOR_PATTERNS if p in text]
        if hits:
            return {"job_type": "browser_actor_check",
                    "params": {},
                    "matched": hits[:2],
                    "note": "user-facing task execution, chua phai Planner day du"}
        shits = [p for p in cls.BROWSER_SEARCH_PATTERNS if p in text]
        if shits:
            # Slice 02: keyword + limit suy tu message (generic, khong
            # hardcode KANS/5). Quote "..." -> keyword; so N video -> limit.
            kw = ""
            m = re.search(r'"([^"]{1,100})"', str(message or ""))
            if m:
                kw = m.group(1).strip()
            else:
                m2 = re.search(
                    r"(?:tìm|tim|search)\s+(.+?)(?:\s+và|\s+va\b|,|\s*$)",
                    str(message or ""), re.IGNORECASE)
                if m2:
                    kw = m2.group(1).strip()[:100]
            limit = 5
            m3 = re.search(r"(\d{1,2})\s*video", text)
            if m3:
                try:
                    limit = min(max(int(m3.group(1)), 1), 12)
                except (TypeError, ValueError):
                    pass
            return {"job_type": "browser_search",
                    "params": {"keyword": kw, "limit": limit},
                    "matched": shits[:2],
                    "note": "slice 02 search, chua phai Planner day du"}
        return {"job_type": "unsupported", "reason": "NO_ROUTE_MATCH"}

    async def run_task_message(self, task_id: str, *, tab_id: int,
                               live_origin: str = "",
                               url: str | None = None,
                               grant_epoch=None,
                               timeout: int = 30) -> dict:
        """Production entry point user-facing: message(task) -> route -> check.
        Luu route vao event de Reviewer doi chieu message thuc -> job.
        """
        record = self.get(task_id)
        route = self.route_message((record.get("request") or {}).get(
            "message", ""))
        self._emit(record, "task_routed", {"route": route})
        if route.get("job_type") == "browser_actor_check":
            out = await self.run_browser_actor_check(
                task_id, tab_id=tab_id, live_origin=live_origin, url=url,
                grant_epoch=grant_epoch, timeout=timeout)
            out["route"] = route
            return out
        if route.get("job_type") == "browser_search":
            out = await self.run_browser_search_check(
                task_id, tab_id=tab_id, live_origin=live_origin,
                url=url,
                grant_epoch=grant_epoch, timeout=timeout,
                limit=int((route.get("params") or {}).get("limit") or 5))
            out["route"] = route
            return out
        return {"ok": False, "error": "NO_ROUTE_MATCH",
                "route": route, "task_id": task_id}

    # ---- Slice 01 production caller: user task -> Gateway -> Bridge ----
    async def run_browser_actor_check(self, task_id: str, *, tab_id: int,
                                      live_origin: str = "",
                                      url: str | None = None,
                                      grant_epoch=None,
                                      timeout: int = 30) -> dict:
        """Actual production call chain Slice 01:

        TaskService.run_browser_actor_check(task_id)
          -> gateway.read_actor_via_bridge
            -> bridge_transport.read_via_bridge (backend-key tao request)
              -> extension claim/execute (session/token)
              -> wait_observation(request_id=...)
            -> eye.evaluate_actor_signals -> Evidence rea-eye.

        Caller truyen http auth qua self.bridge (session/token/backend_key/
        instance_id/base); task_id + lease owner chi de truy vet, khong thay
        the HTTP auth. Task STOP_REQUESTED giua chung -> huy request.
        """
        from miro.browser import gateway as _gateway

        record = self.get(task_id)
        if record.get("status") == TaskStatus.STOP_REQUESTED:
            return {"ok": False, "error": "TASK_STOP_REQUESTED"}
        if self.bridge.get("require_lease", False):
            lease = (record.get("lease") or self.bridge.get("lease"))
            if isinstance(lease, dict) and lease.get("resource"):
                try:
                    from miro.browser.lease_store import LeaseStore
                    LeaseStore(self.bridge.get(
                        "lease_db", r"C:\Miro\var\lease.db")).validate(lease)
                except Exception as exc:
                    return {"ok": False,
                            "error": "LEASE_LOST: " + type(exc).__name__}
        cfg = self.bridge or {}
        cancelled = False

        def _is_cancelled():
            try:
                st = self.get(task_id).get("status")
            except Exception:
                return True
            return st == TaskStatus.STOP_REQUESTED

        self._emit(record, "browser_check_started",
                   {"tab_id": tab_id, "url": url or live_origin or ""})
        r = await _gateway.read_actor_via_bridge(
            str(cfg.get("session_id") or ""), str(cfg.get("token") or ""),
            instance_id=str(cfg.get("instance_id") or "profile20-main"),
            tab_id=int(tab_id), live_origin=str(live_origin or ""),
            url=url, grant_epoch=grant_epoch,
            base=str(cfg.get("base") or ""), timeout=int(timeout or 30),
            backend_key=str(cfg.get("backend_key") or ""),
            task_id=str(task_id), is_cancelled=_is_cancelled)
        if not isinstance(r, dict) or not r.get("ok"):
            err = str((r or {}).get("error", "BRIDGE_READ_FAILED")) \
                if isinstance(r, dict) else "BRIDGE_READ_FAILED"
            try:
                record = self.get(task_id)
                record["error"] = {"code": err,
                                   "message": "browser actor check failed"}
                self._save(record)
                self._emit(record, "browser_check_failed", {"error": err})
            except Exception:
                pass
            cancelled = err in ("REQUEST_CANCELLED", "TASK_STOP_REQUESTED")
            return {"ok": False, "error": err,
                    "cancelled": cancelled, "task_id": task_id}
        try:
            record = self.get(task_id)
            record["evidence"] = r.get("evidence")
            self._save(record)
            self._emit(record, "browser_check_completed",
                       {"actor": str(((r.get("evidence") or {})
                                      .get("actor") or ""))})
        except Exception:
            pass
        return {"ok": True, "task_id": task_id,
                "evidence": r.get("evidence"),
                "observation": r.get("observation")}

    # ---- Slice 02 production caller: user task -> Gateway -> Bridge ----
    async def run_browser_search_check(self, task_id: str, *, tab_id: int,
                                       live_origin: str = "",
                                       url: str | None = None,
                                       grant_epoch=None,
                                       timeout: int = 30,
                                       limit: int = 5) -> dict:
        """Actual production call chain Slice 02 (search):

        TaskService.run_browser_search_check(task_id)
          -> gateway.read_search_via_bridge
            -> bridge_transport.read_via_bridge (backend-key tao request)
            -> extension claim/execute search-videos (record/doc lap)
            -> wait_observation(request_id=...)
          -> per-record validate (gateway) -> tong hop N video -> Evidence.

        Khong hardcode keyword/limit bai nghiem thu: limit tu route params
        (route_message). Thieu record -> PARTIAL (tra duoc bao nhieu +
        ghi ro thieu), khong suy so lieu.
        """
        from miro.browser import gateway as _gateway

        record = self.get(task_id)
        if record.get("status") == TaskStatus.STOP_REQUESTED:
            return {"ok": False, "error": "TASK_STOP_REQUESTED"}
        cfg = self.bridge or {}
        self._emit(record, "browser_search_started",
                   {"tab_id": tab_id, "url": live_origin or "",
                    "limit": int(limit or 5)})
        r = await _gateway.read_search_via_bridge(
            str(cfg.get("session_id") or ""), str(cfg.get("token") or ""),
            instance_id=str(cfg.get("instance_id") or "profile20-main"),
            tab_id=int(tab_id), live_origin=str(live_origin or ""),
            grant_epoch=grant_epoch, url=url,
            base=str(cfg.get("base") or ""), timeout=int(timeout or 30))
        if not isinstance(r, dict) or not r.get("ok"):
            err = str((r or {}).get("error", "BRIDGE_READ_FAILED")) \
                if isinstance(r, dict) else "BRIDGE_READ_FAILED"
            try:
                record = self.get(task_id)
                record["error"] = {"code": err,
                                   "message": "browser search failed"}
                self._save(record)
                self._emit(record, "browser_search_failed", {"error": err})
            except Exception:
                pass
            return {"ok": False, "error": err,
                    "cancelled": err in ("REQUEST_CANCELLED",
                                         "TASK_STOP_REQUESTED"),
                    "task_id": task_id}
        want = max(1, min(int(limit or 5), 12))
        got = list(((r.get("evidence") or {}).get("records")) or [])
        items = got[:want]
        partial = len(items) < want
        try:
            record = self.get(task_id)
            record["evidence"] = r.get("evidence")
            self._save(record)
            self._emit(record, "browser_search_completed",
                       {"got": len(items), "want": want,
                        "partial": partial})
        except Exception:
            pass
        out = {"ok": True, "task_id": task_id, "partial": partial,
               "want": want, "got": len(items),
               "evidence": r.get("evidence"),
               "observation": r.get("observation"),
               "items": items}
        if partial:
            out["missing"] = (f"chi quan sat duoc {len(items)}/{want} "
                              "video; phan con lai thieu du lieu, "
                              "khong suy doan")
        return out

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
    # T5 RECOVER-tu-dong (port A studio_service :67-70 + execution_policy.failure
    # :52-55): job sach (co snapshot) + con budget + chu cu da chet -> ve QUEUED
    # + retry_count+=1 + RECOVER, khong doi resume tay. Chi job sach moi duoc
    # auto (pending_mutation UNKNOWN / chu song / het budget van NEEDS_ATTENTION).
    RECOVER_BUDGET = 3  # A POLICY maxAttempts (execution_policy :52)

    def _recoverable(self, record: dict) -> bool:
        if record.get("pending_mutation"):
            return False
        owner = record.get("worker_owner")
        if owner and _owner_alive(owner):
            return False
        if int(record.get("retry_count", 0)) >= max(self.RECOVER_BUDGET - 1, 0):
            return False
        return bool(record.get("snapshot_signature"))

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
            if self._recoverable(record):
                # Job sach + con budget + chu chet -> RECOVER tu dong nhu A.
                record["retry_count"] = int(record.get("retry_count", 0)) + 1
                record["status"] = TaskStatus.QUEUED
                record["error"] = None
                record["snapshot_signature"] = self._snapshot_signature(record)
                self._save(record)
                self._emit(record, "task_recovered",
                           {"status": record["status"],
                            "retry_count": record["retry_count"]})
                return self.get(task_id)
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
        # T1: resume chi khi snapshot-signature con khop (port A control_job
        # CHECKPOINT_STALE). Checkpoint luu luc submit; timeline doi tu do ->
        # phai review lai, khong replay tren checkpoint cu. Chu cu con song
        # thi van chan truoc nhu cu (OWNERSHIP_UNKNOWN).
        owner = record.get("worker_owner")
        if owner and _owner_alive(owner):
            raise TaskConflictError("OWNERSHIP_UNKNOWN",
                                    "Previous worker still owns this task; reconcile before resuming.")
        expected = record.get("snapshot_signature")
        if expected is not None and expected != self._snapshot_signature(record):
            raise TaskConflictError("CHECKPOINT_STALE",
                                    "Timeline changed since checkpoint; re-review before resuming.")
        record["status"] = TaskStatus.QUEUED
        record["error"] = None
        # Checkpoint moi cho chu ky chay tiep theo; retry reset nhu A
        # (retryCount=0 luc CONTINUE).
        record["retry_count"] = 0
        record["snapshot_signature"] = self._snapshot_signature(record)
        self._save(record)
        self._emit(record, "task_resumed", {})
        return self.get(task_id)

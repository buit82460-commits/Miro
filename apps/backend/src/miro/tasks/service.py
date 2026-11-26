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

    # Slice 02B Level 1A: doc metadata video TikTok dang mo (video-identity).
    # Khong dung actor-login thay the. Check TRUOC search de khong nham
    # voi "tim video" (tim kiem); pattern o day la doc video hien tai.
    BROWSER_VIDEO_PATTERNS = (
        "video dang mo", "video hien tai", "video hien tai",
        "thong tin video", "metadata video", "doc video",
        "video nay", "video dang xem",
        "phan tich video", "phân tích video", "analyze video",
    )

    # Repair Slice 04: URL video TikTok nhan dang truc tiep, khong phu
    # thuoc message co chua cu phap tieng Viet hay khong.
    TIKTOK_VIDEO_URL_RE = r"tiktok\.com/.{0,80}?/video/(\d{5,})"

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
        # Repair Slice 04: message chua URL video TikTok -> route video
        # truoc khi xet keywords, khong bat nguoi dung biet cu phap.
        murl = re.search(cls.TIKTOK_VIDEO_URL_RE, str(message or ""),
                         re.IGNORECASE)
        if murl:
            return {"job_type": "browser_video",
                    "params": {"video_url": murl.group(0)
                               if murl.group(0).startswith("http")
                               else "https://www." + murl.group(0).lstrip("/")},
                    "matched": ["tiktok_video_url"],
                    "note": "repair slice 04: nhan dang URL video truc tiep"}
        vhits = [p for p in cls.BROWSER_VIDEO_PATTERNS if p in text]
        if vhits:
            return {"job_type": "browser_video",
                    "params": {},
                    "matched": vhits[:2],
                    "note": "slice 02B level 1A video metadata, khong actor-login"}
        shits = [p for p in cls.BROWSER_SEARCH_PATTERNS if p in text]
        if shits:
            # Slice 02: keyword + limit suy tu message (generic, khong
            # hardcode KANS/5). Quote "..." -> keyword; so N video -> limit.
            # Pattern "tim kiem tiktok <KW> tong hop N video": KW nam giua
            # ten platform va cum "tong hop/thu thap N video".
            kw = ""
            m = re.search(r'"([^"]{1,100})"', str(message or ""))
            if m:
                kw = m.group(1).strip()
            else:
                m2 = re.search(
                    r"(?:tìm kiếm|tim kiem|tim|tìm|search)\s+"
                    r"(?:tiktok\s+)?(.+?)(?:\s+tổng hợp|\s+tong hop|"
                    r"\s+thu thập|\s+thu thap|\s+và|\s+va\b|,|\s*$)",
                    str(message or ""), re.IGNORECASE)
                if m2:
                    kw = m2.group(1).strip()[:100]
                    # Cat bo tien to platform con sot ("tiktok ...").
                    kw = re.sub(r"^(?:tiktok)\s+", "", kw,
                                flags=re.IGNORECASE)
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
            self._finalize_browser_task(task_id, out)
            return out
        if route.get("job_type") == "browser_video":
            # Repair Slice 04 (Manual Control cho phan tich video):
            # neu message chua URL TikTok cu the nhung khong co tab LIVE
            # (tab_id<=0) -> chay research/video truc tiep thay vi doi
            # Bridge TAB_UNKNOWN. Khong hardcode URL; URL tu route params.
            _vurl = str((route.get("params") or {}).get("video_url") or "")
            if _vurl and int(tab_id or 0) <= 0:
                out = await self.run_research_video_check(task_id, _vurl)
                out["route"] = route
                self._finalize_browser_task(task_id, out)
                return out
            out = await self.run_browser_video_check(
                task_id, tab_id=tab_id, live_origin=live_origin, url=url,
                grant_epoch=grant_epoch, timeout=timeout)
            out["route"] = route
            self._finalize_browser_task(task_id, out)
            return out
        if route.get("job_type") == "browser_search":
            out = await self.run_browser_search_check(
                task_id, tab_id=tab_id, live_origin=live_origin,
                url=url,
                grant_epoch=grant_epoch, timeout=timeout,
                limit=int((route.get("params") or {}).get("limit") or 5))
            out["route"] = route
            self._finalize_browser_task(task_id, out)
            return out
        try:
            record = self.get(task_id)
            record["status"] = TaskStatus.NEEDS_ATTENTION
            record["error"] = {"code": "NO_ROUTE_MATCH",
                               "message": "message khong khop capability browser hien co"}
            self._save(record)
            self._emit(record, "task_blocked", {"code": "NO_ROUTE_MATCH"})
        except Exception:
            pass
        return {"ok": False, "error": "NO_ROUTE_MATCH",
                "route": route, "task_id": task_id}

    def _finalize_browser_task(self, task_id: str, out: dict) -> None:
        """Repair Slice 04: task co ket qua phai chot trang thai that.

        Truoc day status giu `queued` mai ngay ca khi da co error
        (OBSERVATION_TIMEOUT...) hoac da co evidence -> UI hien sai.
        ok -> COMPLETED; fail -> NEEDS_ATTENTION (giu error).
        """
        try:
            rec = self.get(task_id)
            if rec.get("status") == TaskStatus.STOP_REQUESTED:
                return
            if isinstance(out, dict) and out.get("ok"):
                rec["status"] = TaskStatus.COMPLETED
                self._save(rec)
                self._emit(rec, "task_completed", {})
            else:
                err = str((out or {}).get("error", "UNKNOWN")
                          if isinstance(out, dict) else "UNKNOWN")
                rec["status"] = TaskStatus.NEEDS_ATTENTION
                if not rec.get("error"):
                    rec["error"] = {"code": err,
                                    "message": "browser task failed"}
                self._save(rec)
                self._emit(rec, "task_blocked", {"code": err})
        except Exception:
            pass

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

        def _is_cancelled():
            try:
                st = self.get(task_id).get("status")
            except Exception:
                return True
            return st == TaskStatus.STOP_REQUESTED

        self._emit(record, "browser_search_started",
                   {"tab_id": tab_id, "url": live_origin or "",
                    "limit": int(limit or 5)})
        r = await _gateway.read_search_via_bridge(
            str(cfg.get("session_id") or ""), str(cfg.get("token") or ""),
            instance_id=str(cfg.get("instance_id") or "profile20-main"),
            tab_id=int(tab_id), live_origin=str(live_origin or ""),
            grant_epoch=grant_epoch, url=url,
            base=str(cfg.get("base") or ""), timeout=int(timeout or 30),
            backend_key=str(cfg.get("backend_key") or ""),
            task_id=str(task_id), is_cancelled=_is_cancelled)
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

    # ---- Slice 02B Level 1A: video metadata dang mo (video-identity) ----
    async def run_browser_video_check(self, task_id: str, *, tab_id: int,
                                      live_origin: str = "",
                                      url: str | None = None,
                                      grant_epoch=None,
                                      timeout: int = 30) -> dict:
        """Level 1A dung nghia: doc metadata video TikTok dang mo.

        video-identity / feed-video, khong dung actor-login thay the.
        """
        from miro.browser import gateway as _gateway

        record = self.get(task_id)
        if record.get("status") == TaskStatus.STOP_REQUESTED:
            return {"ok": False, "error": "TASK_STOP_REQUESTED"}
        cfg = self.bridge or {}

        def _is_cancelled():
            try:
                st = self.get(task_id).get("status")
            except Exception:
                return True
            return st == TaskStatus.STOP_REQUESTED

        self._emit(record, "browser_video_started",
                   {"tab_id": tab_id, "url": url or live_origin or ""})
        r = await _gateway.read_video_via_bridge(
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
                                   "message": "browser video check failed"}
                self._save(record)
                self._emit(record, "browser_video_failed", {"error": err})
            except Exception:
                pass
            return {"ok": False, "error": err,
                    "cancelled": err in ("REQUEST_CANCELLED",
                                         "TASK_STOP_REQUESTED"),
                    "task_id": task_id}
        try:
            record = self.get(task_id)
            record["evidence"] = r.get("evidence")
            self._save(record)
            self._emit(record, "browser_video_completed",
                       {"aweme_id": str(((r.get("evidence") or {})
                                         .get("aweme_id") or ""))})
        except Exception:
            pass
        return {"ok": True, "task_id": task_id,
                "evidence": r.get("evidence"),
                "observation": r.get("observation")}

    async def run_research_video_check(self, task_id: str,
                                       video_url: str) -> dict:
        """Repair Slice 04: phan tich video TikTok qua research provider.

        Dung khi co URL cu the nhung khong co tab LIVE. Provider mac dinh
        (MediaIntelProvider) tai + phan tich + tra dict nhe. Loi -> tra
        metadata_only (khong gia ket qua frames).
        """
        from miro.research import service as _rs
        record = self.get(task_id)
        if record.get("status") == TaskStatus.STOP_REQUESTED:
            return {"ok": False, "error": "TASK_STOP_REQUESTED",
                    "task_id": task_id}
        self._emit(record, "research_video_started", {"url": video_url})
        try:
            import miro.main as _main
            provider = getattr(_main.app.state, "research_provider", None) \
                or _rs.NullProvider()
        except Exception:
            provider = _rs.NullProvider()
        try:
            # Repair Slice 04: yt-dlp/media_intel la blocking IO nang ->
            # chay trong thread de khong treo event loop cua BE.
            import asyncio as _aio
            res = await _aio.to_thread(_rs.analyze_video, provider,
                                       video_url, True)
            items = list(res.items or [])
            detail = dict(items[0]) if items else {}
            err = str(detail.get("error") or "")
            evidence = {
                "video_url": video_url,
                "metadata": detail.get("metadata") or {},
                "frames_analyzed": bool(detail.get("frames_analyzed")),
                "evidence_level": res.evidence,
                "summary": res.summary,
                "sources": list(res.sources or []),
                "provider": type(provider).__name__,
            }
            record = self.get(task_id)
            record["evidence"] = evidence
            self._save(record)
            if err or not detail:
                code = err.split(":")[0] if err else "VIDEO_ANALYZE_FAILED"
                record = self.get(task_id)
                if not record.get("error"):
                    record["error"] = {"code": code[:60],
                                       "message": err[:200]
                                       or "research video failed"}
                self._save(record)
                self._emit(record, "research_video_failed",
                             {"error": code[:60]})
                return {"ok": False, "error": code[:60],
                        "evidence": evidence, "task_id": task_id}
            self._emit(record, "research_video_completed",
                         {"evidence_level": res.evidence})
            return {"ok": True, "task_id": task_id, "evidence": evidence}
        except Exception as exc:  # noqa: BLE001
            code = type(exc).__name__
            try:
                record = self.get(task_id)
                record["error"] = {"code": code,
                                   "message": str(exc)[:200]}
                self._save(record)
                self._emit(record, "research_video_failed",
                             {"error": code})
            except Exception:
                pass
            return {"ok": False, "error": code, "task_id": task_id}

    # ---- Slice 02B autonomous search: Observe->Decide->Act->Verify ----
    @staticmethod
    def search_url_for(keyword: str) -> str:
        """URL tim kiem TikTok hop le cho keyword (generic, khong hardcode).
        Encode de tranh ky tu dieu khien; khong nhan URL ngoai TikTok."""
        import urllib.parse as _up
        kw = str(keyword or "").strip()[:100]
        if not kw:
            return ""
        return ("https://www.tiktok.com/search?q=" +
                _up.quote(kw, safe=""))

    async def run_browser_autonomous_search(
            self, task_id: str, *, keyword: str, limit: int = 5,
            timeout: int = 30, tab_id: int = 0) -> dict:
        """Miro tu thuc hien nhiem vu tim kiem qua production entry.

        Observe: liet ke tab kha dung tu Bridge /tabs cho instance dang
        quan ly (profile binding). Decide: chon tab TikTok neu co, neu
        khong thi chon tab bat ky cung instance (khong tu tao tab ngoai
        extension). Act: navigate den search URL qua Gateway (backend-key
        tao request, extension tabs.update thuc thi). Verify: quan sat lai
        URL moi + REA-MAT search-videos -> Evidence. Lap lai doc neu can.
        """
        import json as _json
        import urllib.request as _url

        from miro.browser import gateway as _gateway

        record = self.get(task_id)
        if record.get("status") == TaskStatus.STOP_REQUESTED:
            return {"ok": False, "error": "TASK_STOP_REQUESTED"}
        cfg = self.bridge or {}
        base = str(cfg.get("base") or "http://127.0.0.1:18767")
        inst = str(cfg.get("instance_id") or "profile20-main")

        def _is_cancelled():
            try:
                st = self.get(task_id).get("status")
            except Exception:
                return True
            return st == TaskStatus.STOP_REQUESTED

        self._emit(record, "browser_observe_started",
                   {"keyword": keyword, "limit": int(limit or 5)})
        # Observe: tab kha dung cung instance (profile binding).
        try:
            _tabs = _json.loads(_url.urlopen(
                base + "/tabs", timeout=10).read())
            _all = ((_tabs or {}).get("tabs") or [])
        except Exception as exc:
            err = "BROWSER_UNAVAILABLE: " + type(exc).__name__
            self._emit(record, "browser_observe_failed", {"error": err})
            return {"ok": False, "error": err, "task_id": task_id}
        mine = [t for t in _all
                if str((t or {}).get("browser") or "") == inst]
        if not mine:
            err = "NO_MANAGED_TAB"
            self._emit(record, "browser_observe_failed", {"error": err})
            return {"ok": False, "error": err, "task_id": task_id,
                    "hint": "extension Profile 20 chua ket noi"}
        # Decide: goi y tab tu caller neu hop le, neu khong thi chon tab
        # TikTok dau tien, cuoi cung la tab bat ky cung instance.
        chosen = 0
        try:
            if int(tab_id or 0):
                for t in mine:
                    try:
                        if int((t or {}).get("tab")) == int(tab_id):
                            chosen = int(tab_id)
                            break
                    except (TypeError, ValueError):
                        continue
        except (TypeError, ValueError):
            chosen = 0
        if not chosen:
            for t in mine:
                u = str((t or {}).get("url") or "")
                if "tiktok.com" in u:
                    try:
                        chosen = int((t or {}).get("tab"))
                        break
                    except (TypeError, ValueError):
                        continue
        if not chosen:
            try:
                chosen = int((mine[0] or {}).get("tab"))
            except (TypeError, ValueError):
                chosen = 0
        if not chosen:
            err = "NO_MANAGED_TAB"
            self._emit(record, "browser_observe_failed", {"error": err})
            return {"ok": False, "error": err, "task_id": task_id}
        target = self.search_url_for(keyword)
        if not target:
            return {"ok": False, "error": "EMPTY_KEYWORD",
                    "task_id": task_id}
        self._emit(record, "browser_decide_completed",
                   {"tab_id": chosen, "target": target})
        if _is_cancelled():
            return {"ok": False, "error": "TASK_STOP_REQUESTED",
                    "cancelled": True, "task_id": task_id}
        async def _collect(_nav_url: str) -> dict:
            _out = None
            for attempt in range(3):
                if _is_cancelled():
                    return {"ok": False, "error": "TASK_STOP_REQUESTED",
                            "cancelled": True, "task_id": task_id}
                _out = await self.run_browser_search_check(
                    task_id, tab_id=int(chosen),
                    live_origin="https://www.tiktok.com",
                    url=_nav_url, timeout=int(timeout or 30),
                    limit=int(limit or 5))
                if not isinstance(_out, dict):
                    break
                if _out.get("ok") or _out.get("error") not in (
                        "SEARCH_NO_RECORDS", "SEARCH_RECORDS_UNPARSEABLE",
                        "OBSERVATION_TIMEOUT"):
                    break
                try:
                    _rec = self.get(task_id)
                    self._emit(_rec, "browser_collect_retry",
                               {"attempt": attempt + 1,
                                "error": _out.get("error")})
                except Exception:
                    pass
            if isinstance(_out, dict):
                _out["autonomous"] = True
                _out["chosen_tab"] = int(chosen)
                _out["navigated_url"] = _nav_url
            return _out

        # Act: navigate qua Gateway (authorization + backend key), tru khi
        # tab da dung san destination (like-for-like: trang thu cong van
        # doc duoc, tranh tabs.update thua gay OBSERVATION_TIMEOUT khi
        # worker ngu). Kiem tra URL live qua Gateway read title, khong
        # dung /tabs registry lam evidence (co the stale).
        try:
            _sess = str(cfg.get("session_id") or "")
            _tok = str(cfg.get("token") or "")
            _bk = str(cfg.get("backend_key") or "")
            _cur = await _gateway.read_current_url_via_bridge(
                _sess, _tok, instance_id=inst, tab_id=int(chosen),
                live_origin="https://www.tiktok.com",
                base=base, timeout=20, backend_key=_bk,
                task_id=str(task_id), is_cancelled=_is_cancelled)
            from miro.browser.runtime import (
                _urls_same_destination as _same_dest2)
            _live_url = str(((_cur.get("observation") or {}).get("data")
                             or {}).get("url") or "")
            if bool((_cur or {}).get("ok")) and _live_url and \
                    _same_dest2(_live_url, target):
                self._emit(record, "browser_act_skipped",
                           {"tab_id": chosen, "url": _live_url,
                            "reason": "ALREADY_AT_DESTINATION"})
                self._emit(record, "browser_verify_completed",
                           {"tab_id": chosen, "url": _live_url})
                return await _collect(_live_url)
        except Exception:
            pass
        self._emit(record, "browser_act_started",
                   {"tab_id": chosen, "target": target})
        nav = await _gateway.navigate_via_bridge(
            str(cfg.get("session_id") or ""), str(cfg.get("token") or ""),
            instance_id=inst, tab_id=int(chosen), url=target,
            base=base, timeout=int(timeout or 30),
            backend_key=str(cfg.get("backend_key") or ""),
            task_id=str(task_id), is_cancelled=_is_cancelled)
        if not isinstance(nav, dict) or not nav.get("ok"):
            err = str((nav or {}).get("error", "BRIDGE_NAVIGATE_FAILED")) \
                if isinstance(nav, dict) else "BRIDGE_NAVIGATE_FAILED"
            if err == "OBSERVATION_TIMEOUT":
                # Worker ngu khong gui observation, nhung tabs.update co the
                # da doi URL that: verify lai URL live roi tiep tuc thay vi
                # fail. Giong nut "thay nhung chua co bien lai": nhin lai.
                try:
                    _v = await _gateway.read_current_url_via_bridge(
                        str(cfg.get("session_id") or ""),
                        str(cfg.get("token") or ""),
                        instance_id=inst, tab_id=int(chosen),
                        live_origin="https://www.tiktok.com",
                        base=base, timeout=25,
                        backend_key=str(cfg.get("backend_key") or ""),
                        task_id=str(task_id),
                        is_cancelled=_is_cancelled)
                    from miro.browser.runtime import (
                        _urls_same_destination as _same_dest3)
                    _vu = str(((_v.get("observation") or {}).get("data")
                               or {}).get("url") or "")
                    if bool((_v or {}).get("ok")) and _vu and \
                            _same_dest3(_vu, target):
                        self._emit(record, "browser_act_recovered",
                                   {"tab_id": chosen, "url": _vu,
                                    "reason": "NAVIGATE_OBS_LOST_URL_OK"})
                        self._emit(record, "browser_verify_completed",
                                   {"tab_id": chosen, "url": _vu})
                        return await _collect(_vu)
                except Exception:
                    pass
            try:
                record = self.get(task_id)
                record["error"] = {"code": err,
                                   "message": "browser navigate failed"}
                self._save(record)
                self._emit(record, "browser_act_failed", {"error": err})
            except Exception:
                pass
            return {"ok": False, "error": err,
                    "cancelled": err in ("REQUEST_CANCELLED",
                                         "TASK_STOP_REQUESTED"),
                    "task_id": task_id}
        nav_url = str(((nav.get("evidence") or {}).get("url")) or target)
        self._emit(record, "browser_verify_completed",
                   {"tab_id": chosen, "url": nav_url})
        # Collect: REA-MAT search-videos tren trang vua navigate.
        return await _collect(nav_url)

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

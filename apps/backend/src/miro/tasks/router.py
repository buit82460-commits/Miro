"""FastAPI router for unified tasks."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ..permissions.store import PermissionError
from .models import TaskSubmitRequest
from .service import TaskConflictError, TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_service(request: Request) -> TaskService:
    return request.app.state.task_service


def _err(exc: TaskConflictError | PermissionError):
    status = 404 if getattr(exc, "code", "") == "TASK_NOT_FOUND" else 409
    return JSONResponse(status_code=status,
                        content={"detail": {"code": exc.code, "message": exc.message}})


@router.post("", status_code=202)
async def submit(payload: TaskSubmitRequest, request: Request):
    service = get_service(request)
    try:
        record = service.submit(payload)
        if service.get(record["id"])["status"] == "queued":
            request.app.state.run_task(service.run(record["id"]))
        return record
    except TaskConflictError as exc:
        return _err(exc)


@router.get("/recent")
async def recent(request: Request, limit: int = 20):
    """UI doc lap: liet ke task moi nhat (read-only, BE so huu state)."""
    service = get_service(request)
    try:
        return service.store.recent(limit)
    except TaskConflictError as exc:
        return _err(exc)


@router.get("/runtime/status")
async def runtime_status(request: Request):
    """UI doc lap: trang thai runtime + bridge wiring (redacted, khong lo key).

    Tabs quan sat duoc doc tu Bridge /tabs (endpoint mo, read-only).
    Credential tho khong bao gio xuat hien trong response.
    """
    service = get_service(request)
    wiring = getattr(request.app.state, "bridge_wiring", None) or {}
    tabs: list = []
    tabs_error = ""
    try:
        from miro.tasks.bridge_config import load_bridge_config
        cfg = (load_bridge_config().get("auth") or {})
        base = str(cfg.get("base") or "http://127.0.0.1:18767")
        import json as _js
        import urllib.request as _url
        raw = _url.urlopen(base + "/tabs", timeout=5).read()
        tabs = ((_js.loads(raw) or {}).get("tabs") or [])
    except Exception as exc:
        tabs_error = type(exc).__name__
    return {
        "be": {"status": "ok"},
        "wiring": {"ok": bool(wiring.get("ok")),
                   "wiring": wiring.get("wiring", ""),
                   "reason": wiring.get("reason", "")},
        "bridge": {"tabs": tabs, "count": len(tabs),
                   "error": tabs_error},
        "tasks": {"count": len(service.store.recent(100))},
    }


@router.get("/{task_id}")
async def get_task(task_id: str, request: Request):
    try:
        return get_service(request).get(task_id)
    except TaskConflictError as exc:
        return _err(exc)


@router.get("/{task_id}/events")
async def get_events(task_id: str, request: Request):
    service = get_service(request)
    try:
        service.get(task_id)
        return service.store.events(task_id)
    except TaskConflictError as exc:
        return _err(exc)


@router.post("/{task_id}/stop")
async def stop(task_id: str, request: Request):
    try:
        return get_service(request).request_stop(task_id)
    except (TaskConflictError, PermissionError) as exc:
        return _err(exc)


@router.post("/{task_id}/worker-stopped")
async def worker_stopped(task_id: str, request: Request):
    try:
        return get_service(request).acknowledge_worker_stopped(task_id)
    except (TaskConflictError, PermissionError) as exc:
        return _err(exc)


@router.post("/{task_id}/wait-stop")
async def wait_stop(task_id: str, request: Request, grace_seconds: float | None = None):
    """Watchdog stop: doi worker thoat trong grace, het grace buoc STOPPED."""
    try:
        return await get_service(request).wait_stop(task_id, grace_seconds)
    except (TaskConflictError, PermissionError) as exc:
        return _err(exc)


@router.post("/{task_id}/restart")
async def restart(task_id: str, request: Request):
    try:
        return get_service(request).restart(task_id)
    except (TaskConflictError, PermissionError) as exc:
        return _err(exc)


@router.post("/{task_id}/resume")
async def resume(task_id: str, request: Request):
    try:
        return get_service(request).resume(task_id)
    except (TaskConflictError, PermissionError) as exc:
        return _err(exc)


@router.post("/run-message", status_code=200)
async def run_message(body: dict, request: Request):
    """Slice 02 user-facing production entry: message tu nhien -> TaskService.

    Body: {message, tab_id, live_origin?, limit?}. Miro tu route (actor/search),
    tu doc Bridge qua Gateway, tu tong hop Evidence. Development Agent chi
    quan sat log/trace, khong chen giua.
    """
    service = get_service(request)
    msg = str((body or {}).get("message") or "")
    try:
        tab_id = int((body or {}).get("tab_id"))
    except (TypeError, ValueError):
        return JSONResponse(status_code=400,
                            content={"ok": False,
                                     "error": "TAB_INVALID"})
    live_origin = str((body or {}).get("live_origin") or "")
    route = service.route_message(msg)
    if route.get("job_type") not in ("browser_actor_check", "browser_search",
                                     "browser_video"):
        # Repair: message khong route duoc cung tao task + chot NEEDS_ATTENTION
        # (BE so huu state; UI hien that thay vi mat hut).
        try:
            _rid = "msg-%s" % __import__("uuid").uuid4().hex[:12]
            _rec = service.submit(TaskSubmitRequest.model_validate({
                "request_id": _rid,
                "message": msg[:4000],
                "videos": [{"project_id": _rid, "title": msg[:100]}]}))
        except Exception as exc:
            return JSONResponse(status_code=400,
                                content={"ok": False,
                                         "error": "BAD_MESSAGE: " +
                                         type(exc).__name__})
        _out = {"ok": False, "error": "NO_ROUTE_MATCH",
                "route": route, "task_id": _rec["id"]}
        service._finalize_browser_task(_rec["id"], _out)
        return _out
    # Slice 02B autonomous: neu caller khong chi tab hop le (tab_id<=0),
    # Miro tu observe/decide/act/verify (khong doi Coding Agent chuan bi).
    # Quyet tam: Keyword tu route params; khong hardcode KANS 377.
    try:
        _tab_raw = int((body or {}).get("tab_id") or 0)
    except (TypeError, ValueError):
        _tab_raw = 0
    if route.get("job_type") == "browser_search" and _tab_raw <= 0:
        try:
            _rid = "msg-%s" % __import__("uuid").uuid4().hex[:12]
            rec = service.submit(TaskSubmitRequest.model_validate({
                "request_id": _rid,
                "message": msg[:4000],
                "videos": [{"project_id": _rid, "title": msg[:100]}]}))
        except Exception as exc:
            return JSONResponse(status_code=400,
                                content={"ok": False,
                                         "error": "BAD_MESSAGE: " +
                                         type(exc).__name__})
        try:
            kw = str(((route.get("params") or {}).get("keyword")) or "")
            lim = int(((route.get("params") or {}).get("limit")) or 5)
            out = await service.run_browser_autonomous_search(
                rec["id"], keyword=kw, limit=lim)
            out["route"] = route
            # Repair: chot trang thai that cho task search tu dong
            # (NO_MANAGED_TAB... cung phai NEEDS_ATTENTION, khong kept queued).
            service._finalize_browser_task(rec["id"], out)
            return out
        except (TaskConflictError, PermissionError) as exc:
            return _err(exc)
    # Repair Slice 04: browser_video co URL cu the nhung khong co tab LIVE
    # -> chay research/video truc tiep, khong doi Bridge TAB_UNKNOWN.
    if route.get("job_type") == "browser_video" and _tab_raw <= 0:
        _vurl = str(((route.get("params") or {}).get("video_url")) or "")
        if _vurl:
            try:
                _rid = "msg-%s" % __import__("uuid").uuid4().hex[:12]
                rec = service.submit(TaskSubmitRequest.model_validate({
                    "request_id": _rid,
                    "message": msg[:4000],
                    "videos": [{"project_id": _rid, "title": msg[:100]}]}))
            except Exception as exc:
                return JSONResponse(status_code=400,
                                    content={"ok": False,
                                             "error": "BAD_MESSAGE: " +
                                             type(exc).__name__})
            try:
                out = await service.run_research_video_check(
                    rec["id"], _vurl)
                out["route"] = route
                service._finalize_browser_task(rec["id"], out)
                return out
            except (TaskConflictError, PermissionError) as exc:
                return _err(exc)
    # Contract: live_origin phai la origin cua URL tab LIVE do Bridge thay
    # (khong phai domain caller tu khai). Resolve URL day du tu Bridge /tabs
    # truoc khi goi production chain; khong tin live_origin tho tu caller.
    try:
        from miro.tasks.bridge_config import load_bridge_config
        cfg = (load_bridge_config().get("auth") or {})
        import urllib.request as _url, json as _js
        _tabs = _js.loads(_url.urlopen(
            str(cfg.get("base") or "http://127.0.0.1:18767") + "/tabs",
            timeout=10).read())
        live_url = ""
        for _t in ((_tabs or {}).get("tabs") or []):
            try:
                if int((_t or {}).get("tab")) == int(tab_id):
                    live_url = str((_t or {}).get("url") or "")
                    break
            except (TypeError, ValueError):
                continue
    except Exception:
        live_url = ""
    if not live_url:
        # Repair: TAB_UNKNOWN cung tao task + chot NEEDS_ATTENTION
        # (khong de caller nhan dict khong task_id roi UI mat dau vet).
        try:
            _rid = "msg-%s" % __import__("uuid").uuid4().hex[:12]
            _rec = service.submit(TaskSubmitRequest.model_validate({
                "request_id": _rid,
                "message": msg[:4000],
                "videos": [{"project_id": _rid, "title": msg[:100]}]}))
        except Exception as exc:
            return JSONResponse(status_code=400,
                                content={"ok": False,
                                         "error": "BAD_MESSAGE: " +
                                         type(exc).__name__})
        _out = {"ok": False, "error": "TAB_UNKNOWN",
                "route": route, "task_id": _rec["id"],
                "hint": "tab chua duoc extension quan sat sau reload"}
        service._finalize_browser_task(_rec["id"], _out)
        return _out
    try:
        _rid = "msg-%s" % __import__("uuid").uuid4().hex[:12]
        rec = service.submit(TaskSubmitRequest.model_validate({
            "request_id": _rid,
            "message": msg[:4000],
            "videos": [{"project_id": _rid, "title": msg[:100]}]}))
    except Exception as exc:
        return JSONResponse(status_code=400,
                            content={"ok": False,
                                     "error": "BAD_MESSAGE: " +
                                     type(exc).__name__})
    try:
        out = await service.run_task_message(
            rec["id"], tab_id=tab_id, live_origin=live_origin,
            url=live_url)
    except (TaskConflictError, PermissionError) as exc:
        return _err(exc)
    return out


@router.post("/{task_id}/approve")
async def approve(task_id: str, request: Request, item: int = 0, scope: str = "edit",
                  revision: int = 1):
    service = get_service(request)
    try:
        service.get(task_id)
        approval = service.permissions.grant(task_id, item, scope, revision)
        return approval.model_dump()
    except (TaskConflictError, PermissionError) as exc:
        return _err(exc)


@router.post("/{task_id}/revoke")
async def revoke(task_id: str, request: Request, item: int = 0):
    service = get_service(request)
    try:
        service.get(task_id)
        service.permissions.revoke(task_id, item)
        return {"revoked": True}
    except (TaskConflictError, PermissionError) as exc:
        return _err(exc)

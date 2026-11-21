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

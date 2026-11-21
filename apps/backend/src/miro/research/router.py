"""Research router — POST /research/{search,read,channel,video,compare,to-project}."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..tasks.models import TaskSubmitRequest, TaskVideo
from . import service
from .models import (
    ChannelRequest,
    CompareRequest,
    ReadRequest,
    SearchRequest,
    SourcedResult,
    ToProjectRequest,
    VideoRequest,
)

router = APIRouter(prefix="/research", tags=["research"])


def _provider(request: Request):
    return getattr(request.app.state, "research_provider", None) or service.NullProvider()


@router.post("/search", response_model=SourcedResult)
def research_search(body: SearchRequest, request: Request):
    return service.search(_provider(request), body.query, body.limit)


@router.post("/read", response_model=SourcedResult)
def research_read(body: ReadRequest, request: Request):
    return service.read_url(_provider(request), body.url)


@router.post("/channel", response_model=SourcedResult)
def research_channel(body: ChannelRequest, request: Request):
    return service.analyze_channel(_provider(request), body.channel_url, body.max_videos)


@router.post("/video", response_model=SourcedResult)
def research_video(body: VideoRequest, request: Request):
    return service.analyze_video(_provider(request), body.url, body.include_frames)


@router.post("/compare", response_model=SourcedResult)
def research_compare(body: CompareRequest, request: Request):
    return service.compare(_provider(request), body.url_a, body.url_b, body.include_frames)


@router.post("/to-project", status_code=202)
def research_to_project(body: ToProjectRequest, request: Request):
    task_service = getattr(request.app.state, "task_service", None)
    if task_service is None:
        return JSONResponse(status_code=503, content={"detail": {
            "code": "TASK_SERVICE_UNAVAILABLE",
            "message": "Backend chưa cấu hình task_service; không thể chuyển sang project."}})
    record = task_service.submit(TaskSubmitRequest(
        request_id=body.request_id,
        message=f"Dựng từ nguồn: {body.source_url}",
        videos=[TaskVideo(title=body.title, source=body.source_url,
                          transcript=body.transcript)],
    ))
    if task_service.get(record["id"])["status"] == "queued":
        run_task = getattr(request.app.state, "run_task", None)
        if run_task is not None:
            run_task(task_service.run(record["id"]))
    return record

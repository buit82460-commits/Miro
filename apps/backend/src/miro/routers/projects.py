# -*- coding: utf-8 -*-
"""Projects compat — cho tab /editor (FE) dung duoc BE that.

FE /editor goi /api/projects/{id}, .../operations, .../subtitles/{clip},
.../renders, .../approve. Khi FE tro NEXT_PUBLIC_API_BASE sang BE, cac
route nay (prefix /projects) phuc vu du lieu that tu Studio pipeline:
project id == studio video_id, track phu de map tu segments.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from miro.studio.handlers import StudioHandlers
from miro.studio.pipeline import done_path

router = APIRouter(prefix="/projects", tags=["projects"])

_handlers = StudioHandlers()


def _project_view(video_id: str) -> dict:
    proj = _handlers.pipeline.load_project(video_id)
    if not proj:
        raise HTTPException(status_code=404, detail="khong thay project")
    try:
        segments = _handlers.pipeline._load_segments(video_id)
    except (OSError, ValueError):
        segments = []
    clips = [{"id": f"seg-{s['id']}", "kind": "text",
              "start": s["start"], "duration": max(0.5, s["end"] - s["start"]),
              "text": s.get("tgt_text") or s.get("src_text") or ""}
             for s in segments]
    duration = 0.0
    try:
        duration = float(_handlers.pipeline.engine.probe_duration(
            proj.get("output") or _handlers.pipeline._find_video_file(video_id) or "")) or 0.0
    except Exception:
        duration = 0.0
    if not duration and segments:
        duration = max(s["end"] for s in segments)
    return {"id": video_id, "title": proj.get("title") or video_id,
            "revision": _handlers.store.check_revision(video_id, None),
            "duration": duration, "canvas": {"width": 1280, "height": 720},
            "tracks": ([{"id": "subs", "kind": "subtitle", "clips": clips}]
                       if clips else []),
            "render": ({"job_id": "final", "status": "render_done",
                        "preview": False} if proj.get("output") else None),
            "approved": bool(proj.get("approved"))}


def _touch_revision(video_id: str) -> int:
    return _handlers.store.bump_revision(video_id)


class OperationIn(BaseModel):
    operation: dict = Field(default_factory=dict)
    expected_revision: int | None = None


class SubtitlePatch(BaseModel):
    start: float | None = None
    end: float | None = None
    text: str = ""


class RenderIn(BaseModel):
    preview: bool = True


def _apply_subtitle(video_id: str, clip_id: str, start=None, end=None, text=None):
    pipe = _handlers.pipeline
    segments = pipe._load_segments(video_id)
    try:
        seg_id = int(str(clip_id).split("-")[-1])
    except ValueError:
        raise HTTPException(status_code=404, detail="khong thay clip")
    seg = next((s for s in segments if s["id"] == seg_id), None)
    if seg is None:
        raise HTTPException(status_code=404, detail="khong thay clip")
    if text is not None:
        seg["tgt_text"] = str(text)
    if start is not None:
        delta = float(start) - float(seg["start"])
        seg["start"] = float(start)
        seg["end"] = float(seg["end"]) + delta
    if end is not None:
        seg["end"] = max(float(seg["start"]) + 0.5, float(end))
    pipe._save_segments(video_id, segments)
    work = pipe._work_dir(video_id)
    for step in ("tts", "sync", "mix", "render"):
        marker = done_path(work, step)
        if marker.exists():
            marker.unlink()
    return segments


@router.get("/{project_id}")
def get_project(project_id: str):
    return _project_view(project_id)


@router.post("/{project_id}/operations")
def command(project_id: str, body: OperationIn):
    current = _handlers.store.check_revision(project_id, None)
    if body.expected_revision is not None and body.expected_revision != current:
        raise HTTPException(status_code=409, detail="lech revision")
    op = body.operation or {}
    kind = str(op.get("type") or "")
    if kind == "update_subtitle":
        _apply_subtitle(project_id, str(op.get("clip_id") or ""),
                        start=op.get("start"), end=None, text=op.get("text"))
        if op.get("start") is not None and op.get("duration") is not None:
            _apply_subtitle(project_id, str(op.get("clip_id") or ""),
                            end=float(op["start"]) + float(op["duration"]))
    elif kind == "move_clip":
        _apply_subtitle(project_id, str(op.get("clip_id") or ""),
                        start=op.get("start"))
    else:
        raise HTTPException(status_code=422, detail="operation chua ho tro")
    _touch_revision(project_id)
    return _project_view(project_id)


@router.put("/{project_id}/subtitles/{clip_id}")
def update_subtitle(project_id: str, clip_id: str, patch: SubtitlePatch):
    if not (patch.text or "").strip():
        raise HTTPException(status_code=422, detail="nhap noi dung phu de")
    try:
        _apply_subtitle(project_id, clip_id, start=patch.start,
                        end=patch.end, text=patch.text)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _touch_revision(project_id)
    return _project_view(project_id)


@router.post("/{project_id}/renders")
def render(project_id: str, body: RenderIn):
    from miro.studio.local_rules import empty_plan, keep_ranges
    try:
        plan = (load_plan(project_id) if not body.preview else
                {"version": 1, "source_id": project_id,
                 "duration": _project_view(project_id)["duration"],
                 "cuts": [], "zooms": [], "texts": [], "sfx": [], "music": [],
                 "fades": {"in": 0, "out": 0}, "burn_subtitles": False,
                 "notes": []})
        res = _handlers.editor_render(
            project_id, plan, request_id=f"web-{'preview' if body.preview else 'final'}-{project_id}-{_handlers.store.check_revision(project_id, None)}",
            preview=body.preview)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    view = _project_view(project_id)
    view["render"] = {"job_id": "preview" if body.preview else "final",
                      "status": "preview_done" if body.preview else "render_done",
                      "preview": body.preview, "output": res.get("output")}
    return view


def load_plan(project_id: str) -> dict:
    import json as _json
    plan_file = _handlers.pipeline._work_dir(project_id) / "edit_plan.json"
    if plan_file.is_file():
        return _json.loads(plan_file.read_text(encoding="utf-8"))
    from miro.studio.local_rules import empty_plan
    return empty_plan(project_id, _project_view(project_id)["duration"])


@router.post("/{project_id}/approve")
def approve(project_id: str):
    proj = _handlers.pipeline.load_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="khong thay project")
    if not proj.get("output"):
        raise HTTPException(status_code=422,
                            detail="can render ban cuoi truoc khi duyet")
    _handlers.pipeline.save_project(project_id, approved=True)
    _touch_revision(project_id)
    return _project_view(project_id)

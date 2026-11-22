# -*- coding: utf-8 -*-
"""Studio router — expose StudioHandlers qua HTTP (tab Edit dung duoc that).

Bao gom: download (URL/FB reel/TikTok/YT/local) + resolve media, audio/stt/
translate/subtitles, tts/mix/render, overlay text/blur/box/logo, preview,
editor plan/render/restore, cancel, submit/handoff (queue duyet).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Any

from miro.studio.handlers import StudioHandlers
from miro.studio.media import extract_facebook_id, guess_platform, resolve_media_url

router = APIRouter(prefix="/studio", tags=["studio"])

_handlers = StudioHandlers()


def _err(exc: Exception, fallback: int = 409):
    code = getattr(exc, "status_code", None) or getattr(exc, "status", None) or fallback
    try:
        code = int(code)
    except Exception:
        code = fallback
    if code not in (400, 404, 409, 422):
        code = fallback if code >= 400 and code < 500 else 422
    return HTTPException(status_code=code, detail=str(exc))


class DownloadIn(BaseModel):
    source: str = Field(min_length=1)
    request_id: str = Field(min_length=1, max_length=80)
    src_lang: str = "auto"
    expected_revision: int | None = None


class TranslateIn(BaseModel):
    video_id: str
    request_id: str
    src_lang: str = "auto"
    tgt_lang: str = "vi"
    default_voice: str | None = None
    expected_revision: int | None = None


class SaveSubsIn(BaseModel):
    video_id: str
    request_id: str
    rows: list = Field(default_factory=list)
    expected_revision: int | None = None


class RenderIn(BaseModel):
    video_id: str
    request_id: str
    default_voice: str | None = None
    burn_subtitles: bool = False
    overlays: list | None = None
    expected_revision: int | None = None


class OverlayIn(BaseModel):
    video_id: str
    request_id: str
    overlay: dict
    expected_revision: int | None = None


class PlanIn(BaseModel):
    video_id: str
    request_id: str
    instruction: str = Field(min_length=1, max_length=4000)
    expected_revision: int | None = None


class EditorRenderIn(BaseModel):
    video_id: str
    request_id: str
    plan: dict
    preview: bool = True
    expected_revision: int | None = None


class SimpleIn(BaseModel):
    video_id: str
    request_id: str
    expected_revision: int | None = None


class SubmitIn(BaseModel):
    video_id: str
    request_id: str
    title: str = ""
    description: str = ""
    tags: str = ""
    expected_revision: int | None = None


class HandoffIn(SubmitIn):
    transcript: str = ""
    language: str = "vi"


class RevoiceIn(BaseModel):
    video_id: str
    request_id: str
    seg_id: int
    voice: str
    expected_revision: int | None = None


class TimelineOpIn(BaseModel):
    video_id: str
    request_id: str
    op: dict
    expected_revision: int | None = None


class CaptionsImportIn(BaseModel):
    video_id: str
    request_id: str
    srt_text: str = Field(min_length=1)
    expected_revision: int | None = None


class AudioFxIn(BaseModel):
    video_id: str
    request_id: str
    effect: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)
    expected_revision: int | None = None


class CanvasSetIn(BaseModel):
    video_id: str
    request_id: str
    preset_or_wh: Any = "16:9"
    background: str = "black"
    expected_revision: int | None = None


class ExportPlanIn(BaseModel):
    video_id: str
    request_id: str
    export: dict = Field(default_factory=dict)
    preview: bool = False
    expected_revision: int | None = None


@router.get("/resolve")
def resolve(source: str):
    out = resolve_media_url(source)
    if not out.get("ok"):
        raise HTTPException(status_code=422, detail=out.get("error"))
    return out


@router.get("/platform")
def platform(source: str):
    return {"platform": guess_platform(source),
            "facebook_id": extract_facebook_id(source)}


@router.post("/download")
def download(body: DownloadIn):
    try:
        return _handlers.do_download(body.source, request_id=body.request_id,
                                     expected_revision=body.expected_revision,
                                     src_lang=body.src_lang)
    except Exception as exc:
        raise _err(exc)


@router.post("/translate")
def translate(body: TranslateIn):
    try:
        return _handlers.translate(body.video_id, request_id=body.request_id,
                                   expected_revision=body.expected_revision,
                                   src_lang=body.src_lang, tgt_lang=body.tgt_lang,
                                   default_voice=body.default_voice)
    except Exception as exc:
        raise _err(exc)


@router.post("/subtitles/save")
def save_subs(body: SaveSubsIn):
    try:
        return _handlers.save_segments(body.video_id, body.rows,
                                       request_id=body.request_id,
                                       expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc)


@router.get("/subtitles/{video_id}")
def load_subs(video_id: str):
    try:
        return {"video_id": video_id,
                "segments": _handlers.load_segments(video_id)}
    except Exception as exc:
        raise _err(exc, 404)


@router.post("/render")
def render(body: RenderIn):
    try:
        return _handlers.tts_mix_render(body.video_id, request_id=body.request_id,
                                        expected_revision=body.expected_revision,
                                        default_voice=body.default_voice)
    except Exception as exc:
        raise _err(exc)


@router.post("/render/final")
def render_final(body: RenderIn):
    try:
        return _handlers.do_final_render(
            body.video_id, request_id=body.request_id,
            expected_revision=body.expected_revision,
            burn_subtitles=body.burn_subtitles, overlays=body.overlays,
            default_voice=body.default_voice)
    except Exception as exc:
        raise _err(exc)


@router.post("/overlay")
def overlay(body: OverlayIn):
    try:
        return _handlers.add_overlay(body.video_id, body.overlay,
                                    request_id=body.request_id,
                                    expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc, 422)


@router.post("/revoice")
def revoice(body: RevoiceIn):
    try:
        return _handlers.revoice(body.video_id, body.seg_id, body.voice,
                                 request_id=body.request_id,
                                 expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc)


@router.post("/plan")
def plan(body: PlanIn):
    try:
        return _handlers.editor_plan(body.video_id, body.instruction,
                                     request_id=body.request_id,
                                     expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc, 422)


@router.post("/editor/render")
def editor_render(body: EditorRenderIn):
    try:
        return _handlers.editor_render(body.video_id, body.plan,
                                      request_id=body.request_id,
                                      expected_revision=body.expected_revision,
                                      preview=body.preview)
    except Exception as exc:
        raise _err(exc)


@router.post("/editor/restore")
def editor_restore(body: SimpleIn):
    try:
        return _handlers.editor_restore(body.video_id, request_id=body.request_id,
                                       expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc)


@router.post("/cancel")
def cancel(body: SimpleIn):
    return _handlers.cancel_pipeline(body.video_id)


@router.post("/submit")
def submit(body: SubmitIn):
    try:
        return _handlers.submit_studio(body.video_id, body.title, body.description,
                                      body.tags, request_id=body.request_id,
                                      expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc)


@router.post("/handoff")
def handoff(body: HandoffIn):
    try:
        tags = [t.strip() for t in (body.tags or "").split(",") if t.strip()]
        return _handlers.handoff(body.video_id, body.title, body.description,
                                tags, request_id=body.request_id,
                                expected_revision=body.expected_revision,
                                transcript=body.transcript,
                                language=body.language)
    except Exception as exc:
        raise _err(exc, 422)


@router.get("/project/{video_id}")
def project(video_id: str):
    try:
        proj = _handlers.pipeline.load_project(video_id)
        if not proj:
            raise HTTPException(status_code=404, detail="khong thay project")
        try:
            segments = _handlers.pipeline._load_segments(video_id)
        except (OSError, ValueError):
            segments = []
        proj = dict(proj)
        proj["video_id"] = video_id
        proj["segments"] = segments
        proj["revision"] = _handlers.store.check_revision(video_id, None)
        return proj
    except HTTPException:
        raise
    except Exception as exc:
        raise _err(exc, 404)


@router.get("/media/{video_id}")
def media(video_id: str):
    try:
        proj = _handlers.pipeline.load_project(video_id)
        out = proj.get("output") if proj else None
        if not out or not Path(str(out)).is_file():
            found = _handlers.pipeline._find_video_file(video_id)
            out = str(found) if found else out
        if not out:
            raise HTTPException(status_code=404, detail="chua co media")
        return {"video_id": video_id, "output": out}
    except HTTPException:
        raise
    except Exception as exc:
        raise _err(exc, 404)


@router.post("/timeline/op")
def timeline_op(body: TimelineOpIn):
    try:
        return _handlers.timeline_op(body.video_id, body.op,
                                     request_id=body.request_id,
                                     expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc, 422)


@router.post("/timeline/undo")
def timeline_undo(body: SimpleIn):
    try:
        return _handlers.timeline_undo(body.video_id, request_id=body.request_id,
                                       expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc, 422)


@router.post("/timeline/redo")
def timeline_redo(body: SimpleIn):
    try:
        return _handlers.timeline_redo(body.video_id, request_id=body.request_id,
                                       expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc, 422)


@router.post("/captions/import")
def captions_import(body: CaptionsImportIn):
    try:
        return _handlers.import_captions(body.video_id, body.srt_text,
                                         request_id=body.request_id,
                                         expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc, 422)


@router.get("/captions/export/{video_id}")
def captions_export(video_id: str):
    try:
        return _handlers.export_captions(video_id)
    except Exception as exc:
        raise _err(exc, 404)


@router.post("/audiofx/preview")
def audiofx_preview(body: AudioFxIn):
    try:
        return _handlers.audio_fx_preview(body.video_id, body.effect, body.params,
                                          request_id=body.request_id,
                                          expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc, 422)


@router.post("/canvas/set")
def canvas_set(body: CanvasSetIn):
    try:
        return _handlers.canvas_set(body.video_id, body.preset_or_wh,
                                    request_id=body.request_id,
                                    expected_revision=body.expected_revision,
                                    background=body.background)
    except Exception as exc:
        raise _err(exc, 422)


@router.post("/export/plan")
def export_plan(body: ExportPlanIn):
    try:
        return _handlers.export_plan(body.video_id, body.export, body.preview,
                                     request_id=body.request_id,
                                     expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc, 422)


class TrackIn(BaseModel):
    video_id: str
    request_id: str
    roi: dict = Field(default_factory=dict)
    expected_revision: int | None = None


@router.post("/beat")
def beat(body: SimpleIn):
    try:
        return _handlers.beat(body.video_id, request_id=body.request_id,
                              expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc, 422)


@router.post("/separate")
def separate(body: SimpleIn):
    try:
        return _handlers.separate(body.video_id, request_id=body.request_id,
                                  expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc)


@router.post("/track")
def track(body: TrackIn):
    try:
        return _handlers.track(body.video_id, body.roi,
                               request_id=body.request_id,
                               expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc, 422)


class LadderIn(BaseModel):
    video_id: str
    request_id: str
    rungs: list = Field(default_factory=lambda: ["480p", "720p", "1080p"])
    expected_revision: int | None = None


@router.post("/export/ladder")
def export_ladder(body: LadderIn):
    try:
        return _handlers.export_ladder(body.video_id, body.rungs,
                                       request_id=body.request_id,
                                       expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc, 422)


@router.post("/preview/live")
def preview_live(body: SimpleIn):
    try:
        return _handlers.realtime_preview(body.video_id,
                                          request_id=body.request_id,
                                          expected_revision=body.expected_revision)
    except Exception as exc:
        raise _err(exc)

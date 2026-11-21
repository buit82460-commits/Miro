"""Desktop router — Notepad acts qua act() boundary + backend ops that.

- POST /desktop/init: tao/cap epoch job (holder mac dinh).
- POST /desktop/act: read/write/append qua act() (dispatch_window + D2
  select-tab + receipt). CLI loi -> fail-closed 503 CLI_UNAVAILABLE,
  khong crash server; STALE_EPOCH -> 409.
- POST /desktop/transfer: doi holder (bump epoch).

Body phai co job_id + worker + worker_epoch. Chi ho tro Notepad pilot.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/desktop", tags=["desktop"])


class InitRequest(BaseModel):
    job_id: str = Field(min_length=1)
    holder: str = "A"
    base_dir: str | None = None


class ActRequest(BaseModel):
    job_id: str = Field(min_length=1)
    worker: str = Field(min_length=1)
    worker_epoch: int = 0
    base_dir: str | None = None
    app: str | None = "notepad"
    window: str | None = "Notepad"
    doc: str = Field(min_length=1)
    action: str = "read"
    text: str | None = None
    control: str = "textfield"


class TransferRequest(BaseModel):
    job_id: str = Field(min_length=1)
    new_holder: str = Field(min_length=1)
    base_dir: str | None = None


def _base(explicit: str | None) -> str:
    if explicit:
        return explicit
    import os
    from pathlib import Path
    var = Path(os.environ.get("MIRO_BE_DB_DIR", r"C:\Miro\var"))
    path = var / "desktop-jobs"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _cli_unavailable(detail) -> bool:
    if not isinstance(detail, dict):
        return False
    blob = str(detail)
    return "CLI_UNAVAILABLE" in blob


@router.post("/init")
def init_job(body: InitRequest) -> dict:
    from miro.desktop.gate import current_epoch, init_job as _init
    state = _init(_base(body.base_dir), body.job_id, holder=body.holder)
    return {"job_id": body.job_id, "epoch": state.get("epoch", 1),
            "holder": state.get("holder"),
            "current_epoch": current_epoch(_base(body.base_dir), body.job_id)}


@router.post("/act")
def desktop_act(body: ActRequest) -> dict:
    from miro.desktop import act as actmod
    from miro.desktop import backend as be
    base = _base(body.base_dir)
    try:
        ok, out = actmod.act(
            base, body.job_id, body.worker, body.worker_epoch, be,
            app=body.app, window=body.window, doc=body.doc,
            action=body.action, text=body.text, control=body.control)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    if not ok and isinstance(out, dict):
        if _cli_unavailable(out):
            raise HTTPException(status_code=503, detail=out)
        if out.get("error") == "STALE_EPOCH_DENIED":
            raise HTTPException(status_code=409, detail=out)
        if out.get("error") in ("WINDOW_NOT_FOUND", "DOC_NOT_UNIQUE_STOP",
                                "FIND_DOC_FAILED", "LIST_WINDOWS_FAILED",
                                "DOC_REQUIRED", "TEXT_REQUIRED",
                                "UNKNOWN_ACTION"):
            raise HTTPException(status_code=422, detail=out)
    return {"ok": ok, "result": out}


@router.post("/transfer")
def transfer(body: TransferRequest) -> dict:
    from miro.desktop.gate import transfer_job as _transfer
    try:
        state = _transfer(_base(body.base_dir), body.job_id,
                          body.new_holder)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"job_id": body.job_id, "epoch": state.get("epoch"),
            "holder": state.get("holder")}

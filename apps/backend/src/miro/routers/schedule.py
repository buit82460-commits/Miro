"""Schedule router — caller-giu plan (module schedule khong tu requeue).

- POST /schedule/ensure: caller gui policy + new_items + was_clean_shutdown ->
  ensure_day_plan (rebuild/respect theo boot_action) + gan vao Publisher.
- GET /schedule/day-plan: tra plan dang dung (memory truoc, file sau, 404 neu chua co).
- PATCH /schedule/day-plan/status: doi status paused/active (user pause ton trong).

Caller wiring (P1 A TD-scheduler): boot-vs-pause o caller, module chi tinh.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/schedule", tags=["schedule"])


class EnsureRequest(BaseModel):
    policy: dict = Field(default_factory=dict)
    new_items: list[dict] = Field(default_factory=list)
    carryover: list[dict] = Field(default_factory=list)
    date_str: str | None = None
    was_clean_shutdown: bool = True


class StatusPatch(BaseModel):
    status: str = Field(min_length=1)


def _publisher():
    from miro.main import app as _app

    return _app.state.threads_publisher  # type: ignore[attr-defined]


@router.post("/ensure")
def ensure(body: EnsureRequest) -> dict:
    from miro.scheduling.store import ensure_day_plan as _ensure

    plan, action = _ensure(body.policy, body.new_items,
                           date_str=body.date_str,
                           was_clean_shutdown=body.was_clean_shutdown,
                           carryover=body.carryover)
    try:
        _publisher().day_plan = plan
    except Exception as exc:
        raise HTTPException(status_code=500,
                            detail=f"BIND_PLAN_FAILED: {exc}") from None
    due_n = sum(1 for s in plan.get("slots", [])
                if s.get("state") == "pending")
    return {"action": action, "date": plan.get("date"),
            "slots": len(plan.get("slots", [])), "pending": due_n,
            "status": plan.get("status")}


@router.get("/day-plan")
def day_plan() -> dict:
    from miro.scheduling.store import load_plan as _load

    try:
        plan = _publisher().day_plan
    except Exception:
        plan = None
    if not isinstance(plan, dict):
        plan = _load()
    if not isinstance(plan, dict):
        raise HTTPException(status_code=404, detail="NO_DAY_PLAN")
    return plan


@router.patch("/day-plan/status")
def patch_status(body: StatusPatch) -> dict:
    value = str(body.status or "").lower()
    if value not in ("active", "paused"):
        raise HTTPException(status_code=400,
                            detail="status must be active|paused")
    from miro.scheduling.store import load_plan as _load
    from miro.scheduling.store import save_plan as _save

    try:
        pub = _publisher()
    except Exception:
        pub = None
    plan = (getattr(pub, "day_plan", None)
            if pub is not None else None) or _load()
    if not isinstance(plan, dict):
        raise HTTPException(status_code=404, detail="NO_DAY_PLAN")
    plan["status"] = value
    _save(plan)
    if pub is not None:
        try:
            pub.day_plan = plan
        except Exception:
            pass
    return {"status": value, "date": plan.get("date")}

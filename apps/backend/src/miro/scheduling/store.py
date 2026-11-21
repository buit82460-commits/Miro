"""Day-plan store: persist plan ngay xuong var + boot wiring (scheduler caller).

- Plan la file JSON (var/threads-day-plan.json): song restart BE.
- boot: was_clean_shutdown + policy.status -> boot_action (rebuild/respect).
- ensure_day_plan: rebuild khi can, giu nguyen khi respect, persist sau moi
  mutate (record_submit_unknown/mark_slot_verified o day de 1 noi persist).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from miro.scheduling import schedule as _sched


def plan_path(var_dir: str | Path | None = None) -> Path:
    var = Path(var_dir or os.environ.get("MIRO_BE_DB_DIR", r"C:\Miro\var"))
    return var / "threads-day-plan.json"


def load_plan(var_dir: str | Path | None = None) -> dict | None:
    try:
        raw = plan_path(var_dir).read_text(encoding="utf-8-sig")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def save_plan(plan: dict, var_dir: str | Path | None = None) -> dict:
    path = plan_path(var_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(path)
    return plan


def ensure_day_plan(policy: dict, new_items: list[dict], *,
                    var_dir: str | Path | None = None,
                    date_str: str | None = None,
                    was_clean_shutdown: bool = True,
                    carryover: list[dict] | None = None) -> tuple[dict, str]:
    """Tra (plan, action). rebuild -> build moi + persist; respect -> giu cu
    (neu khong co cu thi build moi)."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    today = date_str or _dt.now(_tz(_td(hours=7))).date().isoformat()
    action = _sched.boot_action(was_clean_shutdown,
                                str((policy or {}).get("status", "active")))
    current = load_plan(var_dir)
    if action == "respect" and isinstance(current, dict) \
            and current.get("date") == today:
        return current, action
    plan = _sched.build_day_plan(today, policy or {}, carryover or [],
                                 new_items or [])
    save_plan(plan, var_dir)
    return plan, action


def touch_unknown(plan: dict, task_id: str,
                  var_dir: str | Path | None = None) -> dict:
    _sched.record_submit_unknown(plan, task_id)
    save_plan(plan, var_dir)
    return plan


def touch_verified(plan: dict, task_id: str,
                   var_dir: str | Path | None = None) -> dict:
    _sched.mark_slot_verified(plan, task_id)
    save_plan(plan, var_dir)
    return plan

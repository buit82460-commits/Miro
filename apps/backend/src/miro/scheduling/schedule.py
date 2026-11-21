"""Posting schedule: port nguyen C:\\dubtool\\core\\posting_schedule.py.

Luat A (TD-publisher / HOI-publisher-01, da dap kin):
- Slot UNKNOWN giu nguyen, tinh vao daily_cap, khong giai phong.
- due_slots chi lay "pending" — UNKNOWN khong chay lai trong cung plan.
- reconcile_queue append-only trong plan ngay; caller ngay sau tu quyet
  carryover, module khong tu requeue.
- paused outrank moi slot (do caller kiem tra truoc khi goi).
- Module khong phan biet shutdown-boot vs user-pause — caller quyet
  (nguyen tac B: boot may tat -> tinh lai plan; user pause -> ton trong).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

TZ = "Asia/Ho_Chi_Minh"


def _tz(policy: dict) -> timezone:
    name = (policy or {}).get("timezone", TZ)
    if name in ("Asia/Ho_Chi_Minh", "Asia/Bangkok"):
        return timezone(timedelta(hours=7))
    return timezone(timedelta(hours=7))


def _parse_hhmm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def build_slot_times(date_str: str, policy: dict, count: int) -> list[str]:
    """Dan `count` slot deu trong window policy (ISO local time)."""
    if count <= 0:
        return []
    tz = _tz(policy)
    window = (policy or {}).get("window", {}) or {}
    start_h, start_m = _parse_hhmm(window.get("start", "09:00"))
    end_h, end_m = _parse_hhmm(window.get("end", "21:00"))
    year, month, day = (int(part) for part in date_str.split("-"))
    start = datetime(year, month, day, start_h, start_m, tzinfo=tz)
    end = datetime(year, month, day, end_h, end_m, tzinfo=tz)
    if end <= start or count == 1:
        return [start.isoformat()]
    step = (end - start) / count
    return [(start + step * i).isoformat() for i in range(count)]


def build_day_plan(date_str: str, policy: dict, carryover: list[dict],
                   new_items: list[dict]) -> dict:
    """Uu tien carryover (giu task_id), new items lap slot con lai cua cap."""
    cap = int((policy or {}).get("daily_cap", 10))
    eligible_old = [task for task in carryover if task.get("eligible", True)]
    slots_source = eligible_old + list(new_items or [])
    chosen = slots_source[:cap]
    leftover_new = list((new_items or []))[max(0, cap - len(eligible_old)):]
    times = build_slot_times(date_str, policy, len(chosen))
    slots = []
    for index, task in enumerate(chosen):
        origin = "carryover" if index < len(eligible_old[:cap]) else "new"
        slots.append({
            "slot_index": index,
            "task_id": task.get("task_id"),
            "shortcode": task.get("shortcode"),
            "origin": origin,
            "planned_at": times[index] if index < len(times) else None,
            "state": task.get("state", "pending"),
        })
    return {
        "date": date_str,
        "account": (policy or {}).get("account"),
        "platform": (policy or {}).get("platform"),
        "daily_cap": cap,
        "fetch_cap": (policy or {}).get("fetch_cap", cap),
        "status": (policy or {}).get("status", "active"),
        "slots": slots,
        "storage": [{"task_id": t.get("task_id"), "shortcode": t.get("shortcode")}
                    for t in leftover_new],
        "reconcile_queue": [],
    }


def due_slots(plan: dict, now_iso: str) -> list[dict]:
    """Slot pending den gio (late boot: khong burst, chi slot den han)."""
    now = datetime.fromisoformat(now_iso)
    out = []
    for slot in plan.get("slots", []):
        if slot.get("state") not in ("pending",):
            continue
        planned = slot.get("planned_at")
        if planned and datetime.fromisoformat(planned) <= now:
            out.append(slot)
    return out


def record_submit_unknown(plan: dict, task_id: str) -> dict:
    """Slot UNKNOWN-after-submit vao reconcile queue, GIU slot (tinh vao cap)."""
    for slot in plan.get("slots", []):
        if slot.get("task_id") == task_id:
            slot["state"] = "unknown_pending_reconcile"
    queue = plan.setdefault("reconcile_queue", [])
    if task_id not in queue:
        queue.append(task_id)
    return plan


def consecutive_unknowns(results: list[str]) -> int:
    count = 0
    for result in reversed(results):
        if result == "unknown":
            count += 1
        else:
            break
    return count


def should_auto_pause(results: list[str], threshold: int = 2) -> bool:
    return consecutive_unknowns(results) >= threshold


# ---- caller wiring (P1 phan mo): paused/due/boot o caller, khong trong module
def boot_action(was_clean_shutdown: bool, policy_status: str) -> str:
    """Caller quyet (nguyen tac B): boot may tat (shutdown khong sach) ->
    tinh lai plan theo policy; user pause -> ton trong, khong post bu.

    Tra "rebuild" (tinh lai plan) hay "respect" (giu nguyen, khong post bu).
    """
    if str(policy_status or "active").lower() == "paused":
        return "respect"
    if not was_clean_shutdown:
        return "rebuild"
    return "respect"


def select_due_intents(plan: dict, intents: list, now_iso: str) -> tuple[list, list]:
    """Loc intents theo plan ngay: (due, deferred).

    - plan paused -> tat ca deferred ly do PAUSED (paused outrank moi slot).
    - slot khong pending / chua den han -> deferred (khong burst).
    - Khop intent <-> slot qua intent_id == task_id; intent khong co slot ->
      deferred ly do NO_SLOT.
    """
    deferred: list[dict] = []
    if str((plan or {}).get("status", "active")).lower() == "paused":
        for intent in intents or []:
            iid = getattr(intent, "intent_id", "?")
            deferred.append({"intent": intent, "shortcode": getattr(
                intent, "shortcode", "") or iid, "reason": "PAUSED"})
        return [], deferred
    due_ids = {s.get("task_id") for s in due_slots(plan or {}, now_iso)}
    slot_state = {s.get("task_id"): s.get("state") for s in (plan or {}).get("slots", [])}
    due, deferred = [], deferred
    for intent in intents or []:
        iid = getattr(intent, "intent_id", None)
        sc = getattr(intent, "shortcode", "") or iid or "?"
        if iid in due_ids:
            due.append(intent)
        else:
            reason = "NOT_DUE" if iid in slot_state else "NO_SLOT"
            if iid in slot_state and slot_state.get(iid) != "pending":
                reason = "SLOT_" + str(slot_state.get(iid)).upper()
            deferred.append({"intent": intent, "shortcode": sc, "reason": reason})
    return due, deferred


def mark_slot_verified(plan: dict, task_id: str) -> dict:
    """reconcile-verified ket thuc vong doi slot: verified, ra khoi queue."""
    for slot in (plan or {}).get("slots", []):
        if slot.get("task_id") == task_id:
            slot["state"] = "verified"
    queue = (plan or {}).setdefault("reconcile_queue", [])
    if task_id in queue:
        queue.remove(task_id)
    return plan

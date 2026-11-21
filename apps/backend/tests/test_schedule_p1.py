"""P1 scheduler: port nguyen posting_schedule.py + caller boot/pause (A+B).

Chay: python -m pytest tests/test_schedule_p1.py -q (tu C:\\Miro\\apps\\backend).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

DUBTOOL = Path(r"C:\dubtool")
if str(DUBTOOL) not in sys.path:
    sys.path.insert(0, str(DUBTOOL))

from miro.scheduling.schedule import (  # noqa: E402
    build_day_plan,
    consecutive_unknowns,
    due_slots,
    record_submit_unknown,
    should_auto_pause,
)

POLICY = {"account": "haodaojrk5", "platform": "threads", "daily_cap": 2,
          "window": {"start": "09:00", "end": "21:00"}, "status": "active"}


def _items(*tids):
    return [{"task_id": t, "shortcode": t} for t in tids]


def test_carryover_giu_task_id_cap_khong_vuot():
    plan = build_day_plan("2026-11-22", POLICY,
                          carryover=[{"task_id": "old1", "shortcode": "old1"}],
                          new_items=_items("n1", "n2", "n3"))
    assert len(plan["slots"]) == 2  # cap
    assert plan["slots"][0]["task_id"] == "old1"
    assert plan["slots"][0]["origin"] == "carryover"
    assert [s["task_id"] for s in plan["storage"]] == ["n2", "n3"]


def test_unknown_giu_slot_tinh_cap_khong_chay_lai():
    plan = build_day_plan("2026-11-22", POLICY, carryover=[],
                          new_items=_items("a", "b"))
    record_submit_unknown(plan, "a")
    assert plan["reconcile_queue"] == ["a"]
    # slot van nam trong plan (giu cap), state doi
    states = {s["task_id"]: s["state"] for s in plan["slots"]}
    assert states["a"] == "unknown_pending_reconcile"
    # due_slots chi lay pending -> UNKNOWN khong chay lai cung plan
    due = due_slots(plan, "2026-11-22T21:00:00+07:00")
    assert [s["task_id"] for s in due] == ["b"]


def test_due_slots_khong_burst_late_boot():
    plan = build_day_plan("2026-11-22", POLICY, carryover=[],
                          new_items=_items("a", "b"))
    # boot som: chua slot nao den han
    assert due_slots(plan, "2026-11-22T08:00:00+07:00") == []
    # boot muon: chi slot den han, khong burst them
    due = due_slots(plan, "2026-11-22T12:00:00+07:00")
    assert len(due) == 1 and due[0]["task_id"] == "a"


def test_auto_pause_2_unknown_lien_tiep():
    assert should_auto_pause(["ok", "unknown", "unknown"]) is True
    assert should_auto_pause(["ok", "unknown"]) is False
    assert consecutive_unknowns([]) == 0


def test_caller_boot_vs_pause():
    """Caller phan biet (nguyen tac B): boot may tat -> tinh lai plan;
    user pause Page -> ton trong, khong post bu."""
    # paused outrank moi slot: caller khong goi due_slots khi paused
    paused_policy = {**POLICY, "status": "paused"}
    plan = build_day_plan("2026-11-22", paused_policy, [], _items("a"))
    assert plan["status"] == "paused"
    # caller that phai check status truoc due_slots (quy uoc, test mo ta)
    assert plan["status"] != "active"


def test_oracle_goc_khi_mount_duoc():
    try:
        from core.posting_schedule import (  # noqa
            build_day_plan as _orig_plan,
        )
    except Exception:
        import pytest
        pytest.skip("C:\\dubtool khong mount duoc")
        return
    policy = {"account": "x", "platform": "t", "daily_cap": 1}
    a = build_day_plan("2026-11-22", policy, [], _items("n1", "n2"))
    b = _orig_plan("2026-11-22", policy, [], _items("n1", "n2"))
    assert [s["task_id"] for s in a["slots"]] == [s["task_id"] for s in b["slots"]]
    assert a["storage"] == b["storage"]

"""Scheduler caller: paused/due/boot + verified ket thuc slot (P1 phan mo).

Chay: python -m pytest tests/test_schedule_caller.py -q (tu C:\\Miro\\apps\\backend).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.scheduling.schedule import (  # noqa: E402
    boot_action,
    build_day_plan,
    mark_slot_verified,
    select_due_intents,
)

POLICY = {"account": "haodaojrk5", "platform": "threads", "daily_cap": 2,
          "window": {"start": "09:00", "end": "21:00"}, "status": "active"}


def _items(*tids):
    return [SimpleNamespace(intent_id=t, shortcode=t, owner="haodaojrk5",
                            tag="#dub000001", text="x") for t in tids]


def _plan(items, status="active", date="2026-11-22"):
    pol = dict(POLICY, status=status)
    return build_day_plan(date, pol, [], [{"task_id": t, "shortcode": t}
                                            for t in items])


def test_paused_outrank_moi_slot():
    plan = _plan(["a", "b"], status="paused")
    due, deferred = select_due_intents(plan, _items("a", "b"),
                                       "2026-11-22T21:00:00+07:00")
    assert due == []
    assert {d["reason"] for d in deferred} == {"PAUSED"}


def test_khong_burst_chi_slot_den_han():
    plan = _plan(["a", "b"])  # slot 0 ~09:00, slot 1 ~15:00
    due, deferred = select_due_intents(plan, _items("a", "b"),
                                       "2026-11-22T10:00:00+07:00")
    assert [getattr(i, "intent_id") for i in due] == ["a"]
    assert [d["reason"] for d in deferred] == ["NOT_DUE"]


def test_boot_may_tat_rebuild_user_pause_respect():
    assert boot_action(False, "active") == "rebuild"
    assert boot_action(True, "active") == "respect"
    assert boot_action(False, "paused") == "respect"  # user pause ton trong


def test_verified_ket_thuc_slot_ra_khoi_queue():
    plan = _plan(["a", "b"])
    plan["slots"][0]["state"] = "unknown_pending_reconcile"
    plan["reconcile_queue"] = ["a"]
    mark_slot_verified(plan, "a")
    assert plan["slots"][0]["state"] == "verified"
    assert plan["reconcile_queue"] == []


def test_run_batch_ton_trong_paused(tmp_path):
    from miro.publishing.publisher import Publisher
    pub = Publisher(tmp_path / "pub", tmp_path / "att")
    pub.day_plan = _plan(["a"], status="paused")

    class NoPost:
        def post_once(self, intent):
            raise AssertionError("paused phai chan truoc post")

    out = pub.run_batch(_items("a"), NoPost())
    assert out and out[0].get("defer_reason") == "PAUSED"
    assert out[0].get("posted") is False

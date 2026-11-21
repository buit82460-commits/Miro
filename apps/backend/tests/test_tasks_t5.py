"""T5 RECOVER-tu-dong + L1 stop-cat-backoff.

Chay: python -m pytest tests/test_tasks_t5.py -q (tu C:\\Miro\\apps\\backend).
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.storage.db import TaskStore
from miro.tasks.models import TaskSubmitRequest
from miro.tasks.service import FakeRemote, TaskService


def make_service(tmp_path, remote=None, **kw):
    store = TaskStore(tmp_path / "tasks.db")
    return TaskService(store, None, remote or FakeRemote(), **kw)


def payload(**kw):
    base = {"request_id": "req-1", "message": "recover me",
            "videos": [{"project_id": "proj-1", "title": "Video A"}]}
    base.update(kw)
    return TaskSubmitRequest.model_validate(base)


def _dead_owner(rec):
    rec["status"] = "running"
    rec["worker_owner"] = {"pid": 999999999, "created_at": 1.0}  # da chet
    return rec


def test_t5_job_sach_con_budget_recover_auto(tmp_path):
    svc = make_service(tmp_path)
    rec = svc.submit(payload())
    rec = _dead_owner(rec)
    svc.store.upsert_task(rec)
    out = svc.restart(rec["id"])
    assert out["status"] == "queued"
    assert out["error"] is None
    assert out["retry_count"] == 1
    events = [e["type"] for e in svc.store.events(rec["id"])]
    assert "task_recovered" in events


def test_t5_het_budget_van_needs_attention(tmp_path):
    svc = make_service(tmp_path)
    rec = svc.submit(payload())
    rec = _dead_owner(rec)
    rec["retry_count"] = 2  # RECOVER_BUDGET=3 -> da het
    svc.store.upsert_task(rec)
    out = svc.restart(rec["id"])
    assert out["status"] == "needs_attention"
    assert out["error"]["code"] == "RESTARTED"


def test_t5_pending_mutation_khong_auto(tmp_path):
    svc = make_service(tmp_path)
    rec = svc.submit(payload())
    rec = _dead_owner(rec)
    rec["pending_mutation"] = {"item": 0, "step": "apply"}  # UNKNOWN
    svc.store.upsert_task(rec)
    out = svc.restart(rec["id"])
    assert out["status"] == "needs_attention"
    assert out["error"]["code"] == "REMOTE_RESULT_UNKNOWN"


def test_t5_chu_song_khong_auto(tmp_path):
    svc = make_service(tmp_path)
    rec = svc.submit(payload())
    rec["status"] = "running"  # chu = chinh process nay -> con song
    svc.store.upsert_task(rec)
    out = svc.restart(rec["id"])
    assert out["status"] == "needs_attention"
    assert out["error"]["code"] == "OWNERSHIP_UNKNOWN"


def test_t5_recover_xong_run_duoc(tmp_path):
    svc = make_service(tmp_path)
    rec = svc.submit(payload())
    rec = _dead_owner(rec)
    svc.store.upsert_task(rec)
    out = svc.restart(rec["id"])
    assert out["status"] == "queued"
    # import/track/assemble bump remote 1->4 nen apply chay o revision 4
    # (giong test cu); recover giua chung khong doi revision.
    svc.permissions.grant(rec["id"], 0, "edit", revision=4)
    done = asyncio.run(svc.run(rec["id"]))
    assert done["status"] == "completed"


def test_l1_stop_cat_ngang_backoff():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "miro_launcher", str(Path("C:/Miro/windows/miro.py")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    calls = {"n": 0}

    def fake_sleep(s):
        calls["n"] += 1
        if calls["n"] >= 3:
            mod.CONTROL.write_text('{"action": "stop"}', encoding="utf-8")

    orig_sleep, orig_control = mod.time.sleep, mod.CONTROL
    tmp = Path(orig_control).parent / "control-test.json"
    mod.CONTROL = tmp
    mod.time.sleep = fake_sleep
    try:
        if tmp.exists():
            tmp.unlink()
        stopped = mod._sleep_interruptible(30)
        assert stopped is True
        assert calls["n"] < 30 / 0.2  # cat som, khong ngu het 30s
    finally:
        mod.time.sleep = orig_sleep
        mod.CONTROL = orig_control
        if tmp.exists():
            tmp.unlink()

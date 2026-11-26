"""Repair Slice 04: route URL TikTok + lifecycle chot trang thai that."""
import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(BACKEND))

from miro.storage.db import TaskStore  # noqa: E402
from miro.tasks.models import TaskSubmitRequest  # noqa: E402
from miro.tasks.service import FakeRemote, TaskService  # noqa: E402
from miro.permissions.store import PermissionStore  # noqa: E402


def _svc(tmp):
    store = TaskStore(Path(tmp) / "tasks.db")
    return TaskService(store, PermissionStore(), FakeRemote())


def test_route_tiktok_url_direct(tmp_path):
    r = TaskService.route_message(
        "phan tich video tiktok https://www.tiktok.com/@just_meoz1810/video/7704985956977347861")
    assert r["job_type"] == "browser_video", r
    assert "7704985956977347861" in r["params"]["video_url"], r


def test_route_old_patterns_intact(tmp_path):
    assert TaskService.route_message(
        "kiem tra tai khoan tiktok dang nhap")["job_type"] == "browser_actor_check"
    r = TaskService.route_message("tim kiem tiktok KANS 377 tong hop 5 video")
    assert r["job_type"] == "browser_search", r


def test_no_route_match_finalizes_needs_attention(tmp_path):
    svc = _svc(str(tmp_path))
    rec = svc.submit(TaskSubmitRequest.model_validate(
        {"request_id": "req-noroute-1", "message": "xin chao the gioi",
         "videos": [{"project_id": "p1", "title": "V"}]}))
    out = asyncio.run(svc.run_task_message(rec["id"], tab_id=0))
    assert out.get("error") == "NO_ROUTE_MATCH", out
    stored = svc.get(rec["id"])
    assert stored["status"] == "needs_attention", stored
    assert stored["error"]["code"] == "NO_ROUTE_MATCH", stored
    print("no-route finalizes: PASS")


def _submit(svc, rid, msg):
    return svc.submit(TaskSubmitRequest.model_validate(
        {"request_id": rid, "message": msg,
         "videos": [{"project_id": rid, "title": msg[:100]}]}))


def test_finalize_browser_fail_closes_task(tmp_path):
    # Repair: NO_MANAGED_TAB / TAB_UNKNOWN cung phai NEEDS_ATTENTION,
    # khong de task ket queued mai (UI hien sai).
    svc = _svc(str(tmp_path))
    for rid, code in (("req-fin-1", "NO_MANAGED_TAB"),
                      ("req-fin-2", "TAB_UNKNOWN")):
        rec = _submit(svc, rid, "tim kiem tiktok KANS 377")
        out = {"ok": False, "error": code, "task_id": rec["id"]}
        svc._finalize_browser_task(rec["id"], out)
        stored = svc.get(rec["id"])
        assert stored["status"] == "needs_attention", stored
        assert stored["error"]["code"] == code, stored
    print("finalize-fail closes: PASS")


def test_finalize_browser_ok_completes(tmp_path):
    svc = _svc(str(tmp_path))
    rec = _submit(svc, "req-fin-3", "tim kiem tiktok KANS 377")
    svc._finalize_browser_task(rec["id"], {"ok": True,
                                           "task_id": rec["id"]})
    assert svc.get(rec["id"])["status"] == "completed"
    print("finalize-ok completes: PASS")

"""Slice 02 production caller: TaskService.run_browser_search_check.

Mirror test_slice01_production_caller: fake gateway.read_search_via_bridge,
khong network that. Bao gom route_message generic (keyword/limit bat ky)
va PARTIAL khi thieu record.
"""
import asyncio
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(BACKEND))

from miro.storage.db import TaskStore  # noqa: E402
from miro.tasks.models import TaskSubmitRequest  # noqa: E402
from miro.tasks.service import FakeRemote, TaskService  # noqa: E402
from miro.permissions.store import PermissionStore  # noqa: E402


def _svc(tmp):
    store = TaskStore(Path(tmp) / "tasks.db")
    bridge = {"session_id": "s", "token": "t", "backend_key": "k",
              "instance_id": "profile20-main", "base": "http://x/"}
    return TaskService(store, PermissionStore(), FakeRemote(), bridge=bridge)


def _payload(msg="tim kiem tiktok KANS 377 tong hop 5 video"):
    return TaskSubmitRequest.model_validate(
        {"request_id": "req-search-1", "message": msg,
         "videos": [{"project_id": "proj-1", "title": "Video A"}]})


def _ev(n=5):
    recs = [{"aweme_id": f"90000000000000{i}", "video_url": f"https://www.tiktok.com/@u{i}/video/90000000000000{i}",
             "author": f"@u{i}", "caption_preview": f"c{i}", "hashtags": "",
             "views": "", "likes": "1", "comments": "", "shares": "",
             "position": i + 1} for i in range(n)]
    return {"url": "https://www.tiktok.com/search?q=KANS", "tab_id": "7",
            "instance_id": "profile20-main", "records": recs, "count": n,
            "observed_at": 1.0, "record": {}, "provenance": "rea-eye",
            "platform": "tiktok", "lease": {}}


def test_route_search_generic(monkeypatch, tmp_path):
    r = TaskService.route_message('tim kiem tiktok "dep nam gia re" tong hop 10 video')
    assert r["job_type"] == "browser_search", r
    assert r["params"]["keyword"] == "dep nam gia re", r
    assert r["params"]["limit"] == 10, r
    r2 = TaskService.route_message("kiem tra tai khoan tiktok dang nhap")
    assert r2["job_type"] == "browser_actor_check", r2


def test_production_search_full(monkeypatch, tmp_path):
    import miro.browser.gateway as _gw

    async def fake_search(session_id, token, **kw):
        assert kw.get("instance_id") == "profile20-main"
        return {"ok": True, "evidence": _ev(5), "observation": {"spec": "search-videos"}}

    monkeypatch.setattr(_gw, "read_search_via_bridge", fake_search)
    svc = _svc(str(tmp_path))
    rec = svc.submit(_payload())
    out = asyncio.run(svc.run_browser_search_check(
        rec["id"], tab_id=7, live_origin="https://www.tiktok.com",
        limit=5))
    assert out.get("ok") and not out.get("partial"), out
    assert len(out["items"]) == 5, out
    assert out["items"][0]["video_url"].startswith("https://www.tiktok.com/@u0/video/"), out
    assert svc.get(rec["id"]).get("evidence"), "evidence phai persist"
    print("production search full: PASS")


def test_production_search_partial(monkeypatch, tmp_path):
    import miro.browser.gateway as _gw

    async def fake_search(session_id, token, **kw):
        return {"ok": True, "evidence": _ev(3), "observation": {"spec": "search-videos"}}

    monkeypatch.setattr(_gw, "read_search_via_bridge", fake_search)
    svc = _svc(str(tmp_path))
    rec = svc.submit(_payload())
    out = asyncio.run(svc.run_browser_search_check(
        rec["id"], tab_id=7, live_origin="https://www.tiktok.com",
        limit=5))
    assert out.get("ok") and out.get("partial"), out
    assert out["got"] == 3 and out["want"] == 5, out
    assert "missing" in out and "3/5" in out["missing"], out
    print("production search partial: PASS")


def test_run_message_distinct_request_ids_no_dedupe(tmp_path):
    """Regression (live): 2 message khac nhau khong duoc dedupe ve task cu.

    Router phai dat project_id = request_id rieng moi lan (khong phai
    "msg-task" chung), neu khong dedupe revision-level tra task cu ->
    route/limit sai (limit 7 van tra want=5 cua message truoc).
    """
    import uuid as _uuid
    svc = _svc(str(tmp_path))

    def _submit(msg):
        rid = "msg-%s" % _uuid.uuid4().hex[:12]
        return svc.submit(TaskSubmitRequest.model_validate({
            "request_id": rid, "message": msg,
            "videos": [{"project_id": rid, "title": msg[:100]}]}))

    r1 = _submit("tim kiem tiktok 5 video: KANS 377")
    r2 = _submit("tim tiktok 7 video: kem chong nang")
    assert r1["id"] != r2["id"], (r1["id"], r2["id"])
    assert (TaskService.route_message(
        r1["request"]["message"])["params"]["limit"] == 5)
    assert (TaskService.route_message(
        r2["request"]["message"])["params"]["limit"] == 7)

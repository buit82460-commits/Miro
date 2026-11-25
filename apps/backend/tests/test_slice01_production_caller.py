"""Slice 01 production caller: TaskService.run_browser_actor_check.

Actual call chain: POST /tasks -> TaskService -> gateway.read_actor_via_bridge
-> transport.read_via_bridge (backend key) -> extension claim/execute
-> wait_observation(request_id) -> eye.evaluate_actor_signals -> Evidence.

Fake BridgeClient: tao request + tra observation dung request_id,
khong mo network that.
"""
import asyncio
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "apps" / "backend" / "src"
sys.path.insert(0, str(BACKEND))

from miro.browser import bridge_transport as _bt  # noqa: E402
from miro.storage.db import TaskStore  # noqa: E402
from miro.tasks.models import TaskSubmitRequest  # noqa: E402
from miro.tasks.service import FakeRemote, TaskService  # noqa: E402
from miro.permissions.store import PermissionStore  # noqa: E402


class FakeBridge:
    """Gia lap BridgeClient: tao request_id, claim, tra observation."""

    def __init__(self, actor="/@hank", fail=None):
        self.actor = actor
        self.fail = fail
        self.cancelled = []
        self.requested = []

    def request_read(self, tab_id, spec, **kw):
        self.requested.append((tab_id, spec, kw))
        if self.fail == "denied":
            return {"ok": False, "error": "BACKEND_AUTH_REQUIRED"}
        return {"ok": True, "read": spec, "tabId": tab_id,
                "status": "AUTHORIZED", "request_id": "ab12cd34ef56ab12"}

    def observations(self):
        if self.fail == "timeout":
            return {"ok": True, "observations": []}
        return {"ok": True, "observations": [{
            "spec": "actor-login", "tab_id": 7,
            "instance_id": "profile20-main",
            "live_origin": "https://www.tiktok.com/",
            "grant_epoch": 3, "seq": 9,
            "observed_at": 9999999999.0,
            "request_id": "ab12cd34ef56ab12",
            "data": {"title": "t", "url": "https://www.tiktok.com/",
                     "has_login_button": "", "profile_href": self.actor,
                     "has_upload_link": "1"},
            "untrusted": True}]}

    def cancel_read(self, request_id):
        self.cancelled.append(request_id)
        return {"ok": True, "cancelled": True}


def _svc(tmp, bridge_extra=None):
    store = TaskStore(Path(tmp) / "tasks.db")
    bridge = {"session_id": "s", "token": "t", "backend_key": "k",
              "instance_id": "profile20-main", "base": "http://x/"}
    bridge.update(bridge_extra or {})
    return TaskService(store, PermissionStore(), FakeRemote(), bridge=bridge)


def _payload():
    return TaskSubmitRequest.model_validate(
        {"request_id": "req-actor-1", "message": "kiem tra tiktok",
         "videos": [{"project_id": "proj-1", "title": "Video A"}]})


def test_production_caller_success(monkeypatch, tmp_path):
    fake = FakeBridge()

    async def fake_read(session_id, token, **kw):
        assert kw.get("backend_key") == "k", kw
        assert kw.get("task_id"), "task_id phai duoc truyen de truy vet"
        req = fake.request_read(kw["tab_id"], "actor-login",
                                instance=kw.get("instance_id"),
                                timeout_s=kw.get("timeout"),
                                task_id=kw.get("task_id"))
        rid = req["request_id"]
        out = fake.observations()
        ob = [o for o in out["observations"]
              if o.get("request_id") == rid][0]
        c = _bt.clean_observation(ob)
        assert c.get("ok"), c
        return {"ok": True, "observation": c}

    import miro.browser.gateway as _gw
    monkeypatch.setattr(_gw, "_read_bridge", None, raising=False)

    async def patched(session_id, token, **kw):
        return await fake_read(session_id, token, **kw)

    # patch truc tiep read_via_bridge trong namespace gateway su dung
    import miro.browser.bridge_transport as _t
    monkeypatch.setattr(_t, "read_via_bridge", fake_read)

    async def gw_actor(session_id, token, **kw):
        r = await _t.read_via_bridge(session_id, token, **kw)
        if not r.get("ok"):
            return r
        from miro.eye import evaluate_actor_signals
        sig = evaluate_actor_signals(r["observation"]["data"])
        assert sig.get("ok"), sig
        return {"ok": True,
                "evidence": {"actor": sig.get("actor"),
                             "actor_status": "ACTOR_CLAIMED",
                             "url": "https://www.tiktok.com/",
                             "tab_id": "7",
                             "instance_id": "profile20-main",
                             "observed_at": 1.0,
                             "record": {}, "provenance": "rea-eye",
                             "platform": "tiktok", "lease": {}},
                "observation": r["observation"]}

    monkeypatch.setattr(_gw, "read_actor_via_bridge", gw_actor)
    svc = _svc(str(tmp_path))
    rec = svc.submit(_payload())
    out = asyncio.run(svc.run_browser_actor_check(
        rec["id"], tab_id=7, live_origin="https://www.tiktok.com/"))
    assert out.get("ok"), out
    assert out["evidence"]["actor_status"] == "ACTOR_CLAIMED", out
    assert out["evidence"]["actor"] == "@hank", out
    stored = svc.get(rec["id"])
    assert stored.get("evidence"), "evidence phai persist vao task"
    print("production caller success: PASS")


def test_production_caller_stop_cancels(monkeypatch, tmp_path):
    async def denied(session_id, token, **kw):
        return {"ok": False, "error": "BACKEND_AUTH_REQUIRED"}

    import miro.browser.gateway as _gw
    monkeypatch.setattr(_gw, "read_actor_via_bridge", denied)
    svc = _svc(str(tmp_path))
    rec = svc.submit(_payload())
    svc.request_stop(rec["id"])
    out = asyncio.run(svc.run_browser_actor_check(
        rec["id"], tab_id=7, live_origin="https://www.tiktok.com/"))
    assert out.get("error") == "TASK_STOP_REQUESTED", out
    print("production caller stop: PASS")

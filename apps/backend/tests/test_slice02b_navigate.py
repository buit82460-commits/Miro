"""Slice 02B navigate negative controls + autonomous orchestration.

Khong network that: fake BridgeClient + fake gateway. Moi test khang dinh
1 loi cu the: URL ngoai scope, redirect sai destination, sai Profile/tab,
grant het hieu luc, cancellation.
"""
import asyncio
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(BACKEND))

from miro.browser import gateway  # noqa: E402
import miro.browser.bridge_transport as bt  # noqa: E402
from miro.storage.db import TaskStore  # noqa: E402
from miro.tasks.models import TaskSubmitRequest  # noqa: E402
from miro.tasks.service import FakeRemote, TaskService  # noqa: E402
from miro.permissions.store import PermissionStore  # noqa: E402


class FakeNavClient:
    def __init__(self, obs=None, req_ok=True, nav_url=None):
        self._obs = obs
        self._req_ok = req_ok
        self._nav_url = nav_url

    def request_navigate(self, tab_id, url, **kw):
        if not self._req_ok:
            return {"ok": False, "error": "BACKEND_AUTH_REQUIRED"}
        from urllib.parse import urlparse
        try:
            p = urlparse(str(url or ""))
        except Exception:
            return {"ok": False, "error": "NAVIGATE_URL_INVALID"}
        if p.netloc != "www.tiktok.com":
            return {"ok": False, "error": "NAVIGATE_ORIGIN_DENIED"}
        return {"ok": True, "navigate": url, "status": "AUTHORIZED",
                "request_id": "r-nav-1"}

    def cancel_read(self, request_id):
        return {"ok": True}

    def observations(self):
        return {"ok": True, "observations": [self._obs] if self._obs else []}


def _obs_nav(url, **kw):
    base = {"spec": "navigate",
            "live_origin": url,
            "instance_id": "profile20-main", "tab_id": 7,
            "grant_epoch": 7, "seq": 1, "observed_at": time.time(),
            "request_id": "r-nav-1", "untrusted": True,
            "data": {"title": "t", "url": url}}
    base.update(kw)
    return base


def _run(coro):
    return asyncio.run(coro)


def test_bug11_miro_ui_tab_never_execution_target(monkeypatch, tmp_path):
    # BUG-11: autonomous Decide KHONG bao gio chon tab Miro UI
    # (localhost/:3100 tasks-live...) lam execution tab. Chi con tab
    # Miro UI -> NO_MANAGED_TAB fail-closed, khong navigate cuop tab user.
    import urllib.request as _u

    class _FakeResp:
        def read(self):
            return (b'{"ok": true, "tabs": [{"browser": "profile20-main",'
                    b' "tab": 1302904467,'
                    b' "url": "http://localhost:3100/tasks-live"}]}')

    monkeypatch.setattr(_u, "urlopen", lambda *a, **k: _FakeResp())
    store = TaskStore(Path(str(tmp_path)) / "tasks.db")
    svc = TaskService(store, PermissionStore(), FakeRemote(),
                      bridge={"instance_id": "profile20-main",
                              "base": "http://127.0.0.1:18767"})
    rec = svc.submit(TaskSubmitRequest.model_validate(
        {"request_id": "req-bug11", "message": "tim kiem tiktok 5 video KANS",
         "videos": [{"project_id": "p1", "title": "V"}]}))
    out = _run(svc.run_browser_autonomous_search(
        rec["id"], keyword="KANS", limit=5))
    assert out["error"] == "NO_MANAGED_TAB", out


def test_neg_navigate_outside_scope():
    r = _run(gateway.navigate_via_bridge(
        "", "", instance_id="profile20-main", tab_id=7,
        url="https://evil.example/phish"))
    assert r["error"] == "NAVIGATE_ORIGIN_DENIED", r


def test_neg_navigate_javascript_scheme():
    r = _run(gateway.navigate_via_bridge(
        "", "", instance_id="profile20-main", tab_id=7,
        url="javascript:alert(1)"))
    assert r["error"] == "NAVIGATE_ORIGIN_DENIED", r


def test_neg_navigate_backend_denied(monkeypatch):
    monkeypatch.setattr(bt, "BridgeClient",
                        lambda *a, **k: FakeNavClient(None, req_ok=False))
    r = _run(gateway.navigate_via_bridge(
        "", "", instance_id="profile20-main", tab_id=7,
        url="https://www.tiktok.com/search?q=X"))
    assert r["error"] == "BACKEND_AUTH_REQUIRED", r


def test_neg_navigate_mismatch(monkeypatch):
    # Extension bao URL khac target (redirect ngoai scope) -> tu choi.
    monkeypatch.setattr(
        bt, "BridgeClient",
        lambda *a, **k: FakeNavClient(
            _obs_nav("https://www.tiktok.com/foryou")))
    r = _run(gateway.navigate_via_bridge(
        "", "", instance_id="profile20-main", tab_id=7,
        url="https://www.tiktok.com/search?q=KANS"))
    assert r["error"] == "NAVIGATE_MISMATCH", r


def test_neg_navigate_wrong_instance(monkeypatch):
    monkeypatch.setattr(
        bt, "BridgeClient",
        lambda *a, **k: FakeNavClient(
            _obs_nav("https://www.tiktok.com/search?q=KANS")))
    r = _run(gateway.navigate_via_bridge(
        "", "", instance_id="profile20-OTHER", tab_id=7,
        url="https://www.tiktok.com/search?q=KANS"))
    assert r["error"] == "OBSERVED_INSTANCE_MISMATCH", r


def test_neg_navigate_wrong_tab(monkeypatch):
    # Observation tu tab khac tab duoc lenh: wait_observation loai bo
    # (fail-closed) -> TIMEOUT, khong bao gio nhan nham observation.
    monkeypatch.setattr(
        bt, "BridgeClient",
        lambda *a, **k: FakeNavClient(
            _obs_nav("https://www.tiktok.com/search?q=KANS", tab_id=999)))
    r = _run(gateway.navigate_via_bridge(
        "", "", instance_id="profile20-main", tab_id=7,
        url="https://www.tiktok.com/search?q=KANS"))
    assert r["error"] == "OBSERVATION_TIMEOUT", r


def test_neg_navigate_redirect_offsite(monkeypatch):
    # Redirect ra khoi TikTok giua chung -> tu choi.
    monkeypatch.setattr(
        bt, "BridgeClient",
        lambda *a, **k: FakeNavClient(
            _obs_nav("https://evil.example/phish")))
    r = _run(gateway.navigate_via_bridge(
        "", "", instance_id="profile20-main", tab_id=7,
        url="https://www.tiktok.com/search?q=KANS"))
    assert r["error"] == "NAVIGATE_MISMATCH", r


def test_neg_navigate_policy_revoked(monkeypatch):
    # Policy bi thu hoi giua chừng: server tu choi request.
    class _Revoked(FakeNavClient):
        def request_navigate(self, tab_id, url, **kw):
            return {"ok": False, "error": "POLICY_REVOKED"}

    monkeypatch.setattr(bt, "BridgeClient", lambda *a, **k: _Revoked(None))
    r = _run(gateway.navigate_via_bridge(
        "", "", instance_id="profile20-main", tab_id=7,
        url="https://www.tiktok.com/search?q=KANS"))
    assert r["error"] == "POLICY_REVOKED", r


def test_neg_navigate_cancelled(monkeypatch, tmp_path):
    async def fake_nav(*a, **k):
        raise AssertionError("da stop thi khong duoc goi gateway")

    monkeypatch.setattr(gateway, "navigate_via_bridge", fake_nav)
    store = TaskStore(Path(str(tmp_path)) / "tasks.db")
    svc = TaskService(store, PermissionStore(), FakeRemote(),
                      bridge={"instance_id": "profile20-main"})
    rec = svc.submit(TaskSubmitRequest.model_validate(
        {"request_id": "req-nav-stop", "message": "tim kiem tiktok 5 video",
         "videos": [{"project_id": "p1", "title": "V"}]}))
    svc.request_stop(rec["id"])
    out = _run(svc.run_browser_autonomous_search(
        rec["id"], keyword="KANS", limit=5))
    assert out["error"] == "TASK_STOP_REQUESTED", out


def test_autonomous_no_managed_tab(monkeypatch, tmp_path):
    import urllib.request as _u

    class _FakeResp:
        def read(self):
            return b'{"ok": true, "tabs": []}'

    monkeypatch.setattr(_u, "urlopen", lambda *a, **k: _FakeResp())
    store = TaskStore(Path(str(tmp_path)) / "tasks.db")
    svc = TaskService(store, PermissionStore(), FakeRemote(),
                      bridge={"instance_id": "profile20-main",
                              "base": "http://127.0.0.1:18767"})
    rec = svc.submit(TaskSubmitRequest.model_validate(
        {"request_id": "req-nav-notab", "message": "tim kiem tiktok 5 video",
         "videos": [{"project_id": "p1", "title": "V"}]}))
    out = _run(svc.run_browser_autonomous_search(
        rec["id"], keyword="KANS", limit=5))
    assert out["error"] == "NO_MANAGED_TAB", out


def test_act_skip_already_at_destination(monkeypatch, tmp_path):
    # Tab da dung san destination: skip tabs.update, van collect.
    import urllib.request as _u

    class _FakeResp:
        def read(self):
            return (b'{"ok": true, "tabs": [{"browser": "profile20-main",'
                    b' "tab": 7, "url": "https://www.tiktok.com/search?q=KANS"}]}')

    monkeypatch.setattr(_u, "urlopen", lambda *a, **k: _FakeResp())

    async def fake_cur(*a, **k):
        return {"ok": True, "observation": {
            "data": {"url": "https://www.tiktok.com/search?q=KANS"}}}

    async def fake_nav(*a, **k):
        raise AssertionError("da o dung noi thi khong navigate")

    async def fake_collect(self, task_id, **kw):
        assert kw.get("url", "").startswith(
            "https://www.tiktok.com/search?q=KANS"), kw
        return {"ok": True, "want": 5, "got": 5}

    monkeypatch.setattr(gateway, "read_current_url_via_bridge", fake_cur)
    monkeypatch.setattr(gateway, "navigate_via_bridge", fake_nav)
    monkeypatch.setattr(TaskService, "run_browser_search_check",
                        fake_collect)
    store = TaskStore(Path(str(tmp_path)) / "tasks.db")
    svc = TaskService(store, PermissionStore(), FakeRemote(),
                      bridge={"instance_id": "profile20-main",
                              "base": "http://127.0.0.1:18767"})
    rec = svc.submit(TaskSubmitRequest.model_validate(
        {"request_id": "req-nav-skip", "message": "tim kiem tiktok 5 video",
         "videos": [{"project_id": "p1", "title": "V"}]}))
    out = _run(svc.run_browser_autonomous_search(
        rec["id"], keyword="KANS", limit=5))
    assert out["ok"] is True and out["got"] == 5, out
    assert out["navigated_url"].startswith(
        "https://www.tiktok.com/search?q=KANS"), out


def test_act_recover_navigate_obs_lost(monkeypatch, tmp_path):
    # Navigate timeout nhung URL that da doi: verify lai roi collect.
    import urllib.request as _u

    class _FakeResp:
        def read(self):
            return (b'{"ok": true, "tabs": [{"browser": "profile20-main",'
                    b' "tab": 7, "url": "https://www.tiktok.com/"}]}')

    monkeypatch.setattr(_u, "urlopen", lambda *a, **k: _FakeResp())
    calls = {"n": 0}

    async def fake_cur(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"ok": False, "error": "OBSERVATION_TIMEOUT"}
        return {"ok": True, "observation": {
            "data": {"url": "https://www.tiktok.com/search?q=KANS"}}}

    async def fake_nav(*a, **k):
        return {"ok": False, "error": "OBSERVATION_TIMEOUT"}

    async def fake_collect(self, task_id, **kw):
        return {"ok": True, "want": 5, "got": 5}

    monkeypatch.setattr(gateway, "read_current_url_via_bridge", fake_cur)
    monkeypatch.setattr(gateway, "navigate_via_bridge", fake_nav)
    monkeypatch.setattr(TaskService, "run_browser_search_check",
                        fake_collect)
    store = TaskStore(Path(str(tmp_path)) / "tasks.db")
    svc = TaskService(store, PermissionStore(), FakeRemote(),
                      bridge={"instance_id": "profile20-main",
                              "base": "http://127.0.0.1:18767"})
    rec = svc.submit(TaskSubmitRequest.model_validate(
        {"request_id": "req-nav-rec", "message": "tim kiem tiktok 5 video",
         "videos": [{"project_id": "p1", "title": "V"}]}))
    out = _run(svc.run_browser_autonomous_search(
        rec["id"], keyword="KANS", limit=5))
    assert out["ok"] is True and out["got"] == 5, out


def test_route_video_level1a():
    r = TaskService.route_message("doc thong tin video dang mo nay")
    assert r["job_type"] == "browser_video", r


def test_search_url_for_encodes():
    u = TaskService.search_url_for("KANS 377 & test")
    assert u.startswith("https://www.tiktok.com/search?q="), u
    assert " " not in u and "&" not in u.split("q=", 1)[1], u
    assert TaskService.search_url_for("") == ""

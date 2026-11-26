"""Slice 02 negative controls: fail-closed moi diem binding/validation.

Khong network that: fake BridgeClient + FakeClient. Moi test khang dinh
1 loi cu the, khong khang dinh chung chung.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(BACKEND))

from miro.browser import gateway  # noqa: E402
from miro.browser.bridge_transport import (  # noqa: E402
    BridgeClient, READ_SPECS, SPEC_FIELDS)
import miro.browser.bridge_transport as bt  # noqa: E402
from miro.eye import tiktok_search_record  # noqa: E402
from miro.storage.db import TaskStore  # noqa: E402
from miro.tasks.models import TaskSubmitRequest  # noqa: E402
from miro.tasks.service import FakeRemote, TaskService  # noqa: E402
from miro.permissions.store import PermissionStore  # noqa: E402


class FakeClient:
    def __init__(self, obs=None, req_ok=True):
        self._obs = obs
        self._req_ok = req_ok

    def request_read(self, tab_id, spec, **kw):
        if not self._req_ok:
            return {"ok": False, "error": "BACKEND_AUTH_REQUIRED"}
        return {"ok": True, "read": spec, "status": "AUTHORIZED",
                "request_id": "r-neg-1"}

    def observations(self):
        return {"ok": True, "observations": [self._obs] if self._obs else []}


def _rec(n=2):
    return [{"aweme_id": f"7000000000000{i}", "video_url": f"https://www.tiktok.com/@u{i}/video/7000000000000{i}",
             "author": f"@u{i}", "caption_preview": f"c{i}", "hashtags": "",
             "views": "", "likes": "5", "comments": "", "shares": "",
             "position": i + 1} for i in range(n)]


def _obs(records, **kw):
    base = {"spec": "search-videos",
            "live_origin": "https://www.tiktok.com",
            "instance_id": "profile20-main", "tab_id": 7,
            "grant_epoch": 7, "seq": 1, "observed_at": time.time(),
            "request_id": "r-neg-1",
            "untrusted": True,
            "data": {"title": "t", "url": "https://www.tiktok.com/search?q=X",
                     "records": json.dumps(records)[:2000]}}
    base.update(kw)
    return base


def _run(coro):
    return asyncio.run(coro)


def test_neg_backend_denied(monkeypatch):
    monkeypatch.setattr(bt, "BridgeClient",
                        lambda *a, **k: FakeClient(_obs(_rec()), req_ok=False))
    r = _run(gateway.read_search_via_bridge(
        "", "", instance_id="profile20-main", tab_id=7,
        live_origin="https://www.tiktok.com"))
    assert r["error"] == "BACKEND_AUTH_REQUIRED", r


def test_neg_wrong_instance(monkeypatch):
    monkeypatch.setattr(bt, "BridgeClient",
                        lambda *a, **k: FakeClient(_obs(_rec())))
    r = _run(gateway.read_search_via_bridge(
        "", "", instance_id="profile20-OTHER", tab_id=7,
        live_origin="https://www.tiktok.com"))
    assert r["error"] == "OBSERVED_INSTANCE_MISMATCH", r


def test_neg_wrong_tab(monkeypatch):
    # wait_observation loc dung tab truoc -> sai tab = khong thay
    # observation (fail-closed tai lop loc, khong roi vao binding sau).
    monkeypatch.setattr(bt, "BridgeClient",
                        lambda *a, **k: FakeClient(_obs(_rec())))
    r = _run(gateway.read_search_via_bridge(
        "", "", instance_id="profile20-main", tab_id=999,
        live_origin="https://www.tiktok.com"))
    assert r["error"] == "OBSERVATION_TIMEOUT", r
    # Binding truc tiep: sai tab -> OBSERVED_TAB_MISMATCH.
    from miro.browser.observation import check_observed_binding
    b = check_observed_binding(obs_instance="profile20-main", obs_tab=7,
                               obs_url="https://www.tiktok.com",
                               obs_epoch=7, observed_at=time.time(),
                               instance_id="profile20-main", tab_id=999,
                               url=None, grant_epoch=7)
    assert b["error"] == "OBSERVED_TAB_MISMATCH", b


def test_neg_wrong_origin(monkeypatch):
    monkeypatch.setattr(bt, "BridgeClient",
                        lambda *a, **k: FakeClient(_obs(_rec())))
    r = _run(gateway.read_search_via_bridge(
        "", "", instance_id="profile20-main", tab_id=7,
        live_origin="https://www.youtube.com"))
    assert r["error"] == "ORIGIN_MISMATCH", r


def test_neg_stale_observation(monkeypatch):
    ob = _obs(_rec())
    ob["observed_at"] = time.time() - 400
    monkeypatch.setattr(bt, "BridgeClient",
                        lambda *a, **k: FakeClient(ob))
    r = _run(gateway.read_search_via_bridge(
        "", "", instance_id="profile20-main", tab_id=7,
        live_origin="https://www.tiktok.com"))
    assert r["error"] == "EVIDENCE_STALE", r


def test_neg_unparseable_records(monkeypatch):
    ob = _obs(_rec())
    ob["data"]["records"] = "not-json{{{"
    monkeypatch.setattr(bt, "BridgeClient",
                        lambda *a, **k: FakeClient(ob))
    r = _run(gateway.read_search_via_bridge(
        "", "", instance_id="profile20-main", tab_id=7,
        live_origin="https://www.tiktok.com"))
    assert r["error"] == "SEARCH_RECORDS_UNPARSEABLE", r


def test_neg_empty_records(monkeypatch):
    monkeypatch.setattr(bt, "BridgeClient",
                        lambda *a, **k: FakeClient(_obs([])))
    r = _run(gateway.read_search_via_bridge(
        "", "", instance_id="profile20-main", tab_id=7,
        live_origin="https://www.tiktok.com"))
    assert r["error"] == "SEARCH_NO_RECORDS", r


def test_neg_raw_observation_not_evidence():
    from miro.browser.errors import RegistryError
    try:
        gateway.check_evidence({"url": "https://www.tiktok.com/",
                                "provenance": "untrusted-raw",
                                "observed_at": time.time()})
    except RegistryError as exc:
        assert "EVIDENCE_INVALID" in str(exc), exc
        return
    raise AssertionError("raw observation phai bi tu choi")


def test_neg_media_analysis_not_evidence():
    from miro.browser.errors import RegistryError
    try:
        gateway.check_evidence({"url": "https://www.tiktok.com/",
                                "provenance": "media-analysis",
                                "observed_at": time.time()})
    except RegistryError as exc:
        assert "KHONG phai Evidence" in str(exc), exc
        return
    raise AssertionError("media-analysis phai bi tu choi lam Evidence")


def test_neg_stale_evidence():
    from miro.browser.errors import RegistryError
    try:
        gateway.check_evidence({"url": "https://www.tiktok.com/",
                                "tab_id": "7",
                                "provenance": "rea-eye",
                                "observed_at": time.time() - 400})
    except RegistryError as exc:
        assert "EVIDENCE_STALE" in str(exc), exc
        return
    raise AssertionError("evidence cu phai bi tu choi")


def test_neg_evidence_tab_mismatch():
    from miro.browser.errors import RegistryError
    try:
        gateway.check_evidence({"url": "https://www.tiktok.com/",
                                "tab_id": "7", "provenance": "rea-eye",
                                "observed_at": time.time()}, tab_id="8")
    except RegistryError as exc:
        assert "EVIDENCE_TAB_MISMATCH" in str(exc), exc
        return
    raise AssertionError("evidence sai tab phai bi tu choi")


def test_neg_route_unsupported():
    r = TaskService.route_message("xin chao hom nay troi dep qua")
    assert r["job_type"] == "unsupported", r


def test_neg_stop_requested(monkeypatch, tmp_path):
    async def fake_search(session_id, token, **kw):
        raise AssertionError("da stop thi khong duoc goi gateway")

    monkeypatch.setattr(gateway, "read_search_via_bridge", fake_search)
    store = TaskStore(Path(str(tmp_path)) / "tasks.db")
    svc = TaskService(store, PermissionStore(), FakeRemote(),
                      bridge={"instance_id": "x"})
    rec = svc.submit(TaskSubmitRequest.model_validate(
        {"request_id": "req-neg-stop", "message": "tim kiem tiktok 5 video",
         "videos": [{"project_id": "p1", "title": "V"}]}))
    svc.request_stop(rec["id"])
    out = _run(svc.run_browser_search_check(
        rec["id"], tab_id=7, live_origin="https://www.tiktok.com"))
    assert out["error"] == "TASK_STOP_REQUESTED", out


def test_neg_runtime_registry_has_no_browser_tool():
    from miro.agent.registry import default_registry
    reg = default_registry()
    names = reg.names()
    assert not any("browser" in n or "bridge" in n or n.startswith("shell")
                   for n in names), names
    for n in names:
        spec = reg.get(n)
        assert spec.capability in (
            "voice_change", "timeline_cut", "timeline_preview",
            "search", "read", "synthesize"), spec

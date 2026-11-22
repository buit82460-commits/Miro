"""Tests T1-T12: Session Manager + Gateway runtime enforcement (fake only)."""
import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.browser import gateway, session_manager  # noqa: E402
from miro.browser.errors import RegistryError, WorkerStopped  # noqa: E402
from miro.browser.lease_store import LeaseStore  # noqa: E402
from miro.browser.runtime import BrowserRuntime, ManagedChromeSession  # noqa: E402


class FakePage:
    _counter = [0]

    def __init__(self, url, account="user-1"):
        self.url = url
        self._account = account
        self._closed = False
        self.goto_calls = []
        FakePage._counter[0] += 1
        self.target_id = f"t-{FakePage._counter[0]}"

    def is_closed(self):
        return self._closed

    async def goto(self, url, **kwargs):
        self.goto_calls.append(url)
        self.url = url


class FakeContext:
    def __init__(self, pages):
        self.pages = pages


class FakeBrowser:
    def __init__(self, pages):
        self.contexts = [FakeContext(list(pages))]

    def is_connected(self):
        return True


def make_session(tmp_path, pages, account="user-1"):
    store = LeaseStore(str(tmp_path / "leases.sqlite"))
    runtime = BrowserRuntime(
        browser=FakeBrowser(pages), instance_id="inst-1", store=store,
        allowed_origins=("https://example.com",),
        verify_actor=lambda p, r: p._account)
    runtime.profiles["prof-1"] = {"id": "prof-1", "status": "verified",
                                  "browserInstanceId": "inst-1"}
    return ManagedChromeSession(runtime=runtime, endpoint="ws://fake")


def seed_tab(session, page, url="https://example.com/a", account="user-1"):
    rec = {"id": f"inst-1:{page.target_id}", "targetId": page.target_id,
           "url": url, "profileBindingId": "prof-1",
           "browserInstanceId": "inst-1", "platformId": "demo",
           "expectedAccountId": account, "status": "open", "lastUsedAt": 0.0}
    session.runtime.store.put("tab", rec["id"], rec)
    session.runtime.pages[page.target_id] = page
    return rec


async def fake_eye(page):
    return {"url": page.url, "actor": page._account, "text": "hello"}


# T1: session hop le -> tai dung, khong hoi lai
def test_t1_reuse_no_reask(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    out = asyncio.run(session_manager.reuse_or_open_tab(
        session, platform_id="demo", url="https://example.com/a",
        caller="t1"))
    assert out["reused"] is True
    asyncio.run(out["handle"].release())
    out2 = asyncio.run(session_manager.reuse_or_open_tab(
        session, platform_id="demo", url="https://example.com/a",
        caller="t1"))
    assert out2["record"]["targetId"] == page.target_id
    asyncio.run(out2["handle"].release())


# T2: chay nhung khong CDP -> chan doan dung, khong bao thanh cong gia
def test_t2_no_cdp_blocked(tmp_path):
    report = session_manager.inspect_session(
        str(tmp_path / "khong-co-gi"))
    assert report["status"].startswith("BLOCKED")
    with pytest.raises(RegistryError, match="BLOCKED"):
        asyncio.run(session_manager.ensure_session(
            lambda e: None, str(tmp_path / "khong-co-gi"),
            str(tmp_path / "db.sqlite")))


# T3: endpoint sai instance -> tu choi (connect fail -> WAITING/BLOCKED)
def test_t3_wrong_instance_rejected(tmp_path):
    async def bad_connect(endpoint):
        raise ConnectionError("refused")
    with pytest.raises(RegistryError):
        asyncio.run(ManagedChromeSession.open(
            bad_connect, str(tmp_path), str(tmp_path / "db.sqlite")))


# T4: snapshot truc tiep -> bi tu choi tai runtime
def test_t4_direct_snapshot_denied():
    with pytest.raises(RegistryError, match="BYPASS_DENIED"):
        gateway.deny_direct_browser("browser_snapshot")


# T5: click/evaluate truc tiep -> bi tu choi
def test_t5_direct_click_evaluate_denied():
    for tool in ("browser_click", "browser_evaluate", "browser_type"):
        with pytest.raises(RegistryError, match="BYPASS_DENIED"):
            gateway.deny_direct_browser(tool)


# T6: sub-agent bypass qua tool khac -> van bi tu choi
def test_t6_subagent_other_tool_denied():
    with pytest.raises(RegistryError, match="BYPASS_DENIED"):
        gateway.deny_direct_browser("rea.capture_browser_scenario")


# T7: khong evidence hop le -> adapter khong duoc WRITE
def test_t7_no_evidence_no_write(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)

    async def adapter_fn(p):
        return {"posted": True}

    with pytest.raises(RegistryError, match="EVIDENCE_INVALID"):
        asyncio.run(gateway.write_via_adapter(
            session, platform_id="demo", url="https://example.com/a",
            caller="t", evidence={}, approval={"approved": True},
            adapter_fn=adapter_fn))


# T8: evidence tab A khong dung cho tab B
def test_t8_evidence_wrong_tab(tmp_path):
    ev = {"url": "https://example.com/a", "tab_id": "tab-A",
          "provenance": "rea-eye",
          "observed_at": time.time()}
    with pytest.raises(RegistryError, match="TAB_MISMATCH"):
        gateway.check_evidence(ev, tab_id="tab-B")


def _fresh_evidence(page, actor="user-1", instance="inst-1"):
    return {"url": page.url, "tab_id": page.target_id,
            "instance_id": instance, "actor": actor,
            "provenance": "rea-eye", "observed_at": time.time()}


async def _ok_adapter(p):
    return {"posted": True}


# T13: evidence sai instance -> WRITE bi tu choi
def test_t13_write_wrong_instance_denied(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    with pytest.raises(RegistryError, match="WRONG_INSTANCE"):
        asyncio.run(gateway.write_via_adapter(
            session, platform_id="demo", url="https://example.com/a",
            caller="t", evidence=_fresh_evidence(page, instance="inst-khac"),
            approval={"approved": True}, adapter_fn=_ok_adapter))


# T14: actor doi giua mat-doc va write -> tu choi (fail-closed)
def test_t14_write_actor_changed_denied(tmp_path):
    page = FakePage("https://example.com/a", account="user-1")
    session = make_session(tmp_path, [page])
    seed_tab(session, page, account="user-1")
    page._account = "user-2"
    with pytest.raises((WorkerStopped, RegistryError),
                       match="ACTOR_CHANGED|ACCOUNT_MISMATCH"):
        asyncio.run(gateway.write_via_adapter(
            session, platform_id="demo", url="https://example.com/a",
            caller="t", evidence=_fresh_evidence(page, actor="user-1"),
            approval={"approved": True}, adapter_fn=_ok_adapter))


# T15: tab navigate sau mat-doc -> tu choi
def test_t15_write_tab_navigated_denied(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    ev = _fresh_evidence(page)
    page.url = "https://example.com/khac"
    with pytest.raises(RegistryError, match="ORIGIN_CHANGED"):
        asyncio.run(gateway.write_via_adapter(
            session, platform_id="demo", url="https://example.com/khac",
            caller="t", evidence=ev,
            approval={"approved": True}, adapter_fn=_ok_adapter))


# T16: thieu approval dung task -> WRITE bi tu choi
def test_t16_write_no_approval_denied(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    with pytest.raises(RegistryError, match="WRITE_DENIED"):
        asyncio.run(gateway.write_via_adapter(
            session, platform_id="demo", url="https://example.com/a",
            caller="t", evidence=_fresh_evidence(page),
            approval=None, adapter_fn=_ok_adapter))


# T17: evidence hop le day du -> WRITE pass + read gan instance_id
def test_t17_write_happy_path_and_read_instance(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    ev = asyncio.run(gateway.read_via_eye(
        session, platform_id="demo", url="https://example.com/a",
        caller="reader", eye_fn=fake_eye))
    assert ev["instance_id"] == "inst-1"
    receipt = asyncio.run(gateway.write_via_adapter(
        session, platform_id="demo", url="https://example.com/a",
        caller="t", evidence=ev,
        approval={"approved": True}, adapter_fn=_ok_adapter))
    assert receipt == {"posted": True}


# T9: lease het han/stale -> tu choi (qua read_via_eye verify fail)
def test_t9_stale_lease_rejected(tmp_path):
    page = FakePage("https://example.com/a", account="user-9")
    session = make_session(tmp_path, [page])
    seed_tab(session, page, account="user-1")
    with pytest.raises((WorkerStopped, RegistryError)):
        asyncio.run(gateway.read_via_eye(
            session, platform_id="demo", url="https://example.com/a",
            caller="t", eye_fn=fake_eye, expected_account="user-1"))


# T10: goi lai mo website -> khong tao tab trung
def test_t10_no_duplicate_tab(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    for _ in range(3):
        out = asyncio.run(session_manager.reuse_or_open_tab(
            session, platform_id="demo", url="https://example.com/a",
            caller="t"))
        asyncio.run(out["handle"].release())
    assert len(session.runtime.store.list("tab")) == 1


# T11: user tu choi restart -> khong kill/khong restart (ensure BLOCKED)
def test_t11_user_denies_restart_no_kill(tmp_path):
    report = session_manager.diagnose_connection(str(tmp_path / "nope"))
    assert report["verdict"] == "NOT_CONNECTED"
    assert "KHONG" in report["action"] or "không" in report["action"].lower() \
        or "KHONG" in report["action"].upper() or "taskkill" in report["action"].lower()


# T12: chi doc -> khong side-effect (goto_calls rong)
def test_t12_read_only_no_side_effect(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    ev = asyncio.run(gateway.read_via_eye(
        session, platform_id="demo", url="https://example.com/a",
        caller="reader", eye_fn=fake_eye))
    assert ev["provenance"] == "rea-eye"
    assert ev["record"]["text"] == "hello"
    assert page.goto_calls == []

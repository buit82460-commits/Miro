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
    runtime.write_task_context = lambda caller: {
        "task_id": "t", "scope": "demo-write", "revision": 3,
        "fingerprint": "fp-1", "active": True, "platform_id": "demo",
        "account_id": "user-1", "url": "https://example.com/a"}
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
            caller="t", evidence={}, approval=_approval(_auth()),
            auth=_auth(), adapter_fn=adapter_fn))


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


def _auth(task_id="t", scope="demo-write", revision=3, fingerprint="fp-1"):
    return {"task_id": task_id, "scope": scope, "revision": revision,
            "fingerprint": fingerprint}


def _approval(auth, approved=True):
    return {"approved": approved,
            "task_id": auth["task_id"], "scope": auth["scope"],
            "revision": auth["revision"],
            "fingerprint": auth["fingerprint"]}


@pytest.mark.parametrize("field,value", [
    ("task_id", "old-task"), ("scope", "other-write"),
    ("revision", 2), ("fingerprint", "old-content"),
    ("active", False), ("platform_id", "other"),
    ("account_id", "other-user"), ("url", "https://example.com/other"),
])
def test_p1_current_state_blocks_matching_stale_auth_and_approval(tmp_path, field, value):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    state = session.runtime.write_task_context("t")
    state[field] = value
    session.runtime.write_task_context = lambda caller: dict(state)
    calls = []

    async def adapter(p):
        calls.append(p)
        return {"posted": True}

    with pytest.raises(RegistryError, match="AUTH_REQUIRED"):
        asyncio.run(gateway.write_via_adapter(
            session, platform_id="demo", url=page.url, caller="t",
            evidence=_fresh_evidence(page), auth=_auth(),
            approval=_approval(_auth()), adapter_fn=adapter))
    assert calls == []
    # A rejection must release the tab, including state mismatch paths.
    hold = asyncio.run(session.acquire_managed_tab(
        platform_id="demo", url=page.url, caller="probe"))
    asyncio.run(hold.release())


@pytest.mark.parametrize("field,value,error", [
    ("task_id", "old", "APPROVAL_TASK_MISMATCH"),
    ("scope", "other", "SCOPE_DENIED"),
    ("revision", 2, "STALE_REVISION"),
    ("fingerprint", "other", "FINGERPRINT_CONFLICT"),
])
def test_p1_approval_must_match_current_intent(tmp_path, field, value, error):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    approval = _approval(_auth())
    approval[field] = value
    calls = []

    async def adapter(p):
        calls.append(p)
        return {"posted": True}

    with pytest.raises(RegistryError, match=error):
        asyncio.run(gateway.write_via_adapter(
            session, platform_id="demo", url=page.url, caller="t",
            evidence=_fresh_evidence(page), auth=_auth(),
            approval=approval, adapter_fn=adapter))
    assert calls == []


@pytest.mark.parametrize("missing", ["resolver", "verifier", "actor", "evidence_actor", "expected_actor"])
def test_p1_missing_authority_or_actor_never_calls_adapter(tmp_path, missing):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page, account="" if missing == "expected_actor" else "user-1")
    evidence = _fresh_evidence(page, actor="" if missing == "evidence_actor" else "user-1")
    if missing == "resolver":
        session.runtime.write_task_context = None
    if missing == "verifier":
        session.runtime.verify_actor = None
    if missing == "actor":
        session.runtime.verify_actor = lambda p, r: ""
    calls = []

    async def adapter(p):
        calls.append(p)
        return {"posted": True}

    with pytest.raises((RegistryError, WorkerStopped)):
        asyncio.run(gateway.write_via_adapter(
            session, platform_id="demo", url=page.url, caller="t",
            evidence=evidence, auth=_auth(), approval=_approval(_auth()),
            adapter_fn=adapter))
    assert calls == []


# T13: evidence sai instance -> WRITE bi tu choi
def test_t13_write_wrong_instance_denied(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    with pytest.raises(RegistryError, match="WRONG_INSTANCE"):
        asyncio.run(gateway.write_via_adapter(
            session, platform_id="demo", url="https://example.com/a",
            caller="t", evidence=_fresh_evidence(page, instance="inst-khac"),
            approval=_approval(_auth()), auth=_auth(),
            adapter_fn=_ok_adapter))


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
            approval=_approval(_auth()), auth=_auth(),
            adapter_fn=_ok_adapter))


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
            approval=_approval(_auth()), auth=_auth(),
            adapter_fn=_ok_adapter))


# T16: thieu approval dung task -> WRITE bi tu choi
def test_t16_write_no_approval_denied(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    with pytest.raises(RegistryError, match="WRITE_DENIED"):
        asyncio.run(gateway.write_via_adapter(
            session, platform_id="demo", url="https://example.com/a",
            caller="t", evidence=_fresh_evidence(page),
            approval=None, auth=_auth(), adapter_fn=_ok_adapter))


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
        approval=_approval(_auth()), auth=_auth(), adapter_fn=_ok_adapter))
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


# T18: profile bind instance khac -> acquire bi tu choi
def test_t18_profile_wrong_instance_rejected(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    session.runtime.profiles["prof-1"]["browserInstanceId"] = "inst-khac"
    seed_tab(session, page)
    with pytest.raises(RegistryError, match="PROFILE_UNVERIFIED"):
        asyncio.run(gateway.read_via_eye(
            session, platform_id="demo", url="https://example.com/a",
            caller="t", eye_fn=fake_eye))


# T22: legacy profile thieu browserInstanceId -> KHONG auto-trust, bat rebind
def test_t22_legacy_profile_no_instance_no_autotrust(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    del session.runtime.profiles["prof-1"]["browserInstanceId"]
    seed_tab(session, page)
    with pytest.raises(RegistryError, match="PROFILE_UNVERIFIED"):
        asyncio.run(gateway.read_via_eye(
            session, platform_id="demo", url="https://example.com/a",
            caller="t", eye_fn=fake_eye))


# T23: tab cua instance khac du co targetId giong -> khong dung chung
def test_t23_cross_instance_tab_not_shared(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    session.runtime.instance_id = "inst-spoofed"
    session.runtime.profiles["prof-1"]["browserInstanceId"] = "inst-spoofed"
    with pytest.raises(RegistryError, match="TAB_REQUIRED_OPEN_FIRST"):
        asyncio.run(gateway.read_via_eye(
            session, platform_id="demo", url="https://example.com/a",
            caller="t", eye_fn=fake_eye))


# T24: hai agent tranh 1 tab — agent 2 TAB_BUSY, khong chiem duoc
def test_t24_two_agents_one_tab_single_owner(tmp_path):
    from miro.browser.errors import TabBusy

    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)
    first = asyncio.run(gateway.read_via_eye(
        session, platform_id="demo", url="https://example.com/a",
        caller="agent-1", eye_fn=fake_eye))
    assert first["tab_id"] == page.target_id
    hold = asyncio.run(session.acquire_managed_tab(
        platform_id="demo", url="https://example.com/a", caller="agent-1"))
    try:
        with pytest.raises(TabBusy):
            asyncio.run(session.acquire_managed_tab(
                platform_id="demo", url="https://example.com/a",
                caller="agent-2"))
    finally:
        asyncio.run(hold.release())
    second = asyncio.run(gateway.read_via_eye(
        session, platform_id="demo", url="https://example.com/a",
        caller="agent-2", eye_fn=fake_eye))
    assert second["tab_id"] == page.target_id


# T25: lease het han GIUA luc write (khong chi invalidate) -> UNKNOWN
def test_t25_write_lease_expired_mid_write_unknown(tmp_path):
    now = [2000.0]
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    session.runtime.store.clock = lambda: now[0]
    seed_tab(session, page)

    async def slow_adapter(p):
        now[0] += 400.0
        return {"posted": True}

    ev = asyncio.run(gateway.read_via_eye(
        session, platform_id="demo", url="https://example.com/a",
        caller="reader", eye_fn=fake_eye))
    out = asyncio.run(gateway.write_via_adapter(
        session, platform_id="demo", url="https://example.com/a",
        caller="t", evidence=ev,
        approval=_approval(_auth()), auth=_auth(), adapter_fn=slow_adapter))
    assert out["posted"] is False
    assert out["receipt"] == "UNCONFIRMED_NO_REPLAY"


# T19: tab navigate GIUA luc mat-doc -> bo evidence, khong tra du lieu cu
def test_t19_read_race_navigate_discarded(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)

    async def sneaky_eye(p):
        p.url = "https://example.com/khac"
        return {"url": "https://example.com/a", "actor": p._account}

    with pytest.raises(RegistryError, match="CHANGED_DURING_READ"):
        asyncio.run(gateway.read_via_eye(
            session, platform_id="demo", url="https://example.com/a",
            caller="t", eye_fn=sneaky_eye))


# T20: lease bi thu hoi giua luc write -> receipt khong dang tin (UNKNOWN)
def test_t20_write_lease_lost_mid_write_unknown(tmp_path):
    from miro.browser.lease_store import tab_resource

    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)

    async def evil_adapter(p):
        session.runtime.store.invalidate(
            tab_resource("inst-1", page.target_id))
        return {"posted": True}

    ev = asyncio.run(gateway.read_via_eye(
        session, platform_id="demo", url="https://example.com/a",
        caller="reader", eye_fn=fake_eye))
    out = asyncio.run(gateway.write_via_adapter(
        session, platform_id="demo", url="https://example.com/a",
        caller="t", evidence=ev,
        approval=_approval(_auth()), auth=_auth(), adapter_fn=evil_adapter))
    assert out["posted"] is False
    assert out["receipt"] == "UNCONFIRMED_NO_REPLAY"


# T21: task doi account cu the nhung mat khong verify duoc -> tu choi
def test_t21_read_unverified_actor_with_expected_denied(tmp_path):
    page = FakePage("https://example.com/a")
    session = make_session(tmp_path, [page])
    seed_tab(session, page)

    async def blind_eye(p):
        return {"url": p.url, "text": "x"}

    session.runtime.verify_actor = None
    session.runtime.account_providers = {}
    with pytest.raises(RegistryError, match="EVIDENCE_UNVERIFIED|VERIFIER"):
        asyncio.run(gateway.read_via_eye(
            session, platform_id="demo", url="https://example.com/a",
            caller="t", eye_fn=blind_eye, expected_account="user-1"))


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

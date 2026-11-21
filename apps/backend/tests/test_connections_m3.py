"""M3 phan 1 Connections: verify that qua Browser M1 + revoke invalidate lease.

Test that trong C: FakeBrowser/FakePage trong bo nho + LeaseStore that + account store that.
Khong can Chrome that, khong Post that.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from test_browser_single_owner import FakeBrowser, FakePage, seed_profile, seed_tab

from miro.browser.errors import RegistryError
from miro.browser.lease_store import LeaseStore
from miro.browser.runtime import BrowserRuntime
from miro.connections import service as conn
from miro.connections import store as conn_store
from miro.connections.models import VerifyEvidence


def _account(platform="tiktok", account_id="kemkhongta", profile="prof-1"):
    from miro.connections.models import AccountCreate
    conn_store.reset()
    conn.set_revoke_hook(None)
    return conn.add_account(AccountCreate(
        platform=platform, account_id=account_id, display_name=account_id,
        credential_ref="vault://miro/x", profile_binding_id=profile,
        browser_instance_id="inst-1"))


def _runtime(tmp_path, page, verify=None):
    store = LeaseStore(tmp_path / "leases.sqlite")
    runtime = BrowserRuntime(
        browser=FakeBrowser([page]), instance_id="inst-1", store=store,
        allowed_origins=("https://example.com",),
        verify_actor=verify or (lambda p, r: p._account))
    return runtime, store


def _seed(runtime, store, page, target="t1", url="https://example.com/a", account="kemkhongta"):
    seed_profile(runtime)
    seed_tab(store, target=target, url=url, platform="tiktok", account=account)
    runtime.pages[target] = page
    return {"targetId": target, "url": url, "channelId": None}


def test_verify_via_browser_right_account(tmp_path):
    item = _account()
    page = FakePage("https://example.com/a", account="kemkhongta")
    runtime, store = _runtime(tmp_path, page)
    tab = _seed(runtime, store, page)
    out = asyncio.run(conn.verify_via_browser(item.id, runtime, tab))
    assert out.status == "connected"


def test_verify_via_browser_wrong_actor_rejected(tmp_path):
    item = _account()
    page = FakePage("https://example.com/a", account="tai-khoan-khac")
    runtime, store = _runtime(tmp_path, page)
    tab = _seed(runtime, store, page)
    with pytest.raises(Exception, match="ACCOUNT_MISMATCH|WORKER_STOPPED"):
        asyncio.run(conn.verify_via_browser(item.id, runtime, tab))


def test_verify_via_browser_before_after_mismatch(tmp_path):
    """Doi account giua chung (truoc/sau khac): tu choi."""
    conn_store.reset()
    conn.set_revoke_hook(None)
    item = _account()
    ev = VerifyEvidence(tab_id="t1", platform_id="tiktok", profile_binding_id="prof-1",
                        observed_account_id="kemkhongta", target_id="t1",
                        observed_account_id_after="tai-khoan-khac")
    with pytest.raises(RegistryError, match="ACCOUNT_MISMATCH"):
        conn.verify_account(item.id, ev)


def test_verify_via_browser_profile_path_changed(tmp_path):
    conn_store.reset()
    conn.set_revoke_hook(None)
    item = _account()
    ev = VerifyEvidence(tab_id="t1", platform_id="tiktok", profile_binding_id="prof-1",
                        observed_account_id="kemkhongta", target_id="t1",
                        profile_path="/a/Profile 1", profile_path_after="/a/Profile 2")
    with pytest.raises(RegistryError, match="PROFILE_MISMATCH"):
        conn.verify_account(item.id, ev)


def test_revoke_invalidates_worker_lease(tmp_path):
    """Thu hoi quyen -> hook invalidate lease -> worker cu mat quyen ngay."""
    item = _account()
    page = FakePage("https://example.com/a", account="kemkhongta")
    runtime, store = _runtime(tmp_path, page)
    tab = _seed(runtime, store, page)
    asyncio.run(conn.verify_via_browser(item.id, runtime, tab))

    invalidated = []
    conn.set_revoke_hook(lambda it: invalidated.append(it["id"]))
    try:
        revoked = conn.revoke_account(item.id)
    finally:
        conn.set_revoke_hook(None)
    assert revoked.status == "revoked"
    assert invalidated == [item.id]
    # Sau revoke, verify lai bi tu choi.
    with pytest.raises(RegistryError, match="ACCOUNT_REVOKED"):
        conn.verify_account(item.id, VerifyEvidence(
            tab_id="t1", platform_id="tiktok", profile_binding_id="prof-1",
            observed_account_id="kemkhongta", target_id="t1"))

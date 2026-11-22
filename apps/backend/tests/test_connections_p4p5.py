"""Connections P4/P5: profile_path that trong verify + revoke -> LeaseStore that.

Chay: python -m pytest tests/test_connections_p4p5.py -q (tu C:\\Miro\\apps\\backend).
Fake browser/page + LeaseStore that, khong Chrome that, khong post that.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from test_browser_single_owner import FakeBrowser, FakePage, seed_tab

from miro.browser.errors import LeaseLost, RegistryError
from miro.browser.lease_store import LeaseStore, tab_resource
from miro.browser.runtime import BrowserRuntime
from miro.connections import service as conn
from miro.connections import store as conn_store
from miro.connections.models import AccountCreate


def _account(platform="tiktok", account_id="kemkhongta", profile="prof-1"):
    conn_store.reset()
    conn.set_revoke_hook(None)
    return conn.add_account(AccountCreate(
        platform=platform, account_id=account_id, display_name=account_id,
        credential_ref="vault://miro/x", profile_binding_id=profile,
        browser_instance_id="inst-1"))


def _runtime_with_profile(tmp_path, page, profile_path):
    store = LeaseStore(tmp_path / "leases.sqlite")
    runtime = BrowserRuntime(
        browser=FakeBrowser([page]), instance_id="inst-1", store=store,
        allowed_origins=("https://example.com",),
        verify_actor=(lambda p, r: p._account))
    runtime.profiles["prof-1"] = {"id": "prof-1", "status": "verified",
                                  "profilePath": profile_path,
                                  "browserInstanceId": "inst-1"}
    return runtime, store


def test_p4_verify_that_truyen_profile_path(tmp_path):
    """P4: verify_via_browser lay profilePath tu Browser M1, truyen ca
    truoc/sau vao VerifyEvidence (nhanh realpath co hieu luc that)."""
    item = _account()
    page = FakePage("https://example.com/a", account="kemkhongta")
    runtime, store = _runtime_with_profile(tmp_path, page, "/x/Profile 20")
    seed_tab(store, target="t1", url="https://example.com/a",
             platform="tiktok", account="kemkhongta")
    runtime.pages["t1"] = page
    tab = {"targetId": "t1", "url": "https://example.com/a", "channelId": None}

    seen = {}
    real_verify = conn.verify_account

    def _capture(account_id, ev):
        seen["before"] = ev.profile_path
        seen["after"] = ev.profile_path_after
        return real_verify(account_id, ev)

    conn.verify_account = _capture
    try:
        out = asyncio.run(conn.verify_via_browser(item.id, runtime, tab))
    finally:
        conn.verify_account = real_verify
    assert out.status == "connected"
    assert seen["before"] == "/x/Profile 20"
    assert seen["after"] == "/x/Profile 20"


def test_p4_profile_doi_giua_chung_bi_chan(tmp_path):
    """P4 red-guard: profile duong dan doi giua truoc/sau -> PROFILE_MISMATCH."""
    import os
    from miro.connections.models import VerifyEvidence
    item = _account()
    d = tmp_path / "p1"
    d.mkdir()
    (tmp_path / "p2").mkdir()
    ev = VerifyEvidence(tab_id="t1", platform_id="tiktok", profile_binding_id="prof-1",
                        observed_account_id="kemkhongta", target_id="t1",
                        profile_path=str(d), profile_path_after=str(tmp_path / "p2"))
    with pytest.raises(RegistryError, match="PROFILE_MISMATCH"):
        conn.verify_account(item.id, ev)


def test_p5_revoke_invalidate_lease_that(tmp_path):
    """P5: bind_revoke_to_leases(store) -> revoke lam lease cu mat hieu luc
    ngay (validate -> LeaseLost), khong doi het TTL."""
    item = _account()
    store = LeaseStore(tmp_path / "leases.sqlite")
    seed_tab(store, target="t1", url="https://example.com/a",
             platform="tiktok", account="kemkhongta")
    lease = store.acquire(tab_resource("inst-1", "t1"), "worker-1", ttl=300)
    store.validate(lease)  # con hieu luc truoc revoke

    conn.bind_revoke_to_leases(store, instance_id="inst-1")
    try:
        revoked = conn.revoke_account(item.id)
    finally:
        conn.set_revoke_hook(None)
    assert revoked.status == "revoked"
    with pytest.raises(LeaseLost):
        store.validate(lease)


def test_p5_revoke_khac_account_khong_anh_huong(tmp_path):
    """P5 guard: revoke account A khong invalidate lease cua tab account B."""
    _account(account_id="kemkhongta")
    store = LeaseStore(tmp_path / "leases.sqlite")
    seed_tab(store, target="t1", url="https://example.com/a",
             platform="tiktok", account="nguoi-khac")
    lease_b = store.acquire(tab_resource("inst-1", "t1"), "worker-b", ttl=300)

    conn.bind_revoke_to_leases(store, instance_id="inst-1")
    try:
        conn.revoke_account("tiktok:kemkhongta")
    finally:
        conn.set_revoke_hook(None)
    store.validate(lease_b)  # van con hieu luc

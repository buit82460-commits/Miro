"""Browser M1: ManagedChromeSession + verify actor inject + rank reuse.

Chỉ READ (read/navigate fake trong bộ nhớ) — không post, không Chrome thật.
"""
from __future__ import annotations

import asyncio

import pytest

from miro.browser.errors import RegistryError, TabBusy, WorkerStopped
from miro.browser.lease_store import LeaseStore
from miro.browser.runtime import BrowserRuntime, ManagedChromeSession, chrome_endpoint

from test_browser_single_owner import FakeBrowser, FakePage, seed_profile, seed_tab


def make_runtime(tmp_path, pages, verify=None, origins=("https://example.com",)):
    store = LeaseStore(tmp_path / "leases.sqlite")
    runtime = BrowserRuntime(
        browser=FakeBrowser(pages), instance_id="inst-1", store=store,
        allowed_origins=origins, verify_actor=verify)
    return runtime, store


def test_reuse_same_tab_by_rank(tmp_path):
    """Tái dùng đúng tab theo rank (exact_url, channel, flag)."""
    p1 = FakePage("https://example.com/a")
    p2 = FakePage("https://example.com/b")
    runtime, store = make_runtime(tmp_path, [p1, p2])
    seed_profile(runtime)
    # 2 tab cùng platform, khác channel/flag/url
    seed_tab(store, target="old", url="https://example.com/b",
             channelId="other", flag="RESEARCH", lastUsedAt=1.0)
    seed_tab(store, target="best", url="https://example.com/a",
             channelId="chan-1", flag="PUBLISH", lastUsedAt=2.0)
    runtime.pages["old"] = p2
    runtime.pages["best"] = p1

    req = {"profileBindingId": "prof-1", "platformId": "demo",
           "url": "https://example.com/a", "channelId": "chan-1",
           "flag": "PUBLISH", "leaseTtl": 300}
    acquired = asyncio.run(runtime.acquire_tab(req, caller="task-1"))
    assert acquired.reused is True
    assert acquired.record["targetId"] == "best"
    asyncio.run(acquired.release())


def test_second_task_blocked_tab_busy(tmp_path):
    """Task thứ hai bị chặn TAB_BUSY khi tab đang bận — không tạo tab mới."""
    page = FakePage("https://example.com/a")
    runtime, store = make_runtime(tmp_path, [page])
    seed_profile(runtime)
    seed_tab(store, target="t1")
    runtime.pages["t1"] = page

    req = {"profileBindingId": "prof-1", "platformId": "demo",
           "url": "https://example.com/a", "leaseTtl": 300}
    first = asyncio.run(runtime.acquire_tab(req, caller="task-1"))
    with pytest.raises(TabBusy):
        asyncio.run(runtime.acquire_tab(req, caller="task-2"))
    assert len(store.list("tab")) == 1  # không tạo tab trùng
    asyncio.run(first.release())


def test_verify_actor_injected_before_and_after(tmp_path):
    """verify_actor inject: đúng account pass cả trước+sau; sai -> từ chối."""
    calls = []

    async def verify(page, record):
        calls.append(record.get("expectedAccountId"))
        return page._account

    page = FakePage("https://example.com/a", account="user-1")
    runtime, _ = make_runtime(tmp_path, [page], verify=verify)
    seed_profile(runtime)
    seed_tab(runtime.store, target="t1", account="user-1")
    runtime.pages["t1"] = page

    req = {"profileBindingId": "prof-1", "platformId": "demo",
           "url": "https://example.com/a", "leaseTtl": 300}
    acquired = asyncio.run(runtime.acquire_tab(req, caller="task-1"))
    asyncio.run(acquired.read())
    assert len(calls) == 2  # trước + sau read

    # Sai account -> từ chối, worker mất quyền (lease bị invalidate).
    page._account = "user-9"
    with pytest.raises(WorkerStopped, match="ACCOUNT_MISMATCH"):
        asyncio.run(acquired.read())
    with pytest.raises(WorkerStopped):
        asyncio.run(acquired.renew())
    asyncio.run(acquired.release())


def test_verify_actor_rejected_on_navigate(tmp_path):
    """Navigate cũng verify trước+sau: sai account -> từ chối, không goto."""
    async def verify(page, record):
        return page._account

    page = FakePage("https://example.com/a", account="user-1")
    runtime, _ = make_runtime(tmp_path, [page], verify=verify)
    seed_profile(runtime)
    seed_tab(runtime.store, target="t1", account="user-9")  # kỳ vọng khác
    runtime.pages["t1"] = page

    req = {"profileBindingId": "prof-1", "platformId": "demo",
           "url": "https://example.com/a", "leaseTtl": 300}
    acquired = asyncio.run(runtime.acquire_tab(req, caller="task-1"))
    with pytest.raises(WorkerStopped, match="ACCOUNT_MISMATCH"):
        asyncio.run(acquired.navigate("https://example.com/a"))
    assert page.goto_calls == []  # không điều hướng khi verify fail
    asyncio.run(acquired.release())


def test_disconnect_revokes_worker_no_autoreconnect(tmp_path):
    """disconnect -> worker cũ mất quyền; session cũ đóng, reconnect = open mới."""
    page = FakePage("https://example.com/a", account="user-1")

    async def connect(endpoint):
        connect.calls.append(endpoint)
        return FakeBrowser([page])

    connect.calls = []
    db = tmp_path / "leases.sqlite"
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "DevToolsActivePort").write_text(
        "10000\n/devtools/browser/abc", encoding="utf-8")

    async def flow():
        session = await ManagedChromeSession.open(
            connect, str(tmp_path / "profile"), db,
            verify_actor=lambda p, r: p._account)
        assert len(connect.calls) == 1  # đúng 1 connect_over_cdp / batch
        seed_profile(session.runtime)
        rec = seed_tab(session.runtime.store, target="t1", account="user-1")
        rec["browserInstanceId"] = session.runtime.instance_id
        rec["id"] = f"{session.runtime.instance_id}:t1"
        session.runtime.store.put("tab", rec["id"], rec)
        session.runtime.pages["t1"] = page
        acquired = await session.acquire_managed_tab(
            platform_id="demo", url="https://example.com/a", caller="task-1")
        assert acquired.reused is True
        result = await acquired.read()  # READ-ONLY, có text
        assert "hello" in result["content"]["text"]

        await session.runtime.disconnect()  # mất kết nối giữa chừng
        with pytest.raises(WorkerStopped):
            await acquired.renew()  # worker cũ mất quyền
        with pytest.raises(RegistryError, match="BROWSER_DISCONNECTED"):
            await session.acquire_managed_tab(  # session cũ không tự reconnect
                platform_id="demo", url="https://example.com/a", caller="task-2")
        await session.close()  # idempotent, không raise
        return session

    session = asyncio.run(flow())
    assert session.closed is True
    # Chrome không bị tắt bởi close(): FakeBrowser không có disconnect/kill.
    assert page.is_closed() is False
    # Reconnect thủ công = open session mới (connect lần 2).
    session2 = asyncio.run(ManagedChromeSession.open(
        connect, str(tmp_path / "profile"), db))
    assert len(connect.calls) == 2
    asyncio.run(session2.close())


def test_chrome_endpoint_no_autolaunch(tmp_path):
    """Chrome chưa bật remote-debugging -> CDP_UNAVAILABLE, không tự mở."""
    with pytest.raises(RegistryError, match="CDP_UNAVAILABLE"):
        chrome_endpoint(str(tmp_path / "no-such-dir"))
    assert chrome_endpoint.__doc__ is not None

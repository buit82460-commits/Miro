"""Fixture browser single-owner: 2 task tranh 1 tab, hết lease dừng, đổi tab giữa chừng.

Dùng fake browser/page trong bộ nhớ — không cần Chrome thật, không Post thật.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from miro.browser.errors import RegistryError, TabBusy, WorkerStopped
from miro.browser.lease_store import LeaseStore, tab_resource
from miro.browser.runtime import BrowserRuntime


class FakeLocator:
    def __init__(self, text: str = ""):
        self._text = text

    async def inner_text(self, timeout=None):
        return self._text


class FakePage:
    def __init__(self, url: str, account: str = "user-1", profile_path: str | None = None):
        self.url = url
        self._account = account
        self._profile_path = profile_path
        self._closed = False
        self.goto_calls: list[str] = []

    def is_closed(self):
        return self._closed

    def locator(self, selector: str):
        if selector == "#profile_path":
            return FakeLocator(self._profile_path or "")
        return FakeLocator("")

    async def evaluate(self, script, *args):
        if "miroUploadActive" in script:
            return {"activeUpload": False, "dirtyForm": False}
        limit = args[0] if args else 4000
        return {"url": self.url, "title": "t", "text": ("hello world " * 100)[:limit]}

    async def goto(self, url: str, **kwargs):
        self.goto_calls.append(url)
        self.url = url


class FakeContext:
    def __init__(self, pages):
        self.pages = pages


class FakeBrowser:
    def __init__(self, pages):
        self.contexts = [FakeContext(list(pages))]
        self.connected = True

    def is_connected(self):
        return self.connected


def make_runtime(tmp_path, pages, account="user-1", origins=("https://example.com",)):
    store = LeaseStore(tmp_path / "leases.sqlite")
    browser = FakeBrowser(pages)
    runtime = BrowserRuntime(browser=browser, instance_id="inst-1", store=store,
                             allowed_origins=origins,
                             account_providers={"demo": lambda page: page._account})
    return runtime, store


def seed_tab(store, target="t1", url="https://example.com/a", profile="prof-1",
             platform="demo", account="user-1", **extra):
    record = {"id": f"inst-1:{target}", "targetId": target, "url": url,
              "profileBindingId": profile, "browserInstanceId": "inst-1",
              "platformId": platform, "expectedAccountId": account,
              "status": "open", "lastUsedAt": 0.0, **extra}
    return store.put("tab", record["id"], record)


def seed_profile(runtime, profile_id="prof-1"):
    runtime.profiles[profile_id] = {"id": profile_id, "status": "verified"}
    return profile_id


def test_two_tasks_contend_one_tab(tmp_path):
    """2 task tranh 1 tab: task 2 nhận TAB_BUSY, không tạo tab trùng."""
    page = FakePage("https://example.com/a")
    runtime, store = make_runtime(tmp_path, [page])
    seed_profile(runtime)
    seed_tab(store, target="t1")
    runtime.pages["t1"] = page

    req = {"profileBindingId": "prof-1", "platformId": "demo",
           "url": "https://example.com/a", "leaseTtl": 300}
    first = asyncio.run(runtime.acquire_tab(req, caller="task-1"))
    assert first.reused is True

    with pytest.raises(TabBusy):
        asyncio.run(runtime.acquire_tab(req, caller="task-2"))

    # Tab trùng không được tạo: chỉ 1 record open.
    assert len(store.list("tab")) == 1
    asyncio.run(first.release())
    # Sau release, task 2 acquire được.
    second = asyncio.run(runtime.acquire_tab(req, caller="task-2"))
    assert second.reused is True
    asyncio.run(second.release())


def test_lease_expiry_stops_worker(tmp_path):
    """Hết lease giữa chừng: read -> WorkerStopped, worker dừng không replay."""
    now = [1000.0]
    page = FakePage("https://example.com/a")
    runtime, _ = make_runtime(tmp_path, [page])
    runtime.store = LeaseStore(tmp_path / "leases.sqlite", clock=lambda: now[0])
    seed_profile(runtime)
    seed_tab(runtime.store, target="t1")
    runtime.pages["t1"] = page

    req = {"profileBindingId": "prof-1", "platformId": "demo",
           "url": "https://example.com/a", "leaseTtl": 60}
    acquired = asyncio.run(runtime.acquire_tab(req, caller="task-1"))
    now[0] += 3600  # lease hết hạn
    with pytest.raises(WorkerStopped):
        asyncio.run(acquired.read())
    with pytest.raises(WorkerStopped):
        asyncio.run(acquired.renew())


def test_tab_switch_mid_read_stops_worker(tmp_path):
    """Đổi tab giữa chừng (URL evaluate khác record): read dừng, báo TAB_CHANGED."""
    page = FakePage("https://example.com/a")
    runtime, _ = make_runtime(tmp_path, [page])
    seed_profile(runtime)
    seed_tab(runtime.store, target="t1")
    runtime.pages["t1"] = page

    req = {"profileBindingId": "prof-1", "platformId": "demo",
           "url": "https://example.com/a", "leaseTtl": 300}
    acquired = asyncio.run(runtime.acquire_tab(req, caller="task-1"))
    page.url = "https://example.com/other"  # user đổi tab giữa chừng
    with pytest.raises(RegistryError, match="TAB_CHANGED_DURING_READ|TAB_ORIGIN_CHANGED"):
        asyncio.run(acquired.read())
    asyncio.run(acquired.release())


def test_account_switch_mid_read_stops_worker(tmp_path):
    """Đổi account giữa chừng: verify sau read phát hiện -> dừng."""
    page = FakePage("https://example.com/a", account="user-1")
    runtime, _ = make_runtime(tmp_path, [page])
    seed_profile(runtime)
    seed_tab(runtime.store, target="t1", account="user-1")
    runtime.pages["t1"] = page

    req = {"profileBindingId": "prof-1", "platformId": "demo",
           "url": "https://example.com/a", "leaseTtl": 300}
    acquired = asyncio.run(runtime.acquire_tab(req, caller="task-1"))

    real_evaluate = page.evaluate

    async def evil_evaluate(script, *args):
        if "miroUploadActive" not in script:
            page._account = "user-2"  # đổi account ngay trong lúc đọc
        return await real_evaluate(script, *args)

    page.evaluate = evil_evaluate
    with pytest.raises(RegistryError, match="ACCOUNT_MISMATCH"):
        asyncio.run(acquired.read())
    asyncio.run(acquired.release())


def test_protected_tab_no_navigate(tmp_path):
    """Tab Flag-watched / dirty: navigate bị chặn TAB_PROTECTED, không Post thật."""
    page = FakePage("https://example.com/a")
    runtime, _ = make_runtime(tmp_path, [page])
    seed_profile(runtime)
    seed_tab(runtime.store, target="t1", flagWatch={"origin": "https://example.com"})
    runtime.pages["t1"] = page

    req = {"profileBindingId": "prof-1", "platformId": "demo",
           "url": "https://example.com/a", "leaseTtl": 300}
    acquired = asyncio.run(runtime.acquire_tab(req, caller="task-1"))
    with pytest.raises(RegistryError, match="TAB_PROTECTED_NO_NAVIGATE"):
        asyncio.run(acquired.navigate("https://example.com/other"))
    assert page.goto_calls == []  # không điều hướng thật
    asyncio.run(acquired.release())


def test_single_owner_fence_token(tmp_path):
    """Fence/token: release bằng lease cũ sau khi owner mới acquire -> LeaseLost."""
    store = LeaseStore(tmp_path / "leases.sqlite")
    resource = tab_resource("inst-1", "t1")
    first = store.acquire(resource, "task-1", ttl=1)
    time.sleep(1.05)
    second = store.acquire(resource, "task-2", ttl=300)
    assert second["fence"] == first["fence"] + 1
    with pytest.raises(Exception):
        store.release(first)
    store.release(second)

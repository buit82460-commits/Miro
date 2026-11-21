"""Kiem chung chrome_endpoint (DevToolsActivePort kieu dubtool) + luat 1-tab/platform.

Fake hoan toan: khong Chrome that, khong CDP that, khong new_page/goto that.
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.browser import live_chrome  # noqa: E402
from miro.browser.errors import RegistryError  # noqa: E402
from miro.browser.lease_store import LeaseStore  # noqa: E402
from miro.browser.runtime import BrowserRuntime, ManagedChromeSession, chrome_endpoint  # noqa: E402


# -- fake --------------------------------------------------------------------

class FakePage:
    def __init__(self, url):
        self.url = url
        self._closed = False
        self.goto_calls: list = []

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


def make_session(tmp_path, pages, instance_id="inst-1"):
    store = LeaseStore(str(tmp_path / "leases.sqlite"))
    browser = FakeBrowser(pages)
    runtime = BrowserRuntime(browser=browser, instance_id=instance_id, store=store,
                             allowed_origins=("https://www.threads.com/",))
    return ManagedChromeSession(runtime=runtime, endpoint="ws://fake")


# -- 1. chrome_endpoint -------------------------------------------------------

def test_endpoint_reads_port_file(tmp_path):
    user_data = tmp_path / "User Data"
    user_data.mkdir()
    (user_data / "DevToolsActivePort").write_text(
        "9222\n/devtools/browser/abc-123\n", encoding="utf-8")
    assert chrome_endpoint(str(user_data)) == "ws://127.0.0.1:9222/devtools/browser/abc-123"


def test_endpoint_missing_file(tmp_path):
    with pytest.raises(RegistryError, match="CDP_UNAVAILABLE"):
        chrome_endpoint(str(tmp_path / "nope"))


def test_endpoint_bad_route(tmp_path):
    user_data = tmp_path / "User Data"
    user_data.mkdir()
    (user_data / "DevToolsActivePort").write_text(
        "9222\nsai-route\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="CDP_UNAVAILABLE"):
        chrome_endpoint(str(user_data))


def test_endpoint_bad_port(tmp_path):
    user_data = tmp_path / "User Data"
    user_data.mkdir()
    (user_data / "DevToolsActivePort").write_text(
        "notaport\n/devtools/browser/abc\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="CDP_UNAVAILABLE"):
        chrome_endpoint(str(user_data))


def test_endpoint_direct_passthrough_no_file_read(tmp_path):
    given = "ws://127.0.0.1:9333/devtools/browser/direct-1"
    assert chrome_endpoint(str(tmp_path / "khong-ton-tai"), endpoint=given) == given
    assert chrome_endpoint(str(tmp_path / "khong-ton-tai"), endpoint="  " + given + " ") == given


# -- 2. luat 1-tab/platform ---------------------------------------------------

URL_A = "https://www.threads.com/@user1/post/aaa"
URL_B = "https://www.threads.com/@user1/post/bbb-khac"


def test_second_tab_same_platform_reuses_first(tmp_path):
    page_a = FakePage(URL_A)
    page_b = FakePage(URL_B)
    session = make_session(tmp_path, [page_a, page_b])
    first = live_chrome.register_live_tab(
        session, URL_A, platform_id="threads", profile_id="prof-1")
    second = live_chrome.register_live_tab(
        session, URL_B, platform_id="threads", profile_id="prof-1")
    assert second["id"] == first["id"]
    assert second["url"] == URL_A  # giu tab cu, khong dang ky tab URL moi
    tabs = session.runtime.store.list("tab")
    assert len(tabs) == 1
    assert page_b.goto_calls == [] and page_a.goto_calls == []


def test_missing_tab_denied_no_new_page_or_goto(tmp_path):
    page = FakePage("https://www.threads.com/@user1/post/khac")
    session = make_session(tmp_path, [page])
    calls = []
    session.runtime.browser.new_page = lambda *a, **k: calls.append(1)  # neu goi la lo
    with pytest.raises(RegistryError, match="TAB_REQUIRED_OPEN_FIRST"):
        live_chrome.register_live_tab(
            session, URL_A, platform_id="threads", profile_id="prof-1")
    assert calls == []
    assert page.goto_calls == []
    assert session.runtime.store.list("tab") == []


def test_acquire_missing_tab_required_open_first_no_goto(tmp_path):
    page = FakePage("https://www.threads.com/@user1/post/khac")
    store = LeaseStore(str(tmp_path / "leases.sqlite"))
    browser = FakeBrowser([page])
    runtime = BrowserRuntime(browser=browser, instance_id="inst-1", store=store,
                             allowed_origins=("https://www.threads.com/",))
    runtime.profiles["prof-1"] = {"id": "prof-1", "status": "verified"}
    req = {"profileBindingId": "prof-1", "platformId": "threads",
           "url": URL_A, "leaseTtl": 300}
    with pytest.raises(RegistryError, match="TAB_REQUIRED_OPEN_FIRST"):
        asyncio.run(runtime.acquire_tab(req, caller="t"))
    assert page.goto_calls == []
    assert store.list("tab") == []

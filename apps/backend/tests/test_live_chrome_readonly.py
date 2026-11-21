"""Connector live-read Profile 20: fake CDP, 0 Chrome thật, 0 post.

Kiểm: open 1 connect duy nhất + bind profile + acquire + read 1 URL bài
Threads → trả text, rồi release + disconnect. Module không có post/submit.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.browser import live_chrome  # noqa: E402
from miro.browser.errors import RegistryError  # noqa: E402

URL = "https://www.threads.com/@haodaojrk5/post/dub417888"


class FakeLocator:
    def __init__(self, text):
        self._text = text

    async def inner_text(self, timeout=None):
        return self._text


class FakePage:
    _counter = [100]

    def __init__(self, url, profile_path=""):
        self.url = url
        self._profile_path = profile_path
        self._closed = False
        FakePage._counter[0] += 1
        self.target_id = f"target-{FakePage._counter[0]}"

    def is_closed(self):
        return self._closed

    def locator(self, selector):
        if selector == "#profile_path":
            return FakeLocator(self._profile_path)
        return FakeLocator("")

    async def evaluate(self, script, *args):
        if "miroUpload" in script:
            return {"activeUpload": False, "dirtyForm": False}
        limit = args[0] if args else 4000
        return {"url": self.url, "title": "bai dub417888",
                "text": ("noi dung bai dub417888 " * 50)[:limit]}


class FakeContext:
    def __init__(self, pages):
        self.pages = pages


class FakeBrowser:
    def __init__(self, pages):
        self.contexts = [FakeContext(list(pages))]
        self.connected = True
        self.disconnected = False

    def is_connected(self):
        return self.connected

    async def disconnect(self):
        self.disconnected = True
        self.connected = False


def _fake_env(tmp_path):
    user_data = tmp_path / "User Data"
    user_data.mkdir()
    (user_data / "DevToolsActivePort").write_text(
        "9222\n/devtools/browser/fake-route\n", encoding="utf-8")
    profile_dir = user_data / "Profile 20"
    profile_dir.mkdir()
    version_page = FakePage("chrome://version",
                            profile_path=str(profile_dir.resolve()))
    article = FakePage(URL)
    browser = FakeBrowser([version_page, article])

    async def connect(endpoint):
        assert endpoint == "ws://127.0.0.1:9222/devtools/browser/fake-route"
        return browser

    return str(user_data), str(tmp_path / "leases.sqlite"), browser, connect


def test_read_url_once_fake_cdp_no_post(tmp_path):
    user_data, db, browser, connect = _fake_env(tmp_path)
    out = asyncio.run(live_chrome.read_url_once(
        connect=connect, user_data_dir=user_data, database=db, url=URL,
        expected_account="haodaojrk5"))
    assert out["url"] == URL
    assert "dub417888" in out["text"]
    assert browser.disconnected is True


def test_module_has_no_post_path():
    import inspect
    import re
    src = inspect.getsource(live_chrome)
    assert re.search(r"(?m)^(?:async\s+)?def\s+post", src) is None
    assert "post_once" not in src
    assert re.search(r"(?m)^(?:async\s+)?def\s+(?:navigate|submit)", src) is None


def test_no_chrome_running_denied_without_opening(tmp_path):
    async def dead(endpoint):
        raise ConnectionError("refused")

    user_data = tmp_path / "empty"
    user_data.mkdir()
    (user_data / "DevToolsActivePort").write_text(
        "9222\n/devtools/browser/x\n", encoding="utf-8")
    try:
        asyncio.run(live_chrome.read_url_once(
            connect=dead, user_data_dir=str(user_data),
            database=str(tmp_path / "l.sqlite"), url=URL))
    except RegistryError as exc:
        assert "CDP_UNAVAILABLE" in str(exc) or "WAITING_CONFIRMATION" in str(exc)
    else:
        raise AssertionError("phai tu choi khi khong co Chrome, khong tu mo")

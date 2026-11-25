"""EXP feed-eye-bridge: feed-video spec + eye collector + gateway (no live)."""
import asyncio
import time

from miro.browser.bridge_transport import (
    BridgeClient, clean_observation, READ_SPECS, SPEC_FIELDS)
from miro.eye import evaluate_actor_signals


class FakeClient:
    def __init__(self, obs=None):
        self._obs = obs

    def request_read(self, tab_id, spec, **kw):
        return {"ok": True, "read": spec, "status": "AUTHORIZED"}

    def observations(self):
        return {"ok": True, "observations": [self._obs] if self._obs else []}


def _obs(spec="title", **kw):
    base = {"spec": spec, "live_origin": "https://www.tiktok.com",
            "instance_id": "profile20-main", "tab_id": 1302901352,
            "grant_epoch": 7, "seq": 1, "observed_at": time.time(),
            "untrusted": True}
    data = {f: ("https://www.tiktok.com/" if f == "url" else "v")
            for f in SPEC_FIELDS[spec]}
    base["data"] = data
    base.update(kw)
    return base


def test_feed_video_in_read_specs():
    assert "feed-video" in READ_SPECS
    for f in ("video_url", "aweme_id", "author", "caption_preview",
              "has_video"):
        assert f in SPEC_FIELDS["feed-video"]


def test_clean_feed_video_ok_and_rejects_extra():
    obs = _obs("feed-video", data={
        "title": "t", "url": "https://www.tiktok.com/",
        "video_url": "https://www.tiktok.com/@matdien/video/7500000001",
        "aweme_id": "7500000001", "author": "@matdien",
        "caption_preview": "Day84", "has_video": "1"})
    assert clean_observation(obs)["ok"] is True
    bad = _obs("feed-video", data=dict(obs["data"], evil="1"))
    assert clean_observation(bad)["error"] == "BAD_RESULT"


def _run(coro):
    return asyncio.run(coro)


def test_read_feed_video_via_bridge_ok(monkeypatch):
    import miro.browser.gateway as gw
    import miro.browser.bridge_transport as bt
    obs = _obs("feed-video", data={
        "title": "t", "url": "https://www.tiktok.com/",
        "video_url": "https://www.tiktok.com/@matdien/video/7500000001",
        "aweme_id": "7500000001", "author": "@matdien",
        "caption_preview": "Day84 dam cuoi", "has_video": "1"})
    monkeypatch.setattr(bt, "BridgeClient", lambda *a, **k: FakeClient(obs))
    monkeypatch.setattr(bt.time, "sleep", lambda s: None)
    r = _run(gw.read_feed_video_via_bridge(
        "s", "t", instance_id="profile20-main", tab_id=1302901352,
        live_origin="https://www.tiktok.com", grant_epoch=7))
    assert r.get("ok") is True
    ev = r["evidence"]
    assert ev["aweme_id"] == "7500000001"
    assert ev["author"] == "@matdien"
    assert ev["url"] == \
        "https://www.tiktok.com/@matdien/video/7500000001"
    assert ev["provenance"] == "rea-eye"


def test_read_feed_video_missing_fail(monkeypatch):
    import miro.browser.gateway as gw
    import miro.browser.bridge_transport as bt
    obs = _obs("feed-video", data={
        "title": "t", "url": "https://www.tiktok.com/",
        "video_url": "", "aweme_id": "", "author": "",
        "caption_preview": "", "has_video": ""})
    monkeypatch.setattr(bt, "BridgeClient", lambda *a, **k: FakeClient(obs))
    monkeypatch.setattr(bt.time, "sleep", lambda s: None)
    r = _run(gw.read_feed_video_via_bridge(
        "s", "t", instance_id="profile20-main", tab_id=1302901352,
        live_origin="https://www.tiktok.com", grant_epoch=7))
    assert r.get("ok") is False
    assert "FEED_VIDEO" in r.get("error", "")


class FakeA:
    def __init__(self, href, text="cap"):
        self._href = href
        self._text = text

    async def get_attribute(self, k):
        return self._href if k == "href" else ""

    def locator(self, sel):
        return FakeLoc(has=False)


class FakeLoc:
    def __init__(self, items=None, has=True):
        self._items = items or []
        self.first = self
        self._has = has

    async def all(self):
        return self._items

    async def count(self):
        return 1 if self._has else 0

    async def inner_text(self):
        return "Day84 caption"


class FakePage:
    url = "https://www.tiktok.com/"

    def locator(self, sel):
        if "/video/" in sel:
            return FakeLoc(items=[
                FakeA("/@matdien/video/7500000001"),
                FakeA("/@khac/video/7500000002")])
        return FakeLoc(has=False)


def test_eye_feed_video_first_anchor():
    from miro.eye import tiktok_feed_video_record

    async def go():
        return await tiktok_feed_video_record(FakePage())

    rec = asyncio.run(go())
    assert rec["post_id"] == "7500000001"
    assert rec["author"] == "@matdien"
    assert rec["url"] == \
        "https://www.tiktok.com/@matdien/video/7500000001"
    assert rec["has_video"] is True

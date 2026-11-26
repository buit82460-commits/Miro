"""Slice 02: search-videos spec + eye search record + gateway (no live)."""
import asyncio
import json
import time

from miro.browser import gateway
from miro.browser.bridge_transport import (
    BridgeClient, clean_observation, READ_SPECS, SPEC_FIELDS)
from miro.eye import tiktok_search_record


class FakeClient:
    def __init__(self, obs=None):
        self._obs = obs

    def request_read(self, tab_id, spec, **kw):
        return {"ok": True, "read": spec, "status": "AUTHORIZED",
                "request_id": "r-search-1"}

    def observations(self):
        return {"ok": True, "observations": [self._obs] if self._obs else []}


def _recs(n=3, bad=False):
    out = []
    for i in range(n):
        out.append({
            "aweme_id": f"100000000000000{i}" if not bad or i else "abc",
            "video_url": f"https://www.tiktok.com/@user{i}/video/100000000000000{i}",
            "author": f"@user{i}",
            "caption_preview": f"KANS 377 caption {i} #kans",
            "hashtags": "#kans",
            "views": "12.3K" if i else "",
            "likes": "850", "comments": "12", "shares": "3",
            "position": i + 1,
        })
    return out


def _obs(records):
    return {"spec": "search-videos",
            "live_origin": "https://www.tiktok.com",
            "instance_id": "profile20-main", "tab_id": 7,
            "grant_epoch": 7, "seq": 1, "observed_at": time.time(),
            "untrusted": True,
            "request_id": "r-search-1",
            "data": {"title": "t", "url": "https://www.tiktok.com/search?q=KANS",
                     "records": json.dumps(records)[:2000]}}


def test_search_videos_in_read_specs():
    assert "search-videos" in READ_SPECS
    assert set(SPEC_FIELDS["search-videos"]) == {"title", "url", "records"}
    c = clean_observation(_obs(_recs()))
    assert c["ok"]


def test_clean_rejects_extra_field():
    ob = _obs(_recs())
    ob["data"]["evil"] = "1"
    assert clean_observation(ob)["error"] == "BAD_RESULT"


def test_gateway_rejects_bad_identity():
    import miro.browser.bridge_transport as bt
    real_client = bt.BridgeClient
    bt.BridgeClient = lambda *a, **k: FakeClient(_obs(_recs(bad=True)))
    try:
        r = asyncio.run(gateway.read_search_via_bridge(
            "", "", instance_id="profile20-main", tab_id=7,
            live_origin="https://www.tiktok.com"))
    finally:
        bt.BridgeClient = real_client
    assert r["error"] == "SEARCH_IDENTITY_MISSING"


def test_gateway_returns_per_record_evidence():
    import miro.browser.bridge_transport as bt
    real_client = bt.BridgeClient
    bt.BridgeClient = lambda *a, **k: FakeClient(_obs(_recs()))
    try:
        r = asyncio.run(gateway.read_search_via_bridge(
            "", "", instance_id="profile20-main", tab_id=7,
            live_origin="https://www.tiktok.com"))
    finally:
        bt.BridgeClient = real_client
    assert r["ok"] and r["evidence"]["provenance"] == "rea-eye"
    assert len(r["evidence"]["records"]) == 3
    assert r["evidence"]["records"][0]["views"] == ""
    assert r["evidence"]["records"][1]["likes"] == "850"


class _FakeA:
    def __init__(self, href, text=""):
        self._href = href
        self._text = text

    async def get_attribute(self, name):
        return self._href

    def locator(self, sel):
        parent = self

        class _Scope:
            async def count(self):
                return 1

            @property
            def first(self):
                return self

            async def inner_text(self):
                return parent._text

            def locator(self, _sel):
                class _Inner:
                    @property
                    def first(self):
                        return self

                    async def inner_text(self):
                        return ""
                return _Inner()
        return _Scope()


class _FakePage:
    url = "https://www.tiktok.com/search?q=KANS"

    def locator(self, sel):
        class _L:
            async def all(self):
                return [_FakeA("/@user1/video/1001", "KANS 377 #kans"),
                        _FakeA("/@user2/video/1002", "KANS 377 #kans")]
            @property
            def first(self):
                return self

            async def count(self):
                return 0

            async def inner_text(self):
                return ""
        return _L()


def test_eye_search_records_independent():
    out = asyncio.run(tiktok_search_record(_FakePage(), limit=2))
    assert out["count"] == 2
    assert out["records"][0]["aweme_id"] == "1001"
    assert out["records"][1]["author"] == "@user2"
    assert out["records"][0]["position"] == 1

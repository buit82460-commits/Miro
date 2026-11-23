"""Phien A: production Bridge transport + Gateway wrappers (no live)."""
import asyncio
import time

from miro.browser import gateway
from miro.browser.bridge_transport import (
    BridgeClient, clean_observation, READ_SPECS, SPEC_FIELDS)


class FakeClient:
    def __init__(self, obs=None, err=None):
        self._obs = obs
        self._err = err
        self.requested = []

    def request_read(self, tab_id, spec):
        self.requested.append((tab_id, spec))
        return {"ok": True, "read": spec, "status": "AUTHORIZED"}

    def observations(self):
        if self._err:
            return {"ok": False, "error": self._err}
        return {"ok": True, "observations": [self._obs] if self._obs else []}

    def revoke(self):
        return {"ok": True, "revoked": 0}


def _obs(spec="title", **kw):
    base = {"spec": spec, "live_origin": "https://www.tiktok.com",
            "instance_id": "profile20-main", "tab_id": 1,
            "grant_epoch": 7, "seq": 1, "observed_at": time.time(),
            "untrusted": True}
    data = {f: ("https://www.tiktok.com/@x" if f == "url" else "v")
            for f in SPEC_FIELDS[spec]}
    base["data"] = data
    base.update(kw)
    return base


def test_specs_cover_video_identity():
    assert "video-identity" in READ_SPECS
    assert "aweme_id" in SPEC_FIELDS["video-identity"]


def test_clean_rejects_extra_field():
    bad = _obs()
    bad["data"]["evil"] = "1"
    assert clean_observation(bad)["error"] == "BAD_RESULT"


def test_clean_rejects_untrusted_false():
    bad = _obs()
    bad["untrusted"] = False
    assert clean_observation(bad)["error"] == "OBSERVATION_MUST_BE_UNTRUSTED"


def _run(coro):
    return asyncio.run(coro)


def test_read_actor_via_bridge_claimed(monkeypatch):
    import miro.browser.gateway as gw
    obs = _obs("actor-login", data={
        "title": "t", "url": "https://www.tiktok.com/@kemkhongta",
        "has_login_button": "", "profile_href": "/@kemkhongta",
        "has_upload_link": "1"})
    fake = FakeClient(obs=obs)
    import miro.browser.bridge_transport as bt
    monkeypatch.setattr(bt, "BridgeClient", lambda *a, **k: fake)
    monkeypatch.setattr(bt.time, "sleep", lambda s: None)
    r = _run(gw.read_actor_via_bridge(
        "s", "t", instance_id="profile20-main", tab_id=1,
        live_origin="https://www.tiktok.com",
        url="https://www.tiktok.com/@kemkhongta", grant_epoch=7))
    assert r.get("ok") is True
    assert r["evidence"]["actor"] == "@kemkhongta"
    assert r["evidence"]["actor_status"] == "ACTOR_CLAIMED"


def test_read_actor_unverified_fail(monkeypatch):
    import miro.browser.gateway as gw
    obs = _obs("actor-login", data={
        "title": "t", "url": "https://www.tiktok.com/",
        "has_login_button": "1", "profile_href": "",
        "has_upload_link": ""})
    fake = FakeClient(obs=obs)
    import miro.browser.bridge_transport as bt
    monkeypatch.setattr(bt, "BridgeClient", lambda *a, **k: fake)
    monkeypatch.setattr(bt.time, "sleep", lambda s: None)
    r = _run(gw.read_actor_via_bridge(
        "s", "t", instance_id="profile20-main", tab_id=1,
        live_origin="https://www.tiktok.com", grant_epoch=7))
    assert r.get("ok") is False
    assert "ACTOR_UNVERIFIED" in r.get("error", "")


def test_read_video_identity_ok_and_mismatch(monkeypatch):
    import miro.browser.gateway as gw
    import miro.browser.bridge_transport as bt
    obs = _obs("video-identity", data={
        "title": "t", "url": "https://www.tiktok.com/@x/video/7500000001",
        "aweme_id": "7500000001", "caption_preview": "hi",
        "has_video": "1"})
    fake = FakeClient(obs=obs)
    monkeypatch.setattr(bt, "BridgeClient", lambda *a, **k: fake)
    monkeypatch.setattr(bt.time, "sleep", lambda s: None)
    ok = _run(gw.read_video_via_bridge(
        "s", "t", instance_id="profile20-main", tab_id=1,
        live_origin="https://www.tiktok.com",
        url="https://www.tiktok.com/@x/video/7500000001",
        grant_epoch=7, expected_aweme="7500000001"))
    assert ok.get("ok") is True
    assert ok["evidence"]["aweme_id"] == "7500000001"
    bad = _run(gw.read_video_via_bridge(
        "s", "t", instance_id="profile20-main", tab_id=1,
        live_origin="https://www.tiktok.com",
        url="https://www.tiktok.com/@x/video/7500000001",
        grant_epoch=7, expected_aweme="999"))
    assert bad.get("error") == "VIDEO_IDENTITY_MISMATCH"

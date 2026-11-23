"""Test Bridge read transport cho Gateway (Phien A, read-only).

Gateway la diem vao duy nhat; transport chi doc tab da grant; actor qua
title luon UNVERIFIED; replay/cross-tab/forged/stale deu fail-closed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.bridge_reader import BridgeReadTransport  # noqa: E402
from bridge.grants import GrantStore  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 20000.0

    def __call__(self):
        return self.t


def _setup():
    clk = Clock()
    g = GrantStore(clock=clk)
    obs = {}
    t = BridgeReadTransport(g, obs, clock=clk)
    b, tab, o = "profile20-main", 894, "https://www.tiktok.com/"
    assert g.grant(b, tab, o, 1)["ok"]
    obs[(b, tab, 1)] = {"spec": "title", "live_origin": o,
                        "data": {"title": "TikTok - Make Your Day",
                                 "url": o},
                        "untrusted": True, "observed_at": clk()}
    return t, clk, (b, tab, o)


def test_transport_read_ok():
    t, clk, (b, tab, o) = _setup()
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=1)
    assert r["ok"] and r["observation"]["untrusted"] is True, r
    assert r["observation"]["data"]["title"] == "TikTok - Make Your Day", r
    print("transport doc observation da grant: PASS")


def test_transport_negative():
    t, clk, (b, tab, o) = _setup()
    # Replay seq -> tu choi.
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=1)
    assert r["ok"]
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=1)
    assert r["error"] == "OBSERVATION_REPLAY", r
    # Cross-tab: grant tab A khong doc duoc tab B.
    r = t.read(browser_instance_id=b, tab_id=999, live_origin=o, seq=1)
    assert r["error"] == "GRANT_REQUIRED", r
    # Forged origin: khac origin -> thu hoi grant.
    r = t.read(browser_instance_id=b, tab_id=tab,
               live_origin="https://evil.example/", seq=1)
    assert r["error"] == "ORIGIN_MISMATCH", r
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=1)
    assert r["error"] == "GRANT_REQUIRED", r  # da bi thu hoi
    # Stale: observation qua 300s -> tu choi (grant cap lai de con han).
    t2, clk2, (b2, tab2, o2) = _setup()
    clk2.t += 200  # grant het han o 120s, cap grant moi seq 2
    from bridge.grants import GRANT_TTL_S
    assert GRANT_TTL_S == 120
    g2 = t2._grants
    g2.grant(b2, tab2, o2, 2)
    t2._observations[(b2, tab2, 2)] = dict(t2._observations[(b2, tab2, 1)])
    t2._observations[(b2, tab2, 2)]["observed_at"] = clk2() - 400
    r = t2.read(browser_instance_id=b2, tab_id=tab2, live_origin=o2, seq=2)
    assert r["error"] == "EVIDENCE_STALE", r
    print("transport negative (replay/cross-tab/forged/stale): PASS")


def test_actor_always_unverified():
    t, clk, (b, tab, o) = _setup()
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=1)
    assert r["ok"]
    a = t.verify_actor(r["observation"])
    assert a["error"] == "ACTOR_UNVERIFIED", a
    print("actor qua title luon UNVERIFIED: PASS")


def test_actor_login_verified_and_negative():
    t, clk, (b, tab, o) = _setup()
    # Grant seq 2 + observation actor-login hop le.
    assert t._grants.grant(b, tab, o, 2)["ok"]
    t._observations[(b, tab, 2)] = {
        "spec": "actor-login", "live_origin": o,
        "data": {"title": "TikTok - Make Your Day", "url": o,
                 "has_login_button": "", "profile_href": "/@kemkhongta",
                 "has_upload_link": "1"},
        "untrusted": True, "observed_at": clk()}
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=2)
    assert r["ok"], r
    a = t.verify_actor(r["observation"])
    assert a == {"ok": True, "actor": "@kemkhongta"}, a
    # Forged: khong login (con nut Log in) -> UNVERIFIED.
    assert t._grants.grant(b, tab, o, 3)["ok"]
    t._observations[(b, tab, 3)] = {
        "spec": "actor-login", "live_origin": o,
        "data": {"title": "TikTok - Make Your Day", "url": o,
                 "has_login_button": "1", "profile_href": "/@kemkhongta",
                 "has_upload_link": "1"},
        "untrusted": True, "observed_at": clk()}
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=3)
    assert r["ok"], r
    a = t.verify_actor(r["observation"])
    assert a["error"] == "ACTOR_UNVERIFIED" and \
        "has_login_button" in a["missing"], a
    # Wrong tab: grant tab A khong doc duoc observation cua tab B.
    t._observations[(b, 999, 4)] = {
        "spec": "actor-login", "live_origin": o,
        "data": {"title": "TikTok", "url": o,
                 "has_login_button": "", "profile_href": "/@other",
                 "has_upload_link": "1"},
        "untrusted": True, "observed_at": clk()}
    r = t.read(browser_instance_id=b, tab_id=999, live_origin=o, seq=4)
    assert r["error"] == "GRANT_REQUIRED", r
    # Thieu profile_href (comment/caption khong du) -> UNVERIFIED.
    assert t._grants.grant(b, tab, o, 5)["ok"]
    t._observations[(b, tab, 5)] = {
        "spec": "actor-login", "live_origin": o,
        "data": {"title": "TikTok - Make Your Day", "url": o,
                 "has_login_button": "", "profile_href": "",
                 "has_upload_link": "1"},
        "untrusted": True, "observed_at": clk()}
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=5)
    assert r["ok"], r
    a = t.verify_actor(r["observation"])
    assert a["error"] == "ACTOR_UNVERIFIED" and \
        "profile_href" in a["missing"], a
    print("actor-login VERIFIED + negative (forged/thieu/wrong-tab): PASS")


if __name__ == "__main__":
    test_transport_read_ok()
    test_transport_negative()
    test_actor_always_unverified()
    test_actor_login_verified_and_negative()

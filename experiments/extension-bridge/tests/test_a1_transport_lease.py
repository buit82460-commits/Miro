"""A1: BridgeReadTransport + lease binding (OBSERVED-level, fail-closed).

Scope rieng A1: transport/mo rong bridge_reader (pre/post validation gan
lease: live_origin + grant epoch + freshness 300s + replay + revoke/
navigation) + DOM Observation Interface (locator hep + url/title +
evaluate-readonly). KHONG sua file cua agent khac.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.bridge_reader import BridgeReadTransport  # noqa: E402
from bridge.grants import GrantStore  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 50000.0

    def __call__(self):
        return self.t


def _setup():
    clk = Clock()
    g = GrantStore(clock=clk)
    obs = {}
    t = BridgeReadTransport(g, obs, clock=clk)
    b, tab, o = "profile20-main", 894, "https://www.tiktok.com/"
    assert g.grant(b, tab, o, 7)["ok"]
    obs[(b, tab, 7)] = {"spec": "title", "live_origin": o,
                        "data": {"title": "TikTok - Make Your Day", "url": o},
                        "untrusted": True, "observed_at": clk()}
    lease = {"instance_id": b, "tab_id": tab, "url": o, "grant_epoch": 7,
             "ttl": 300}
    return t, clk, g, obs, (b, tab, o), lease


def test_a1_read_ok_with_lease():
    t, clk, g, obs, (b, tab, o), lease = _setup()
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=7,
               lease=lease)
    assert r["ok"], r
    ob = r["observation"]
    assert ob["grant_epoch"] == 7, ob
    assert ob["untrusted"] is True, ob
    assert ob["instance_id"] == b and ob["tab_id"] == tab, ob
    print("A1 read ok voi lease binding: PASS")


def test_a1_backward_compat_no_lease():
    t, clk, g, obs, (b, tab, o), lease = _setup()
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=7)
    assert r["ok"], r
    print("A1 backward-compat (khong lease): PASS")


def test_a1_epoch_mismatch_denied():
    t, clk, g, obs, (b, tab, o), lease = _setup()
    bad = dict(lease, grant_epoch=6)
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=7,
               lease=bad)
    assert r["error"] == "OBSERVED_EPOCH_MISMATCH", r
    # Grant moi (re-grant epoch 8): lease cu het hieu luc ngay.
    assert g.grant(b, tab, o, 8)["ok"]
    obs[(b, tab, 8)] = {"spec": "title", "live_origin": o,
                        "data": {"title": "TikTok", "url": o},
                        "untrusted": True, "observed_at": clk()}
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=8,
               lease=lease)
    assert r["error"] == "OBSERVED_EPOCH_MISMATCH", r
    print("A1 epoch mismatch (stale lease sau re-grant): PASS")


def test_a1_tab_instance_mismatch_denied():
    t, clk, g, obs, (b, tab, o), lease = _setup()
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=7,
               lease=dict(lease, tab_id=999))
    assert r["error"] == "OBSERVED_TAB_MISMATCH", r
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=7,
               lease=dict(lease, instance_id="other-instance"))
    assert r["error"] == "OBSERVED_INSTANCE_MISMATCH", r
    print("A1 tab/instance mismatch: PASS")


def test_a1_revoke_navigation_denied():
    t, clk, g, obs, (b, tab, o), lease = _setup()
    # Navigation khac origin -> grant bi thu hoi, lease cu vo hieu.
    r = t.read(browser_instance_id=b, tab_id=tab,
               live_origin="https://evil.example/", seq=7, lease=lease)
    assert r["error"] == "ORIGIN_MISMATCH", r
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=7,
               lease=lease)
    assert r["error"] in ("GRANT_REQUIRED", "OBSERVED_EPOCH_MISMATCH"), r
    # Revoke chu dong -> lease cu vo hieu.
    t2, clk2, g2, obs2, (b2, tab2, o2), lease2 = _setup()
    assert g2.revoke_tab(b2, tab2) is True
    r = t2.read(browser_instance_id=b2, tab_id=tab2, live_origin=o2, seq=7,
                lease=lease2)
    assert r["error"] in ("GRANT_REQUIRED", "OBSERVED_EPOCH_MISMATCH"), r
    print("A1 revoke/navigation thu hoi grant: PASS")


def test_a1_stale_and_replay_with_lease():
    t, clk, g, obs, (b, tab, o), lease = _setup()
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=7,
               lease=lease)
    assert r["ok"], r
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=7,
               lease=lease)
    assert r["error"] == "OBSERVATION_REPLAY", r
    # Stale: observation qua 300s.
    assert g.grant(b, tab, o, 9)["ok"]
    lease9 = dict(lease, grant_epoch=9)
    obs[(b, tab, 9)] = {"spec": "title", "live_origin": o,
                        "data": {"title": "TikTok", "url": o},
                        "untrusted": True, "observed_at": clk() - 400}
    r = t.read(browser_instance_id=b, tab_id=tab, live_origin=o, seq=9,
               lease=lease9)
    assert r["error"] == "EVIDENCE_STALE", r
    print("A1 stale + replay voi lease: PASS")


def test_a1_locator_and_read_op():
    t, clk, g, obs, (b, tab, o), lease = _setup()
    assert t.check_locator({"kind": "role", "value": "main"})["ok"]
    assert t.check_locator({"kind": "text", "value": "Log in"})["ok"]
    # Kind la / JS / qua dai -> tu choi.
    assert t.check_locator({"kind": "xpath",
                            "value": "//div"})["error"] == \
        "LOCATOR_KIND_DENIED"
    assert t.check_locator({"kind": "css",
                            "value": "evaluate(document)"})["error"] == \
        "LOCATOR_EVALUATE_DENIED"
    assert t.check_locator({"kind": "role", "value": "x" * 300})["error"] == \
        "LOCATOR_TOO_WIDE"
    assert t.check_locator({"kind": "role"})["error"] == "LOCATOR_INVALID"
    # Op doc cho phep; evaluate/op ghi bi tu choi.
    assert t.check_read_op("text")["ok"]
    assert t.check_read_op("evaluate")["error"] == "READ_SPEC_DENIED"
    assert t.check_read_op("click")["error"] == "READ_SPEC_DENIED"
    print("A1 locator hep + evaluate-readonly: PASS")


def test_a1_observation_interface_binding():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent
                           .parent / "apps" / "backend" / "src"))
    from miro.browser.observation import (check_narrow_locator,
                                          check_read_op,
                                          validate_dom_observation)
    assert check_narrow_locator({"kind": "role",
                                 "value": "main"})["ok"]
    assert check_narrow_locator({"kind": "css",
                                 "value": "evaluate(1)"})["error"] == \
        "LOCATOR_EVALUATE_DENIED"
    assert check_read_op("click")["error"] == "READ_SPEC_DENIED"
    obs = {"spec": "title", "locator": {"kind": "role", "value": "main"},
           "op": "text", "live_origin": "https://www.tiktok.com/",
           "url": "https://www.tiktok.com/",
           "instance_id": "profile20-main", "tab_id": 894, "grant_epoch": 7,
           "observed_at": 50000.0, "untrusted": True, "data": {}}
    lease = {"instance_id": "profile20-main", "tab_id": 894,
             "url": "https://www.tiktok.com/", "grant_epoch": 7, "ttl": 300}
    import time as _t
    r = validate_dom_observation(obs, lease, clock=lambda: 50010.0)
    assert r["ok"], r
    r = validate_dom_observation(obs, dict(lease, grant_epoch=6),
                                 clock=lambda: 50010.0)
    assert r["error"] == "OBSERVED_EPOCH_MISMATCH", r
    print("A1 observation interface binding: PASS")


if __name__ == "__main__":
    test_a1_read_ok_with_lease()
    test_a1_backward_compat_no_lease()
    test_a1_epoch_mismatch_denied()
    test_a1_tab_instance_mismatch_denied()
    test_a1_revoke_navigation_denied()
    test_a1_stale_and_replay_with_lease()
    test_a1_locator_and_read_op()
    test_a1_observation_interface_binding()

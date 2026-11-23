"""Test grant-theo-tab + read_spec (sau va B1/B2/B3/W3).

B1: khong tin gesture client; grant can grant_seq don dieu.
B2: origin LIVE, mismatch -> thu hoi.
B3: DOM result tach khoi registry (registry poisoning).
W3: snapshot thieu complete -> khong xoa.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.channel import BridgeChannel  # noqa: E402
from bridge.grants import GrantStore, validate_read_spec  # noqa: E402
from bridge.registry import TabRegistry  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 9000.0

    def __call__(self):
        return self.t


def test_grant_no_gesture_trust():
    # B1: grant() khong con nhan gesture; ke tan cong gui gesture gia
    # cung khong anh huong (tham so bi loai khoi chu ky).
    import inspect
    assert "gesture" not in inspect.signature(GrantStore.grant).parameters, \
        "grant() phai loai bo tham so gesture"
    print("B1 khong tin gesture client: PASS")


def test_grant_seq_replay():
    g = GrantStore(clock=Clock())
    b = "profile20-main"
    o = "https://www.tiktok.com/"
    r = g.grant(b, 395, o, 1)
    assert r["ok"], r
    # Replay cung seq -> tu choi.
    r = g.grant(b, 395, o, 1)
    assert r["error"] == "GRANT_REPLAY", r
    # Seq moi -> cap lai duoc.
    r = g.grant(b, 395, o, 2)
    assert r["ok"], r
    print("B1 grant_seq chong replay: PASS")


def test_grant_flow():
    g = GrantStore(clock=Clock())
    b = "profile20-main"
    o = "https://www.tiktok.com/"
    # Origin khong duoc cap -> tu choi.
    r = g.grant(b, 395, "https://evil.example/", 1)
    assert r["error"] == "ORIGIN_NOT_GRANTED", r
    r = g.grant(b, 395, o, 1)
    assert r["ok"], r
    assert g.check(b, 395, o)["ok"]
    assert g.check(b, 999, o)["error"] == "GRANT_REQUIRED"
    # B2: origin LIVE khac -> thu hoi ngay.
    assert g.check(b, 395, "https://evil.example/")["error"] \
        == "ORIGIN_MISMATCH"
    assert g.check(b, 395, o)["error"] == "GRANT_REQUIRED", \
        "grant phai bi thu hoi sau mismatch"
    # Het han -> tu choi.
    g.grant(b, 395, o, 2)
    g._clock.t += 200
    assert g.check(b, 395, o)["error"] == "GRANT_EXPIRED"
    print("grant-theo-tab (origin/seq/expiry/revoke): PASS")


def test_read_spec_fixed():
    assert validate_read_spec("title")["ok"]
    assert validate_read_spec("meta")["ok"]
    assert validate_read_spec("text-limited")["ok"]
    assert validate_read_spec("actor-login")["ok"]
    for bad in ("evaluate", "document.cookie", "innerHTML",
                "querySelector", "", None, "TITLE"):
        r = validate_read_spec(bad)
        assert r["error"] == "READ_SPEC_DENIED", (bad, r)
    print("read_spec co dinh (4 spec, cam arbitrary JS): PASS")


def test_b3_read_result_isolation():
    # B3: DOM title gia mao KHONG duoc ghi de registry.
    reg = TabRegistry()
    b = "profile20-main"
    reg.apply("updated", b, 395, url="https://www.tiktok.com/",
              title="TikTok - Make Your Day")
    before = reg.tabs[(b, 395)].title
    # Mo phong /read-result: chi luu observation, khong apply vao registry.
    evil_title = "TikTok - Verified Account"
    assert reg.tabs[(b, 395)].title == before  # registry giu nguyen
    assert evil_title != before  # title gia khac that
    print("B3 registry khong bi DOM poisoning: PASS")


def test_w3_incomplete_snapshot():
    reg = TabRegistry()
    b = "profile20-main"
    reg.apply("updated", b, 381, url="https://www.tiktok.com/")
    # Thieu complete -> khong xoa (fail-closed).
    r = reg.reconcile_snapshot(b, [{"tabId": 389}], generation=1,
                               complete=False)
    assert r["removed"] == [] and (b, 381) in reg.tabs, r
    print("W3 snapshot thieu complete -> khong xoa: PASS")


def test_channel_still_blocks_write():
    ch = BridgeChannel(clock=Clock())
    ok = ch.redeem(ch.issue_pairing_code(), "profile20-main")
    for bad in ("click", "type", "evaluate", "debugger", "dom", "readDOM"):
        r = ch.push_events(ok["session_id"], ok["token"], 1,
                           [{"event": "opened", "tabId": 1, "action": bad}])
        assert r["error"] == "ACTION_FORBIDDEN", (bad, r)
    print("channel van cam WRITE tren duong doc: PASS")


if __name__ == "__main__":
    test_grant_no_gesture_trust()
    test_grant_seq_replay()
    test_grant_flow()
    test_read_spec_fixed()
    test_b3_read_result_isolation()
    test_w3_incomplete_snapshot()
    test_channel_still_blocks_write()

"""Test bo sung bao mat: pairing TTL/lock, origin, query, action cam."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.channel import BridgeChannel  # noqa: E402
from bridge import server as srv  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 3000.0

    def __call__(self):
        return self.t


def test_security():
    ch = BridgeChannel(clock=Clock())
    # Pairing code TTL ngan: het han -> INVALID.
    code = ch.issue_pairing_code()
    ch._clock.t += 200
    r = ch.redeem(code, "profile20-main")
    assert r["error"] == "PAIRING_INVALID", r
    # 5 lan sai -> khoa.
    for _ in range(5):
        ch.redeem("000000", "profile20-main")
    r = ch.redeem("000001", "profile20-main")
    assert r["error"] == "PAIRING_LOCKED", r
    # Gioi han code song song.
    ch2 = BridgeChannel(clock=Clock())
    codes = [ch2.issue_pairing_code() for _ in range(6)]
    assert codes[-1] == "", codes
    # Origin: website http(s) la bi tu choi; extension/khong Origin duoc.
    assert srv._origin_ok("") is True
    assert srv._origin_ok("chrome-extension://abc") is True
    assert srv._origin_ok("https://evil.example/") is False
    assert srv._origin_ok("http://127.0.0.1:18767/") is False
    # Action ghi bi cam o tang channel (clock moi, khong bi lock).
    ch3 = BridgeChannel(clock=Clock())
    ok = ch3.redeem(ch3.issue_pairing_code(), "profile20-main")
    r = ch3.push_events(ok["session_id"], ok["token"], 1,
                        [{"event": "opened", "tabId": 1,
                          "action": "evaluate"}])
    assert r["error"] == "ACTION_FORBIDDEN", r
    print("security (pairing TTL+lock, origin, action cam): PASS")


if __name__ == "__main__":
    test_security()

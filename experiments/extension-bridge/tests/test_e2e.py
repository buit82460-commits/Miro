"""Nghiem thu buoc 3: pairing -> push tu dong -> registry, khong nhap tay."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.channel import BridgeChannel  # noqa: E402
from bridge.importer import import_outbox  # noqa: E402
from bridge.registry import TabRegistry  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 2000.0

    def __call__(self):
        return self.t


def test_e2e():
    ch = BridgeChannel(clock=Clock())
    reg = TabRegistry()
    # Pairing 1 lan (server cap instance rieng).
    code = ch.issue_pairing_code()
    r = ch.redeem(code, "profile20-main")
    assert r["ok"] and r.get("instance_id"), r
    inst = r["instance_id"]
    sid, tok = r["session_id"], r["token"]
    # Mo tab TikTok (event that tu log user) -> push seq 1.
    seq = 1
    evs = [{"event": "opened", "tabId": 1302900374, "url": "",
            "title": "New Tab", "status": "loading"}]
    r = ch.push_events(sid, tok, seq, evs)
    assert r["ok"], r
    assert import_outbox(reg, r["instance"], r["events"]) == 1
    # Doi URL (event that) -> push seq 2.
    seq = 2
    evs = [{"event": "url-changed", "tabId": 1302900374,
            "url": "https://www.tiktok.com/@nghecontent9699",
            "title": "tiktok.com/@nghecontent9699", "status": "loading"}]
    r = ch.push_events(sid, tok, seq, evs)
    assert r["ok"], r
    assert import_outbox(reg, r["instance"], r["events"]) == 1
    assert reg.tabs[(inst, 1302900374)].url.endswith(
        "@nghecontent9699")
    # Dong tab -> push seq 3 -> registry loai bo.
    seq = 3
    r = ch.push_events(sid, tok, seq,
                       [{"event": "closed", "tabId": 1302900374}])
    assert r["ok"], r
    assert import_outbox(reg, r["instance"], r["events"]) == 1
    assert (inst, 1302900374) not in reg.tabs
    # Restart service worker: resync voi full list rong -> khong con tab nao.
    r = ch.resync(sid, tok, 4, [])
    assert r["ok"] and r["live_tab_ids"] == [], r
    # Khong session hop le -> tu choi.
    r = ch.push_events("x", "y", 9, evs)
    assert r["error"] == "SESSION_UNKNOWN", r
    print("buoc3 e2e (pair->push->registry, mo/doi/dong/resync): PASS")


if __name__ == "__main__":
    test_e2e()

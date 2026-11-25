"""Test kenh xac thuc: handshake, seq, replay, resync, revoke, fail-closed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.channel import BridgeChannel  # noqa: E402
from bridge.registry import TabRegistry  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_full():
    ch = BridgeChannel(clock=Clock())
    # 1. Khong session -> tu choi.
    r = ch.push_events("no", "no", 1, [])
    assert r == {"ok": False, "error": "SESSION_UNKNOWN"}, r
    # 2. Pairing + redeem (server cap instance_id rieng, khong tin client).
    code = ch.issue_pairing_code()
    bad = ch.redeem("000000", "profile20-main")
    assert bad["error"] == "PAIRING_INVALID", bad
    ok = ch.redeem(code, "profile20-main")
    assert ok["ok"] and ok.get("instance_id"), ok
    inst = ok["instance_id"]
    sid, tok = ok["session_id"], ok["token"]
    # 3. Token sai -> tu choi, khong lo token that ra log.
    r = ch.push_events(sid, "sai", 1, [])
    assert r["error"] == "AUTH_DENIED", r
    # 4. Push seq 1 hop le.
    evs = [{"event": "opened", "tabId": 11, "url": "https://x/",
            "title": "X", "status": "loading"}]
    r = ch.push_events(sid, tok, 1, evs)
    assert r["ok"] and r["accepted"] == 1, r
    # 5. Replay seq 1 -> tu choi.
    r = ch.push_events(sid, tok, 1, evs)
    assert r["error"] == "SEQ_REPLAY", r
    # 6. Nhay seq (3 ma last=1) -> doi resync.
    r = ch.push_events(sid, tok, 3, evs)
    assert r["error"] == "RESYNC_REQUIRED", r
    # 7. Action cam -> tu choi cung (fail-closed).
    r = ch.push_events(sid, tok, 2, [{"event": "opened", "tabId": 1,
                                      "action": "click"}])
    assert r["error"] == "ACTION_FORBIDDEN", r
    # 8. Push seq 2 hop le -> registry nhan.
    reg = TabRegistry()
    r = ch.push_events(
        sid, tok, 2, [{"event": "url-changed", "tabId": 11,
                       "url": "https://www.tiktok.com/",
                       "title": "TikTok", "status": "loading"}])
    assert r["ok"], r
    from bridge.importer import import_outbox
    got = import_outbox(reg, r["instance"],
                        [{**e, "tabId": e.get("tabId")} for e in r["events"]])
    assert got == 1 and reg.tabs[(inst, 11)].url.endswith(
        "tiktok.com/"), got
    # 9. Resync: backend biet tab 11 con song, tab 99 -> STALE.
    reg.apply("opened", inst, 99, url="https://cu/")
    r = ch.resync(sid, tok, 3, [{"tabId": 11}])
    assert r["ok"] and r["live_tab_ids"] == [11], r
    live = set(r["live_tab_ids"])
    stale = [k for k in reg.tabs if k[1] not in live]
    assert stale == [(inst, 99)], stale
    # 10. Het han (qua SESSION_TTL 3600s) -> tu choi.
    ch._clock.t += 3700
    r = ch.push_events(sid, tok, 4, evs)
    assert r["error"] == "SESSION_EXPIRED", r
    # 11. Revoke: session moi cung bi xoa.
    code2 = ch.issue_pairing_code()
    ok2 = ch.redeem(code2, "profile20-main")
    assert ok2.get("instance_id"), ok2
    assert ch.revoke(ok2["instance_id"]) >= 1
    r = ch.push_events(ok2["session_id"], ok2["token"], 1, evs)
    assert r["error"] == "SESSION_UNKNOWN", r
    print("channel auth+seq+replay+resync+revoke+expiry: PASS")


if __name__ == "__main__":
    test_full()

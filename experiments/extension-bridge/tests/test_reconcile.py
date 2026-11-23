"""Test authoritative snapshot reconciliation (sua loi 381 ket STALE)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.channel import BridgeChannel  # noqa: E402
from bridge.importer import import_outbox  # noqa: E402
from bridge.registry import TabRegistry  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 5000.0

    def __call__(self):
        return self.t


def test_reconcile_removes_closed_offline():
    reg = TabRegistry()
    b = "profile20-main"
    reg.apply("updated", b, 381, url="https://www.tiktok.com/")
    reg.apply("updated", b, 389, url="https://www.tiktok.com/")
    # Extension reconnect, snapshot day du chi con 389 -> 381 bi xoa.
    r = reg.reconcile_snapshot(b, [{"tabId": 389}], generation=1,
                               complete=True)
    assert r["removed"] == [381], r
    assert (b, 381) not in reg.tabs
    assert (b, 389) in reg.tabs
    print("reconcile xoa tab dong offline: PASS")


def test_reconcile_fail_closed():
    reg = TabRegistry()
    b = "profile20-main"
    reg.apply("updated", b, 381, url="https://www.tiktok.com/")
    # Snapshot chua complete -> khong xoa.
    r = reg.reconcile_snapshot(b, [{"tabId": 389}], generation=1,
                               complete=False)
    assert r["removed"] == [] and (b, 381) in reg.tabs, r
    # Generation cu/replay -> khong xoa.
    r = reg.reconcile_snapshot(b, [{"tabId": 381}], generation=1,
                               complete=True)
    assert r["removed"] == [] and (b, 381) in reg.tabs, r
    r2 = reg.reconcile_snapshot(b, [], generation=1, complete=True)
    assert r2["removed"] == [] and (b, 381) in reg.tabs, r2  # replay gen
    # Snapshot rong NHUNG complete + gen moi -> xoa (dong het that).
    r3 = reg.reconcile_snapshot(b, [], generation=2, complete=True)
    assert r3["removed"] == [381], r3
    print("reconcile fail-closed (incomplete/replay): PASS")


def test_reconcile_out_of_order_and_restart():
    reg = TabRegistry()
    b = "profile20-main"
    reg.apply("updated", b, 381, url="https://www.tiktok.com/")
    # Service worker restart: mat ket noi -> STALE, resync gen moi xoa.
    reg.mark_stale(b)
    assert reg.tabs[(b, 381)].availability == "stale"
    r = reg.reconcile_snapshot(b, [{"tabId": 389}], generation=5,
                               complete=True)
    assert r["removed"] == [381], r
    # Stale event cu toi sau (out-of-order) khong hoi sinh tab da xoa o day;
    # event hop le moi se tao lai qua apply (fail-open co kiem soat o importer).
    print("reconcile restart/out-of-order: PASS")


def test_e2e_closed_offline_then_resync():
    ch = BridgeChannel(clock=Clock())
    reg = TabRegistry()
    code = ch.issue_pairing_code()
    s = ch.redeem(code, "profile20-main")
    sid, tok = s["session_id"], s["token"]
    r = ch.push_events(sid, tok, 1, [{"event": "updated", "tabId": 381,
                                      "url": "https://www.tiktok.com/"}])
    import_outbox(reg, r["instance"], r["events"])
    # 381 dong luc mat ket noi (closed rot) -> resync chi thay 389.
    r = ch.resync(sid, tok, 2, [{"tabId": 389}], generation=2,
                  complete=True)
    assert r["ok"], r
    rec = reg.reconcile_snapshot(r["instance"], [{"tabId": 389}],
                                 r["generation"], r["complete"])
    assert rec["removed"] == [381], rec
    assert ("profile20-main", 381) not in reg.tabs
    print("e2e closed-offline + resync xoa xac: PASS")


if __name__ == "__main__":
    test_reconcile_removes_closed_offline()
    test_reconcile_fail_closed()
    test_reconcile_out_of_order_and_restart()
    test_e2e_closed_offline_then_resync()

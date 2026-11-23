"""Test kenh Extension -> Backend -> TabRegistry (moc 1 + moc 2)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.importer import import_outbox  # noqa: E402
from bridge.registry import TabRegistry  # noqa: E402


def test_import_outbox():
    reg = TabRegistry()
    b = "profile20-main"
    # Mo ta outbox that: extension thay 2 tab TikTok + FB.
    outbox = [
        {"event": "opened", "tabId": 11,
         "url": "https://www.tiktok.com/", "title": "TikTok",
         "status": "complete", "observed_at": 1700000000000},
        {"event": "opened", "tabId": 22,
         "url": "https://www.facebook.com/", "title": "Facebook",
         "status": "complete", "observed_at": 1700000001000},
        {"event": "url-changed", "tabId": 11,
         "url": "https://www.tiktok.com/explore", "title": "Explore",
         "status": "loading", "observed_at": 1700000002000},
        {"event": "closed", "tabId": 22, "observed_at": 1700000003000},
        {"event": "x-bogus", "tabId": 99},
        "not-a-dict",
        {"event": "opened"},
    ]
    n = import_outbox(reg, b, outbox)
    assert n == 4, n
    recs = reg.list()
    assert [r.tab_id for r in recs] == [11], [r.tab_id for r in recs]
    assert recs[0].url.endswith("/explore")
    assert reg.tabs[(b, 11)].availability == "fresh"
    print("import_outbox moc1+moc2: PASS (nhan 4/7 event hop le)")


if __name__ == "__main__":
    test_import_outbox()

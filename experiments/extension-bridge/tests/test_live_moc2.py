"""Moc 2 Live Test 1: event that tu log service worker cua user."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.importer import import_outbox  # noqa: E402
from bridge.registry import TabRegistry  # noqa: E402

OUTBOX = [
    {"event": "opened", "tabId": 1302900374, "url": "",
     "title": "New Tab", "status": "loading"},
    {"event": "url-changed", "tabId": 1302900374,
     "url": "chrome://newtab/", "title": "New Tab",
     "status": "loading"},
    {"event": "updated", "tabId": 1302900374,
     "url": "chrome://newtab/", "title": "New Tab",
     "status": "complete"},
    {"event": "url-changed", "tabId": 1302900374,
     "url": "https://www.tiktok.com/@nghecontent9699",
     "title": "tiktok.com/@nghecontent9699", "status": "loading"},
    {"event": "updated", "tabId": 1302900374,
     "url": "https://www.tiktok.com/@nghecontent9699",
     "title": "tiktok.com/@nghecontent9699", "status": "complete"},
    {"event": "updated", "tabId": 1302900374,
     "url": "https://www.tiktok.com/@nghecontent9699",
     "title": "TikTok - Make Your Day", "status": "complete"},
]


def test_live_moc2():
    reg = TabRegistry()
    b = "profile20-main"
    n = import_outbox(reg, b, OUTBOX)
    assert n == 6, n
    r = reg.tabs[(b, 1302900374)]
    assert r.url == "https://www.tiktok.com/@nghecontent9699", r.url
    assert r.availability == "fresh"
    print("MOC2 live-sim (event that user): PASS")


if __name__ == "__main__":
    test_live_moc2()

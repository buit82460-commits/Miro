"""Slice 02B bridge-level: navigate URL guard (khong network that)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.grants import validate_navigate_url  # noqa: E402


def test_navigate_allow_tiktok_search():
    r = validate_navigate_url("https://www.tiktok.com/search?q=KANS%20377")
    assert r["ok"] is True and r["url"].startswith(
        "https://www.tiktok.com/"), r


def test_navigate_deny_offsite():
    r = validate_navigate_url("https://evil.example/phish")
    assert r["error"] == "NAVIGATE_ORIGIN_DENIED", r


def test_navigate_deny_javascript_scheme():
    r = validate_navigate_url("javascript:alert(1)")
    assert r["error"] == "NAVIGATE_ORIGIN_DENIED", r


def test_navigate_deny_control_chars():
    r = validate_navigate_url(
        "https://www.tiktok.com/search?q=a b")
    assert r["error"] == "NAVIGATE_URL_INVALID", r


if __name__ == "__main__":
    test_navigate_allow_tiktok_search()
    test_navigate_deny_offsite()
    test_navigate_deny_javascript_scheme()
    test_navigate_deny_control_chars()
    print("slice02b navigate guard: PASS")

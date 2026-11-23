"""Test TabRegistry: key (browser, tab), STALE, UNAVAILABLE, khong tab trung."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.registry import TabRegistry  # noqa: E402


def test_lifecycle():
    reg = TabRegistry()
    b = "profile20-main"
    reg.apply("opened", b, 11, url="https://www.tiktok.com/",
              title="TikTok")
    assert len(reg.list()) == 1
    reg.apply("url-changed", b, 11,
              url="https://www.tiktok.com/explore", title="Explore")
    assert reg.tabs[(b, 11)].url.endswith("/explore")
    reg.apply("updated", b, 11, status="complete")
    assert reg.tabs[(b, 11)].status == "complete"
    # Cung tabId nhung browser khac = ban ghi rieng (khong trung).
    reg.apply("opened", "other-instance", 11,
              url="https://www.facebook.com/", title="FB")
    assert len(reg.list()) == 2
    assert len(reg.list(only_fresh=True)) == 2
    # Mat ket noi -> STALE, Miro khong dung du lieu cu o che do fresh-only.
    assert reg.mark_stale(b) == 1
    assert reg.tabs[(b, 11)].availability == "stale"
    assert all(r.tab_id == 11 for r in reg.list(only_fresh=True))
    # Resync khi extension bao cao lai.
    reg.apply("updated", b, 11, status="complete")
    assert reg.tabs[(b, 11)].availability == "fresh"
    # Thu hoi quyen -> UNAVAILABLE.
    assert reg.mark_unavailable(b) == 1
    assert reg.tabs[(b, 11)].availability == "unavailable"
    assert reg.list(only_fresh=True)[0].browser_instance_id == "other-instance"
    # Dong tab -> xoa ban ghi.
    reg.apply("closed", "other-instance", 11)
    assert len(reg.list()) == 1
    print("TabRegistry lifecycle+stale+revoke: PASS")


if __name__ == "__main__":
    test_lifecycle()

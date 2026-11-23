"""Transport read-only cho Gateway (spike, theo contract Phien B).

- discover_tabs(): [{tabId, url, title}] tu TabRegistry (fresh-only mac dinh).
- read_tab(): tra page-handle that de eye collector doc — SPIKE: chua co
  handle that, raise NOT_CONNECTED (khong tra DOM tu parse, khong tu tao
  Evidence). Eye/REA phai doc tren tab that.
- close_transport(): ngat transport, invalidate (danh dau stale), khong tat Chrome.

Cam: tu tao tab/navigate/click/type/evaluate, tu cap quyen, tu tao Evidence.
Tab discovery (URL/title) = du lieu chua tin cay, chi thanh Evidence sau
read_via_eye tren tab that.
"""
from __future__ import annotations


class NotConnected(Exception):
    pass


class BridgeTransport:
    def __init__(self, registry, browser_instance_id):
        self._registry = registry
        self._instance = browser_instance_id
        self._closed = False

    async def discover_tabs(self):
        """[{tabId, url, title}] — read-only, khong DOM, khong WRITE."""
        if self._closed:
            raise NotConnected("TRANSPORT_CLOSED")
        out = []
        for (bid, tid), rec in sorted(self._registry.tabs.items()):
            if bid != self._instance:
                continue
            if rec.availability != "fresh":
                continue
            out.append({"tabId": tid, "url": rec.url, "title": rec.title})
        return out

    async def read_tab(self, tab_id):
        """Tra page-handle that — spike: chua co, tu choi ro rang."""
        raise NotConnected("NO_PAGE_HANDLE_YET (can eye/REA tren tab that)")

    async def close_transport(self):
        """Ngat transport, invalidate lease, khong tat Chrome."""
        self._closed = True
        self._registry.mark_stale(self._instance)

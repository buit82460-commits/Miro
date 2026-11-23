"""Kenh Extension -> Backend -> TabRegistry (spike, read-only).

MOC 1: extension thay tab -> ghi event vao storage.local outbox.
MOC 2 (ham nay): backend keo outbox ve, apply vao TabRegistry.
Khong doc DOM, khong ghi, khong tao tab.
"""
from __future__ import annotations


def import_outbox(registry, browser_instance_id, outbox):
    """Apply tung event outbox vao registry. Tra ve so event da nhan."""
    n = 0
    for ev in outbox or []:
        if not isinstance(ev, dict):
            continue
        event = str(ev.get("event") or "")
        if event not in ("opened", "closed", "url-changed", "updated",
                         "startup"):
            continue
        try:
            tab_id = int(ev.get("tabId"))
        except (TypeError, ValueError):
            continue
        registry.apply(event, browser_instance_id, tab_id,
                       url=str(ev.get("url") or ""),
                       title=str(ev.get("title") or ""),
                       status=str(ev.get("status") or ""))
        n += 1
    return n

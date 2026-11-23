"""Tab Registry cho Extension Bridge (spike, read-only).

Nhan event tu extension (opened/closed/url-changed/updated), giu 1 ban ghi
moi nhat cho moi (browser_instance_id, tab_id) — tabId KHONG la dinh danh
toan cuc. Khong tao tab, khong navigate, khong doc DOM.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TabRecord:
    browser_instance_id: str
    tab_id: int
    url: str = ""
    title: str = ""
    status: str = ""
    last_event: str = ""
    observed_at: float = 0.0
    # fresh: extension con bao cao | stale: mat ket noi/restart chua resync
    # unavailable: thu hoi quyen tabs.
    availability: str = "fresh"


@dataclass
class TabRegistry:
    tabs: dict = field(default_factory=dict)
    _generations: dict = field(default_factory=dict)

    def _key(self, browser_instance_id, tab_id):
        return (browser_instance_id, tab_id)

    def apply(self, event, browser_instance_id, tab_id, url="",
              title="", status=""):
        now = time.time()
        key = self._key(browser_instance_id, tab_id)
        if event == "closed":
            self.tabs.pop(key, None)
            return TabRecord(browser_instance_id=browser_instance_id,
                             tab_id=tab_id, last_event="closed",
                             observed_at=now)
        rec = self.tabs.get(key)
        if rec is None:
            rec = TabRecord(browser_instance_id=browser_instance_id,
                            tab_id=tab_id)
        rec.last_event = event
        rec.observed_at = now
        rec.availability = "fresh"
        if url:
            rec.url = url
        if title:
            rec.title = title
        if status:
            rec.status = status
        self.tabs[key] = rec
        return rec

    def mark_stale(self, browser_instance_id):
        """Mat ket noi/extension restart: danh dau STALE, khong xoa."""
        n = 0
        for (bid, _tid), rec in self.tabs.items():
            if bid == browser_instance_id and rec.availability == "fresh":
                rec.availability = "stale"
                n += 1
        return n

    def reconcile_snapshot(self, browser_instance_id, snapshot,
                           generation, complete):
        """Authoritative snapshot reconciliation (Phan A, sua loi 381 ket STALE).

        Chi xoa khi DU 4 dieu kien: snapshot thuoc dung instance (caller dam
        bao), generation/sequence hop le (tang don dieu, chong replay/cu),
        complete=True (snapshot day du, khong mot phan). Thieu 1 -> khong
        xoa gi, giu nguyen de fail-closed.
        Tra {"removed": [...], "stale_kept": [...]}.
        """
        if not complete:
            kept = [tid for (bid, tid) in self.tabs
                    if bid == browser_instance_id]
            return {"removed": [], "stale_kept": sorted(kept)}
        try:
            generation = int(generation)
        except (TypeError, ValueError):
            kept = [tid for (bid, tid) in self.tabs
                    if bid == browser_instance_id]
            return {"removed": [], "stale_kept": sorted(kept)}
        last = self._generations.get(browser_instance_id, 0)
        if generation <= last:
            kept = [tid for (bid, tid) in self.tabs
                    if bid == browser_instance_id]
            return {"removed": [], "stale_kept": sorted(kept)}
        self._generations[browser_instance_id] = generation
        live = set()
        for t in snapshot or []:
            if isinstance(t, dict):
                try:
                    live.add(int(t.get("tabId")))
                except (TypeError, ValueError):
                    continue
        removed, kept = [], []
        for (bid, tid) in list(self.tabs.keys()):
            if bid != browser_instance_id:
                continue
            if tid not in live:
                del self.tabs[(bid, tid)]
                removed.append(tid)
            else:
                kept.append(tid)
        return {"removed": sorted(removed), "stale_kept": sorted(kept)}

    def mark_unavailable(self, browser_instance_id):
        """Thu hoi quyen tabs: UNAVAILABLE, Miro khong dung du lieu cu."""
        n = 0
        for (bid, _tid), rec in self.tabs.items():
            if bid == browser_instance_id:
                rec.availability = "unavailable"
                n += 1
        return n

    def list(self, only_fresh=False):
        recs = sorted(self.tabs.values(),
                      key=lambda r: (r.browser_instance_id, r.tab_id))
        if only_fresh:
            return [r for r in recs if r.availability == "fresh"]
        return recs

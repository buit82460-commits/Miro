"""Desktop watcher: tab -> object -> event -> reaction -> deadline.

Unified pipeline (dubtool desktop_act cached fast-path + JARVIS
desktop_task observe→act→verify + jev-desktop read-back discipline):

  tab (window+doc identity) -> doi tuong (control refs) -> su kien
  (focus/select/content change) -> phan ung (callback, once per event)
  -> thoi han (deadline_ms; late events dropped, never replayed).

Anti double-fire: every emission carries a stable event_id
(window_id, tab/doc, control, value_digest or state). A per-tab
seen-set makes a new message trigger exactly once: re-emission of the
same content/state is suppressed, and re-verify on focus change updates
identity instead of firing the old event again.

Stale focus: when the selected tab changes (or refs go stale), the
watcher re-verifies window+doc identity before reacting; findings bound
to a dead ref are discarded without emitting.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WatchEvent:
    tab: str
    object: str
    kind: str
    detail: dict = field(default_factory=dict)
    event_id: str = ""
    at: float = field(default_factory=time.time)


def event_id_for(tab: str, obj: str, kind: str, state: str) -> str:
    digest = hashlib.sha256(f"{tab}\0{obj}\0{kind}\0{state}".encode("utf-8")).hexdigest()[:16]
    return f"{tab}::{obj}::{kind}::{digest}"


class Watcher:
    """Owns one watch session: tabs, seen events, deadlines."""

    def __init__(self, deadline_ms: int = 2000):
        self.deadline_ms = deadline_ms
        self.tabs: dict[str, dict] = {}
        self.seen: set[str] = set()
        self.fired: list[WatchEvent] = []
    def watch_tab(self, tab: str, obj: str, initial_state: str = "") -> None:
        self.tabs[tab] = {"object": obj, "state": initial_state,
                          "focused": True, "last_at": None}

    def focus_changed(self, tab: str, focused: bool, reverify_state: str | None = None) -> None:
        """Re-verify identity on focus change: update stored state, fire nothing."""
        entry = self.tabs.get(tab)
        if entry is None:
            return
        entry["focused"] = focused
        if reverify_state is not None:
            entry["state"] = reverify_state
            entry["last_at"] = None

    def observe(self, tab: str, kind: str, state: str,
                react=None, now: float | None = None) -> WatchEvent | None:
        """Observe new state; react at most once per event_id, within deadline."""
        entry = self.tabs.get(tab)
        if entry is None or not entry.get("focused", True):
            return None
        t = time.time() if now is None else now
        obj = entry["object"]
        if state == entry["state"] and kind != "focus":
            return None
        eid = event_id_for(tab, obj, kind, state)
        if eid in self.seen:
            return None
        last_at = entry.get("last_at")
        if last_at is not None and (t - last_at) * 1000.0 > self.deadline_ms:
            entry["last_at"] = t
            entry["state"] = state
            return None
        self.seen.add(eid)
        entry["state"] = state
        entry["last_at"] = t
        event = WatchEvent(tab=tab, object=obj, kind=kind,
                           detail={"state": state}, event_id=eid, at=t)
        self.fired.append(event)
        if react is not None:
            react(event)
        return event

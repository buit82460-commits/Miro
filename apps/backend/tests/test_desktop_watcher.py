"""Proof tests: epoch/stale-epoch, focus re-verify, DOM double-fire guard.

  - worker cu mat quyen (transfer_job bump epoch) bi tu choi (STALE_EPOCH),
    backend op khong bao gio chay.
  - tin moi chi kich hoat 1 lan: observe() cung state 2 lan chi fire 1 event;
    pilot.write_text() trung text khong goi lai backend.
"""
from __future__ import annotations

import pytest

from miro.desktop.dispatch import dispatch
from miro.desktop.gate import gate, init_job, transfer_job
from miro.desktop.watcher import Watcher
from miro.workflows.notepad_pilot import (
    NotepadPilot,
    StaleWindowError,
    run_notepad_pilot,
)


class FakeOps:
    """Fake Notepad ops: find/snapshot/write with a write counter."""

    def __init__(self, window_id="win-1", title="Untitled - Notepad"):
        self.window_id = window_id
        self.title = title
        self.writes = 0

    def find_window(self, title_substr="Notepad"):
        if title_substr.lower() in self.title.lower():
            return {"window_id": self.window_id, "title": self.title}
        return None

    def snapshot(self, window_id):
        if window_id != self.window_id:
            return None
        return {"window_id": self.window_id, "state": self.title}

    def write(self, window_id, ref, text):
        self.writes += 1
        return {"ok": True, "window": window_id, "ref": ref, "value": text}


def test_stale_worker_denied_and_backend_never_runs(tmp_path):
    init_job(tmp_path, "job-1", holder="A")
    calls = []
    ok, out = dispatch(tmp_path, "job-1", "A", 1,
                        lambda: calls.append(1) or {"wrote": True})
    assert ok is True
    transfer_job(tmp_path, "job-1", "B")
    allowed, detail = gate(tmp_path, "job-1", "A", 1)
    assert allowed is False and detail["reason"] == "STALE_EPOCH"
    ok2, out2 = dispatch(tmp_path, "job-1", "A", 1,
                          lambda: calls.append(1) or {"wrote": True})
    assert ok2 is False
    assert out2["denied"]["reason"] == "STALE_EPOCH"
    assert calls == [1]


def test_new_message_fires_exactly_once(tmp_path):
    init_job(tmp_path, "job-2", holder="A")
    ops = FakeOps()
    pilot = NotepadPilot(tmp_path, "job-2", "A", 1, ops=ops)
    pilot.attach("win-1")
    fired = []
    ok, out = pilot.write_text("hello", react=fired.append)
    assert ok is True and out["event"] is not None
    assert len(fired) == 1
    ok2, out2 = pilot.write_text("hello", react=fired.append)
    assert ok2 is True and len(fired) == 1
    assert ops.writes == 1
    ok3, out3 = pilot.write_text("world", react=fired.append)
    assert ok3 is True and len(fired) == 2
    assert ops.writes == 2


def test_reverify_on_lost_focus_discards_stale_window(tmp_path):
    init_job(tmp_path, "job-3", holder="A")
    ops = FakeOps()
    pilot = NotepadPilot(tmp_path, "job-3", "A", 1, ops=ops)
    pilot.attach("win-1")
    assert pilot.focus_changed({"window_id": "win-2", "state": "x"}) is False
    event = pilot.watcher.observe("notepad:win-1", kind="content",
                                  state="late text")
    assert event is None
    assert pilot.focus_changed({"window_id": "win-1", "state": "fresh"}) is True
    event2 = pilot.watcher.observe("notepad:win-1", kind="content",
                                   state="fresh text")
    assert event2 is not None and event2.event_id


def test_watcher_deadline_drops_late_events_never_replayed():
    w = Watcher(deadline_ms=100)
    w.watch_tab("t1", obj="edit", initial_state="")
    e1 = w.observe("t1", kind="content", state="a", now=1000.0)
    assert e1 is not None
    assert w.observe("t1", kind="content", state="a", now=1000.05) is None
    assert w.observe("t1", kind="content", state="b", now=2000.0) is None
    assert w.observe("t1", kind="content", state="b", now=2000.05) is None
    assert len(w.fired) == 1


def test_run_notepad_pilot_end_to_end(tmp_path):
    init_job(tmp_path, "job-4", holder="A")
    ops = FakeOps()
    fired = []
    ok, out = run_notepad_pilot(tmp_path, "job-4", "A", 1, "pilot text",
                                ops=ops, react=fired.append)
    assert ok is True and len(fired) == 1 and ops.writes == 1


def test_run_notepad_pilot_stale_worker_denied(tmp_path):
    init_job(tmp_path, "job-5", holder="A")
    transfer_job(tmp_path, "job-5", "B")
    ops = FakeOps()
    ok, out = run_notepad_pilot(tmp_path, "job-5", "A", 1, "late",
                                ops=ops)
    assert ok is False
    assert out["denied"]["reason"] == "STALE_EPOCH"
    assert ops.writes == 0


def test_run_notepad_pilot_missing_window(tmp_path):
    init_job(tmp_path, "job-6", holder="A")
    ops = FakeOps(title="Something else")
    with pytest.raises(StaleWindowError):
        run_notepad_pilot(tmp_path, "job-6", "A", 1, "x", ops=ops,
                          title="NoSuchAppXYZ")

"""Notepad pilot workflow: epoch-gated writes + focus re-verify + once-only reactions.

Pipeline: tab (window identity) -> doi tuong (edit control ref) ->
su kien (content change) -> phan ung (react callback, once per event) ->
thoi han (watcher deadline_ms; late events dropped, never replayed).

Rules enforced here (not in backend):
  1. Epoch first: write_text() calls gate() BEFORE any dedup shortcut, so a
     stale worker is always denied even when the text is unchanged.
  2. Re-verify on focus change: focus_changed() takes a fresh snapshot and
     compares window identity; findings bound to a dead/gone window are
     discarded without emitting.
  3. Anti double-fire: identical content is suppressed at the pilot level
     (no redundant backend write) and at the watcher level (seen event_ids).

Stdlib only. Real Notepad access goes through CliOps (agent-desktop CLI);
tests inject a fake ops object with the same 3 methods.
"""
from __future__ import annotations

from miro.desktop import gate as gate_mod
from miro.desktop.dispatch import dispatch_window
from miro.desktop.watcher import Watcher


class StaleWindowError(Exception):
    """Raised when the target window is gone or identity changed."""

    def __init__(self, window_id, detail="STALE_WINDOW"):
        super().__init__(f"{detail}: {window_id}")
        self.window_id = window_id


class CliOps:
    """Real ops over the agent-desktop CLI (Notepad on Windows, headless)."""

    APP = "notepad"

    def find_window(self, title_substr="Notepad"):
        from miro.desktop import backend as backend_mod

        payload = backend_mod.run_cli(["list-windows", "--app", self.APP])
        items = []
        if isinstance(payload, dict):
            data = payload.get("data", payload)
            if isinstance(data, dict):
                for key in ("windows", "items", "result"):
                    if isinstance(data.get(key), list):
                        items = data[key]
                        break
            elif isinstance(data, list):
                items = data
        needle = title_substr.lower()
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", ""))
            if needle in title.lower():
                wid = item.get("window_id", item.get("id", title))
                return {"window_id": str(wid), "title": title}
        return None

    def snapshot(self, window_id):
        from miro.desktop import backend as backend_mod

        payload = backend_mod.run_cli(
            ["snapshot", "--window-id", str(window_id)])
        if isinstance(payload, dict) and payload.get("ok") is True:
            return {"window_id": str(window_id), "snapshot": payload.get("data")}
        return None

    def write(self, window_id, ref, text):
        from miro.desktop import backend as backend_mod

        set_res = backend_mod.run_cli(["set-value", str(ref), str(text)])
        verify = backend_mod.run_cli(
            ["get", str(ref), "--property", "value"])
        value = None
        if isinstance(verify, dict):
            data = verify.get("data", verify)
            value = data.get("value") if isinstance(data, dict) else None
        return {"ok": True, "set": set_res, "verified_value": value}


class NotepadPilot:
    """One pilot session: one job, one worker epoch, one Notepad window."""

    def __init__(self, base_dir, job_id, worker, worker_epoch, ops=None,
                 deadline_ms=2000, window_lock_dir=None):
        self.base_dir = base_dir
        self.job_id = job_id
        self.worker = worker
        self.worker_epoch = worker_epoch
        self.ops = ops if ops is not None else CliOps()
        self.watcher = Watcher(deadline_ms=deadline_ms)
        self.window_lock_dir = window_lock_dir
        self.window_id = None
        self.tab = None

    def attach(self, window_id, initial_state=""):
        """Bind the watcher tab to a window id. Fires nothing."""
        self.window_id = window_id
        self.tab = f"notepad:{window_id}"
        self.watcher.watch_tab(self.tab, obj="edit",
                               initial_state=initial_state)
        return self.tab

    def attach_window(self, title_substr="Notepad"):
        """Find a Notepad window and attach. Raises StaleWindowError if none."""
        found = self.ops.find_window(title_substr)
        if not found:
            raise StaleWindowError(title_substr, detail="WINDOW_NOT_FOUND")
        return self.attach(found["window_id"])

    def focus_changed(self, snapshot):
        """Re-verify window identity on focus change. Fires nothing.

        snapshot: fresh read (dict with window_id/state) or None when the
        window is gone. Returns True if still the same window, False when
        stale (finding discarded, watcher unfocused).
        """
        if self.tab is None:
            return False
        if not isinstance(snapshot, dict) or \
                snapshot.get("window_id") != self.window_id:
            self.watcher.focus_changed(self.tab, False)
            return False
        self.watcher.focus_changed(self.tab, True,
                                   reverify_state=snapshot.get("state", ""))
        return True

    def write_text(self, text, ref="edit", react=None):
        """Write text through the epoch gate, react at most once.

        Order: gate() -> dedup -> dispatch_window() -> watcher.observe().
        Returns (ok, result). ok=False with denied/STALE_EPOCH detail means
        this worker lost ownership; the backend op never ran.
        """
        if self.window_id is None:
            raise ValueError("NOT_ATTACHED")
        allowed, detail = gate_mod.gate(
            self.base_dir, self.job_id, self.worker, self.worker_epoch)
        if not allowed:
            return False, {"denied": detail}
        entry = self.watcher.tabs.get(self.tab, {})
        if entry.get("state") == text:
            return True, {"deduped": True, "event": None}

        def _op():
            return self.ops.write(self.window_id, ref, text)

        ok, out = dispatch_window(
            self.base_dir, self.window_id, self.job_id,
            self.worker, self.worker_epoch, _op,
            window_lock_dir=self.window_lock_dir)
        if not ok:
            return False, out
        event = self.watcher.observe(self.tab, kind="content",
                                     state=text, react=react)
        return True, {"dispatch": out, "event": event,
                      "duplicate": event is None}


def run_notepad_pilot(base_dir, job_id, worker, worker_epoch, text, ops=None,
                      title="Notepad", ref="edit", react=None,
                      deadline_ms=2000, window_lock_dir=None):
    """Full pipeline: attach -> re-verify focus -> gated write -> once-only react."""
    pilot = NotepadPilot(base_dir, job_id, worker, worker_epoch, ops=ops,
                         deadline_ms=deadline_ms,
                         window_lock_dir=window_lock_dir)
    pilot.attach_window(title)
    snapshot = None
    if hasattr(pilot.ops, "snapshot"):
        snapshot = pilot.ops.snapshot(pilot.window_id)
        if snapshot is not None and "state" not in snapshot:
            snapshot = {"window_id": pilot.window_id,
                        "state": snapshot.get("title", "")}
    if snapshot is not None and not pilot.focus_changed(snapshot):
        raise StaleWindowError(pilot.window_id)
    return pilot.write_text(text, ref=ref, react=react)

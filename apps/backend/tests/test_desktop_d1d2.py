"""D1/D2/L1 + T5 RECOVER-auto (reread-foundation bug C can sua).

Chay: python -m pytest tests/test_desktop_d1d2.py tests/test_tasks_t5.py -q (tu C:\\Miro\\apps\\backend).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


# ---------- D1: window-lock default ve state-dir chung ----------

import importlib as _importlib

_gate_mod = _importlib.import_module("miro.desktop.gate")
_disp_mod = _importlib.import_module("miro.desktop.dispatch")


def test_d1_window_lock_mac_dinh_chung_state_dir(tmp_path, monkeypatch):
    disp = _disp_mod
    gatemod = _gate_mod
    shared = tmp_path / "shared-state"
    monkeypatch.setattr(gatemod, "STATE_DIR", shared, raising=False)
    import miro.desktop.backend as be
    monkeypatch.setattr(be, "STATE_DIR", shared, raising=False)
    monkeypatch.setattr(disp, "ensure_state_dir", lambda path=None: shared, raising=False)
    base_a = tmp_path / "job-a"
    base_b = tmp_path / "job-b"
    for base in (base_a, base_b):
        base.mkdir()
    gatemod.init_job(base_a, "job-a", holder="w1")
    gatemod.init_job(base_b, "job-b", holder="w1")
    ea = gatemod.current_epoch(base_a, "job-a")
    eb = gatemod.current_epoch(base_b, "job-b")
    import threading
    import time as _time
    spans = {}

    def op(tag):
        def _op():
            spans[tag] = {"in": _time.monotonic()}
            _time.sleep(1.0)  # giu lock 1s: neu lock chung, op kia phai doi
            spans[tag]["out"] = _time.monotonic()
            return {"ok": True}
        return _op

    ta = threading.Thread(target=lambda: disp.dispatch_window(
        base_a, "win-1", "job-a", "w1", ea, op("a")))
    ta.start()
    _time.sleep(0.2)  # dam bao a vao lock truoc
    tb = threading.Thread(target=lambda: disp.dispatch_window(
        base_b, "win-1", "job-b", "w1", eb, op("b")))
    tb.start()
    ta.join(timeout=20)
    tb.join(timeout=20)
    assert not ta.is_alive() and not tb.is_alive()
    # Serialize tren lock chung: b vao sau khi a ra (khong xen nhau).
    assert spans["b"]["in"] >= spans["a"]["out"] - 0.05


def test_d1_caller_van_truyen_rieng_duoc(tmp_path):
    disp = _disp_mod
    g = _gate_mod
    base = tmp_path / "job"
    base.mkdir()
    g.init_job(base, "job", holder="w1")
    ep = g.current_epoch(base, "job")
    custom = tmp_path / "custom-locks"
    ok, out = disp.dispatch_window(base, "win-9", "job", "w1", ep,
                                   lambda: {"ok": True},
                                   window_lock_dir=str(custom))
    assert ok is True
    assert (custom / "window-win-9.lock").exists()


# ---------- D2: ensure_selected_by_ref truoc write ----------

class SelectOps:
    """Fake ops: tab ban dau chua selected, click xong moi selected."""

    def __init__(self, windows, tabs, values, states=None):
        self.windows = windows
        self.tabs = tabs
        self.values = dict(values)
        self.states = dict(states or {})
        self.calls = []

    def list_windows(self, app=None):
        self.calls.append("list-windows")
        return {"ok": True, "windows": self.windows}

    def find(self, window_id, role=None, name=None, **_):
        self.calls.append(f"find:{role}:{name}")
        if role == "tab":
            return {"ok": True,
                    "matches": [{**m, "states": self.states.get(m["ref_id"], [])}
                                for m in self.tabs.get(window_id, [])]}
        if role == "textfield":
            return {"ok": True, "matches": [{"ref_id": "field-1"}]}
        return {"ok": True, "matches": []}

    def get_states(self, ref):
        self.calls.append(f"get-states:{ref}")
        return {"ok": True, "states": self.states.get(ref, [])}

    def click(self, ref, headed=False):
        self.calls.append(f"click:{ref}:{'headed' if headed else 'sem'}")
        self.states[ref] = ["selected"]
        return {"ok": True}

    def get_value(self, ref):
        self.calls.append(f"get:{ref}")
        return {"ok": True, "value": self.values.get(ref, "")}

    def write(self, ref, text):
        self.calls.append(f"write:{ref}")
        self.values[ref] = text
        return {"ok": True}


def _fresh_gate(tmp_path, job="job-d", worker="w1"):
    base = tmp_path / "gate"
    base.mkdir()
    _gate_mod.init_job(base, job, holder=worker)
    return base, _gate_mod.current_epoch(base, job)


def test_d2_write_click_reselect_khi_tab_chua_selected(tmp_path):
    from miro.desktop import act as actmod
    base, epoch = _fresh_gate(tmp_path)
    ops = SelectOps([{"window_id": "w1", "title": "Notepad - d.txt"}],
                    {"w1": [{"ref_id": "t1", "name": "d.txt"}]},
                    {"field-1": ""}, states={"t1": []})
    ok, out = actmod.act(base, "job-d", "w1", epoch, ops,
                         app="notepad", window="Notepad", doc="d.txt",
                         action="write", text="hi")
    assert ok is True, out
    assert any(c.startswith("click:t1") for c in ops.calls)
    assert any(c.startswith("write:") for c in ops.calls)


def test_d2_tab_khong_select_duoc_thi_stop_truoc_write(tmp_path):
    from miro.desktop import act as actmod

    class DeadClick(SelectOps):
        def click(self, ref, headed=False):
            self.calls.append(f"click:{ref}")
            return {"ok": False, "error": "CLICK_FAILED"}  # mai khong selected

        def get_states(self, ref):
            self.calls.append(f"get-states:{ref}")
            return {"ok": True, "states": []}

    base, epoch = _fresh_gate(tmp_path)
    ops = DeadClick([{"window_id": "w1", "title": "Notepad - d.txt"}],
                    {"w1": [{"ref_id": "t1", "name": "d.txt"}]},
                    {"field-1": ""})
    ok, out = actmod.act(base, "job-d", "w1", epoch, ops,
                         app="notepad", window="Notepad", doc="d.txt",
                         action="write", text="hi")
    assert ok is True  # dispatch van chay op, nhung op bao select-tab fail
    assert out["result"]["ok"] is False and out["result"]["stage"] == "select-tab"
    assert out["result"]["detail"] == {"stale": False,
                                       "detail": {"ok": False, "error": "CLICK_FAILED"}}
    assert not any(c.startswith("write:") for c in ops.calls)


def test_d2_already_selected_khong_click_thua(tmp_path):
    from miro.desktop import act as actmod
    base, epoch = _fresh_gate(tmp_path)
    ops = SelectOps([{"window_id": "w1", "title": "Notepad - d.txt"}],
                    {"w1": [{"ref_id": "t1", "name": "d.txt"}]},
                    {"field-1": ""}, states={"t1": ["selected"]})
    ok, out = actmod.act(base, "job-d", "w1", epoch, ops,
                         app="notepad", window="Notepad", doc="d.txt",
                         action="write", text="hi")
    assert ok is True, out
    assert not any(c.startswith("click:") for c in ops.calls)

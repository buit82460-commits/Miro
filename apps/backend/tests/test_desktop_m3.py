"""Desktop M3: act qua dispatch boundary that trong C (fake ops, logic that).

- Epoch cu -> STALE_EPOCH_DENIED, khong cham backend.
- Doc ambiguity (!=1 match) -> DOC_NOT_UNIQUE_STOP truoc write.
- Write -> read-back verify newline; receipt dung cua so.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.desktop import act as actmod
from miro.desktop.gate import current_epoch, gate, init_job


class FakeOps:
    def __init__(self, windows, tabs, values):
        self.windows = windows
        self.tabs = tabs  # window_id -> list[{ref_id, name}]
        self.values = dict(values)
        self.calls = []

    def list_windows(self, app=None):
        self.calls.append("list-windows")
        return {"ok": True, "windows": self.windows}

    def find(self, window_id, role=None, name=None, **_):
        self.calls.append(f"find:{role}:{name}")
        if role == "tab":
            return {"ok": True, "matches": self.tabs.get(window_id, [])}
        if role == "textfield":
            return {"ok": True, "matches": [{"ref_id": "field-1"}]}
        return {"ok": True, "matches": []}

    def get_value(self, ref):
        self.calls.append(f"get:{ref}")
        return {"ok": True, "value": self.values.get(ref, "")}

    def get_states(self, ref):
        self.calls.append(f"get-states:{ref}")
        return {"ok": True, "states": ["selected"]}

    def click(self, ref, headed=False):
        self.calls.append(f"click:{ref}")
        return {"ok": True}

    def write(self, ref, text):
        self.calls.append(f"write:{ref}")
        return {"ok": True}


def _fresh_gate(tmp_path, job="job-m3", worker="w1"):
    base = tmp_path / "gate"
    base.mkdir()
    init_job(base, job, holder=worker)
    epoch = current_epoch(base, job)
    return base, epoch


def test_stale_epoch_denied_without_touching_backend(tmp_path):
    base, _ = _fresh_gate(tmp_path)
    ops = FakeOps([{"window_id": "w1", "title": "Notepad - docB.txt"}],
                  {"w1": [{"ref_id": "t1", "name": "docB.txt"}]}, {})
    ok, out = actmod.act(base, "job-m3", "w1", 0, ops,
                         app="notepad", window="Notepad", doc="docB.txt",
                         action="read")
    assert ok is False and out.get("error") == "STALE_EPOCH_DENIED"
    assert ops.calls == []  # khong cham backend


def test_doc_ambiguity_stops_before_write(tmp_path):
    base, epoch = _fresh_gate(tmp_path)
    ops = FakeOps([{"window_id": "w1", "title": "Notepad"}],
                  {"w1": [{"ref_id": "t1", "name": "doc.txt"},
                           {"ref_id": "t2", "name": "doc.txt"}]}, {})
    ok, out = actmod.act(base, "job-m3", "w1", epoch, ops,
                         app="notepad", window="Notepad", doc="doc.txt",
                         action="write", text="hello")
    assert ok is False and out.get("error") == "DOC_NOT_UNIQUE_STOP"
    assert not any(c.startswith("write:") for c in ops.calls)


def test_write_readback_verify_and_receipt_window(tmp_path):
    base, epoch = _fresh_gate(tmp_path)
    ops = FakeOps([{"window_id": "w1", "title": "Notepad - docB.txt"}],
                  {"w1": [{"ref_id": "t1", "name": "docB.txt"}]},
                  {"field-1": "Hello"})
    # append "!" vao "Hello" -> read-back "Hello!" verify pass
    ops.values["field-1"] = "Hello!"

    class VerifyOps(FakeOps):
        def write(self, ref, text):
            self.calls.append(f"write:{ref}")
            self.values[ref] = (self.values.get(ref, "") + text
                                if text == "!" else text)
            return {"ok": True}

    vops = VerifyOps(ops.windows, ops.tabs, {"field-1": "Hello"})
    ok, out = actmod.act(base, "job-m3", "w1", epoch, vops,
                         app="notepad", window="Notepad", doc="docB.txt",
                         action="append", text="!")
    assert ok is True, out
    assert out["result"]["ok"] is True
    receipts = list(Path(base).glob("receipt-*.json"))
    assert len(receipts) == 1

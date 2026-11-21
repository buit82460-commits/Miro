"""Desktop act boundary: resolve window + doc, then mutate only via dispatch.

Port of C:/dubtool/scripts/desktop_act.py core rules (M3 §9.1/§9.5):

- resolve window (title substring, first match) then resolve doc (tab role
  match by doc name) — doc MUST be exactly 1, else STOP (DOC_NOT_UNIQUE_STOP)
  BEFORE any write.
- every mutation goes through dispatch_window under base->window lock order,
  with a fresh epoch re-read inside the lock (2 checks when hold_before_op).
- receipt `receipt-<run>` immutable per window; `cache_stale` writes no receipt.
- verify by read-back with newline normalisation (\\r\\n vs \\n).

Stdlib only. Real backend calls go through miro.desktop.backend (agent-desktop
CLI); tests inject a fake ops object with the same methods.
"""
from __future__ import annotations

import time
from pathlib import Path


class DocAmbiguousError(Exception):
    """Raised when doc resolution is not exactly 1 — STOP before write."""

    def __init__(self, doc, count, detail="DOC_NOT_UNIQUE_STOP"):
        super().__init__(f"{detail}: doc={doc!r} matches={count}")
        self.doc = doc
        self.count = count


class WindowNotFoundError(Exception):
    def __init__(self, title, detail="WINDOW_NOT_FOUND"):
        super().__init__(f"{detail}: {title!r}")
        self.title = title


def _norm(text):
    if isinstance(text, str):
        return text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def resolve_window(ops, app=None, title_substr=None):
    """Return (window_id, candidates, error). First title-substring match."""
    res = ops.list_windows(app=app)
    if not isinstance(res, dict) or not res.get("ok"):
        return None, [], {"error": "LIST_WINDOWS_FAILED", "detail": res}
    items = res.get("windows") or []
    if not isinstance(items, list):
        items = []
    if title_substr:
        needle = str(title_substr).lower()
        items = [w for w in items
                 if needle in str(w.get("title", "")).lower()]
    if not items:
        return None, [], {"error": "WINDOW_NOT_FOUND"}
    first = items[0]
    wid = first.get("window_id", first.get("id"))
    return wid, items, None


def resolve_doc(ops, window_id, doc):
    """Return (match, error). STOP unless exactly 1 tab matches doc."""
    res = ops.find(window_id, role="tab", name=doc)
    if not isinstance(res, dict) or not res.get("ok"):
        return None, {"error": "FIND_DOC_FAILED", "detail": res}
    matches = res.get("matches") or []
    if len(matches) != 1:
        return None, {"error": "DOC_NOT_UNIQUE_STOP", "count": len(matches)}
    return matches[0], None


def build_write_result(mode, text, before_value, readback, after_ok):
    if mode == "write":
        if not after_ok or _norm(readback) != _norm(text):
            return {"ok": False, "stage": "verify", "reconciled": True,
                    "replayed": False, "content_met": False,
                    "sent": text, "readback": readback}
    else:
        if not after_ok or _norm(readback) != _norm((before_value or "") + text):
            return {"ok": False, "stage": "verify", "reconciled": True,
                    "replayed": False, "content_met": False,
                    "expected": (before_value or "") + text,
                    "readback": readback}
    return {"ok": True, "before": before_value, "after": readback}


def act(base_dir, job_id, worker, worker_epoch, ops, *, app=None,
        window=None, doc=None, action="read", text=None,
        control="textfield", window_lock_dir=None):
    """One desktop act through the dispatch boundary.

    Returns (ok, payload). Denied/stale/ambiguous never run the backend op.
    Receipt lands in base_dir as receipt-<run>.json (window included).
    """
    from miro.desktop.dispatch import dispatch_window
    from miro.desktop.gate import gate as _gate

    base = Path(base_dir)
    t_start = time.time()
    if doc is None:
        return False, {"error": "DOC_REQUIRED"}
    allowed, detail = _gate(base, job_id, worker, worker_epoch)
    if not allowed:
        return False, {"denied": detail, "error": "STALE_EPOCH_DENIED"}

    wid, _, werr = resolve_window(ops, app=app, title_substr=window)
    if werr:
        return False, werr
    match, derr = resolve_doc(ops, wid, doc)
    if derr:
        return False, derr
    tab_ref = match["ref_id"]

    if action == "read":
        def _read():
            fields = ops.find(wid, role=control)
            if not isinstance(fields, dict) or not fields.get("ok") \
                    or not fields.get("matches"):
                return {"ok": False, "stage": "find-control",
                        "detail": fields}
            val = ops.get_value(fields["matches"][0]["ref_id"])
            if not isinstance(val, dict) or not val.get("ok"):
                return {"ok": False, "stage": "read", "detail": val}
            return {"ok": True, "value": val.get("value")}
        ok, out = dispatch_window(base, wid, job_id, worker, worker_epoch,
                                  _read, window_lock_dir=window_lock_dir)
        if ok:
            out["result"]["via"] = "act-read"
            out["result"]["total_s"] = round(time.time() - t_start, 3)
        return ok, out

    if action not in ("write", "append"):
        return False, {"error": "UNKNOWN_ACTION", "action": action}
    if text is None:
        return False, {"error": "TEXT_REQUIRED"}

    def _write():
        fields = ops.find(wid, role=control)
        if not isinstance(fields, dict) or not fields.get("ok") \
                or not fields.get("matches"):
            return {"ok": False, "stage": "find-control", "detail": fields}
        fr = fields["matches"][0]["ref_id"]
        before_value = None
        if action == "append":
            pre = ops.get_value(fr)
            if not isinstance(pre, dict) or not pre.get("ok"):
                return {"ok": False, "stage": "read-before", "detail": pre}
            before_value = pre.get("value") or ""
        wrote = ops.write(fr, text)
        if not isinstance(wrote, dict) or not wrote.get("ok", True):
            if isinstance(wrote, dict) and not wrote.get("ok", True) \
                    and wrote.get("ok") is False:
                return {"ok": False, "stage": "set-value", "detail": wrote}
        after = ops.get_value(fr) if hasattr(ops, "get_value") else wrote
        if isinstance(after, dict) and after.get("ok"):
            readback, after_ok = after.get("value"), True
        elif isinstance(wrote, dict) and "verified_value" in wrote:
            readback, after_ok = wrote.get("verified_value"), True
        else:
            readback, after_ok = None, False
        return build_write_result(action, text, before_value,
                                  readback, after_ok)

    ok, out = dispatch_window(base, wid, job_id, worker, worker_epoch,
                              _write, window_lock_dir=window_lock_dir)
    if ok:
        out["result"]["via"] = "act-write"
        out["result"]["total_s"] = round(time.time() - t_start, 3)
    return ok, out

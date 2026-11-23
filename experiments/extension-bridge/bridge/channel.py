"""Kenh xac thuc Extension -> Backend (spike, read-only).

Thiet ke:
- Pairing 1 lan: backend sinh pairing code (6 so), user nhap vao extension
  popup. Extension doi code lay session token (server giu, khong log token).
- Moi request: header X-Session + seq tang don dieu (chong replay/trung/
  sai thu tu). Sai seq -> server tra RESYNC_REQUIRED.
- Reconnect: extension gui full tab list qua /resync; tab backend co ma
  extension khong gui -> STALE.
- Fail-closed: khong session hop le -> tu choi. Het han (120s) -> tu choi.
- Chi event read-only (opened/closed/url-changed/updated). Bat cu action
  nao khac (click/type/evaluate/...) -> tu choi.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

SESSION_TTL_S = 120
PAIRING_TTL_S = 120
MAX_PAIRING_OUTSTANDING = 5
MAX_REDEEM_FAILS_WINDOW_S = 60
MAX_REDEEM_FAILS = 5
ALLOWED_EVENTS = {"opened", "closed", "url-changed", "updated", "startup"}
FORBIDDEN_ACTIONS = {"click", "type", "evaluate", "fill", "exec", "run",
                     "debugger", "attach", "dom", "readDOM"}


def _redact(value):
    if not value:
        return "<empty>"
    s = str(value)
    return s[:2] + "***" if len(s) > 4 else "***"


class BridgeChannel:
    """Server logic thuan (khong socket) de de test. HTTP wrapper o ngoai."""

    def __init__(self, clock=None):
        self._clock = clock or time.time
        self._pairing = {}   # code -> expires_at
        self._sessions = {}  # session_id -> {instance, expires_at, last_seq}
        self._pair_secret = secrets.token_hex(16)
        self._redeem_fails = []  # [ts...] cua lan redeem sai gan day

    # -- pairing ---------------------------------------------------------
    def issue_pairing_code(self):
        # Gioi han so code song song de chong spam pairing.
        now = self._clock()
        live = {c: e for c, e in self._pairing.items() if e > now}
        self._pairing = live
        if len(live) >= MAX_PAIRING_OUTSTANDING:
            return ""
        code = "%06d" % secrets.randbelow(1000000)
        self._pairing[code] = now + PAIRING_TTL_S
        return code

    def _redeem_locked(self):
        cutoff = self._clock() - MAX_REDEEM_FAILS_WINDOW_S
        self._redeem_fails = [t for t in self._redeem_fails if t > cutoff]
        return len(self._redeem_fails) >= MAX_REDEEM_FAILS

    def redeem(self, code, browser_instance_id):
        """Doi pairing code lay session token. Tra token 1 lan duy nhat."""
        now = self._clock()
        if self._redeem_locked():
            return {"ok": False, "error": "PAIRING_LOCKED"}
        exp = self._pairing.pop(str(code), None)
        if exp is None or exp <= now:
            self._redeem_fails.append(now)
            return {"ok": False, "error": "PAIRING_INVALID"}
        if not browser_instance_id:
            return {"ok": False, "error": "INSTANCE_REQUIRED"}
        session_id = secrets.token_hex(16)
        token = secrets.token_hex(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        self._sessions[session_id] = {
            "instance": str(browser_instance_id),
            "expires_at": now + SESSION_TTL_S,
            "last_seq": 0,
            "token_digest": digest,
        }
        return {"ok": True, "session_id": session_id, "token": token,
                "expires_in": SESSION_TTL_S}

    # -- auth ------------------------------------------------------------
    def _auth(self, session_id, token):
        s = self._sessions.get(str(session_id or ""))
        if s is None:
            return None, "SESSION_UNKNOWN"
        if s["expires_at"] <= self._clock():
            self._sessions.pop(session_id, None)
            return None, "SESSION_EXPIRED"
        expect = s["token_digest"]
        got = hashlib.sha256(str(token or "").encode()).hexdigest()
        if not hmac.compare_digest(expect, got):
            return None, "AUTH_DENIED"
        return s, ""

    # -- events ----------------------------------------------------------
    def push_events(self, session_id, token, seq, events):
        s, err = self._auth(session_id, token)
        if s is None:
            return {"ok": False, "error": err}
        try:
            seq = int(seq)
        except (TypeError, ValueError):
            return {"ok": False, "error": "SEQ_INVALID"}
        if seq <= s["last_seq"]:
            return {"ok": False, "error": "SEQ_REPLAY",
                    "last_seq": s["last_seq"]}
        if seq != s["last_seq"] + 1:
            return {"ok": False, "error": "RESYNC_REQUIRED",
                    "last_seq": s["last_seq"]}
        accepted, rejected = [], []
        for ev in events or []:
            if not isinstance(ev, dict):
                rejected.append("bad-shape")
                continue
            if str(ev.get("action") or "") in FORBIDDEN_ACTIONS:
                return {"ok": False, "error": "ACTION_FORBIDDEN"}
            if str(ev.get("event") or "") not in ALLOWED_EVENTS:
                rejected.append("bad-event")
                continue
            accepted.append(ev)
        s["last_seq"] = seq
        return {"ok": True, "accepted": len(accepted),
                "rejected": rejected, "instance": s["instance"],
                "events": accepted}

    def resync(self, session_id, token, seq, full_tabs,
               generation=None, complete=False):
        """Nhan full tab list, tra ve tap tabId con hieu luc de caller STALE."""
        s, err = self._auth(session_id, token)
        if s is None:
            return {"ok": False, "error": err}
        try:
            seq = int(seq)
        except (TypeError, ValueError):
            return {"ok": False, "error": "SEQ_INVALID"}
        if seq <= s["last_seq"]:
            return {"ok": False, "error": "SEQ_REPLAY",
                    "last_seq": s["last_seq"]}
        live = set()
        for t in full_tabs or []:
            if isinstance(t, dict):
                try:
                    live.add(int(t.get("tabId")))
                except (TypeError, ValueError):
                    continue
        s["last_seq"] = seq
        if generation is None:
            generation = seq
        try:
            generation = int(generation)
        except (TypeError, ValueError):
            generation = seq
        return {"ok": True, "instance": s["instance"], "live_tab_ids": sorted(live),
                "count": len(live), "generation": generation,
                "complete": bool(complete)}

    def revoke(self, browser_instance_id):
        """Thu hoi: xoa session cua instance -> moi request sau bi tu choi."""
        gone = [k for k, v in self._sessions.items()
                if v["instance"] == browser_instance_id]
        for k in gone:
            del self._sessions[k]
        return len(gone)

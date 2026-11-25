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

SESSION_TTL_S = 3600
PAIRING_TTL_S = 600
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
        # Slice 01B: trusted connection + persistent authorization.
        self._devices = {}   # device_id -> {instance, created_at, revoked}
        self._policies = {}  # instance -> {read_allowed, origins, ...}

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

    def redeem(self, code, browser_instance_id=None, profile_name=""):
        """Doi pairing code lay session token. Tra token 1 lan duy nhat.
        Slice multi-profile: moi redeem cap instance_id RIENG (inst-xxxx),
        khong tin instance do client khai bao. profile_name chi la nhan
        hien thi, khong dung cho auth."""
        now = self._clock()
        if self._redeem_locked():
            return {"ok": False, "error": "PAIRING_LOCKED"}
        exp = self._pairing.pop(str(code), None)
        if exp is None or exp <= now:
            self._redeem_fails.append(now)
            return {"ok": False, "error": "PAIRING_INVALID"}
        # Server cap instance rieng cho moi lan pair thanh cong.
        instance_id = "inst-" + secrets.token_hex(4)
        session_id = secrets.token_hex(16)
        token = secrets.token_hex(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        # Slice 01B: device link ben vung (one-click reconnect). device_id
        # on dinh theo trinh duyet (extension sinh + luu local); session van
        # ngan han, nhung device duoc tin de cap lai session khong can code.
        # Slate: ten hien thi do user dat khi pair (khong dung cho auth).
        # Mac dinh lay profile_name neu co; user doi sau qua /rename.
        name = str(profile_name or "")[:40]
        device_id = "dev-" + secrets.token_hex(8)
        self._devices[device_id] = {
            "instance": instance_id,
            "profile_name": name,
            "created_at": now,
            "revoked": False,
        }
        self._sessions[session_id] = {
            "instance": instance_id,
            "expires_at": now + SESSION_TTL_S,
            "last_seq": 0,
            "token_digest": digest,
            "device_id": device_id,
        }
        # Slice 01B: policy mac dinh sau pair thanh cong: read-only TikTok,
        # cho phep auto-grant. User thu hoi qua /policy (revoke).
        self._policies[instance_id] = {
            "read_allowed": True,
            "revoked": False,
            "origins": ["https://www.tiktok.com"],
            "granted_at": now,
            "revoked_at": None,
            "regranted_at": None,
            "device_id": device_id,
            "profile_name": name,
        }
        return {"ok": True, "session_id": session_id, "token": token,
                "expires_in": SESSION_TTL_S, "device_id": device_id,
                "instance_id": instance_id}

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

    # -- Slice 01B: trusted reconnect + policy ---------------------------
    def reconnect(self, device_id, browser_instance_id=None):
        """Cap lai session cho device da link, khong can pairing code.
        Instance lay tu device da luu — khong tin client khai bao.
        Device bi revoke/forget -> tu choi, phai pair lai tu dau."""
        now = self._clock()
        d = self._devices.get(str(device_id or ""))
        if d is None or d.get("revoked"):
            return {"ok": False, "error": "DEVICE_UNKNOWN"}
        inst = str(d.get("instance") or "")
        pol = self._policies.get(inst)
        if not isinstance(pol, dict) or not pol.get("read_allowed"):
            return {"ok": False, "error": "POLICY_REVOKED"}
        session_id = secrets.token_hex(16)
        token = secrets.token_hex(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        self._sessions[session_id] = {
            "instance": inst,
            "expires_at": now + SESSION_TTL_S,
            "last_seq": 0,
            "token_digest": digest,
            "device_id": str(device_id),
        }
        return {"ok": True, "session_id": session_id, "token": token,
                "expires_in": SESSION_TTL_S, "instance_id": inst}

    def policy(self, browser_instance_id):
        pol = self._policies.get(str(browser_instance_id or ""))
        if not isinstance(pol, dict):
            return {"ok": True, "read_allowed": False,
                    "revoked": False, "granted_at": None,
                    "capabilities": [], "origins": [],
                    "display_name": ""}
        return {"ok": True, "read_allowed": bool(pol.get("read_allowed")),
                "revoked": bool(pol.get("revoked")),
                "origins": list(pol.get("origins") or []),
                "capabilities": ["read"],
                "display_name": str(pol.get("profile_name") or ""),
                "granted_at": pol.get("granted_at"),
                "revoked_at": pol.get("revoked_at"),
                "regranted_at": pol.get("regranted_at")}

    def revoke_policy(self, browser_instance_id):
        """Revoke permission: giu device link, tat policy. Re-grant manual
        van duoc; auto-grant bi chan cho toi khi policy bat lai (grant_policy
        hoac pair lai)."""
        pol = self._policies.get(str(browser_instance_id or ""))
        if isinstance(pol, dict):
            pol["read_allowed"] = False
            pol["revoked"] = True
            pol["revoked_at"] = self._clock()
        return {"ok": True, "revoked": True}

    def grant_policy(self, browser_instance_id):
        """Cap lai User Authorization sau revoke, KHONG can pair lai.
        Chi goi tu thao tac xac nhan ro rang cua user (server doi confirm).
        Device link giu nguyen; session cu neu con han van dung duoc."""
        pol = self._policies.get(str(browser_instance_id or ""))
        if not isinstance(pol, dict):
            return {"ok": False, "error": "POLICY_UNKNOWN"}
        pol["read_allowed"] = True
        pol["revoked"] = False
        pol["regranted_at"] = self._clock()
        return {"ok": True, "regranted": True}

    def rename(self, browser_instance_id, display_name):
        """Doi ten hien thi cua instance (do user dat). Chi la nhan con
        nguoi doc; KHONG dung cho auth, KHONG anh huong quyen/session."""
        name = str(display_name or "").strip()[:40]
        if not name:
            return {"ok": False, "error": "NAME_REQUIRED"}
        pol = self._policies.get(str(browser_instance_id or ""))
        dev = None
        for d in self._devices.values():
            if str(d.get("instance") or "") == str(browser_instance_id or ""):
                dev = d
                break
        if not isinstance(pol, dict) and dev is None:
            return {"ok": False, "error": "INSTANCE_UNKNOWN"}
        if isinstance(pol, dict):
            pol["profile_name"] = name
        if isinstance(dev, dict):
            dev["profile_name"] = name
        return {"ok": True, "display_name": name}

    def forget_device(self, device_id):
        """Forget device: xoa link + policy + moi session cua device.
        Pair lai tu dau moi ket noi duoc."""
        d = self._devices.pop(str(device_id or ""), None)
        gone = 0
        for sid in [k for k, v in self._sessions.items()
                    if v.get("device_id") == str(device_id or "")]:
            self._sessions.pop(sid, None)
            gone += 1
        if d is not None:
            self._policies.pop(str(d.get("instance") or ""), None)
        return {"ok": True, "forgotten": d is not None, "sessions": gone}

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

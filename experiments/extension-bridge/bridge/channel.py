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
        # One-click Approval: yeu cau lien ket dung 1 lan, co han.
        # request_id -> {secret_digest, fingerprint, hint, installation_id,
        #   created_at, expires_at, state, approved_at}.
        # state: pending|approved|consumed. Secret chi extension tao moi co.
        self._link_requests = {}
        # Profile Binding Challenge: challenge_id -> {request_id,
        #   profile_directory, created_at, expires_at, state}.
        # state: pending|consumed. Server mo trang verify tren Profile chi
        # dinh; extension trong Profile do thay URL -> nop challenge qua
        # kenh link-request cua minh -> server bind installation<->profile.
        self._challenges = {}

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
        return self._issue_credentials(str(profile_name or "")[:40])

    # -- One-click Approval (code-free pairing) --------------------------
    # Extension tao yeu cau lien ket (request_id + secret chi minh biet),
    # user xac nhan 1 lan tren Miro (backend key), extension doi secret lay
    # credential. Khong auto-pair: redeem chi thanh cong sau approve.
    def create_link_request(self, installation_id="", hint=""):
        """Tao yeu cau lien ket dung 1 lan, co han. Tra secret ve cho
        extension GIU (server chi luu digest)."""
        now = self._clock()
        live = {k: v for k, v in self._link_requests.items()
                if v.get("expires_at", 0) > now
                and v.get("state") == "pending"}
        self._link_requests = {k: v for k, v in self._link_requests.items()
                               if v.get("expires_at", 0) > now}
        for k, v in live.items():
            self._link_requests[k] = v
        if len(live) >= MAX_PAIRING_OUTSTANDING:
            return {"ok": False, "error": "LINK_BUSY"}
        inst = str(installation_id or "")[:64]
        if not inst:
            return {"ok": False, "error": "INSTALLATION_REQUIRED"}
        request_id = "lr-" + secrets.token_hex(8)
        secret = secrets.token_hex(24)
        digest = hashlib.sha256(secret.encode()).hexdigest()
        self._link_requests[request_id] = {
            "secret_digest": digest,
            "installation_id": inst,
            "hint": str(hint or "")[:40],
            "created_at": now,
            "expires_at": now + 300,
            "state": "pending",
            "approved_at": None,
            "display_name": "",
        }
        return {"ok": True, "request_id": request_id, "secret": secret,
                "expires_in": 300}

    def list_link_requests(self):
        """Miro UI: liet ke yeu cau pending (khong lo digest/secret)."""
        now = self._clock()
        out = []
        for rid, v in self._link_requests.items():
            if v.get("expires_at", 0) <= now:
                continue
            if v.get("state") != "pending":
                continue
            out.append({"request_id": rid,
                        "installation_id": v.get("installation_id", ""),
                        "hint": v.get("hint", ""),
                        "created_at": v.get("created_at")})
        return {"ok": True, "pending": out}

    def approve_link_request(self, request_id, display_name=""):
        """User xac nhan 1 lan tren Miro. Dieu kien: Profile da duoc xac
        minh qua challenge (verified_profile) — khong duyet request mo.
        Ten hien thi mac dinh = Profile directory da verify; operator co
        the dat ten khac (chi la nhan, khong dung auth)."""
        now = self._clock()
        v = self._link_requests.get(str(request_id or ""))
        if v is None or v.get("expires_at", 0) <= now:
            return {"ok": False, "error": "LINK_UNKNOWN_OR_EXPIRED"}
        if v.get("state") != "pending":
            return {"ok": False, "error": "LINK_ALREADY_USED"}
        prof = str(v.get("verified_profile") or "")
        if not prof:
            return {"ok": False, "error": "PROFILE_UNVERIFIED"}
        v["state"] = "approved"
        v["approved_at"] = now
        # Ten mac dinh = Profile da verify (tu dong, khong nhap tay);
        # operator/user doi sau qua /rename (chi la nhan hien thi).
        v["display_name"] = (str(display_name or "")[:40] or prof)
        return {"ok": True, "approved": True,
                "verified_profile": prof}

    def redeem_link_request(self, request_id, secret, installation_id=""):
        """Extension doi secret lay credential sau khi user approve.
        Rang buoc: secret khop digest + installation khop + approved +
        chua dung + con han. Dung 1 lan (consume)."""
        now = self._clock()
        if self._redeem_locked():
            return {"ok": False, "error": "PAIRING_LOCKED"}
        v = self._link_requests.get(str(request_id or ""))
        if v is None or v.get("expires_at", 0) <= now:
            self._redeem_fails.append(now)
            return {"ok": False, "error": "LINK_UNKNOWN_OR_EXPIRED"}
        if v.get("state") != "approved":
            # Chua approve: khong tinh fail, khong consume, cho tiep.
            return {"ok": False, "error": "LINK_NOT_APPROVED"}
        if str(v.get("installation_id") or "") != str(installation_id or ""):
            self._redeem_fails.append(now)
            return {"ok": False, "error": "INSTALLATION_MISMATCH"}
        got = hashlib.sha256(str(secret or "").encode()).hexdigest()
        if not hmac.compare_digest(str(v.get("secret_digest") or ""), got):
            self._redeem_fails.append(now)
            return {"ok": False, "error": "LINK_FORBIDDEN"}
        # Tieu thu 1 lan: xoa truoc khi cap credential (chong replay).
        name = str(v.get("display_name") or "")[:40]
        self._link_requests.pop(str(request_id or ""), None)
        return self._issue_credentials(name)

    # -- Profile Binding Challenge --------------------------------------
    # Miro mo trang verify tren Profile chi dinh (qua launcher san co);
    # extension trong Profile do thay URL /verify/<id> -> nop challenge qua
    # kenh link-request cua minh. Server bind installation<->profile that.
    # Khong doan tu URL, khong doc chrome://, khong sua du lieu Chrome.
    def issue_challenge(self, request_id, profile_directory):
        """Tao challenge dung 1 lan cho link-request dang pending.
        Can Backend role (nguoi duyet chi dinh Profile muc tieu)."""
        import re as _re
        now = self._clock()
        if not isinstance(profile_directory, str) or not _re.fullmatch(
                r"Default|Profile \d{1,5}", profile_directory):
            return {"ok": False, "error": "INVALID_PROFILE_DIRECTORY"}
        v = self._link_requests.get(str(request_id or ""))
        if v is None or v.get("expires_at", 0) <= now:
            return {"ok": False, "error": "LINK_UNKNOWN_OR_EXPIRED"}
        if v.get("state") != "pending":
            return {"ok": False, "error": "LINK_ALREADY_USED"}
        challenge_id = "ch-" + secrets.token_hex(8)
        self._challenges[challenge_id] = {
            "request_id": str(request_id),
            "profile_directory": profile_directory,
            "created_at": now,
            "expires_at": now + 300,
            "state": "pending",
        }
        return {"ok": True, "challenge_id": challenge_id,
                "verify_path": "/verify/" + challenge_id,
                "expires_in": 300}

    def answer_challenge(self, request_id, challenge_id, secret,
                         installation_id):
        """Extension nop challenge thay duoc trong tab cua Profile minh.
        Rang buoc: link-request con pending + secret/installation khop +
        challenge pending + cung request_id + con han. Dung 1 lan."""
        import re as _re
        now = self._clock()
        v = self._link_requests.get(str(request_id or ""))
        if v is None or v.get("expires_at", 0) <= now:
            self._redeem_fails.append(now)
            return {"ok": False, "error": "LINK_UNKNOWN_OR_EXPIRED"}
        if str(v.get("installation_id") or "") != str(installation_id or ""):
            self._redeem_fails.append(now)
            return {"ok": False, "error": "INSTALLATION_MISMATCH"}
        got = hashlib.sha256(str(secret or "").encode()).hexdigest()
        if not hmac.compare_digest(str(v.get("secret_digest") or ""), got):
            self._redeem_fails.append(now)
            return {"ok": False, "error": "LINK_FORBIDDEN"}
        c = self._challenges.get(str(challenge_id or ""))
        if c is None or c.get("expires_at", 0) <= now:
            return {"ok": False, "error": "CHALLENGE_UNKNOWN_OR_EXPIRED"}
        if c.get("state") != "pending":
            return {"ok": False, "error": "CHALLENGE_ALREADY_USED"}
        if str(c.get("request_id") or "") != str(request_id or ""):
            return {"ok": False, "error": "CHALLENGE_MISMATCH"}
        prof = str(c.get("profile_directory") or "")
        if not _re.fullmatch(r"Default|Profile \d{1,5}", prof):
            return {"ok": False, "error": "INVALID_PROFILE_DIRECTORY"}
        c["state"] = "consumed"
        v["verified_profile"] = prof
        v["verified_at"] = now
        return {"ok": True, "verified_profile": prof}

    def _issue_credentials(self, name=""):
        """Cap instance/device/session/policy moi (dung chung cho redeem
        code va redeem link-request da approve)."""
        now = self._clock()
        instance_id = "inst-" + secrets.token_hex(4)
        session_id = secrets.token_hex(16)
        token = secrets.token_hex(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        name = str(name or "")[:40]
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

"""Server demo kenh xac thuc (loopback 127.0.0.1, spike only).

Chay:  python server.py 18767
Pair:   server in pairing code ra console -> user nhap vao extension.
Khong phai production, khong mo ra ngoai loopback.

Bao mat loopback:
- Bind duy nhat 127.0.0.1 (khong 0.0.0.0).
- Khong wildcard CORS: khong phat Access-Control-Allow-Origin *.
- Origin la: chi nhan extension (chrome-extension://) hoac khong Origin
  (curl/test noi bo). Moi Origin http(s) la -> 403.
- Pairing code TTL ngan + gioi han so lan redeem sai (khoa tam thoi).
- Session token chi di trong header X-Token (POST), khong trong URL/log.
- Chi event read-only; bat ky action ghi nao -> ACTION_FORBIDDEN.
"""
import hashlib
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.channel import BridgeChannel  # noqa: E402
from bridge.grants import GrantStore, validate_read_spec  # noqa: E402
from bridge.importer import import_outbox  # noqa: E402
from bridge.registry import TabRegistry  # noqa: E402

CHANNEL = BridgeChannel(persist_path=str(
    Path(__file__).resolve().parent.parent.parent.parent
    / ".miro-runtime" / "bridge-trusted.json"))
REGISTRY = TabRegistry()
GRANTS = GrantStore()
OBSERVATIONS = {}  # (instance, tab, seq) -> untrusted DOM observation (B3)
# PENDING: request_id -> {instance, tab_id, spec, created_at, deadline,
#   state, claimed_by, claimed_at, cancelled}. state: queued|claimed|done.
PENDING = {}
# DONE: request_id -> stored_at. Terminal result bat bien: duplicate result
# cung request_id sau khi stored -> REQUEST_COMPLETED, khong ghi de.
DONE = {}
CANCELLED = {}  # request_id -> cancelled_at (TTL don 300s)
# Multi-profile: KHONG co instance mac dinh. Moi Extension installation
# duoc server cap instance_id RIENG (inst-xxxx) khi redeem thanh cong.
# Moi request backend phai chi ro instance; auth lay tu session/device,
# khong tin client tu khai instance de huong quyen instance khac.

# Credential separation:
# - Extension role: X-Session/X-Token (pairing). Duoc: /push /resync /grant
#   /inbox /read-result /revoke. KHONG duoc tao production request (/read).
# - Backend role: X-Backend-Key (MIRO_BRIDGE_BACKEND_KEY, so sanh hmac,
#   khong log). Duoc: /read (tao) /observations (poll) /cancel. KHONG duoc
#   gia danh result (/read-result).
# - task_id/lease owner KHONG phai HTTP auth, khong thay the 2 co che tren.
MAX_PENDING = 200
MAX_DONE = 500
PENDING_TTL_S = 120
CLAIM_RETRY_S = 30
REQUEST_TIMEOUT_DEFAULT_S = 30
REQUEST_TIMEOUT_MAX_S = 120


def _backend_key():
    return str(os.environ.get("MIRO_BRIDGE_BACKEND_KEY") or "")


def _backend_ok(value):
    """Xac thuc Backend role: hmac compare voi env key. Key rong -> deny."""
    key = _backend_key()
    if not key:
        return False
    got = str(value or "")
    if not got:
        return False
    return hmac.compare_digest(got, key)


def _cleanup_pending(now):
    """Don entry het han (deadline hoac TTL cung 120s) + enforce bound.
    Tra so da xoa. Vuot MAX_PENDING -> evict queued cu nhat truoc."""
    dead = [k for k, v in PENDING.items()
            if now - float(v.get("created_at", 0)) > PENDING_TTL_S
            or now > float(v.get("deadline", 0) or 0)]
    for k in dead:
        PENDING.pop(k, None)
    old_c = [k for k, v in CANCELLED.items()
               if now - float(v or 0) > 300]
    for k in old_c:
        CANCELLED.pop(k, None)
    while len(PENDING) > MAX_PENDING:
        oldest = min(PENDING,
                     key=lambda k: float(PENDING[k].get("created_at", 0)))
        PENDING.pop(oldest, None)
    if len(DONE) > MAX_DONE:
        for k in sorted(DONE, key=lambda x: DONE[x])[:len(DONE) - MAX_DONE]:
            DONE.pop(k, None)
    return len(dead)


def _origin_ok(value):
    if not value:
        return True  # curl/test noi bo, khong Origin
    v = value.strip()
    if v.startswith("chrome-extension://"):
        return True
    try:
        scheme = urlparse(v).scheme.lower()
    except ValueError:
        return False
    return scheme not in ("http", "https")


class Handler(BaseHTTPRequestHandler):
    server_version = "MiroBridge/0.3"
    timeout = 10

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # Khong wildcard CORS: chi phan hoi dung origin extension goi toi.
        origin = (self.headers.get("Origin") or "").strip()
        if origin.startswith("chrome-extension://"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        # Preflight tu extension: chi chap nhan origin extension.
        origin = (self.headers.get("Origin") or "").strip()
        if not origin.startswith("chrome-extension://"):
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, X-Session, X-Token")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        # Khong ho tro GET tham so/token tren URL. Pair qua POST /pair.
        if self.path == "/health":
            return self._send(200, {"ok": True})
        # Trang verify cho Profile Binding Challenge: Miro mo URL nay tren
        # Profile chi dinh (launcher san co). Extension trong Profile do doc
        # URL tab cua minh (chrome.tabs, khong can inject DOM) -> nop lai
        # challenge_id qua /link-answer. Khong token, khong auth o day.
        if (self.path or "").startswith("/verify/"):
            cid = (self.path or "")[len("/verify/"):].split(
                "?", 1)[0].split("/", 1)[0][:64]
            return self._send(200, {"ok": True, "challenge_id": cid,
                                    "hint": "miro-verify"})
        if self.path == "/tabs":
            # Spike only: doc registry tren loopback de nghiem thu live.
            tabs = [{"browser": k[0], "tab": k[1], "url": v.url,
                     "title": v.title, "event": v.last_event,
                     "av": v.availability}
                    for k, v in sorted(REGISTRY.tabs.items())]
            return self._send(200, {"ok": True, "tabs": tabs})
        if self.path == "/observations":
            # Production transport poll: backend (key) hoac extension
            # (session) moi duoc doc. Khong cho anonymous doc observation.
            _bkey_ok = _backend_ok(self.headers.get("X-Backend-Key", ""))
            _sess, _serr = CHANNEL._auth(
                self.headers.get("X-Session", ""),
                self.headers.get("X-Token", ""))
            if not _bkey_ok and _sess is None:
                return self._send(403, {"ok": False,
                                        "error": "OBS_AUTH_REQUIRED"})
            # Observation untrusted moi nhat, ke ca manual (co flag manual).
            items = []
            for (inst, tab, seq), ob in sorted(OBSERVATIONS.items()):
                items.append({"instance_id": inst, "tab_id": tab,
                              "seq": seq, "spec": ob.get("spec"),
                              "live_origin": ob.get("live_origin"),
                              "grant_epoch": ob.get("grant_seq", 0), "request_id": ob.get("request_id", ""),
                              "task_id": ob.get("task_id", ""),
                              "manual": bool(ob.get("manual", False)),
                              "data": ob.get("data"),
                              "untrusted": True,
                              "observed_at": ob.get("observed_at")})
            return self._send(200, {"ok": True,
                                    "observations": items[-50:]})
        return self._send(404, {"ok": False, "error": "NOT_FOUND"})

    def do_POST(self):
        if "?" in (self.path or ""):
            # Token khong bao gio trong URL/query.
            return self._send(403, {"ok": False,
                                    "error": "QUERY_NOT_ALLOWED"})
        if not _origin_ok(self.headers.get("Origin", "")):
            return self._send(403, {"ok": False, "error": "ORIGIN_DENIED"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > 65536:
            return self._send(413, {"ok": False, "error": "BODY_TOO_LARGE"})
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"ok": False, "error": "BAD_JSON"})
        if not isinstance(data, dict):
            return self._send(400, {"ok": False, "error": "BAD_JSON"})
        sid = self.headers.get("X-Session", "")
        tok = self.headers.get("X-Token", "")
        path = (self.path or "").split("?", 1)[0]
        if path == "/pair":
            code = CHANNEL.issue_pairing_code()
            if not code:
                return self._send(429, {"ok": False,
                                        "error": "PAIRING_BUSY"})
            print("PAIRING_CODE:", code, flush=True)
            return self._send(200, {"ok": True, "hint": "nhap code vao ext"})
        if path == "/redeem":
            # Multi-profile: server cap instance_id RIENG cho moi lan pair
            # thanh cong. profile_name chi la nhan hien thi, khong dung auth.
            r = CHANNEL.redeem(str(data.get("code") or ""),
                               profile_name=str(data.get("profile_name")
                                                or "")[:40])
            safe = {"ok": r["ok"], "error": r.get("error", "")}
            if r["ok"]:
                safe["session_id"] = r["session_id"]
                safe["token"] = r["token"]
                # Slice 01B: tra device_id de extension luu + reconnect.
                if r.get("device_id"):
                    safe["device_id"] = r["device_id"]
                # Multi-profile: extension luu instance rieng cua minh.
                if r.get("instance_id"):
                    safe["instance_id"] = r["instance_id"]
            return self._send(200, safe)
        if path == "/link-request":
            # One-click Approval: extension tao yeu cau lien ket (dung 1
            # lan, han 300s). Khong cap credential o day — doi user approve.
            r = CHANNEL.create_link_request(
                str(data.get("installation_id") or ""),
                str(data.get("hint") or ""))
            code = 200 if r.get("ok") else (
                429 if r.get("error") == "LINK_BUSY" else 400)
            return self._send(code, r)
        if path == "/link-pending":
            # Miro UI: xem yeu cau cho approve. Can Backend role
            # (user xac nhan tren Miro, khong phai extension tu duyet).
            if not _backend_ok(self.headers.get("X-Backend-Key", "")):
                return self._send(403, {"ok": False,
                                        "error": "BACKEND_AUTH_REQUIRED"})
            return self._send(200, CHANNEL.list_link_requests())
        if path == "/link-approve":
            # User xac nhan 1 lan tren Miro. Can Backend role + Profile da
            # duoc xac minh qua challenge (verified_profile).
            if not _backend_ok(self.headers.get("X-Backend-Key", "")):
                return self._send(403, {"ok": False,
                                        "error": "BACKEND_AUTH_REQUIRED"})
            r = CHANNEL.approve_link_request(
                str(data.get("request_id") or ""),
                str(data.get("display_name") or ""))
            return self._send(200 if r.get("ok") else 400, r)
        if path == "/challenge":
            # Tao Profile Binding Challenge cho link-request dang pending.
            # Can Backend role. Miro mo verify_path tren Profile chi dinh
            # (qua launcher san co); extension trong Profile do nop lai.
            if not _backend_ok(self.headers.get("X-Backend-Key", "")):
                return self._send(403, {"ok": False,
                                        "error": "BACKEND_AUTH_REQUIRED"})
            r = CHANNEL.issue_challenge(
                str(data.get("request_id") or ""),
                str(data.get("profile_directory") or ""))
            return self._send(200 if r.get("ok") else 400, r)
        if path == "/link-answer":
            # Extension nop challenge thay trong tab cua Profile minh.
            r = CHANNEL.answer_challenge(
                str(data.get("request_id") or ""),
                str(data.get("challenge_id") or ""),
                str(data.get("secret") or ""),
                str(data.get("installation_id") or ""))
            code = 200 if r.get("ok") else (
                403 if r.get("error") in ("LINK_FORBIDDEN",
                                          "INSTALLATION_MISMATCH") else 400)
            return self._send(code, r)
        if path == "/challenge-opened":
            # Launcher xac nhan: da mo verify URL tren dung Profile muc
            # tieu (mo bang --profile-directory). Can Backend role.
            if not _backend_ok(self.headers.get("X-Backend-Key", "")):
                return self._send(403, {"ok": False,
                                        "error": "BACKEND_AUTH_REQUIRED"})
            r = CHANNEL.mark_challenge_launched(
                str(data.get("challenge_id") or ""),
                str(data.get("profile_directory") or ""))
            return self._send(200 if r.get("ok") else 400, r)
        if path == "/link-confirm":
            # Fallback: nguoi dung xac nhan 1 lan Profile dang dung.
            # Can Backend role. Ghi verified_via=manual-confirm.
            if not _backend_ok(self.headers.get("X-Backend-Key", "")):
                return self._send(403, {"ok": False,
                                        "error": "BACKEND_AUTH_REQUIRED"})
            r = CHANNEL.confirm_profile_once(
                str(data.get("request_id") or ""),
                str(data.get("profile_directory") or ""),
                str(data.get("display_name") or ""))
            return self._send(200 if r.get("ok") else 400, r)
        if path == "/link-status":
            # Miro UI poll: request da verify chua (khong lo secret).
            if not _backend_ok(self.headers.get("X-Backend-Key", "")):
                return self._send(403, {"ok": False,
                                        "error": "BACKEND_AUTH_REQUIRED"})
            v = CHANNEL._link_requests.get(str(data.get("request_id") or ""))
            if v is None:
                return self._send(404, {"ok": False,
                                        "error": "LINK_UNKNOWN"})
            return self._send(200, {
                "ok": True, "state": str(v.get("state") or ""),
                # Phan biet (khong dung tham so launcher lam bang chung):
                # requested: moi gui, chua verify gi.
                # challenge_answered: installation da tra loi challenge
                #   (chua phai verified identity doc lap).
                # verified: chi khi co co che xac minh doc lap (tam thoi
                #   chi manual-confirm).
                "link_stage": ("verified"
                               if (str(v.get("verified_profile") or "")
                                   and str(v.get("verified_via") or ""))
                               else ("challenge_answered"
                                     if str(v.get("verified_profile") or "")
                                     else "requested")),
                "verified_profile": v.get("verified_profile") or "",
                "verified_via": v.get("verified_via") or ""})
        if path == "/link-redeem":
            # Extension doi secret lay credential sau approve.
            # Rang buoc: secret + installation khop + da approve + 1 lan.
            r = CHANNEL.redeem_link_request(
                str(data.get("request_id") or ""),
                str(data.get("secret") or ""),
                str(data.get("installation_id") or ""))
            safe = {"ok": r["ok"], "error": r.get("error", "")}
            if r["ok"]:
                safe["session_id"] = r["session_id"]
                safe["token"] = r["token"]
                if r.get("device_id"):
                    safe["device_id"] = r["device_id"]
                if r.get("instance_id"):
                    safe["instance_id"] = r["instance_id"]
            err = str(r.get("error") or "")
            code = 200 if r["ok"] else (
                403 if err in ("LINK_FORBIDDEN", "INSTALLATION_MISMATCH",
                               "PAIRING_LOCKED") else 400)
            return self._send(code, safe)
        if path == "/push":
            r = CHANNEL.push_events(sid, tok, data.get("seq"),
                                    data.get("events"))
            if r.get("error") == "RESYNC_REQUIRED":
                return self._send(409, r)
            if not r.get("ok"):
                return self._send(403, r)
            got = import_outbox(REGISTRY, r["instance"], r["events"])
            tabs = [{"tab": k[1], "url": v.url, "av": v.availability}
                    for k, v in sorted(REGISTRY.tabs.items())]
            return self._send(200, {"ok": True, "imported": got,
                                    "tabs": tabs})
        if path == "/resync":
            # W3: thieu complete=True -> fail-closed, khong xoa registry.
            if data.get("complete") is not True:
                return self._send(200, {"ok": True, "stale": [],
                                        "removed": [],
                                        "warning": "SNAPSHOT_NOT_COMPLETE"})
            r = CHANNEL.resync(sid, tok, data.get("seq"),
                               data.get("tabs"), data.get("generation"),
                               True)
            if not r.get("ok"):
                return self._send(403, r)
            rec = REGISTRY.reconcile_snapshot(
                r["instance"], data.get("tabs"), r["generation"],
                r["complete"])
            return self._send(200, {"ok": True, "stale": [],
                                    "removed": rec["removed"],
                                    "generation": r["generation"]})
        if path == "/revoke":
            # Multi-profile: revoke theo session goi toi (instance cua minh),
            # khong cham instance khac. Backend role (khong session) bat buoc
            # chi ro instance.
            s, err = CHANNEL._auth(sid, tok)
            if s is not None:
                inst = str(s.get("instance") or "")
            elif _backend_ok(self.headers.get("X-Backend-Key", "")):
                inst = str(data.get("instance") or "")
                if not inst:
                    return self._send(400, {"ok": False,
                                            "error": "INSTANCE_REQUIRED"})
            else:
                return self._send(403, {"ok": False, "error": "AUTH_REQUIRED"})
            n = CHANNEL.revoke(inst)
            REGISTRY.mark_unavailable(inst)
            GRANTS.revoke_instance(inst)
            return self._send(200, {"ok": True, "revoked": n,
                                    "instance": inst})
        if path == "/grant":
            # B1: KHONG tin truong `gesture` do caller gui. Grant chi cap khi:
            # session hop le + tab da co trong registry (extension that
            # observed) + origin allowlist + grant_seq don dieu.
            s, err = CHANNEL._auth(sid, tok)
            if s is None:
                return self._send(403, {"ok": False, "error": err})
            try:
                tab_id = int(data.get("tabId"))
            except (TypeError, ValueError):
                return self._send(400, {"ok": False, "error": "TAB_INVALID"})
            stale = int(str(s.get("last_seq") or 0))
            try:
                gseq = int(data.get("grant_seq"))
            except (TypeError, ValueError):
                return self._send(400, {"ok": False, "error": "SEQ_INVALID"})
            if gseq <= stale:
                return self._send(403, {"ok": False,
                                        "error": "GRANT_REPLAY"})
            rec = REGISTRY.tabs.get((s["instance"], tab_id))
            if rec is None:
                return self._send(404, {"ok": False, "error": "TAB_UNKNOWN"})
            g = GRANTS.grant(s["instance"], tab_id, rec.url, gseq)
            if not g["ok"]:
                return self._send(403, g)
            return self._send(200, g)
        if path == "/read":
            # BACKEND ROLE: tao production request. Auth = X-Backend-Key
            # (MIRO_BRIDGE_BACKEND_KEY). Extension session/token KHONG duoc
            # tao request. task_id/lease owner khong phai HTTP auth.
            if not _backend_ok(self.headers.get("X-Backend-Key", "")):
                return self._send(403, {"ok": False,
                                        "error": "BACKEND_AUTH_REQUIRED"})
            # Chi nhan read_spec co dinh; khong JS tuy y. Extension thuc thi
            # func cung da dong goi; backend kiem grant truoc khi cho doc.
            spec = validate_read_spec(data.get("read"))
            if not spec["ok"]:
                return self._send(403, spec)
            try:
                tab_id = int(data.get("tabId"))
            except (TypeError, ValueError):
                return self._send(400, {"ok": False, "error": "TAB_INVALID"})
            # Multi-profile: instance do BACKEND chi dinh theo ket noi dang
            # quan ly (service -> gateway -> transport). Khong tin client/JS
            # tu khai instance de huong quyen instance khac; instance chi hop
            # le khi trung tab da observed trong registry cho instance do.
            inst = str(data.get("instance") or "")
            if not inst:
                return self._send(400, {"ok": False,
                                        "error": "INSTANCE_REQUIRED"})
            rec = REGISTRY.tabs.get((inst, tab_id))
            if rec is None:
                return self._send(404, {"ok": False, "error": "TAB_UNKNOWN"})
            g = GRANTS.check(inst, tab_id, rec.url)
            if not g["ok"]:
                # Slice 01B: auto runtime grant ngan han trong pham vi policy.
                # Dieu kien: policy read_allowed + origin thuoc policy +
                # tab da observed trong registry. Grant thu cong van uu tien
                # (epoch cao hon); auto-grant ghi flag de truy vet.
                err = str(g.get("error") or "")
                auto = None
                if err in ("GRANT_REQUIRED", "GRANT_EXPIRED"):
                    pol = CHANNEL.policy(inst)
                    allowed = [str(o or "") for o in
                               (pol.get("origins") or [])]
                    if pol.get("read_allowed") and \
                            str(rec.url or "").startswith(tuple(allowed or ())):
                        auto = GRANTS.auto_grant(inst, tab_id, rec.url)
                if auto is None or not auto.get("ok"):
                    return self._send(403, g)
                auto_granted = True
            else:
                auto_granted = False
            # Backend KHONG doc DOM truc tiep; chi cho phep lenh doc co dinh.
            # Du lieu tra ve = chua tin cay, cho REA/Eye xac minh.
            try:
                timeout_s = float(data.get("timeout_s")
                                  or REQUEST_TIMEOUT_DEFAULT_S)
            except (TypeError, ValueError):
                timeout_s = float(REQUEST_TIMEOUT_DEFAULT_S)
            timeout_s = min(max(timeout_s, 1.0),
                            float(REQUEST_TIMEOUT_MAX_S))
            import secrets as _secrets
            import time as _time_req
            now = _time_req.time()
            _cleanup_pending(now)
            if len(PENDING) >= MAX_PENDING:
                # Registry bound: evict request cu nhat truoc khi them.
                oldest = min(PENDING,
                             key=lambda k: float(PENDING[k].get("created_at",
                                                                0)))
                PENDING.pop(oldest, None)
            request_id = _secrets.token_hex(8)
            PENDING[request_id] = {
                "instance": inst, "tab_id": tab_id,
                "spec": spec["spec"], "created_at": now,
                "deadline": now + timeout_s,
                "timeout_s": timeout_s,
                "task_id": str(data.get("task_id") or ""),
                "state": "queued", "claimed_by": "",
                "claimed_at": 0.0, "cancelled": False,
            }
            return self._send(200, {"ok": True, "read": spec["spec"],
                                    "tabId": tab_id,
                                    "status": "AUTHORIZED",
                                    "request_id": request_id,
                                    "deadline_in": timeout_s,
                                    "auto_grant": bool(auto_granted)})
        if path == "/navigate":
            # Slice 02B BACKEND ROLE: dieu huong tab den URL hop le.
            # Auth = X-Backend-Key. Extension session/token KHONG duoc tao
            # navigate. URL phai qua validate_navigate_url (origin allowlist).
            # Execution: extension chrome.tabs.update + observe lai URL moi.
            from bridge.grants import validate_navigate_url as _val_nav
            if not _backend_ok(self.headers.get("X-Backend-Key", "")):
                return self._send(403, {"ok": False,
                                        "error": "BACKEND_AUTH_REQUIRED"})
            nav = _val_nav(data.get("url"))
            if not nav["ok"]:
                return self._send(403, nav)
            try:
                tab_id = int(data.get("tabId"))
            except (TypeError, ValueError):
                return self._send(400, {"ok": False, "error": "TAB_INVALID"})
            inst = str(data.get("instance") or "")
            if not inst:
                return self._send(400, {"ok": False,
                                        "error": "INSTANCE_REQUIRED"})
            rec = REGISTRY.tabs.get((inst, tab_id))
            if rec is None:
                return self._send(404, {"ok": False, "error": "TAB_UNKNOWN"})
            pol = CHANNEL.policy(inst)
            if not pol.get("read_allowed") or pol.get("revoked"):
                return self._send(403, {"ok": False,
                                        "error": "POLICY_REVOKED"})
            try:
                timeout_s = float(data.get("timeout_s") or 30.0)
            except (TypeError, ValueError):
                timeout_s = 30.0
            timeout_s = min(max(timeout_s, 5.0), 60.0)
            import secrets as _secrets_nv
            import time as _time_nv
            now = _time_nv.time()
            _cleanup_pending(now)
            if len(PENDING) >= MAX_PENDING:
                oldest = min(PENDING,
                             key=lambda k: float(PENDING[k].get("created_at",
                                                                0)))
                PENDING.pop(oldest, None)
            request_id = _secrets_nv.token_hex(8)
            PENDING[request_id] = {
                "instance": inst, "tab_id": tab_id,
                "spec": "navigate", "url": nav["url"],
                "created_at": now, "deadline": now + timeout_s,
                "timeout_s": timeout_s,
                "task_id": str(data.get("task_id") or ""),
                "state": "queued", "claimed_by": "",
                "claimed_at": 0.0, "cancelled": False,
            }
            return self._send(200, {"ok": True, "navigate": nav["url"],
                                    "tabId": tab_id,
                                    "status": "AUTHORIZED",
                                    "request_id": request_id,
                                    "deadline_in": timeout_s})
        # ---- Slice 01B: one-click connection & persistent auth ----
        if path == "/reconnect":
            # Trusted reconnect: device da link xin session moi, khong code.
            # Instance lay tu device da luu, tra ve de extension cap nhat.
            r = CHANNEL.reconnect(str(data.get("device_id") or ""))
            safe = {"ok": r["ok"], "error": r.get("error", "")}
            if r["ok"]:
                safe["session_id"] = r["session_id"]
                safe["token"] = r["token"]
                if r.get("instance_id"):
                    safe["instance_id"] = r["instance_id"]
            return self._send(200 if r["ok"] else 403, safe)
        if path == "/policy":
            # Xem policy hien tai. Session role: policy cua instance minh.
            # Backend role: bat buoc chi ro instance.
            s, err = CHANNEL._auth(sid, tok)
            if s is not None:
                inst = str(s.get("instance") or "")
            else:
                inst = str(data.get("instance") or "")
                if not inst:
                    return self._send(400, {"ok": False,
                                            "error": "INSTANCE_REQUIRED"})
            return self._send(200, CHANNEL.policy(inst))
        if path == "/revoke-policy":
            # Revoke permission: tat auto-grant, giu device link.
            # Chi revoke instance cua session goi toi (khong cham B).
            s, err = CHANNEL._auth(sid, tok)
            if s is not None:
                inst = str(s.get("instance") or "")
            elif _backend_ok(
                    self.headers.get("X-Backend-Key", "")):
                inst = str(data.get("instance") or "")
                if not inst:
                    return self._send(400, {"ok": False,
                                            "error": "INSTANCE_REQUIRED"})
            else:
                return self._send(403, {"ok": False, "error": "AUTH_REQUIRED"})
            return self._send(200, CHANNEL.revoke_policy(inst))
        if path == "/grant-policy":
            # Cap lai User Authorization sau revoke, KHONG can pair lai.
            # Dieu kien cung: user xac nhan ro rang (confirm:true) qua kenh
            # da xac thuc (session cua chinh instance do). Device link giu
            # nguyen; khong mo rong origin/capability.
            s, err = CHANNEL._auth(sid, tok)
            if s is None:
                return self._send(403, {"ok": False, "error": err})
            if data.get("confirm") is not True:
                return self._send(400, {"ok": False,
                                        "error": "CONFIRM_REQUIRED"})
            return self._send(200, CHANNEL.grant_policy(
                str(s.get("instance") or "")))
        if path == "/rename":
            # Doi ten hien thi (nhan con nguoi). Chi la label, khong auth.
            s, err = CHANNEL._auth(sid, tok)
            if s is None:
                return self._send(403, {"ok": False, "error": err})
            r = CHANNEL.rename(str(s.get("instance") or ""),
                               str(data.get("display_name") or ""))
            return self._send(200 if r.get("ok") else 400, r)
        if path == "/forget":
            # Forget device: xoa link + policy + session. Pair lai tu dau.
            s, err = CHANNEL._auth(sid, tok)
            if s is None and not _backend_ok(
                    self.headers.get("X-Backend-Key", "")):
                return self._send(403, {"ok": False, "error": "AUTH_REQUIRED"})
            dev = str(data.get("device_id") or (s or {}).get("device_id")
                      or "")
            return self._send(200, CHANNEL.forget_device(dev))
        if path == "/cancel":
            # BACKEND ROLE: huy request dang cho (task cancel/stop).
            if not _backend_ok(self.headers.get("X-Backend-Key", "")):
                return self._send(403, {"ok": False,
                                        "error": "BACKEND_AUTH_REQUIRED"})
            rid = str(data.get("request_id") or "")
            pend = PENDING.get(rid) if rid else None
            if pend is None:
                if rid in DONE:
                    return self._send(409, {"ok": False,
                                            "error": "REQUEST_COMPLETED"})
                return self._send(404, {"ok": False,
                                        "error": "REQUEST_UNKNOWN"})
            import time as _time_cx
            pend["cancelled"] = True
            pend["state"] = "cancelled"
            PENDING.pop(rid, None)
            CANCELLED[rid] = _time_cx.time()
            return self._send(200, {"ok": True, "cancelled": True})
        if path == "/claim":
            # EXTENSION ROLE: claim nguyen tu 1 request queued ve minh.
            # Poll dong thoi lan 2 -> CLAIM_CONFLICT (atomic claim).
            s, err = CHANNEL._auth(sid, tok)
            if s is None:
                return self._send(403, {"ok": False, "error": err})
            import time as _time_cl
            now = _time_cl.time()
            _cleanup_pending(now)
            rid = str(data.get("request_id") or "")
            pend = PENDING.get(rid) if rid else None
            if pend is None:
                if rid in DONE:
                    return self._send(409, {"ok": False,
                                            "error": "REQUEST_COMPLETED"})
                return self._send(404, {"ok": False,
                                        "error": "REQUEST_EXPIRED"})
            if pend.get("cancelled") or pend.get("state") == "cancelled":
                PENDING.pop(rid, None)
                return self._send(410, {"ok": False,
                                        "error": "REQUEST_CANCELLED"})
            if pend.get("instance") != s["instance"]:
                return self._send(403, {"ok": False,
                                        "error": "INSTANCE_DENIED"})
            if pend.get("state") == "claimed":
                # Reclaim sau CLAIM_RETRY_S cho phep (extension chet giua
                # chung); trong cua so thi tu choi de chong double-exec.
                # Fencing: moi claim cap claim_token moi; result phai kem
                # token khop — result tu claim cu (da het hieu luc) bi
                # CLAIM_STALE, khong hoan thanh request.
                if now - float(pend.get("claimed_at", 0)) < CLAIM_RETRY_S:
                    return self._send(409, {"ok": False,
                                            "error": "CLAIM_CONFLICT"})
            import secrets as _secrets_cl
            claim_token = _secrets_cl.token_hex(8)
            pend["state"] = "claimed"
            pend["claimed_by"] = str(sid or "")
            pend["claimed_at"] = now
            pend["claim_token"] = claim_token
            pend["claim_seq"] = int(pend.get("claim_seq", 0) or 0) + 1
            return self._send(200, {"ok": True, "request_id": rid,
                                    "tabId": pend["tab_id"],
                                    "spec": pend["spec"],
                                    "url": str(pend.get("url") or ""),
                                    "claim_token": claim_token})
        if path == "/inbox":
            # Extension poll lenh doc cho (dispatch server -> extension).
            # Chi tra request queued (chua claimed/cancelled/het han).
            s, err = CHANNEL._auth(sid, tok)
            if s is None:
                return self._send(403, {"ok": False, "error": err})
            import time as _time_ib
            now = _time_ib.time()
            _cleanup_pending(now)
            mine = [{"request_id": k, "tabId": v["tab_id"],
                     "spec": v["spec"],
                     "url": str(v.get("url") or ""),
                     "deadline_in": max(0.0, float(v.get("deadline", 0))
                                        - now)}
                    for k, v in PENDING.items()
                    if v.get("instance") == s["instance"]
                    and v.get("state") == "queued"
                    and not v.get("cancelled")]
            return self._send(200, {"ok": True, "pending": mine})
        if path == "/read-result":
            # EXTENSION ROLE: chi extension (session/token) duoc gui result.
            # Backend key KHONG duoc gia danh result -> BACKEND_CANNOT_POST_RESULT.
            if _backend_key() and str(self.headers.get("X-Backend-Key") or ""):
                return self._send(403, {"ok": False,
                                        "error": "BACKEND_CANNOT_POST_RESULT"})
            s, err = CHANNEL._auth(sid, tok)
            if s is None:
                return self._send(403, {"ok": False, "error": err})
            is_nav_rr = str(data.get("read") or "") == "navigate" or \
                str(data.get("spec") or "") == "navigate"
            if is_nav_rr:
                spec = {"ok": True, "spec": "navigate"}
            else:
                spec = validate_read_spec(data.get("read"))
            if not spec["ok"]:
                return self._send(403, spec)
            try:
                tab_id = int(data.get("tabId"))
            except (TypeError, ValueError):
                return self._send(400, {"ok": False, "error": "TAB_INVALID"})
            # B2: kiem origin LIVE do extension gui kem, thu hoi khi mismatch.
            live_origin = str(data.get("live_origin") or "")
            g = GRANTS.check(s["instance"], tab_id, live_origin)
            if not g["ok"]:
                # Grant bi thu hoi/giua claim va execution -> GRANT thu hoi,
                # request van PENDING de backend timeout dung contract.
                return self._send(403, g)
            try:
                rseq = int(data.get("seq"))
            except (TypeError, ValueError):
                return self._send(400, {"ok": False, "error": "SEQ_INVALID"})
            import time as _time_rr
            now = _time_rr.time()
            _cleanup_pending(now)
            # MANUAL PATH: popup thu cong khong request_id -> luu observation
            # rieng (manual:true), KHONG hoan thanh production request nao.
            # Manual result KHONG bao gio duoc gan vao PENDING/DONE.
            rid = str(data.get("request_id") or "")
            if not rid:
                if rseq <= int(str(s.get("last_seq") or 0)):
                    return self._send(403, {"ok": False,
                                            "error": "SEQ_REPLAY"})
                if spec["spec"] == "navigate":
                    # Navigate khong co manual path: bat buoc production
                    # request_id do backend tao (fail-closed).
                    return self._send(403, {"ok": False,
                                            "error": "REQUEST_ID_MISMATCH"})
                payload = data.get("data")
                if not isinstance(payload, dict):
                    return self._send(400, {"ok": False,
                                            "error": "BAD_RESULT"})
                s["last_seq"] = rseq
                import time as _time_m
                from bridge.grants import SPEC_FIELDS as _SPEC_M
                mfields = _SPEC_M.get(spec["spec"], ("title", "url"))
                OBSERVATIONS[(s["instance"], tab_id, rseq)] = {
                    "spec": spec["spec"], "live_origin": live_origin,
                    "grant_seq": GRANTS.epoch(s["instance"], tab_id),
                    "request_id": "",
                    "manual": True,
                    "data": {k: str(payload.get(k) or "")[:2000]
                             for k in mfields},
                    "untrusted": True,
                    "observed_at": _time_m.time(),
                }
                return self._send(200, {"ok": True, "stored": True,
                                        "manual": True,
                                        "untrusted": True})
            # PRODUCTION PATH: bat buoc request_id khop truoc khi check seq.
            pend = PENDING.get(rid)
            if pend is None:
                if rid in DONE:
                    # Duplicate result sau terminal -> khong ghi de.
                    return self._send(409, {"ok": False,
                                            "error": "REQUEST_COMPLETED"})
                # Request dung format (16 hex) nhung khong con PENDING:
                # da het deadline/cancelled/bi cleanup -> EXPIRED thay vi
                # MISMATCH chung chung (deadline consistency). ID sai
                # format -> MISMATCH (khong phai production request).
                if rid in CANCELLED:
                    return self._send(410, {"ok": False,
                                            "error": "REQUEST_CANCELLED"})
                import re as _re
                if _re.fullmatch(r"[0-9a-f]{16}", rid or ""):
                    return self._send(410, {"ok": False,
                                            "error": "REQUEST_EXPIRED"})
                return self._send(403, {"ok": False,
                                        "error": "REQUEST_ID_MISMATCH"})
            # Deadline consistency: backend da timeout/cancel -> tu choi
            # late result, khong chap nhan lam ket qua moi.
            if pend.get("cancelled") or pend.get("state") == "cancelled":
                PENDING.pop(rid, None)
                return self._send(410, {"ok": False,
                                        "error": "REQUEST_CANCELLED"})
            if now > float(pend.get("deadline", 0) or 0):
                PENDING.pop(rid, None)
                return self._send(410, {"ok": False,
                                        "error": "REQUEST_EXPIRED"})
            if pend.get("instance") != s["instance"] \
                    or int(pend.get("tab_id", -1)) != int(tab_id) \
                    or str(pend.get("spec") or "") != str(spec["spec"] or ""):
                return self._send(403, {"ok": False,
                                        "error": "REQUEST_ID_MISMATCH"})
            # Claim fencing: neu request da duoc claim (co claim_token),
            # result phai kem token khop. Reclaim cap token moi -> result tu
            # claim cu bi CLAIM_STALE, khong hoan thanh request (Reviewer B:
            # reclaim 30s). Request chua claim lan nao (test truc tiep,
            # flow cu) -> chap nhan de tuong thich nguoc.
            _ct = str(pend.get("claim_token") or "")
            if _ct and str(data.get("claim_token") or "") != _ct:
                return self._send(409, {"ok": False,
                                        "error": "CLAIM_STALE"})
            if spec["spec"] == "navigate":
                # Slice 02B: navigate lam doi URL nen KHONG check grant
                # (grant gan voi origin cu). Thay vao do: policy phai con
                # hieu luc + live_origin sau navigate phai cung destination
                # voi URL backend yeu cau (extension bao cao that).
                if rseq <= int(str(s.get("last_seq") or 0)):
                    return self._send(403, {"ok": False,
                                            "error": "SEQ_REPLAY"})
                pol = CHANNEL.policy(s["instance"])
                if not pol.get("read_allowed") or pol.get("revoked"):
                    return self._send(403, {"ok": False,
                                            "error": "POLICY_REVOKED"})
                target = str(pend.get("url") or "")
                if not target or not str(live_origin or "").startswith(
                        "https://www.tiktok.com"):
                    return self._send(403, {"ok": False,
                                            "error": "NAVIGATE_MISMATCH"})
                try:
                    from urllib.parse import (urlparse as _up,
                                              parse_qsl as _pqs,
                                              urlencode as _ue)
                    _t, _l = _up(target), _up(str(live_origin or ""))
                    if _t.netloc != _l.netloc or \
                            _t.path.rstrip("/") != _l.path.rstrip("/"):
                        return self._send(403, {"ok": False,
                                                "error": "NAVIGATE_MISMATCH"})
                    _tq = dict(_pqs(_t.query, keep_blank_values=True))
                    _lq = dict(_pqs(_l.query, keep_blank_values=True))
                    if str(_tq.get("q", "")) != str(_lq.get("q", "")):
                        return self._send(403, {"ok": False,
                                                "error": "NAVIGATE_MISMATCH"})
                except Exception:
                    return self._send(403, {"ok": False,
                                            "error": "NAVIGATE_MISMATCH"})
                exec_err = str(data.get("exec_error") or "")
                if exec_err:
                    s["last_seq"] = rseq
                    PENDING.pop(rid, None)
                    DONE[rid] = now
                    _cleanup_pending(now)
                    return self._send(200, {"ok": True, "stored": False,
                                            "exec_error": exec_err,
                                            "terminal": True})
                payload = data.get("data")
                if not isinstance(payload, dict):
                    return self._send(400, {"ok": False,
                                            "error": "BAD_RESULT"})
                s["last_seq"] = rseq
                PENDING.pop(rid, None)
                DONE[rid] = now
                import time as _time_nv
                OBSERVATIONS[(s["instance"], tab_id, rseq)] = {
                    "spec": "navigate",
                    "live_origin": str(live_origin or ""),
                    "grant_seq": GRANTS.epoch(s["instance"], tab_id),
                    "request_id": rid,
                    "task_id": str(pend.get("task_id") or ""),
                    "data": {"url": str(payload.get("url")
                                        or live_origin or "")[:2000],
                             "title": str(payload.get("title") or "")[:2000]},
                    "untrusted": True,
                    "observed_at": _time_nv.time(),
                }
                return self._send(200, {"ok": True, "stored": True,
                                        "untrusted": True})
            # Grant bi thu hoi giua claim va execution -> tu choi execution,
            # giu request de backend timeout/huy dung contract.
            gg = GRANTS.check(pend.get("instance"), pend.get("tab_id"),
                              live_origin)
            if not gg["ok"]:
                return self._send(403, gg)
            if rseq <= int(str(s.get("last_seq") or 0)):
                return self._send(403, {"ok": False, "error": "SEQ_REPLAY"})
            payload = data.get("data")
            if not isinstance(payload, dict):
                return self._send(400, {"ok": False, "error": "BAD_RESULT"})
            # Error propagation: extension bao loi execution (NAVIGATION_RACE,
            # NOT_ACTIVE_TAB...) -> luu terminal error, khong luu data gia.
            exec_err = str(data.get("exec_error") or "")
            if exec_err:
                s["last_seq"] = rseq
                PENDING.pop(rid, None)
                DONE[rid] = now
                _cleanup_pending(now)
                return self._send(200, {"ok": True, "stored": False,
                                        "exec_error": exec_err,
                                        "terminal": True})
            s["last_seq"] = rseq
            PENDING.pop(rid, None)
            DONE[rid] = now
            import time as _time
            from bridge.grants import SPEC_FIELDS as _SPEC_FIELDS
            fields = _SPEC_FIELDS.get(spec["spec"], ("title", "url"))
            OBSERVATIONS[(s["instance"], tab_id, rseq)] = {
                "spec": spec["spec"], "live_origin": live_origin,
                "grant_seq": GRANTS.epoch(s["instance"], tab_id),
                "request_id": rid,
                "task_id": str(pend.get("task_id") or ""),
                "data": {k: str(payload.get(k) or "")[:2000]
                         for k in fields},
                "untrusted": True,
                "observed_at": _time.time(),
            }
            return self._send(200, {"ok": True, "stored": True,
                                    "untrusted": True})
        return self._send(404, {"ok": False, "error": "NOT_FOUND"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18767
    print("bridge demo tren 127.0.0.1:%d (spike only)" % port, flush=True)
    # Bind duy nhat loopback. Threading: Chrome giu tab /verify keep-alive
    # khong chan request khac (don luong gay refused that o production).
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()

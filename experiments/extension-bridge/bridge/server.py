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
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.channel import BridgeChannel  # noqa: E402
from bridge.grants import GrantStore, validate_read_spec  # noqa: E402
from bridge.importer import import_outbox  # noqa: E402
from bridge.registry import TabRegistry  # noqa: E402

CHANNEL = BridgeChannel()
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
INSTANCE = "profile20-main"

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
            r = CHANNEL.redeem(str(data.get("code") or ""), INSTANCE)
            safe = {"ok": r["ok"], "error": r.get("error", "")}
            if r["ok"]:
                safe["session_id"] = r["session_id"]
                safe["token"] = r["token"]
                # Slice 01B: tra device_id de extension luu + reconnect.
                if r.get("device_id"):
                    safe["device_id"] = r["device_id"]
            return self._send(200, safe)
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
            n = CHANNEL.revoke(INSTANCE)
            REGISTRY.mark_unavailable(INSTANCE)
            GRANTS.revoke_instance(INSTANCE)
            return self._send(200, {"ok": True, "revoked": n})
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
            inst = str(data.get("instance") or INSTANCE)
            # Profile/tab binding: chi instance nay (profile20-main).
            if inst != INSTANCE:
                return self._send(403, {"ok": False,
                                        "error": "INSTANCE_DENIED"})
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
        # ---- Slice 01B: one-click connection & persistent auth ----
        if path == "/reconnect":
            # Trusted reconnect: device da link xin session moi, khong code.
            r = CHANNEL.reconnect(str(data.get("device_id") or ""),
                                  INSTANCE)
            safe = {"ok": r["ok"], "error": r.get("error", "")}
            if r["ok"]:
                safe["session_id"] = r["session_id"]
                safe["token"] = r["token"]
            return self._send(200 if r["ok"] else 403, safe)
        if path == "/policy":
            # Xem policy hien tai (extension role hoac backend role).
            return self._send(200, CHANNEL.policy(INSTANCE))
        if path == "/revoke-policy":
            # Revoke permission: tat auto-grant, giu device link.
            s, err = CHANNEL._auth(sid, tok)
            if s is None and not _backend_ok(
                    self.headers.get("X-Backend-Key", "")):
                return self._send(403, {"ok": False, "error": "AUTH_REQUIRED"})
            return self._send(200, CHANNEL.revoke_policy(INSTANCE))
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
    # Bind duy nhat loopback.
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()

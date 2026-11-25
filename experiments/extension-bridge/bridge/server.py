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
import json
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
PENDING = {}  # request_id -> {instance, tab_id, spec, created_at} (inbox dispatch)
INSTANCE = "profile20-main"


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
            # Production transport poll: observation untrusted moi nhat.
            items = []
            for (inst, tab, seq), ob in sorted(OBSERVATIONS.items()):
                items.append({"instance_id": inst, "tab_id": tab,
                              "seq": seq, "spec": ob.get("spec"),
                              "live_origin": ob.get("live_origin"),
                              "grant_epoch": ob.get("grant_seq", 0), "request_id": ob.get("request_id", ""),
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
            # Chi nhan read_spec co dinh; khong JS tuy y. Extension thuc thi
            # func cung da dong goi; backend kiem grant truoc khi cho doc.
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
            rec = REGISTRY.tabs.get((s["instance"], tab_id))
            if rec is None:
                return self._send(404, {"ok": False, "error": "TAB_UNKNOWN"})
            g = GRANTS.check(s["instance"], tab_id, rec.url)
            if not g["ok"]:
                return self._send(403, g)
            # Backend KHONG doc DOM truc tiep; chi cho phep lenh doc co dinh.
            # Du lieu tra ve = chua tin cay, cho REA/Eye xac minh.
            import secrets as _secrets
            import time as _time_req
            request_id = _secrets.token_hex(8)
            PENDING[request_id] = {"instance": s["instance"],
                                   "tab_id": tab_id,
                                   "spec": spec["spec"],
                                   "created_at": _time_req.time()}
            return self._send(200, {"ok": True, "read": spec["spec"],
                                    "tabId": tab_id,
                                    "status": "AUTHORIZED",
                                    "request_id": request_id})
        if path == "/inbox":
            # Extension poll lenh doc cho (dispatch server -> extension).
            s, err = CHANNEL._auth(sid, tok)
            if s is None:
                return self._send(403, {"ok": False, "error": err})
            import time as _time_ib
            now = _time_ib.time()
            stale = [k for k, v in PENDING.items()
                     if now - float(v.get("created_at", 0)) > 120
                     or v.get("instance") != s["instance"]]
            for k in stale:
                PENDING.pop(k, None)
            mine = [{"request_id": k, "tabId": v["tab_id"],
                     "spec": v["spec"]} for k, v in PENDING.items()
                    if v.get("instance") == s["instance"]]
            return self._send(200, {"ok": True, "pending": mine})
        if path == "/read-result":
            # B3: DOM result TACH RIENG khoi /push lifecycle. Khong ghi de
            # TabRegistry. Luu untrusted observation, cho REA/Eye xac minh.
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
                return self._send(403, g)
            try:
                rseq = int(data.get("seq"))
            except (TypeError, ValueError):
                return self._send(400, {"ok": False, "error": "SEQ_INVALID"})
            # Correlation TRUOC seq: observation phai gan dung request_id
            # vua dispatch. Thieu/sai -> REQUEST_ID_MISMATCH, khong bump
            # last_seq, khong pop PENDING (cho phep retry dung request_id).
            # Chong nhan nham observation cu cua popup thu cong.
            rid = str(data.get("request_id") or "")
            pend = PENDING.get(rid) if rid else None
            if pend is None or pend.get("instance") != s["instance"] \
                    or int(pend.get("tab_id", -1)) != int(tab_id) \
                    or str(pend.get("spec") or "") != str(spec["spec"] or ""):
                return self._send(403, {"ok": False,
                                        "error": "REQUEST_ID_MISMATCH"})
            if rseq <= int(str(s.get("last_seq") or 0)):
                return self._send(403, {"ok": False, "error": "SEQ_REPLAY"})
            payload = data.get("data")
            if not isinstance(payload, dict):
                return self._send(400, {"ok": False, "error": "BAD_RESULT"})
            s["last_seq"] = rseq
            PENDING.pop(rid, None)
            import time as _time
            from bridge.grants import SPEC_FIELDS as _SPEC_FIELDS
            fields = _SPEC_FIELDS.get(spec["spec"], ("title", "url"))
            OBSERVATIONS[(s["instance"], tab_id, rseq)] = {
                "spec": spec["spec"], "live_origin": live_origin,
                "grant_seq": GRANTS.epoch(s["instance"], tab_id),
                "request_id": rid,
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

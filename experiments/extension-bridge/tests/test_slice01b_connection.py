"""Slice 01B: one-click connection & persistent authorization.

- Pair 1 lan -> device_id + policy read_allowed.
- /reconnect cap lai session bang device_id, khong can code.
- /read tu dong auto-grant runtime ngan han khi policy cho phep
  (khong can Grant DOM thu cong). Grant tay van uu tien (epoch cao hon).
- /revoke-policy tat auto-grant (grant tay van duoc).
- /forget xoa link + policy + session -> reconnect that bai, phai pair lai.
- Disconnect la trang thai extension-local (dung poll); server khong giu
  flag — OFF/ON nghiem thu tren Chrome that.
"""
import json
import sys
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.server import Handler  # noqa: E402

BASE_PORT = [18801]
BASE = "http://127.0.0.1:18801"


def _post(path, body, sid="", tok="", bkey=""):
    headers = {"Content-Type": "application/json",
               "X-Session": sid, "X-Token": tok}
    if bkey:
        headers["X-Backend-Key"] = bkey
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body or {}).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def _post_expect(path, body, sid="", tok="", bkey=""):
    try:
        return (200, _post(path, body, sid, tok, bkey))
    except urllib.error.HTTPError as exc:
        try:
            out = json.loads(exc.read().decode())
        except Exception:
            out = {"error": str(exc.code)}
        return (exc.code, out)


def _reset():
    from bridge import server as _srv
    _srv.CHANNEL._sessions.clear()
    _srv.CHANNEL._pairing.clear()
    _srv.CHANNEL._devices.clear()
    _srv.CHANNEL._policies.clear()
    _srv.GRANTS._grants.clear()
    _srv.REGISTRY.tabs.clear()
    _srv.OBSERVATIONS.clear()
    _srv.PENDING.clear()
    _srv.DONE.clear()
    import os
    os.environ["MIRO_BRIDGE_BACKEND_KEY"] = "test-backend-key-01"


def _boot():
    global BASE
    _reset()
    HTTPServer.allow_reuse_address = True
    for _ in range(20):
        BASE_PORT[0] += 1
        try:
            srv = HTTPServer(("127.0.0.1", BASE_PORT[0]), Handler)
            break
        except OSError:
            continue
    BASE = "http://127.0.0.1:%d" % BASE_PORT[0]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def _pair():
    from bridge.server import CHANNEL
    c = CHANNEL.issue_pairing_code()
    assert c, "khong sinh duoc pairing code"
    r = _post("/redeem", {"code": c})
    assert r.get("ok") and r.get("device_id"), r
    return r


def _push(sid, tok, tab, seq, url="https://www.tiktok.com/"):
    return _post("/push", {"seq": seq, "events": [
        {"event": "updated", "tabId": tab, "url": url,
         "title": "t", "status": "complete"}]}, sid, tok)


def test_pair_returns_device_and_policy():
    srv = _boot()
    try:
        r = _pair()
        code, out = _post_expect("/policy", {}, r["session_id"], r["token"])
        assert code == 200 and out.get("read_allowed"), (code, out)
        assert "https://www.tiktok.com" in (out.get("origins") or []), out
        print("pair device+policy: PASS")
    finally:
        srv.shutdown()


def test_reconnect_without_code():
    srv = _boot()
    try:
        from bridge.server import CHANNEL
        r = _pair()
        dev = r["device_id"]
        sid, tok = r["session_id"], r["token"]
        _push(sid, tok, 41, 1)
        # Gia session het han: xoa session cu, reconnect bang device.
        CHANNEL._sessions.pop(sid, None)
        code, out = _post_expect("/reconnect", {"device_id": dev})
        assert code == 200 and out.get("ok"), (code, out)
        assert out.get("session_id") and out.get("token"), out
        nsid, ntok = out["session_id"], out["token"]
        # Session moi dung duoc ngay (push seq bat dau lai tu 1).
        p = _push(nsid, ntok, 41, 1)
        assert p.get("ok"), p
        print("reconnect without code: PASS")
    finally:
        srv.shutdown()


def test_auto_grant_on_read():
    srv = _boot()
    try:
        r = _pair()
        sid, tok = r["session_id"], r["token"]
        _push(sid, tok, 42, 1)
        # KHONG grant tay. Backend tao /read -> server tu auto-grant.
        c = _post("/read", {"tabId": 42, "read": "title",
                            "timeout_s": 30},
                  bkey="test-backend-key-01")
        assert c.get("ok") and c.get("request_id"), c
        assert c.get("auto_grant") is True, c
        # Claim + execute + result van qua dung contract.
        cl = _post("/claim", {"request_id": c["request_id"]}, sid, tok)
        assert cl.get("ok") and cl.get("claim_token"), cl
        from bridge.server import CHANNEL as _CH
        seq = int(_CH._sessions[sid].get("last_seq", 0)) + 1
        ok = _post("/read-result",
                   {"seq": seq, "tabId": 42, "read": "title",
                    "live_origin": "https://www.tiktok.com/",
                    "data": {"title": "t", "url": "https://www.tiktok.com/"},
                    "request_id": c["request_id"],
                    "claim_token": cl["claim_token"]}, sid, tok)
        assert ok.get("stored"), ok
        print("auto-grant on read: PASS")
    finally:
        srv.shutdown()


def test_revoke_policy_blocks_auto_grant():
    srv = _boot()
    try:
        r = _pair()
        sid, tok = r["session_id"], r["token"]
        _push(sid, tok, 43, 1)
        v = _post("/revoke-policy", {}, sid, tok)
        assert v.get("revoked"), v
        code, out = _post_expect("/read", {"tabId": 43, "read": "title"},
                                 bkey="test-backend-key-01")
        assert code == 403, (code, out)
        # Grant tay van duoc sau revoke (uu tien manual).
        _push(sid, tok, 43, 2)
        g = _post("/grant", {"tabId": 43, "grant_seq": 3}, sid, tok)
        assert g.get("ok"), g
        c = _post("/read", {"tabId": 43, "read": "title"},
                  bkey="test-backend-key-01")
        assert c.get("ok") and not c.get("auto_grant"), c
        print("revoke blocks auto-grant, manual still works: PASS")
    finally:
        srv.shutdown()


def test_forget_device_requires_repair():
    srv = _boot()
    try:
        from bridge.server import CHANNEL
        r = _pair()
        dev = r["device_id"]
        sid, tok = r["session_id"], r["token"]
        f = _post("/forget", {"device_id": dev}, sid, tok)
        assert f.get("forgotten"), f
        code, out = _post_expect("/reconnect", {"device_id": dev})
        assert code in (403, 404), (code, out)
        assert CHANNEL.policy("profile20-main").get("read_allowed") is False
        print("forget requires re-pair: PASS")
    finally:
        srv.shutdown()

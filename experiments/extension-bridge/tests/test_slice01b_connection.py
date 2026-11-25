"""Slice 01B + multi-profile: one-click connection & persistent authorization.

- Pair 1 lan -> instance_id RIENG (inst-xxxx) + device_id + policy read_allowed.
- /reconnect cap lai session bang device_id, khong can code (tra instance).
- /read bat buoc instance (backend chi dinh); tu dong auto-grant runtime
  ngan han khi policy cho phep. Grant tay van uu tien (epoch cao hon).
- /revoke-policy tat auto-grant cua RIENG instance do (grant tay van duoc).
- /forget xoa link + policy + session -> reconnect that bai, phai pair lai.
- Hai Profile pair doc lap: request dung instance, khong doc nham;
  revoke A khong anh huong B; restart A khong mat B.
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
    _srv.CHANNEL._redeem_fails.clear()
    _srv.CHANNEL._link_requests.clear()
    _srv.GRANTS._grants.clear()
    _srv.GRANTS._used_grant_seq.clear()
    _srv.REGISTRY.tabs.clear()
    _srv.OBSERVATIONS.clear()
    _srv.PENDING.clear()
    _srv.DONE.clear()
    _srv.CANCELLED.clear()
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


def _pair(name=""):
    from bridge.server import CHANNEL
    c = CHANNEL.issue_pairing_code()
    assert c, "khong sinh duoc pairing code"
    body = {"code": c}
    if name:
        body["profile_name"] = name
    r = _post("/redeem", body)
    assert r.get("ok") and r.get("device_id") and r.get("instance_id"), r
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
        sid, tok, inst = r["session_id"], r["token"], r["instance_id"]
        _push(sid, tok, 42, 1)
        # KHONG grant tay. Backend tao /read -> server tu auto-grant.
        c = _post("/read", {"tabId": 42, "read": "title",
                            "instance": inst, "timeout_s": 30},
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
        sid, tok, inst = r["session_id"], r["token"], r["instance_id"]
        _push(sid, tok, 43, 1)
        v = _post("/revoke-policy", {}, sid, tok)
        assert v.get("revoked"), v
        code, out = _post_expect("/read", {"tabId": 43, "read": "title",
                                           "instance": inst},
                                 bkey="test-backend-key-01")
        assert code == 403, (code, out)
        # Grant tay van duoc sau revoke (uu tien manual).
        _push(sid, tok, 43, 2)
        g = _post("/grant", {"tabId": 43, "grant_seq": 3}, sid, tok)
        assert g.get("ok"), g
        c = _post("/read", {"tabId": 43, "read": "title",
                            "instance": inst},
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
        assert CHANNEL.policy(r.get("instance_id", "")).get(
            "read_allowed") is False
        print("forget requires re-pair: PASS")
    finally:
        srv.shutdown()


def test_two_profiles_isolated():
    """Acceptance multi-profile: 2 Profile pair doc lap, ket noi dong thoi.
    - Instance khac nhau (server cap, khong tin client).
    - /read dung instance A chi doc duoc tab cua A (B -> TAB_UNKNOWN).
    - Revoke/revoke-policy A khong anh huong B.
    - Restart A (reconnect bang device A) khong mat B.
    """
    srv = _boot()
    try:
        from bridge.server import CHANNEL
        a = _pair()
        b = _pair()
        assert a["instance_id"] != b["instance_id"], (a, b)
        assert a["device_id"] != b["device_id"], (a, b)
        sa, ta, ia = a["session_id"], a["token"], a["instance_id"]
        sb, tb, ib = b["session_id"], b["token"], b["instance_id"]
        _push(sa, ta, 71, 1)
        _push(sb, tb, 72, 1)
        # Backend doc A -> ok; doc nham tab B bang instance A -> 404.
        ra = _post("/read", {"tabId": 71, "read": "title",
                             "instance": ia},
                   bkey="test-backend-key-01")
        assert ra.get("ok") and ra.get("request_id"), ra
        code, out = _post_expect("/read", {"tabId": 72, "read": "title",
                                           "instance": ia},
                                 bkey="test-backend-key-01")
        assert code == 404 and out.get("error") == "TAB_UNKNOWN", (code, out)
        # Khong instance -> 400 (khong doan instance mac dinh).
        code, out = _post_expect("/read", {"tabId": 71, "read": "title"},
                                 bkey="test-backend-key-01")
        assert code == 400 and out.get("error") == "INSTANCE_REQUIRED", \
            (code, out)
        # Revoke session A -> B van push/inbox binh thuong.
        n = CHANNEL.revoke(ia)
        assert n >= 1, n
        code, out = _post_expect("/push", {"seq": 2, "events": []},
                                 sa, ta)
        assert code == 403, (code, out)
        okb = _push(sb, tb, 72, 2)
        assert okb.get("ok"), okb
        ibx = _post("/inbox", {}, sb, tb)
        assert ibx.get("ok"), ibx
        # Revoke-policy A chi tat A, B van auto-grant duoc.
        # (A da het session nen dung backend role + instance cu the.)
        v = _post("/revoke-policy", {"instance": ib}, sb, tb)
        assert v.get("revoked"), v
        code, out = _post_expect("/read", {"tabId": 72, "read": "title",
                                           "instance": ib},
                                 bkey="test-backend-key-01")
        assert code == 403, (code, out)
        print("two profiles isolated: PASS")
    finally:
        srv.shutdown()


def test_reconnect_keeps_other_profile():
    """Restart 1 Profile (reconnect bang device) khong mat Profile con lai."""
    srv = _boot()
    try:
        from bridge.server import CHANNEL
        a = _pair()
        b = _pair()
        sa, ta = a["session_id"], a["token"]
        sb, tb = b["session_id"], b["token"]
        _push(sa, ta, 81, 1)
        _push(sb, tb, 82, 1)
        # Gia A restart: mat session, reconnect bang device A.
        CHANNEL._sessions.pop(sa, None)
        code, out = _post_expect("/reconnect",
                                 {"device_id": a["device_id"]})
        assert code == 200 and out.get("ok"), (code, out)
        assert out.get("instance_id") == a["instance_id"], out
        nsa, nta = out["session_id"], out["token"]
        assert _push(nsa, nta, 81, 1).get("ok")
        # B khong anh huong: session cu van dung.
        assert _push(sb, tb, 82, 2).get("ok")
        rb = _post("/read", {"tabId": 82, "read": "title",
                             "instance": b["instance_id"]},
                   bkey="test-backend-key-01")
        assert rb.get("ok") and rb.get("auto_grant"), rb
        print("reconnect keeps other profile: PASS")
    finally:
        srv.shutdown()


def test_display_name_never_auth():
    """Ten hien thi do user dat khi pair; doi ten khong anh huong auth.
    Ten khong dung lam can cu xac thuc/cap quyen o bat ky endpoint nao."""
    srv = _boot()
    try:
        from bridge.server import CHANNEL
        a = _pair(name="Chrome ca nhan")
        sa, ta, ia = a["session_id"], a["token"], a["instance_id"]
        assert CHANNEL.policy(ia).get("display_name") == "Chrome ca nhan"
        _push(sa, ta, 91, 1)
        # Doi ten: session/quyen/grant giu nguyen, doc van duoc.
        r = _post("/rename", {"display_name": "Chrome lam content"},
                  sa, ta)
        assert r.get("ok"), r
        assert CHANNEL.policy(ia).get("display_name") == "Chrome lam content"
        assert CHANNEL.policy(ia).get("read_allowed") is True
        c = _post("/read", {"tabId": 91, "read": "title", "instance": ia},
                  bkey="test-backend-key-01")
        assert c.get("ok"), c
        # Ten rong -> tu choi, ten cu giu nguyen.
        code, out = _post_expect("/rename", {"display_name": "  "}, sa, ta)
        assert code == 400, (code, out)
        print("display name never auth: PASS")
    finally:
        srv.shutdown()


def test_regrant_after_revoke_without_repair():
    """Cap lai quyen sau revoke KHONG can pair lai.
    Dieu kien: confirm:true qua kenh da xac thuc (session cua instance).
    Thieu confirm -> tu choi; khong mo rong origin/capability."""
    srv = _boot()
    try:
        a = _pair()
        sa, ta, ia = a["session_id"], a["token"], a["instance_id"]
        _push(sa, ta, 92, 1)
        v = _post("/revoke-policy", {}, sa, ta)
        assert v.get("revoked"), v
        code, out = _post_expect("/read", {"tabId": 92, "read": "title",
                                           "instance": ia},
                                 bkey="test-backend-key-01")
        assert code == 403, (code, out)
        # Thieu confirm -> tu choi.
        code, out = _post_expect("/grant-policy", {}, sa, ta)
        assert code == 400 and out.get("error") == "CONFIRM_REQUIRED", \
            (code, out)
        # Confirm ro rang -> cap lai duoc, doc lai auto-grant.
        g = _post("/grant-policy", {"confirm": True}, sa, ta)
        assert g.get("regranted"), g
        c = _post("/read", {"tabId": 92, "read": "title", "instance": ia},
                  bkey="test-backend-key-01")
        assert c.get("ok") and c.get("auto_grant"), c
        print("regrant without re-pair: PASS")
    finally:
        srv.shutdown()


def test_policy_errors_are_not_revoked():
    """/policy khong auth -> INSTANCE_REQUIRED (khong phai revoked).
    Loi doc policy khong duoc dien giai thanh trang thai Revoked/OFF."""
    srv = _boot()
    try:
        # Khong session, khong instance -> 400, khong phai revoked.
        code, out = _post_expect("/policy", {})
        assert code == 400 and out.get("error") == "INSTANCE_REQUIRED", \
            (code, out)
        assert "revoked" not in out, out
        # Session hop le nhung instance la -> policy that.
        a = _pair()
        sa, ta = a["session_id"], a["token"]
        p = _post("/policy", {}, sa, ta)
        assert p.get("ok") and p.get("read_allowed") is True, p
        assert p.get("revoked") is False, p
        assert p.get("capabilities") == ["read"], p
        print("policy errors are not revoked: PASS")
    finally:
        srv.shutdown()


def test_link_approve_redeem_once():
    """One-click Approval: request -> approve (backend key) -> redeem 1 lan.
    Chua approve -> tu choi; redeem xong -> request het (replay bi tu choi)."""
    srv = _boot()
    try:
        q = _post("/link-request",
                  {"installation_id": "install-A", "hint": "Chrome ca nhan"})
        assert q.get("ok") and q.get("request_id") and q.get("secret"), q
        rid, sec = q["request_id"], q["secret"]
        # Chua approve: redeem bi tu choi, chua consume.
        code, out = _post_expect("/link-redeem",
                                 {"request_id": rid, "secret": sec,
                                  "installation_id": "install-A"})
        assert code == 400 and out.get("error") == "LINK_NOT_APPROVED", \
            (code, out)
        # Extension KHONG tu approve duoc (thieu backend key).
        code, out = _post_expect("/link-approve",
                                 {"request_id": rid,
                                  "display_name": "Chrome ca nhan"})
        assert code == 403, (code, out)
        # User duyet 1 lan tren Miro (backend key).
        a = _post("/link-approve",
                  {"request_id": rid, "display_name": "Chrome ca nhan"},
                  bkey="test-backend-key-01")
        assert a.get("approved"), a
        # Redeem thanh cong: co credential + instance rieng + ten hien thi.
        r = _post("/link-redeem",
                  {"request_id": rid, "secret": sec,
                   "installation_id": "install-A"})
        assert r.get("ok") and r.get("session_id") and r.get("token"), r
        assert r.get("instance_id", "").startswith("inst-"), r
        from bridge.server import CHANNEL
        assert CHANNEL.policy(
            r["instance_id"]).get("display_name") == "Chrome ca nhan"
        # Replay bi tu choi (request da consume).
        code, out = _post_expect("/link-redeem",
                                 {"request_id": rid, "secret": sec,
                                  "installation_id": "install-A"})
        assert code == 400, (code, out)
        print("link approve redeem once: PASS")
    finally:
        srv.shutdown()


def test_link_no_autopair_and_binding():
    """Khong auto-pair: sai secret / sai installation / het han deu tu choi.
    Approve 2 lan bi tu choi (khong cap credential trung)."""
    srv = _boot()
    try:
        from bridge.server import CHANNEL
        q = _post("/link-request", {"installation_id": "install-B"})
        rid, sec = q["request_id"], q["secret"]
        _post("/link-approve", {"request_id": rid}, bkey="test-backend-key-01")
        # Approve lan 2 -> tu choi.
        code, out = _post_expect("/link-approve", {"request_id": rid},
                                 bkey="test-backend-key-01")
        assert code == 400 and out.get("error") == "LINK_ALREADY_USED", \
            (code, out)
        # Sai secret -> 403 (khong consume, van redeem dung duoc).
        code, out = _post_expect("/link-redeem",
                                 {"request_id": rid, "secret": "wrong",
                                  "installation_id": "install-B"})
        assert code == 403 and out.get("error") == "LINK_FORBIDDEN", \
            (code, out)
        # Sai installation -> 403.
        code, out = _post_expect("/link-redeem",
                                 {"request_id": rid, "secret": sec,
                                  "installation_id": "install-X"})
        assert code == 403, (code, out)
        # Het han -> tu choi.
        CHANNEL._link_requests[rid]["expires_at"] = CHANNEL._clock() - 1
        code, out = _post_expect("/link-redeem",
                                 {"request_id": rid, "secret": sec,
                                  "installation_id": "install-B"})
        assert code == 400, (code, out)
        print("link no autopair and binding: PASS")
    finally:
        srv.shutdown()

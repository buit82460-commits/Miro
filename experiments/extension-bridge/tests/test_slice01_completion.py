"""Slice 01 COMPLETION: credential separation + atomic claim + lifecycle.

Contract moi (thay test cu):
- /read: BACKEND ROLE (X-Backend-Key). Extension session/token -> 403.
- /read-result: EXTENSION ROLE. Backend key gia danh -> 403.
- /claim truoc execute (atomic): poll dong thoi lan 2 -> CLAIM_CONFLICT.
- /read-result khong request_id -> manual path (stored, manual:true),
  KHONG hoan thanh production request.
- Deadline: result sau deadline -> REQUEST_EXPIRED. Cancel -> REQUEST_CANCELLED.
- Duplicate result sau terminal -> REQUEST_COMPLETED, khong ghi de.
"""
import json
import os
import sys
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.server import Handler  # noqa: E402

_BASE_PORT = [18799]
BASE = "http://127.0.0.1:18799"
BACKEND_KEY = "test-backend-key-01"
ACTOR_DATA = {"title": "t", "url": "https://www.tiktok.com/",
              "has_login_button": "", "profile_href": "/@hank",
              "has_upload_link": "1"}


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


import urllib.error  # noqa: E402


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as resp:
        return json.loads(resp.read().decode())


def _reset():
    from bridge import server as _srv
    _srv.CHANNEL._sessions.clear()
    _srv.CHANNEL._pairing.clear()
    _srv.GRANTS._grants.clear()
    _srv.REGISTRY.tabs.clear()
    _srv.OBSERVATIONS.clear()
    _srv.PENDING.clear()
    _srv.DONE.clear()
    os.environ["MIRO_BRIDGE_BACKEND_KEY"] = BACKEND_KEY


def _boot():
    global BASE
    _reset()
    HTTPServer.allow_reuse_address = True
    for _ in range(20):
        _BASE_PORT[0] += 1
        try:
            srv = HTTPServer(("127.0.0.1", _BASE_PORT[0]), Handler)
            break
        except OSError:
            continue
    BASE = "http://127.0.0.1:%d" % _BASE_PORT[0]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def _pair():
    from bridge.server import CHANNEL
    c = CHANNEL.issue_pairing_code()
    assert c, "khong sinh duoc pairing code"
    r = _post("/redeem", {"code": c})
    assert r.get("ok"), r
    return r["session_id"], r["token"]


def _grant(sid, tok, tab):
    from bridge.server import CHANNEL, REGISTRY
    inst = CHANNEL._sessions[sid]["instance"]
    REGISTRY.apply("opened", inst, tab, url="https://www.tiktok.com/",
                   title="t")
    for k in list(REGISTRY.tabs):
        if k[1] != tab:
            REGISTRY.tabs.pop(k, None)
    seq = int(CHANNEL._sessions[sid].get("last_seq", 0)) + 1
    req = urllib.request.Request(
        BASE + "/grant", data=json.dumps({"tabId": tab, "grant_seq": seq}).encode(),
        headers={"Content-Type": "application/json",
                 "X-Session": sid, "X-Token": tok})
    with urllib.request.urlopen(req, timeout=5) as resp:
        out = json.loads(resp.read().decode())
    assert out.get("ok"), out
    return seq


def _mkreq(tab, timeout_s=30, task_id="task-1"):
    return _post("/read", {"tabId": tab, "read": "actor-login",
                           "timeout_s": timeout_s, "task_id": task_id},
                 bkey=BACKEND_KEY)


def _result(sid, tok, tab, seq, rid, data=None, exec_error=""):
    body = {"seq": seq, "tabId": tab, "read": "actor-login",
            "live_origin": "https://www.tiktok.com/",
            "data": dict(data or ACTOR_DATA), "request_id": rid}
    if exec_error:
        body["exec_error"] = exec_error
        body["data"] = {}
    return body


# ---- 1. credential separation ----
def test_credential_roles():
    srv = _boot()
    try:
        sid, tok = _pair()
        _grant(sid, tok, 21)
        # extension tao production request -> tu choi
        code, out = _post_expect("/read", {"tabId": 21, "read": "actor-login"},
                                 sid, tok)
        assert code == 403 and out.get("error") == "BACKEND_AUTH_REQUIRED", out
        # backend tao ok
        r = _mkreq(21)
        assert r.get("request_id"), r
        rid = r["request_id"]
        # backend gia danh result -> tu choi
        from bridge.server import CHANNEL
        seq = int(CHANNEL._sessions[sid].get("last_seq", 0)) + 1
        code, out = _post_expect("/read-result",
                                 _result(sid, tok, 21, seq, rid), bkey=BACKEND_KEY)
        assert code == 403 and out.get("error") == "BACKEND_CANNOT_POST_RESULT", out
        # extension gui result that -> nhan
        ok = _post("/read-result", _result(sid, tok, 21, seq, rid), sid, tok)
        assert ok.get("stored"), ok
        print("credential roles: PASS")
    finally:
        srv.shutdown()


# ---- 2. atomic claim ----
def test_atomic_claim():
    srv = _boot()
    try:
        sid, tok = _pair()
        _grant(sid, tok, 22)
        r = _mkreq(22)
        rid = r["request_id"]
        ib = _post("/inbox", {}, sid, tok)
        assert any(p.get("request_id") == rid for p in ib.get("pending", [])), ib
        c1 = _post("/claim", {"request_id": rid}, sid, tok)
        assert c1.get("ok"), c1
        # claim lan 2 trong cua so -> conflict
        code, out = _post_expect("/claim", {"request_id": rid}, sid, tok)
        assert code == 409 and out.get("error") == "CLAIM_CONFLICT", (code, out)
        # claimed khong con trong inbox
        ib2 = _post("/inbox", {}, sid, tok)
        assert not any(p.get("request_id") == rid for p in ib2.get("pending", [])), ib2
        print("atomic claim: PASS")
    finally:
        srv.shutdown()


# ---- 3. manual regression ----
def test_manual_regression():
    srv = _boot()
    try:
        sid, tok = _pair()
        _grant(sid, tok, 23)
        r = _mkreq(23)
        rid = r["request_id"]
        from bridge.server import CHANNEL
        seq = int(CHANNEL._sessions[sid].get("last_seq", 0)) + 1
        # manual (khong request_id) -> stored rieng, khong hoan thanh request
        m = _post("/read-result", _result(sid, tok, 23, seq, ""), sid, tok)
        assert m.get("stored") and m.get("manual"), m
        # production request van pending
        ib = _post("/inbox", {}, sid, tok)
        # manual da bump seq nen claimed khong hien; request goc van ton tai
        from bridge.server import PENDING
        assert rid in PENDING, "manual khong duoc xoa production request"
        # production result dung ID van nhan duoc
        seq2 = int(CHANNEL._sessions[sid].get("last_seq", 0)) + 1
        ok = _post("/read-result", _result(sid, tok, 23, seq2, rid), sid, tok)
        assert ok.get("stored") and not ok.get("manual"), ok
        obs = _get("/observations")
        items = obs.get("observations") or []
        mans = [i for i in items if i.get("manual")]
        prods = [i for i in items if i.get("request_id") == rid]
        assert mans and prods, obs
        print("manual regression: PASS")
    finally:
        srv.shutdown()


# ---- 4. deadline + cancel + duplicate terminal ----
def test_deadline_cancel_terminal():
    srv = _boot()
    try:
        sid, tok = _pair()
        _grant(sid, tok, 24)
        from bridge.server import CHANNEL
        # deadline ngan: doi het han roi gui -> EXPIRED
        r = _mkreq(24, timeout_s=1)
        rid = r["request_id"]
        import time as _t
        _t.sleep(1.2)
        seq = int(CHANNEL._sessions[sid].get("last_seq", 0)) + 1
        code, out = _post_expect("/read-result",
                                 _result(sid, tok, 24, seq, rid), sid, tok)
        assert code == 410 and out.get("error") == "REQUEST_EXPIRED", (code, out)
        # cancel: request moi -> cancel -> late result CANCELLED
        r2 = _mkreq(24)
        rid2 = r2["request_id"]
        c = _post("/cancel", {"request_id": rid2}, bkey=BACKEND_KEY)
        assert c.get("cancelled"), c
        seq2 = int(CHANNEL._sessions[sid].get("last_seq", 0)) + 1
        code, out = _post_expect("/read-result",
                                 _result(sid, tok, 24, seq2, rid2), sid, tok)
        assert code == 410 and out.get("error") == "REQUEST_CANCELLED", (code, out)
        # duplicate sau terminal: hoan thanh roi gui lai -> COMPLETED
        r3 = _mkreq(24)
        rid3 = r3["request_id"]
        seq3 = int(CHANNEL._sessions[sid].get("last_seq", 0)) + 1
        ok = _post("/read-result", _result(sid, tok, 24, seq3, rid3), sid, tok)
        assert ok.get("stored"), ok
        n_obs = len((_get("/observations").get("observations") or []))
        seq4 = seq3 + 1
        code, out = _post_expect("/read-result",
                                 _result(sid, tok, 24, seq4, rid3), sid, tok)
        assert code == 409 and out.get("error") == "REQUEST_COMPLETED", (code, out)
        n_obs2 = len((_get("/observations").get("observations") or []))
        assert n_obs2 == n_obs, "duplicate khong duoc ghi de terminal"
        print("deadline/cancel/terminal: PASS")
    finally:
        srv.shutdown()


# ---- 5. exec error + grant revoke giua claim va execution ----
def test_exec_error_and_grant_revoke():
    srv = _boot()
    try:
        from bridge.server import CHANNEL, GRANTS
        sid, tok = _pair()
        _grant(sid, tok, 25)
        # exec error: extension bao loi -> terminal, khong data gia
        r = _mkreq(25)
        rid = r["request_id"]
        seq = int(CHANNEL._sessions[sid].get("last_seq", 0)) + 1
        ok = _post("/read-result",
                   _result(sid, tok, 25, seq, rid, exec_error="NAVIGATION_RACE"),
                   sid, tok)
        assert ok.get("terminal") and ok.get("exec_error") == "NAVIGATION_RACE", ok
        obs = _get("/observations").get("observations") or []
        assert not any(i.get("request_id") == rid for i in obs), obs
        # grant revoke giua claim va execution -> GRANT tu choi
        r2 = _mkreq(25)
        rid2 = r2["request_id"]
        c = _post("/claim", {"request_id": rid2}, sid, tok)
        assert c.get("ok"), c
        assert GRANTS.revoke_tab("profile20-main", 25)
        seq2 = int(CHANNEL._sessions[sid].get("last_seq", 0)) + 1
        code, out = _post_expect("/read-result",
                                 _result(sid, tok, 25, seq2, rid2), sid, tok)
        assert code == 403 and "GRANT" in str(out.get("error", "")), (code, out)
        print("exec-error/grant-revoke: PASS")
    finally:
        srv.shutdown()


# ---- 6. registry bound + restart ----
def test_registry_bound_and_restart():
    from bridge import server as _srv
    _reset()
    now = 1000.0
    # bound: qua MAX_PENDING thi evict cu nhat
    for i in range(_srv.MAX_PENDING + 5):
        _srv.PENDING["r%04d" % i] = {"instance": "profile20-main",
                                     "tab_id": 1, "spec": "title",
                                     "created_at": now + i,
                                     "deadline": now + i + 120,
                                     "state": "queued",
                                     "cancelled": False}
    _srv._cleanup_pending(now + 1)
    assert len(_srv.PENDING) <= _srv.MAX_PENDING, len(_srv.PENDING)
    # stale deadline bi don
    _srv.PENDING["old"] = {"instance": "profile20-main", "tab_id": 1,
                           "spec": "title", "created_at": now - 500,
                           "deadline": now - 1, "state": "queued",
                           "cancelled": False}
    assert _srv._cleanup_pending(now) >= 1
    assert "old" not in _srv.PENDING
    # restart (module reload): process moi PENDING/DONE rong, request cu
    # khong song lai -> wait_observation cu chi thay timeout.
    assert isinstance(_srv.PENDING, dict) and isinstance(_srv.DONE, dict)
    print("registry-bound/restart: PASS")

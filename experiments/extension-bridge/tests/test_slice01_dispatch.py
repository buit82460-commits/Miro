"""Slice 01: Bridge dispatch (inbox) + request correlation + negative control.

- /read sinh request_id, dua vao PENDING (inbox).
- /inbox tra lenh cho cho extension da paired.
- /read-result bat buoc request_id khop: sai/thieu -> REQUEST_ID_MISMATCH,
  observation cu (popup thu cong) khong duoc nhan lam ket qua dispatch.
"""
import json
import sys
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge import channel as _ch  # noqa: E402
from bridge import grants as _gr  # noqa: E402
from bridge import importer as _im  # noqa: E402
from bridge import registry as _reg  # noqa: E402
from bridge.server import Handler  # noqa: E402

BASE = "http://127.0.0.1:18799"


def _post(path, body, sid="", tok="", bkey=""):
    headers = {"Content-Type": "application/json",
               "X-Session": sid, "X-Token": tok}
    if bkey:
        headers["X-Backend-Key"] = bkey
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body or {}).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def _get(path, sid="", tok="", bkey=""):
    headers = {}
    if bkey:
        headers["X-Backend-Key"] = bkey
    elif sid or tok:
        headers["X-Session"] = sid
        headers["X-Token"] = tok
    else:
        headers["X-Backend-Key"] = "test-backend-key-01"
    req = urllib.request.Request(BASE + path, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def _reset():
    import os
    os.environ["MIRO_BRIDGE_BACKEND_KEY"] = "test-backend-key-01"
    from bridge.server import CHANNEL, GRANTS, REGISTRY, OBSERVATIONS, PENDING, DONE, CANCELLED
    CHANNEL._sessions.clear()
    CHANNEL._pairing.clear()
    CHANNEL._devices.clear()
    CHANNEL._policies.clear()
    CHANNEL._redeem_fails.clear()
    GRANTS._grants.clear()
    try:
        GRANTS._used_grant_seq.clear()
    except AttributeError:
        pass
    REGISTRY.tabs.clear()
    OBSERVATIONS.clear()
    PENDING.clear()
    DONE.clear()
    CANCELLED.clear()


def _boot():
    _reset()
    srv = HTTPServer(("127.0.0.1", 18799), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def _pair():
    code = Handler.__dict__ and None
    # issue pairing truc tiep qua channel (khong qua HTTP de tranh log)
    from bridge.server import CHANNEL
    c = CHANNEL.issue_pairing_code()
    assert c, "khong sinh duoc pairing code"
    r = _post("/redeem", {"code": c})
    assert r.get("ok"), r
    assert r.get("instance_id"), r
    return r["session_id"], r["token"], r["instance_id"]


def _grant(sid, tok, tab):
    from bridge.server import CHANNEL, GRANTS, REGISTRY
    inst = CHANNEL._sessions[sid]["instance"]
    REGISTRY.apply("opened", inst, tab, url="https://www.tiktok.com/",
                   title="t")
    for k in list(REGISTRY.tabs):
        if k[1] != tab:
            REGISTRY.tabs.pop(k, None)
    # grant_seq don dieu: doc seq hien tai roi +1
    seq = int(CHANNEL._sessions[sid].get("last_seq", 0)) + 1
    # registry da co tab -> /grant thanh cong
    req = urllib.request.Request(
        BASE + "/grant", data=json.dumps({"tabId": tab, "grant_seq": seq}).encode(),
        headers={"Content-Type": "application/json",
                 "X-Session": sid, "X-Token": tok})
    with urllib.request.urlopen(req, timeout=5) as resp:
        out = json.loads(resp.read().decode())
    assert out.get("ok"), out
    return seq


def test_slice01_read_returns_request_id_and_inbox():
    srv = _boot()
    try:
        sid, tok, inst = _pair()
        _grant(sid, tok, 11)
        r = _post("/read", {"tabId": 11, "read": "actor-login",
                            "instance": inst},
                  bkey="test-backend-key-01")
        assert r.get("status") == "AUTHORIZED", r
        assert r.get("request_id"), r
        ib = _post("/inbox", {}, sid, tok)
        assert ib.get("ok"), ib
        pend = ib.get("pending") or []
        assert any(p.get("request_id") == r["request_id"]
                   and p.get("spec") == "actor-login" for p in pend), pend
        print("Slice01 inbox dispatch: PASS")
    finally:
        srv.shutdown()


def test_slice01_read_result_requires_request_id():
    srv = _boot()
    try:
        sid, tok, inst = _pair()
        _grant(sid, tok, 12)
        r = _post("/read", {"tabId": 12, "read": "actor-login",
                            "instance": inst},
                  bkey="test-backend-key-01")
        rid = r.get("request_id")
        assert rid, r
        from bridge.server import CHANNEL
        seq = int(CHANNEL._sessions[sid].get("last_seq", 0)) + 1
        bad = {"seq": seq, "tabId": 12, "read": "actor-login",
               "live_origin": "https://www.tiktok.com/",
               "data": {"title": "t", "url": "https://www.tiktok.com/",
                        "has_login_button": "", "profile_href": "/@hank",
                        "has_upload_link": "1"}}
        # thieu request_id -> MANUAL PATH (contract COMPLETION):
        # stored rieng manual:true, KHONG hoan thanh production request.
        m = _post("/read-result", bad, sid, tok)
        assert m.get("stored") and m.get("manual"), m
        from bridge.server import PENDING as _PEND
        assert rid in _PEND, "manual khong duoc xoa production request"
        # sai request_id format -> tu choi
        bad2 = dict(bad, request_id="nope" * 4)
        try:
            _post("/read-result", bad2, sid, tok)
            assert False, "sai request_id phai bi tu choi"
        except Exception as exc:
            assert "403" in str(exc) or "REQUEST_ID_MISMATCH" in str(exc), exc
        # dung request_id -> nhan (tinh lai seq sau manual bump)
        seq3 = int(CHANNEL._sessions[sid].get("last_seq", 0)) + 1
        good = dict(bad, seq=seq3, request_id=rid)
        ok = _post("/read-result", good, sid, tok)
        assert ok.get("ok") and ok.get("stored"), ok
        obs = _get("/observations")
        items = obs.get("observations") or []
        assert any(i.get("request_id") == rid for i in items), obs
        print("Slice01 correlation: PASS")
    finally:
        srv.shutdown()

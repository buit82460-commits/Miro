"""A3 — Evidence levels contract + negative security tests (Bridge/TikTok).

Contract de xuat (tuong thich, khong breaking change):
  OBSERVED      observation doc OK qua transport (untrusted, dung grant/tab/
                origin, tuoi <=300s, khong replay). Chi de doc-hieu, KHONG
                bao gio du dieu kien WRITE.
  ACTOR_CLAIMED observation actor-login DU 3 tin hieu tren cung DOM
                (has_login_button=="" + profile_href "/@" + has_upload_link=="1")
                + eye khop title. Moi la TUYEN BO mot nguon (single-DOM),
                CHUA du dieu kien WRITE.
  ACTOR_VERIFIED CLAIMED + nguon doc lap thu hai xac nhan cung handle
                (REA/Eye tren page that qua Gateway read_via_eye + verify_actor,
                khop eye ground-truth handle). HIEN CHUA CO cho TikTok qua
                Bridge (chi 1 kenh DOM) -> Bridge khong duoc tu gan VERIFIED.
  UNVERIFIED    thieu tin hieu / spec khong phai actor-login / actor rong.
                Fail-closed: khong WRITE.
  MISMATCH      bat ky khop nao rot (title/origin/actor/tab/stale/replay/
                revoke/navigation race) -> bo observation, khong tra du lieu cu.

Luat cung (khoa):
  1. CAM nang CLAIMED -> VERIFIED khi thieu nguon doc lap thu hai.
     Test hien tai trong test_evidence.py goi actor-login khop eye la
     "VERIFIED" — theo contract nay phai ha xuong CLAIMED (don nguon DOM);
     chi Gateway read_via_eye + verify_actor doc lap moi duoc gan VERIFIED.
     (Chi la proposal doi ten/nhan; khong sua evidence.py trong task nay.)
  2. CAM dung media-analysis (provenance "media-analysis") cho WRITE —
     Gateway check_evidence tu choi; chi rea-eye tuoi dung tab moi duoc.
  3. Provenance "rea-eye" duoc giu nguyen de khong breaking change; level
     la truong mo rong them (evidence["actor_level"]), mac dinh UNVERIFIED.

Negative cover trong file nay (8 nhom):
  forged actor / wrong tab / wrong URL-origin / stale >300s / replay seq /
  revoke / navigation race / eye-vs-bridge mismatch.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.bridge_reader import BridgeReadTransport  # noqa: E402
from bridge.evidence import build_evidence  # noqa: E402
from bridge.grants import GrantStore  # noqa: E402

ORIGIN = "https://www.tiktok.com/"
EVIL = "https://evil.example/"
INST = "profile20-main"
TAB = 408

LEVELS = ("OBSERVED", "ACTOR_CLAIMED", "ACTOR_VERIFIED",
          "UNVERIFIED", "MISMATCH")


def classify_evidence(*, transport_ok, verify_result, eye_matched,
                      second_source_ok=False):
    """Proposal classifier (tham khao, khong thay evidence.py).

    - transport fail / eye khong khop -> MISMATCH
    - spec thuong, khong claim actor -> OBSERVED
    - actor-login du 3 tin hieu + eye khop, chua co nguon 2 -> ACTOR_CLAIMED
    - + nguon doc lap thu hai khop cung handle -> ACTOR_VERIFIED
    - thieu tin hieu / actor rong -> UNVERIFIED
    """
    if not transport_ok or not eye_matched:
        return "MISMATCH"
    if verify_result is None:
        return "OBSERVED"
    if not isinstance(verify_result, dict) or not verify_result.get("ok"):
        return "UNVERIFIED"
    if second_source_ok:
        return "ACTOR_VERIFIED"
    return "ACTOR_CLAIMED"


class Clock:
    def __init__(self):
        self.t = 50000.0

    def __call__(self):
        return self.t


def _setup(clock=None):
    clk = clock or Clock()
    g = GrantStore(clock=clk)
    obs = {}
    t = BridgeReadTransport(g, obs, clock=clk)
    return t, clk, g, obs


def _grant_read(t, g, obs, clk, seq, spec="title", data=None, origin=ORIGIN):
    assert g.grant(INST, TAB, origin, seq)["ok"], f"grant seq {seq} fail"
    obs[(INST, TAB, seq)] = {
        "spec": spec, "live_origin": origin,
        "data": data if data is not None else {
            "title": "TikTok - Make Your Day", "url": origin},
        "untrusted": True, "observed_at": clk(),
    }


def _eye(handle="/@kemkhongta", title="TikTok - Make Your Day"):
    return {"url": ORIGIN, "title": title, "text": "For You preview",
            "profile_href": handle}


def _actor_login_data(handle="/@kemkhongta", login_btn="", upload="1"):
    return {"title": "TikTok - Make Your Day", "url": ORIGIN,
            "has_login_button": login_btn, "profile_href": handle,
            "has_upload_link": upload}


# 1. Forged actor: con nut Log in / thieu href / sai handle -> UNVERIFIED.
def test_a3_forged_actor():
    t, clk, g, obs = _setup()
    _grant_read(t, g, obs, clk, 1, spec="actor-login",
                data=_actor_login_data(login_btn="1"))  # chua login
    r = t.read(browser_instance_id=INST, tab_id=TAB,
               live_origin=ORIGIN, seq=1)
    assert r["ok"], r
    a = t.verify_actor(r["observation"])
    assert a["error"] == "ACTOR_UNVERIFIED"
    assert "has_login_button" in a["missing"], a
    assert classify_evidence(transport_ok=True, verify_result=a,
                             eye_matched=True) == "UNVERIFIED"

    _grant_read(t, g, obs, clk, 2, spec="actor-login",
                data=_actor_login_data(handle=""))  # caption thay href
    r = t.read(browser_instance_id=INST, tab_id=TAB,
               live_origin=ORIGIN, seq=2)
    a = t.verify_actor(r["observation"])
    assert a["error"] == "ACTOR_UNVERIFIED"
    assert "profile_href" in a["missing"], a

    # Actor khong khop handle observation -> build_evidence tu choi.
    _grant_read(t, g, obs, clk, 3, spec="actor-login",
                data=_actor_login_data())
    r = t.read(browser_instance_id=INST, tab_id=TAB,
               live_origin=ORIGIN, seq=3)
    a = t.verify_actor(r["observation"])
    assert a == {"ok": True, "actor": "@kemkhongta"}, a
    ev = build_evidence(observation=r["observation"],
                        eye_record=_eye(handle="/@kemkhongta"),
                        instance_id=INST, tab_id=TAB, actor="@doi-gia-mao")
    assert ev["error"] == "ACTOR_UNVERIFIED", ev
    print("A3 forged actor (fake-login/thieu-href/sai-handle): PASS")


# 2. Wrong tab: grant tab A khong doc duoc tab B.
def test_a3_wrong_tab():
    t, clk, g, obs = _setup()
    _grant_read(t, g, obs, clk, 1)
    r = t.read(browser_instance_id=INST, tab_id=999,
               live_origin=ORIGIN, seq=1)
    assert r["error"] == "GRANT_REQUIRED", r
    print("A3 wrong tab (cross-tab GRANT_REQUIRED): PASS")


# 3. Wrong URL/origin: origin la -> ORIGIN_MISMATCH + grant bi thu hoi.
def test_a3_wrong_url_origin():
    t, clk, g, obs = _setup()
    _grant_read(t, g, obs, clk, 1)
    r = t.read(browser_instance_id=INST, tab_id=TAB,
               live_origin=EVIL, seq=1)
    assert r["error"] == "ORIGIN_MISMATCH", r
    # Grant da bi thu hoi sau mismatch -> doc lai origin that cung rot.
    r = t.read(browser_instance_id=INST, tab_id=TAB,
               live_origin=ORIGIN, seq=1)
    assert r["error"] == "GRANT_REQUIRED", r
    # Eye-vs-bridge: observation origin la khop eye that -> bo.
    ev = build_evidence(
        observation={"untrusted": True, "live_origin": EVIL,
                     "data": {"title": "TikTok - Make Your Day"}},
        eye_record=_eye(), instance_id=INST, tab_id=TAB,
        actor="@kemkhongta")
    assert ev["error"] == "ORIGIN_MISMATCH", ev
    print("A3 wrong URL/origin (mismatch + revoke): PASS")


# 4. Stale >300s: observation cu + evidence cu deu bi tu choi.
def test_a3_stale_over_300s():
    t, clk, g, obs = _setup()
    _grant_read(t, g, obs, clk, 1)
    obs[(INST, TAB, 1)]["observed_at"] = clk() - 400
    # Grant TTL 120s cung het -> cap grant moi giu observation cu.
    assert g.grant(INST, TAB, ORIGIN, 2)["ok"]
    obs[(INST, TAB, 2)] = dict(obs[(INST, TAB, 1)])
    r = t.read(browser_instance_id=INST, tab_id=TAB,
               live_origin=ORIGIN, seq=2)
    assert r["error"] == "EVIDENCE_STALE", r
    ev = build_evidence(
        observation={"untrusted": True, "live_origin": ORIGIN,
                     "data": {"title": "TikTok - Make Your Day"}},
        eye_record=_eye(), instance_id=INST, tab_id=TAB,
        actor="@kemkhongta", observed_at=time.time() - 400)
    assert ev["error"] == "EVIDENCE_STALE", ev
    print("A3 stale >300s (transport + evidence): PASS")


# 5. Replay seq: doc lai seq cu / xin grant lai seq cu deu rot.
def test_a3_replay_seq():
    t, clk, g, obs = _setup()
    _grant_read(t, g, obs, clk, 1)
    r = t.read(browser_instance_id=INST, tab_id=TAB,
               live_origin=ORIGIN, seq=1)
    assert r["ok"], r
    r = t.read(browser_instance_id=INST, tab_id=TAB,
               live_origin=ORIGIN, seq=1)
    assert r["error"] == "OBSERVATION_REPLAY", r
    assert classify_evidence(transport_ok=False, verify_result=None,
                             eye_matched=False) == "MISMATCH"
    assert g.grant(INST, TAB, ORIGIN, 1)["error"] == "GRANT_REPLAY"
    print("A3 replay seq (observation + grant): PASS")


# 6. Revoke: thu hoi tab / instance -> doc rot.
def test_a3_revoke():
    t, clk, g, obs = _setup()
    _grant_read(t, g, obs, clk, 1)
    assert g.revoke_tab(INST, TAB) is True
    r = t.read(browser_instance_id=INST, tab_id=TAB,
               live_origin=ORIGIN, seq=1)
    assert r["error"] == "GRANT_REQUIRED", r
    _grant_read(t, g, obs, clk, 2)
    assert g.revoke_instance(INST) >= 1
    r = t.read(browser_instance_id=INST, tab_id=TAB,
               live_origin=ORIGIN, seq=2)
    assert r["error"] == "GRANT_REQUIRED", r
    print("A3 revoke (tab + instance): PASS")


# 7. Navigation race: tab navigate khac origin giua chung -> grant vo hieu.
def test_a3_navigation_race():
    t, clk, g, obs = _setup()
    _grant_read(t, g, obs, clk, 1)
    # Tab navigate sang origin khac truoc khi doc -> rot + mat grant.
    r = t.read(browser_instance_id=INST, tab_id=TAB,
               live_origin="https://www.tiktok.com/@kemkhongta",
               seq=1)
    assert r["error"] == "ORIGIN_MISMATCH", r
    r = t.read(browser_instance_id=INST, tab_id=TAB,
               live_origin=ORIGIN, seq=1)
    assert r["error"] == "GRANT_REQUIRED", r
    print("A3 navigation race (origin doi giua chung): PASS")


# 8. Eye-vs-bridge mismatch: title gia mao / eye handle khac.
def test_a3_eye_bridge_mismatch():
    good_obs = {"untrusted": True, "live_origin": ORIGIN,
                "data": {"title": "TikTok - Make Your Day"}}
    # Poisoned title khong khop eye -> bo.
    ev = build_evidence(
        observation={"untrusted": True, "live_origin": ORIGIN,
                     "data": {"title": "TikTok - Verified Account"}},
        eye_record=_eye(), instance_id=INST, tab_id=TAB,
        actor="@kemkhongta")
    assert ev["error"] == "TITLE_MISMATCH", ev
    # Observation gia vo tin cay -> bo.
    ev = build_evidence(observation=dict(good_obs, untrusted=False),
                        eye_record=_eye(), instance_id=INST, tab_id=TAB,
                        actor="@kemkhongta")
    assert ev["error"] == "OBSERVATION_MUST_BE_UNTRUSTED", ev
    # Actor-login: eye thay handle khac -> ACTOR_MISMATCH.
    obs_login = {"untrusted": True, "live_origin": ORIGIN,
                 "spec": "actor-login", "data": _actor_login_data()}
    ev = build_evidence(observation=obs_login,
                        eye_record=_eye(handle="/@tai-khoan-khac"),
                        instance_id=INST, tab_id=TAB, actor="@kemkhongta")
    assert ev["error"] == "ACTOR_MISMATCH", ev
    assert classify_evidence(transport_ok=True, verify_result=None,
                             eye_matched=False) == "MISMATCH"
    print("A3 eye-vs-bridge mismatch (title/trust/actor): PASS")


# Contract levels: CLAIMED (don nguon) != VERIFIED (can nguon 2).
def test_a3_levels_claimed_vs_verified():
    assert set(LEVELS) == {"OBSERVED", "ACTOR_CLAIMED", "ACTOR_VERIFIED",
                           "UNVERIFIED", "MISMATCH"}
    # Spec thuong, khong claim actor -> OBSERVED (chi doc-hieu).
    assert classify_evidence(transport_ok=True, verify_result=None,
                             eye_matched=True) == "OBSERVED"
    # Du 3 tin hieu + eye khop nhung KHONG nguon 2 -> CLAIMED, khong WRITE.
    assert classify_evidence(
        transport_ok=True, verify_result={"ok": True, "actor": "@kemkhongta"},
        eye_matched=True, second_source_ok=False) == "ACTOR_CLAIMED"
    # Cung du lieu + nguon doc lap thu hai khop -> VERIFIED.
    assert classify_evidence(
        transport_ok=True, verify_result={"ok": True, "actor": "@kemkhongta"},
        eye_matched=True, second_source_ok=True) == "ACTOR_VERIFIED"
    # Cam nang CLAIMED -> VERIFIED khi thieu nguon 2 (Bridge TikTok hien
    # tai chi co 1 kenh DOM -> mai la CLAIMED, khong tu nhan VERIFIED).
    print("A3 levels (OBSERVED/CLAIMED!=VERIFIED/UNVERIFIED/MISMATCH): PASS")


if __name__ == "__main__":
    test_a3_forged_actor()
    test_a3_wrong_tab()
    test_a3_wrong_url_origin()
    test_a3_stale_over_300s()
    test_a3_replay_seq()
    test_a3_revoke()
    test_a3_navigation_race()
    test_a3_eye_bridge_mismatch()
    test_a3_levels_claimed_vs_verified()

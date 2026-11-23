"""A4 integration harness: E2E fixtures + Evidence level classification.

Ownership A4 (Verification): fixture + harness only, KHONG sua production
logic. Muc dich: mot noi duy nhat dinh nghia observation actor-login hop le
va cac bien the forged/stale/revoke/navigation/cross-tab, roi kiem thu theo
tung muc Evidence:

- OBSERVED:      transport.read ok (observation untrusted, da grant, fresh).
- ACTOR_CLAIMED: transport.verify_actor ok -> handle claimed (chua eye).
- UNVERIFIED:    actor khong chung minh duoc (forged/thieu tin hieu/stale).
- MISMATCH:      grant/origin/eye khong khop (revoke/navigation/cross-tab,
                 replay, title/actor mismatch) -> fail-closed.

Map tu production errors sang level chi nam trong ham `classify` o day
(harness-side), khong cham vao bridge/*.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.bridge_reader import BridgeReadTransport  # noqa: E402
from bridge.evidence import build_evidence  # noqa: E402
from bridge.grants import GrantStore  # noqa: E402

B = "profile20-main"
TAB = 894
ORIGIN = "https://www.tiktok.com/"
EVIL = "https://evil.example/"
HANDLE = "@kemkhongta"


class Clock:
    def __init__(self):
        self.t = 50000.0

    def __call__(self):
        return self.t


def valid_actor_login_obs(clock, live_origin=ORIGIN, handle=HANDLE):
    """Fixture: observation actor-login hop le (3 tin hieu doc lap)."""
    href = "/" + handle  # "/@kemkhongta"
    return {"spec": "actor-login", "live_origin": live_origin,
            "data": {"title": "TikTok - Make Your Day",
                     "url": live_origin,
                     "has_login_button": "",
                     "profile_href": href,
                     "has_upload_link": "1"},
            "untrusted": True, "observed_at": clock()}


def matching_eye(handle=HANDLE):
    return {"url": ORIGIN, "title": "TikTok - Make Your Day",
            "text": "For You preview", "profile_href": "/" + handle}


def make_env():
    """Fixture: transport + grants + observations voi grant seq 1 san."""
    clk = Clock()
    g = GrantStore(clock=clk)
    obs = {}
    t = BridgeReadTransport(g, obs, clock=clk)
    assert g.grant(B, TAB, ORIGIN, 1)["ok"]
    obs[(B, TAB, 1)] = valid_actor_login_obs(clk)
    return t, clk, g, obs


def grant_next(t, clk, seq):
    """Cap grant moi (het han/revoke xong cap lai) + observation moi."""
    assert t._grants.grant(B, TAB, ORIGIN, seq)["ok"]
    t._observations[(B, TAB, seq)] = valid_actor_login_obs(clk)
    return seq


# --- Harness-side classification (khong phai production logic) ---

def classify(*, transport_result=None, actor_result=None,
             evidence_result=None):
    """Map ket qua transport/actor/evidence -> 1 trong 4 muc Evidence."""
    tr = transport_result or {}
    if not tr.get("ok"):
        err = tr.get("error", "")
        if err in ("EVIDENCE_STALE", "ACTOR_UNVERIFIED",
                    "OBSERVATION_MUST_BE_UNTRUSTED"):
            return "UNVERIFIED"
        return "MISMATCH"  # GRANT_REQUIRED/EXPIRED, ORIGIN_MISMATCH,
        # OBSERVATION_REPLAY/NOT_FOUND, TAB/SEQ_INVALID, ...
    if evidence_result is not None:
        if evidence_result.get("ok"):
            return "VERIFIED-BY-EYE"
        err = evidence_result.get("error", "")
        if err in ("ACTOR_UNVERIFIED", "EVIDENCE_STALE",
                    "OBSERVED_AT_INVALID"):
            return "UNVERIFIED"
        return "MISMATCH"  # TITLE/ACTOR/ORIGIN_MISMATCH, ...
    if actor_result is not None:
        if actor_result.get("ok"):
            return "ACTOR_CLAIMED"
        return "UNVERIFIED"
    return "OBSERVED"


# --- Level: OBSERVED ---

def test_level_observed_valid_actor_login():
    t, clk, g, obs = make_env()
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=1)
    assert r["ok"], r
    assert r["observation"]["untrusted"] is True
    assert classify(transport_result=r) == "OBSERVED"
    print("A4 OBSERVED (actor-login hop le, read ok): PASS")


# --- Level: ACTOR_CLAIMED ---

def test_level_actor_claimed_valid_handle():
    t, clk, g, obs = make_env()
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=1)
    assert r["ok"], r
    a = t.verify_actor(r["observation"])
    assert a == {"ok": True, "actor": HANDLE}, a
    assert classify(transport_result=r, actor_result=a) == "ACTOR_CLAIMED"
    # Eye khop -> VERIFIED-BY-EYE (muc dich cuoi, can kenh doc lap).
    ev = build_evidence(observation=r["observation"],
                        eye_record=matching_eye(),
                        instance_id=B, tab_id=TAB, actor=a["actor"])
    assert ev["ok"] and ev["evidence"]["provenance"] == "rea-eye", ev
    assert classify(transport_result=r, actor_result=a,
                    evidence_result=ev) == "VERIFIED-BY-EYE"
    print("A4 ACTOR_CLAIMED -> VERIFIED-BY-EYE (eye khop): PASS")


# --- Level: UNVERIFIED (forged / thieu / stale) ---

def test_level_unverified_forged_login_button():
    t, clk, g, obs = make_env()
    grant_next(t, clk, 2)
    forged = valid_actor_login_obs(clk)
    forged["data"] = dict(forged["data"], has_login_button="1")  # chua login
    t._observations[(B, TAB, 2)] = forged
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=2)
    assert r["ok"], r
    a = t.verify_actor(r["observation"])
    assert a["error"] == "ACTOR_UNVERIFIED" and \
        "has_login_button" in a["missing"], a
    assert classify(transport_result=r, actor_result=a) == "UNVERIFIED"
    print("A4 UNVERIFIED (forged: con nut Log in): PASS")


def test_level_unverified_missing_profile_href():
    t, clk, g, obs = make_env()
    grant_next(t, clk, 2)
    nohref = valid_actor_login_obs(clk)
    nohref["data"] = dict(nohref["data"], profile_href="")  # caption ko du
    t._observations[(B, TAB, 2)] = nohref
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=2)
    assert r["ok"], r
    a = t.verify_actor(r["observation"])
    assert a["error"] == "ACTOR_UNVERIFIED" and \
        "profile_href" in a["missing"], a
    assert classify(transport_result=r, actor_result=a) == "UNVERIFIED"
    print("A4 UNVERIFIED (thieu profile_href): PASS")


def test_level_unverified_missing_upload_link():
    t, clk, g, obs = make_env()
    grant_next(t, clk, 2)
    noupload = valid_actor_login_obs(clk)
    noupload["data"] = dict(noupload["data"], has_upload_link="")  # logged out
    t._observations[(B, TAB, 2)] = noupload
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=2)
    assert r["ok"], r
    a = t.verify_actor(r["observation"])
    assert a["error"] == "ACTOR_UNVERIFIED" and \
        "has_upload_link" in a["missing"], a
    assert classify(transport_result=r, actor_result=a) == "UNVERIFIED"
    print("A4 UNVERIFIED (thieu upload link): PASS")


def test_level_unverified_stale_observation():
    t, clk, g, obs = make_env()
    clk.t += 200  # grant seq 1 het han (TTL 120s) -> cap moi seq 2
    grant_next(t, clk, 2)
    stale = valid_actor_login_obs(clk)
    stale["observed_at"] = clk() - 400  # qua TTL 300s
    t._observations[(B, TAB, 2)] = stale
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=2)
    assert r["error"] == "EVIDENCE_STALE", r
    assert classify(transport_result=r) == "UNVERIFIED"
    print("A4 UNVERIFIED (stale >300s): PASS")


def test_level_unverified_title_only_never_actor():
    t, clk, g, obs = make_env()
    t._observations[(B, TAB, 1)] = {
        "spec": "title", "live_origin": ORIGIN,
        "data": {"title": "TikTok - Make Your Day", "url": ORIGIN},
        "untrusted": True, "observed_at": clk()}
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=1)
    assert r["ok"], r
    a = t.verify_actor(r["observation"])
    assert a["error"] == "ACTOR_UNVERIFIED", a
    assert classify(transport_result=r, actor_result=a) == "UNVERIFIED"
    print("A4 UNVERIFIED (title-only khong bao gio la actor): PASS")


# --- Level: MISMATCH (revoke / navigation / cross-tab / replay / eye) ---

def test_level_mismatch_revoke():
    t, clk, g, obs = make_env()
    assert t._grants.revoke_tab(B, TAB) is True
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=1)
    assert r["error"] == "GRANT_REQUIRED", r
    assert classify(transport_result=r) == "MISMATCH"
    print("A4 MISMATCH (revoke -> GRANT_REQUIRED): PASS")


def test_level_mismatch_instance_revoke():
    t, clk, g, obs = make_env()
    assert t._grants.revoke_instance(B) >= 1
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=1)
    assert r["error"] == "GRANT_REQUIRED", r
    assert classify(transport_result=r) == "MISMATCH"
    print("A4 MISMATCH (revoke instance -> GRANT_REQUIRED): PASS")


def test_level_mismatch_navigation_evil_origin():
    t, clk, g, obs = make_env()
    # Navigation sang origin la: grant bi thu hoi ngay (B2).
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=EVIL, seq=1)
    assert r["error"] == "ORIGIN_MISMATCH", r
    r2 = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=1)
    assert r2["error"] == "GRANT_REQUIRED", r2  # da bi thu hoi
    assert classify(transport_result=r) == "MISMATCH"
    print("A4 MISMATCH (navigation evil origin -> thu hoi): PASS")


def test_level_mismatch_cross_tab():
    t, clk, g, obs = make_env()
    # Grant tab A khong doc duoc observation tab B (neu co).
    t._observations[(B, 999, 1)] = valid_actor_login_obs(clk)
    r = t.read(browser_instance_id=B, tab_id=999, live_origin=ORIGIN, seq=1)
    assert r["error"] == "GRANT_REQUIRED", r
    assert classify(transport_result=r) == "MISMATCH"
    print("A4 MISMATCH (cross-tab -> GRANT_REQUIRED): PASS")


def test_level_mismatch_replay_seq():
    t, clk, g, obs = make_env()
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=1)
    assert r["ok"], r
    r2 = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=1)
    assert r2["error"] == "OBSERVATION_REPLAY", r2
    assert classify(transport_result=r2) == "MISMATCH"
    print("A4 MISMATCH (replay seq -> tu choi): PASS")


def test_level_mismatch_eye_actor_handle():
    t, clk, g, obs = make_env()
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=1)
    assert r["ok"], r
    a = t.verify_actor(r["observation"])
    assert a["ok"], a
    # Eye thay handle khac (sai account) -> ACTOR_MISMATCH.
    ev = build_evidence(observation=r["observation"],
                        eye_record=matching_eye("@other"),
                        instance_id=B, tab_id=TAB, actor=a["actor"])
    assert ev["error"] == "ACTOR_MISMATCH", ev
    assert classify(transport_result=r, actor_result=a,
                    evidence_result=ev) == "MISMATCH"
    print("A4 MISMATCH (eye handle khac -> ACTOR_MISMATCH): PASS")


def test_level_mismatch_eye_title_poison():
    t, clk, g, obs = make_env()
    r = r_read(t)
    assert r["ok"], r
    poisoned = dict(r["observation"])
    poisoned = dict(poisoned, data={"title": "TikTok - Verified Account",
                                    "url": ORIGIN,
                                    "has_login_button": "",
                                    "profile_href": "/@kemkhongta",
                                    "has_upload_link": "1"})
    ev = build_evidence(observation=poisoned,
                        eye_record=matching_eye(),
                        instance_id=B, tab_id=TAB, actor=HANDLE)
    assert ev["error"] == "TITLE_MISMATCH", ev
    assert classify(transport_result={"ok": True}, actor_result={"ok": True},
                    evidence_result=ev) == "MISMATCH"
    print("A4 MISMATCH (title poisoning -> TITLE_MISMATCH): PASS")


def r_read(t):
    return t.read(browser_instance_id=B, tab_id=TAB,
                  live_origin=ORIGIN, seq=1)


def test_level_mismatch_evidence_must_stay_untrusted():
    t, clk, g, obs = make_env()
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=1)
    assert r["ok"], r
    fake_trusted = dict(r["observation"], untrusted=False)
    ev = build_evidence(observation=fake_trusted,
                        eye_record=matching_eye(),
                        instance_id=B, tab_id=TAB, actor=HANDLE)
    assert ev["error"] == "OBSERVATION_MUST_BE_UNTRUSTED", ev
    assert classify(transport_result={"ok": True}, actor_result={"ok": True},
                    evidence_result=ev) == "MISMATCH"
    print("A4 MISMATCH (vo tin cay -> tu choi): PASS")


def test_evidence_stale_at_build_time():
    t, clk, g, obs = make_env()
    r = t.read(browser_instance_id=B, tab_id=TAB, live_origin=ORIGIN, seq=1)
    assert r["ok"], r
    ev = build_evidence(observation=r["observation"],
                        eye_record=matching_eye(),
                        instance_id=B, tab_id=TAB, actor=HANDLE,
                        observed_at=time.time() - 400)
    assert ev["error"] == "EVIDENCE_STALE", ev
    assert classify(transport_result=r, actor_result={"ok": True},
                    evidence_result=ev) == "UNVERIFIED"
    print("A4 UNVERIFIED (evidence stale luc build): PASS")


if __name__ == "__main__":
    test_level_observed_valid_actor_login()
    test_level_actor_claimed_valid_handle()
    test_level_unverified_forged_login_button()
    test_level_unverified_missing_profile_href()
    test_level_unverified_missing_upload_link()
    test_level_unverified_stale_observation()
    test_level_unverified_title_only_never_actor()
    test_level_mismatch_revoke()
    test_level_mismatch_instance_revoke()
    test_level_mismatch_navigation_evil_origin()
    test_level_mismatch_cross_tab()
    test_level_mismatch_replay_seq()
    test_level_mismatch_eye_actor_handle()
    test_level_mismatch_eye_title_poison()
    test_level_mismatch_evidence_must_stay_untrusted()
    test_evidence_stale_at_build_time()

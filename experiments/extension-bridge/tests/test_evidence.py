"""Test Evidence pipeline: observation untrusted + eye + actor (Phien A)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.evidence import build_evidence  # noqa: E402

OBS = {"untrusted": True, "live_origin": "https://www.tiktok.com/",
       "data": {"title": "TikTok - Make Your Day"}}
EYE = {"url": "https://www.tiktok.com/",
       "title": "TikTok - Make Your Day", "text": "For You preview"}


def test_evidence_ok():
    r = build_evidence(observation=OBS, eye_record=EYE,
                       instance_id="profile20-main", tab_id=408,
                       actor="@miro_test")
    assert r["ok"] and r["evidence"]["provenance"] == "rea-eye", r
    assert r["evidence"]["actor"] == "@miro_test", r
    print("evidence khop eye+actor: PASS")


def test_evidence_negative():
    # Title gia mao (poisoning) khong khop eye -> bo.
    evil = dict(OBS, data={"title": "TikTok - Verified Account"})
    r = build_evidence(observation=evil, eye_record=EYE,
                       instance_id="profile20-main", tab_id=408,
                       actor="@miro_test")
    assert r["error"] == "TITLE_MISMATCH", r
    # Origin khac -> bo.
    evil2 = dict(OBS, live_origin="https://evil.example/")
    r = build_evidence(observation=evil2, eye_record=EYE,
                       instance_id="profile20-main", tab_id=408,
                       actor="@miro_test")
    assert r["error"] == "ORIGIN_MISMATCH", r
    # Chua xac minh actor (chi title) -> bo.
    r = build_evidence(observation=OBS, eye_record=EYE,
                       instance_id="profile20-main", tab_id=408, actor="")
    assert r["error"] == "ACTOR_UNVERIFIED", r
    # Observation gia vo tin cay -> bo.
    fake = dict(OBS, untrusted=False)
    r = build_evidence(observation=fake, eye_record=EYE,
                       instance_id="profile20-main", tab_id=408,
                       actor="@miro_test")
    assert r["error"] == "OBSERVATION_MUST_BE_UNTRUSTED", r
    print("evidence negative (poison/origin/actor/trust): PASS")


ACTOR_OBS = {"untrusted": True, "live_origin": "https://www.tiktok.com/",
             "spec": "actor-login",
             "data": {"title": "TikTok - Make Your Day",
                      "url": "https://www.tiktok.com/",
                      "has_login_button": "", "profile_href": "/@kemkhongta",
                      "has_upload_link": "1"}}
ACTOR_EYE = dict(EYE, profile_href="/@kemkhongta")


def test_evidence_actor_login():
    # Actor-login khop eye -> Evidence VERIFIED.
    r = build_evidence(observation=ACTOR_OBS, eye_record=ACTOR_EYE,
                       instance_id="profile20-main", tab_id=898,
                       actor="@kemkhongta")
    assert r["ok"] and r["evidence"]["actor"] == "@kemkhongta", r
    # Eye thay handle khac (sai account) -> ACTOR_MISMATCH.
    eye_other = dict(ACTOR_EYE, profile_href="/@other")
    r = build_evidence(observation=ACTOR_OBS, eye_record=eye_other,
                       instance_id="profile20-main", tab_id=898,
                       actor="@kemkhongta")
    assert r["error"] == "ACTOR_MISMATCH", r
    # Actor khong khop handle observation -> UNVERIFIED.
    r = build_evidence(observation=ACTOR_OBS, eye_record=ACTOR_EYE,
                       instance_id="profile20-main", tab_id=898,
                       actor="@other")
    assert r["error"] == "ACTOR_UNVERIFIED", r
    # Caption/comment thay cho profile_href -> UNVERIFIED (khong nhan).
    nohref = dict(ACTOR_OBS, data=dict(ACTOR_OBS["data"], profile_href=""))
    r = build_evidence(observation=nohref, eye_record=ACTOR_EYE,
                       instance_id="profile20-main", tab_id=898,
                       actor="@kemkhongta")
    assert r["error"] == "ACTOR_MISMATCH", r
    print("evidence actor-login (verified/mismatch/forged): PASS")


if __name__ == "__main__":
    test_evidence_ok()
    test_evidence_negative()
    test_evidence_actor_login()

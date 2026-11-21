"""Test comment/message/engage: TikTok port + stub UNSUPPORTED cac platform.

Offline (fake page/base), khong cham Chrome that. Port tiktok_engage_one.py:
guard trung (publication-engage + journal), daily cap, comment text tu
manifest/CLI (khong hard-code), never replay UNKNOWN.
"""
from __future__ import annotations


def _base(tmp_path):
    base = tmp_path / "engage"
    (base / "attempts").mkdir(parents=True, exist_ok=True)
    return base


def test_tiktok_describe_engage_ok_and_no_comment_text(tmp_path):
    from miro.adapters import tiktok
    base = _base(tmp_path)
    ok = tiktok.describe_engage("v123", ["like", "follow"], comment_text="")
    assert ok["actions"] == ["like", "follow"]
    assert ok["daily_caps"]["like"] == 20
    no = tiktok.describe_engage("v123", ["comment"], comment_text="  ")
    assert no["skipped"] == "NO_COMMENT_TEXT"


def test_tiktok_describe_engage_bad_action():
    from miro.adapters import tiktok
    import pytest
    with pytest.raises(ValueError):
        tiktok.describe_engage("v", ["spam"])


def test_tiktok_guard_engage_skip_and_journal(tmp_path):
    from miro.adapters import tiktok
    base = _base(tmp_path)
    jid = tiktok.engage_job_id("v1", "Profile20", "like") + ".json"
    assert tiktok.guard_engage(base, "v1", "Profile20", "like", jid) is None
    (base / "attempts" / jid).write_text("{}", encoding="utf-8")
    skip = tiktok.guard_engage(base, "v1", "Profile20", "like", jid)
    assert skip["skipped"] == "UNRECONCILED_ATTEMPT"
    tiktok.merge_engage(base, {"shortcode": "v1", "profile": "Profile20",
                               "action": "like", "status": "verified"})
    skip2 = tiktok.guard_engage(base, "v1", "Profile20", "like", "other.json")
    assert skip2["skipped"] == "ALREADY_IN_PUBLICATION"


def test_tiktok_daily_cap_counts_today_only(tmp_path):
    from miro.adapters import tiktok
    base = _base(tmp_path)
    jid = tiktok.engage_job_id("v9", "Profile20", "like") + ".json"
    (base / "attempts" / jid).write_text(
        '{"profile": "Profile20", "action": "like", "status": "verified"}',
        encoding="utf-8")
    assert tiktok.daily_engage_count(base, "Profile20", "like") >= 1
    assert tiktok.daily_engage_count(base, "Profile20", "follow") == 0


def test_live_engage_platform_khac_tra_unsupported():
    from miro.adapters.live import LivePage
    page = LivePage(object(), "threads", "@haodaojrk5")
    out = page.engage({"action": "like", "shortcode": "x"})
    assert out["error"] == "UNSUPPORTED_ENGAGE_THREADS"


def test_stub_comment_message_cac_platform():
    from miro.adapters import facebook, instagram, threads, youtube
    assert facebook.send_comment("u", "hi")["error"] == \
        "UNSUPPORTED_COMMENT_FACEBOOK"
    assert facebook.send_message("t", "hi")["error"] == \
        "UNSUPPORTED_MESSAGE_FACEBOOK"
    assert instagram.send_comment("u", "hi")["error"] == \
        "UNSUPPORTED_COMMENT_INSTAGRAM"
    assert instagram.send_message("t", "hi")["error"] == \
        "UNSUPPORTED_MESSAGE_INSTAGRAM"
    assert threads.send_comment("u", "hi")["error"] == \
        "UNSUPPORTED_COMMENT_THREADS"
    assert threads.send_message("t", "hi")["error"] == \
        "UNSUPPORTED_MESSAGE_THREADS"
    assert youtube.send_comment("vid", "hi")["error"] == \
        "UNSUPPORTED_COMMENT_YOUTUBE"

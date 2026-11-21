"""Test tinh nang bo sung 8 adapter (offline, khong cham mang/Chrome that)."""
from __future__ import annotations

import pytest

from miro.adapters import chatgpt as C
from miro.adapters import facebook as F
from miro.adapters import flow as FL
from miro.adapters import instagram as I
from miro.adapters import shopee as S
from miro.adapters import threads as T
from miro.adapters import tiktok as TT
from miro.adapters import youtube_api as Y


def test_threads_helpers():
    assert T.resolve_post_url("Df_K1qEe2R").endswith("/t/Df_K1qEe2R/")
    assert "threads.com" in T.resolve_post_url(
        "https://www.threads.com/t/Df_K1qEe2R/")
    with pytest.raises(ValueError):
        T.resolve_post_url("!!!")
    out = T.run_reconcile("s1", "alice", [])
    assert out["receipt"] == "UNKNOWN"
    hit = T.run_reconcile("s1", "alice", [{
        "author": "@alice", "tag": "#dub1", "url": "u", "post_id": "P",
        "has_video": False}])
    assert hit["receipt"] in ("VERIFIED", "UNKNOWN")


def test_facebook_helpers():
    assert F.canonical_reel_url("123") == "https://www.facebook.com/reel/123"
    assert F.verify_reel({}, "a", "cap")["verified"] is False
    assert F.reconcile_candidates(["1"], ["1", "2"]) == ["2"]
    cap = F.caption_for_item({"shortcode": "9", "title": "t",
                              "description": "d"})
    assert "#cat" in cap


def test_tiktok_helpers():
    assert TT.draft_job_id("x") == "tiktok-draft-x"
    probs = TT.check_preflight({"caption": "hi", "audience": "Everyone",
                                "ai_label": True, "avatar": "@a"}, "hi", "a")
    assert probs == []
    assert "CAPTION_MISMATCH" in TT.check_preflight({"caption": "x"}, "y", "a")
    assert TT.discover("hashtag", "cat")["kind"] == "hashtag"
    with pytest.raises(ValueError):
        TT.discover("nope")
    d = TT.run_draft({"shortcode": "d1", "title": "t", "description": "d",
                      "local_path": __file__})
    assert d["draft"] is True


def test_instagram_helpers():
    assert I.instagram_response_payload("for (;;);{\"a\":1}") == {"a": 1}
    ok = I.instagram_created_media({"media": {"owner_id": "1", "code": "C",
                                              "caption": "hello cap"}},
                                   "1", "hello")
    assert ok["verified"] is True and ok["url"].endswith("/reel/C/")
    assert I.instagram_created_media({"media": {"owner_id": "2"}},
                                     "1", "")["verified"] is False
    assert I.resolve_reel_url(
        "https://www.instagram.com/reel/AbC123/") == \
        "https://www.instagram.com/reel/AbC123/"
    with pytest.raises(ValueError):
        I.resolve_reel_url("https://www.instagram.com/user/reels/")
    assert I.save_draft()["error"] == "UNSUPPORTED_DRAFT"
    assert I.set_audience()["error"] == "UNSUPPORTED_AUDIENCE"
    assert I.edit_caption()["error"] == "UNSUPPORTED_CAPTION_EDIT"
    assert I.validate_item_pre_browser({"shortcode": "1"})  # no media -> problems


def test_youtube_helpers():
    assert Y.DEFAULT_CHANNEL == "UCrUkQHY9OUP-Z_5muDDR6Bg"
    with pytest.raises(Exception):
        Y.resolve_channel("no-such-channel-xyz")


def test_shopee_helpers():
    probs = S.validate_product({"shortcode": "1", "name": "",
                                "price": 0, "stock": 0})
    assert probs
    ok = S.validate_product({"shortcode": "2", "name": "sp", "price": 5,
                             "stock": 1})
    assert ok == []
    assert S.read_orders("a")["orders"] == "LIVE_ONLY"
    assert "shopee.vn" in S.research_product("u")["runtime"]


def test_chatgpt_helpers():
    assert C.resolve_conversation_url(
        "https://chatgpt.com/c/abc-123") == "https://chatgpt.com/c/abc-123"
    with pytest.raises(ValueError):
        C.resolve_conversation_url("!!!")
    rec = C.reply_record("hello", "u")
    assert rec["reply_chars"] == 5 and len(rec["reply_sha256"]) == 64
    assert C.extract_reply("prompt text\nreply here", "prompt text")
    assert C.read_conversation("https://chatgpt.com/c/abc-123")["transcript"] == \
        "LIVE_ONLY"


def test_flow_helpers():
    assert FL.resolve_video_url("abc123").startswith("https://flow.google.com/")
    with pytest.raises(ValueError):
        FL.resolve_video_url("!!!")
    assert FL.reconcile_one("abc123")["receipt"] == "UNKNOWN"
    assert FL.reconcile_one("abc123",
                            "https://flow.google.com/video/abc123")["verified"] is True
    assert FL.cheapest_settings()["runtime"] == "LIVE_ONLY"

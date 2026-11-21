"""Test luat cung REA-mat: moi platform/thao tac phai co eye collector;
tay (LivePage) khong duoc bam khi mat chua do. Offline (fake page)."""
from __future__ import annotations

import asyncio

import pytest

from miro import eye as E
from miro.adapters import live as L


class _Text:
    def __init__(self, text=""):
        self._text = text

    async def inner_text(self):
        return self._text

    async def get_attribute(self, _name):
        return ""


class _Loc:
    def __init__(self, page, text=""):
        self._page = page
        self._text = text
        self.first = self

    async def all(self):
        return []

    async def count(self):
        return 0

    async def wait_for(self, **_kw):
        return None

    async def click(self, **_kw):
        self._page.clicked.append(True)
        return None

    async def fill(self, _text):
        return None

    async def inner_text(self):
        return self._text

    async def get_attribute(self, _name):
        return ""


class _FakePage:
    def __init__(self, url="https://www.tiktok.com/@a/video/123"):
        self.url = url
        self.clicked: list[bool] = []

    def locator(self, sel):
        if "comment-post" in sel:
            return _Loc(self)
        return _Loc(self, "")


def test_eye_coverage_du_8_platform():
    assert set(E.EYE_COVERAGE) == {
        "threads", "facebook", "tiktok", "instagram", "youtube", "shopee",
        "chatgpt", "flow", "desktop"}
    assert len(E.EYE_COVERAGE["tiktok"]) >= 3  # comment + video + profile


def test_eye_tiktok_comment_records_empty_page():
    recs = asyncio.run(E.tiktok_comment_records(_FakePage(), "123"))
    assert isinstance(recs, list)


def test_eye_records_tung_platform():
    page = _FakePage("https://www.tiktok.com/@kemkhongta")
    prof = asyncio.run(E.tiktok_profile_record(page))
    assert prof["handle"] == "@kemkhongta"
    vid = asyncio.run(E.tiktok_video_record(
        _FakePage("https://www.tiktok.com/@a/video/7704133695866785044")))
    assert vid["post_id"] == "7704133695866785044"
    fb = asyncio.run(E.facebook_reel_record(_FakePage("https://fb.com/reel/1")))
    assert fb["url"].endswith("/reel/1")
    ig = asyncio.run(E.instagram_reel_record(
        _FakePage("https://www.instagram.com/reel/AbC123/")))
    assert ig["post_id"] == "AbC123"
    fl = asyncio.run(E.flow_video_record(_FakePage("https://flow.google.com/x")))
    assert fl["rendered"] is False
    cg = asyncio.run(E.chatgpt_conversation_record(_FakePage("https://c/x")))
    assert cg["turns"] == 0
    sp = asyncio.run(E.shopee_product_record(_FakePage("https://shopee.vn/x")))
    assert sp["url"].endswith("/x")
    yt = E.youtube_video_record({"id": "v1", "snippet": {"title": "t"},
                                 "status": {"privacyStatus": "public"}})
    assert yt["url"].endswith("v1") and yt["privacyStatus"] == "public"


def test_engage_comment_thieu_text_bao_loi_truoc_click():
    lp = L.LivePage(_FakePage(), "tiktok", "kemkhongta")
    with pytest.raises(Exception):
        lp.engage({"action": "comment", "url": "https://x",
                   "comment_text": "   "})


class _Btn:
    def __init__(self, page, sel=""):
        self._page = page
        self.first = self

    async def wait_for(self, **_kw):
        return None

    async def click(self, **_kw):
        self._page.clicked.append(True)
        return None

    async def is_enabled(self):
        return True

    async def inner_text(self):
        return "Post"

    async def is_visible(self):
        return True

    async def count(self):
        return 1

    async def scroll_into_view_if_needed(self, **_kw):
        return None

    async def all(self):
        return []


class _EyePage(_FakePage):
    def locator(self, sel):
        if "comment-post" in sel or "like-button" in sel:
            return _Btn(self, sel)
        return _Loc(self, "")

    async def title(self):
        return "t"

    async def wait_for_timeout(self, _ms):
        return None


def test_eye_moi_composer_ack_tab_desktop():
    page = _EyePage()
    comp = asyncio.run(E.composer_state(page, "threads"))
    assert isinstance(comp, dict) and "box" in comp
    ack = asyncio.run(E.ack_state(page, "threads"))
    assert ack["toast"] is False
    tab = asyncio.run(E.tab_state(page))
    assert "url" in tab and "text" in tab
    prof = asyncio.run(E.profile_path_record(page))
    assert "profile_path" in prof
    eng = asyncio.run(E.engage_records(page, "tiktok"))
    assert "buttons" in eng

    class _Ops:
        def list_windows(self, app=None):
            return {"ok": True, "windows": [{"title": "t", "window_id": 1}]}

        def find(self, wid, role=None, name=None):
            return {"ok": True, "matches": [{"id": 1}]}

    assert E.desktop_window_record(_Ops(), title_substr="t")["ok"] is True
    assert E.desktop_doc_record(_Ops(), 1, "d")["ok"] is True

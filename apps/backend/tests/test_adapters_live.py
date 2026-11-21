"""Live page factory cho ca 8 adapter — test import + smoke offline."""
from __future__ import annotations

import pytest

from miro.adapters.live import (
    ACK_HINTS, COMPOSER_OPEN, POST_BUTTON, TEXT_BOX, LivePage,
    fill_composer, make_live_page,
)
from miro.adapters.youtube_api import DEFAULT_CHANNEL


def test_tables_cover_8_platforms():
    for pid in ("threads", "facebook", "tiktok", "instagram",
                "shopee", "chatgpt", "flow"):
        assert pid in COMPOSER_OPEN or pid in ("facebook", "tiktok",
                                               "instagram")
        assert TEXT_BOX.get(pid)
    for pid in ("threads", "facebook", "tiktok", "instagram", "youtube",
                "shopee", "chatgpt", "flow"):
        assert ACK_HINTS.get(pid)
    assert POST_BUTTON["threads"]


def test_make_live_page_factory():
    page = make_live_page(object(), "threads", "haodaojrk5")
    assert isinstance(page, LivePage)
    assert page.platform == "threads"


def test_default_channel_constant():
    assert DEFAULT_CHANNEL == "UCrUkQHY9OUP-Z_5muDDR6Bg"


def test_fill_composer_fail_closed_no_box():
    import asyncio

    class Loc:
        def __init__(self, sel=""):
            self.sel = sel
            self.first = self

        async def wait_for(self, **kw):
            raise RuntimeError("no such element")

        async def click(self, **kw):
            raise RuntimeError("no such element")

        async def all(self):
            return []

    class FakePWPage:
        def locator(self, sel):
            return Loc(sel)

    async def _run():
        with pytest.raises(Exception):
            await fill_composer(FakePWPage(), "threads", "hello")

    asyncio.run(_run())

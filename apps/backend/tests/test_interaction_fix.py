"""Wire interaction_fix vao live.fill_composer.

Bang fix rut tu test live Profile 16 ngay 22-11 (TikTok/FB/IG comment):
- TikTok: click evaluate (JS), giu selector goc [data-e2e].
- Facebook: evaluate-click -> type -> Enter dispatch.
- Instagram: browser_click icon -> type -> JS Post x2 + verify nut bien mat.
"""
from __future__ import annotations

import asyncio

from miro.adapters import interaction_fix as F
from miro.adapters import live as L


def test_tables_cover_comment_platforms():
    for pid in ("tiktok", "facebook", "instagram"):
        assert pid in F.INTERACTION_FIX
        assert F.click_for(pid)
        assert F.post_for(pid)
        assert F.verify_for(pid)


def test_click_order_prefers_evaluate():
    assert F.CLICK_ORDER[0] == "evaluate"
    assert F.click_for("tiktok") == "evaluate"
    assert F.post_for("facebook") == "enter-dispatch"
    assert F.verify_for("instagram") == "post-button-gone-plus-list-contains"


def test_fill_composer_uses_fix_selectors_when_no_composer_open():
    calls = []

    class Loc:
        def __init__(self, sel=""):
            self.sel = sel
            self.first = self

        async def wait_for(self, **kw):
            raise RuntimeError("no such element")

        async def click(self, **kw):
            raise RuntimeError("no click")

        async def all(self):
            return []

    class FakePWPage:
        def locator(self, sel):
            return Loc(sel)

        async def evaluate(self, script, sel=None):
            calls.append(sel)
            return True

        async def wait_for_timeout(self, ms):
            return None

    async def _run():
        try:
            await L.fill_composer(FakePWPage(), "tiktok", "hello")
        except Exception:
            pass
        return calls

    seen = asyncio.run(_run())
    assert any((c or "").startswith("[data-e2e") for c in seen)

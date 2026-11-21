"""Dau day mat that: ManagedThreadsPage + worker 1-collect (luat A).

Chay: python -m pytest tests/test_eye_wiring.py -q (tu C:\\Miro\\apps\\backend).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.browser.threads_page import ManagedThreadsPage  # noqa: E402
from miro.threads.worker import _ReadOnlyBrowser  # noqa: E402


def _fake_dom(records):
    """Page fake dung shape Playwright ma eye port dung: locator().all(),
    link.get_attribute('href'), link.evaluate(js)."""

    class Link:
        def __init__(self, rec):
            self._rec = rec

        async def get_attribute(self, name):
            return self._rec["href"] if name == "href" else None

        async def evaluate(self, js):
            if "innerText" in js:
                return self._rec["text"]
            if "closest('article')" in js and "querySelector" not in js:
                return True  # link nam trong article
            return self._rec["has_video"]

    class Page:
        def locator(self, sel):
            if sel == "article":
                class ArticleLoc:
                    async def count(self):
                        return len(records)

                return ArticleLoc()
            assert "/@alice/post/" in sel and "/@alice/t/" in sel  # locator hep A

            class Loc:
                async def all(self):
                    return [Link(r) for r in records]

                async def count(self):
                    return len(records)

            return Loc()

    return Page()


def _tab(page, owner="alice"):
    return SimpleNamespace(page=page, record={"expectedAccountId": owner},
                           renew=lambda ttl=300: None, release=lambda: None)


def test_managed_page_read_eye_qua_eye_port():
    recs = [{"href": "/@alice/post/P1", "text": "hello #dub111111",
             "has_video": True}]
    page = ManagedThreadsPage(_tab(_fake_dom(recs)), owner="alice")
    out = page.read_eye(SimpleNamespace(owner="alice"))
    assert len(out) == 1
    assert out[0]["post_id"] == "P1" and out[0]["tag"] == "#dub111111"
    assert out[0]["has_video"] is True


def test_worker_1_collect_chi_quet_1_lan():
    recs = [{"href": "/@alice/post/P1", "text": "a #dub111111", "has_video": False},
            {"href": "/@alice/post/P2", "text": "b #dub222222", "has_video": False}]
    calls = {"n": 0}

    class CountingPage(ManagedThreadsPage):
        def collect_records(self, owner=""):
            calls["n"] += 1
            return super().collect_records(owner)

    page = CountingPage(_tab(_fake_dom(recs)), owner="alice")
    ro = _ReadOnlyBrowser(page)
    intents = [SimpleNamespace(owner="alice", tag="#dub111111", text="a",
                               shortcode="s1", intent_id="s1"),
               SimpleNamespace(owner="alice", tag="#dub222222", text="b",
                               shortcode="s2", intent_id="s2")]
    out = ro.read_group_receipts(intents)
    assert calls["n"] == 1  # 1-collect, khong N-read
    assert set(out) == {"s1", "s2"}
    assert out["s1"]["post_id"] == "P1" and out["s2"]["post_id"] == "P2"


def test_verify_actor_khop_va_lech():
    page = ManagedThreadsPage(_tab(_fake_dom([]), owner="alice"), owner="alice")
    assert page.verify_actor("alice") is True
    assert page.verify_actor("@ALICE") is True
    assert page.verify_actor("bob") is False


def test_b4_scan_log_hit_miss_va_b8_author_live():
    import asyncio
    from miro.publishing.publisher import collect_post_records
    recs = [{"href": "/@alice/post/P1", "text": "a #dub111111", "has_video": False},
            {"href": "/@alice/post/P1", "text": "a #dub111111", "has_video": False}]
    diag: dict = {}
    raw = asyncio.run(collect_post_records(_fake_dom(recs), "alice", diag=diag))
    assert diag["links"] == 2 and diag["articles"] == 2 and diag["dupes"] == 1
    assert len(raw) == 1  # contract cu: chi record that, khong tron diagnostic
    assert raw[0]["author"] == "@alice"  # B8: doc tu href quan sat duoc


def test_b8_author_lech_tab_nao_tu_choi():
    from miro.publishing.publisher import match_eye_records
    recs = [{"author": "@bob", "tag": "#dub111111",
             "url": "https://www.threads.com/@bob/post/P9",
             "post_id": "P9", "has_video": False}]
    assert match_eye_records(recs, "alice", "#dub111111", "x", []) is None

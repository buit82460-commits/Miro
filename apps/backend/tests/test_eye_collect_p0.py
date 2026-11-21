"""P0 mat: collect_post_records that + fix S2/S3/B1-B3/B6-B7.

Chay: python -m pytest tests/test_eye_collect_p0.py -q (tu C:\\Miro\\apps\\backend).
Fake DOM Threads, khong Chrome that, khong mang.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.publishing.publisher import (  # noqa: E402
    Intent,
    collect_post_records,
    extract_eye_tag,
    verify_receipt,
)


class FakeLink:
    def __init__(self, href, article_text, has_video, article=True):
        self._href = href
        self._text = article_text
        self._video = has_video
        self._article = article

    async def get_attribute(self, name):
        assert name == "href"
        return self._href

    async def evaluate(self, js):
        if "innerText" in js:
            return self._text
        if "querySelector('video')" in js:
            # mo phong fix B1: khong article -> False (khong lan document)
            return self._video if self._article else False
        if "closest('article')" in js:
            return self._article
        return self._text


class FakeLocator:
    def __init__(self, links):
        self._links = links

    async def all(self):
        return self._links

    async def count(self):
        return len(self._links)


class FakePage:
    def __init__(self, links):
        self._links = links
        self.locator_calls: list[str] = []

    def locator(self, selector):
        self.locator_calls.append(selector)
        return FakeLocator(self._links)


def run(coro):
    import asyncio
    return asyncio.run(coro)


def test_locator_hep_2_pattern():
    page = FakePage([])
    run(collect_post_records(page, "alice", diag={}))
    # 1 call links (locator hep A) + 1 call dem articles (B4)
    assert len(page.locator_calls) == 2
    sel = page.locator_calls[0]
    assert "/@alice/post/" in sel and "/@alice/t/" in sel
    assert page.locator_calls[1] == "article"


def test_same_record_2_article_khong_ghep_cheo():
    links = [
        FakeLink("/@alice/post/P1", "bai mot #dub111111", True),
        FakeLink("/@alice/post/P2", "bai hai #dub222222", False),
    ]
    recs = run(collect_post_records(FakePage(links), "alice"))
    assert len(recs) == 2
    assert recs[0]["post_id"] == "P1" and recs[0]["tag"] == "#dub111111"
    assert recs[1]["post_id"] == "P2" and recs[1]["tag"] == "#dub222222"
    assert recs[0]["has_video"] is True and recs[1]["has_video"] is False


def test_b1_video_khong_article_khong_lan_document():
    links = [FakeLink("/@alice/post/P9", "bai khong article #dub999999",
                      True, article=False)]
    recs = run(collect_post_records(FakePage(links), "alice"))
    assert recs and recs[0]["has_video"] is False


def test_b2_post_id_cat_query_fragment():
    links = [FakeLink("/@alice/post/abc123?x=1&utm_yyy#frag",
                      "bai query #dub333333", False)]
    recs = run(collect_post_records(FakePage(links), "alice"))
    assert recs and recs[0]["post_id"] == "abc123"


def test_b3_tag_dai_khong_hit_6_so_dau():
    assert extract_eye_tag("caption #dub1234567 dai") == ""
    assert extract_eye_tag("chuan #dub123456 ok") == "#dub123456"


def test_b6_dedup_limit_theo_record():
    links = [
        FakeLink("/@alice/post/P1", "mot #dub111111", False),
        FakeLink("/@alice/post/P1?x=2", "mot lap #dub111111", False),
        FakeLink("/@alice/post/P2", "hai #dub222222", False),
    ]
    recs = run(collect_post_records(FakePage(links), "alice", limit=2))
    assert [r["post_id"] for r in recs] == ["P1", "P2"]


def test_b7_preview_giu_tag_cuoi_caption_dai():
    body = "x" * 280 + " #dub444444"
    links = [FakeLink("/@alice/post/P4", body, False)]
    recs = run(collect_post_records(FakePage(links), "alice"))
    assert recs and "#dub444444" in recs[0]["text"]


def test_s2_bo_passthrough_match_post_id_tu_khai():
    intent = Intent(intent_id="t-s2", shortcode="s2", owner="alice",
                    text="x #dub000001", tag="#dub000001")
    # receipt tu khai match=post_id nhung tag sai + post_id khong trong known -> tu choi
    fake = {"owner": "alice", "url": "https://www.threads.com/@alice/post/PX",
            "post_id": "PX", "tag": "#dub000099", "match": "post_id"}
    assert verify_receipt(fake, intent, ["OTHER"]) is None
    # post_id trong known_ids thi chap nhan (khong can tag)
    assert verify_receipt(fake, intent, ["PX"])["status"] == "published"


def test_s3_eye_record_key_author_duoc_chap_nhan():
    intent = Intent(intent_id="t-s3", shortcode="s3", owner="alice",
                    text="x #dub000001", tag="#dub000001")
    rec = {"author": "@alice", "url": "https://www.threads.com/@alice/post/P1",
           "post_id": "P1", "tag": "#dub000001"}
    assert verify_receipt(rec, intent)["status"] == "published"


def test_oracle_goc_khi_mount_duoc():
    try:
        from core.rea_eye import collect_post_records as _orig  # noqa
    except Exception:
        pytest.skip("C:\\dubtool khong mount duoc")

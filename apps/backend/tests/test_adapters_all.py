"""Test 8 platform adapters — mock page offline, khong cham Chrome that."""
from __future__ import annotations

import pytest

from miro.adapters.core import (
    SPECS, PlatformWorker, guard_duplicate, job_id_for, text_for,
)


class FakePage:
    def __init__(self, ack=None, fail=None, before_submit=True):
        self.ack = ack or {}
        self.fail = fail
        self.before_submit = before_submit
        self.submits = 0
        self.released = False

    def submit_once(self, req):
        from miro.adapters.core import LiveChromeError
        self.submits += 1
        if self.fail:
            raise LiveChromeError(self.fail, before_submit=self.before_submit)
        return dict(self.ack)

    def reconcile(self, req):
        return {"url": f"https://example.test/{req['shortcode']}", "verified": True}

    def release(self):
        self.released = True


@pytest.mark.parametrize("pid", sorted(SPECS))
def test_spec_registered(pid):
    spec = SPECS[pid]
    assert spec.publication.startswith("publication")
    assert spec.job_prefix
    assert spec.entry_url.startswith("http")


def _item(sc="7", **kw):
    d = {"shortcode": sc, "title": "t", "description": "d", "tags": []}
    d.update(kw)
    return d


def test_text_for_caption_adds_tag():
    text = text_for(SPECS["threads"], _item("123"))
    assert "#dub123" in text.lower()
    assert len(text) <= 500


def test_text_for_prompt_and_product():
    p = text_for(SPECS["chatgpt"], {"shortcode": "1", "prompt": "hello"})
    assert p == "hello"
    with pytest.raises(ValueError):
        text_for(SPECS["chatgpt"], {"shortcode": "1", "prompt": ""})
    prod = text_for(SPECS["shopee"], {"shortcode": "2", "name": "sp",
                                      "price": 5, "stock": 1, "description": "mota"})
    assert "sp" in prod
    with pytest.raises(ValueError):
        text_for(SPECS["shopee"], {"shortcode": "2", "name": "", "price": 5, "stock": 1})


def test_limits_enforced():
    trimmed = text_for(SPECS["threads"], _item("9", description="x" * 600))
    assert len(trimmed) <= 500
    with pytest.raises(ValueError):
        text_for(SPECS["chatgpt"], {"shortcode": "1", "prompt": "y" * 8001})
    with pytest.raises(ValueError):
        text_for(SPECS["threads"], {"shortcode": "1"})


def _run(pid, items, tmp_path, **kw):
    worker = PlatformWorker(SPECS[pid])
    base = tmp_path / pid
    base.mkdir(exist_ok=True)
    page = FakePage(**kw.pop("page_kw", {}))
    out = worker.run_batch(items, base, kw.pop("account", "acc"),
                           lambda: page, attempts_dir=base / "attempts")
    return out, page


@pytest.mark.parametrize("pid", sorted(SPECS))
def test_run_batch_posts_and_reconciles(pid, tmp_path):
    item = _item("42", **({"prompt": "hi"} if SPECS[pid].kind == "prompt"
                          else {"name": "n", "price": 1, "stock": 0}
                          if SPECS[pid].kind == "product" else {}))
    out, page = _run(pid, [item], tmp_path,
                     page_kw={"ack": {"receipt": "SUBMITTED", "url": "u"}})
    assert out["results"][0].get("posted") is True
    assert out["report"]["submitted"] == ["42"]
    assert out["report"]["reconciled"] == ["42"]
    assert page.released is True
    # guard: chay lai -> skip, khong submit them
    out2, page2 = _run(pid, [item], tmp_path,
                       page_kw={"ack": {"receipt": "SUBMITTED"}})
    # publication da merge nen skip ALREADY_IN_PUBLICATION
    assert out2["results"][0].get("skipped") == "ALREADY_IN_PUBLICATION"


def test_failed_before_post_does_not_block_next(tmp_path):
    from miro.adapters.core import LiveChromeError  # noqa
    worker = PlatformWorker(SPECS["threads"])
    base = tmp_path / "t"
    base.mkdir()
    calls = {"n": 0}

    class P(FakePage):
        def submit_once(self, req):
            calls["n"] += 1
            if req["shortcode"] == "a":
                raise LiveChromeError("no composer", before_submit=True)
            return {"receipt": "SUBMITTED", "url": "u"}

    page = P()
    out = worker.run_batch([_item("a"), _item("b")], base, "acc",
                           lambda: page, attempts_dir=base / "attempts")
    assert out["results"][0].get("error") == "FAILED_BEFORE_POST"
    assert out["results"][1].get("posted") is True


def test_unknown_stops_batch_no_replay(tmp_path):
    worker = PlatformWorker(SPECS["threads"])
    base = tmp_path / "u"
    base.mkdir()

    class P(FakePage):
        def submit_once(self, req):
            from miro.adapters.core import LiveChromeError
            self.submits += 1
            if req["shortcode"] == "a":
                raise LiveChromeError("ack timeout", before_submit=False)
            return {"receipt": "SUBMITTED", "url": "u"}

    page = P()
    out = worker.run_batch([_item("a"), _item("b")], base, "acc",
                           lambda: page, attempts_dir=base / "attempts")
    assert out["results"][0].get("receipt") == "UNKNOWN"
    assert out["results"][1].get("receipt") == "UNKNOWN"
    assert out["results"][1].get("cause") == "STOP_AFTER_AMBIGUOUS"
    assert page.submits == 1


def test_guard_duplicate_journal(tmp_path):
    attempts = tmp_path / "att"
    attempts.mkdir()
    (attempts / "threads-1.json").write_text("{}", encoding="utf-8")
    skip = guard_duplicate(SPECS["threads"], tmp_path, "1",
                           "threads-1.json", attempts)
    assert skip and skip["skipped"] == "UNRECONCILED_ATTEMPT"


def test_job_id_for():
    assert job_id_for(SPECS["facebook"], {"shortcode": "x"}) == "olichopper-fb-x"

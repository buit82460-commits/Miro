"""Publisher vs DU LIEU THAT cua A (C:\\dubtool) — chay trong C.

Dinh nghia merge moi, tieu chi (3): kiem chung bang luong thuc te trong C,
khong mock tu-pass. Moi test doc file that do code cu A sinh ra; skip khi
A khong mount (CI co A mount thi phai chay).

Nguon that:
- reports/resource-batches/threads-20261120/download.json (1 item test-001)
- reports/resource-batches/threads-20261120/publication-threads.json (published)
- reports/social-attempts/threads-test-001.json (published, reconciledReadOnly)
- reports/social-attempts/threads-7679492543322557728.json (submit — con treo)
- reports/social-attempts/threads-7696940881491889440.json (awaiting-group)
- reports/resource-batches/threads-20261120-2v/download.json (2 item co media)
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.publishing.publisher import (  # noqa: E402
    Intent,
    Publisher,
    caption_for,
    check_video,
    guard_duplicate,
    media_for,
)

A = Path(r"C:\dubtool")
BATCH = A / "reports" / "resource-batches" / "threads-20261120"
BATCH_2V = A / "reports" / "resource-batches" / "threads-20261120-2v"
ATTEMPTS = A / "reports" / "social-attempts"

needs_a = pytest.mark.skipif(not A.exists(), reason="C:\\dubtool khong mount")


def _load_manifest():
    data = json.loads((BATCH / "download.json").read_text(encoding="utf-8-sig"))
    return data["saved"][0]


class ReadOnlyBrowser:
    """Chi doc, khong bao gio post that.

    - attempts: so lan publish di qua gate den post_once (gate mo).
    - posts: so post THANH CONG (luon 0 — raise truoc khi post that).
    An toan: bat ky code nao muon post that deu bi chan o day.
    """

    def __init__(self, receipt=None):
        self.posts = 0
        self.attempts = 0
        self.receipt = receipt

    def post_once(self, intent):
        self.attempts += 1
        # Dry-run: khong post len mang that — raise TRUOC khi co post thanh cong.
        raise AssertionError("dry-run: khong duoc post len mang that")

    def read_receipt(self, intent):
        return self.receipt


def _copy_production_shape(tmp_path):
    """Dung batch tmp tu copy du lieu production that."""
    base = tmp_path / "batch"
    attempts = tmp_path / "attempts"
    base.mkdir()
    attempts.mkdir()
    shutil.copy(BATCH / "publication-threads.json", base / "publication-threads.json")
    shutil.copy(ATTEMPTS / "threads-test-001.json", attempts / "threads-test-001.json")
    return base, attempts


@needs_a
def test_real_manifest_caption_guard(tmp_path):
    item = _load_manifest()
    assert item["shortcode"] == "test-001"
    text = caption_for(item)
    assert "Hello Threads!" in text
    assert "#dub" in text  # unique tag that tu shortcode

    base, attempts = _copy_production_shape(tmp_path)
    skip = guard_duplicate(base, "test-001", "threads-test-001.json", attempts)
    assert skip is not None and skip["skipped"] == "ALREADY_IN_PUBLICATION"

    pending = guard_duplicate(base, "chua-tung-co", "threads-chua-tung-co.json", attempts)
    assert pending is None


@needs_a
def test_real_journal_reconcile_readonly(tmp_path):
    base, attempts = _copy_production_shape(tmp_path)
    item = _load_manifest()
    intent = Intent.from_item(item, "haodaojrk5")
    pub = Publisher(base, attempts)

    journal = json.loads((attempts / "threads-test-001.json").read_text(encoding="utf-8-sig"))
    browser = ReadOnlyBrowser(receipt={
        "owner": "haodaojrk5", "url": journal["url"],
        "post_id": journal["post_id"], "tag": intent.tag,
    })
    out = pub.reconcile(intent, browser)
    assert out.get("reconciled") is True
    assert browser.posts == 0  # read-only, khong post

    # Journal submit con treo that: guard cam replay, reconcile khong post
    shutil.copy(ATTEMPTS / "threads-7679492543322557728.json",
                attempts / "threads-7679492543322557728.json")
    stuck = guard_duplicate(base, "7679492543322557728",
                            "threads-7679492543322557728.json", attempts)
    assert stuck is not None and stuck["skipped"] == "UNRECONCILED_ATTEMPT"
    stuck_intent = Intent(intent_id="threads-7679492543322557728",
                          shortcode="7679492543322557728",
                          owner="haodaojrk5", text="treo #dub000002", tag="#dub000002")
    out2 = pub.reconcile(stuck_intent, ReadOnlyBrowser(receipt=None))
    assert out2.get("reconciled") is False


@needs_a
def test_real_batch_dryrun(tmp_path):
    """Batch tren copy du lieu production: guard dung, 0 post that."""
    base, attempts = _copy_production_shape(tmp_path)
    item = _load_manifest()
    intent = Intent.from_item(item, "haodaojrk5")
    pub = Publisher(base, attempts)
    browser = ReadOnlyBrowser()
    out = pub.run_batch([intent], browser)
    assert browser.posts == 0
    # test-001 da published -> skip, khong post
    assert any(r.get("skipped") == "ALREADY_IN_PUBLICATION" for r in out)

    # Batch 2v that (2 item co media that, file con tren may):
    # hanh vi MOI (M2 fix #3): file that gate pass -> di qua gate den post;
    # browser dry-run raise (loi sau click) -> batch ghi UNKNOWN + dung,
    # 0 post THANH CONG. Neu file khong con -> MEDIA_UNVERIFIED fail-closed.
    data2 = json.loads((BATCH_2V / "download.json").read_text(encoding="utf-8-sig"))
    intents2 = [Intent.from_item(s, "haodaojrk5") for s in data2["saved"]]
    have_files = [bool(Path(s.get("local_path") or "").exists())
                  for s in data2["saved"]]
    out2 = pub.run_batch(intents2, browser)
    assert browser.posts == 0  # khong co post thanh cong nao
    if all(have_files):
        # Gate mo -> da goi post (attempt), loi sau click -> UNKNOWN, khong replay
        assert browser.attempts > 0
        assert any(r.get("receipt") in ("UNKNOWN", "UNCONFIRMED_NO_REPLAY")
                   for r in out2)
    else:
        # File mat -> fail-closed truoc click, khong goi post
        assert browser.attempts == 0
        assert all(r.get("error") or r.get("skipped") for r in out2)


@needs_a
def test_real_media_gate(tmp_path):
    data2 = json.loads((BATCH_2V / "download.json").read_text(encoding="utf-8-sig"))
    real = [s for s in data2["saved"]
            if s.get("local_path") and Path(s["local_path"]).exists()]
    if not real:
        pytest.skip("khong con file video that cua A tren may nay")
    item = real[0]
    problems = check_video(Path(item["local_path"]))
    assert isinstance(problems, list)  # gate chay duoc tren file that
    assert media_for(item) is not None

    base, attempts = _copy_production_shape(tmp_path)
    pub = Publisher(base, attempts)
    intent = Intent.from_item(item, "haodaojrk5")
    assert intent.media_path  # from_item giu duong dan media that
    browser = ReadOnlyBrowser()
    # Hanh vi MOI (M2 fix #3): file that gate pass -> publish di den post
    # (khong con MEDIA_NOT_PORTED cung); browser dry-run raise truoc khi
    # co post thanh cong -> chung to gate MO, va 0 post that.
    with pytest.raises(AssertionError, match="dry-run"):
        pub.publish(intent, browser)
    assert browser.attempts == 1  # da di qua gate den post
    assert browser.posts == 0  # khong co post thanh cong nao
    # Gate fail van fail-closed: file khong ton tai -> FAILED_BEFORE_POST
    bad = Intent(intent_id="threads-bad", shortcode="bad",
                 owner="haodaojrk5", text="x #dub000001", tag="#dub000001",
                 media_path=str(tmp_path / "khong-ton-tai.mp4"))
    out = pub.publish(bad, browser)
    assert out.get("error") == "FAILED_BEFORE_POST"
    assert browser.attempts == 1  # khong goi post khi gate fail

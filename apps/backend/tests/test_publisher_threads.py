"""Tests mirroring threads_post_one.py semantics. No real Post.

Layout mirrors legacy: base=<batch dir> holds publication-threads.json,
attempts=<reports/social-attempts> holds threads-<shortcode>.json.
Run: python -m pytest tests/test_publisher_threads.py -q

New tests touch legacy code directly (dieiu kien 2): caption_for/guard_duplicate
tu C:\\dubtool\\scripts\\threads_post_one.py va match_eye_records tu
C:\\dubtool\\core\\rea_eye.py lam oracle, khong mock 100%.
"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.publishing.publisher import (  # noqa: E402
    Intent,
    Publisher,
    caption_for,
    check_video,
    guard_duplicate,
    journal_path_for,
    match_eye_records,
    media_for,
    unique_tag,
    verify_receipt,
)

DUBTOOL = Path(r"C:\dubtool")
if str(DUBTOOL) not in sys.path:
    sys.path.insert(0, str(DUBTOOL))


class MockBrowser:
    def __init__(self, owner="alice", crash_after_post=False, receipts=None):
        self.posts = 0
        self.touches = 0
        self.owner = owner
        self.crash_after_post = crash_after_post
        self.receipts = receipts or {}
        self.lock = threading.Lock()

    def post_once(self, intent):
        with self.lock:
            self.posts += 1
            self.touches += 1
            n = self.posts
        if self.crash_after_post:
            raise RuntimeError("simulated crash after Post click")
        return {"owner": intent.owner,
                "url": f"https://www.threads.com/@{intent.owner}/post/P{n}",
                "post_id": f"P{n}", "tag": intent.tag, "has_video": True}

    def read_receipt(self, intent):
        self.touches += 1
        return self.receipts.get(intent.intent_id)


def make_pub(tmp_path):
    base = tmp_path / "batch"
    attempts = tmp_path / "social-attempts"
    base.mkdir()
    return Publisher(base, attempts_dir=attempts), base, attempts


def test_two_workers_one_intent_only_one_sends(tmp_path):
    pub, base, attempts = make_pub(tmp_path)
    intent = Intent(intent_id="threads-sc1", shortcode="sc1", owner="alice",
                    text="hello #dub000001", tag="#dub000001")
    browser = MockBrowser()
    results = []

    def worker():
        results.append(pub.publish(intent, browser))

    t1, t2 = threading.Thread(target=worker), threading.Thread(target=worker)
    t1.start(); t2.start(); t1.join(); t2.join()
    assert browser.posts == 1, f"expected 1 send, got {browser.posts}"
    skips = [r for r in results if r.get("skipped")]
    posted = [r for r in results if r.get("posted")]
    assert len(posted) == 1 and len(skips) == 1
    assert (base / "publication-threads.json").exists()
    assert (attempts / "threads-sc1.json").exists()


def test_crash_after_post_journal_keeps_submit_and_reraise(tmp_path):
    """Legacy _post_live_chrome_on_page:670-700 — loi sau click thi re-raise,
    journal giu 'submit'; caller (run_batch) moi ghi unknown + dung submit."""
    pub, base, attempts = make_pub(tmp_path)
    intent = Intent(intent_id="threads-sc2", shortcode="sc2", owner="alice",
                    text="crash test #dub000002", tag="#dub000002")
    crashing = MockBrowser(crash_after_post=True)
    with pytest.raises(RuntimeError):
        pub.publish(intent, crashing)
    import json
    journal = json.loads((attempts / "threads-sc2.json").read_text(encoding="utf-8-sig"))
    assert journal["status"] == "submit", journal
    # run_batch tren intent MOI voi crashing browser: caller ghi unknown + dung
    fresh = Intent(intent_id="threads-sc2b", shortcode="sc2b", owner="alice",
                   text="crash batch #dub000002", tag="#dub000002")
    out = pub.run_batch([fresh], crashing)
    journal2 = json.loads((attempts / "threads-sc2b.json").read_text(encoding="utf-8-sig"))
    assert journal2["status"] == "unknown", journal2
    assert any(r.get("receipt") == "UNKNOWN" for r in out)
    # guard: intent cu (journal submit) khong bao gio replay trong batch
    out2 = pub.run_batch([intent], MockBrowser())
    assert out2 and out2[0].get("skipped") == "UNRECONCILED_ATTEMPT"
    # restart: same intent must NOT resend; goes to reconcile only
    pub2 = Publisher(base, attempts_dir=attempts)
    retry = pub2.publish(intent, MockBrowser())
    assert retry.get("skipped") == "UNRECONCILED_ATTEMPT"
    # reconcile read-only promotes with verified receipt, 0 Post clicks
    reader = MockBrowser(receipts={"threads-sc2": {"owner": "alice",
        "url": "https://www.threads.com/@alice/post/P9", "post_id": "P9",
        "tag": "#dub000002", "match": "post_id", "has_video": True}})
    rec = pub2.reconcile(intent, reader)
    assert rec.get("reconciled") is True and rec.get("post_id") == "P9"
    assert reader.posts == 0


def test_old_unknown_batch_into_reconcile_zero_browser_post(tmp_path):
    pub, base, attempts = make_pub(tmp_path)
    intents = [Intent(intent_id=f"threads-old{i}", shortcode=f"old{i}", owner="alice",
                      text=f"t{i} #dub0000{i}", tag=f"#dub0000{i}") for i in (3, 4)]
    for it in intents:
        with pytest.raises(RuntimeError):
            pub.publish(it, MockBrowser(crash_after_post=True))
    reader = MockBrowser(receipts={
        "threads-old3": {"owner": "alice",
                         "url": "https://www.threads.com/@alice/post/P3",
                         "post_id": "P3", "tag": "#dub00003", "match": "post_id",
                         "has_video": True},
        # old4 stays unconfirmed
    })
    results = [pub.reconcile(it, reader) for it in intents]
    assert results[0].get("reconciled") is True
    assert results[1].get("reconciled") is False
    assert reader.posts == 0, "reconcile must never click Post"


def test_failed_before_post_allows_retry(tmp_path):
    pub, base, attempts = make_pub(tmp_path)
    intent = Intent(intent_id="threads-sc5", shortcode="sc5", owner="alice",
                    text="retry me #dub000005", tag="#dub000005")

    class BeforeSubmitFail:
        def post_once(self, intent):
            err = RuntimeError("composer missing")
            err.before_submit = True
            raise err

        def read_receipt(self, intent):
            return None

    out = pub.publish(intent, BeforeSubmitFail())
    assert out.get("error") == "FAILED_BEFORE_POST"
    journal = attempts / "threads-sc5.json"
    assert journal.exists()


def test_batch_two_phase_ack_then_group_reconcile(tmp_path):
    """Two-phase dung legacy: Phase A chi ack (khong merge publication),
    Phase B group reconcile moi merge + verified."""
    pub, base, attempts = make_pub(tmp_path)
    ok = Intent(intent_id="threads-b1", shortcode="b1", owner="alice",
                text="one #dub000011", tag="#dub000011")
    bad = Intent(intent_id="threads-b2", shortcode="b2", owner="alice",
                 text="two #dub000012", tag="#dub000012")
    after = Intent(intent_id="threads-b3", shortcode="b3", owner="alice",
                   text="three #dub000013", tag="#dub000013")

    class SeqBrowser:
        def __init__(self):
            self.calls: list[str] = []

        def post_once(self, intent):
            self.calls.append(intent.intent_id)
            if intent.intent_id == "threads-b1":
                return {"ack_post_codes": ["PB1"], "ack_via": "network"}
            raise RuntimeError("simulated ambiguous ack after click")

        def read_receipt(self, intent):
            if intent.intent_id == "threads-b1":
                return {"owner": "alice",
                        "url": "https://www.threads.com/@alice/post/PB1",
                        "post_id": "PB1", "tag": "#dub000011", "has_video": True}
            return None

    seq = SeqBrowser()
    res = pub.run_batch([ok, bad, after], seq)
    assert seq.calls == ["threads-b1", "threads-b2"]
    deferred = [r for r in res if r.get("receipt") == "DEFERRED_TO_GROUP_RECONCILE"]
    assert len(deferred) == 1 and deferred[0]["shortcode"] == "b3"
    import json
    pub_data = json.loads((base / "publication-threads.json").read_text(encoding="utf-8-sig"))
    urls = {x["shortcode"]: x.get("url") for x in pub_data.get("items", [])}
    # chi b1 (verified qua group) duoc merge; b2 unknown khong merge
    assert urls.get("b1") == "https://www.threads.com/@alice/post/PB1"
    assert "b2" not in urls
    pub1 = [r for r in res if r.get("shortcode") == "b1" and r.get("posted")]
    assert pub1 and pub1[0].get("status") == "published"
    assert "profile_match_seen" in pub1[0].get("timeline", {})
    assert "ack_to_match_s" in pub1[0]


def test_batch_before_submit_error_continues(tmp_path):
    """Khop _run_batch_legacy :937-941: loi before_submit thi tiep tuc item sau."""
    pub, base, attempts = make_pub(tmp_path)
    fail = Intent(intent_id="threads-c1", shortcode="c1", owner="alice",
                  text="bad composer #dub000021", tag="#dub000021")
    good = Intent(intent_id="threads-c2", shortcode="c2", owner="alice",
                  text="good #dub000022", tag="#dub000022")

    class MixedBrowser:
        def post_once(self, intent):
            if intent.intent_id == "threads-c1":
                err = RuntimeError("composer missing")
                err.before_submit = True
                raise err
            return {"ack_post_codes": ["PC2"], "ack_via": "network"}

        def read_receipt(self, intent):
            if intent.intent_id == "threads-c2":
                return {"owner": "alice",
                        "url": "https://www.threads.com/@alice/post/PC2",
                        "post_id": "PC2", "tag": "#dub000022", "has_video": True}
            return None

    res = pub.run_batch([fail, good], MixedBrowser())
    assert any(r.get("error") == "FAILED_BEFORE_POST" for r in res)
    got = [r for r in res if r.get("shortcode") == "c2" and r.get("status") == "published"]
    assert got, res


def test_batch_duplicate_tags_abort(tmp_path):
    """Legacy run_batch :779-786: 2 item cung #dub thi abort ca batch."""
    pub, base, attempts = make_pub(tmp_path)
    a = Intent(intent_id="threads-d1", shortcode="11", owner="alice",
               text="dup tag", tag="#dub000011")
    b = Intent(intent_id="threads-d2", shortcode="22", owner="alice",
               text="dup tag", tag="#dub000011")
    # unique_tag("11") vs ("22") khac nhau -> ep trung tag thu cong
    b.tag = "#dub000011"
    res = pub.run_batch([a, b], MockBrowser())
    assert res and res[0].get("error") == "DUPLICATE_TAGS"
    assert res[0].get("tags") == ["#dub000011"]


# ---- Test cham code cu (dieu kien 2): oracle tu dubtool ----
def _legacy_caption():
    try:
        from scripts.threads_post_one import caption_for as legacy_caption
        return legacy_caption
    except Exception:
        try:
            import threads_post_one as _lt
            return _lt.caption_for
        except Exception:
            return None


def test_legacy_caption_oracle():
    legacy_caption = _legacy_caption()
    if legacy_caption is None:
        pytest.skip("C:\\dubtool khong mount duoc")
    fixtures = [
        {"shortcode": "abc123456", "title": "Hello", "description": "World",
         "tags": ["dub", "test"]},
        {"shortcode": "xyz", "title": "Video by foo", "description": "Video by foo"},
        {"shortcode": "999", "title": "T" * 600, "description": "D",
         "tags": ["a", "b"]},
        {"shortcode": "42", "title": "", "description": "only desc", "tags": []},
    ]
    for item in fixtures:
        assert caption_for(item) == legacy_caption(item), item


def test_legacy_guard_duplicate_oracle(tmp_path):
    try:
        import scripts.threads_post_one as _lt
        legacy_guard = _lt.guard_duplicate
    except Exception:
        try:
            import threads_post_one as _lt
            legacy_guard = _lt.guard_duplicate
        except Exception:
            pytest.skip("C:\\dubtool khong mount duoc")
    base = tmp_path / "batch"
    attempts = tmp_path / "social-attempts"
    base.mkdir(parents=True, exist_ok=True)
    attempts.mkdir(parents=True, exist_ok=True)
    # legacy guard doc ATTEMPTS_DIR global -> tro sang tmp de oracle cong bang
    _lt.ATTEMPTS_DIR = attempts
    item = {"shortcode": "g1"}
    assert guard_duplicate(base, "g1", "threads-g1.json", attempts) is None
    assert legacy_guard(base, "g1", "threads-g1.json") is None
    (attempts / "threads-g1.json").write_text("{}", encoding="utf-8")
    assert guard_duplicate(base, "g1", "threads-g1.json", attempts)["skipped"] == \
        legacy_guard(base, "g1", "threads-g1.json")["skipped"] == "UNRECONCILED_ATTEMPT"


def test_legacy_eye_match_oracle():
    """match_eye_records port vs core/rea_eye.match_eye_records goc."""
    try:
        from core.rea_eye import match_eye_records as eye_match
    except Exception:
        pytest.skip("C:\\dubtool khong mount duoc")
    records = [
        {"author": "@alice", "tag": "#dub000001",
         "url": "https://www.threads.com/@alice/post/P1", "post_id": "P1",
         "has_video": True, "text": "hello #dub000001"},
        {"author": "@alice", "tag": "#dub000002",
         "url": "https://www.threads.com/@alice/post/P2", "post_id": "P2",
         "has_video": True, "text": "world #dub000002"},
    ]
    pending = {"sc1": {"tag": "#dub000002", "post_ids": ["P2"]}}
    receipts, missing = eye_match(pending, records)
    assert receipts["sc1"]["post_id"] == "P2"
    hit = match_eye_records(records, "alice", "#dub000002", "world #dub000002", ["P2"])
    assert hit and hit["post_id"] == "P2" and hit["match"] == "eye-post_id"
    # exact tag khong can post_id
    hit2 = match_eye_records(records, "alice", "#dub000001", "", [])
    assert hit2 and hit2["post_id"] == "P1"


def test_same_record_strictness_no_substring(tmp_path):
    """Port siet same-record: substring/prefix bi tu choi (legacy eye
    doi exact tag equality, khong text fallback)."""
    recs = [{"author": "@alice", "tag": "#dub000099",
             "url": "https://www.threads.com/@alice/post/PX", "post_id": "PX",
             "has_video": True, "text": "unrelated article"}]
    # tag khac -> khong match du text co chua substring
    assert match_eye_records(recs, "alice", "#dub000001", "unrelated article", []) is None
    intent = Intent(intent_id="threads-s1", shortcode="s1", owner="alice",
                    text="x #dub000001", tag="#dub000001")
    # receipt dung url nhung sai tag -> tu choi (khong substring url/JSON)
    bad = {"owner": "alice", "url": "https://www.threads.com/@alice/post/PX",
           "post_id": "PX", "tag": "#dub000099"}
    assert verify_receipt(bad, intent) is None
    # receipt dung tag exact -> chap nhan
    good = {"owner": "alice", "url": "https://www.threads.com/@alice/post/P1",
            "post_id": "P1", "tag": "#dub000001"}
    assert verify_receipt(good, intent)["status"] == "published"


def test_known_ids_plumbing_from_journal(tmp_path):
    """run_reconcile legacy :1019: known_ids = journal ack_post_codes."""
    import json
    pub, base, attempts = make_pub(tmp_path)
    intent = Intent(intent_id="threads-k1", shortcode="k1", owner="alice",
                    text="known #dub000031", tag="#dub000031")
    (attempts / "threads-k1.json").write_text(json.dumps({
        "shortcode": "k1", "account": "alice", "status": "submitted-awaiting-group-reconcile",
        "ack_post_codes": ["PK1"]}), encoding="utf-8")

    class EyeBrowser:
        def read_receipt(self, intent):
            # eye records: author+tag+post_id cung 1 record
            return [{"author": "@alice", "tag": "#dub000031",
                     "url": "https://www.threads.com/@alice/post/PK1",
                     "post_id": "PK1", "has_video": True, "text": "known #dub000031"}]

    rec = pub.reconcile(intent, EyeBrowser())
    assert rec.get("reconciled") is True and rec.get("post_id") == "PK1"


def test_media_gate_blocks_unverified_publish(tmp_path):
    pub, base, attempts = make_pub(tmp_path)
    intent = Intent(intent_id="threads-m1", shortcode="m1", owner="alice",
                    text="media #dub000041", tag="#dub000041",
                    media_sha256="abc123", media_path="/tmp/x.mp4")
    out = pub.publish(intent, MockBrowser())
    assert out.get("error") == "FAILED_BEFORE_POST"
    assert out.get("cause") == "ValueError"
    # media_for gate that: khong ton tai -> None; sai ext -> None
    assert media_for({"shortcode": "m", "media_path": "/no/such/file.mp4"}) is None
    assert media_for({"shortcode": "m"}) is None


def test_integrity_baseline_fail_closed(tmp_path):
    from miro.publishing.publisher import enforce_adapter_integrity
    base_file = tmp_path / "adapter_baseline.json"
    base_file.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="INTEGRITY_DRIFT"):
        enforce_adapter_integrity(base_file)
    enforce_adapter_integrity(tmp_path / "not-exist.json")  # no-op


def test_actor_contract_mismatch_blocks(tmp_path):
    pub, base, attempts = make_pub(tmp_path)
    intent = Intent(intent_id="threads-a1", shortcode="a1", owner="alice",
                    text="actor #dub000051", tag="#dub000051")

    class WrongActor:
        declared_actor = "bob"

        def post_once(self, intent):
            raise AssertionError("must not post on actor mismatch")

        def read_receipt(self, intent):
            return None

    out = pub.publish(intent, WrongActor())
    assert out.get("error") == "FAILED_BEFORE_POST"

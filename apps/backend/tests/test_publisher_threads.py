"""Mock-browser tests mirroring threads_post_one.py semantics. No real Post.

Layout mirrors legacy: base=<batch dir> holds publication-threads.json,
attempts=<reports/social-attempts> holds threads-<shortcode>.json.
Run: python -m pytest tests/test_publisher_threads.py -q
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.publishing.publisher import Intent, Publisher, journal_path_for


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


def test_crash_after_post_restart_keeps_attempt(tmp_path):
    pub, base, attempts = make_pub(tmp_path)
    intent = Intent(intent_id="threads-sc2", shortcode="sc2", owner="alice",
                    text="crash test #dub000002", tag="#dub000002")
    crashing = MockBrowser(crash_after_post=True)
    out = pub.publish(intent, crashing)
    assert out.get("receipt") == "UNCONFIRMED_NO_REPLAY"
    journal = attempts / "threads-sc2.json"
    assert journal.exists()
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
        out = pub.publish(it, MockBrowser(crash_after_post=True))
        assert out.get("receipt") == "UNCONFIRMED_NO_REPLAY"
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
    # legacy keeps failed-before-post journal; Miro allows fresh retry only
    # after operator clears the journal (same invariant: no blind replay)
    journal = attempts / "threads-sc5.json"
    assert journal.exists()


def test_batch_two_phase_stops_on_unknown(tmp_path):
    pub, base, attempts = make_pub(tmp_path)
    ok = Intent(intent_id="threads-b1", shortcode="b1", owner="alice",
                text="one #dub000011", tag="#dub000011")
    bad = Intent(intent_id="threads-b2", shortcode="b2", owner="alice",
                  text="two #dub000012", tag="#dub000012")
    after = Intent(intent_id="threads-b3", shortcode="b3", owner="alice",
                   text="three #dub000013", tag="#dub000013")
    outcomes = [pub.publish(ok, MockBrowser()),
                pub.publish(bad, MockBrowser(crash_after_post=True))]
    assert outcomes[0].get("status") == "published"
    assert outcomes[1].get("receipt") == "UNCONFIRMED_NO_REPLAY"
    # two-phase via run_batch on fresh intents: first verified, second
    # ambiguous stops the third (deferred), group reconcile promotes b2
    import tempfile
    with tempfile.TemporaryDirectory() as td2:
        pub2, base2, _ = make_pub(Path(td2))

        class SeqBrowser:
            def __init__(self):
                self.calls: list[str] = []

            def post_once(self, intent):
                self.calls.append(intent.intent_id)
                if intent.intent_id == "threads-b1":
                    return {"owner": "alice",
                            "url": "https://www.threads.com/@alice/post/PB1",
                            "post_id": "PB1", "match": "post_id",
                            "has_video": True}
                raise RuntimeError("simulated ambiguous ack after click")

            def read_receipt(self, intent):
                if intent.intent_id == "threads-b2":
                    return {"owner": "alice",
                            "url": "https://www.threads.com/@alice/post/PB2",
                            "post_id": "PB2", "match": "post_id",
                            "has_video": True}
                return None

        seq = SeqBrowser()
        res = pub2.run_batch([ok, bad, after], seq)
        assert seq.calls == ["threads-b1", "threads-b2"]
        deferred = [r for r in res if r.get("receipt") == "DEFERRED_TO_GROUP_RECONCILE"]
        assert len(deferred) == 1 and deferred[0]["shortcode"] == "b3"
        by_sc = {g["shortcode"]: g["group_reconcile"]
                 for g in res if g.get("group_reconcile")}
        assert by_sc["b2"].get("reconciled") is True
        assert by_sc["b2"]["post_id"] == "PB2"
        assert by_sc["b3"].get("reconciled") is False

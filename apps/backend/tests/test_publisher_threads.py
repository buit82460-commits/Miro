"""Mock-browser tests: no real Post. Run: python -m pytest tests -q"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.publishing.publisher import Intent, Publisher


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
        return {"owner": intent.owner, "url": f"https://threads.test/@{intent.owner}/post/P{n}",
                "post_id": f"P{n}", "tag": intent.tag, "has_video": True}

    def read_receipt(self, intent):
        self.touches += 1
        return self.receipts.get(intent.intent_id)


def test_two_workers_one_intent_only_one_sends(tmp_path):
    pub = Publisher(tmp_path)
    intent = Intent(intent_id="i1", owner="alice", text="hello #dub000001", tag="#dub000001")
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


def test_crash_after_post_restart_keeps_attempt(tmp_path):
    pub = Publisher(tmp_path)
    intent = Intent(intent_id="i2", owner="alice", text="crash test #dub000002", tag="#dub000002")
    crashing = MockBrowser(crash_after_post=True)
    out = pub.publish(intent, crashing)
    assert out.get("receipt") == "UNKNOWN"
    journal = tmp_path / "attempts" / "i2.json"
    assert journal.exists()
    # restart: same intent must NOT resend; goes to reconcile only
    pub2 = Publisher(tmp_path)
    retry = pub2.publish(intent, MockBrowser())
    assert retry.get("skipped") == "UNRECONCILED_ATTEMPT"
    # reconcile read-only promotes with verified receipt, 0 Post clicks
    reader = MockBrowser(receipts={"i2": {"owner": "alice",
        "url": "https://threads.test/@alice/post/P9", "post_id": "P9",
        "tag": "#dub000002", "has_video": True}})
    rec = pub2.reconcile(intent, reader)
    assert rec.get("reconciled") is True and rec.get("post_id") == "P9"


def test_old_unknown_batch_into_reconcile_zero_browser_post(tmp_path):
    pub = Publisher(tmp_path)
    intents = [Intent(intent_id=f"old{i}", owner="alice", text=f"t{i} #dub0000{i}",
                      tag=f"#dub0000{i}") for i in (3, 4)]
    for it in intents:
        out = pub.publish(it, MockBrowser(crash_after_post=True))
        assert out.get("receipt") == "UNKNOWN"
    posts_before = 0
    reader = MockBrowser(receipts={
        "old3": {"owner": "alice", "url": "https://threads.test/@alice/post/P3",
                 "post_id": "P3", "tag": "#dub00003", "has_video": True},
        # old4 stays unconfirmed
    })
    results = [pub.reconcile(it, reader) for it in intents]
    assert results[0].get("reconciled") is True
    assert results[1].get("reconciled") is False
    assert reader.posts == posts_before == 0, "reconcile must never click Post"

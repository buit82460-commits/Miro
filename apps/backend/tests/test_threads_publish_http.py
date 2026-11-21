"""HTTP khép kín POST /threads/publish → ThreadsWorker.run_batch.

Fake tab trong bộ nhớ, 0 post thật: dry-run mặc định không submit;
allow_post=true kèm approval còn hiệu lực mới chạy post (fake ack).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from miro.main import app  # noqa: E402
from miro.threads.flow import approve_intent  # noqa: E402
from miro.publishing.publisher import Intent  # noqa: E402

client = TestClient(app)
_stamp = str(int(time.time() * 1000) % 1000000)


def _body(**extra):
    tag_no = "".join(c for c in extra.get("attempt_id", "0") if c.isdigit()) or "0"
    base = {
        "publication_id": f"http-pub-{_stamp}",
        "attempt_id": "att-1",
        "render_id": "render-1",
        "channel": "threads",
        "text": f"bài http {extra.get('attempt_id', 'x')} #dub417888",
        "owner": "alice",
        "shortcode": f"http-{extra.get('attempt_id', 'x')}",
        "tag": "#dub417888",
    }
    base.update(extra)
    base["text"] = f"bài http {base['attempt_id']} #dub417888"
    base["shortcode"] = f"http-{base['attempt_id']}"
    return base


def test_publish_defaults_to_dry_run_zero_post():
    res = client.post("/threads/publish", json=_body(attempt_id="att-dry"))
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["worker"]["results"][0].get("dry_run") is True
    assert data.get("posted_fake") == []


def test_publish_allow_post_without_approval_denied():
    res = client.post("/threads/publish",
                      json=_body(attempt_id="att-noappr", allow_post=True))
    assert res.status_code == 201, res.text
    data = res.json()
    first = data["worker"]["results"][0]
    assert first.get("error") in ("APPROVAL_REQUIRED", "FAILED_BEFORE_POST")


def test_publish_allow_post_with_approval_runs_fake_post_only():
    body = _body(attempt_id=f"att-ok-{_stamp}", allow_post=True, revision=7)
    intent = Intent(intent_id=f"threads-{body['shortcode']}", owner=body["owner"],
                    text=body["text"], tag=body["tag"],
                    shortcode=body["shortcode"])
    body["approval"] = approve_intent(intent, 7)
    res = client.post("/threads/publish", json=body)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data.get("posted_fake") == [body["shortcode"]]
    first = data["worker"]["results"][0]
    assert first.get("posted") is True
    assert first.get("receipt") == "UNCONFIRMED_NO_REPLAY"

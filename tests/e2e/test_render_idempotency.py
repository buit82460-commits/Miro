"""E2E: render idempotency theo contracts/render.json (khung, cần backend chạy)."""

import urllib.request
import json

BASE = "http://localhost:8000"


def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_render_idempotent_same_content_replays():
    body = {
        "request_id": "e2e-req-1",
        "project_id": "e2e-proj",
        "expected_revision": 0,
        "content_hash": "abc123",
        "spec": {},
    }
    s1, r1 = post("/renders", body)
    assert s1 == 201
    s2, r2 = post("/renders", body)
    assert s2 == 201 and r2["replayed"] is True
    assert r1["render_id"] == r2["render_id"]


def test_render_same_id_different_content_conflicts():
    body = {
        "request_id": "e2e-req-2",
        "project_id": "e2e-proj",
        "expected_revision": 0,
        "content_hash": "aaa",
        "spec": {},
    }
    assert post("/renders", body)[0] == 201
    body["content_hash"] = "bbb"
    status, _ = post("/renders", body)
    assert status == 409

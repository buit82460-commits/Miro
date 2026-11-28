"""Slice 04: UI doc lap doc task moi + runtime status (read-only).

Khong dong den browser/bridge/media; chi doc TaskStore + wiring redacted.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from miro.main import app  # noqa: E402
from miro.tasks.models import TaskSubmitRequest  # noqa: E402

client = TestClient(app)


def _payload(rid, msg="kiem tra tai khoan tiktok dang nhap"):
    return TaskSubmitRequest.model_validate({
        "request_id": rid,
        "message": msg,
        "videos": [{"project_id": rid, "title": "Video " + rid}]})


def test_recent_lists_submitted_tasks():
    svc = app.state.task_service
    rec = svc.submit(_payload("slice04-recent-1"))
    res = client.get("/tasks/recent?limit=100")
    assert res.status_code == 200, res.text
    # DB production dung chung giua cac lan chay: loc theo request_id
    # thay vi doi task moi nhat nam trong top-5.
    got = [t for t in res.json()
           if t.get("request_id") == "slice04-recent-1"]
    assert got and got[0]["id"] == rec["id"], res.text[:500]


def test_runtime_status_redacts_credentials():
    res = client.get("/tasks/runtime/status")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["be"]["status"] == "ok"
    blob = res.text
    assert "miro-" not in blob  # khong lo backend-key tho
    assert body["wiring"]["wiring"] == "bridge_config"


def test_recent_does_not_change_state():
    svc = app.state.task_service
    rec = svc.submit(_payload("slice04-recent-2"))
    before = svc.get(rec["id"])["status"]
    client.get("/tasks/recent?limit=5")
    assert svc.get(rec["id"])["status"] == before

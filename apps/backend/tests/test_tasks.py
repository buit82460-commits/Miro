"""Proof tests: idempotent submit, two-phase stop, restart states, permissions."""
from __future__ import annotations

import asyncio

import pytest

from miro.permissions.store import PermissionError, PermissionStore
from miro.storage.db import TaskStore
from miro.tasks.models import TaskSubmitRequest
from miro.tasks.service import FakeRemote, TaskConflictError, TaskService


def make_service(tmp_path, remote=None):
    store = TaskStore(tmp_path / "tasks.db")
    return TaskService(store, PermissionStore(), remote or FakeRemote())


def payload(**kw):
    base = {"request_id": "req-1", "message": "zoom nhe",
            "videos": [{"project_id": "proj-1", "title": "Video A"}]}
    base.update(kw)
    return TaskSubmitRequest.model_validate(base)


def test_same_request_id_returns_same_job(tmp_path):
    svc = make_service(tmp_path)
    first = svc.submit(payload())
    second = svc.submit(payload())
    assert second["id"] == first["id"]
    with pytest.raises(TaskConflictError) as exc:
        svc.submit(payload(message="khac"))
    assert exc.value.code == "REQUEST_ID_CONFLICT"


def test_stop_distinguishes_requested_from_worker_stopped(tmp_path):
    svc = make_service(tmp_path)
    record = svc.submit(payload())
    stopped_req = svc.request_stop(record["id"])
    assert stopped_req["status"] == "stop_requested"
    assert stopped_req["worker_stopped"] is False
    # idempotent second request: still requested, worker not stopped
    again = svc.request_stop(record["id"])
    assert again["status"] == "stop_requested" and again["worker_stopped"] is False
    final = svc.acknowledge_worker_stopped(record["id"])
    assert final["status"] == "stopped"
    assert final["worker_stopped"] is True
    events = svc.store.events(record["id"])
    types = [e["type"] for e in events]
    assert "stop_requested" in types and "worker_stopped" in types


@pytest.mark.asyncio
async def test_restart_shows_correct_state(tmp_path):
    svc = make_service(tmp_path)
    record = svc.submit(payload())
    # import/track/assemble bump the remote 1->4, so apply runs at revision 4:
    # approval must bind to exactly that revision.
    svc.permissions.grant(record["id"], 0, "edit", revision=4)
    done = await svc.run(record["id"])
    assert done["status"] == "completed"
    # restart on terminal task: unchanged
    assert svc.restart(record["id"])["status"] == "completed"

    # in-flight task becomes needs_attention with RESTARTED
    svc2 = make_service(tmp_path / "second")
    rec2 = svc2.submit(payload(request_id="req-2"))
    rec2["status"] = "running"
    rec2["worker_owner"] = {"pid": 999999999, "created_at": 1.0}  # chu cu da chet
    svc2.store.upsert_task(rec2)
    out = svc2.restart(rec2["id"])
    assert out["status"] == "needs_attention"
    assert out["error"]["code"] == "RESTARTED"

    # chu cu con song (cung process) -> OWNERSHIP_UNKNOWN, khong replay
    rec2b = svc2.submit(payload(request_id="req-2b"))
    rec2b["status"] = "running"
    svc2.store.upsert_task(rec2b)
    out2 = svc2.restart(rec2b["id"])
    assert out2["error"]["code"] == "OWNERSHIP_UNKNOWN"

    # unknown mutation blocks resume after restart
    remote = FakeRemote()
    remote.fail_unknown_on = "apply"
    svc3 = make_service(tmp_path / "third", remote)
    rec3 = svc3.submit(payload(request_id="req-3"))
    svc3.permissions.grant(rec3["id"], 0, "edit", revision=4)
    out3 = await svc3.run(rec3["id"])
    assert out3["status"] == "needs_attention"
    assert out3["pending_mutation"]["step"] == "apply"
    with pytest.raises(TaskConflictError) as exc:
        svc3.resume(rec3["id"])
    assert exc.value.code == "REMOTE_RESULT_UNKNOWN"


def test_permissions_scope_revision_revoke(tmp_path):
    svc = make_service(tmp_path)
    record = svc.submit(payload())
    # wrong scope denied
    svc.permissions.grant(record["id"], 0, "read", revision=1)
    with pytest.raises(PermissionError) as exc:
        svc.permissions.check(record["id"], 0, "edit", 1)
    assert exc.value.code == "SCOPE_DENIED"
    # stale revision denied
    svc.permissions.grant(record["id"], 0, "edit", revision=1)
    with pytest.raises(PermissionError) as exc2:
        svc.permissions.check(record["id"], 0, "edit", 2)
    assert exc2.value.code == "STALE_REVISION"
    # revoke blocks
    svc.permissions.revoke(record["id"], 0)
    with pytest.raises(PermissionError) as exc3:
        svc.permissions.check(record["id"], 0, "edit", 1)
    assert exc3.value.code == "APPROVAL_REQUIRED"

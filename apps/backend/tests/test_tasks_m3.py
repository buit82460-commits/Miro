"""M3 phan 1: workerOwner liveness, retry TRANSIENT co ngan sach, stop watchdog.

Test that trong C (FakeRemote + psutil that), khong can Chrome/Post that.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from miro.storage.db import TaskStore
from miro.tasks.models import TaskSubmitRequest
from miro.tasks.service import FakeRemote, TaskConflictError, TaskService


def make_service(tmp_path, remote=None, **kw):
    store = TaskStore(tmp_path / "tasks.db")
    return TaskService(store, None, remote or FakeRemote(), **kw)


def payload(**kw):
    base = {"request_id": "req-1", "message": "zoom nhe",
            "videos": [{"project_id": "proj-1", "title": "Video A"}]}
    base.update(kw)
    return TaskSubmitRequest.model_validate(base)


def test_worker_owner_recorded_on_submit_and_run(tmp_path):
    svc = make_service(tmp_path)
    rec = svc.submit(payload())
    assert rec["worker_owner"]["pid"] == os.getpid()
    assert rec["worker_owner"]["created_at"] > 0
    svc.permissions.grant(rec["id"], 0, "edit", revision=4)
    done = asyncio.run(svc.run(rec["id"]))
    assert done["worker_owner"]["pid"] == os.getpid()


def test_restart_owner_alive_blocks(tmp_path):
    svc = make_service(tmp_path)
    rec = svc.submit(payload())
    rec["status"] = "running"  # gia lap dang chay khi crash
    svc.store.upsert_task(rec)
    out = svc.restart(rec["id"])  # chu cu = chinh process nay -> con song
    assert out["status"] == "needs_attention"
    assert out["error"]["code"] == "OWNERSHIP_UNKNOWN"


def test_restart_owner_dead_recovers_auto(tmp_path):
    svc = make_service(tmp_path)
    rec = svc.submit(payload())
    rec["status"] = "running"
    rec["worker_owner"] = {"pid": 999999999, "created_at": 1.0}  # pid khong ton tai
    svc.store.upsert_task(rec)
    out = svc.restart(rec["id"])
    # T5: chu chet + job sach + con budget -> RECOVER tu dong (queued)
    assert out["status"] == "queued"
    assert out["retry_count"] == 1


@pytest.mark.asyncio
async def test_retry_transient_readonly_within_budget(tmp_path):
    remote = FakeRemote()
    remote.fail_transient = {"import": {"code": "REMOTE_TIMEOUT", "times": 2}}
    svc = make_service(tmp_path, remote)
    rec = svc.submit(payload())
    svc.permissions.grant(rec["id"], 0, "edit", revision=4)  # retry fail khong bump revision
    done = await svc.run(rec["id"])
    assert done["status"] == "completed"
    assert done["retry_count"] == 2
    assert remote.calls.count("import") == 1  # chi 1 side-effect that


@pytest.mark.asyncio
async def test_retry_exhausted_budget_blocks(tmp_path):
    remote = FakeRemote()
    remote.fail_transient = {"import": {"code": "REMOTE_503", "times": 10}}
    svc = make_service(tmp_path, remote)
    rec = svc.submit(payload())
    svc.permissions.grant(rec["id"], 0, "edit", revision=4)
    done = await svc.run(rec["id"])
    assert done["status"] == "needs_attention"
    assert done["error"]["code"] == "REMOTE_503"
    assert done["retry_count"] == 2  # 1 try + 2 retry = MAX_ATTEMPTS 3


@pytest.mark.asyncio
async def test_no_retry_on_mutation_step(tmp_path):
    remote = FakeRemote()
    remote.fail_transient = {"apply": {"code": "REMOTE_TIMEOUT", "times": 1}}
    svc = make_service(tmp_path, remote)
    rec = svc.submit(payload())
    svc.permissions.grant(rec["id"], 0, "edit", revision=4)
    done = await svc.run(rec["id"])
    assert done["status"] == "needs_attention"
    assert done["retry_count"] == 0  # mutation khong replay


@pytest.mark.asyncio
async def test_stop_watchdog_forces_stopped(tmp_path):
    svc = make_service(tmp_path, stop_grace_seconds=0.05)
    rec = svc.submit(payload())
    rec["status"] = "running"
    svc.store.upsert_task(rec)
    svc.request_stop(rec["id"])
    # worker khong bao gio ack -> watchdog buoc STOPPED
    out = await svc.wait_stop(rec["id"])
    assert out["status"] == "stopped"
    assert out["worker_stopped"] is True
    events = svc.store.events(rec["id"])
    forced = [e for e in events if e["type"] == "worker_stopped"]
    assert forced and forced[0]["data"]["forced"] is True


@pytest.mark.asyncio
async def test_wait_stop_idempotent_and_409_without_request(tmp_path):
    svc = make_service(tmp_path)
    rec = svc.submit(payload())
    with pytest.raises(TaskConflictError) as exc:
        await svc.wait_stop(rec["id"])
    assert exc.value.code == "STOP_NOT_REQUESTED"
    rec["status"] = "stopped"
    rec["worker_stopped"] = True
    svc.store.upsert_task(rec)
    assert (await svc.wait_stop(rec["id"]))["status"] == "stopped"

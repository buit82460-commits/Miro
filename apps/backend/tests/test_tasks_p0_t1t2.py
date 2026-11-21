"""P0 tasks T1-T4 (port A studio_service.control_job/_start_render/_run_render).

T1: resume so snapshot-signature (CHECKPOINT_STALE khi timeline doi).
T2: dedupe (project, revision, preview) tra job cu thay vi tao job moi.
T3: retry PipelineError mang ma TRANSIENT (khong chi OSError tho).
T4: tu choi save_project(output) khi timeline doi giua render.
"""
from __future__ import annotations

import pytest

from miro.storage.db import TaskStore
from miro.tasks.models import TaskSubmitRequest
from miro.tasks.service import FakeRemote, TaskConflictError, TaskService


def _payload(**kw):
    base = {"request_id": "req-t", "message": "zoom nhe",
            "videos": [{"project_id": "proj-1", "title": "Video A"}]}
    base.update(kw)
    return TaskSubmitRequest.model_validate(base)


def _service(tmp_path, remote=None):
    return TaskService(TaskStore(tmp_path / "tasks.db"), None, remote or FakeRemote())


def test_T1_resume_stale_timeline_rejected(tmp_path):
    """Timeline doi giua checkpoint va resume -> CHECKPOINT_STALE."""
    svc = _service(tmp_path)
    rec = svc.submit(_payload())
    rec["status"] = "needs_attention"
    rec["worker_owner"] = {"pid": 999999999, "created_at": 1.0}
    svc.store.upsert_task(rec)
    # Gia lap timeline doi: remote revision tang (mutate tu step doc truoc).
    svc.remote.mutate("import", svc.remote.revision)
    with pytest.raises(TaskConflictError) as exc:
        svc.resume(rec["id"])
    assert exc.value.code == "CHECKPOINT_STALE"


def test_T1_resume_fresh_instance_same_db(tmp_path):
    """Instance moi tren cung DB: snapshot-signature duoc persist, resume van
    phat hien stale sau khi timeline doi."""
    svc = _service(tmp_path)
    rec = svc.submit(_payload())
    rec["status"] = "needs_attention"
    rec["worker_owner"] = {"pid": 999999999, "created_at": 1.0}
    svc.store.upsert_task(rec)
    fresh = TaskService(TaskStore(tmp_path / "tasks.db"))
    out = fresh.resume(rec["id"])  # chua doi -> resume duoc
    assert out["status"] == "queued"
    out["status"] = "needs_attention"  # gia lap crash lan nua
    # Gia lap timeline doi: them project vao record (persist tren DB chung).
    out["items"] = list(out["items"]) + [{"title": "Video B", "project_id": "proj-2",
                                          "status": "pending", "checkpoints": {}}]
    fresh.store.upsert_task(out)
    third = TaskService(TaskStore(tmp_path / "tasks.db"))
    with pytest.raises(TaskConflictError) as exc:
        third.resume(rec["id"])
    assert exc.value.code == "CHECKPOINT_STALE"


def test_T2_dedupe_same_project_revision_preview(tmp_path):
    """Cung (project, revision, preview), khac request_id -> tra job cu."""
    svc = _service(tmp_path)
    first = svc.submit(_payload(request_id="req-a"))
    second = svc.submit(_payload(request_id="req-b"))
    assert second["id"] == first["id"]
    # Revision doi -> timeline moi -> job moi.
    svc.remote.mutate("import", svc.remote.revision)
    third = svc.submit(_payload(request_id="req-c"))
    assert third["id"] != first["id"]

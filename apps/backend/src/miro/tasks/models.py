"""Task domain models: task / item / step / event / checkpoint.

Single unified contract, ported from D:/JARVIS-Assistant dubtool_tasks
(write-ahead markers, checkpoints, no replay of unknown writes) onto the
Python 3.12 + FastAPI + Pydantic + SQLite stack.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

IDENTIFIER = r"^[A-Za-z0-9_-]{1,160}$"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    STOP_REQUESTED = "stop_requested"
    STOPPED = "stopped"
    COMPLETED = "completed"
    AWAITING_REVIEW = "awaiting_review"
    NEEDS_ATTENTION = "needs_attention"


TERMINAL_STATUSES = frozenset({
    TaskStatus.STOPPED, TaskStatus.COMPLETED, TaskStatus.AWAITING_REVIEW,
})
ACTIVE_STATUSES = frozenset({
    TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.STOP_REQUESTED,
})


class TaskVideo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=100)
    project_id: str | None = Field(default=None, pattern=IDENTIFIER)
    source: str | None = Field(default=None, min_length=1, max_length=4096)
    clip_id: str | None = Field(default=None, pattern=IDENTIFIER)
    transcript: str = Field(default="", max_length=50000)

    @model_validator(mode="after")
    def _target(self):
        if bool(self.source) == bool(self.project_id):
            raise ValueError("Each video needs exactly one local source or project_id.")
        return self


class TaskSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    message: str = Field(min_length=1, max_length=4000)
    videos: list[TaskVideo] = Field(min_length=1, max_length=20)
    use_ai: bool = False
    handoff: bool = False
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    language: Literal["vi", "en", "zh"] = "vi"

    @model_validator(mode="after")
    def _validate(self):
        if not self.message.strip() or any(not v.title.strip() for v in self.videos):
            raise ValueError("Message and titles must not be blank.")
        ids = [v.project_id for v in self.videos if v.project_id]
        if len(ids) != len(set(ids)):
            raise ValueError("Do not edit the same project twice in one task.")
        return self


class TaskError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class TaskCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: str
    revision: int | None = None
    result: dict[str, Any] = Field(default_factory=dict)


class TaskEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = 0
    task_id: str
    sequence: int = Field(ge=1)
    timestamp: str = Field(default_factory=utc_now_iso)
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class TaskItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    project_id: str | None = None
    status: str = "pending"
    checkpoints: dict[str, TaskCheckpoint] = Field(default_factory=dict)


class WorkerOwner(BaseModel):
    """Chủ worker đã chạy job: pid + create_time để restart kiểm tra liveness.

    Port JARVIS jobs/runner.py `_run_autonomously` (workerOwner={pid, createdAt}).
    """

    model_config = ConfigDict(extra="forbid")

    pid: int
    created_at: float


class TaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    request_id: str
    fingerprint: str
    status: TaskStatus = TaskStatus.QUEUED
    revision: int = 1
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    error: TaskError | None = None
    pending_mutation: dict[str, Any] | None = None
    worker_stopped: bool = False
    worker_owner: WorkerOwner | None = None
    retry_count: int = 0
    stop_grace_seconds: float = 10.0
    items: list[TaskItem] = Field(default_factory=list)

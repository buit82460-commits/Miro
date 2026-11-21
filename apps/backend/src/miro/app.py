"""Miro backend app factory (Python 3.12 + FastAPI + Pydantic + SQLite)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI

from .permissions.store import PermissionStore
from .storage.db import TaskStore
from .tasks.router import router as tasks_router
from .tasks.service import FakeRemote, TaskService


def create_app(db_path: Path | None = None, remote: FakeRemote | None = None) -> FastAPI:
    app = FastAPI(title="Miro Backend")
    store = TaskStore(db_path or Path("miro-tasks.db"))
    service = TaskService(store, PermissionStore(), remote)
    app.state.task_service = service
    app.state.run_task = lambda coro: asyncio.ensure_future(coro)
    app.include_router(tasks_router)
    return app

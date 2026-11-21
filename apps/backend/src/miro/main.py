"""FastAPI application entrypoint (canonical — launcher chay miro.main:app)."""

import asyncio
from pathlib import Path

from fastapi import FastAPI

from miro.permissions.store import PermissionStore
from miro.routers import health, platforms, publisher, renders
from miro.storage.db import TaskStore
from miro.tasks.router import router as tasks_router
from miro.tasks.service import FakeRemote, TaskService
from miro.research import service as research_service
from miro.research.router import router as research_router
from miro.connections import router as connections_router

app = FastAPI(title="Miro API", version="0.1.0")

_task_store = TaskStore(Path(r"C:\Miro\var\tasks.db"))
_task_service = TaskService(_task_store, PermissionStore(), FakeRemote())
app.state.task_service = _task_service
app.state.run_task = lambda coro: asyncio.ensure_future(coro)
app.state.research_provider = research_service.NullProvider()

app.include_router(health.router)
app.include_router(tasks_router)
app.include_router(renders.router)
app.include_router(publisher.router)
app.include_router(platforms.router)
app.include_router(research_router)
app.include_router(connections_router.router)

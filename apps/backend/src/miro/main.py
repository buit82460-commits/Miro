"""FastAPI application entrypoint (canonical — launcher chay miro.main:app)."""

import asyncio
from pathlib import Path

from fastapi import FastAPI

from miro.permissions.store import PermissionStore
from miro.routers import health, platforms, publisher, renders, threads
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
app.include_router(threads.router)
app.include_router(platforms.router)
app.include_router(research_router)
app.include_router(connections_router.router)


def _init_threads_state() -> None:
    """State M2: Library + Renders + Publications + Publisher + audit + dry-run browser."""
    import os as _os

    from miro.library.service import LibraryService as _LibraryService
    from miro.library.store import LibraryStore as _LibraryStore
    from miro.publishing.publisher import Publisher as _Publisher
    from miro.storage.registry import PublicationStore as _PublicationStore
    from miro.storage.registry import RenderStore as _RenderStore
    from miro.threads.flow import AuditLog as _AuditLog

    var = Path(_os.environ.get("MIRO_BE_DB_DIR", r"C:\Miro\var"))
    base = Path(_os.environ.get("MIRO_THREADS_BASE", str(var / "threads" / "batch")))
    attempts = Path(_os.environ.get("MIRO_THREADS_ATTEMPTS",
                                    str(var / "threads" / "social-attempts")))
    base.mkdir(parents=True, exist_ok=True)
    attempts.mkdir(parents=True, exist_ok=True)
    _library = _LibraryService(_LibraryStore(var / "threads-library.db"))
    _renders = _RenderStore(var / "threads-renders.db")
    _publications = _PublicationStore(var / "threads-publications.db")
    app.state.threads_services = (_library, _renders, _publications)
    app.state.threads_base = str(base)
    app.state.threads_attempts = str(attempts)
    app.state.threads_publisher = _Publisher(
        base, attempts_dir=attempts, require_approval=True)
    app.state.threads_browser = None  # gắn ManagedChromeSession/browser thật khi chạy live
    app.state.threads_audit = _AuditLog(var / "threads" / "audit.jsonl")


_init_threads_state()

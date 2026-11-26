"""FastAPI application entrypoint (canonical — launcher chay miro.main:app)."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from miro.permissions.store import PermissionStore
from miro.routers import health, platforms, publisher, renders, threads
from miro.routers import studio as studio_router
from miro.routers import projects as projects_router
from miro.routers import desktop as desktop_router
from miro.routers import schedule as schedule_router
from miro.storage.db import TaskStore
from miro.tasks.router import router as tasks_router
from miro.tasks.service import FakeRemote, TaskService
from miro.research import service as research_service
from miro.research.router import router as research_router
from miro.connections import router as connections_router


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup sweep best-effort: don workspace job chet sau restart.

    Khong chan boot: moi loi deu swallow. Chi goi 1 lan/khoi dong.
    """
    try:
        from miro import media_intel as _mi
        res = _mi.sweep_stale_workspaces()
        app.state.media_sweep = res
    except Exception:
        app.state.media_sweep = {"swept": [], "kept": [],
                                 "note": "sweep skipped (best-effort)"}
    yield


app = FastAPI(title="Miro API", version="0.1.0",
                lifespan=_lifespan)

_task_store = TaskStore(Path(r"C:\Miro\var\tasks.db"))
_task_service = TaskService(_task_store, PermissionStore(), FakeRemote())


def _init_bridge_wiring() -> dict:
    """Production wiring Slice 02: nap Bridge config tu trusted runtime.

    Env MIRO_BRIDGE_* uu tien; instance resolve tu trusted file theo
    Profile 20. Thieu backend_key/session -> wiring INCOMPLETE (fail-closed,
    khong khoi tao gia). Credential tho chi o app.state.bridge_auth,
    khong log.
    """
    try:
        from miro.tasks.bridge_config import load_bridge_config
        loaded = load_bridge_config(profile_directory="Profile 20")
        auth = loaded.get("auth") or {}
        _task_service.bridge = {
            "base": auth.get("base") or "",
            "instance_id": auth.get("instance_id") or "",
            "backend_key": auth.get("backend_key") or "",
            "session_id": auth.get("session_id") or "",
            "token": auth.get("token") or "",
        }
        ok = bool(auth.get("backend_key") and auth.get("instance_id"))
        return {"ok": ok, "wiring": "bridge_config",
                "redacted": loaded.get("redacted"),
                "reason": "" if ok else "BRIDGE_WIRING_INCOMPLETE"}
    except Exception as exc:
        return {"ok": False, "wiring": "bridge_config",
                "reason": "BRIDGE_WIRING_FAILED: " + type(exc).__name__}


app.state.task_service = _task_service
app.state.bridge_wiring = _init_bridge_wiring()
app.state.run_task = lambda coro: asyncio.ensure_future(coro)
app.state.research_provider = research_service.NullProvider()
try:
    from miro.research.media_provider import MediaIntelProvider
    app.state.research_provider = MediaIntelProvider()
except Exception:
    pass

app.include_router(health.router)
app.include_router(tasks_router)
app.include_router(renders.router)
app.include_router(publisher.router)
app.include_router(threads.router)
app.include_router(platforms.router)
app.include_router(studio_router.router)
app.include_router(projects_router.router)
app.include_router(desktop_router.router)
app.include_router(schedule_router.router)
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
    try:  # boot wiring: nap plan da persist (song restart BE), respect mac dinh
        from miro.scheduling.store import load_plan as _load_day_plan
        _persisted = _load_day_plan()
        if isinstance(_persisted, dict):
            app.state.threads_publisher.day_plan = _persisted
    except Exception:
        pass
    app.state.threads_browser = None  # gắn ManagedChromeSession/browser thật khi chạy live
    app.state.threads_audit = _AuditLog(var / "threads" / "audit.jsonl")


_init_threads_state()

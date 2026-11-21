"""Backward-compat alias: entrypoint duy nhat la miro.main:app.

Giu file nay vi mot so test/tool cu import miro.app; factory create_app
tra ve cung app canonical thay vi dung app rieng thieu router.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from .main import app


def create_app(db_path: Path | None = None, remote=None) -> FastAPI:
    if db_path is not None or remote is not None:
        from .permissions.store import PermissionStore
        from .storage.db import TaskStore
        from .tasks.service import FakeRemote, TaskService

        app.state.task_service = TaskService(
            TaskStore(db_path or Path(r"C:\Miro\var\tasks.db")),
            PermissionStore(), remote or FakeRemote())
    return app

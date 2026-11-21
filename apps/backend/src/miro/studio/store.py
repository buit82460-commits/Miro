"""Idempotent request store: same request_id returns same render_id."""
from __future__ import annotations

import hashlib
import threading


class IdempotentStore:
    """request_id -> result. Deterministic render_id = render-<sha16(request_id)>."""

    def __init__(self):
        self._guard = threading.RLock()
        self._results: dict[str, dict] = {}
        self._revisions: dict[str, int] = {}

    @staticmethod
    def render_id_for(request_id: str) -> str:
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:16]
        return f"render-{digest}"

    def get(self, request_id: str):
        with self._guard:
            result = self._results.get(request_id)
            return dict(result) if result else None

    def put(self, request_id: str, result: dict) -> dict:
        with self._guard:
            result = dict(result)
            result["render_id"] = self.render_id_for(request_id)
            result["request_id"] = request_id
            self._results[request_id] = dict(result)
            return dict(result)

    def check_revision(self, project_id: str, expected_revision):
        """Raise on stale revision. Returns current revision."""
        with self._guard:
            current = self._revisions.get(project_id, 0)
            if expected_revision is not None and expected_revision != current:
                error = ValueError(
                    f"Revision conflict for {project_id}: "
                    f"expected {expected_revision}, current {current}."
                )
                error.status_code = 409
                raise error
            return current

    def bump_revision(self, project_id: str) -> int:
        with self._guard:
            current = self._revisions.get(project_id, 0) + 1
            self._revisions[project_id] = current
            return current

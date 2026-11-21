"""Idempotency + revision store for Studio handlers.

Gaps vs B closed here (reader-jarvis §7.1 items 1, 2, 5):
1. fingerprint: same request_id + same content -> replay; same id + different
   content -> REQUEST_ID_CONFLICT (B: dubtool_tasks.py:196-209).
2. single slot per project + contamination lock (B: jobs/manager.py:215-244).
5. atomic persist (tmp + fsync + replace) for the on-disk cache so a crash
   between write-ahead and side effect cannot silently lose the record
   (B: dubtool_tasks.py:139-156).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path


class StudioConflict(ValueError):
    code = "REQUEST_ID_CONFLICT"

    def __init__(self, message: str):
        super().__init__(message)
        self.status_code = 409


class SlotBusy(StudioConflict):
    code = "SLOT_BUSY"

    def __init__(self, message: str):
        super().__init__(message)
        self.status_code = 409


class SlotContaminated(StudioConflict):
    code = "RESOURCE_CLEANUP_UNCLEAN"

    def __init__(self, message: str):
        super().__init__(message)
        self.status_code = 409


def fingerprint_of(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


class IdempotentStore:
    """request_id -> result. Deterministic render_id = render-<sha16(request_id)>."""

    def __init__(self, persist_dir: str | Path | None = None):
        self._guard = threading.RLock()
        self._results: dict[str, dict] = {}
        self._fingerprints: dict[str, str] = {}
        self._revisions: dict[str, int] = {}
        # Single active pipeline per video_id (B: 1 slot). video_id -> request_id.
        self._active: dict[str, str] = {}
        self._contaminated: set[str] = set()
        self._persist_dir = Path(persist_dir) if persist_dir else None
        if self._persist_dir:
            self._load()

    # ---- snapshot ----
    def _snapshot(self) -> dict:
        return {"results": self._results, "fingerprints": self._fingerprints,
                "revisions": self._revisions}

    def _load(self) -> None:
        path = self._persist_dir / "idempotency.json"
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self._results = data.get("results", {})
        self._fingerprints = data.get("fingerprints", {})
        self._revisions = data.get("revisions", {})

    def _save(self) -> None:
        if self._persist_dir:
            _atomic_write_json(self._persist_dir / "idempotency.json", self._snapshot())

    @staticmethod
    def render_id_for(request_id: str) -> str:
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:16]
        return f"render-{digest}"

    def check_fingerprint(self, request_id: str, payload: dict) -> dict | None:
        """Cache hit with content validation. Raises on id reuse with new content."""
        fingerprint = fingerprint_of(payload)
        with self._guard:
            cached = self._results.get(request_id)
            if cached is None:
                return None
            if self._fingerprints.get(request_id) != fingerprint:
                raise StudioConflict(
                    "request_id da dung voi noi dung khac (REQUEST_ID_CONFLICT).")
            cached = dict(cached)
            cached["idempotent_replay"] = True
            return cached

    def get(self, request_id: str):
        with self._guard:
            result = self._results.get(request_id)
            return dict(result) if result else None

    def put(self, request_id: str, payload: dict, result: dict) -> dict:
        with self._guard:
            result = dict(result)
            result["render_id"] = self.render_id_for(request_id)
            result["request_id"] = request_id
            result["fingerprint"] = fingerprint_of(payload)
            result["idempotent_replay"] = False
            self._results[request_id] = dict(result)
            self._fingerprints[request_id] = result["fingerprint"]
            self._save()
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
            self._save()
            return current

    def set_revision(self, project_id: str, revision: int) -> None:
        with self._guard:
            self._revisions[project_id] = revision
            self._save()

    # ---- single slot per project (B: manager.py:215-229) ----
    def acquire_slot(self, video_id: str, request_id: str) -> None:
        with self._guard:
            if video_id in self._contaminated:
                raise SlotContaminated(
                    f"Pipeline {video_id} bi khoa sau lan don dep that bai "
                    "(RESOURCE_CLEANUP_UNCLEAN). Kiem tra thu cong truoc khi chay lai.")
            owner = self._active.get(video_id)
            if owner is not None and owner != request_id:
                raise SlotBusy(
                    f"Pipeline {video_id} dang chay (slot don); cho xong roi chay lai.")
            self._active[video_id] = request_id

    def release_slot(self, video_id: str, request_id: str) -> None:
        with self._guard:
            if self._active.get(video_id) == request_id:
                del self._active[video_id]

    def mark_contaminated(self, video_id: str) -> None:
        """Cleanup failure: block new pipelines until manual inspection (B: 231-244)."""
        with self._guard:
            self._active.pop(video_id, None)
            self._contaminated.add(video_id)

    def clear_contamination(self, video_id: str) -> None:
        with self._guard:
            self._contaminated.discard(video_id)

    def is_contaminated(self, video_id: str) -> bool:
        with self._guard:
            return video_id in self._contaminated

    def active_count(self) -> int:
        with self._guard:
            return len(self._active)

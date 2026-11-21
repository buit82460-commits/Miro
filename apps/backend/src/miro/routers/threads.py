"""Threads router (M2) — nối Studio→Library→Renders→Publications→worker→adapter→lịch sử.

- POST /threads/prepare: nhập asset (Library dedupe sha256) + tạo render
  idempotent (RenderStore) + link asset↔render. Read-only với dubtool: không
  đụng submit_studio/timeline/handoff.
- POST /threads/approve: duyệt intent (bound fingerprint + revision), trả
  approval để worker/worker-gate dùng ở biên publish.
- POST /threads/publish: queue publication attempt (PublicationStore, key
  (publication_id, attempt_id)) + chạy worker. Mặc định dry-run/read-only:
  lượt đăng mới chỉ chạy khi allow_post=true KÈM approval còn hiệu lực.
- POST /threads/reconcile: UNKNOWN → reconcile read-only, không replay.
- GET /threads/history: mở đúng file render + đúng bài (Library trace +
  journal + publication queue), không suy đoán trạng thái đăng.

Entry point test luồng thật: POST /threads/run-batch trên bản sao dữ liệu
production (xem apps/backend/tests/test_threads_flow.py).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from miro.library.service import LibraryService
from miro.library.store import LibraryStore
from miro.browser.errors import RegistryError
from miro.storage.registry import PublicationStore, RenderStore
from miro.threads.flow import (
    ApprovalError,
    AuditLog,
    approve_intent,
    check_approval,
    check_secret_text,
    history_for,
    intent_fingerprint,
    prepare_publish,
)
from miro.threads.worker import ThreadsWorker

router = APIRouter(prefix="/threads", tags=["threads"])


class PrepareRequest(BaseModel):
    asset_path: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    content_hash: str = Field(min_length=1)
    spec: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ApproveRequest(BaseModel):
    text: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    shortcode: str = Field(min_length=1)
    revision: int = Field(ge=0)
    tag: str = ""
    media_sha256: str = ""
    media_path: str = ""
    approved_by: str = "user"


class PublishRequest(BaseModel):
    publication_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    render_id: str = Field(min_length=1)
    channel: str = Field(default="threads")
    approval: dict = Field(default_factory=dict)
    revision: int = Field(default=0)
    allow_post: bool = Field(default=False)
    text: str = ""
    owner: str = ""
    shortcode: str = ""
    tag: str = ""
    media_sha256: str = ""
    media_path: str = ""


class ReconcileRequest(BaseModel):
    text: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    shortcode: str = Field(min_length=1)
    tag: str = ""


def _services() -> tuple[LibraryService, RenderStore, PublicationStore]:
    from miro.main import app as _app

    return _app.state.threads_services  # type: ignore[attr-defined]


def _intent_of(body) -> object:
    from miro.publishing.publisher import Intent

    return Intent(
        intent_id=f"threads-{body.shortcode}", owner=body.owner,
        text=body.text, tag=body.tag,
        media_sha256=getattr(body, "media_sha256", "") or "",
        shortcode=body.shortcode,
        media_path=getattr(body, "media_path", "") or "")


@router.post("/prepare")
def prepare(body: PrepareRequest) -> dict:
    library, renders, _ = _services()
    try:
        return prepare_publish(
            library, renders, asset_path=body.asset_path,
            project_id=body.project_id, request_id=body.request_id,
            expected_revision=body.expected_revision,
            content_hash=body.content_hash, spec=body.spec, tags=body.tags)
    except (ApprovalError, ValueError) as exc:  # noqa: F821
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=str(exc)) from None


@router.post("/approve")
def approve(body: ApproveRequest) -> dict:
    intent = _intent_of(body)
    try:
        check_secret_text(intent.text)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=str(exc)) from None
    return approve_intent(intent, body.revision, approved_by=body.approved_by)


@router.post("/publish", status_code=status.HTTP_201_CREATED)
def publish(body: PublishRequest) -> dict:
    from miro.main import app as _app

    _, _, publications = _services()
    try:
        queued, replayed = publications.publish(
            body.publication_id, body.attempt_id, body.render_id, body.channel)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=str(exc)) from None
    intent = _intent_of(body)
    if not intent.text.strip():
        return {**queued, "replayed": replayed, "worker": {"skipped": "no-intent"}}
    publisher = _app.state.threads_publisher  # type: ignore[attr-defined]
    audit = _app.state.threads_audit  # type: ignore[attr-defined]
    worker = ThreadsWorker(publisher, audit=audit)
    fake_posts: list[str] = []

    class _FakePage:
        owner = intent.owner

        def verify_actor(self, owner):
            return str(owner or "").lower().lstrip("@") == intent.owner.lower()

        def submit(self, intent):
            fake_posts.append(intent.shortcode or intent.intent_id)
            url = f"https://www.threads.com/@{intent.owner}/post/FAKE"
            return {"ack_post_codes": [], "ack_via": "http-dry-run",
                    "ack_response_url": None, "observed_toasts": [],
                    "observed_responses": []}

        def read_eye(self, intent):
            return []

        def renew(self, ttl=300):
            return None

        def release(self):
            return None

    approvals = {}
    if isinstance(body.approval, dict) and body.approval:
        approvals[intent.intent_id] = body.approval
    try:
        out = worker.run_batch([intent], lambda: _FakePage(),
                               allow_post=bool(body.allow_post),
                               approvals=approvals, revision=body.revision)
    except (ApprovalError,) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"{exc.code}: {exc.message}") from None
    return {**queued, "replayed": replayed, "worker": out,
            "posted_fake": fake_posts}


@router.post("/reconcile")
def reconcile(body: ReconcileRequest) -> dict:
    from miro.main import app as _app

    publisher = _app.state.threads_publisher  # type: ignore[attr-defined]
    intent = _intent_of(body)
    return publisher.reconcile(intent, _app.state.threads_browser)  # type: ignore[attr-defined]


@router.get("/history")
def history(publication_id: str, render_id: str) -> dict:
    from miro.main import app as _app

    lib, _, pubs = _services()
    return history_for(
        lib, pubs, _app.state.threads_base,  # type: ignore[attr-defined]
        _app.state.threads_attempts,  # type: ignore[attr-defined]
        publication_id=publication_id, render_id=render_id)

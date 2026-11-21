"""Miro Threads flow (M2) — khép kín Studio→Library→Renders→Publications→worker→adapter→lịch sử.

Nguồn merge (chỉ đọc, không sửa code legacy):
- C:\\dubtool vòng M2 (reader-dubtool §8, commit 363b35d): journal trước click,
  UNKNOWN không replay, guard 2 lớp, tag #dub duy nhất, 1 CDP + 1 managed tab
  cả batch, ack 3 đường, phase B eye match cùng-record, Threads KHÔNG qua
  submit_studio/timeline/handoff (đường manifest→adapter→publication+journal).
- D:\\JARVIS-Assistant vòng M2 (reader-jarvis §10, commit 2318d37): approval bound
  fingerprint+revision (gắn gate tại Publisher.publish), REQUEST_ID_CONFLICT,
  write-ahead marker, receipt duyệt non-blocking, không suy đoán trạng thái đăng,
  secret không vào journal.

Mặc định dry-run/read-only: lượt đăng mới chỉ chạy khi có approval còn hiệu lực
bound đúng fingerprint+revision. Không có Chrome thật thì worker báo
CDP_UNAVAILABLE, không tự mở browser thay thế, không fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

THREADS_CHANNEL = "threads"
PUBLISH_SCOPE = "threads_post"

_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|passwd|password|cookie|ds_user_id|sessionid)\s*[:=]"
)


class ApprovalError(Exception):
    """Lỗi gate duyệt. `code`: APPROVAL_REQUIRED | STALE_REVISION |
    FINGERPRINT_CONFLICT | SECRET_REJECTED."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def intent_fingerprint(intent) -> str:
    """Fingerprint bound approval: sha256 canonical JSON của intent tại lúc duyệt.

    Thực thi recompute ở biên publish; intent đổi text/owner/media trong lúc
    chờ → lệch → từ chối (mẫu JARVIS dubtool_tasks REQUEST_ID_CONFLICT +
    approval one-shot bound, reader-jarvis §10.3/§10.5).
    """
    canonical = {
        "media_sha256": str(getattr(intent, "media_sha256", "") or ""),
        "media_path": str(getattr(intent, "media_path", "") or ""),
        "owner": str(getattr(intent, "owner", "") or ""),
        "shortcode": str(getattr(intent, "shortcode", "") or ""),
        "tag": str(getattr(intent, "tag", "") or ""),
        "text": str(getattr(intent, "text", "") or ""),
    }
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def check_secret_text(text: str) -> None:
    """Fail-closed: intent chứa secret thật → từ chối trước mọi side-effect.

    Journal/receipt/audit chỉ giữ text_sha256, không bao giờ giữ raw text
    (mẫu JARVIS runner sanitize + dubtool_tasks TASK_CONTAINS_SECRET).
    """
    if _SECRET_RE.search(str(text or "")):
        raise ApprovalError(
            "SECRET_REJECTED",
            "Intent chứa mẫu secret thật; từ chối đăng, không ghi journal.",
        )


def approve_intent(intent, revision: int, approved_by: str = "user") -> dict:
    """Duyệt intent: gắn fingerprint + revision tại thời điểm duyệt."""
    check_secret_text(getattr(intent, "text", ""))
    return {
        "scope": PUBLISH_SCOPE,
        "revision": int(revision),
        "fingerprint": intent_fingerprint(intent),
        "approved_by": approved_by,
        "approved_at": time.time(),
    }


def check_approval(approval: dict | None, intent, revision: int) -> dict:
    """Gate tại biên publish: SAU guard_duplicate + verify actor, TRƯỚC post_once.

    - Thiếu approval → APPROVAL_REQUIRED (deny mặc định, unknown → deny).
    - Sai scope → SCOPE_DENIED. Lệch revision → STALE_REVISION.
    - Lệch fingerprint (intent đổi trong lúc chờ) → FINGERPRINT_CONFLICT.
    """
    if not isinstance(approval, dict):
        raise ApprovalError("APPROVAL_REQUIRED", "Đăng Threads cần duyệt còn hiệu lực.")
    if approval.get("scope") != PUBLISH_SCOPE:
        raise ApprovalError(
            "SCOPE_DENIED",
            f"Approval scope '{approval.get('scope')}', cần '{PUBLISH_SCOPE}'.",
        )
    if int(approval.get("revision", -1)) != int(revision):
        raise ApprovalError(
            "STALE_REVISION",
            f"Approval gắn revision {approval.get('revision')}; hiện tại {revision}.",
        )
    want = str(approval.get("fingerprint") or "")
    got = intent_fingerprint(intent)
    if want != got:
        raise ApprovalError(
            "FINGERPRINT_CONFLICT",
            "Intent đổi sau khi duyệt; cần duyệt lại, không đăng bản cũ.",
        )
    check_secret_text(getattr(intent, "text", ""))
    return approval


def prepare_publish(library, renders, *, asset_path: str | Path, project_id: str,
                    request_id: str, expected_revision: int, content_hash: str,
                    spec: dict | None = None, tags: list[str] | None = None) -> dict:
    """Studio→Library→Renders: nhập asset (dedupe sha256) + tạo render idempotent
    + link asset↔render để truy 2 chiều. Không đụng M3."""
    asset = library.import_asset(asset_path, tags=list(tags or []))
    try:
        render, replayed = renders.create(
            request_id, project_id, expected_revision, content_hash, dict(spec or {}))
    except KeyError as exc:
        raise ApprovalError(
            "REQUEST_ID_CONFLICT",
            f"request_id đã dùng với nội dung khác (render {exc.args[0]}).",
        )
    library.link_usage(asset["id"], render["render_id"], project_id=project_id)
    return {"asset": asset, "render": render, "replayed": replayed}


def history_for(library, publications, publisher_base: str | Path,
                attempts_dir: str | Path, *, publication_id: str,
                render_id: str) -> dict:
    """Lịch sử: mở đúng file render + đúng bài.

    - asset↔render↔post qua LibraryService.trace_* (SQLite, persistent).
    - attempts: journal publisher ghi (submit/verified/unknown + url/post_id).
    - publication store: attempt queue (queued/replayed).
    Không suy đoán trạng thái đăng: chỉ verified có url readback mới là posted.
    """
    base = Path(publisher_base)
    attempts = Path(attempts_dir)
    trace_r = library.trace_render(render_id)
    trace_p = library.trace_post(publication_id)
    queue = publications.list_by_publication(publication_id)
    journals: list[dict] = []
    if attempts.is_dir():
        for journal_file in sorted(attempts.glob("threads-*.json")):
            try:
                data = json.loads(journal_file.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            journals.append({
                "file": journal_file.name,
                "shortcode": data.get("shortcode"),
                "status": data.get("status"),
                "url": data.get("url"),
                "post_id": data.get("post_id"),
            })
    assets: list[dict] = []
    for asset_id in trace_r.get("asset_ids", []):
        asset = library.store.get_by_id(asset_id)
        if asset is None:
            continue
        assets.append({
            "asset_id": asset_id, "path": asset["path"],
            "exists": Path(asset["path"]).is_file(), "sha256": asset["sha256"],
        })
    return {
        "publication_id": publication_id, "render_id": render_id,
        "assets": assets, "renders": trace_r.get("renders", []),
        "posts": trace_p.get("posts", []) or trace_r.get("posts", []),
        "queue": queue, "journals": journals,
    }


class AuditLog:
    """Receipt quyết định duyệt ghi batch non-blocking (mẫu JARVIS
    approval/__init__.py:180–218): queue đầy → đếm dropped, không chặn post."""

    def __init__(self, path: str | Path, batch_size: int = 20):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.batch_size = max(1, int(batch_size))
        self._pending: list[dict] = []
        self.dropped = 0

    def append(self, decision: dict) -> None:
        if len(self._pending) >= self.batch_size * 5:
            self.dropped += 1
            return
        self._pending.append({**decision, "at": time.time()})
        if len(self._pending) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        lines = "".join(
            json.dumps(d, ensure_ascii=False) + "\n" for d in self._pending)
        self._pending = []
        try:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(lines)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
        except OSError:
            self.dropped += 1

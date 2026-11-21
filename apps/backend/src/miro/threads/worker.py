"""Threads adapter chạy trên ManagedChromeSession (M2) — port hành vi legacy
C:\\dubtool\\scripts\\threads_post_one.py vào kiến trúc C.

- 1 CDP + 1 managed tab cả batch: item đầu acquire, item sau `renew(ttl=300)`
  + CONNECTION_REUSE; lỗi trong acquire → release rồi raise, không để lease treo
  (legacy :646-666, :811-817, :924-929).
- Verify actor @username trước mọi Post: ưu tiên callback inject
  (browser_use/verify_actor), fallback assert body chứa username khi read-only;
  mismatch → FAILED_BEFORE_POST, không post nhầm tài khoản (legacy :251-268).
- Phase A: journal submit TRƯỚC click mỗi item; ack 3 đường (toast Posted mới /
  network ack URL / composer-closed fallback) do browser cung cấp qua `submit()`.
- Dừng submit sau ack mơ hồ đầu tiên (UNKNOWN/disconnect → break, item sau
  KHÔNG submit; legacy :840-856); Phase B group reconcile 1 lần read-only.
- Batch cuối `release + disconnect` trong finally (DISCONNECT_CLOSE), disconnect
  giữa chừng → UNKNOWN, không reconnect/restart Chrome.

Browser là interface inject (`ThreadsPage`): production nối Playwright qua
ManagedChromeSession, test dùng fake. Adapter không tự connect CDP.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


class ThreadsPage(Protocol):
    """Interface một managed tab Threads. Production implement bằng page của
    ManagedChromeSession + Publisher của C; test dùng fake in-memory."""

    owner: str

    def verify_actor(self, owner: str) -> bool:
        ...

    def submit(self, intent) -> dict:
        """Post một intent: trả ack {ack_post_codes, ack_via, ack_response_url,
        observed_toasts, observed_responses} hoặc raise (before_submit=True →
        lỗi trước click; _is_disconnect → UNKNOWN)."""
        ...

    def read_eye(self, intent) -> list[dict]:
        """Read-only readback: eye records [{author, tag, url, post_id,
        has_video}] để phase B match cùng-record."""
        ...

    def renew(self, ttl: int = 300) -> None:
        ...

    def release(self) -> None:
        ...


@dataclass
class BatchReport:
    submitted: list[str]
    ambiguous: list[str]
    published: list[str]
    unknown: list[str]
    total_s: float


class ThreadsWorker:
    """Worker batch 2-phase (legacy run_batch :744-901) chạy trên Publisher C.

    - Publisher C đã có guard 2 lớp/journal/UNKNOWN/reconcile/DUPLICATE_TAGS
      (publishing/publisher.py, ĐẠT). Worker chỉ thêm: 1 tab cả batch (renew),
      verify actor trước Post, release/disconnect trong finally.
    - Mặc định dry-run: `allow_post=False` → mọi intent chạy read-only
      (guard + reconcile, 0 post_once). Lượt đăng mới chỉ khi allow_post=True
      KÈM approval gate đã pass ở Publisher.publish (JARVIS §10.5).
    """

    def __init__(self, publisher, audit=None):
        self.publisher = publisher
        self.audit = audit

    def _audit(self, decision: dict) -> None:
        if self.audit is not None:
            try:
                self.audit.append(decision)
            except Exception:
                pass

    def run_batch(self, intents: list, page_factory, *, allow_post: bool = False,
                  approvals: dict[str, dict] | None = None,
                  revision: int = 0) -> dict:
        """Chạy batch. `page_factory()` → ThreadsPage (đã acquire managed tab).

        Trả {results, report}. Disconnect → UNKNOWN + dừng, không reconnect.
        """
        from miro.threads.flow import ApprovalError, check_approval

        started = time.time()
        if not intents:
            return {"results": [], "report": {"submitted": [], "total_s": 0.0}}
        # Guard DUPLICATE_TAGS ca batch (A §8.7.2, giong Publisher.run_batch
        # :650-657): trung → dung ca batch, 0 post.
        _tag_counts: dict[str, int] = {}
        for _i in intents:
            _t = (getattr(_i, "tag", "") or "").lower()
            if _t:
                _tag_counts[_t] = _tag_counts.get(_t, 0) + 1
        _dupes = sorted(t for t, c in _tag_counts.items() if c > 1)
        if _dupes:
            return {"results": [{"batch": "threads-worker",
                                 "error": "DUPLICATE_TAGS", "tags": _dupes,
                                 "hint": "tag #dub trung nhau; dung ca batch, "
                                         "khong dang"}],
                    "report": {"submitted": [],
                               "total_s": round(time.time() - started, 1)}}
        try:
            page = page_factory()
        except Exception as exc:
            return {"results": [
                {"shortcode": getattr(i, "shortcode", "?"),
                 "receipt": "UNKNOWN", "cause": type(exc).__name__,
                 "hint": "CDP_UNAVAILABLE: no managed tab; never replay"}
                for i in intents]}
        results: list[dict] = []
        first = True
        try:
            for intent in intents:
                sc = getattr(intent, "shortcode", "") or getattr(intent, "intent_id", "?")
                if not allow_post:
                    out = self.publisher.reconcile(intent, _ReadOnlyBrowser(page))
                    results.append({"shortcode": sc, "dry_run": True, **out})
                    continue
                try:
                    if not page.verify_actor(intent.owner):
                        raise _BeforeSubmit("ACTOR_MISMATCH")
                    approval = (approvals or {}).get(
                        getattr(intent, "intent_id", "") or sc)
                    check_approval(approval, intent, revision)
                except ApprovalError as exc:
                    self._audit({"shortcode": sc, "decision": "denied",
                                 "code": exc.code, "message": exc.message})
                    results.append({"shortcode": sc, "error": exc.code,
                                    "hint": exc.message})
                    continue
                except Exception as exc:
                    if getattr(exc, "before_submit", False) or type(exc).__name__ in (
                            "ApprovalError", "_BeforeSubmit"):
                        results.append({"shortcode": sc,
                                        "error": "FAILED_BEFORE_POST",
                                        "cause": type(exc).__name__})
                        continue
                    raise
                self._audit({"shortcode": sc, "decision": "approved",
                             "revision": revision})
                if not first:
                    try:
                        page.renew(300)
                    except Exception as exc:
                        results.append({"shortcode": sc, "receipt": "UNKNOWN",
                                        "cause": type(exc).__name__,
                                        "hint": "renew failed; stopped submitting"})
                        break
                first = False
                try:
                    out = self.publisher.publish(
                        intent, _PostingBrowser(page),
                        approval=(approvals or {}).get(
                            getattr(intent, "intent_id", "") or sc),
                        revision=revision)
                except Exception as exc:
                    from miro.publishing.publisher import (
                        _is_disconnect as _is_disc,
                    )
                    journal_path = self.publisher.attempts / f"{intent.intent_id}.json"
                    try:
                        from miro.publishing.publisher import atomic_save as _save
                        _save(journal_path, {
                            "shortcode": sc, "account": intent.owner,
                            "status": "unknown", "at": time.time(),
                            "hint": "UNCONFIRMED_NO_REPLAY",
                            "cause": type(exc).__name__})
                    except Exception:
                        pass
                    results.append({"shortcode": sc, "receipt": "UNKNOWN",
                                    "cause": type(exc).__name__,
                                    "hint": "disconnect;" if _is_disc(exc) else
                                    "ambiguous ack after click; stopped submitting, "
                                    "group reconcile only"})
                    break  # dừng submit sau ack mơ hồ đầu tiên (legacy :840-856)
                results.append(out)
                if isinstance(out, dict) and out.get("receipt") in (
                        "UNKNOWN", "UNCONFIRMED_NO_REPLAY"):
                    break
            # Phase B: group reconcile 1 lan read-only (A §8.1) roi moi merge
            # publication cho item submitted-nhung-chua-verified.
            try:
                posted_sc = {r.get("shortcode") for r in results
                             if isinstance(r, dict) and r.get("posted")}
                pending = [i for i in intents
                           if (getattr(i, "shortcode", "") or
                               getattr(i, "intent_id", "?")) in posted_sc]
                reconciled_out = []
                if pending and hasattr(self.publisher, "reconcile"):
                    _ro = _ReadOnlyBrowser(page)
                    # 1 pass gom nhom read-only (A §8.1 phase B).
                    try:
                        _ro.read_group_receipts(pending)
                    except Exception:
                        pass
                    for _pi in pending:
                        try:
                            _rec = self.publisher.reconcile(_pi, _ro)
                        except Exception:
                            continue
                        if isinstance(_rec, dict) and _rec.get("reconciled"):
                            reconciled_out.append(_rec)
                if reconciled_out:
                    results.append({"phase": "B-group-reconcile",
                                    "reconciled": reconciled_out})
            except Exception:
                pass
        finally:
            try:
                page.release()
            except Exception:
                pass
            # Dong CDP sau release (docstring: "release + disconnect").
            _disc = getattr(page, "disconnect", None)
            if callable(_disc):
                try:
                    _disc()
                except Exception:
                    pass
        total_s = round(time.time() - started, 1)
        return {"results": results,
                "report": {"submitted": [r.get("shortcode") for r in results
                                        if r.get("posted")],
                           "total_s": total_s}}


class _BeforeSubmit(RuntimeError):
    before_submit = True


class _ReadOnlyBrowser:
    """Browser read-only cho dry-run/reconcile: post bị cấm tuyệt đối."""

    def __init__(self, page: ThreadsPage):
        self._page = page

    def post_once(self, intent):
        raise AssertionError("dry-run/read-only: không được post")

    def read_receipt(self, intent):
        return self._page.read_eye(intent)

    def read_group_receipts(self, intents):
        out = {}
        for intent in intents:
            try:
                records = self._page.read_eye(intent)
            except Exception:
                continue
            from miro.publishing.publisher import match_eye_records
            hit = match_eye_records(records, intent.owner, intent.tag,
                                    intent.text, [])
            if hit:
                out[intent.shortcode or intent.intent_id] = {
                    "owner": intent.owner, "url": hit["url"],
                    "post_id": hit.get("post_id"), "match": hit.get("match")}
        return out


class _PostingBrowser:
    """Browser post qua managed tab: journal-submit trước click do Publisher C
    giữ (claim_attempt O_CREAT|O_EXCL); ack do page.submit cung cấp."""

    def __init__(self, page: ThreadsPage):
        self._page = page
        self.owner = getattr(page, "owner", "")
        self.declared_actor = getattr(page, "owner", "")

    def verify_actor(self, owner):
        return self._page.verify_actor(owner)

    def post_once(self, intent):
        return self._page.submit(intent)

    def read_receipt(self, intent):
        return self._page.read_eye(intent)

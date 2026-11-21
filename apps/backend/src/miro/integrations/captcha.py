"""Captcha solver: PyPasser mặc định + OhMyCaptcha standby.

runtime:
  CaptchaSolver — wrapper mỏng quanh vendor/pypasser (đọc C:\\dubtool\\shared\\captcha_solver.py):
    sync solve + async asolve, cần opencv trong venv. KHÔNG cài vendor ở Miro,
    chỉ khai báo interface; solver thật được inject (page object + solve fns).
  OhmCaptchaStandby — service YesCaptcha-style self-host, STANDBY (không chạy
    mặc định, cần GPU/RAM). Wrapper chỉ kiểm tra cấu hình + forward job khi
    được bật tường minh.
input:  CaptchaJob(kind, page_ref, params).
output: {"ok": bool, "kind": str, "elapsed_s": float, "via": "pypasser"|"ohmycaptcha"}.
errors:  CAPTCHA_UNSUPPORTED_KIND | CAPTCHA_SOLVER_MISSING |
         CAPTCHA_SOLVE_FAILED | CAPTCHA_POLICY_DENIED.
Policy (giữ từ dubtool): NEVER auto-solve khi chưa có task xác nhận — caller
  phải truyền confirmed=True; mọi lần solve đều journal qua callback.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from .base import IntegrationError


SOLVERS_AVAILABLE = (
    "recaptcha-v2",
    "recaptcha-v3",
    "turnstile",
    "geetest-v4",
    "arcaptcha",
    "lemin",
)


class CaptchaJob(BaseModel):
    kind: str = Field(min_length=1, max_length=32)
    page_ref: str = Field(default="", max_length=500)
    params: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class CaptchaSolver:
    """PyPasser wrapper. solve_fn/asolve_fn inject từ runtime có vendor thật."""

    def __init__(
        self,
        solve_fn: Callable[..., Any] | None = None,
        asolve_fn: Callable[..., Any] | None = None,
        journal: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._solve_fn = solve_fn
        self._asolve_fn = asolve_fn
        self._journal = journal or (lambda entry: None)

    def _guard(self, job: CaptchaJob) -> None:
        if job.kind not in SOLVERS_AVAILABLE:
            raise IntegrationError(
                "CAPTCHA_UNSUPPORTED_KIND",
                f"Loại captcha chưa hỗ trợ: {job.kind} (có: {SOLVERS_AVAILABLE})",
            )
        if not job.confirmed:
            raise IntegrationError(
                "CAPTCHA_POLICY_DENIED",
                "Từ chối auto-solve: task chưa xác nhận (confirmed=False).",
            )
        if self._solve_fn is None and self._asolve_fn is None:
            raise IntegrationError(
                "CAPTCHA_SOLVER_MISSING",
                "PyPasser chưa sẵn sàng (thiếu opencv/solver fn).",
            )

    def solve(self, job: CaptchaJob, page: Any = None) -> dict[str, Any]:
        self._guard(job)
        if self._solve_fn is None:
            raise IntegrationError("CAPTCHA_SOLVER_MISSING", "Chưa gắn solve_fn đồng bộ.")
        started = time.time()
        try:
            self._solve_fn(job.kind, page, **job.params)
        except IntegrationError:
            raise
        except Exception as exc:
            self._journal({"kind": job.kind, "ok": False, "err": str(exc)[:200]})
            raise IntegrationError("CAPTCHA_SOLVE_FAILED", f"Giải thất bại: {exc}") from exc
        elapsed = round(time.time() - started, 2)
        self._journal({"kind": job.kind, "ok": True, "elapsed_s": elapsed, "via": "pypasser"})
        return {"ok": True, "kind": job.kind, "elapsed_s": elapsed, "via": "pypasser"}

    async def asolve(self, job: CaptchaJob, page: Any = None) -> dict[str, Any]:
        self._guard(job)
        fn = self._asolve_fn or self._solve_fn
        if fn is None:  # pragma: no cover - guard đã chặn
            raise IntegrationError("CAPTCHA_SOLVER_MISSING", "Chưa gắn solver fn.")
        started = time.time()
        try:
            res = fn(job.kind, page, **job.params)
            if hasattr(res, "__await__"):
                await res
        except IntegrationError:
            raise
        except Exception as exc:
            self._journal({"kind": job.kind, "ok": False, "err": str(exc)[:200]})
            raise IntegrationError("CAPTCHA_SOLVE_FAILED", f"Giải thất bại: {exc}") from exc
        elapsed = round(time.time() - started, 2)
        self._journal({"kind": job.kind, "ok": True, "elapsed_s": elapsed, "via": "pypasser"})
        return {"ok": True, "kind": job.kind, "elapsed_s": elapsed, "via": "pypasser"}


class OhmCaptchaStandby:
    """OhMyCaptcha ở chế độ standby: chỉ forward khi url được cấu hình + enabled."""

    def __init__(self, base_url: str = "", *, enabled: bool = False,
                 http_client: Any = None) -> None:
        self._url = base_url.rstrip("/")
        self._enabled = enabled
        self._http = http_client

    def status(self) -> dict[str, Any]:
        return {"standby": True, "enabled": self._enabled,
                "url_set": bool(self._url), "url": self._url or "OHMYCAPTCHA_URL unset"}

    async def submit(self, image_b64: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            raise IntegrationError("CAPTCHA_POLICY_DENIED", "Từ chối: task chưa xác nhận.")
        if not self._enabled or not self._url:
            raise IntegrationError(
                "CAPTCHA_SOLVER_MISSING",
                "OhMyCaptcha đang standby (chưa cấu hình/enable OHMYCAPTCHA_URL).",
            )
        if self._http is None:  # pragma: no cover - cần wiring runtime thật
            raise IntegrationError("CAPTCHA_SOLVER_MISSING", "Chưa gắn http client cho standby.")
        async with self._http() as client:
            resp = await client.post(f"{self._url}/solve", json={"image": image_b64})
        if getattr(resp, "status_code", 200) != 200:
            raise IntegrationError("CAPTCHA_SOLVE_FAILED", "Standby solver trả lỗi HTTP.")
        return {"ok": True, "kind": "image-classify", "elapsed_s": 0.0, "via": "ohmycaptcha"}

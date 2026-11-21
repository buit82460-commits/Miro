"""Adapter browser-use / live-chrome (existing CDP, no launch).

runtime (2 mode, port từ JARVIS live_chrome.py + research/repos/browser-use):
  live   — gắn vào Chrome đang chạy qua CDP (tabs/bind/read), KHÔNG launch
    Chrome mới, KHÔNG copy profile, KHÔNG tự kết nối lại khi gặp hộp Allow.
    Lease theo miro.browser.lease_store (1 owner / tab).
  automate — job browser-use có lease (navigate/act/extract trong TTL lease);
    driver inject được để test mock.
input:  BindRequest(browser_id/target ids/profile/account) | ReadTabRequest |
        AutomateRequest(actions, lease).
output: live: {"tabs"|"binding_id"|"content", "mode": "existing_cdp"} ;
  automate: {"steps": [...], "extracted": {...}}.
errors:  BROWSER_BUSY | BROWSER_LEASE_LOST | BROWSER_ACTION_FAILED |
         BROWSER_RUNTIME_MISSING.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .base import IntegrationError


class BindRequest(BaseModel):
    browser_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_id: str = Field(min_length=1, max_length=128)
    profile_target_id: str = Field(min_length=1, max_length=128)
    profile_directory: str = Field(pattern=r"^(Default|Profile [0-9]{1,5})$")
    account_id: str = Field(pattern=r"^[0-9]{1,30}$")


class ReadTabRequest(BaseModel):
    binding_id: str = Field(min_length=1, max_length=64)
    max_chars: int = Field(default=12000, ge=1, le=30000)


class AutomateRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    actions: list[str] = Field(default_factory=list, max_length=50)
    max_steps: int = Field(default=20, ge=1, le=200)


class BrowserUseAdapter:
    """Existing-CDP live read + automate có lease. Driver inject để mock."""

    def __init__(self, driver: Any = None) -> None:
        self._driver = driver
        self._bindings: dict[str, dict[str, Any]] = {}

    def _need_driver(self) -> Any:
        if self._driver is None:
            raise IntegrationError("BROWSER_RUNTIME_MISSING", "Chưa gắn browser driver.")
        return self._driver

    async def tabs(self) -> dict[str, Any]:
        d = self._need_driver()
        try:
            tabs = await d.tabs()
        except IntegrationError:
            raise
        except Exception as exc:
            raise IntegrationError("BROWSER_ACTION_FAILED", f"tabs thất bại: {exc}") from exc
        return {"tabs": tabs, "mode": "existing_cdp", "adapter": "playwright_cdp"}

    async def bind(self, req: BindRequest) -> dict[str, Any]:
        d = self._need_driver()
        try:
            result = await d.bind(req.model_dump())
        except IntegrationError:
            raise
        except Exception as exc:
            raise IntegrationError("BROWSER_ACTION_FAILED", f"bind thất bại: {exc}") from exc
        import uuid
        binding_id = str(uuid.uuid4())
        self._bindings[binding_id] = req.model_dump()
        return {**dict(result or {}), "binding_id": binding_id,
                "capability": "READ", "mode": "existing_cdp"}

    async def read(self, req: ReadTabRequest) -> dict[str, Any]:
        binding = self._bindings.get(req.binding_id)
        if binding is None:
            raise IntegrationError("BROWSER_LEASE_LOST", "Binding không tồn tại — gắn lại tab.")
        d = self._need_driver()
        try:
            result = await d.read(binding, req.max_chars)
        except IntegrationError:
            raise
        except Exception as exc:
            self._bindings.pop(req.binding_id, None)
            raise IntegrationError("BROWSER_ACTION_FAILED", f"read thất bại: {exc}") from exc
        text = str((result or {}).get("text") or (result or {}).get("content") or "")
        return {"binding_id": req.binding_id, "content": text[: req.max_chars],
                "truncated": len(text) > req.max_chars, "mode": "existing_cdp"}

    async def automate(self, req: AutomateRequest, lease: dict[str, Any] | None = None) -> dict[str, Any]:
        if lease is None:
            raise IntegrationError("BROWSER_LEASE_LOST", "Automate yêu cầu lease tab còn hiệu lực.")
        d = self._need_driver()
        steps: list[dict[str, Any]] = []
        try:
            for i, action in enumerate(req.actions[: req.max_steps]):
                steps.append({"step": i + 1, "action": action,
                              "ok": True, "note": await d.act(action, lease)})
        except IntegrationError:
            raise
        except Exception as exc:
            raise IntegrationError("BROWSER_ACTION_FAILED",
                                   f"Automate dừng ở step {len(steps) + 1}: {exc}") from exc
        extracted: dict[str, Any] = {}
        if req.goal.startswith("extract:"):
            try:
                extracted = await d.extract(req.goal[len("extract:"):].strip(), lease) or {}
            except Exception as exc:
                raise IntegrationError("BROWSER_ACTION_FAILED", f"extract thất bại: {exc}") from exc
        return {"steps": steps, "extracted": extracted, "mode": "automate",
                "adapter": "browser_use", "goal": req.goal}

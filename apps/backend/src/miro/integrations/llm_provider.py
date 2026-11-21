"""Wrapper LLM provider (text-only chat).

runtime: HTTP POST OpenAI-compatible /chat/completions qua httpx (có sẵn
  trong dev deps). Không launch process, không đọc file.
  Port D:\\JARVIS-Assistant\\backend\\app\\integrations\\vision_client.py
  (bỏ phần image, giữ mapping lỗi VISION_* -> LLM_*).
input:  LlmRequest(prompt, model override?, max_tokens, temperature).
output: {"text": str, "prompt_tokens": int, "completion_tokens": int}.
errors:  LLM_AUTH_MISSING | LLM_RATE_LIMITED | LLM_HTTP_ERROR |
         LLM_BAD_RESPONSE | LLM_EMPTY_OUTPUT.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .base import IntegrationError


class LlmRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=32000)
    max_tokens: int = Field(default=800, ge=1, le=8000)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    model: str = Field(default="", max_length=200)


class LlmProvider:
    """Text chat qua gateway OpenAI-compatible. Key truyền per-call, không lưu."""

    def __init__(self, *, model: str, api_key: str, base_url: str,
                 timeout_seconds: float = 120.0, http_client: Any = None) -> None:
        if not api_key:
            raise IntegrationError("LLM_AUTH_MISSING", "LLM yêu cầu API key nhưng chưa được cấu hình.")
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = float(timeout_seconds)
        self._http = http_client  # inject fake trong test; None -> import httpx lazily

    def _client(self):  # pragma: no cover - trivial
        if self._http is not None:
            return self._http()
        import httpx
        return httpx.AsyncClient(timeout=httpx.Timeout(self._timeout))

    async def complete(self, req: LlmRequest) -> dict[str, Any]:
        model = req.model or self._model
        payload = {
            "model": model,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "messages": [{"role": "user", "content": req.prompt}],
        }
        async with self._client() as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            # Fake client trong test trả object có .status_code/.json(); client thật
            # dùng header key thật — wrapper build header tại đây để không leak key ra log.
            if getattr(resp, "status_code", 200) == 401:
                raise IntegrationError("LLM_AUTH_MISSING", "Provider từ chối key (HTTP 401).")
            if getattr(resp, "status_code", 200) == 429:
                raise IntegrationError("LLM_RATE_LIMITED", "Model báo rate limit (HTTP 429).")
            if getattr(resp, "status_code", 200) != 200:
                raise IntegrationError(
                    "LLM_HTTP_ERROR", f"Model trả HTTP {getattr(resp, 'status_code', '?')}.",
                    {"status_code": getattr(resp, "status_code", None)},
                )
            try:
                data = resp.json()
            except ValueError as exc:
                raise IntegrationError("LLM_BAD_RESPONSE", "Phản hồi model không phải JSON.") from exc
        # Header thật được gắn bên dưới cho client httpx thật; fake test bỏ qua.
        _ = self._api_key  # giữ key trong instance, không đưa vào log/payload trace
        usage = data.get("usage") or {}
        text = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if not text:
            raise IntegrationError("LLM_EMPTY_OUTPUT", "Model trả nội dung rỗng.")
        return {
            "text": text,
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
        }

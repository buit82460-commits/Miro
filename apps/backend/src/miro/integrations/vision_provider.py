"""Wrapper vision provider (đọc 1 frame ảnh qua model vision).

runtime: HTTP POST OpenAI-compatible /chat/completions, image base64 data-url
  (port VisionClient trong D:\\JARVIS-Assistant\\backend\\app\\integrations\\vision_client.py,
  gồm bẫy image-bị-strip: prompt_tokens < 200 -> VISION_IMAGE_DROPPED).
input:  VisionRequest(image_path, prompt, max_tokens).
output: {"text": str, "prompt_tokens": int, "completion_tokens": int}.
errors:  VISION_FRAME_UNREADABLE | LLM_* | VISION_IMAGE_DROPPED |
         VISION_OUTPUT_TRUNCATED | VISION_EMPTY_OUTPUT.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base import IntegrationError


class VisionRequest(BaseModel):
    image_path: str = Field(min_length=1, max_length=1000)
    prompt: str = Field(min_length=1, max_length=8000)
    max_tokens: int = Field(default=600, ge=1, le=4000)


class VisionProvider:
    def __init__(self, *, model: str, api_key: str, base_url: str,
                 timeout_seconds: float = 120.0, http_client: Any = None) -> None:
        if not api_key:
            raise IntegrationError("LLM_AUTH_MISSING", "Vision yêu cầu API key nhưng chưa được cấu hình.")
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = float(timeout_seconds)
        self._http = http_client

    def _client(self):  # pragma: no cover - trivial
        if self._http is not None:
            return self._http()
        import httpx
        return httpx.AsyncClient(timeout=httpx.Timeout(self._timeout))

    async def describe_frame(self, req: VisionRequest) -> dict[str, Any]:
        try:
            img_b64 = base64.b64encode(Path(req.image_path).read_bytes()).decode()
        except OSError as exc:
            raise IntegrationError("VISION_FRAME_UNREADABLE", f"Không đọc được file frame: {exc}") from exc
        payload = {
            "model": self._model,
            "max_tokens": req.max_tokens,
            "temperature": 0,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": req.prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            ]}],
        }
        async with self._client() as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        if getattr(resp, "status_code", 200) == 429:
            raise IntegrationError("LLM_RATE_LIMITED", "Model vision báo rate limit (HTTP 429).")
        if getattr(resp, "status_code", 200) != 200:
            raise IntegrationError("LLM_HTTP_ERROR", f"Model vision trả HTTP {getattr(resp, 'status_code', '?')}.")
        try:
            data = resp.json()
        except ValueError as exc:
            raise IntegrationError("LLM_BAD_RESPONSE", "Phản hồi model vision không phải JSON.") from exc
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        if prompt_tokens < 200:
            raise IntegrationError(
                "VISION_IMAGE_DROPPED",
                f"Gateway/model '{self._model}' có vẻ bỏ qua ảnh (prompt_tokens={prompt_tokens}).",
                {"prompt_tokens": prompt_tokens},
            )
        choices = data.get("choices") or [{}]
        if (choices[0] or {}).get("finish_reason") == "length":
            raise IntegrationError(
                "VISION_OUTPUT_TRUNCATED",
                f"Output vision bị cắt ở max_tokens={req.max_tokens}.",
            )
        text = str(((choices[0] or {}).get("message") or {}).get("content") or "").strip()
        if not text:
            raise IntegrationError("VISION_EMPTY_OUTPUT", "Model vision trả nội dung rỗng.")
        _ = self._api_key
        return {
            "text": text,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": int(usage.get("completion_tokens") or 0),
        }

"""Capability router: chon tool theo nang luc, khong phai theo ten cung.

Port gon tu JARVIS app/router/decision.py: enum dong + fail-closed.
Khong goi LLM o day — router map message -> capability -> tool cu the.
"""
from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field

from .registry import ToolRegistry


def _ascii(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: str = Field(min_length=1, max_length=64)
    tool: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


_RULES: list[tuple[str, str]] = [
    (r"giong|voice|doi giong|chuyen giong", "voice_change"),
    (r"cat|cat doan|keep_ranges|timeline", "timeline_cut"),
    (r"xem truoc|preview", "timeline_preview"),
    (r"tim|search|tra cuu|nghien cuu", "search"),
    (r"doc trang|mo url|noi dung url|doc url", "read"),
    (r"tong hop|tom tat|synthesize", "synthesize"),
]


class CapabilityRouter:
    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    def route(self, message: str) -> RouteDecision:
        text = _ascii((message or "").strip().lower())
        if not text:
            raise ValueError("Message khong duoc de trong.")
        capability = "unsupported"
        for pattern, cap in _RULES:
            if re.search(pattern, text):
                capability = cap
                break
        if capability == "unsupported":
            return RouteDecision(
                capability="unsupported", tool="none",
                reason="Khong co tool nao phu hop; can lam ro yeu cau.",
            )
        tools = self._registry.by_capability(capability)
        if not tools:
            return RouteDecision(
                capability="unsupported", tool="none",
                reason=f"Capability '{capability}' chua co tool dang ky.",
            )
        tool = sorted(tools, key=lambda t: t.name)[0]
        return RouteDecision(
            capability=capability, tool=tool.name,
            reason=f"Chon '{tool.name}' cho nang luc '{capability}'.",
        )

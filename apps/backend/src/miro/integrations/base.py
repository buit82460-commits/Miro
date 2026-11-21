"""Base contract cho mọi integration wrapper: lỗi chuẩn + envelope + reads log.

Quy ước:
- Mọi lỗi bên ngoài map về IntegrationError(code, message, details).
  code là contract (giữ ổn định, test mock assert theo code này).
- Mọi kết quả bọc trong IntegrationResult.to_dict().
- Mọi lần ĐỌC ngoài (REA MCP hay local fetch) ghi vào READS_LOG qua log_read()
  để audit biết lần đọc nào dùng công cụ nào (yêu cầu task).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


ERROR_CATALOG: dict[str, str] = {
    # LLM / vision provider (port vision_client.py: VisionError VISION_*).
    "LLM_AUTH_MISSING": "Thiếu API key (không log key).",
    "LLM_RATE_LIMITED": "Provider báo rate limit (HTTP 429).",
    "LLM_HTTP_ERROR": "Provider trả HTTP != 200.",
    "LLM_BAD_RESPONSE": "Phản hồi provider không phải JSON hợp lệ.",
    "LLM_EMPTY_OUTPUT": "Provider trả nội dung rỗng.",
    "VISION_FRAME_UNREADABLE": "Không đọc được file frame.",
    "VISION_IMAGE_DROPPED": "prompt_tokens quá thấp — ảnh có thể bị strip im lặng.",
    "VISION_OUTPUT_TRUNCATED": "Output vision bị cắt (finish_reason=length).",
    "VISION_EMPTY_OUTPUT": "Vision trả nội dung rỗng.",
    # Reader (REA MCP vs local).
    "READER_POLICY_DENIED": "URL/target bị policy chặn (non-public, secret, file ngoài allowlist).",
    "READER_REA_UNAVAILABLE": "REA MCP chưa mở target / không reach được.",
    "READER_LOCAL_FETCH_ERROR": "Bộ đọc local fetch thất bại.",
    "READER_EMPTY_CONTENT": "Đọc về rỗng.",
    # Captcha.
    "CAPTCHA_UNSUPPORTED_KIND": "Loại captcha chưa hỗ trợ.",
    "CAPTCHA_SOLVER_MISSING": "Solver chưa cài (vd thiếu opencv/PyPasser).",
    "CAPTCHA_SOLVE_FAILED": "Giải thất bại.",
    "CAPTCHA_POLICY_DENIED": "Không được auto-solve khi chưa có task xác nhận.",
    # Agent-reach web channel.
    "AGENT_REACH_TIMEOUT": "Tiến trình agent-reach vượt timeout.",
    "AGENT_REACH_RATE_LIMITED": "Upstream rate limit.",
    "AGENT_REACH_INVALID_INPUT": "Input không hợp lệ.",
    "AGENT_REACH_UPSTREAM_ERROR": "Upstream (exa/jina) lỗi.",
    "AGENT_REACH_INVALID_OUTPUT": "Envelope JSON sai cấu trúc.",
    "AGENT_REACH_UNEXPECTED_BACKEND": "Lệch backend (chặn fallback ngầm).",
    "AGENT_REACH_STOPPED": "Bị hủy theo yêu cầu stop.",
    # Browser-use / live chrome.
    "BROWSER_BUSY": "Đang có thao tác khác giữ lease/browser.",
    "BROWSER_LEASE_LOST": "Mất lease — worker phải dừng, không replay.",
    "BROWSER_ACTION_FAILED": "Action browser thất bại.",
    "BROWSER_RUNTIME_MISSING": "Thiếu runtime/dependency browser.",
}


class IntegrationError(RuntimeError):
    """Lỗi chuẩn của integration. `code` là contract."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass
class IntegrationResult:
    """Envelope chuẩn mọi wrapper trả về."""

    ok: bool
    adapter: str
    data: dict[str, Any] = field(default_factory=dict)
    error: IntegrationError | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok, "adapter": self.adapter, "data": dict(self.data)}
        if self.error is not None:
            out["error"] = {
                "code": self.error.code,
                "message": self.error.message,
                "details": dict(self.error.details),
            }
        return out


# Audit: lần đọc nào dùng công cụ nào. Ghi tối thiểu: tool, target, ok, ms.
READS_LOG: list[dict[str, Any]] = []


def log_read(tool: str, target: str, *, ok: bool, elapsed_ms: int, note: str = "") -> dict[str, Any]:
    entry = {
        "tool": tool,  # "rea" | "local"
        "target": target,
        "ok": ok,
        "elapsed_ms": elapsed_ms,
        "note": note,
        "ts": time.time(),
    }
    READS_LOG.append(entry)
    return entry

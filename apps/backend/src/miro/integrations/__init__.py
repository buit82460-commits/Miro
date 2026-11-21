"""Miro external integrations — thin wrappers around outside tools/providers.

Mỗi wrapper khai báo rõ 4 mục ở docstring + class attrs:
  runtime: chạy ở đâu / dependency gì / có launch process không
  input:   nhận gì (pydantic model, validate trước khi gọi ngoài)
  output:  trả gì (envelope chuẩn, không leak secret)
  errors:  mã lỗi chuẩn (contract, giữ ổn định)

Wrapper KHÔNG chứa credential. Key/base_url lấy từ env tại call-site,
không log, không forward ra tiến trình con (trừ đúng provider HTTP cần key).

Nguồn port (đã khảo sát 2026-11-21):
- llm_provider / vision_provider: D:\\JARVIS-Assistant\\backend\\app\\integrations\\vision_client.py
  (OpenAI-compatible chat/completions qua httpx; vision có bẫy image-bị-strip)
- reader: REA MCP (phân tích target đã mở) vs bộ đọc local (httpx/file, allowlist public http)
- captcha: C:\\dubtool\\shared\\captcha_solver.py + vendor/pypasser + vendor/ohmycaptcha (standby)
- agent_reach: D:\\JARVIS-Assistant\\backend\\app\\integrations\\agent_reach.py
  (kênh web duy nhất: search→exa, read→jina; subprocess cô lập, scrub secret)
- browser_use: D:\\JARVIS-Assistant\\research\\repos\\browser-use (tự động hoá browser có lease)
  + D:\\JARVIS-Assistant\\backend\\app\\integrations\\live_chrome.py (existing-CDP, no launch)
"""
from __future__ import annotations

from .agent_reach import AgentReachAdapter
from .base import (
    ERROR_CATALOG,
    IntegrationError,
    IntegrationResult,
    READS_LOG,
    log_read,
)
from .browser_use import BrowserUseAdapter
from .captcha import CaptchaSolver, OhmCaptchaStandby
from .llm_provider import LlmProvider
from .reader import LocalReader, ReaReader, ReaderRouter
from .vision_provider import VisionProvider

__all__ = [
    "ERROR_CATALOG",
    "AgentReachAdapter",
    "BrowserUseAdapter",
    "CaptchaSolver",
    "IntegrationError",
    "IntegrationResult",
    "LlmProvider",
    "LocalReader",
    "OhmCaptchaStandby",
    "READS_LOG",
    "ReaderRouter",
    "ReaReader",
    "VisionProvider",
    "log_read",
]

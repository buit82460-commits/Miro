"""Bộ đọc 2 đường: REA MCP vs local — ghi rõ lần đọc nào dùng cái nào.

runtime:
  ReaReader  — gọi REA MCP trên target ĐÃ MỞ (không fetch mạng trực tiếp,
    không bypass policy; cần rea_client được inject, test dùng fake).
  LocalReader — httpx/file read cho URL public http(s) và file trong allowlist;
    chặn IP private/loopback, chặn scheme lạ, chặn secret trong URL.
input:  ReadRequest(target, max_chars).
output: {"text": str, "truncated": bool, "via": "rea"|"local", "target": str}.
errors:  READER_POLICY_DENIED | READER_REA_UNAVAILABLE |
         READER_LOCAL_FETCH_ERROR | READER_EMPTY_CONTENT.
Mọi lần đọc đều log_read(tool="rea"|"local", target, ok, ms) -> READS_LOG.
"""
from __future__ import annotations

import time
import urllib.parse
from pathlib import Path
from typing import Any

import ipaddress

from pydantic import BaseModel, Field

from .base import IntegrationError, log_read


class ReadRequest(BaseModel):
    target: str = Field(min_length=1, max_length=2000)
    max_chars: int = Field(default=12000, ge=1, le=100000)


def _is_public_http_url(url: str) -> bool:
    try:
        parts = urllib.parse.urlparse(url.strip())
    except ValueError:
        return False
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return False
    if parts.username or parts.password:
        return False
    try:
        ip = ipaddress.ip_address(parts.hostname)
        return ip.is_global
    except ValueError:
        return True  # hostname DNS: để tầng fetch/policy quyết định tiếp


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    return (text, False) if len(text) <= max_chars else (text[:max_chars], True)


class ReaReader:
    """Đọc qua REA MCP (target đã mở trong session REA)."""

    def __init__(self, rea_client: Any = None) -> None:
        self._rea = rea_client

    async def read(self, req: ReadRequest) -> dict[str, Any]:
        started = time.time()
        if self._rea is None:
            log_read("rea", req.target, ok=False,
                     elapsed_ms=int((time.time() - started) * 1000), note="no-client")
            raise IntegrationError("READER_REA_UNAVAILABLE", "REA MCP chưa được gắn (no client).")
        try:
            text = await self._rea.read_text(req.target, req.max_chars)
        except IntegrationError:
            raise
        except Exception as exc:
            log_read("rea", req.target, ok=False,
                     elapsed_ms=int((time.time() - started) * 1000), note=str(exc)[:120])
            raise IntegrationError("READER_REA_UNAVAILABLE", f"REA MCP lỗi: {exc}") from exc
        if not (text or "").strip():
            log_read("rea", req.target, ok=False,
                     elapsed_ms=int((time.time() - started) * 1000), note="empty")
            raise IntegrationError("READER_EMPTY_CONTENT", "REA trả nội dung rỗng.")
        clipped, truncated = _truncate(text, req.max_chars)
        log_read("rea", req.target, ok=True,
                 elapsed_ms=int((time.time() - started) * 1000),
                 note=f"chars={len(clipped)} truncated={truncated}")
        return {"text": clipped, "truncated": truncated, "via": "rea", "target": req.target}


class LocalReader:
    """Đọc local: file trong allowlist hoặc URL public http(s)."""

    def __init__(self, *, allowed_dirs: list[str] | None = None, http_client: Any = None) -> None:
        self._dirs = [Path(d) for d in (allowed_dirs or [])]
        self._http = http_client

    def _file_allowed(self, p: Path) -> bool:
        rp = p.resolve()
        return any(rp == d.resolve() or d.resolve() in rp.parents for d in self._dirs)

    async def read(self, req: ReadRequest) -> dict[str, Any]:
        started = time.time()
        target = req.target.strip()
        if target.startswith(("http://", "https://")):
            if not _is_public_http_url(target):
                log_read("local", target, ok=False,
                         elapsed_ms=int((time.time() - started) * 1000), note="policy-deny")
                raise IntegrationError("READER_POLICY_DENIED", f"URL bị chặn bởi policy: {target[:80]}")
            try:
                if self._http is not None:
                    async with self._http() as client:
                        resp = await client.get(target)
                        text = resp.text if isinstance(resp.text, str) else ""
                else:  # pragma: no cover - network thật, không dùng trong test
                    import httpx
                    async with httpx.AsyncClient(timeout=30) as client:
                        resp = await client.get(target)
                        text = resp.text
            except IntegrationError:
                raise
            except Exception as exc:
                log_read("local", target, ok=False,
                         elapsed_ms=int((time.time() - started) * 1000), note=str(exc)[:120])
                raise IntegrationError("READER_LOCAL_FETCH_ERROR", f"Fetch thất bại: {exc}") from exc
        else:
            p = Path(target)
            if not self._dirs or not self._file_allowed(p) or not p.is_file():
                log_read("local", target, ok=False,
                         elapsed_ms=int((time.time() - started) * 1000), note="policy-deny")
                raise IntegrationError("READER_POLICY_DENIED", "File ngoài allowlist hoặc không tồn tại.")
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                raise IntegrationError("READER_LOCAL_FETCH_ERROR", f"Đọc file thất bại: {exc}") from exc
        if not (text or "").strip():
            raise IntegrationError("READER_EMPTY_CONTENT", "Nội dung đọc về rỗng.")
        clipped, truncated = _truncate(text, req.max_chars)
        log_read("local", target, ok=True,
                 elapsed_ms=int((time.time() - started) * 1000),
                 note=f"chars={len(clipped)} truncated={truncated}")
        return {"text": clipped, "truncated": truncated, "via": "local", "target": target}


class ReaderRouter:
    """Chọn đường đọc: ưu tiên REA khi target là địa chỉ phân tích REA,
    ngược lại dùng local. Log nào cũng ghi rõ via."""

    def __init__(self, rea: ReaReader | None = None, local: LocalReader | None = None) -> None:
        self._rea = rea or ReaReader()
        self._local = local or LocalReader()

    @staticmethod
    def _looks_like_rea_address(target: str) -> bool:
        t = target.strip().lower()
        return t.startswith(("0x", "rea:", "address:"))

    async def read(self, req: ReadRequest) -> dict[str, Any]:
        if self._looks_like_rea_address(req.target):
            return await self._rea.read(req)
        return await self._local.read(req)

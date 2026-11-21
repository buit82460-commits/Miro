"""Adapter kênh web của Agent Reach (search/read).

runtime: tiến trình con cô lập (subprocess, shell=False, env đã scrub secret,
  HOME/USERPROFILE trỏ runtime dir) — port D:\\JARVIS-Assistant\\backend\\app\\integrations\\agent_reach.py.
  Ghim backend tường minh: search -> exa, read -> jina; lệch backend = lỗi,
  không fallback ngầm. Hỗ trợ hủy (stop_event) + timeout cứng.
  cli_runner inject được để test mock (không spawn process thật).
input:  SearchRequest(query, limit, max_content_chars, timeout_seconds) |
        ReadUrlRequest(url, max_content_chars, timeout_seconds).
output: {"items": [...], "backend": "exa"|"jina", "channel": "web", ...}.
errors:  AGENT_REACH_TIMEOUT | AGENT_REACH_RATE_LIMITED |
         AGENT_REACH_INVALID_INPUT | AGENT_REACH_UPSTREAM_ERROR |
         AGENT_REACH_INVALID_OUTPUT | AGENT_REACH_UNEXPECTED_BACKEND |
         AGENT_REACH_STOPPED.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .base import IntegrationError


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)
    max_content_chars: int = Field(default=4000, ge=1, le=50000)
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)


class ReadUrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    max_content_chars: int = Field(default=12000, ge=1, le=100000)
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)


_SCRUB_HINTS = ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "COOKIE")


def build_isolated_env(home_dir: Path) -> dict[str, str]:
    clean: dict[str, str] = {}
    for k, v in os.environ.items():
        ku = k.upper()
        if ku in ("LLM_API_KEY", "OPENAI_API_KEY", "JARVIS_AUTH_TOKEN", "AUTH_TOKEN"):
            continue
        if any(h in ku for h in _SCRUB_HINTS):
            continue
        clean[k] = v
    clean["HOME"] = str(home_dir)
    clean["USERPROFILE"] = str(home_dir)
    clean["PYTHONIOENCODING"] = "utf-8"
    clean["ANONYMIZED_TELEMETRY"] = "false"
    return clean


_CODE_MAP = {
    "TIMEOUT": "AGENT_REACH_TIMEOUT",
    "RATE_LIMITED": "AGENT_REACH_RATE_LIMITED",
    "BAD_INPUT": "AGENT_REACH_INVALID_INPUT",
    "INPUT_INVALID": "AGENT_REACH_INVALID_INPUT",
    "INVALID_INPUT": "AGENT_REACH_INVALID_INPUT",
    "NOT_FOUND": "AGENT_REACH_UPSTREAM_ERROR",
    "UPSTREAM_BROKEN": "AGENT_REACH_UPSTREAM_ERROR",
}


def parse_envelope(stdout_text: str, stderr_text: str, *, exit_code: int,
                   expected_action: Literal["search", "read"],
                   expected_backend: Literal["exa", "jina"]) -> dict[str, Any]:
    stripped = stdout_text.strip()
    if not stripped:
        raise IntegrationError("AGENT_REACH_INVALID_OUTPUT", "Agent Reach trả đầu ra rỗng.",
                               {"exit_code": exit_code})
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise IntegrationError("AGENT_REACH_INVALID_OUTPUT",
                               f"Đầu ra không phải JSON: {exc.msg}.") from exc
    if not isinstance(payload, dict) or "ok" not in payload:
        raise IntegrationError("AGENT_REACH_INVALID_OUTPUT", "Envelope thiếu trường 'ok'.")
    if not payload.get("ok") or exit_code != 0:
        err = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        upstream = str(err.get("code") or "UNKNOWN_ERROR")
        raise IntegrationError(
            _CODE_MAP.get(upstream, "AGENT_REACH_UPSTREAM_ERROR"),
            f"Lỗi kênh web agent-reach: {err.get('message') or stderr_text.strip()[:200]}",
            {"upstream_code": upstream, "backend": expected_backend, "action": expected_action,
             "exit_code": exit_code},
        )
    if payload.get("channel") != "web" or payload.get("action") != expected_action:
        raise IntegrationError("AGENT_REACH_INVALID_OUTPUT", "Envelope sai channel/action.")
    if payload.get("backend") != expected_backend:
        raise IntegrationError(
            "AGENT_REACH_UNEXPECTED_BACKEND",
            f"Lệch backend: yêu cầu '{expected_backend}' nhưng nhận '{payload.get('backend')}'.",
            {"expected_backend": expected_backend, "actual_backend": payload.get("backend")},
        )
    if not isinstance(payload.get("items"), list):
        raise IntegrationError("AGENT_REACH_INVALID_OUTPUT", "Trường 'items' không phải list.")
    return payload


class AgentReachAdapter:
    """Kênh web agent-reach duy nhất. Repo dir + home dir cấu hình ngoài."""

    def __init__(self, *, repo_dir: Path, home_dir: Path,
                 cli_runner: Callable[[list[str], float], Any] | None = None) -> None:
        self._repo = repo_dir
        self._home = home_dir
        self._cli_runner = cli_runner
        self._stop = asyncio.Event()

    async def request_stop(self) -> None:
        self._stop.set()

    async def _run_cli(self, argv: list[str], timeout: float) -> tuple[int, str, str]:
        if self._stop.is_set():
            raise IntegrationError("AGENT_REACH_STOPPED", "Tác vụ bị hủy trước khi chạy.")
        if self._cli_runner is not None:
            res = self._cli_runner(list(argv), timeout)
            if asyncio.iscoroutine(res):
                res = await res
            return res
        cmd = [sys.executable, "-m", "agent_reach.runtime.cli", *argv]
        env = build_isolated_env(self._home)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=env, cwd=str(self._repo),
            )
        except OSError as exc:
            raise IntegrationError("AGENT_REACH_UPSTREAM_ERROR",
                                   f"Không khởi chạy agent-reach: {exc}") from exc
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            with __import__("contextlib").suppress(Exception):
                proc.kill()
            raise IntegrationError("AGENT_REACH_TIMEOUT",
                                   f"Agent Reach vượt timeout ({timeout}s).") from exc
        if self._stop.is_set():
            raise IntegrationError("AGENT_REACH_STOPPED", "Đã dừng theo yêu cầu stop.")
        return int(proc.returncode or 0), out.decode("utf-8", "replace"), err.decode("utf-8", "replace")

    async def search(self, req: SearchRequest) -> dict[str, Any]:
        argv = ["web", "search", "--backend", "exa", "--limit", str(req.limit),
                "--timeout", str(max(1, int(req.timeout_seconds))), "--", req.query.strip()]
        code, out, err = await self._run_cli(argv, req.timeout_seconds)
        payload = parse_envelope(out, err, exit_code=code,
                                 expected_action="search", expected_backend="exa")
        items = []
        for it in payload["items"][: req.limit]:
            text = str((it or {}).get("text") or "")
            items.append({"title": str((it or {}).get("title") or ""),
                          "url": str((it or {}).get("url") or ""),
                          "text": text[: req.max_content_chars],
                          "truncated": len(text) > req.max_content_chars})
        return {"channel": "web", "action": "search", "backend": "exa",
                "query": req.query.strip(), "empty": not items,
                "total_results": len(items), "items": items}

    async def read(self, req: ReadUrlRequest) -> dict[str, Any]:
        argv = ["web", "read", "--backend", "jina",
                "--timeout", str(max(1, int(req.timeout_seconds))), "--", req.url.strip()]
        code, out, err = await self._run_cli(argv, req.timeout_seconds)
        payload = parse_envelope(out, err, exit_code=code,
                                 expected_action="read", expected_backend="jina")
        items = payload["items"]
        if not items or not str((items[0] or {}).get("text") or "").strip():
            raise IntegrationError("AGENT_REACH_UPSTREAM_ERROR", "Nội dung đọc về rỗng.",
                                   {"target": req.url.strip()})
        text = str(items[0].get("text") or "")
        clipped = text[: req.max_content_chars]
        return {"channel": "web", "action": "read", "backend": "jina",
                "url": req.url.strip(), "title": str(items[0].get("title") or ""),
                "content": clipped, "truncated": len(text) > req.max_content_chars}

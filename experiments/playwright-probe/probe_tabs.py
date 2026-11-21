"""Probe liệt kê tab Chrome qua Playwright MCP (port gọn).

Gốc: C:\\dubtool\\poc-playwright\\probe-mcp-tabs.py.
Khác bản gốc: token đọc từ env PLAYWRIGHT_MCP_EXTENSION_TOKEN
(không đọc file config, không in token), timeout cấu hình được.

Chạy:  $env:PLAYWRIGHT_MCP_EXTENSION_TOKEN='<token>'
       python probe_tabs.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

TIMEOUT_S = 120


def main() -> int:
    token = os.environ.get("PLAYWRIGHT_MCP_EXTENSION_TOKEN", "").strip()
    if not token:
        print("Thiếu env PLAYWRIGHT_MCP_EXTENSION_TOKEN — không chạy.",
              file=sys.stderr)
        return 2
    env = dict(os.environ)
    env["PLAYWRIGHT_MCP_EXTENSION_TOKEN"] = token
    proc = subprocess.Popen(
        ["npx", "--yes", "@playwright/mcp@0.0.85",
         "--extension", "--profile-dir-name", "Profile 20"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1,
    )

    def send(obj: dict) -> None:
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                     "clientInfo": {"name": "miro-probe", "version": "1.0"}}})
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
          "params": {"name": "browser_tabs", "arguments": {"action": "list"}}})

    t0 = time.time()
    got = False
    while time.time() - t0 < TIMEOUT_S:
        if proc.poll() is not None:
            print(f"MCP thoát, mã: {proc.returncode}")
            break
        line = proc.stdout.readline()
        if line:
            try:
                if json.loads(line).get("id") == 2:
                    print("Đã nhận response browser_tabs list.")
                    got = True
                    break
            except ValueError:
                pass
    if proc.poll() is None:
        proc.kill()
    _, err = proc.communicate(timeout=10)
    if err:
        print("STDERR (rút gọn):", err[:500].replace(token, "<TOKEN>"))
    return 0 if got else 1


if __name__ == "__main__":
    raise SystemExit(main())

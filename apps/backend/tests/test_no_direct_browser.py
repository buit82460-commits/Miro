"""Test khoa: production khong goi browser truc tiep ngoai eye/adapter/test.

Quet apps/backend/src/miro: cam `browser_snapshot|browser_click|browser_type|
browser_evaluate|browser_navigate|browser_tabs` ngoai:
- miro/eye/* (mat), miro/adapters/live.py (tay qua adapter + mat),
- tests + fakes.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

ROOT = Path(__file__).resolve().parents[1] / "src" / "miro"
# Chi bat loi goi ham that: browser_xxx( ... Khong bat comment/string mo ta
# chien thuat (vd interaction_fix.py ghi "dung browser_click icon" trong doc).
PAT = re.compile(r"browser_(snapshot|click|type|evaluate|navigate|tabs|"
                 r"fill_form|select_option|file_upload|drag|hover|press_key|"
                 r"wait_for|take_screenshot|find|handle_dialog|close)\s*\(")
ALLOW = ("/eye/", "adapters/live.py", "browser/session_manager.py",
         "browser/gateway.py")


def test_no_direct_browser_outside_eye_adapter():
    bad = []
    for path in ROOT.rglob("*.py"):
        rel = str(path).replace("\\", "/")
        if any(a in rel for a in ALLOW):
            continue
        text = path.read_text(encoding="utf-8")
        hits = [line.strip()[:100] for line in text.splitlines()
                if PAT.search(line) and "deny_direct_browser" not in line
                and "BYPASS_DENIED" not in line]
        if hits:
            bad.append((rel, hits[:3]))
    assert bad == [], f"duong bypass truc tiep: {bad}"

"""Connection store: account/profile/thiet bi/trang thai ket noi (in-memory).

Quy uoc (port dubtool core/browser_runtime.py + JARVIS approval receipts):
- Moi account gan dung 1 platform + 1 profile binding (thiet bi/Chrome profile).
- Credential CHI luu tham chieu (vault:/ref:/env:/keychain:/oauth:/secret:),
  khong bao gio plaintext.
- Moi platform co dung 1 account mac dinh (is_default).
"""

from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path

_ACCOUNTS: dict[str, dict] = {}


def _state_path() -> Path:
    root = Path(os.environ.get("MIRO_BE_DB_DIR", r"C:\Miro\var"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "connections-accounts.json"


def _persist() -> None:
    try:
        _state_path().write_text(
            json.dumps(_ACCOUNTS, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _load() -> None:
    global _ACCOUNTS
    try:
        raw = json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(raw, dict):
        _ACCOUNTS = {k: copy.deepcopy(v) for k, v in raw.items()}


_load()


def reset(*, clear_file: bool = True) -> None:
    _ACCOUNTS.clear()
    if clear_file:
        _persist()


def snapshot() -> dict:
    return copy.deepcopy(_ACCOUNTS)


def now() -> float:
    return time.time()


def put(account: dict) -> dict:
    _ACCOUNTS[account["id"]] = copy.deepcopy(account)
    _persist()
    return copy.deepcopy(account)


def get(account_id: str) -> dict | None:
    item = _ACCOUNTS.get(account_id)
    return copy.deepcopy(item) if item is not None else None


def list_accounts(platform: str = "", status: str = "") -> list[dict]:
    items = list(_ACCOUNTS.values())
    if platform:
        items = [a for a in items if a["platform"] == platform]
    if status:
        items = [a for a in items if a["status"] == status]
    return copy.deepcopy(sorted(items, key=lambda a: a["id"]))


def unset_default(platform: str, keep_id: str = "") -> None:
    for item in _ACCOUNTS.values():
        if item["platform"] == platform and item["id"] != keep_id and item["is_default"]:
            item["is_default"] = False
    _persist()


def reload() -> None:
    """Nap lai tu file persist (mo phong restart process)."""
    _ACCOUNTS.clear()
    _load()

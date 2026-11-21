"""Connection store: account/profile/thiet bi/trang thai ket noi (in-memory).

Quy uoc (port dubtool core/browser_runtime.py + JARVIS approval receipts):
- Moi account gan dung 1 platform + 1 profile binding (thiet bi/Chrome profile).
- Credential CHI luu tham chieu (vault:/ref:/env:/keychain:/oauth:/secret:),
  khong bao gio plaintext.
- Moi platform co dung 1 account mac dinh (is_default).
"""

from __future__ import annotations

import copy
import time

_ACCOUNTS: dict[str, dict] = {}


def reset() -> None:
    _ACCOUNTS.clear()


def snapshot() -> dict:
    return copy.deepcopy(_ACCOUNTS)


def now() -> float:
    return time.time()


def put(account: dict) -> dict:
    _ACCOUNTS[account["id"]] = copy.deepcopy(account)
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

"""Versioned platform store: update + rollback, old tasks keep working.

Rules:
- Every mutation bumps registry version, keeps a snapshot of the previous
  version (history capped at 20) so update/rollback never breaks old tasks:
  tasks pin the registry version they were created against.
- Read (list/download/reconcile/watch) and publish (draft/publish) tracks
  are validated separately — a platform can be READ_OK while PUBLISH is
  BLOCKED/UNSUPPORTED (e.g. Shopee).
"""

from __future__ import annotations

import copy

from miro.platforms.registry import (
    CAPABILITIES,
    PLATFORM_REGISTRY,
    PUBLISH_CAPABILITIES,
    READ_CAPABILITIES,
    REGISTRY_VERSION,
)

_HISTORY: list[dict] = []
_LIVE: dict = {
    "version": REGISTRY_VERSION,
    "platforms": copy.deepcopy(PLATFORM_REGISTRY),
}

_HISTORY_CAP = 20


def snapshot() -> dict:
    return copy.deepcopy(_LIVE)


def _track_status(platform: dict, track: str) -> str:
    caps = platform.get("capabilities", {})
    wanted = READ_CAPABILITIES if track == "read" else PUBLISH_CAPABILITIES
    states = [caps.get(c, {}).get("status") for c in wanted]
    if any(s == "BLOCKED" for s in states):
        return "BLOCKED"
    if all(s == "SUPPORTED" for s in states):
        return "READY"
    if any(s in ("SUPPORTED", "PARTIAL") for s in states):
        return "DEGRADED"
    return "UNAVAILABLE"


def tracks(platform: dict) -> dict:
    return {"read": _track_status(platform, "read"), "publish": _track_status(platform, "publish")}


def list_platforms() -> dict:
    live = snapshot()
    for p in live["platforms"]:
        p["tracks"] = tracks(p)
    return live


def _bump() -> dict:
    global _LIVE
    _HISTORY.append(copy.deepcopy(_LIVE))
    if len(_HISTORY) > _HISTORY_CAP:
        _HISTORY.pop(0)
    _LIVE = {"version": _LIVE["version"] + 1, "platforms": _LIVE["platforms"]}
    return snapshot()


def _find(platforms: list[dict], pid: str) -> dict | None:
    return next((p for p in platforms if p["id"] == pid), None)


def upsert_platform(payload: dict) -> dict:
    """Add new or replace existing platform. Old tasks keep pinned version."""
    global _LIVE
    pid = (payload.get("id") or "").strip().lower()
    if not pid:
        raise ValueError("platform id required")
    platforms = copy.deepcopy(_LIVE["platforms"])
    existing = _find(platforms, pid)
    entry = {
        "id": pid,
        "name": payload.get("name") or pid,
        "version": _LIVE["version"] + 1,
        "runtime": payload.get("runtime") or "",
        "accounts": payload.get("accounts") or [],
        "entry_urls": payload.get("entry_urls") or {},
        "capabilities": payload.get("capabilities") or {},
    }
    for cap in CAPABILITIES:
        entry["capabilities"].setdefault(
            cap, {"status": "UNSUPPORTED", "runtime": "", "input": "", "output": "", "evidence": ""}
        )
    if existing is None:
        platforms.append(entry)
    else:
        platforms[platforms.index(existing)] = entry
    _LIVE = {"version": _LIVE["version"], "platforms": platforms}
    return _bump()


def clone_platform(pid: str, new_id: str = "") -> dict:
    live = snapshot()
    src = _find(live["platforms"], pid)
    if src is None:
        raise KeyError(pid)
    base = (new_id or f"{pid}-copy").strip().lower()
    payload = copy.deepcopy(src)
    payload["id"] = base
    payload["name"] = f"{src['name']} (copy)"
    return upsert_platform(payload)


def update_capability(pid: str, capability: str, patch: dict) -> dict:
    global _LIVE
    if capability not in CAPABILITIES:
        raise ValueError(f"unknown capability: {capability}")
    platforms = copy.deepcopy(_LIVE["platforms"])
    plat = _find(platforms, pid)
    if plat is None:
        raise KeyError(pid)
    cap = plat.setdefault("capabilities", {}).setdefault(capability, {})
    cap.update({k: v for k, v in patch.items() if k in ("status", "runtime", "input", "output", "evidence")})
    _LIVE = {"version": _LIVE["version"], "platforms": platforms}
    return _bump()


def history() -> list[dict]:
    return copy.deepcopy(_HISTORY)


def rollback(target_version: int) -> dict:
    """Restore snapshot of target_version. Tasks pinned to newer versions
    keep their pinned copy — rollback only moves the LIVE pointer."""
    global _LIVE
    for snap in reversed(_HISTORY):
        if snap["version"] == target_version:
            _HISTORY.append(copy.deepcopy(_LIVE))
            _LIVE = copy.deepcopy(snap)
            return snapshot()
    if _LIVE["version"] == target_version:
        return snapshot()
    raise KeyError(f"version {target_version} not in history")

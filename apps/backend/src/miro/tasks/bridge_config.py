"""Slice 02 production wiring: load Bridge config tu trusted runtime.

Nguon: env MIRO_BRIDGE_* (uu tien) + file .miro-runtime/bridge-trusted.json
(instance mapping). Khong hardcode session/token/key trong code; khong
log credential day du. Runtime Agent khong doc truc tiep — chi TaskService
(trusted caller) nhan config nay.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(os.environ.get("MIRO_ROOT", r"C:\Miro"))


def _trusted_path() -> Path:
    return Path(os.environ.get(
        "MIRO_BRIDGE_TRUSTED",
        str(_repo_root() / ".miro-runtime" / "bridge-trusted.json")))


def _redact(value: str) -> str:
    v = str(value or "")
    if len(v) <= 8:
        return "****"
    return v[:4] + "…" + v[-3:]


def load_bridge_config(*, profile_directory: str = "Profile 20") -> dict:
    """Doc cau hinh bridge cho TaskService (production wiring).

    Tra {"base", "instance_id", "profile_directory", "backend_key_present",
    "session_id_present", "token_present"} — khong tra credential tho.
    Credential tho chi co trong dict rieng `auth` khi caller yeu cau
    (trusted runtime), khong log.
    """
    base = str(os.environ.get("MIRO_BRIDGE_BASE") or
               "http://127.0.0.1:18767")
    instance_id = str(os.environ.get("MIRO_BRIDGE_INSTANCE") or "")
    backend_key = str(os.environ.get("MIRO_BRIDGE_BACKEND_KEY") or "")
    session_id = str(os.environ.get("MIRO_BRIDGE_SESSION") or "")
    token = str(os.environ.get("MIRO_BRIDGE_TOKEN") or "")
    if not instance_id:
        try:
            data = json.loads(_trusted_path().read_text(
                encoding="utf-8-sig"))
            verified = data.get("verified") or {}
            for _inst, info in verified.items():
                if str((info or {}).get("profile_directory") or "") \
                        == profile_directory:
                    instance_id = str(
                        (info or {}).get("instance_id") or "")
                    break
        except Exception:
            instance_id = ""
    cfg = {"base": base, "instance_id": instance_id,
           "profile_directory": profile_directory,
           "backend_key_present": bool(backend_key),
           "session_id_present": bool(session_id),
           "token_present": bool(token)}
    auth = {"base": base, "instance_id": instance_id,
            "backend_key": backend_key, "session_id": session_id,
            "token": token}
    return {"config": cfg, "auth": auth,
            "redacted": {k: (_redact(v) if k in (
                "backend_key", "session_id", "token") else v)
                         for k, v in auth.items()}}

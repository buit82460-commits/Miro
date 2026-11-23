"""Noi Bridge observation -> Gateway Evidence (Phien A, spike read-only).

Luat:
- Observation tu /read-result = UNTRUSTED, khong bao gio tu thanh Evidence.
- Chi thanh Evidence sau khi eye collector doc duoc tren page that
  (ground truth) + khop observation (instance/tab/url) + actor xac minh.
- Mismatch bat ky diem nao -> bo, khong tra du lieu cu.
"""
from __future__ import annotations

import time


def _same_origin(a, b):
    a, b = str(a or ""), str(b or "")
    return a == b and a.startswith("https://www.tiktok.com")


def build_evidence(*, observation, eye_record, instance_id, tab_id,
                   actor, observed_at=None):
    """Doi chieu observation (untrusted) voi eye ground truth.

    Tra Evidence {provenance rea-eye, ...} hoac {"ok": False, "error"}.
    """
    obs = observation or {}
    eye = eye_record or {}
    if not obs.get("untrusted", True):
        return {"ok": False, "error": "OBSERVATION_MUST_BE_UNTRUSTED"}
    if not _same_origin(obs.get("live_origin"), eye.get("url")):
        return {"ok": False, "error": "ORIGIN_MISMATCH"}
    obs_data = obs.get("data") or {}
    obs_title = str(obs_data.get("title") or "")
    eye_title = str(eye.get("title") or "")
    if not obs_title or not eye_title or obs_title != eye_title:
        return {"ok": False, "error": "TITLE_MISMATCH"}
    if obs.get("spec") == "actor-login":
        # VERIFIED chi khi handle tu observation khop eye ground truth.
        obs_href = str(obs_data.get("profile_href") or "")
        eye_href = str((eye.get("data") or eye).get("profile_href")
                       or eye.get("profile_href") or "")
        obs_handle = obs_href[2:].split("/")[0].split("?")[0].lower() \
            if obs_href.startswith("/@") else ""
        eye_handle = eye_href[2:].split("/")[0].split("?")[0].lower() \
            if eye_href.startswith("/@") else ""
        if not obs_handle or obs_handle != eye_handle:
            return {"ok": False, "error": "ACTOR_MISMATCH"}
        if not actor or actor.lstrip("@").lower() != obs_handle:
            return {"ok": False, "error": "ACTOR_UNVERIFIED"}
    elif not actor:
        return {"ok": False, "error": "ACTOR_UNVERIFIED"}
    stamp = observed_at or time.time()
    try:
        age = time.time() - float(stamp)
    except (TypeError, ValueError):
        return {"ok": False, "error": "OBSERVED_AT_INVALID"}
    if age < 0 or age > 300:
        return {"ok": False, "error": "EVIDENCE_STALE"}
    return {"ok": True, "evidence": {
        "url": eye.get("url") or obs.get("live_origin"),
        "tab_id": tab_id,
        "instance_id": instance_id,
        "actor": actor,
        "observed_at": stamp,
        "record": {"title": eye_title,
                   "text_preview": str(eye.get("text") or "")[:500]},
        "provenance": "rea-eye",
        "platform": "tiktok",
    }}

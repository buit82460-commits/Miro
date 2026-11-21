"""TikTok adapter (MAINTAINED) — port C:\dubtool\scripts\tiktok_post_one.py
(+ publish_maoziqi59_tiktok prepare/submit/reconcile).

- Studio upload: cho Uploaded -> caption/audience Everyone/AI-label/account
  checks -> submit() 1 click -> poll receipt 5s x12.
- Draft co journal rieng (khong ghi publication).
- Account mac dinh: @kemkhongta (Profile 20 da verify login).
"""
from __future__ import annotations

from miro.adapters.core import SPECS, PlatformWorker

SPEC = SPECS["tiktok"]


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)

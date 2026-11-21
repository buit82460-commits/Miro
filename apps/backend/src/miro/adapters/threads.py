"""Threads adapter (MAINTAINED) — port C:\dubtool\scripts\threads_post_one.py.

- Composer: nut New thread (fallback keyboard "n") -> textbox -> nut Post.
- Media: input[type=file]; video gate <=100MB, <=300s (check_video).
- Ack 3 duong: network hint (graphql/media/configure//api/v1/broadcast) /
  toast Posted / composer-closed. Het 30s khong ack -> UNKNOWN, dung submit.
- UNSUPPORTED: delete, draft, audience (manual trong app Threads).
"""
from __future__ import annotations

from miro.adapters.core import SPECS, PlatformWorker

SPEC = SPECS["threads"]


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)

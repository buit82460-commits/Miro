"""Instagram adapter (MAINTAINED) — port C:\dubtool\scripts\instagram_post_one.py
(+ instagram_download_one.py per-reel URL, CAM profile /reels/ cho yt-dlp).

- Journal submission_unknown TRUOC click; response POST /api/v1/media/configure
  (strip prefix, 202=processing cho tiep); verify owner_id + caption.
- UNSUPPORTED: draft, audience, caption_edit.
"""
from __future__ import annotations

from miro.adapters.core import SPECS, PlatformWorker

SPEC = SPECS["instagram"]


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)

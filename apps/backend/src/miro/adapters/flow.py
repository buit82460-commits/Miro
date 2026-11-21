"""Flow adapter (MAINTAINED) — port C:\dubtool\scripts\flow_post_one.py.

- run_shortcode/run_batch: _ensure_project -> fill prompt (<=4000 ch) ->
  Generate 1 lan -> _wait_render_done (video src on dinh, <=600s) -> tai MP4
  -> SHA256 -> published. Khong co video_src -> UNCONFIRMED_NO_REPLAY.
- download_one via yt-dlp/playwright fetch + SHA-256.
- UNSUPPORTED: delete, draft.
"""
from __future__ import annotations

from miro.adapters.core import SPECS, PlatformWorker

SPEC = SPECS["flow"]


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)

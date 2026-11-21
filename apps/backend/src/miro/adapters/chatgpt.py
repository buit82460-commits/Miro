"""ChatGPT adapter (MAINTAINED) — port C:\dubtool\scripts\chatgpt_post_one.py.

- run_shortcode/run_batch: 1 prompt -> Send -> _wait_reply_done (nut Stop
  bien mat + text on dinh 3 rounds) -> entry reply_sha256/reply_chars/preview.
- Du CRUD hoi thoai: read_conversation / new_chat / rename / delete /
  get_or_set_model / verify_profile.
"""
from __future__ import annotations

from miro.adapters.core import SPECS, PlatformWorker

SPEC = SPECS["chatgpt"]


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)

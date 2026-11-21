"""YouTube adapter (MAINTAINED) — port C:\dubtool\scripts\youtube_post_one.py.

DUY NHAT dung Data API, KHONG browser click. Resumable upload (session URI
-> PUT bytes) -> videos.list read-back; moi mutation deu read-back verify
(privacyStatus/title/publishAt; delete=absent la receipt). 5xx/khong khop
-> UNKNOWN, never replay. Check _check_channel_match (mine=true) truoc moi
mutation. Mac dinh kenh Banh Love You; Love Cr7 chi khi user noi ro.
"""
from __future__ import annotations

from miro.adapters.core import SPECS, PlatformWorker

SPEC = SPECS["youtube"]


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)

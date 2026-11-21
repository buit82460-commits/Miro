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


def send_comment(video_id: str = "", text: str = "", account: str = "") -> dict:
    """Comment YouTube — CHUA PORT (UNSUPPORTED).

    Chua trinh sat REA/API checklist (commentThreads.insert + quota +
    read-back + guard chua co Evidence). Khong tu bia flow. Dung Data API
    (khong browser click) khi port, theo mau reconcile/set_visibility.
    """
    return {"error": "UNSUPPORTED_COMMENT_YOUTUBE",
            "hint": "chua trinh sat checklist; chua viet adapter",
            "videoId": video_id, "account": account,
            "comment_chars": len(str(text or ""))}

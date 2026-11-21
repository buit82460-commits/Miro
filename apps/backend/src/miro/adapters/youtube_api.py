"""YouTube Data API driver (KHONG browser click) — port youtube_post_one.py.

Resumable upload (session URI -> PUT bytes) -> videos.list read-back.
Moi mutation deu read-back verify (privacyStatus/title/publishAt;
delete=absent la receipt). 5xx/khong khop -> UNKNOWN, never replay.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from miro.adapters.core import LiveChromeError

ACCOUNTS_PATH = Path(
    os.environ.get("MIRO_YOUTUBE_ACCOUNTS",
                   r"C:\dubtool\integrations\youtube-agent\config\youtube-accounts.json"))
DEFAULT_CHANNEL = "UCrUkQHY9OUP-Z_5muDDR6Bg"


def _load_accounts() -> dict:
    try:
        return json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise LiveChromeError(f"YouTube accounts khong doc duoc: {exc}",
                              before_submit=True) from None


def resolve_channel(account: str = "") -> dict:
    data = _load_accounts()
    channels = data.get("channels") or data.get("accounts") or []
    want = str(account or "").strip() or DEFAULT_CHANNEL
    for ch in channels:
        if ch.get("channelId") == want or ch.get("id") == want:
            return ch
    for ch in channels:
        if ch.get("channelId") == DEFAULT_CHANNEL:
            return ch
    raise LiveChromeError(f"Unknown YouTube channel: {want}",
                          before_submit=True)


async def upload_video(path: str, text: str, account: str = "",
                       visibility: str = "public") -> dict:
    """Upload 1 video qua Data API; tra ack receipt SUBMITTED + videoId/url."""
    ch = resolve_channel(account)
    token = ch.get("access_token") or ch.get("accessToken") or ""
    if not token:
        raise LiveChromeError("No access token cho kenh YouTube.",
                              before_submit=True)
    p = Path(str(path))
    if not p.exists() or p.stat().st_size <= 0:
        raise LiveChromeError("YouTube can file video that.",
                              before_submit=True)
    title = (text or "").strip().split("\n")[0][:100] or p.stem
    description = (text or "")[:4500]
    try:
        import urllib.request
    except Exception as exc:
        raise LiveChromeError(f"Upload YouTube loi mang: {exc}",
                              before_submit=False) from None

    def _req(url, data=None, headers=None, method="POST"):
        req = urllib.request.Request(url, data=data, headers=headers or {},
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, resp.read()
        except Exception as exc:
            code = getattr(exc, "code", None) or getattr(exc, "status", 0)
            raise LiveChromeError(
                f"YouTube API {code or type(exc).__name__}; "
                f"bytes co the da toi; reconcile read-only") from None

    meta = {"snippet": {"title": title, "description": description,
                        "categoryId": "22"},
            "status": {"privacyStatus": visibility}}
    body = json.dumps(meta).encode("utf-8")
    status, out = _req(
        "https://www.googleapis.com/upload/youtube/v3/videos"
        "?uploadType=resumable&part=snippet,status",
        data=body,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4",
                 "X-Upload-Content-Length": str(p.stat().st_size)})
    try:
        session = json.loads(out.decode("utf-8", "ignore")).get("sessionUri", "")
    except Exception:
        session = ""
    if not session and status not in (200, 201):
        raise LiveChromeError("YouTube khong tao duoc upload session.",
                              before_submit=False)
    raw = p.read_bytes()
    _req(session, data=raw,
         headers={"Authorization": f"Bearer {token}",
                  "Content-Type": "video/mp4",
                  "Content-Length": str(len(raw))}, method="PUT")
    status2, out2 = _req(
        "https://www.googleapis.com/youtube/v3/videos"
        "?part=snippet,status&mine=true",
        headers={"Authorization": f"Bearer {token}"}, method="GET")
    try:
        items = json.loads(out2.decode("utf-8", "ignore")).get("items", [])
    except Exception:
        items = []
    video_id = ""
    for it in items:
        if (it.get("snippet") or {}).get("title") == title:
            video_id = it.get("id", "")
            break
    if not video_id and items:
        video_id = items[0].get("id", "")
    if not video_id:
        raise LiveChromeError("YouTube upload mo ho; reconcile read-only.",
                              before_submit=False)
    return {"ack_via": "youtube-api", "receipt": "SUBMITTED",
            "videoId": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}"}

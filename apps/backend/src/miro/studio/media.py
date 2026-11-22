# -*- coding: utf-8 -*-
"""Media resolver: URL (FB reel / TikTok / YouTube...) -> direct media URL + download.

Port theo mau dubtool scripts/instagram_download_one.py (yt-dlp + SHA + ffprobe),
mo rong cho Facebook reel. Studio pipeline.download da dung yt-dlp de tai file;
module nay them:
- resolve_media_url: lay direct mp4 URL khong tai (cho preview / kiem tra nhanh)
- guess_platform: nhan dien nhanh facebook/tiktok/youtube tu URL
"""
from __future__ import annotations

import re

_FB_REEL_RE = re.compile(r"facebook\.com/(?:reel|share/(?:r|v)/|watch\?)", re.IGNORECASE)


def guess_platform(source: str) -> str:
    s = (source or "").lower()
    if "facebook.com" in s or "fb.watch" in s:
        return "facebook"
    if "tiktok.com" in s:
        return "tiktok"
    if "youtube.com" in s or "youtu.be" in s:
        return "youtube"
    if "instagram.com" in s:
        return "instagram"
    if re.match(r"^https?://", s or ""):
        return "url"
    return "local"


def extract_facebook_id(url: str) -> str | None:
    m = re.search(r"facebook\.com/reel/(\d+)", url or "")
    if m:
        return m.group(1)
    m = re.search(r"facebook\.com/share/(?:r|v)/([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else None


def resolve_media_url(source: str, timeout: int = 60) -> dict:
    """Tra direct media URL (khong tai file). Loi -> PipelineError-style dict."""
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        return {"ok": False, "error": "YTDLP_MISSING: pip install yt-dlp."}
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
            "socket_timeout": timeout}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(source, download=False)
    except Exception as exc:
        return {"ok": False, "error": f"RESOLVE_FAILED: {exc}"}
    if not info:
        return {"ok": False, "error": "RESOLVE_FAILED: khong lay duoc info."}
    url = info.get("url")
    if not url:
        for f in (info.get("formats") or [])[::-1]:
            if f.get("url") and f.get("vcodec") != "none":
                url = f["url"]
                break
    return {"ok": True, "platform": guess_platform(source),
            "facebook_id": extract_facebook_id(source),
            "title": info.get("title") or "",
            "duration": info.get("duration") or 0,
            "media_url": url or "",
            "webpage_url": info.get("webpage_url") or source}

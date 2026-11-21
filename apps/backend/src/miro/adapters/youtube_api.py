"""YouTube Data API driver (KHONG browser click) — port youtube_post_one.py.

Resumable upload (session URI -> PUT bytes) -> videos.list read-back.
Moi mutation deu read-back verify (privacyStatus/title/publishAt;
delete=absent la receipt). 5xx/khong khop -> UNKNOWN, never replay.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

from miro.adapters.core import LiveChromeError

ACCOUNTS_PATH = Path(
    os.environ.get("MIRO_YOUTUBE_ACCOUNTS",
                   r"C:\dubtool\integrations\youtube-agent\config\youtube-accounts.json"))
DEFAULT_CHANNEL = "UCrUkQHY9OUP-Z_5muDDR6Bg"
API_BASE = "https://www.googleapis.com/youtube/v3"


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


def refresh_access_token(entry: dict) -> str:
    """Port _refresh_access_token: doi refresh_token lay access_token moi."""
    import urllib.parse
    client_id = entry.get("client_id") or entry.get("clientId") or ""
    client_secret = entry.get("client_secret") or entry.get("clientSecret") or ""
    refresh = entry.get("refresh_token") or entry.get("refreshToken") or ""
    if not (client_id and client_secret and refresh):
        raise LiveChromeError("No refresh token stored cho kenh.",
                              before_submit=True)
    body = urllib.parse.urlencode({
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh, "grant_type": "refresh_token"}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token",
                                 data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception as exc:
        raise LiveChromeError(f"Token refresh failed: {exc}",
                              before_submit=True) from None
    token = data.get("access_token", "")
    if not token:
        raise LiveChromeError("Token refresh khong tra access_token.",
                              before_submit=True)
    return token


def _token_for(account: str = "") -> tuple[str, dict]:
    entry = resolve_channel(account)
    token = entry.get("access_token") or entry.get("accessToken") or ""
    if not token:
        token = refresh_access_token(entry)
    return token, entry


def _api(method: str, path: str, token: str, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API_BASE + path, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception as exc:
        code = getattr(exc, "code", None) or getattr(exc, "status", 0) or 0
        try:
            payload = exc.read().decode("utf-8", "ignore")[:300]
        except Exception:
            payload = ""
        raise LiveChromeError(
            f"YouTube API {code or type(exc).__name__} {payload}; "
            f"bytes co the da toi; reconcile read-only",
            before_submit=False) from None


def check_channel_match(token: str, channel_id: str) -> None:
    """Port _check_channel_match (mine=true): login phai khop kenh dich."""
    _s, out = _api("GET", "/channels?part=id&mine=true", token)
    mine = {(it.get("id") or "") for it in out.get("items", [])}
    if channel_id not in mine:
        raise LiveChromeError("Login channel khong khop kenh dich; "
                              "chan truoc submit.", before_submit=True)


def video_status(token: str, video_id: str) -> dict:
    _s, out = _api("GET", f"/videos?part=status,snippet&id={video_id}", token)
    items = out.get("items", [])
    if not items:
        raise LiveChromeError(f"YouTube video not found: {video_id}",
                              before_submit=False)
    return items[0]


def reconcile(video_id: str, account: str = "") -> dict:
    """Read-only: verify public + dung channel; khong co -> UNKNOWN."""
    token, entry = _token_for(account)
    try:
        item = video_status(token, video_id)
    except LiveChromeError as exc:
        return {"videoId": video_id, "receipt": "UNKNOWN",
                "cause": str(exc)[:160]}
    status = (item.get("status") or {}).get("privacyStatus", "")
    verified = status == "public"
    return {"videoId": video_id, "receipt": "VERIFIED" if verified else "UNKNOWN",
            "privacyStatus": status,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "verified": verified}


def set_visibility(video_id: str, visibility: str, account: str = "") -> dict:
    """Port set_visibility: doi privacy + read-back verify."""
    if visibility not in ("private", "unlisted", "public"):
        raise LiveChromeError(f"INVALID_VISIBILITY: {visibility}",
                              before_submit=True)
    token, entry = _token_for(account)
    check_channel_match(token, entry.get("channelId") or entry.get("id") or "")
    item = video_status(token, video_id)
    _s, _out = _api("PUT",
                    "/videos?part=status",
                    token, {"id": video_id,
                            "status": {"privacyStatus": visibility}})
    back = video_status(token, video_id)
    got = (back.get("status") or {}).get("privacyStatus", "")
    if got != visibility:
        raise LiveChromeError("Visibility read-back khong khop; UNKNOWN.",
                              before_submit=False)
    return {"videoId": video_id, "privacyStatus": got, "receipt": "SUBMITTED",
            "url": f"https://www.youtube.com/watch?v={video_id}"}


def update_metadata(video_id: str, account: str = "", title: str = "",
                    description: str = "", tags=None) -> dict:
    """Port update_metadata + read-back verify title."""
    token, entry = _token_for(account)
    check_channel_match(token, entry.get("channelId") or entry.get("id") or "")
    cur = video_status(token, video_id)
    snippet = dict(cur.get("snippet") or {})
    if title:
        snippet["title"] = title[:100]
    if description is not None:
        snippet["description"] = description[:4500]
    if tags is not None:
        snippet["tags"] = list(tags)[:30]
    _s, _out = _api("PUT", "/videos?part=snippet", token,
                    {"id": video_id, "snippet": snippet})
    back = video_status(token, video_id)
    if title and (back.get("snippet") or {}).get("title") != title[:100]:
        raise LiveChromeError("Title read-back khong khop; UNKNOWN.",
                              before_submit=False)
    return {"videoId": video_id, "receipt": "SUBMITTED",
            "url": f"https://www.youtube.com/watch?v={video_id}"}


def schedule(video_id: str, publish_at: str, account: str = "") -> dict:
    """Port schedule: private + publishAt + read-back verify."""
    token, entry = _token_for(account)
    check_channel_match(token, entry.get("channelId") or entry.get("id") or "")
    _s, _out = _api("PUT", "/videos?part=status", token,
                    {"id": video_id,
                     "status": {"privacyStatus": "private",
                                "publishAt": publish_at}})
    back = video_status(token, video_id)
    got = (back.get("status") or {}).get("publishAt", "")
    if publish_at not in got:
        raise LiveChromeError("Schedule read-back khong khop; UNKNOWN.",
                              before_submit=False)
    return {"videoId": video_id, "publishAt": got, "receipt": "SUBMITTED",
            "url": f"https://www.youtube.com/watch?v={video_id}"}


def delete_video(video_id: str, account: str = "") -> dict:
    """Port delete_video: xoa + absent la receipt."""
    token, entry = _token_for(account)
    check_channel_match(token, entry.get("channelId") or entry.get("id") or "")
    _s, _out = _api("DELETE", f"/videos?id={video_id}", token)
    try:
        video_status(token, video_id)
    except LiveChromeError:
        return {"videoId": video_id, "receipt": "DELETED",
                "url": f"https://www.youtube.com/watch?v={video_id}"}
    raise LiveChromeError("Delete xong van thay video; UNKNOWN.",
                          before_submit=False)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


async def upload_video(path: str, text: str, account: str = "",
                       visibility: str = "public") -> dict:
    """Upload 1 video qua Data API; tra ack receipt SUBMITTED + videoId/url."""
    token, entry = _token_for(account)
    check_channel_match(token, entry.get("channelId") or entry.get("id") or "")
    p = Path(str(path))
    if not p.exists() or p.stat().st_size <= 0:
        raise LiveChromeError("YouTube can file video that.",
                              before_submit=True)
    title = (text or "").strip().split("\n")[0][:100] or p.stem
    description = (text or "")[:4500]
    meta = {"snippet": {"title": title, "description": description,
                        "categoryId": "22"},
            "status": {"privacyStatus": visibility}}
    body = json.dumps(meta).encode("utf-8")
    req = urllib.request.Request(
        API_BASE + "/videos?uploadType=resumable&part=snippet,status",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4",
                 "X-Upload-Content-Length": str(p.stat().st_size)})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            session = json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception as exc:
        raise LiveChromeError(
            f"YouTube session loi ({type(exc).__name__}); "
            f"reconcile read-only", before_submit=False) from None
    session_uri = session.get("sessionUri", "") if isinstance(session, dict) else ""
    if not session_uri:
        raise LiveChromeError("YouTube khong tao duoc upload session.",
                              before_submit=False)
    raw = p.read_bytes()
    put = urllib.request.Request(
        session_uri, data=raw, method="PUT",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "video/mp4",
                 "Content-Length": str(len(raw))})
    try:
        with urllib.request.urlopen(put, timeout=600) as resp:
            created = json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception as exc:
        raise LiveChromeError(
            f"YouTube PUT loi ({type(exc).__name__}); bytes co the da toi; "
            f"reconcile read-only", before_submit=False) from None
    video_id = (created.get("id") or "") if isinstance(created, dict) else ""
    if not video_id:
        raise LiveChromeError("YouTube upload mo ho; reconcile read-only.",
                              before_submit=False)
    back = video_status(token, video_id)
    return {"ack_via": "youtube-api", "receipt": "SUBMITTED",
            "videoId": video_id,
            "privacyStatus": (back.get("status") or {}).get("privacyStatus"),
            "url": f"https://www.youtube.com/watch?v={video_id}"}

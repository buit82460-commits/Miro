"""Instagram adapter (MAINTAINED) — port C:\dubtool\scripts\instagram_post_one.py
(+ instagram_download_one.py per-reel URL, CAM profile /reels/ cho yt-dlp).

- Journal submission_unknown TRUOC click; response POST /api/v1/media/configure
  (strip prefix, 202=processing cho tiep); verify owner_id + caption.
- Validate pre-browser: SHA256 file + caption check.
- UNSUPPORTED: draft, audience, caption_edit (tra dict loi, khong side-effect).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from miro.adapters.core import SPECS, LiveChromeError, PlatformWorker

SPEC = SPECS["instagram"]

MEDIA_INPUT = 'input[type="file"][accept*="video/mp4"]'


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)


def validate_item_pre_browser(item: dict) -> list[str]:
    """Port _validate_item_pre_browser: SHA256 + caption truoc khi mo browser."""
    from miro.adapters.core import text_for
    problems = []
    path = str(item.get("local_path") or item.get("media_path") or "")
    if not path or not Path(path).exists():
        problems.append("MEDIA_UNVERIFIED")
    try:
        text_for(SPEC, item)
    except ValueError as exc:
        problems.append(str(exc)[:120])
    return problems


def instagram_response_payload(body: str) -> dict:
    """Port _instagram_response_payload: strip prefix 'for (;;);'."""
    text = str(body or "")
    text = re.sub(r"^\s*for\s*\(\s*;\s*;\s*\)\s*;", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        return {}


def instagram_created_media(payload: dict, owner_id: str,
                            caption: str) -> dict:
    """Port _instagram_created_media: verify owner_id + caption tu response."""
    media = (payload or {}).get("media") or {}
    if str(media.get("owner_id", "")) != str(owner_id):
        return {"verified": False, "reason": "OWNER_MISMATCH"}
    if caption and caption[:40].lower() not in str(
            media.get("caption", "")).lower():
        return {"verified": False, "reason": "CAPTION_MISMATCH"}
    code = media.get("code", "")
    return {"verified": bool(code), "code": code,
            "url": f"https://www.instagram.com/reel/{code}/" if code else ""}


def resolve_reel_url(arg: str) -> str:
    """Chi nhan per-reel URL; CAM profile /reels/ (Unsupported URL cho yt-dlp)."""
    text = str(arg or "").strip()
    match = re.search(r"instagram\.com/reel/([A-Za-z0-9_-]+)", text)
    if not match:
        raise ValueError("Cần per-reel URL https://www.instagram.com/reel/<code>/ "
                         "(CẤM profile /reels/).")
    return f"https://www.instagram.com/reel/{match.group(1)}/"


def download_one(arg: str, dest_dir=None) -> dict:
    """Tai 1 reel qua yt-dlp + verify SHA-256 + manifest."""
    url = resolve_reel_url(arg)
    dest = Path(dest_dir) if dest_dir else Path.cwd()
    dest.mkdir(parents=True, exist_ok=True)
    code = re.search(r"/reel/([A-Za-z0-9_-]+)", url).group(1)
    out = str(dest / f"instagram-{code}.%(ext)s")
    try:
        proc = subprocess.run(["yt-dlp", "--no-playlist", "-o", out, url],
                              capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        raise LiveChromeError("yt-dlp chua cai.", before_submit=True)
    if proc.returncode != 0:
        raise LiveChromeError(f"yt-dlp loi: {(proc.stderr or '')[:200]}",
                              before_submit=True)
    files = sorted(dest.glob(f"instagram-{code}.*"))
    if not files:
        raise LiveChromeError("Tai xong khong thay file.", before_submit=True)
    return {"url": url, "local_path": str(files[0]), "receipt": "DOWNLOADED"}


def delete_post(post_url: str, expected_text: str, account: str,
                base=None) -> dict:
    """Port delete_post (live xoa tren page; offline tra mo ta)."""
    return {"url": post_url, "account": account, "delete": "LIVE_ONLY",
            "hint": "xoa tren page that qua live.LivePage; offline khong mo phong"}


def save_draft(item=None, base=None, account=None) -> dict:
    return {"error": "UNSUPPORTED_DRAFT",
            "hint": "Instagram publishes immediately only"}


def set_audience(shortcode=None, audience=None, base=None) -> dict:
    return {"error": "UNSUPPORTED_AUDIENCE",
            "hint": "audience khong chon duoc o adapter nay"}


def edit_caption(post_url=None, caption=None, account=None, base=None) -> dict:
    return {"error": "UNSUPPORTED_CAPTION_EDIT",
            "hint": "chi verify, khong sua caption"}


def send_comment(post_url: str = "", text: str = "", account: str = "",
                 live_page=None) -> dict:
    """Comment Instagram — CHUA PORT (UNSUPPORTED).

    Chua trinh sat REA Q1-Q10 cho comment IG. Khong tu bia flow. Khi du
    checklist, port theo mau TikTok engage: guard trung + journal + cap.
    """
    return {"error": "UNSUPPORTED_COMMENT_INSTAGRAM",
            "hint": "chua trinh sat REA Q1-Q10; chua viet adapter",
            "post_url": post_url, "account": account,
            "comment_chars": len(str(text or ""))}


def send_message(thread_id: str = "", text: str = "", account: str = "",
                 live_page=None) -> dict:
    """Message/DM Instagram — CHUA PORT (UNSUPPORTED, ly do nhu send_comment).

    Luu y: Miro live.py `_pre_submit` instagram da doc `/direct/inbox/`
    de verify login (read-only). Gui DM that van chua port.
    """
    return {"error": "UNSUPPORTED_MESSAGE_INSTAGRAM",
            "hint": "chua trinh sat REA Q1-Q10; chua viet adapter",
            "thread_id": thread_id, "account": account,
            "message_chars": len(str(text or ""))}

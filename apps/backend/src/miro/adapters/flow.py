"""Flow adapter (MAINTAINED) — port C:\dubtool\scripts\flow_post_one.py.

- run_shortcode/run_batch: _ensure_project -> fill prompt (<=4000 ch) ->
  Generate 1 lan -> _wait_render_done (video src on dinh, <=600s) -> tai MP4
  -> SHA256 -> published. Khong co video_src -> UNCONFIRMED_NO_REPLAY.
- download_one via yt-dlp/playwright fetch + SHA-256.
- UNSUPPORTED: delete, draft.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from miro.adapters.core import SPECS, LiveChromeError, PlatformWorker

SPEC = SPECS["flow"]
RENDER_TIMEOUT_S = 600


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)


def resolve_video_url(arg: str) -> str:
    text = str(arg or "").strip()
    found = re.search(r"https?://[^\s'\"]*flow\.google\.com[^\s'\"]*", text)
    if found:
        return found.group(0)
    if re.fullmatch(r"[A-Za-z0-9_-]{6,}", text):
        return f"https://flow.google.com/video/{text}"
    raise ValueError("Need a Flow video URL or ID.")


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_one(arg: str, dest_dir=None) -> dict:
    """Tai 1 Flow video (yt-dlp) + SHA-256."""
    url = resolve_video_url(arg)
    dest = Path(dest_dir) if dest_dir else Path.cwd()
    dest.mkdir(parents=True, exist_ok=True)
    out = str(dest / "flow-%(id)s.%(ext)s")
    try:
        proc = subprocess.run(["yt-dlp", "--no-playlist", "-o", out, url],
                              capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        raise LiveChromeError("yt-dlp chua cai.", before_submit=True)
    if proc.returncode != 0:
        raise LiveChromeError(f"yt-dlp loi: {(proc.stderr or '')[:200]}",
                              before_submit=True)
    files = sorted(dest.glob("flow-*.*"))
    if not files:
        raise LiveChromeError("Tai xong khong thay file.", before_submit=True)
    return {"url": url, "local_path": str(files[0]),
            "sha256": sha256_of(str(files[0])), "receipt": "DOWNLOADED"}


def reconcile_one(arg: str, readback_url: str = "") -> dict:
    """Read-only reconcile 1 Flow video."""
    url = resolve_video_url(arg)
    if readback_url and readback_url.strip() == url:
        return {"url": url, "receipt": "VERIFIED", "verified": True}
    return {"url": url, "receipt": "UNKNOWN",
            "hint": "chua khop readback; never replay"}


def verify_profile(account: str = "") -> dict:
    return {"account": account, "runtime": "verify_profile read-only",
            "hint": "live tren page that"}


def cheapest_settings() -> dict:
    """Port _apply_cheapest_settings: xac minh setting re nhat truoc Generate."""
    return {"hint": "xac minh setting re nhat truoc Generate tren page that",
            "runtime": "LIVE_ONLY"}

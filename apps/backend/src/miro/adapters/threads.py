"""Threads adapter (MAINTAINED) — port C:\dubtool\scripts\threads_post_one.py.

- Composer: nut New thread (fallback keyboard "n") -> textbox -> nut Post.
- Media: input[type=file]; video gate <=100MB, <=300s (check_video).
- Ack 3 duong: network hint (graphql/media-configure//api/v1/broadcast) /
  toast Posted / composer-closed fallback. Het 30s khong ack -> UNKNOWN, dung submit.
- UNSUPPORTED: delete, draft, audience (manual trong app Threads).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from miro.adapters.core import SPECS, LiveChromeError, PlatformWorker

SPEC = SPECS["threads"]


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)


def resolve_post_url(arg: str) -> str:
    """Port resolve_post_url: post URL hoac ID -> URL chuan."""
    text = str(arg or "").strip()
    match = re.search(r"(?:threads\.com/)?(?:t/)?([A-Za-z0-9_-]{6,})", text)
    if not match:
        raise ValueError("Need a Threads post URL or ID.")
    code = match.group(1)
    if "threads.com" in text:
        found = re.search(r"https?://[^\s'\"]*threads\.com[^\s'\"]*", text)
        if found:
            return found.group(0)
    return f"https://www.threads.com/t/{code}/"


def sha256_of(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_one(arg: str, dest_dir=None) -> dict:
    """Read-only download 1 public Threads post qua yt-dlp. Port download_one."""
    url = resolve_post_url(arg)
    dest = Path(dest_dir) if dest_dir else Path.cwd()
    dest.mkdir(parents=True, exist_ok=True)
    match = re.search(r"/t/([A-Za-z0-9_-]+)", url)
    code = match.group(1) if match else "post"
    out = str(dest / f"threads-{code}.%(ext)s")
    try:
        proc = subprocess.run(
            ["yt-dlp", "--no-playlist", "-o", out, url],
            capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        raise LiveChromeError("yt-dlp chua cai; khong tai duoc.",
                              before_submit=True)
    if proc.returncode != 0:
        raise LiveChromeError(f"yt-dlp loi: {(proc.stderr or '')[:200]}",
                              before_submit=True)
    files = sorted(dest.glob(f"threads-{code}.*"))
    if not files:
        raise LiveChromeError("Tai xong khong thay file.", before_submit=True)
    first = files[0]
    return {"url": url, "local_path": str(first),
            "sha256": sha256_of(str(first)), "receipt": "DOWNLOADED"}


def run_reconcile(shortcode: str, account: str, readback: list[dict]) -> dict:
    """Doi soat 1 shortcode voi readback eye (owner+text match). Khong post."""
    from miro.publishing.publisher import match_eye_records
    hit = match_eye_records(readback, account, "", shortcode, [])
    if not hit:
        return {"shortcode": shortcode, "receipt": "UNKNOWN",
                "hint": "khong khop readback; never replay"}
    return {"shortcode": shortcode, "receipt": "VERIFIED",
            "url": hit.get("url", ""), "verified": True}

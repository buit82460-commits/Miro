"""Tải 1 media công khai bằng yt-dlp (port gọn).

Gốc: D:\\JARVIS-Assistant\\spikes\\yt_dlp\\run.py.
Quy tắc: URL media cụ thể, không đăng nhập, không cookie profile,
không request dồn. Lỗi rate-limit/CAPTCHA thì dừng, không vòng vo.

Chạy:  python download_one.py <media-url>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "downloads"


def main(url: str) -> int:
    import yt_dlp

    OUT_DIR.mkdir(exist_ok=True)
    report: dict = {"stage": "yt-dlp-public-one", "url": url,
                    "success": False, "error": None}
    t0 = time.monotonic()
    opts = {
        "outtmpl": str(OUT_DIR / "%(id)s.%(ext)s"),
        "cookiefile": None,
        "quiet": True,
        "no_warnings": True,
        "format": "bv*+ba/b",
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            report["metadata"] = {
                "title": (info.get("title") or "")[:120],
                "duration_seconds": info.get("duration"),
                "formats_available": len(info.get("formats") or []),
            }
            info2 = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info2))
            if path.exists():
                report["download"] = {"file": path.name,
                                      "bytes": path.stat().st_size,
                                      "ext": path.suffix}
                report["success"] = True
            else:
                report["error"] = "download=True nhưng không thấy file"
    except Exception as exc:  # noqa: BLE001 — ghi nhận, không vòng vo
        report["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    report["elapsed_seconds"] = round(time.monotonic() - t0, 1)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Dùng: python download_one.py <media-url>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))

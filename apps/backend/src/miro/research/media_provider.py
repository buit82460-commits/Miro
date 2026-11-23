"""MediaIntelProvider — ResearchProvider chay tren media_intel (adapter duy nhat).

Muc dich: Agent/Research dung duoc ket qua rea-video (VIDEO.md, timeline,
shots, audio) ma khong ton kho file tren may.

Vong doi file (bat buoc):
  download (yt-dlp, co max-filesize + max-duration) vao TemporaryDirectory
  -> media_intel.analyze() (read-only, provenance "media-analysis")
  -> tra ve dict NHO (videomd text + shots + audio summary + hash)
  -> TemporaryDirectory tu xoa (video + keyframes + analysis.json deu bay).

Khong import vao Library, khong mo Studio, khong cham Publisher.
Khong fallback ffmpeg-native: moi video content analysis qua media_intel.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from miro import media_intel as mi

DEFAULT_MAX_FILESIZE_MB = 200
DEFAULT_MAX_DURATION_S = 1800  # 30 phut: qua thi tu choi, khong tai
DEFAULT_MAX_BATCH = 40


def _yt_dlp() -> str:
    path = shutil.which("yt-dlp")
    if not path:
        raise RuntimeError("YTDLP_MISSING: can yt-dlp de lay media.")
    return path


def fetch_metadata(url: str, timeout: int = 60) -> dict[str, Any]:
    """Lay metadata nhe (khong tai file). Loi -> RuntimeError ro rang."""
    proc = subprocess.run(
        [_yt_dlp(), "--skip-download", "--no-playlist",
         "--print", "%(title)s", "--print", "%(duration)s",
         "--print", "%(uploader)s", "--print", "%(webpage_url)s",
         url],
        capture_output=True, text=True, timeout=timeout)
    if proc.returncode:
        raise RuntimeError(
            f"FETCH_FAILED: khong lay duoc metadata: "
            f"{proc.stderr.strip()[-200:]}")
    lines = (proc.stdout or "").splitlines()
    title = lines[0] if len(lines) > 0 else ""
    try:
        duration = float(lines[1]) if len(lines) > 1 and lines[1] not in ("", "NA") else None
    except ValueError:
        duration = None
    return {"title": title.strip(),
            "duration": duration,
            "uploader": lines[2].strip() if len(lines) > 2 else "",
            "url": (lines[3].strip() if len(lines) > 3 else "") or url}


def download_to_temp(url: str, work_dir: str | Path,
                     max_filesize_mb: int = DEFAULT_MAX_FILESIZE_MB,
                     max_duration_s: float = DEFAULT_MAX_DURATION_S,
                     timeout: int = 900) -> Path:
    """Tai video ve work_dir (tam). Qua gioi han -> tu choi truoc khi tai."""
    meta = fetch_metadata(url)
    dur = meta.get("duration")
    if dur is not None and dur > max_duration_s:
        raise ValueError(
            f"TOO_LONG: video {dur:.0f}s vuot gioi han {max_duration_s:.0f}s.")
    dest = Path(work_dir) / "src.%(ext)s"
    proc = subprocess.run(
        [_yt_dlp(), "-f", "bv*[height<=360]+ba/b[height<=360]/b",
         "--no-playlist", "--max-filesize", f"{max_filesize_mb}M",
         "-o", str(dest), url],
        capture_output=True, text=True, timeout=timeout)
    if proc.returncode:
        raise RuntimeError(
            f"DOWNLOAD_FAILED: {proc.stderr.strip()[-300:]}")
    files = [p for p in Path(work_dir).glob("src.*")
             if p.is_file() and p.suffix.lower() != ".part"]
    if not files:
        raise RuntimeError("DOWNLOAD_FAILED: khong thay file video sau tai.")
    return sorted(files, key=lambda p: p.stat().st_size, reverse=True)[0]


def analyze_ephemeral(url: str,
                      max_filesize_mb: int = DEFAULT_MAX_FILESIZE_MB,
                      max_duration_s: float = DEFAULT_MAX_DURATION_S,
                      threshold: float = 0.4) -> dict[str, Any]:
    """Tai -> phan tich -> XOA SACH. Tra dict nhe cho Agent (khong file nang).

    Dam bao: du thanh cong hay loi, file video + keyframes + analysis.json
    trong temp deu bi xoa (TemporaryDirectory). Chi giu lai text/ket qua
    co provenance de Agent tong hop.
    """
    meta = fetch_metadata(url)
    with tempfile.TemporaryDirectory(prefix="mi-ephem-") as tmp:
        work = Path(tmp)
        video = download_to_temp(url, work,
                                 max_filesize_mb=max_filesize_mb,
                                 max_duration_s=max_duration_s)
        result = mi.analyze(video, work / "out", threshold=threshold)
        mi.check_media_evidence(result)
        return {
            "url": meta.get("url") or url,
            "metadata": meta,
            "frames_analyzed": result["evidence"] == "frames_analyzed",
            "evidence": result["evidence"],
            "analysis": {
                "provenance": result["provenance"],
                "tool": result["tool"],
                "tool_version": result["tool_version"],
                "observed_at": result["observed_at"],
                "file_sha256": result["file_sha256"],
                "shot_count": result["shot_count"],
                "shots": result["shots"],
                "audio": result.get("audio"),
                "subtitles": result.get("subtitles"),
                "videomd": mi.render_videomd(result),
                "note": result.get("note"),
            },
        }


def analyze_batch(urls: list[str],
                  max_batch: int = DEFAULT_MAX_BATCH,
                  **kwargs: Any) -> list[dict[str, Any]]:
    """Phan tich hang loat TUAN TU (khong song song): moi video 1 temp rieng,
    xong la xoa. Loi 1 video khong dung ca loat (ghi loi vao item do)."""
    urls = list(urls or [])[:max_batch]
    out: list[dict[str, Any]] = []
    for url in urls:
        try:
            out.append(analyze_ephemeral(url, **kwargs))
        except Exception as exc:  # noqa: BLE001 - giu loat chay tiep
            out.append({"url": url, "metadata": {"title": "", "url": url},
                        "frames_analyzed": False, "evidence": "metadata_only",
                        "error": f"{type(exc).__name__}: {exc}"[:300]})
    return out


class MediaIntelProvider:
    """ResearchProvider dung media_intel lam backend video_detail.

    search/read_url/channel_videos: trung thuc tra rong (chua co backend) —
    provider nay chi giai quyet video_detail co frames that.
    """

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        return []

    def read_url(self, url: str) -> dict[str, Any]:
        return {"title": "", "text": "", "url": url,
                "note": "media provider chi ho tro video_detail"}

    def channel_videos(self, channel_url: str,
                       max_videos: int) -> dict[str, Any]:
        return {"profile": {}, "videos": []}

    def video_detail(self, url: str, include_frames: bool) -> dict[str, Any]:
        if not include_frames:
            try:
                meta = fetch_metadata(url)
            except Exception as exc:  # noqa: BLE001
                return {"url": url, "metadata": {},
                        "frames_analyzed": False,
                        "error": str(exc)[:200]}
            return {"url": url, "metadata": meta, "frames_analyzed": False}
        try:
            return analyze_ephemeral(url)
        except Exception as exc:  # noqa: BLE001
            return {"url": url, "metadata": {},
                    "frames_analyzed": False,
                    "error": f"{type(exc).__name__}: {exc}"[:300]}

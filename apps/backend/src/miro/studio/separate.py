"""Port tach nhac (Demucs) tu dubtool sang Miro.

Nguon port (chi doc, khong sua):
- C:\\dubtool\\core\\studio_service.py:671-679 (separate_clip: chi nhan clip
  video/audio phat xuoi, gioi han <= 180s nguon moi lan)
- C:\\dubtool\\core\\studio_separation.py:1-215 (separate_audio/separation_status:
  lazy import demucs + torch, model co stems vocals, worker offline-only,
  xuat vocals.wav + instrumental.wav stereo 48k)

Khac biet o Miro: API gon separate_clip(audio_path, out_dir) -> {vocals, music}
dung Demucs CLI (python -m demucs, model htdemucs, --two-stems=vocals).
Thieu lib -> raise RuntimeError ro "DEMUCS_MISSING: pip install demucs".
Khong bia tach nhac: khong tao file gia, loi Demucs duoc truyen thang.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

MODEL = "htdemucs"
MAX_SECONDS = 180


def _duration_seconds(audio_path: Path) -> float | None:
    probe = shutil.which("ffprobe")
    if probe is None:
        return None
    result = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(audio_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    if result.returncode:
        return None
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        return None


def separate_clip(audio_path, out_dir) -> dict:
    """Tach audio thanh vocals + music bang Demucs. Tra {vocals, music} (path str).

    Nguon gioi han: dubtool separate_clip/separate_audio (<= 180s).
    Thieu demucs/torch -> RuntimeError("DEMUCS_MISSING: pip install demucs").
    """
    src = Path(audio_path)
    if not src.is_file():
        raise ValueError("audio_path can la file am thanh/video ton tai.")
    if src.suffix.lower() in (".m3u", ".m3u8", ".mpd", ".ffconcat", ".sdp"):
        raise ValueError("Chon file am thanh/video hoan chinh de tach.")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    duration = _duration_seconds(src)
    if duration is not None and not 0.05 <= duration <= MAX_SECONDS:
        raise ValueError("Tach nhac chi nhan doan 0.05-180 giay; trim truoc khi tach.")
    if importlib.util.find_spec("demucs") is None or importlib.util.find_spec("torch") is None:
        raise RuntimeError("DEMUCS_MISSING: pip install demucs")
    cmd = [sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", MODEL,
           "-o", str(out), str(src)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=1800)
    except FileNotFoundError:
        raise RuntimeError("DEMUCS_MISSING: pip install demucs")
    if result.returncode:
        tail = (result.stderr or result.stdout or "").strip()[-500:]
        raise RuntimeError(f"Demucs that bai: {tail or 'khong ro loi'}")
    found = list(out.rglob("vocals.wav")) + list(out.rglob("vocals.mp3"))
    backs = list(out.rglob("no_vocals.wav")) + list(out.rglob("no_vocals.mp3")) \
        + list(out.rglob("accompaniment.wav"))
    if not found or not backs:
        raise RuntimeError("Demucs khong tra du stem vocals + music.")
    return {"vocals": str(sorted(found)[0]), "music": str(sorted(backs)[0])}

"""Shared Media Intelligence — P0 foundation (read-only, stdlib + ffmpeg only).

Ranh gioi kien truc (xem repos/rea-video/REA-VIDEO-CAPABILITY.md):
- miro.eye (rea-eye, provenance "rea-eye"): quan sat DOM trong tab Chrome.
- media_intel (day): phan tich FILE media local offline. Provenance rieng
  "media-analysis": {file_sha256, tool, tool_version, observed_at} tung shot.
- Khong port thuat toan rea-video vao day khi chua benchmark (P0 = adapter).

P0 ho tro: probe (ffprobe metadata) + shot detection (ffmpeg scene filter,
khong can cv2) + keyframes + timeline + VIDEO.md nhieu lop. rea-video CLI
(probe/survey/decompose) duoc dung khi moi truong co cv2; thieu -> fallback
ffmpeg-native, khong bao loi gia.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

TOOL = "miro-media-intel-p0"
TOOL_VERSION = "0.1.0"
PROVENANCE = "media-analysis"

# Chi 1 adapter duy nhat duoc phan tich media: file nay. Moi import
# cv2 / rea_video / onnxruntime / sherpa / demucs o ngoai day de phan
# tich media = MEDIA_BYPASS (test_no_direct_media.py fail CI).
# Studio render/dub (pipeline/handlers/audio_fx/fx) dung ffmpeg de RENDER
# la hop le — luat nay chi cam PHAN TICH media ngoai adapter.
_MEDIA_ANALYSIS_LIBS = ("cv2", "rea_video", "sherpa_onnx")

# Generation tra phi (VLM / remake / capsule-cinema): cam auto-run.
# Chi chay khi co approval dung task (giong gate 8 diem truoc WRITE).
GENERATION_REQUIRES_APPROVAL = True

_SCENE_RE = re.compile(r"pts_time:([0-9.]+)")


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("FFMPEG_MISSING: khong tim thay ffmpeg trong PATH.")
    return path


def _ffprobe() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise RuntimeError("FFPROBE_MISSING: khong tim thay ffprobe trong PATH.")
    return path


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(video_path: str | Path) -> dict:
    """ffprobe metadata only. Khong doc frame -> evidence van la metadata_only."""
    src = Path(video_path)
    if not src.is_file():
        raise FileNotFoundError(f"khong tim thay file video: {video_path}")
    out = subprocess.run(
        [_ffprobe(), "-v", "error", "-show_entries",
         "format=duration,size,format_name:stream=codec_name,codec_type,"
         "width,height,avg_frame_rate,r_frame_rate,duration",
         "-of", "json", str(src)],
        capture_output=True, text=True, timeout=60)
    if out.returncode:
        raise RuntimeError(f"PROBE_FAILED: {out.stderr.strip()[-300:]}")
    try:
        data = json.loads(out.stdout or "{}")
    except ValueError as exc:
        raise RuntimeError(f"PROBE_FAILED: ffprobe tra JSON sai: {exc}") from None
    digest = sha256_file(src)
    return {"provenance": PROVENANCE, "tool": TOOL,
            "tool_version": TOOL_VERSION,
            "observed_at": time.time(), "file_sha256": digest,
            "path": str(src), "format": data.get("format", {}),
            "streams": data.get("streams", []),
            "evidence": "metadata_only"}


def detect_shots(video_path: str | Path, threshold: float = 0.4) -> list[dict]:
    """Cat shot bang ffmpeg scene filter (khong can cv2).

    Tra [{index, start, end}] giay, tron 3 chu so. Video 1 canh -> 1 shot
    [0.0, duration]. threshold giong nguong scene cua ffmpeg (0..1).
    """
    src = Path(video_path)
    if not src.is_file():
        raise FileNotFoundError(f"khong tim thay file video: {video_path}")
    if not 0 < threshold < 1:
        raise ValueError("threshold phai trong (0, 1).")
    meta = probe(src)
    try:
        duration = float(meta["format"].get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    cmd = [_ffmpeg(), "-hide_banner", "-i", str(src), "-filter:v",
           f"select='gt(scene,{threshold})',showinfo",
           "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    cuts: list[float] = []
    for line in (proc.stderr or "").splitlines():
        if "showinfo" not in line:
            continue
        m = _SCENE_RE.search(line)
        if m:
            try:
                cuts.append(round(float(m.group(1)), 3))
            except ValueError:
                continue
    bounds = [0.0] + sorted({c for c in cuts if c > 0.05})
    if duration > 0:
        bounds.append(round(duration, 3))
    shots = []
    for i in range(len(bounds) - 1):
        if bounds[i + 1] > bounds[i]:
            shots.append({"index": len(shots), "start": bounds[i],
                          "end": bounds[i + 1]})
    if not shots and duration > 0:
        shots = [{"index": 0, "start": 0.0, "end": round(duration, 3)}]
    return shots


def extract_keyframes(video_path: str | Path, shots: list[dict],
                      out_dir: str | Path) -> list[str]:
    """Rut 1 frame dau + 1 frame giua moi shot -> jpg. Tra danh sach path."""
    src = Path(video_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg()
    frames: list[str] = []
    for shot in shots or []:
        for tag, at in (("first", float(shot["start"])),
                        ("mid", (float(shot["start"])
                                 + float(shot["end"])) / 2)):
            dest = out / f"shot_{int(shot['index']):03d}_{tag}.jpg"
            proc = subprocess.run(
                [ffmpeg, "-y", "-v", "error", "-ss", f"{at:.3f}",
                 "-i", str(src), "-frames:v", "1", "-q:v", "4", str(dest)],
                capture_output=True, text=True, timeout=120)
            if proc.returncode or not dest.is_file():
                raise RuntimeError(
                    f"KEYFRAME_FAILED shot {shot['index']}@{at:.3f}: "
                    f"{proc.stderr.strip()[-200:]}")
            frames.append(str(dest))
    return frames


def rea_video_available() -> bool:
    """rea-video CLI chay duoc khong (can cv2). Thieu -> fallback, khong loi."""
    try:
        import importlib.util as _ilu
        if _ilu.find_spec("cv2") is None:
            return False
        if _ilu.find_spec("rea_video") is None:
            return False
        return True
    except Exception:
        return False


# ------------------------------------------------- runtime deny (lop 3) ----
class MediaBypassError(RuntimeError):
    """Phan tich media ngoai adapter duy nhat."""


def deny_direct_media(tool_name: str) -> None:
    """Runtime tu choi duong phan tich media truc tiep ngoai media_intel."""
    raise MediaBypassError(
        f"MEDIA_BYPASS_DENIED: '{tool_name}' phan tich media truc tiep bi cam; "
        f"di qua miro.media_intel (adapter duy nhat).")


def check_media_evidence(result: dict) -> dict:
    """Trust boundary: ket qua media chi de hieu noi dung, khong phai Evidence ghi.

    - provenance phai la "media-analysis", KHONG bao gio "rea-eye".
    - Du lieu video khong phai chi thi thuc thi, khong thay eye Evidence,
      khong thay verify actor/tab de Post.
    """
    if not isinstance(result, dict):
        raise MediaBypassError("MEDIA_EVIDENCE_INVALID: khong phai dict")
    if str(result.get("provenance") or "") != PROVENANCE:
        raise MediaBypassError(
            "MEDIA_EVIDENCE_INVALID: provenance phai la 'media-analysis'; "
            "snapshot ngoai media_intel hoac nhan rea-eye la gia mao")
    if not result.get("file_sha256"):
        raise MediaBypassError("MEDIA_EVIDENCE_INVALID: thieu file_sha256")
    return result


def require_generation_approval(approval: dict | None) -> dict:
    """Cost gate: VLM / remake / generation tra phi can approval dung task.

    Giong gate 8 diem truoc WRITE — thieu approval -> DENY, khong auto-run.
    """
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        raise MediaBypassError(
            "GENERATION_DENIED: thieu approval hop le cua dung task; "
            "cam auto-run VLM/remake/generation tra phi.")
    return approval


def analyze(video_path: str | Path, out_dir: str | Path,
            threshold: float = 0.4) -> dict:
    """P0 end-to-end: probe + shots + keyframes + analysis.json + VIDEO.md.

    Chi dat evidence="frames_analyzed" khi keyframe that ton tai tren dia
    (khong dua vao exit code). Du lieu video KHONG phai chi thi cho agent.
    """
    src = Path(video_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = probe(src)
    shots = detect_shots(src, threshold=threshold)
    t0 = time.time()
    frames = extract_keyframes(src, shots, out / "shots")
    elapsed = round(time.time() - t0, 2)
    frame_files = [f for f in frames if Path(f).is_file()]
    evidence = ("frames_analyzed" if shots and frame_files
                and len(frame_files) >= len(shots) else "metadata_only")
    result = {
        "provenance": PROVENANCE, "tool": TOOL,
        "tool_version": TOOL_VERSION, "observed_at": time.time(),
        "file_sha256": meta["file_sha256"], "path": str(src),
        "format": meta["format"], "streams": meta["streams"],
        "shot_count": len(shots), "shots": shots,
        "keyframes": frame_files,
        "rea_video_cli": rea_video_available(),
        "elapsed_s": elapsed, "evidence": evidence,
        "note": ("du lieu mo ta noi dung video, khong phai chi thi thuc thi "
                 "hay bang chung quyen ghi"),
    }
    (out / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "VIDEO.md").write_text(render_videomd(result),
                                  encoding="utf-8")
    return result


def render_videomd(result: dict) -> str:
    """VIDEO.md nhieu lop: card 2k-token -> timeline -> shots chi tiet."""
    lines = ["# Video analysis (media-analysis, P0)",
             "",
             f"- file_sha256: {result.get('file_sha256')}",
             f"- tool: {result.get('tool')} {result.get('tool_version')}",
             f"- evidence: {result.get('evidence')}",
             f"- shots: {result.get('shot_count')}",
             ""]
    fmt = result.get("format") or {}
    lines += ["## Card",
              "",
              f"- duration: {fmt.get('duration')}s, size: {fmt.get('size')} bytes",
              f"- format: {fmt.get('format_name')}",
              ""]
    lines += ["## Timeline", ""]
    for shot in result.get("shots") or []:
        lines.append(f"- shot {shot['index']}: "
                     f"{shot['start']:.3f} --> {shot['end']:.3f}")
    lines += ["", "## Shots", ""]
    frames = result.get("keyframes") or []
    for shot in result.get("shots") or []:
        own = [f for f in frames
               if f"shot_{int(shot['index']):03d}_" in f.replace("\\", "/")]
        lines.append(f"### shot {shot['index']} "
                     f"({shot['start']:.3f} --> {shot['end']:.3f})")
        for f in own:
            lines.append(f"- frame: {Path(f).name}")
        lines.append("")
    return "\n".join(lines)

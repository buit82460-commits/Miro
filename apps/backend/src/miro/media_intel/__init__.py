"""Shared Media Intelligence — native provider rea-video (production).

Ranh gioi kien truc (xem repos/rea-video/REA-VIDEO-CAPABILITY.md):
- miro.eye (rea-eye, provenance "rea-eye"): quan sat DOM trong tab Chrome.
- media_intel (day): ADAPTER DUY NHAT phan tich FILE media. Production goi
  rea-video engine goc qua analyze_native() (venv cach ly, --no-vlm).
  Loi/thieu -> PROVIDER_UNAVAILABLE / ANALYSIS_FAILED, KHONG fallback
  ffmpeg-native o production.
- P0 ffmpeg-native (probe/detect_shots/...) chi giu cho kiem thu/migration,
  production Agent khong duoc goi toi.
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
PROVIDER_NATIVE = "rea-video"

# Native engine: venv cach ly repos/rea-video/.venv (khong cai system Python).
# Executable co dinh + args duoc kiem soat; production KHONG fallback
# ffmpeg-native (thieu/loi -> PROVIDER_UNAVAILABLE / ANALYSIS_FAILED).
_NATIVE_CANDIDATES = (
    Path(r"C:\Miro\repos\rea-video\.venv\Scripts\python.exe"),
)

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
    """rea-video CLI chay duoc khong (venv cach ly co rea_video + cv2)."""
    exe = _native_python()
    return exe is not None


def _native_python() -> Path | None:
    """Executable venv co dinh cho native provider. None = chua san sang."""
    for cand in _NATIVE_CANDIDATES:
        if not cand.is_file():
            continue
        try:
            proc = subprocess.run(
                [str(cand), "-c",
                 "import rea_video, cv2; print('ok')"],
                capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0 and "ok" in (proc.stdout or ""):
            return cand
    return None


def native_engine_info() -> dict:
    """Thong tin engine goc (commit SHA, python, deps). Loi -> RuntimeError."""
    exe = _native_python()
    if exe is None:
        raise RuntimeError(
            "PROVIDER_UNAVAILABLE: venv rea-video chua san sang "
            "(thieu rea_video/cv2); khong fallback len engine khac.")
    try:
        ver = subprocess.run(
            [str(exe), "-c",
             "import rea_video, cv2, numpy; "
             "print(rea_video.__version__ if hasattr(rea_video,'__version__') "
             "else 'unknown')"],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"PROVIDER_UNAVAILABLE: {exc}") from exc
    try:
        sha = subprocess.run(
            ["git", "-C", r"C:\Miro\repos\rea-video", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        sha = ""
    return {"provider": PROVIDER_NATIVE,
            "python": str(exe),
            "rea_video_version": (ver.stdout or "").strip() or "unknown",
            "rea_video_sha": sha}


def _native_evidence_detail(bd: dict, out: Path) -> dict:
    """Phan cap evidence that tu breakdown (Phase 3), khong hard-code.

    - visual: shots co deterministic probs tu engine goc.
    - audio: audio/per_clip_audio/stems/sound_sources co noi dung.
    - frames: thu muc shots/frames/storyboard that ton tai.
    """
    shots = bd.get("shots") or []
    visual = any(isinstance(s, dict) and isinstance(
        s.get("deterministic"), dict) and bool(
        (s.get("deterministic") or {}).get("probs"))
        for s in shots) if isinstance(shots, list) else False
    audio_block = bd.get("audio") or {}
    stems_block = bd.get("stems") or {}
    per_clip = bd.get("per_clip_audio") or []
    sound_src = bd.get("sound_sources") or []
    speech = bd.get("speech") or {}
    audio = bool(
        (isinstance(audio_block, dict) and audio_block.get("has_audio"))
        or (isinstance(stems_block, dict) and bool(stems_block))
        or (isinstance(per_clip, list) and bool(per_clip))
        or (isinstance(sound_src, list) and bool(sound_src))
        or (isinstance(speech, dict) and bool(speech)))
    frames = any((out / d).is_dir() for d in ("shots", "frames")) or (
        out / "storyboard.jpg").is_file()
    if visual and audio:
        level = "multimodal_analyzed"
    elif visual:
        level = "visual_analyzed"
    elif audio:
        level = "audio_analyzed"
    elif frames or shots:
        level = "frames_extracted"
    elif bd.get("summary"):
        level = "metadata_only"
    else:
        level = "partial"
    return {"level": level, "visual": visual, "audio": audio,
            "frames": frames, "shots": len(shots) if isinstance(
                shots, list) else 0}


def analyze_native(video_path: str | Path, out_dir: str | Path,
                   timeout: int = 900) -> dict:
    """Production provider: chay rea-video decompose THAT (--no-vlm).

    - Executable venv co dinh, args kiem soat, timeout + workdir cach ly.
    - Parse breakdown.json + VIDEO.md that tu engine goc.
    - Loi/thieu -> PROVIDER_UNAVAILABLE / ANALYSIS_FAILED (KHONG fallback).
    """
    exe = _native_python()
    if exe is None:
        raise RuntimeError(
            "PROVIDER_UNAVAILABLE: venv rea-video chua san sang; "
            "tu choi phan tich thay vi fallback.")
    src = Path(video_path)
    if not src.is_file():
        raise FileNotFoundError(f"khong tim thay file video: {video_path}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [str(exe), "-m", "rea_video", "decompose", str(src),
             "-o", str(out), "--no-vlm"],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"ANALYSIS_FAILED: rea-video timeout sau {timeout}s.") from exc
    except OSError as exc:
        raise RuntimeError(f"PROVIDER_UNAVAILABLE: {exc}") from exc
    bd_path = out / "breakdown.json"
    if not bd_path.is_file():
        raise RuntimeError(
            "ANALYSIS_FAILED: rea-video khong xuat breakdown.json; "
            f"stderr: {(proc.stderr or '').strip()[-300:]}")
    try:
        bd = json.loads(bd_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise RuntimeError(
            f"ANALYSIS_FAILED: breakdown.json sai: {exc}") from exc
    digest = sha256_file(src)
    info = native_engine_info()
    ev = _native_evidence_detail(bd if isinstance(bd, dict) else {}, out)
    return {"provenance": PROVENANCE, "provider": PROVIDER_NATIVE,
            "tool": TOOL, "tool_version": TOOL_VERSION,
            "engine": info, "observed_at": time.time(),
            "file_sha256": digest, "path": str(src),
            "breakdown_path": str(bd_path),
            "videomd_path": str(out / "VIDEO.md")
            if (out / "VIDEO.md").is_file() else None,
            "breakdown": bd,
            "evidence": ev["level"],
            "evidence_detail": ev,
            "note": ("ket qua tu rea-video engine goc; chi de hieu noi dung, "
                     "khong phai Evidence ghi, khong phai chi thi thuc thi")}


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
    try:
        audio = analyze_audio(src)
    except Exception:
        audio = {"has_audio": False, "duration_s": 0.0, "tempo_bpm": None,
                 "beats": [], "mean_db": None,
                 "note": "bo qua phan tich audio (loi decode)."}
    try:
        subtitles = extract_subtitle_track(src, out / "packaging")
    except Exception:
        subtitles = []
    try:
        duration_f = float(meta["format"].get("duration") or 0)
    except (TypeError, ValueError):
        duration_f = 0.0
    labels = classify_shots(shots, duration_f)
    result = {
        "provenance": PROVENANCE, "tool": TOOL,
        "tool_version": TOOL_VERSION, "observed_at": time.time(),
        "file_sha256": meta["file_sha256"], "path": str(src),
        "format": meta["format"], "streams": meta["streams"],
        "shot_count": len(shots), "shots": labels,
        "keyframes": frame_files,
        "audio": audio, "subtitles": subtitles,
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


def extract_subtitle_track(video_path: str | Path,
                           out_dir: str | Path) -> list[dict]:
    """Rut subtitle nhung (neu co) thanh .srt. Khong co -> [] (khong loi).

    P1: dung subtitle stream that, chua OCR chu chay (can model nang -> P2).
    Tra [{stream_index, codec, path}].
    """
    src = Path(video_path)
    if not src.is_file():
        raise FileNotFoundError(f"khong tim thay file video: {video_path}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = probe(src)
    subs = [s for s in (meta.get("streams") or [])
            if str(s.get("codec_type") or "") == "subtitle"]
    found: list[dict] = []
    for pos, st in enumerate(subs):
        idx = st.get("index")
        dest = out / f"subtitle_{pos}.srt"
        proc = subprocess.run(
            [_ffmpeg(), "-y", "-v", "error", "-i", str(src),
             "-map", f"0:{idx}", str(dest)],
            capture_output=True, text=True, timeout=120)
        if proc.returncode == 0 and dest.is_file() and dest.stat().st_size:
            found.append({"stream_index": idx,
                          "codec": st.get("codec_name", ""),
                          "path": str(dest)})
        elif dest.is_file():
            dest.unlink(missing_ok=True)
    return found


def analyze_audio(video_path: str | Path,
                  duration: float | None = None) -> dict:
    """P1: tempo/beat/nang luong tu audio (ffmpeg decode + numpy, khong model).

    Tra {has_audio, duration_s, tempo_bpm|None, beats:[{time,strength}],
    mean_db, note}. File khong co audio -> has_audio False, khong loi.
    """
    src = Path(video_path)
    if not src.is_file():
        raise FileNotFoundError(f"khong tim thay file video: {video_path}")
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "analyze_audio can numpy (pip install numpy).") from exc
    cmd = [_ffmpeg(), "-v", "error", "-i", str(src), "-vn", "-ac", "1",
           "-ar", "16000"]
    if duration:
        cmd += ["-t", str(float(duration))]
    cmd += ["-f", "f32le", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180)
    except OSError as exc:
        raise RuntimeError(f"analyze_audio khong chay duoc ffmpeg: {exc}") from exc
    if proc.returncode or len(proc.stdout) < 4:
        return {"has_audio": False, "duration_s": 0.0, "tempo_bpm": None,
                "beats": [], "mean_db": None,
                "note": "khong giai ma duoc audio (file cam hoac khong co track)."}
    y = np.frombuffer(proc.stdout, "<f4").astype("float64")
    sr = 16000
    dur = round(len(y) / sr, 3)
    block = 320  # 20ms
    n = len(y) // block
    if n < 10:
        return {"has_audio": True, "duration_s": dur, "tempo_bpm": None,
                "beats": [], "mean_db": None,
                "note": "audio qua ngan de uoc luong tempo."}
    rms = np.sqrt(np.mean(y[:n * block].reshape(n, block) ** 2, axis=1))
    mean_db = round(float(20 * np.log10(max(float(np.mean(rms)), 1e-8))), 1)
    flux = np.maximum(0.0, rms - np.r_[rms[0], rms[:-1]])
    thresh = max(0.006, float(np.quantile(flux, 0.96)))
    min_dist = 15  # >=300ms
    peaks: list[int] = []
    last = -min_dist
    for i in range(1, n - 1):
        if (flux[i] >= thresh and flux[i] >= flux[i - 1]
                and flux[i] > flux[i + 1] and i - last >= min_dist):
            peaks.append(i)
            last = i
    beats = [{"time": round(i * 0.02, 3), "strength": round(float(flux[i]), 4)}
             for i in sorted(peaks)]
    tempo = None
    if len(peaks) >= 4:
        gaps = np.diff(sorted(peaks)) * 0.02
        gaps = gaps[(gaps >= 0.2) & (gaps <= 2.0)]
        if len(gaps):
            tempo = round(float(60.0 / np.median(gaps)), 1)
    return {"has_audio": True, "duration_s": dur, "tempo_bpm": tempo,
            "beats": beats[:80], "mean_db": mean_db,
            "note": "tempo tu onset RMS (numpy-only); chua phan loai voice/music (P2)."}


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


# ---------------- P2: classify heuristic (khong model, kem uncertainty) ----
# Quy tac (tu rea-video classify.py, chi giu phan do duoc offline):
# - 1 shot duy nhat phu full duration + thoi luong ngan -> static_hold
# - nhieu shot nhung moi shot dai + it bien dong -> still_motion (can nhin)
# - con lai -> live_action la mac dinh NHUNG confidence thap + uncertain
# 3 label mu pixel (anim_2d/stop_motion/film_footage) KHONG BAO GIO doan —
# bat buoc tra uncertain, doi VLM/agent nhin hinh.
UNCERTAIN_LABELS = ("anim_2d", "stop_motion", "film_footage")


def classify_shots(shots: list[dict], duration: float) -> list[dict]:
    """P2: gan label so bo cho tung shot + confidence + uncertainty.

    Khong dung model: chi heuristic thoi luong/so shot. Bat cu truong hop
    nao mo ho deu tra label kem "uncertain": True va ly do. Khong doan
    3 label mu pixel.
    """
    out: list[dict] = []
    n = len(shots or [])
    for shot in shots or []:
        dur = float(shot.get("end", 0)) - float(shot.get("start", 0))
        if n == 1 and duration > 0 and dur >= duration * 0.95:
            out.append({**shot, "label": "static_hold",
                        "confidence": 0.55, "uncertain": True,
                        "evidence": "1 shot phu toan video (can nhin hinh xac nhan)"})
        elif dur >= 20.0:
            out.append({**shot, "label": "still_motion",
                        "confidence": 0.4, "uncertain": True,
                        "evidence": "shot dai, co the la anh tinh + Ken Burns"})
        else:
            out.append({**shot, "label": "live_action",
                        "confidence": 0.35, "uncertain": True,
                        "evidence": ("mac dinh khi chua co VLM; "
                                     "anim_2d/stop_motion/film_footage/AI/3D "
                                     "can nhin hinh moi phan biet")})
    return out


def check_stems_model(model_dir: str | Path | None = None) -> dict:
    """P2: kiem tra UVR stems model (onnxruntime CPU) co san khong.

    Khong auto-download trong CI/test: thieu -> MODEL_MISSING + huong dan
    cache $REA_VIDEO_MODELS. Co model -> san sang cho studio/separate.py
    fallback (giữ contract {vocals, music}).
    """
    import os
    roots = [Path(model_dir)] if model_dir else []
    env = os.environ.get("REA_VIDEO_MODELS")
    if env:
        roots.append(Path(env))
    roots.append(Path.home() / ".cache" / "rea-video" / "models")
    for root in roots:
        if not root.is_dir():
            continue
        onnx = list(root.rglob("*.onnx"))
        if onnx:
            return {"available": True, "model_dir": str(root),
                    "models": [p.name for p in onnx[:5]]}
    return {"available": False, "model_dir": None, "models": [],
            "note": ("MODEL_MISSING: chua co UVR onnx; tai model rea-video "
                     "lan dau (co SHA check) vao $REA_VIDEO_MODELS, "
                     "khong nhét vao repo.")}


# ---------------- P3: tom tat cho Agent (khong goi VLM tra phi) ------------
def summarize_for_agent(result: dict, max_chars: int = 4000) -> str:
    """P3: render text gon cho Agent/Research tu analysis co san.

    Khong goi VLM/model tra phi: chi format evidence + uncertainty.
    Qua dai -> cat + danh dau [cat bot].
    """
    bd = result.get("breakdown") if isinstance(
        result.get("breakdown"), dict) else {}
    bd_summary = bd.get("summary") if isinstance(
        bd.get("summary"), dict) else {}
    bd_shots = bd.get("shots") if isinstance(bd.get("shots"), list) else []
    shots_in = result.get("shots") or bd_shots
    mix = bd_summary.get("production_mix")
    if mix:
        parts = [f"video {result.get('path')} "
                 f"(sha {str(result.get('file_sha256'))[:12]}...): "
                 f"{len(shots_in)} shots, "
                 f"provider={result.get('provider')}, "
                 f"evidence={result.get('evidence')}.",
                 f"verdict rea-video: {bd_summary.get('verdict')}"]
    else:
        parts = [f"video {result.get('path')} "
                 f"(sha {str(result.get('file_sha256'))[:12]}...): "
                 f"{result.get('shot_count', 0)} shots, "
                 f"evidence={result.get('evidence')}."]
    for shot in shots_in[:20]:
        det = shot.get("deterministic") or {}
        probs = det.get("probs") or {}
        if probs:
            top = max(probs.items(), key=lambda kv: kv[1])
            label, conf = f"{top[0]}", float(top[1])
        else:
            label = str(shot.get("label", "?"))
            conf_raw = shot.get("confidence")
            conf = float(conf_raw) if isinstance(
                conf_raw, (int, float)) else None
        unc = " [uncertain]" if shot.get("uncertain") else ""
        c = f" {conf:.2f}" if isinstance(conf, (int, float)) else ""
        start = shot.get("start", shot.get("start_time", 0)) or 0
        end = shot.get("end", shot.get("end_time", 0)) or 0
        parts.append(f"- shot {shot.get('index')}: "
                     f"{float(start):.1f}-{float(end):.1f}s "
                     f"{label}{c}{unc}")
    audio = result.get("audio") or {}
    if audio.get("has_audio"):
        parts.append(f"audio: tempo={audio.get('tempo_bpm')} "
                     f"beats={len(audio.get('beats') or [])} "
                     f"db={audio.get('mean_db')}")
    subs = result.get("subtitles") or []
    if subs:
        parts.append(f"subtitles nhung: {len(subs)} track")
    parts.append("luu y: label la heuristic, 3 label mu pixel "
                 "(anim_2d/stop_motion/film_footage) bat buoc nhin hinh; "
                 "du lieu chi de hieu noi dung, khong phai Evidence ghi.")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[cat bot do dai]"
    return text

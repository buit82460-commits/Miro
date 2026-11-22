"""Port tracking ROI tu dubtool sang Miro (thuan stdlib + PIL/numpy lazy, khong opencv).

Nguon port (chi doc, khong sua):
- C:\\dubtool\\core\\studio_analysis.py:47-105 (match_target NCC cuc bo + track_frames
  roi {x, y, width, height} tuong doi 0-1, threshold mac dinh 0.55, dung khi
  confidence < threshold, toi da ~99 frame mau)
- C:\\dubtool\\core\\studio_analysis.py:108-128 (sample_clip: ffmpeg trich frame
  fps thich ung, scale=320:-2, clip <= 180s, can it nhat 2 frame)
- C:\\dubtool\\core\\studio_service.py:508-568 (tracking_frame/track_object lay frame
  dau lam mau, reframe doi xung toa do)
- C:\\dubtool\\core\\studio_ui.py:218-222 (endpoint tracking nhan roi + reframe)

Khac biet o Miro: nhan dau vao linh hoat (thu muc frame HOAC file video),
roi dung khoa ngan {x, y, w, h} (chap nhan alias width/height), khong phu thuoc
opencv/scipy. Neu thieu PIL/numpy/ffmpeg -> khong bia tracking: tra ROI goc voi
score 1.0 va flag static_roi=True tren moi diem.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

SAMPLE_SCALE_WIDTH = 320
MAX_SAMPLE_FRAMES = 99
MAX_SPAN_SECONDS = 180


def _norm_roi(roi: dict) -> dict:
    if not isinstance(roi, dict):
        raise ValueError("roi can la dict {x, y, w, h} tuong doi 0-1.")
    data = dict(roi)
    if "w" not in data and "width" in data:
        data["w"] = data["width"]
    if "h" not in data and "height" in data:
        data["h"] = data["height"]
    if set(data) - {"x", "y", "w", "h", "width", "height"} or any(
        k not in data for k in ("x", "y", "w", "h")
    ):
        raise ValueError("roi can gom x, y, w, h tuong doi 0-1.")
    vals = {k: data[k] for k in ("x", "y", "w", "h")}
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in vals.values()):
        raise ValueError("Toa do roi can la so huu han.")
    if min(vals["x"], vals["y"]) < 0 or min(vals["w"], vals["h"]) <= 0 \
            or vals["x"] + vals["w"] > 1 or vals["y"] + vals["h"] > 1:
        raise ValueError("Vung theo doi phai nam trong khung hinh.")
    return {k: float(v) for k, v in vals.items()}


def _static_points(roi: dict, count: int, fps: float) -> list:
    cx, cy = roi["x"] + roi["w"] / 2, roi["y"] + roi["h"] / 2
    return [{"t": round(i / fps, 4), "x": round(cx, 6), "y": round(cy, 6),
             "score": 1.0, "static_roi": True} for i in range(max(count, 1))]


def _resolve_frames(source, fps: float) -> tuple[list, str | None]:
    """Tra ve (danh sach frame, tmpdir|None). Video -> ffmpeg trich mau."""
    path = Path(source)
    if path.is_dir():
        frames = sorted(p for p in path.iterdir()
                        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp"))
        if not frames:
            raise ValueError("Thu muc khong co frame anh.")
        return frames[:MAX_SAMPLE_FRAMES], None
    if not path.is_file():
        raise ValueError("frames_dir_or_video can la thu muc frame hoac file video.")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("Thieu ffmpeg de trich frame video.")
    tmp = tempfile.mkdtemp(prefix="miro-track-")
    rate = min(max(2.0 / MAX_SPAN_SECONDS, 0.5), min(5.0, fps))
    result = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(path), "-an",
         "-vf", f"fps={rate:.6f},scale={SAMPLE_SCALE_WIDTH}:-2",
         "-frames:v", str(MAX_SAMPLE_FRAMES), str(Path(tmp) / "frame-%04d.png")],
        capture_output=True, timeout=90)
    if result.returncode:
        raise ValueError("Khong trich duoc frame tu video (can ffmpeg).")
    frames = sorted(Path(tmp).glob("frame-*.png"))
    if len(frames) < 1:
        raise ValueError("Video qua ngan, khong co frame de theo doi.")
    return frames, tmp


def _match(gray, template, prev, np) -> tuple:
    """So khop mau cuc bo quanh vi tri cu (NCC; mau phang dung khoang cach mau).

    Nguon y tuong: studio_analysis.match_target (cua so tim kiem margin quanh ROI).
    """
    px, py, pw, ph = prev
    h, w = gray.shape
    margin = max(16, round(max(pw, ph) * 1.2))
    left, top = max(0, px - margin), max(0, py - margin)
    right, bottom = min(w, px + pw + margin), min(h, py + ph + margin)
    search = gray[top:bottom, left:right].astype("float64") / 255.0
    pattern = template.astype("float64") / 255.0
    sh, sw = search.shape
    if sh < ph or sw < pw:
        return prev, 0.0
    centered = pattern - pattern.mean()
    energy = float((centered ** 2).sum())
    best, best_score = (px, py), 0.0
    if energy < 1e-8:
        mean = float(pattern.mean())
        best_err = None
        for yy in range(0, sh - ph + 1):
            for xx in range(0, sw - pw + 1):
                err = float((((search[yy:yy + ph, xx:xx + pw] - mean) ** 2).mean()))
                score = float(1.0 / (1.0 + err * 50.0))
                pen = 1e-5 * ((left + xx - px) ** 2 + (top + yy - py) ** 2)
                if best_err is None or err + pen < best_err:
                    best_err = err + pen
                    best, best_score = (left + xx, top + yy), score
        return (*best, pw, ph), float(max(0.0, min(1.0, best_score)))
    denom_tpl = float((centered ** 2).sum())
    for yy in range(0, sh - ph + 1):
        for xx in range(0, sw - pw + 1):
            window = search[yy:yy + ph, xx:xx + pw]
            wc = window - window.mean()
            denom = (denom_tpl * float((wc ** 2).sum())) ** 0.5
            score = float((centered * wc).sum() / denom) if denom > 1e-10 else 0.0
            pen = 1e-5 * ((left + xx - px) ** 2 + (top + yy - py) ** 2)
            adj = max(0.0, min(1.0, score)) - pen
            if adj > best_score - (0.0 if best_score else 1.0) and (adj > best_score or best_score == 0.0):
                best_score, best = adj, (left + xx, top + yy)
    return (*best, pw, ph), float(max(0.0, min(1.0, best_score)))


def track_frames(frames_dir_or_video, roi: dict, threshold: float = 0.55,
                 fps: float = 2.0) -> list:
    """Bam ROI qua cac frame, tra [{t, x, y, score}] (x/y la tam tuong doi 0-1).

    Nguon: studio_analysis.track_frames (template tu frame dau, dung khi
    confidence < threshold). Neu thieu PIL/numpy/ffmpeg -> tra ROI goc,
    score 1.0, flag static_roi=True (khong bia tracking).
    """
    roi = _norm_roi(roi)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) \
            or not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("threshold can trong (0, 1].")
    try:
        from PIL import Image  # lazy
        import numpy as np  # lazy
    except ImportError:
        return _static_points(roi, 1, fps)
    try:
        frames, tmp = _resolve_frames(frames_dir_or_video, fps)
    except RuntimeError:
        return _static_points(roi, 1, fps)
    try:
        with Image.open(frames[0]) as img:
            first = np.asarray(img.convert("L"))
        height, width = first.shape
        x, y = round(roi["x"] * width), round(roi["y"] * height)
        w = min(width - x, round(roi["w"] * width))
        h = min(height - y, round(roi["h"] * height))
        if min(w, h) < 4:
            raise ValueError("Vung theo doi qua nho; can it nhat 4 pixel.")
        template = first[y:y + h, x:x + w].copy()
        prev = (x, y, w, h)
        points = []
        for index, file in enumerate(frames):
            score = 1.0
            if index:
                with Image.open(file) as img:
                    gray = np.asarray(img.convert("L"))
                if gray.shape != first.shape:
                    with Image.open(file) as img2:
                        gray = np.asarray(img2.convert("L").resize((width, height)))
                prev, score = _match(gray, template, prev, np)
                if score < threshold:
                    break
            bx, by, bw, bh = prev
            points.append({"t": round(index / fps, 4),
                           "x": round((bx + bw / 2) / width, 6),
                           "y": round((by + bh / 2) / height, 6),
                           "score": round(float(score), 4)})
        if not points:
            return _static_points(roi, 1, fps)
        return points
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


def reframe_box(track: dict, canvas_w: int, canvas_h: int, zoom: float = 1.5) -> dict:
    """Tinh khung reframe (pixel) bam theo diem track hien tai.

    Nguon y tuong: studio_service.track_object(reframe=True) dao toa do de giu
    vat the giua khung. `track` la 1 diem {x, y} tuong doi 0-1 (lay tu
    track_frames). zoom >= 1: khung cang nho khi zoom cang lon.
    """
    if not isinstance(track, dict) or any(k not in track for k in ("x", "y")):
        raise ValueError("track can la diem {x, y} tuong doi 0-1.")
    for key in ("x", "y"):
        v = track[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError("track x/y can la so huu han.")
    if isinstance(zoom, bool) or not isinstance(zoom, (int, float)) \
            or not math.isfinite(zoom) or zoom < 1:
        raise ValueError("zoom can >= 1.")
    cx = min(1.0, max(0.0, float(track["x"]))) * canvas_w
    cy = min(1.0, max(0.0, float(track["y"]))) * canvas_h
    bw, bh = canvas_w / zoom, canvas_h / zoom
    bx = min(canvas_w - bw, max(0.0, cx - bw / 2))
    by = min(canvas_h - bh, max(0.0, cy - bh / 2))
    return {"x": round(bx, 2), "y": round(by, 2),
            "w": round(bw, 2), "h": round(bh, 2)}

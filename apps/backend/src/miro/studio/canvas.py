"""Canvas + export args cho studio timeline (port tu dubtool, thuan stdlib).

Nguon (chi doc, khong copy nguyen ham):
- C:\\dubtool\\core\\studio_model.py dong 31 (EXPORT{fps,codec,quality,audio_bitrate,interpolation})
  + dong 545+ (set_canvas: update canvas width/height/background).
- C:\\dubtool\\core\\studio_render.py dong 329-398 (progress pipe, preview rut gon 20s,
  preview scale nho ~640, codec h264, fps lay tu export).
- C:\\dubtool\\web\\src\\app\\editor\\page.tsx dong 147-152
  (preset 1920x1080 / 1080x1920 / 1080x1080).
"""
from __future__ import annotations

CANVAS_PRESETS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}

EXPORT_DEFAULTS = {
    "fps": 30,
    "codec": "h264",
    "crf": 23,
    "audio_bitrate": "192k",
    "interpolation": "bilinear",
}

_MIN_WH = 16
_MAX_WH = 8192


def _check_wh(w, h):
    for v, name in ((w, "w"), (h, "h")):
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f"{name} phai la so nguyen.")
        if not _MIN_WH <= v <= _MAX_WH:
            raise ValueError(f"{name} phai trong khoang {_MIN_WH}..{_MAX_WH}.")
    return w, h


def resolve_canvas(preset_or_wh, background="black"):
    """Giai quyet canvas tu preset ("16:9") hoac "WxH" hoac tuple (w, h).

    Tra ve dict {w, h, background}. Validate kich thuoc 16..8192.
    """
    if not isinstance(background, str) or not background.strip():
        raise ValueError("background can la chuoi khac rong.")
    w = h = None
    if isinstance(preset_or_wh, tuple) and len(preset_or_wh) == 2:
        w, h = preset_or_wh
    elif isinstance(preset_or_wh, str):
        key = preset_or_wh.strip()
        if key in CANVAS_PRESETS:
            w, h = CANVAS_PRESETS[key]
        else:
            parts = key.lower().replace(" ", "").split("x")
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                w, h = int(parts[0]), int(parts[1])
            else:
                raise ValueError(
                    "preset_or_wh phai la '16:9'/'9:16'/'1:1'/'4:5', 'WxH' hoac tuple (w,h)."
                )
    else:
        raise ValueError(
            "preset_or_wh phai la '16:9'/'9:16'/'1:1'/'4:5', 'WxH' hoac tuple (w,h)."
        )
    w, h = _check_wh(w, h)
    return {"w": w, "h": h, "background": background}


def fit_filter(src_w, src_h, canvas_w, canvas_h, mode="contain"):
    """Tao filter scale+pad (contain) hoac scale+crop (cover)."""
    for v, name in ((src_w, "src_w"), (src_h, "src_h"),
                    (canvas_w, "canvas_w"), (canvas_h, "canvas_h")):
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            raise ValueError(f"{name} phai la so nguyen duong.")
    if mode not in ("contain", "cover"):
        raise ValueError("mode chi nhan 'contain' hoac 'cover'.")
    if mode == "contain":
        return (
            f"scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=decrease,"
            f"pad={canvas_w}:{canvas_h}:(ow-iw)/2:(oh-ih)/2:color=black"
        )
    return (
        f"scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=increase,"
        f"crop={canvas_w}:{canvas_h}"
    )


def blur_background():
    """CHUA CO NGUON — de trong (khong port; dubtool chua co blur background)."""
    raise NotImplementedError("CHUA CO NGUON — de trong")


LADDER = (
    {"name": "480p", "w": 854, "h": 480, "crf": 26, "audio_bitrate": "128k"},
    {"name": "720p", "w": 1280, "h": 720, "crf": 24, "audio_bitrate": "160k"},
    {"name": "1080p", "w": 1920, "h": 1080, "crf": 23, "audio_bitrate": "192k"},
    {"name": "4K", "w": 3840, "h": 2160, "crf": 22, "audio_bitrate": "256k"},
)


def export_ladder(canvas, export, rungs=("480p", "720p", "1080p")):
    """Ke hoach ladder (ffmpeg scale lanczos that, khong AI-upscale).

    Tra list [{name, w, h, args}]. Rung la → ValueError. Canvas/validate
    theo validate_export (chi h264).
    """
    cfg = validate_export(export or {})
    if not isinstance(canvas, dict) or "w" not in canvas or "h" not in canvas:
        raise ValueError("canvas can co 'w' va 'h'.")
    wanted = list(rungs or ())
    known = {r["name"]: r for r in LADDER}
    plans = []
    for name in wanted:
        rung = known.get(name)
        if rung is None:
            raise ValueError(f"rung khong ho tro: {name!r} (chon trong 480p/720p/1080p/4K).")
        w, h = rung["w"], rung["h"]
        args = ["-s", f"{w}x{h}", "-r", str(cfg["fps"]), "-c:v", "libx264",
                "-crf", str(rung["crf"]), "-preset", "veryfast",
                "-c:a", "aac", "-b:a", rung["audio_bitrate"],
                "-vf", "scale=%d:%d:flags=lanczos" % (w, h)]
        plans.append({"name": name, "w": w, "h": h, "args": args})
    return plans


def upscale_filter(scale: float) -> str:
    """Upscale bang ffmpeg scale lanczos that (khong AI model).

    scale 1..4 (vd 2.0 = gap doi). Khac upscale AI — ghi ro de khong bia.
    """
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) \
            or not 1 <= scale <= 4:
        raise ValueError("upscale scale phai trong 1..4.")
    return f"scale=iw*{float(scale):.3g}:ih*{float(scale):.3g}:flags=lanczos"


def validate_export(export):
    """Validate dict export, tra ve dict da chuan hoa.

    Quy tac: fps 1..120, crf 0..51, codec chi h264
    (khac -> ValueError "chi ho tro h264").
    """
    if not isinstance(export, dict):
        raise ValueError("export phai la dict.")
    merged = dict(EXPORT_DEFAULTS)
    merged.update(export)
    codec = str(merged.get("codec", "h264")).lower()
    if codec != "h264":
        raise ValueError("chi ho tro h264")
    merged["codec"] = codec
    fps = merged.get("fps")
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not 1 <= fps <= 120:
        raise ValueError("fps phai trong khoang 1..120.")
    merged["fps"] = int(fps)
    crf = merged.get("crf", merged.get("quality", 23))
    if isinstance(crf, bool) or not isinstance(crf, (int, float)) or not 0 <= crf <= 51:
        raise ValueError("crf phai trong khoang 0..51.")
    merged["crf"] = int(crf)
    ab = str(merged.get("audio_bitrate", "192k"))
    digits = "".join(ch for ch in ab if ch.isdigit())
    if not digits:
        raise ValueError("audio_bitrate khong hop le.")
    if ab.strip()[-1:].lower() != "k":
        ab = f"{digits}k"
    merged["audio_bitrate"] = ab
    if str(merged.get("interpolation", "bilinear")).strip() == "":
        merged["interpolation"] = "bilinear"
    return merged


def export_args(canvas, export, preview):
    """Tra ve args ffmpeg cho render xuat file.

    Co ban: -s WxH -r fps -c:v libx264 -crf N -preset veryfast -c:a aac -b:a 192k.
    preview=True -> them -t 20 -vf scale nho (scale=min(640,iw)).
    """
    if not isinstance(canvas, dict) or "w" not in canvas or "h" not in canvas:
        raise ValueError("canvas can co 'w' va 'h'.")
    w, h = _check_wh(int(canvas["w"]), int(canvas["h"]))
    cfg = validate_export(export or {})
    args = [
        "-s", f"{w}x{h}",
        "-r", str(cfg["fps"]),
        "-c:v", "libx264",
        "-crf", str(cfg["crf"]),
        "-preset", "veryfast",
        "-c:a", "aac",
        "-b:a", cfg["audio_bitrate"],
    ]
    if preview:
        args += ["-t", "20", "-vf", "scale=min(640\\,iw):-2"]
    return args

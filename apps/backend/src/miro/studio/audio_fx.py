"""Audio FX: sinh chuoi filter ffmpeg + tinh toan so (thuan stdlib, khong chay ffmpeg).

Nguon port:
- C:\\dubtool\\core\\studio_render.py:134-145 (volume_dB/atempo/afade/bass/treble/afftdn)
- C:\\dubtool\\core\\studio_render.py:184-199 (ducking threshold/duck_db/attack/release)
- C:\\dubtool\\core\\studio_render.py:205-218 (loudnorm, TP=-1.5/LRA=11)
- C:\\dubtool\\core\\studio_model.py:26 (AUDIO_EFFECTS), :30 (AUDIO_MIX), :87-90 (bounds)
- C:\\dubtool\\core\\ffmpeg_utils.py:16-27 (atempo_chain)
- C:\\dubtool\\core\\mix.py:65-72 (orig_gain_db, mix), :75-80 (peak normalize -1.5 dB)
"""
from __future__ import annotations

import math

AUDIO_EFFECTS = ("bass", "treble", "denoise", "volume", "fade_in", "fade_out", "tempo")

AUDIO_MIX_DEFAULTS = {
    "ducking": False,
    "duck_db": -12.0,
    "threshold": -35.0,
    "attack": 0.03,
    "release": 0.3,
    "lufs": None,
}


def _num(params: dict, key: str, default: float) -> float:
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{key} can la so huu han.")
    return float(value)


def atempo_chain(speed: float) -> str:
    """Nguon: C:\\dubtool\\core\\ffmpeg_utils.py:16-27. atempo chi nhan 0.5-2.0."""
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or speed <= 0:
        raise ValueError("speed can la so duong huu han.")
    parts: list[str] = []
    s = float(speed)
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.6g}")
    return ",".join(parts)


def audio_filter(effect: str, params: dict) -> str:
    """Tra ve 1 filter ffmpeg cho effect. Nguon chinh: studio_render.py:134-145."""
    params = dict(params or {})
    if effect == "bass":
        gain = _num(params, "gain_db", params.get("bass_db", 0.0))
        freq = _num(params, "freq", 200.0)
        if not -20 <= gain <= 20:
            raise ValueError("bass gain_db phai trong -20..20.")
        return f"bass=g={gain}:f={freq}:w=0.5"
    if effect == "treble":
        gain = _num(params, "gain_db", params.get("treble_db", 0.0))
        freq = _num(params, "freq", 3000.0)
        if not -20 <= gain <= 20:
            raise ValueError("treble gain_db phai trong -20..20.")
        return f"treble=g={gain}:f={freq}:w=0.5"
    if effect == "denoise":
        return "afftdn=nr=8:nf=-35:tn=1"
    if effect == "volume":
        db = _num(params, "db", params.get("volume_db", 0.0))
        if not -60 <= db <= 12:
            raise ValueError("volume db phai trong -60..12.")
        return f"volume={db}dB"
    if effect == "fade_in":
        duration = _num(params, "duration", 0.0)
        if duration < 0:
            raise ValueError("fade_in duration khong am.")
        return f"afade=t=in:st=0:d={duration}"
    if effect == "fade_out":
        duration = _num(params, "duration", 0.0)
        start = _num(params, "start", max(0.0, _num(params, "clip_duration", duration) - duration))
        if duration < 0 or start < 0:
            raise ValueError("fade_out duration/start khong am.")
        return f"afade=t=out:st={start:.9f}:d={duration}"
    if effect == "tempo":
        return atempo_chain(_num(params, "speed", 1.0))
    raise ValueError(f"effect khong ho tro: {effect}. Chon trong {AUDIO_EFFECTS}.")


def mix_filter(inputs: list, mix: dict) -> str:
    """Chain amix + ducking (sidechaincompress) + loudnorm 1-pass.

    Nguon: studio_render.py:184-199 (ducking), :205-206 (loudnorm I/TP/LRA),
    studio_model.py:30 (defaults), mix.py:65-72 (orig gain) / :75-80 (peak -1.5dB).
    `inputs` chi dung de dem so nguon cho amix (doi so luong input).
    """
    cfg = {**AUDIO_MIX_DEFAULTS, **(mix or {})}
    n = max(1, len(inputs))
    chain = [f"amix=inputs={n}:normalize=0"]
    if cfg.get("ducking"):
        duck_db = float(cfg.get("duck_db", -12.0))
        threshold = float(cfg.get("threshold", cfg.get("threshold_db", -35.0)))
        attack = float(cfg.get("attack", 0.03))
        release = float(cfg.get("release", 0.3))
        ratio = max(1.0, abs(duck_db) / 3.0 + 1.0)
        chain.append(
            "sidechaincompress=threshold={:.1f}dB:ratio={:.2f}:attack={}:release={}".format(
                threshold, ratio, attack, release
            )
        )
    if cfg.get("lufs") is not None:
        target = parse_lufs(cfg["lufs"])
        chain.append(f"loudnorm=I={target}:TP=-1.5:LRA=11")
    else:
        chain.append("alimiter=level_in=1:level_out=1:limit=0.841:attack=7:release=100")
    return ",".join(chain)


def parse_lufs(value) -> float:
    """Validate muc tieu LUFS trong -40..-10. Nguon bounds: studio_model.py:87-90."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("LUFS can la so huu han.")
    result = float(value)
    if not -40 <= result <= -10:
        raise ValueError("LUFS phai trong khoang -40..-10.")
    return result


def beat_detect(audio_path: str, params: dict | None = None) -> dict:
    """Phat hien nhip/beat that tu audio (RMS onset + khoang lang).

    Port tu dubtool `core/reference_blueprint.py:36-65` (audio_evidence):
    ffmpeg decode mono 16k -> RMS block 20ms -> flux duong -> peak picking
    (quantile 96% + khoang cach toi thieu). Khong dung librosa/scipy/aubio;
    chi can ffmpeg + numpy (lazy). Peak picking thay find_peaks bang
    local-max tu viet (numpy thuan).
    Tra {"present", "beats": [{time, strength, confidence}],
         "silences": [[start, end]], "note"}.
    """
    import shutil
    import subprocess

    try:
        import numpy as np  # lazy
    except ImportError as exc:
        raise RuntimeError("beat_detect can numpy (pip install numpy).") from exc
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("beat_detect can ffmpeg.")
    src = str(audio_path)
    cfg = dict(params or {})
    duration = cfg.get("duration")
    cmd = [ffmpeg, "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000"]
    if duration:
        cmd += ["-t", str(float(duration))]
    cmd += ["-f", "f32le", "-"]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
    except OSError as exc:
        raise RuntimeError(f"beat_detect khong chay duoc ffmpeg: {exc}") from exc
    if result.returncode or len(result.stdout) < 4:
        raise ValueError("Khong giai ma duoc audio de phan tich nhip.")
    values = np.frombuffer(result.stdout, "<f4").astype("float64")
    block = 320  # 20ms @16k
    n = len(values) // block
    if not n:
        return {"present": True, "beats": [], "silences": [],
                "note": "Audio qua ngan de phan tich nhip."}
    rms = np.sqrt(np.mean(values[:n * block].reshape(n, block) ** 2, axis=1))
    db = 20 * np.log10(np.maximum(rms, 1e-8))
    flux = np.maximum(0.0, rms - np.r_[rms[0], rms[:-1]])
    thresh = max(0.006, float(np.quantile(flux, 0.96)))
    min_dist = 15
    peaks: list[int] = []
    last = -min_dist
    for i in range(1, n - 1):
        if flux[i] >= thresh and flux[i] >= flux[i - 1] \
                and flux[i] > flux[i + 1] and i - last >= min_dist:
            peaks.append(i)
            last = i
    strongest = sorted(peaks, key=lambda i: float(flux[i]), reverse=True)[:80]
    beats = [{"time": round(int(i) * 0.02, 3),
              "strength": round(float(flux[i]), 4),
              "confidence": 0.45} for i in sorted(strongest)]
    silences: list[list[float]] = []
    start = None
    total_dur = n * 0.02
    for i, quiet in enumerate(list(db < -35) + [False]):
        if quiet and start is None:
            start = i
        elif not quiet and start is not None:
            if (i - start) * 0.02 >= 0.65:
                silences.append([round(start * 0.02, 3),
                                 round(min(total_dur, i * 0.02), 3)])
            start = None
    return {"present": True, "beats": beats, "silences": silences,
            "note": "RMS 20ms; diem tang nang luong uoc luong, "
                    "chua phan loai SFX/nhac/thoai."}

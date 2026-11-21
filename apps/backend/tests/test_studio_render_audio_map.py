# -*- coding: utf-8 -*-
"""Studio render phai map dung audio mix (khong roi ve tieng goc).

Bug: nhanh render mac dinh (khong overlay/subtitle/preview) khong co
`-map` nao nen ffmpeg tu chon stream -> MP4 ra tieng goc du da mix.
Test do tan so that: video goc tone 440Hz + mix 880Hz, output phai
uu tien 880Hz. + assert lenh map + fallback an toan khi thieu mix.
"""
import math
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.studio.pipeline import LocalEngine


def _sine_wav(path: Path, freq: float, secs: float = 3.0, rate: int = 44100) -> Path:
    import array
    n = int(rate * secs)
    frames = array.array("h")
    for i in range(n):
        frames.append(int(15000 * math.sin(2 * math.pi * freq * i / rate)))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(frames.tobytes())
    return path


def _goertzel(path: Path, target: float) -> float:
    with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        nch, sw = wav.getnchannels(), wav.getsampwidth()
        raw = wav.readframes(wav.getnframes())
    import array
    fmt = {1: "b", 2: "h", 4: "i"}[sw]
    data = array.array(fmt, raw)
    if sw == 1:
        data = array.array("h", (s * 256 for s in data))
    mono = [sum(data[i + c] for c in range(nch)) / nch
            for i in range(0, len(data) - nch + 1, nch)]
    omega = 2.0 * math.pi * target / rate
    cos, sin = math.cos(omega), math.sin(omega)
    coeff = 2.0 * cos
    s0 = s1 = s2 = 0.0
    for s in mono:
        s0 = s + coeff * s1 - s2
        s2, s1 = s1, s0
    return s1 * s1 + s2 * s2 - coeff * s1 * s2


def _extract_wav(src: Path, dest: Path) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-vn", "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(dest)],
        check=True, timeout=120)
    return dest


def test_C13_default_render_maps_mix_audio(tmp_path):
    eng = LocalEngine()
    video = tmp_path / "orig440.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=3",
         "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
         "-shortest", str(video)],
        check=True, timeout=120)
    mix = _sine_wav(tmp_path / "mix880.wav", 880.0)
    out = tmp_path / "out.mp4"
    eng.render_video(str(video), str(mix), out)
    assert out.is_file()
    got = _extract_wav(out, tmp_path / "out.wav")
    e880, e440 = _goertzel(got, 880.0), _goertzel(got, 440.0)
    assert e880 > e440 * 4, f"output van tieng goc: E880={e880:.0f} E440={e440:.0f}"


def test_C14_default_cmd_contains_map_mix(monkeypatch, tmp_path):
    eng = LocalEngine()
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"x")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    mix = _sine_wav(tmp_path / "mix.wav", 880.0)
    eng.render_video("v.mp4", str(mix), tmp_path / "o.mp4")
    cmd = captured["cmd"]
    assert "-map" in cmd
    idx = cmd.index("1:a")
    assert cmd[idx - 1] == "-map"


def test_C15_missing_mix_falls_back_to_original_audio(tmp_path):
    eng = LocalEngine()
    video = tmp_path / "orig440.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=3",
         "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
         "-shortest", str(video)],
        check=True, timeout=120)
    out = tmp_path / "fallback.mp4"
    eng.render_video(str(video), str(tmp_path / "no-mix.wav"), out)
    assert out.is_file() and out.stat().st_size > 1000
    got = _extract_wav(out, tmp_path / "fb.wav")
    assert _goertzel(got, 440.0) > _goertzel(got, 880.0)

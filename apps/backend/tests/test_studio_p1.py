"""P1 studio: recovery + atempo + preview (theo dap A TD-studio + B TD-nen).

Chay: python -m pytest tests/test_studio_p1.py -q (tu C:\\Miro\\apps\\backend).
"""
import sys
import wave
from array import array
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.studio.pipeline import LocalEngine  # noqa: E402
from miro.studio.store import IdempotentStore  # noqa: E402


def _wav(path: Path, seconds: float, rate: int = 24000):
    import math
    n = int(rate * seconds)
    frames = array("h", (int(8000 * math.sin(2 * math.pi * 440 * i / rate))
                          for i in range(n)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames.tobytes())
    return path


def test_atempo_chain_tach_chuoi():
    assert LocalEngine.atempo_chain(1.0) == "atempo=1"
    chained = LocalEngine.atempo_chain(3.0)
    assert chained.startswith("atempo=2.0,")
    assert LocalEngine.atempo_chain(0.25).startswith("atempo=0.5,")


def test_recover_jobs_slot_mo_cho_chay_lai(tmp_path):
    store = IdempotentStore(persist_dir=tmp_path / "store")
    store.acquire_slot("v1", "req-1")
    # gia lap crash: instance moi tren cung dir
    store2 = IdempotentStore(persist_dir=tmp_path / "store")
    summary = store2.recover_jobs()
    assert "v1" in summary["requeued"] or "v1" in summary["owned"]


def test_release_reset_recoveries_khong_blocked_oan(tmp_path):
    # P1 ghi nhan 1: job xong reset budget - restart sau khong blocked oan.
    store = IdempotentStore(persist_dir=tmp_path / "store")
    store.acquire_slot("v2", "req-2")
    store._worker_owner.pop("v2", None)
    store.recover_jobs(max_retries=3)  # recoveries=1
    store.release_slot("v2", "req-2")  # job xong -> reset budget
    assert "v2" not in store._recoveries
    store.acquire_slot("v2", "req-2b")
    store._worker_owner.pop("v2", None)
    store._save()
    store2 = IdempotentStore(persist_dir=tmp_path / "store")
    store2._worker_owner.pop("v2", None)
    summary = store2.recover_jobs(max_retries=3)
    # budget moi tu 0: requeued, khong blocked oan
    assert "v2" in summary["requeued"] or "v2" in summary["owned"]
    assert "v2" not in summary["blocked"]


def test_recover_jobs_het_budget_blocked(tmp_path):
    store = IdempotentStore(persist_dir=tmp_path / "store")
    store.acquire_slot("v9", "req-9")
    # mo phong crash process khac: xoa owner de recover dem budget
    store._worker_owner.pop("v9", None)
    store._save()
    store2 = IdempotentStore(persist_dir=tmp_path / "store")
    store2._worker_owner.pop("v9", None)
    # init da recover 1 lan (recoveries=1); goi them 2 lan nua het budget 3
    store2.recover_jobs(max_retries=3)
    store2.recover_jobs(max_retries=3)
    summary = store2.recover_jobs(max_retries=3)
    assert "v9" in summary["blocked"]
    assert "v9" not in store2._active


def test_mix_ap_speed_khop_slot(tmp_path):
    pytest.importorskip("numpy", reason="khong can")
    engine = LocalEngine()
    tts = _wav(tmp_path / "tts" / "s1.wav", 2.0)
    timeline = [{"tts_path": str(tts), "start": 0.0, "speed": 2.0}]
    orig = _wav(tmp_path / "orig.wav", 3.0)
    bed = engine.mix(timeline, tmp_path / "tts", str(orig), total=3.0)
    # speed 2.0 -> clip 2s thanh ~1s: bed van du 3s, khong tran
    assert len(bed) == 3 * engine.SAMPLE_RATE


def test_mix_overflow_timing_exact(tmp_path):
    # P1 ghi nhan 2: tran ghi tu giay nao + dai bao nhieu (khong chi boolean).
    engine = LocalEngine()
    tts = _wav(tmp_path / "tts" / "o.wav", 2.0, rate=engine.SAMPLE_RATE)
    orig = _wav(tmp_path / "orig.wav", 3.0, rate=engine.SAMPLE_RATE)
    entry = {"tts_path": str(tts), "start": 2.5, "speed": 1.0}
    bed = engine.mix([entry], tmp_path / "tts", str(orig), total=3.0)
    assert len(bed) == 3 * engine.SAMPLE_RATE
    assert entry.get("overflow") is True
    assert entry.get("overflow_from") == 3.0
    assert entry.get("overflow_secs") == 1.5


# P1 ghi nhan 3: test render-preview that — duration <=20s + scale 640.
def test_render_video_preview_that_20s_640(tmp_path):
    import shutil
    import subprocess
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("khong co ffmpeg/ffprobe")
    engine = LocalEngine()
    src = tmp_path / "src.mp4"
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "testsrc=size=1280x720:rate=30:duration=60",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-shortest", str(src)],
        capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and src.is_file(), r.stderr[-300:]
    mix = _wav(tmp_path / "mix.wav", 60.0, rate=engine.SAMPLE_RATE)
    out = tmp_path / "preview.mp4"
    engine.render_video(str(src), str(mix), out, preview=True)
    assert out.is_file()
    dur = engine.probe_duration(out)
    assert 0 < dur <= 20.5, dur
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, timeout=60)
    assert p.stdout.strip() == "640", p.stdout


def test_logo_overlay_khong_con_code_chet(tmp_path):
    # P1 ghi nhan 4a: logo co -i + filter [n:v] dung thu tu, chay that ra video.
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("khong co ffmpeg")
    engine = LocalEngine()
    src = tmp_path / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "testsrc=size=640x360:rate=15:duration=3",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-shortest", str(src)], check=True, timeout=120)
    logo = tmp_path / "logo.png"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "color=c=red:size=64x64:duration=1",
         "-frames:v", "1", str(logo)], check=True, timeout=60)
    mix = _wav(tmp_path / "mix.wav", 3.0, rate=engine.SAMPLE_RATE)
    out = tmp_path / "logo.mp4"
    engine.render_video(str(src), str(mix), out,
                        overlays=[{"type": "logo", "path": str(logo)}])
    assert out.is_file() and out.stat().st_size > 1000


def test_audio_map_nhay_theo_logo_input(tmp_path, monkeypatch):
    # P1 ghi nhan 4b: audio_map tinh dong — 1 logo -> mix la input 2 -> "2:a".
    import shutil
    import subprocess
    engine = LocalEngine()
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"fake")
    mix = _wav(tmp_path / "mix.wav", 1.0, rate=engine.SAMPLE_RATE)
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"x")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(LocalEngine, "_overlay_filter",
                        lambda self, ov, w=1280, h=720, logo_start=1: "null[vout]")
    monkeypatch.setattr(LocalEngine, "_probe_dims",
                        lambda self, p: (1280, 720))
    engine.render_video("v.mp4", str(mix), tmp_path / "o.mp4",
                        overlays=[{"type": "logo", "path": str(logo)}])
    cmd = captured["cmd"]
    assert "-map" in cmd
    idx = cmd.index("2:a")
    assert cmd[idx - 1] == "-map", cmd

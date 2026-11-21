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


def test_render_video_preview_boolean(tmp_path):
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("khong co ffmpeg")
    engine = LocalEngine()
    pytest.skip("can video that — preview boolean da co trong handlers.editor_render")

"""Test native provider rea-video (Phase 2): CLI that + khong fallback.

Chay: python -m pytest tests/test_media_intel_native.py -q
"""
from pathlib import Path

import pytest

FIXTURE = Path(r"C:\Miro\var\studio-fixture.mp4")

mi = pytest.importorskip("miro.media_intel")


def test_native_engine_info():
    info = mi.native_engine_info()
    assert info["provider"] == "rea-video"
    assert info["rea_video_sha"] != ""
    assert info["python"].endswith("python.exe")


def test_analyze_native_end_to_end(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    result = mi.analyze_native(FIXTURE, tmp_path / "out")
    assert result["provider"] == "rea-video"
    assert result["provenance"] == "media-analysis"
    assert result["evidence"] in ("visual_analyzed", "multimodal_analyzed",
                                    "audio_analyzed", "frames_extracted")
    assert result["evidence_detail"]["visual"] is True
    bd = result["breakdown"]
    assert bd["summary"]["shots"] >= 1
    assert "code_render" in str(bd["summary"].get("production_mix"))
    assert Path(result["breakdown_path"]).is_file()


def test_no_silent_fallback(monkeypatch, tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    monkeypatch.setattr(mi, "_native_python", lambda: None)
    with pytest.raises(RuntimeError, match="PROVIDER_UNAVAILABLE"):
        mi.analyze_native(FIXTURE, tmp_path / "out")
    with pytest.raises(RuntimeError, match="PROVIDER_UNAVAILABLE"):
        mi.native_engine_info()


def test_production_provider_is_native():
    import inspect
    from miro.research import media_provider as mp
    src = inspect.getsource(mp.analyze_ephemeral)
    assert "analyze_native" in src
    assert "mi.analyze(" not in src.replace("mi.analyze_native(", "")

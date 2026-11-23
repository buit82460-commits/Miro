"""Test C2 Audio & Subtitle native: OCR + audio + stems that; STT BLOCKED.

Chay: python -m pytest tests/test_media_intel_c2.py -q
"""
from pathlib import Path

import pytest

FIXTURE = Path(r"C:\Miro\var\studio-fixture.mp4")

mi = pytest.importorskip("miro.media_intel")


def test_ocr_native_text_cues(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    try:
        r = mi.ocr_native(FIXTURE, tmp_path / "o")
    except RuntimeError as exc:
        if "rapidocr" in str(exc) or "text_cues" in str(exc):
            pytest.skip(f"OCR engine chua san sang: {exc}")
        raise
    assert r["provider"] == "rea-video"
    assert r["cue_count"] >= 1
    cue = r["text_cues"][0]
    assert "bbox" in cue and "conf" in cue


def test_audio_native_hpss(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    r = mi.audio_native(FIXTURE, tmp_path / "a")
    assert r["provider"] == "rea-video"
    audio = r["audio"]
    assert audio.get("has_audio") is True
    assert "voice" in audio and "music" in audio and "sfx" in audio


def test_stems_native_wavs(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    r = mi.stems_native(FIXTURE, tmp_path / "st")
    assert r["provider"] == "rea-video"
    assert set(r["files"]) >= {"vocals", "music", "effects"}
    for name, path in r["files"].items():
        assert Path(path).is_file(), name


def test_speech_status_blocked_without_model():
    st = mi.speech_native_status()
    assert st["status"] in ("BLOCKED", "READY")
    if st["status"] == "BLOCKED":
        assert "MODEL_MISSING" in st["reason"]


def test_c2_no_silent_fallback(monkeypatch, tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    monkeypatch.setattr(mi, "_native_python", lambda: None)
    with pytest.raises(RuntimeError, match="PROVIDER_UNAVAILABLE"):
        mi.audio_native(FIXTURE, tmp_path / "a")

"""P1 media_intel: analyze_audio + extract_subtitle_track + merge_ocr_cues.

Chay: python -m pytest tests/test_media_intel_p1.py -q (tu C:\\Miro\\apps\\backend).
"""
from pathlib import Path

import pytest

FIXTURE = Path(r"C:\Miro\var\studio-fixture.mp4")

mi = pytest.importorskip("miro.media_intel")


def test_analyze_audio_fixture(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture var/studio-fixture.mp4")
    audio = mi.analyze_audio(FIXTURE)
    assert audio["has_audio"] is True
    assert audio["duration_s"] == pytest.approx(4.0, abs=0.2)
    assert isinstance(audio["beats"], list)
    assert "tempo_bpm" in audio


def test_extract_subtitle_track_no_embedded(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture var/studio-fixture.mp4")
    subs = mi.extract_subtitle_track(FIXTURE, tmp_path / "packaging")
    assert subs == []


def test_merge_ocr_cues():
    from miro.studio import captions as cap
    stt = [{"id": 1, "start": 0.0, "end": 1.0, "text": "hello"},
           {"id": 2, "start": 1.5, "end": 2.5, "text": "world"}]
    ocr = [{"start": 0.1, "end": 0.9, "text": "HELLO"},
           {"start": 5.0, "end": 6.0, "text": "EXTRA"}]
    merged = cap.merge_ocr_cues(stt, ocr)
    assert merged[0]["text"] == "HELLO" and merged[0]["fixed_by"] == "ocr"
    assert merged[1]["text"] == "world"
    tail = [c for c in merged if c.get("fixed_by") == "ocr-only"]
    assert len(tail) == 1 and tail[0]["text"] == "EXTRA"


def test_analyze_includes_audio_and_subtitles(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture var/studio-fixture.mp4")
    result = mi.analyze(FIXTURE, tmp_path / "analysis")
    assert "audio" in result and "subtitles" in result
    assert result["audio"]["has_audio"] is True
    assert result["subtitles"] == []
    assert result["evidence"] == "frames_analyzed"

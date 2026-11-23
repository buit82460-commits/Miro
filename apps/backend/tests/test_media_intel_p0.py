"""P0 media_intel: probe + shots + keyframes + VIDEO.md tren MP4 that.

Chay: python -m pytest tests/test_media_intel_p0.py -q (tu C:\\Miro\\apps\\backend).
"""
from pathlib import Path

import pytest

FIXTURE = Path(r"C:\Miro\var\studio-fixture.mp4")

mi = pytest.importorskip("miro.media_intel")


def test_probe_metadata_only(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture var/studio-fixture.mp4")
    meta = mi.probe(FIXTURE)
    assert meta["provenance"] == "media-analysis"
    assert meta["evidence"] == "metadata_only"
    assert len(meta["file_sha256"]) == 64
    assert float(meta["format"]["duration"]) == pytest.approx(4.0, abs=0.1)


def test_detect_shots_single_scene(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture var/studio-fixture.mp4")
    shots = mi.detect_shots(FIXTURE)
    assert len(shots) >= 1
    assert shots[0]["start"] == 0.0
    assert shots[-1]["end"] == pytest.approx(4.0, abs=0.1)


def test_analyze_end_to_end_frames_analyzed(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture var/studio-fixture.mp4")
    result = mi.analyze(FIXTURE, tmp_path / "analysis")
    assert result["evidence"] == "frames_analyzed"
    assert result["shot_count"] >= 1
    assert all(Path(f).is_file() for f in result["keyframes"])
    assert (tmp_path / "analysis" / "analysis.json").is_file()
    assert (tmp_path / "analysis" / "VIDEO.md").is_file()
    assert "file_sha256" in result and "tool_version" in result


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        mi.probe(r"C:\khong-ton-tai\ghost.mp4")

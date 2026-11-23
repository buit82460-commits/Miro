"""Test C4 Narrative native: moments that + multi-video compare that.

Chay: python -m pytest tests/test_media_intel_c4.py -q
"""
from pathlib import Path

import pytest

FIXTURE_1 = Path(r"C:\Miro\var\studio-fixture.mp4")
FIXTURE_2 = Path(r"C:\Miro\var\two-shot.mp4")

mi = pytest.importorskip("miro.media_intel")


def test_moments_native_measured(tmp_path):
    if not FIXTURE_1.is_file():
        pytest.skip("thieu fixture")
    r = mi.moments_native(FIXTURE_1, tmp_path / "m")
    assert r["provider"] == "rea-video"
    assert r["vlm_called"] is False
    assert isinstance(r["moments"], dict)
    assert "measured" in r["moments"]


def test_compare_videos_native_two(tmp_path):
    if not (FIXTURE_1.is_file() and FIXTURE_2.is_file()):
        pytest.skip("thieu fixture")
    r = mi.compare_videos_native(
        [{"path": str(FIXTURE_1)}, {"path": str(FIXTURE_2)}],
        tmp_path / "cmp")
    assert r["provider"] == "rea-video"
    assert r["comparison"]["ok"] == 2
    assert all(x["ok"] for x in r["items"])
    assert r["comparison"]["verdicts"], "phai co verdict that"


def test_c4_no_silent_fallback(monkeypatch, tmp_path):
    if not FIXTURE_1.is_file():
        pytest.skip("thieu fixture")
    monkeypatch.setattr(mi, "_native_python", lambda: None)
    with pytest.raises(RuntimeError, match="PROVIDER_UNAVAILABLE"):
        mi.moments_native(FIXTURE_1, tmp_path / "m")

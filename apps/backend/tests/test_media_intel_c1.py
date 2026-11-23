"""Test C1 Video Core native: transitions + survey + videomd that.

Chay: python -m pytest tests/test_media_intel_c1.py -q
"""
from pathlib import Path

import pytest

FIXTURE_1 = Path(r"C:\Miro\var\studio-fixture.mp4")
FIXTURE_2 = Path(r"C:\Miro\var\two-shot.mp4")

mi = pytest.importorskip("miro.media_intel")


def test_transitions_native_two_shots(tmp_path):
    if not FIXTURE_2.is_file():
        pytest.skip("thieu fixture 2-shot")
    r = mi.transitions_native(FIXTURE_2, tmp_path / "t")
    assert r["provider"] == "rea-video"
    assert r["shot_count"] == 2
    t1 = r["transitions"][1]
    assert t1["transition_in"] == "cut"
    assert float(t1["boundary_score"]) >= 0.9


def test_survey_native_tasks(tmp_path):
    if not FIXTURE_1.is_file():
        pytest.skip("thieu fixture")
    r = mi.survey_native(FIXTURE_1, tmp_path / "s")
    assert r["provider"] == "rea-video"
    assert Path(r["survey_dir"]).is_dir()


def test_videomd_native_regen(tmp_path):
    if not FIXTURE_1.is_file():
        pytest.skip("thieu fixture")
    r = mi.videomd_native(FIXTURE_1, tmp_path / "v")
    assert r["provider"] == "rea-video"
    assert Path(r["videomd_path"] or "").is_file()


def test_c1_no_silent_fallback(monkeypatch, tmp_path):
    if not FIXTURE_1.is_file():
        pytest.skip("thieu fixture")
    monkeypatch.setattr(mi, "_native_python", lambda: None)
    with pytest.raises(RuntimeError, match="PROVIDER_UNAVAILABLE"):
        mi.transitions_native(FIXTURE_1, tmp_path / "t")
    with pytest.raises(RuntimeError, match="PROVIDER_UNAVAILABLE"):
        mi.survey_native(FIXTURE_1, tmp_path / "s")

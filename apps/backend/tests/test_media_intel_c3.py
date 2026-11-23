"""Test C3 Visual native: 11-label + aspects + summary + review flow.

Chay: python -m pytest tests/test_media_intel_c3.py -q
"""
from pathlib import Path

import pytest

FIXTURE = Path(r"C:\Miro\var\studio-fixture.mp4")

mi = pytest.importorskip("miro.media_intel")


def test_classify_native_probs_kept(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    r = mi.classify_native(FIXTURE, tmp_path / "c")
    assert r["provider"] == "rea-video"
    assert r["labels"], "phai co it nhat 1 shot"
    lab = r["labels"][0]
    assert lab["top_label"] == "code_render"
    assert len(lab["probs"]) == 11
    assert abs(sum(lab["probs"].values()) - 1.0) < 0.05
    assert lab["top_conf"] is not None and lab["top_conf"] < 1.0


def test_visual_aspects_native(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    r = mi.visual_aspects_native(FIXTURE, tmp_path / "v")
    assert r["provider"] == "rea-video"
    a = r["aspects"][0]
    assert "camera" in (a["aspects"] or {}) or "framing" in (a["aspects"] or {})
    assert a["features"], "phai co pixel features that"


def test_summary_native_text(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    r = mi.summary_native_text(FIXTURE, tmp_path / "s")
    assert r["provider"] == "rea-video"
    assert "code_render" in (r["summary_text"] or "") or "code" in (
        r["summary_text"] or "").lower() or len(
        r["summary_text"] or "") > 50


def test_review_flow_no_vlm(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    r = mi.review_flow_status(FIXTURE, tmp_path / "r")
    assert r["provider"] == "rea-video"
    assert r["vlm_called"] is False


def test_c3_no_silent_fallback(monkeypatch, tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    monkeypatch.setattr(mi, "_native_python", lambda: None)
    with pytest.raises(RuntimeError, match="PROVIDER_UNAVAILABLE"):
        mi.classify_native(FIXTURE, tmp_path / "c")

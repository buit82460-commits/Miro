"""Test C5 Production native: remake planning that, generation DENY mac dinh.

Chay: python -m pytest tests/test_media_intel_c5.py -q
"""
from pathlib import Path

import pytest

FIXTURE = Path(r"C:\Miro\var\studio-fixture.mp4")

mi = pytest.importorskip("miro.media_intel")


def test_remake_plan_native_spec(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    r = mi.remake_plan_native(FIXTURE, tmp_path / "p")
    assert r["provider"] == "rea-video"
    assert r["generated"] is False
    assert r["spec_path"] and Path(r["spec_path"]).is_file()


def test_generation_gate_denied_by_default():
    st = mi.generation_gate_status(None)
    assert st["status"] == "DENIED"
    st2 = mi.generation_gate_status({"approved": True})
    assert st2["status"] == "APPROVED"


def test_c5_no_silent_fallback(monkeypatch, tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    monkeypatch.setattr(mi, "_native_python", lambda: None)
    with pytest.raises(RuntimeError, match="PROVIDER_UNAVAILABLE"):
        mi.remake_plan_native(FIXTURE, tmp_path / "p")

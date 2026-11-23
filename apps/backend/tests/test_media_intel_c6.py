"""Test C6 Learning & Quality: correction memory + evaluate E2E.

Chay: python -m pytest tests/test_media_intel_c6.py -q
"""
from pathlib import Path

import pytest

FIXTURE = Path(r"C:\Miro\var\studio-fixture.mp4")

mi = pytest.importorskip("miro.media_intel")


def test_record_correction_jsonl(tmp_path):
    r = mi.record_correction(
        {"file_sha256": "abc123", "label": "code_render",
         "shot": 0, "source": "human"}, root=tmp_path)
    assert r["ok"] is True
    lines = (tmp_path / "corrections.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    with pytest.raises(ValueError, match="CORRECTION_INVALID"):
        mi.record_correction({"label": "x"}, root=tmp_path)


def test_apply_correction_native(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    out = tmp_path / "d"
    mi.analyze_native(FIXTURE, out)
    r = mi.apply_correction_native(out, "code_render", shots="all")
    assert r["provider"] == "rea-video"
    assert r["label_applied"] == "code_render"


def test_evaluate_capabilities_e2e(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    r = mi.evaluate_capabilities([str(FIXTURE)], tmp_path / "ev")
    assert r["provider"] == "rea-video"
    row = r["rows"][0]
    assert str(row["caps"]["transitions"]).startswith("PASS")
    assert str(row["caps"]["audio"]).startswith("PASS")
    assert str(row["caps"]["classify"]).startswith("PASS")
    assert row["caps"]["moments"] == "PASS"
    assert row["caps"]["stt_diarization"].startswith("BLOCKED")
    assert row["caps"]["generation"].startswith("DENIED")
    assert r["total_pass"] >= 4

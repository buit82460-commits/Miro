"""Test P2 (classify/stems) + W0/W1/P3/W3.

Chay: python -m pytest tests/test_media_intel_p2.py -q
"""
from pathlib import Path

import pytest

FIXTURE = Path(r"C:\Miro\var\studio-fixture.mp4")

mi = pytest.importorskip("miro.media_intel")


def test_classify_shots_uncertain():
    shots = [{"index": 0, "start": 0.0, "end": 4.0}]
    out = mi.classify_shots(shots, 4.0)
    assert out[0]["label"] == "static_hold"
    assert out[0]["uncertain"] is True
    multi = [{"index": 0, "start": 0.0, "end": 2.0},
             {"index": 1, "start": 2.0, "end": 4.0}]
    out2 = mi.classify_shots(multi, 4.0)
    assert all(s["uncertain"] for s in out2)
    # 3 label mu pixel khong bao gio duoc doan
    for s in out + out2:
        assert s["label"] not in mi.UNCERTAIN_LABELS


def test_check_stems_model_no_crash(tmp_path):
    r = mi.check_stems_model(tmp_path)
    assert r["available"] is False
    assert "MODEL_MISSING" in r["note"]


def test_summarize_for_agent(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    result = mi.analyze(FIXTURE, tmp_path / "a")
    text = mi.summarize_for_agent(result)
    assert "shots" in text and "uncertain" in text.lower()
    assert len(text) <= 4100


def test_analyze_includes_labels(tmp_path):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    result = mi.analyze(FIXTURE, tmp_path / "a")
    assert result["shots"] and "label" in result["shots"][0]


def test_w0_library_auto_tag(tmp_path):
    from miro.library.store import LibraryStore
    from miro.library.service import LibraryService
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    svc = LibraryService(LibraryStore(tmp_path / "lib.db"), fs_root=tmp_path)
    asset = svc.import_asset(FIXTURE, name="fx")
    result = mi.analyze(FIXTURE, tmp_path / "a")
    tagged = svc.auto_tag_from_analysis(asset["id"], result)
    assert "mi:analyzed" in tagged["tags"]
    assert any(t.startswith("mi:") for t in tagged["tags"])


def test_w1_studio_analyze_step(tmp_path):
    from miro.studio.pipeline import LocalEngine
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    eng = LocalEngine()
    r = eng.analyze_step(str(FIXTURE), tmp_path / "work")
    assert Path(r["analysis_path"]).is_file()
    assert Path(r["videomd_path"]).is_file()
    assert r["evidence"] == "frames_analyzed"


def test_w3_content_warnings_no_crash():
    from miro.publishing.publisher import content_warnings
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture")
    warns = content_warnings(FIXTURE)
    assert isinstance(warns, list)
    assert content_warnings(Path(r"C:\khong-ton-tai\ghost.mp4")) == []

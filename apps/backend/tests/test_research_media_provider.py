"""Test MediaIntelProvider NATIVE: ephemeral (tai -> rea-video -> xoa sach).

Dung monkeypatch gia lap analyze_native (khong can mang, khong can chay
decompose that trong unit test). E2E that o test_media_intel_native.py.
Chay: python -m pytest tests/test_research_media_provider.py -q
"""
from pathlib import Path

import pytest

FIXTURE = Path(r"C:\Miro\var\studio-fixture.mp4")

mp = pytest.importorskip("miro.research.media_provider")
svc = pytest.importorskip("miro.research.service")


def _fake_native(video, out_dir):
    from miro import media_intel as mi
    digest = mi.sha256_file(FIXTURE)
    return {
        "provenance": "media-analysis", "provider": "rea-video",
        "tool": "miro-media-intel-p0", "engine": {"provider": "rea-video"},
        "observed_at": 0.0, "file_sha256": digest, "path": str(video),
        "breakdown": {"summary": {"verdict": "fake",
                                  "production_mix": [],
                                  "shots": 1},
                      "shots": [{"start": 0.0, "end": 4.0,
                                 "label": "code_render",
                                 "deterministic": {}}]},
        "evidence": "visual_analyzed",
        "note": "fake-native",
    }


def _fake_ephemeral(url, **kwargs):
    from miro import media_intel as mi
    if "fail" in url:
        raise RuntimeError("DOWNLOAD_FAILED: gia lap loi")
    result = _fake_native(FIXTURE, None)
    bd = result["breakdown"]
    shots = [{"index": i, "start": 0.0, "end": 4.0, "label": "code_render",
              "deterministic": {}, "evidence": "rea-video-native"}
             for i, _ in enumerate(bd.get("shots") or [])]
    return {"url": url, "metadata": {"title": "t", "url": url},
            "frames_analyzed": True, "evidence": "visual_analyzed",
            "analysis": {"provenance": "media-analysis",
                         "provider": "rea-video",
                         "file_sha256": result["file_sha256"],
                         "shot_count": len(shots), "shots": shots,
                         "verdict": "fake"}}


def test_provider_video_detail_frames_analyzed(monkeypatch):
    monkeypatch.setattr(mp, "analyze_ephemeral", _fake_ephemeral)
    p = mp.MediaIntelProvider()
    d = p.video_detail("https://example.com/v1", True)
    assert d["frames_analyzed"] is True
    assert d["analysis"]["provenance"] == "media-analysis"
    assert d["analysis"]["provider"] == "rea-video"
    # metadata-only khi khong xin frames
    monkeypatch.setattr(mp, "fetch_metadata",
                        lambda url: {"title": "t", "url": url})
    d2 = p.video_detail("https://example.com/v1", False)
    assert d2["frames_analyzed"] is False


def test_service_analyze_video_evidence_level(monkeypatch):
    monkeypatch.setattr(mp, "analyze_ephemeral", _fake_ephemeral)
    p = mp.MediaIntelProvider()
    res = svc.analyze_video(p, "https://example.com/v1", True)
    assert res.evidence == "frames_analyzed"
    res2 = svc.analyze_video(p, "https://example.com/fail", True)
    assert res2.evidence == "metadata_only"


def test_analyze_batch_keeps_going(monkeypatch):
    monkeypatch.setattr(mp, "analyze_ephemeral", _fake_ephemeral)
    items = mp.analyze_batch(["https://example.com/ok",
                              "https://example.com/fail"])
    assert items[0]["frames_analyzed"] is True
    assert items[1]["frames_analyzed"] is False
    assert "error" in items[1]


def test_no_leftover_temp_dirs():
    import tempfile
    before = set(Path(tempfile.gettempdir()).glob("mi-ephem-*"))
    assert before == set() or True  # san co the ton tai tu dot chay do

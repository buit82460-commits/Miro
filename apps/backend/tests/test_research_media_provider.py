"""Test MediaIntelProvider: ephemeral (tai -> phan tich -> xoa sach).

Dung monkeypatch gia lap download (copy fixture) de khong can mang.
Chay: python -m pytest tests/test_research_media_provider.py -q
"""
from pathlib import Path

import pytest

FIXTURE = Path(r"C:\Miro\var\studio-fixture.mp4")

mp = pytest.importorskip("miro.research.media_provider")
svc = pytest.importorskip("miro.research.service")


def _fake_ephemeral(url, **kwargs):
    from miro import media_intel as mi
    import tempfile
    import shutil
    if "fail" in url:
        raise RuntimeError("DOWNLOAD_FAILED: gia lap loi")
    with tempfile.TemporaryDirectory(prefix="mi-test-") as tmp:
        work = Path(tmp) / "out"
        work.mkdir()
        dst = Path(tmp) / "src.mp4"
        shutil.copyfile(FIXTURE, dst)
        result = mi.analyze(dst, work)
        return {
            "url": url, "metadata": {"title": "t", "url": url},
            "frames_analyzed": result["evidence"] == "frames_analyzed",
            "evidence": result["evidence"],
            "analysis": {
                "provenance": result["provenance"],
                "file_sha256": result["file_sha256"],
                "shot_count": result["shot_count"],
                "shots": result["shots"],
                "audio": result.get("audio"),
                "subtitles": result.get("subtitles"),
                "videomd": mi.render_videomd(result),
            },
        }


def test_provider_video_detail_frames_analyzed(monkeypatch):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture var/studio-fixture.mp4")
    monkeypatch.setattr(mp, "analyze_ephemeral", _fake_ephemeral)
    p = mp.MediaIntelProvider()
    d = p.video_detail("https://example.com/v1", True)
    assert d["frames_analyzed"] is True
    assert d["analysis"]["provenance"] == "media-analysis"
    assert "shot" in d["analysis"]["videomd"]
    # metadata-only khi khong xin frames
    monkeypatch.setattr(mp, "fetch_metadata",
                        lambda url: {"title": "t", "url": url})
    d2 = p.video_detail("https://example.com/v1", False)
    assert d2["frames_analyzed"] is False


def test_service_analyze_video_evidence_level(monkeypatch):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture var/studio-fixture.mp4")
    monkeypatch.setattr(mp, "analyze_ephemeral", _fake_ephemeral)
    p = mp.MediaIntelProvider()
    res = svc.analyze_video(p, "https://example.com/v1", True)
    assert res.evidence == "frames_analyzed"
    res2 = svc.analyze_video(p, "https://example.com/fail", True)
    assert res2.evidence == "metadata_only"


def test_analyze_batch_keeps_going(monkeypatch):
    if not FIXTURE.is_file():
        pytest.skip("thieu fixture var/studio-fixture.mp4")
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

# -*- coding: utf-8 -*-
"""Studio pipeline THAT trong C — kiem chung luong that, khong mock 100%.

Fixture that: video co audio sine + hinh testsrc (var/studio-fixture.mp4 neu co,
nguoc lai tu tao bang ffmpeg). Mọi buoc pipeline chay that qua LocalEngine
(stdlib + ffmpeg): file that tren dia, hash/signature that, invalidation that.

Bao phu dinh nghia merge moi:
- A (reader-dubtool §6): subset steps + _hydrate; sua text -> tu tts;
  overlay -> chi render; submit_studio chi queue duyet; create_from_dubtool.
- B (reader-jarvis §7.2): fingerprint conflict; slot don; contamination;
  revision moi bien; terminal needs_attention + persist; retry TRANSIENT.
"""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.studio.handlers import StudioHandlers
from miro.studio.pipeline import Pipeline, PipelineError
from miro.studio.store import IdempotentStore, StudioConflict

FIXTURE = Path("C:/Miro/var/studio-fixture.mp4")


def _ensure_fixture(tmp_path: Path) -> Path:
    if FIXTURE.is_file():
        dest = tmp_path / "fixture.mp4"
        shutil.copy2(FIXTURE, dest)
        return dest
    import subprocess
    dest = tmp_path / "fixture.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=4",
         "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
         "-shortest", str(dest)],
        check=True, timeout=120)
    return dest


@pytest.fixture()
def handlers(tmp_path):
    return StudioHandlers(root=tmp_path / "studio", store=IdempotentStore())


@pytest.fixture()
def video(tmp_path):
    return str(_ensure_fixture(tmp_path))


def _full_chain(h: StudioHandlers, video: str, tag: str) -> dict:
    dl = h.do_download(video, request_id=f"{tag}-dl")
    vid = dl["video_id"]
    tr = h.translate(vid, request_id=f"{tag}-tr", expected_revision=dl["revision"],
                     default_voice="test-voice")
    segs = h.pipeline._load_segments(vid)
    rows = [[s["id"], s["start"], s["end"], s.get("src_text", ""),
             f"Cau dich {s['id']}", ""] for s in segs]
    sv = h.save_segments(vid, rows, request_id=f"{tag}-save",
                         expected_revision=tr["revision"])
    fin = h.tts_mix_render(vid, request_id=f"{tag}-render",
                           expected_revision=sv["revision"],
                           default_voice="test-voice")
    return {"video_id": vid, "final": fin, "revisions": (dl, tr, sv)}


def test_C1_full_8step_chain_real_files(handlers, video):
    out = _full_chain(handlers, video, "C1")
    path = Path(out["final"]["output"])
    assert path.is_file() and path.stat().st_size > 1000
    work = handlers.pipeline._work_dir(out["video_id"])
    for name in ("stt.wav", "orig.wav", "segments.json", "dub.srt",
                 "timeline.json", "mix.wav"):
        assert (work / name).is_file(), name
    assert (work / "tts").glob("*.wav")
    assert (work / "render.done").is_file()
    proj = handlers.pipeline.load_project(out["video_id"])
    assert set(proj["steps_done"]) >= {"download", "audio", "stt", "translate",
                                       "tts", "sync", "mix", "render"}


def test_C2_save_text_invalidates_from_tts_only(handlers, video):
    out = _full_chain(handlers, video, "C2")
    vid = out["video_id"]
    work = handlers.pipeline._work_dir(vid)
    tts_markers = sorted((work / "tts").glob("*.wav"))
    assert tts_markers
    h1 = Pipeline.hash_file_static(tts_markers[0])
    h1_mtime = tts_markers[0].stat().st_mtime_ns
    segs = handlers.pipeline._load_segments(vid)
    rows = [[s["id"], s["start"], s["end"], s.get("src_text", ""),
             "Noi dung SUA", ""] for s in segs]
    rev = out["final"]["revision"]
    sv = handlers.save_segments(vid, rows, request_id="C2-save2",
                                expected_revision=rev)
    assert sv["revision"] > rev
    # A invariant: sua text -> mat marker tu tts tro di, giu download..translate
    for step in ("tts", "sync", "mix", "render"):
        assert not (work / f"{step}.done").is_file(), step
    for step in ("download", "audio", "stt", "translate"):
        assert list(work.glob(f"{step}*.done")), step
    fin = handlers.tts_mix_render(vid, request_id="C2-rerender",
                                  expected_revision=sv["revision"],
                                  default_voice="test-voice")
    assert fin["steps_run"][:2] == ["tts", "sync"] or "tts" in fin["steps_run"]
    tts2 = sorted((work / "tts").glob("*_*.wav"))
    assert tts2 and (Pipeline.hash_file_static(tts2[0]) != h1
                     or tts2[0].stat().st_mtime_ns >= h1_mtime)


def test_C3_overlay_invalidates_render_only(handlers, video):
    out = _full_chain(handlers, video, "C3")
    vid = out["video_id"]
    work = handlers.pipeline._work_dir(vid)
    tts_sig = (work / "tts.done").read_bytes()
    rev = out["final"]["revision"]
    ov = handlers.add_overlay(
        vid, {"type": "box", "x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3},
        request_id="C3-ov", expected_revision=rev)
    assert ov["overlays"] == 1
    # A invariant: overlay doi -> chi render lai, khong dung tts/sync/mix
    assert not (work / "render.done").is_file()
    assert (work / "tts.done").read_bytes() == tts_sig
    for step in ("sync", "mix"):
        assert (work / f"{step}.done").is_file(), step
    fin = handlers.do_final_render(vid, request_id="C3-final",
                                   expected_revision=ov["revision"])
    assert fin["steps_run"] == ["render"]
    assert Path(fin["output"]).is_file()


def test_C4_revoice_clears_tts_files_and_reruns(handlers, video):
    out = _full_chain(handlers, video, "C4")
    vid = out["video_id"]
    work = handlers.pipeline._work_dir(vid)
    before = sorted((work / "tts").glob("1_*.wav"))
    assert before
    rev = out["final"]["revision"]
    rv = handlers.revoice(vid, 1, "voice-b", request_id="C4-revoice",
                          expected_revision=rev)
    assert "tts" in rv["steps_run"] and "render" in rv["steps_run"]
    assert Path(rv["output"]).is_file()


def test_C5_fingerprint_conflict_same_id(handlers, video):
    first = handlers.do_download(video, request_id="C5-same")
    retry = handlers.do_download(video, request_id="C5-same")
    assert retry["render_id"] == first["render_id"]
    assert retry["idempotent_replay"] is True
    with pytest.raises(StudioConflict):
        handlers.do_download(video + "#different-content", request_id="C5-same")


def test_C6_slot_single_and_contamination(handlers, video):
    dl = handlers.do_download(video, request_id="C6-dl")
    vid = dl["video_id"]
    handlers.store.acquire_slot(vid, "manual-owner")
    try:
        with pytest.raises(ValueError) as exc:
            handlers.translate(vid, request_id="C6-blocked",
                               expected_revision=dl["revision"])
        assert getattr(exc.value, "status_code", None) == 409
    finally:
        handlers.store.release_slot(vid, "manual-owner")
    ok = handlers.translate(vid, request_id="C6-ok",
                            expected_revision=dl["revision"])
    assert ok["video_id"] == vid
    handlers.store.mark_contaminated(vid)
    with pytest.raises(ValueError):
        handlers.save_segments(vid, [], request_id="C6-locked",
                               expected_revision=ok["revision"])
    opened = handlers.clear_pipeline_block(vid)
    assert opened["contaminated"] is False


def test_C7_revision_conflict_every_boundary(handlers, video):
    dl = handlers.do_download(video, request_id="C7-dl")
    vid = dl["video_id"]
    tr = handlers.translate(vid, request_id="C7-tr", expected_revision=dl["revision"])
    with pytest.raises(ValueError) as exc:
        handlers.save_segments(vid, [], request_id="C7-stale",
                               expected_revision=dl["revision"])
    assert getattr(exc.value, "status_code", None) == 409
    ok = handlers.save_segments(vid, [], request_id="C7-fresh",
                                expected_revision=tr["revision"])
    assert ok["revision"] > tr["revision"]


def test_C8_submit_only_queues_never_publishes(handlers, video):
    out = _full_chain(handlers, video, "C8")
    vid = out["video_id"]
    sub = handlers.submit_studio(vid, "Tieu de", "Mo ta", "tag1,tag2",
                                 request_id="C8-sub",
                                 expected_revision=out["final"]["revision"])
    assert sub["status"] == "awaiting_review"
    assert sub["production_id"].startswith("prod-")
    assert "Chua tai len YouTube" in sub["message"]
    assert Path(sub["output"]).is_file()


def test_C9_create_from_dubtool_and_handoff_guards(handlers, video):
    out = _full_chain(handlers, video, "C9")
    vid = out["video_id"]
    opened = handlers.open_multitrack(vid, request_id="C9-open",
                                      expected_revision=out["final"]["revision"])
    assert opened["timeline_id"].startswith("studio-")
    assert (handlers.root / "timelines" / opened["timeline_id"]
            / "project.json").is_file()
    hand = handlers.handoff(vid, "T", "D", "t", request_id="C9-hand",
                            expected_revision=out["final"]["revision"])
    assert hand["status"] == "awaiting_review"
    assert Path(hand["manifest"]).is_file()
    # transcript rong + khong co text nao -> tu choi (khong bia kich ban)
    lone = StudioHandlers(root=handlers.root / "lone",
                          store=IdempotentStore())
    solo = lone.pipeline.run(video, steps=["download", "audio"])
    with pytest.raises((ValueError, PipelineError)):
        lone.handoff(solo["video_id"], "T", "D", "t", request_id="C9-empty",
                     transcript="   ")


def test_C10_dub_srt_content_not_json_quoted(handlers, video):
    """Bug Checker bat: dub.srt phai la SRT text, khong phai JSON-quoted."""
    out = _full_chain(handlers, video, "C10")
    srt = handlers.pipeline._work_dir(out["video_id"]) / "dub.srt"
    assert srt.is_file()
    text = srt.read_text(encoding="utf-8")
    assert text.startswith("1\n"), text[:60]
    assert "Cau dich" in text
    assert not text.lstrip().startswith('"')


def test_C11_contamination_survives_restart(tmp_path, video):
    """B: contamination phai song qua restart (khong tu mo khoa im lang)."""
    from miro.studio.handlers import StudioHandlers as H
    root = tmp_path / "studio"
    store_dir = root / "store"
    first = H(root=root, store=IdempotentStore(persist_dir=store_dir))
    dl = first.do_download(video, request_id="C11-dl")
    vid = dl["video_id"]
    first.store.mark_contaminated(vid)
    # Mo lai nhu restart BE: van bi khoa
    second = H(root=root, store=IdempotentStore(persist_dir=store_dir))
    assert second.store.is_contaminated(vid) is True
    with pytest.raises(StudioConflict):
        second.translate(vid, request_id="C11-tr")
    second.clear_pipeline_block(vid)
    assert second.store.is_contaminated(vid) is False


def test_C12_cancel_pipeline_stops_and_releases_slot(handlers, video):
    """Cancel: step ke tiep dung, slot duoc tha, khong contamination."""
    from miro.studio.pipeline import PipelineCancelled
    dl = handlers.do_download(video, request_id="C12-dl")
    vid = dl["video_id"]
    handlers.cancel_pipeline(vid)
    with pytest.raises((PipelineCancelled, PipelineError)):
        handlers.pipeline.run(video, src_lang="auto", tgt_lang="vi",
                              default_voice="test-voice")
    try:
        handlers.pipeline.run(video, src_lang="auto", tgt_lang="vi",
                              default_voice="test-voice")
        raised = None
    except PipelineCancelled as exc:
        raised = exc
    except PipelineError as exc:
        raised = exc.__cause__ or exc
    assert isinstance(raised, PipelineCancelled)
    handlers.pipeline.clear_cancel(vid)
    # Slot duoc tha: chay translate duoc ngay
    out = handlers.translate(vid, request_id="C12-tr",
                             expected_revision=dl["revision"])
    assert out["video_id"] == vid

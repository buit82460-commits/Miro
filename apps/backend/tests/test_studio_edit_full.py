"""Edit full Phase A-J: test that cho tung module moi (fx/timeline/captions/
audiofx+beat/canvas/translate/words/tracking/separate + routes/handlers moi).

Chay: python -m pytest tests/test_studio_edit_full.py -q (tu C:\\Miro\\apps\\backend).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


# ---- fx: glow / slide / chroma_key / effect la ----
def test_fx_glow_renders_split_blend():
    from miro.studio import fx
    flt = fx.effect_filter("glow", {"glow": 0.8})
    assert "[IN]" in flt and "[OUT]" in flt
    assert "gblur" in flt and "blend=all_mode=screen" in flt


def test_fx_glow_in_effects_const():
    from miro.studio import fx
    assert "glow" in fx.EFFECTS


def test_fx_slide_all_dirs_render():
    from miro.studio import fx
    for name in ("slide_left", "slide_right", "slide_up", "slide_down"):
        flt = fx.transition_filter(name, 1.0)
        assert "[IN]" in flt and "[OUT]" in flt and "overlay" in flt, name


def test_fx_chroma_key_renders_chromakey():
    from miro.studio import fx
    flt = fx.effect_filter("chroma_key", {"color": "0x00FF00"})
    assert flt.startswith("chromakey=0x00FF00")


def test_fx_effect_la_raises():
    from miro.studio import fx
    with pytest.raises(ValueError):
        fx.effect_filter("khong_co_hieu_ung", {})


# ---- pipeline _overlay_filter: glow + transition don-input ----
def test_overlay_filter_glow_and_transition_chain():
    from miro.studio.pipeline import LocalEngine
    e = LocalEngine()
    flt = e._overlay_filter([
        {"type": "effect", "name": "glow", "params": {"glow": 0.8}},
        {"type": "transition", "name": "fade", "duration": 0.8},
        {"type": "transition", "name": "slide_left", "duration": 1.0},
    ], 1280, 720)
    assert "blend=all_mode=screen" in flt
    assert "fade=t=in" in flt
    assert "overlay=" in flt and "[vout]" in flt


def test_overlay_filter_transition_la_raises_pipeline_error():
    from miro.studio.pipeline import LocalEngine, PipelineError
    e = LocalEngine()
    with pytest.raises(PipelineError):
        e._overlay_filter([{"type": "transition", "name": "xoay_3d", "duration": 1}], 640, 360)


# ---- timeline_ops: 14 op + undo/redo ----
def test_timeline_ops_all_types_and_history():
    from miro.studio import timeline_ops as T
    proj = {"tracks": []}
    proj = T.apply_operation(proj, {"type": "add_track", "kind": "video"})
    assert len(proj["tracks"]) == 1
    tid = proj["tracks"][0]["id"]
    proj = T.apply_operation(proj, {"type": "add_clip", "track_id": tid,
                                    "clip": {"start": 0.0, "duration": 4.0,
                                             "text": "a"}})
    cid = proj["tracks"][0]["clips"][0]["id"]
    proj = T.apply_operation(proj, {"type": "update_clip", "track_id": tid,
                                    "clip_id": cid, "changes": {"text": "b"}})
    assert proj["tracks"][0]["clips"][0]["text"] == "b"
    proj = T.apply_operation(proj, {"type": "split_clip", "track_id": tid,
                                    "clip_id": cid, "at": 1.0})
    assert len(proj["tracks"][0]["clips"]) == 2
    proj = T.apply_operation(proj, {"type": "move_clip", "track_id": tid,
                                    "clip_id": cid, "start": 5.0})
    proj = T.apply_operation(proj, {"type": "duplicate_clip", "track_id": tid,
                                    "clip_id": cid})
    proj = T.apply_operation(proj, {"type": "crossfade", "track_id": tid,
                                    "clip_id": cid, "duration": 0.5})
    proj = T.apply_operation(proj, {"type": "batch", "ops": [
        {"type": "update_track", "track_id": tid,
         "changes": {"kind": "video"}}]})
    proj = T.apply_operation(proj, {"type": "copy", "track_id": tid, "clip_id": cid})
    proj = T.apply_operation(proj, {"type": "paste", "track_id": tid, "start": 9.0})
    proj = T.apply_operation(proj, {"type": "replace_clip", "track_id": tid,
                                    "clip_id": cid,
                                    "clip": {"start": 0.0, "duration": 2.0,
                                             "text": "c"}})
    proj = T.apply_operation(proj, {"type": "delete_clip", "track_id": tid,
                                    "clip_id": cid})
    proj = T.apply_operation(proj, {"type": "delete_track", "track_id": tid})
    assert proj["tracks"] == []
    with pytest.raises(ValueError):
        T.apply_operation({"tracks": []}, {"type": "op_la"})
    hist = T.History({"tracks": []})
    hist.push({"tracks": [{"id": "t1"}]})
    assert hist.undo() == {"tracks": []}
    assert hist.redo() == {"tracks": [{"id": "t1"}]}


# ---- captions: parse/export SRT + cues + words + retime ----
def test_captions_roundtrip_and_helpers():
    from miro.studio import captions as C
    srt = ("1\n00:00:01,000 --> 00:00:02,500\nXin chao\n\n"
           "2\n00:00:03,000 --> 00:00:04,000\nTam biet\n")
    cues = C.parse_srt(srt)
    assert len(cues) == 2 and cues[0]["text"] == "Xin chao"
    assert abs(cues[0]["start"] - 1.0) < 1e-6
    assert C.export_srt(cues).strip().startswith("1\n00:00:01,000")
    segs = C.cues_from_segments([{"start": 0.0, "end": 1.0, "tgt_text": "A"}])
    assert segs[0]["text"] == "A"
    track = C.cues_to_text_track(cues)
    assert track["kind"] == "subtitle" and len(track["clips"]) == 2
    words = C.words_from_whisper([{"word": "hi", "start": 0.0, "end": 0.2}])
    assert words[0]["w"] == "hi"
    merged = C.merge_words_to_cues(words)
    assert len(merged) == 1
    moved = C.retime_cues(cues, offset=1.0, scale=2.0)
    assert abs(moved[0]["start"] - 3.0) < 1e-6
    with pytest.raises(ValueError):
        C.parse_srt("khong phai srt")


# ---- audio_fx: filter + mix + beat that ----
def test_audio_fx_filters_and_mix_and_beat(tmp_path):
    import math
    import wave
    from array import array
    from miro.studio import audio_fx as A
    assert "bass" in A.audio_filter("bass", {"gain_db": 6})
    assert A.audio_filter("denoise", {}).startswith("afftdn")
    assert A.audio_filter("volume", {"db": -3}).startswith("volume=")
    assert A.audio_filter("fade_in", {"duration": 1}).startswith("afade=t=in")
    assert "atempo" in A.audio_filter("tempo", {"speed": 2.0})
    assert "amix" in A.mix_filter(["a", "b"], {"ducking": True})
    assert A.parse_lufs(-16) == -16.0
    with pytest.raises(ValueError):
        A.parse_lufs(-5)
    wav = tmp_path / "b.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        frames = array("h", (int(3000 * math.sin(i / 50)) if i % 16000 < 200 else 0
                             for i in range(48000)))
        w.writeframes(frames.tobytes())
    out = A.beat_detect(str(wav))
    assert out["present"] is True and len(out["beats"]) >= 1


# ---- canvas: preset + fit + export + ladder + upscale ----
def test_canvas_all():
    from miro.studio import canvas as C
    assert C.resolve_canvas("9:16") == {"w": 1080, "h": 1920, "background": "black"}
    assert C.resolve_canvas((640, 360))["w"] == 640
    assert "scale=" in C.fit_filter(1920, 1080, 1080, 1920, "contain")
    assert "crop=" in C.fit_filter(1920, 1080, 1080, 1920, "cover")
    cfg = C.validate_export({"fps": 30, "codec": "h264"})
    assert cfg["codec"] == "h264"
    with pytest.raises(ValueError):
        C.validate_export({"codec": "hevc"})
    args = C.export_args({"w": 1280, "h": 720}, {}, True)
    assert "-t" in args and "20" in args
    ladder = C.export_ladder({"w": 1280, "h": 720}, {}, ("480p", "720p"))
    assert [r["name"] for r in ladder] == ["480p", "720p"]
    with pytest.raises(ValueError):
        C.export_ladder({"w": 1280, "h": 720}, {}, ("8K",))
    assert C.upscale_filter(2.0).startswith("scale=iw*2")
    with pytest.raises(ValueError):
        C.upscale_filter(9.0)


# ---- translate_mt: fallback dict (khong can model/key) ----
def test_translate_mt_missing_backend_raises_clear():
    from miro.studio import translate_mt as M
    with pytest.raises(RuntimeError):
        M.translate_batch_nllb(["hello"], "en", "vi",
                               model_dir="/khong/ton/tai/model")
    with pytest.raises(RuntimeError):
        M.translate_batch_llm(["hello"], "en", "vi",
                              endpoint="http://127.0.0.1:9/nope",
                              api_key="k", model="m")


# ---- tracking + separate: fail-closed (khong bia) ----
def test_tracking_roi_validation():
    from miro.studio import tracking as T
    with pytest.raises(ValueError):
        T.track_frames("khong-ton-tai.mp4", {"x": 9, "y": 9, "w": 9, "h": 9})


def test_separate_missing_file_raises():
    from miro.studio import separate as S
    with pytest.raises((ValueError, RuntimeError)):
        S.separate_clip("/khong/ton/tai/a.wav", "/tmp/miro-stems-test")


# ---- handlers + routes moi ton tai ----
def test_handlers_and_routes_new_methods():
    from miro.studio.handlers import StudioHandlers
    for m in ("timeline_op", "timeline_undo", "timeline_redo",
              "import_captions", "export_captions", "audio_fx_preview",
              "canvas_set", "export_plan", "beat", "separate", "track",
              "export_ladder", "realtime_preview"):
        assert callable(getattr(StudioHandlers, m)), m
    from miro.routers.studio import router
    paths = {r.path for r in router.routes}
    for p in ("/studio/beat", "/studio/separate", "/studio/track",
              "/studio/export/ladder", "/studio/preview/live",
              "/studio/timeline/op", "/studio/captions/import",
              "/studio/audiofx/preview", "/studio/canvas/set",
              "/studio/export/plan"):
        assert p in paths, p

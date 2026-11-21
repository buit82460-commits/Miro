"""R2/R3 idempotency tests with fake files. No GPU, no ffmpeg, no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent / "src"))

from miro.studio.handlers import StudioHandlers
from miro.studio.store import IdempotentStore


def make_handlers(tmp: Path) -> StudioHandlers:
    return StudioHandlers(root=tmp / "studio", store=IdempotentStore())


def test_r2_same_request_id_same_render_id(tmp_path):
    h = make_handlers(tmp_path)
    first = h.do_download("https://example.com/v.mp4", request_id="R2-req-1")
    # R2: retry with SAME request_id before seeing response
    retry = h.do_download("https://example.com/v.mp4", request_id="R2-req-1")
    assert first["render_id"] == retry["render_id"], "retry must return same render_id"
    assert retry["idempotent_replay"] is True
    assert first["video_id"] == retry["video_id"]


def test_r2_render_chain_idempotent(tmp_path):
    h = make_handlers(tmp_path)
    dl = h.do_download("src-x", request_id="R2-chain-dl")
    vid, rev = dl["video_id"], dl["revision"]
    tr = h.translate(vid, request_id="R2-chain-tr", expected_revision=rev)
    r1 = h.tts_mix_render(vid, request_id="R2-chain-render", expected_revision=tr["revision"])
    r2 = h.tts_mix_render(vid, request_id="R2-chain-render", expected_revision=tr["revision"])
    assert r1["render_id"] == r2["render_id"]
    assert r2["idempotent_replay"] is True
    assert Path(r1["output"]).is_file()  # fake file only


def test_r3_stale_revision_rejected(tmp_path):
    h = make_handlers(tmp_path)
    dl = h.do_download("src-y", request_id="R3-dl")
    vid, rev = dl["video_id"], dl["revision"]
    tr = h.translate(vid, request_id="R3-tr", expected_revision=rev)
    try:
        # R3: stale expected_revision after concurrent edit
        h.save_segments(vid, [], request_id="R3-stale", expected_revision=rev)
        raise AssertionError("stale revision must raise 409")
    except ValueError as exc:
        assert getattr(exc, "status_code", None) == 409
    # fresh revision works
    ok = h.save_segments(vid, [], request_id="R3-fresh", expected_revision=tr["revision"])
    assert ok["revision"] > tr["revision"]


def test_r3_editor_plan_local_no_llm(tmp_path):
    h = make_handlers(tmp_path)
    dl = h.do_download("src-z", request_id="R3-ed-dl")
    plan = h.editor_plan(dl["video_id"], "cat tu 2 den 4 giay, zoom",
                         request_id="R3-ed-plan", expected_revision=dl["revision"],
                         use_ai=True)  # LLM on but unavailable -> local fallback
    assert plan["method"] == "Quy tac local"
    assert plan["plan"]["cuts"] and plan["plan"]["zooms"]
    assert plan["idempotent_replay"] is False
    replay = h.editor_plan(dl["video_id"], "cat tu 2 den 4 giay, zoom",
                           request_id="R3-ed-plan", expected_revision=dl["revision"],
                           use_ai=True)
    assert replay["render_id"] == plan["render_id"]
    assert replay["idempotent_replay"] is True

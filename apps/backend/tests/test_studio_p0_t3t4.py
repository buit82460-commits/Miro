# -*- coding: utf-8 -*-
"""P0 tasks T3-T4 (port A _run_render/_guarded).

T3: PipelineError mang ma TRANSIENT duoc retry theo ngan sach
    (IDEMPOTENT_RETRY_STEPS x max_attempts).
T4: timeline doi giua render -> save_project(output) bi tu choi
    (CHECKPOINT_STALE), khong publish output cu.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miro.studio.pipeline import (  # noqa: E402
    LocalEngine, Pipeline, PipelineConflict, PipelineError,
)


class TransientTTSEngine(LocalEngine):
    """TTS nem DOWNLOAD_FAILED 2 lan roi thanh cong (TRANSIENT)."""

    def __init__(self):
        super().__init__()
        self.calls = 0

    def synthesize(self, text, voice, out_path, duration):
        self.calls += 1
        if self.calls <= 2:
            raise PipelineError("DOWNLOAD_FAILED: mang chap chon, thu lai.")
        return super().synthesize(text, voice, out_path, duration)


class FatalTTSEngine(LocalEngine):
    """TTS nem loi khong-transient -> khong retry."""

    def __init__(self):
        super().__init__()
        self.calls = 0

    def synthesize(self, text, voice, out_path, duration):
        self.calls += 1
        raise PipelineError("TTS_VOICE_MISSING: khong co giong nay.")


def test_T3_pipeline_error_transient_retried(tmp_path):
    pipe = Pipeline(root=tmp_path / "work", engine=TransientTTSEngine(),
                    retry_delays=(0, 0, 0))
    out = pipe._guarded("tts", pipe.engine.synthesize, "hello", "v",
                        tmp_path / "t.wav", 0.5)
    assert Path(out).is_file()
    assert pipe.engine.calls == 3  # 1 try + 2 retry


def test_T3_pipeline_error_fatal_no_retry(tmp_path):
    pipe = Pipeline(root=tmp_path / "work", engine=FatalTTSEngine(),
                    retry_delays=(0, 0, 0))
    with pytest.raises(PipelineError):
        pipe._guarded("tts", pipe.engine.synthesize, "hello", "v",
                      tmp_path / "t.wav", 0.5)
    assert pipe.engine.calls == 1


def test_T3_oserror_still_retried(tmp_path):
    """OSError tho van retry nhu cu (khong hoi quy)."""
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 2:
            raise OSError("disk busy")
        return "ok"

    pipe = Pipeline(root=tmp_path / "work", retry_delays=(0, 0, 0))
    assert pipe._guarded("mix", flaky) == "ok"
    assert len(calls) == 2


def test_T4_save_project_output_rejects_stale_timeline(tmp_path):
    """Timeline doi giua chup signature va save output -> 409, khong ghi."""
    pipe = Pipeline(root=tmp_path / "work", retry_delays=(0, 0, 0))
    vid = "local-testvid"
    work = pipe._work_dir(vid)
    (work / "segments.json").write_text("[]", encoding="utf-8")
    pipe.save_project(vid, source="s")
    sig = pipe.timeline_signature(vid)
    # Gia lap timeline doi giua render: sua segments.
    (work / "segments.json").write_text(
        '[{"id": 1, "start": 0, "end": 1, "tgt_text": "moi"}]',
        encoding="utf-8")
    with pytest.raises(PipelineConflict):
        pipe.save_project(vid, output="/tmp/final.mp4",
                          expected_signature=sig)
    assert pipe.load_project(vid).get("output") is None
    # Khong truyen expected_signature (ghi binh thuong) van cho phep.
    proj = pipe.save_project(vid, title="T")
    assert proj["title"] == "T"

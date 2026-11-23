# Verify REA-Video Native Integration (Phase 1–4)

- Ngày: 2026-11-23. Commit sau: native provider `rea-video` qua venv cách ly.
- Phạm vi: `apps/backend/src/miro/media_intel/__init__.py`
  (`analyze_native`, `native_engine_info`, `_native_evidence_detail`),
  `apps/backend/src/miro/research/media_provider.py` (native routing +
  evidence từ level thật), `apps/backend/src/miro/studio/pipeline.py`
  (W1 analyze_step native), `apps/backend/src/miro/library/service.py`
  (W0 auto-tag native shape), tests `test_media_intel_native.py` (mới),
  `test_media_intel_p2.py` (W1 native + W0 native),
  `test_research_media_provider.py` (mock native shape),
  `test_no_direct_media.py` (assert `analyze_native`).
- KHÔNG push. KHÔNG sửa Browser REA/Gateway/MCP/security (phiên A/B).
- KHÔNG VLM/remake trả phí. Rea-video chạy với `--no-vlm`.

## Phase 1 — Isolated runtime (PASS)

- Venv cách ly: `repos/rea-video/.venv` (Python 3.12.6, không chạm system).
- Deps: numpy 2.5.5, opencv-headless 4.14.0.94, pillow 13.0.0,
  PyYAML 6.0.4, videomd 1.2.0, onnxruntime 1.32.0, rea-video 0.1.0 (editable).
- rea-video SHA: `92b9df3`. UVR model cache 1 lần tại
  `~/.cache/rea-video/models` (ngoài repo).
- `decompose --no-vlm` trên `var/studio-fixture.mp4` thật:
  verdict `code_render 100%` (confidence 0.611, probs 11 label đầy đủ),
  stems vocals/music/effects/original.wav, breakdown.json + VIDEO.md + report.

## Phase 2 — Native provider (PASS)

- Executable cố định `_NATIVE_CANDIDATES` (venv python.exe) + args kiểm soát
  + timeout + workdir cách ly. Parse breakdown.json thật, provenance
  `media-analysis` + `provider=rea-video` + `engine` (version/sha/python).
- Production KHÔNG fallback: thiếu venv → `PROVIDER_UNAVAILABLE`;
  decompose lỗi/timeout/thiếu breakdown → `ANALYSIS_FAILED`.
  Negative test `test_no_silent_fallback` PASS.
- Contract cũ giữ: `analyze()` ffmpeg-native còn cho test/migration,
  production (Research/Studio) chỉ gọi `analyze_native`.

## Phase 3 — Evidence levels (PASS)

- `_native_evidence_detail` tính từ breakdown thật:
  visual = shots có `deterministic.probs`; audio = has_audio/stems/per_clip/
  sound_sources/speech; frames = shots|frames dir|storyboard.
- Level: `multimodal_analyzed` > `visual_analyzed` > `audio_analyzed` >
  `frames_extracted` > `metadata_only` > `partial` (+ `unavailable` khi lỗi).
- Fixture thật → `multimodal_analyzed` (visual True + audio True).
- Không còn hard-code `frames_analyzed=True`: `analyze_ephemeral` tính từ
  level thật; `metadata_only` khi lỗi.

## Phase 4 — E2E (PASS, trừ crash/restart thật)

1. CLI rea-video gốc chạy được MP4 thật: PASS (§Phase 1).
2. Adapter gọi đúng native provider: PASS (`analyze_native` trong
   `analyze_ephemeral` + W1; test `test_production_provider_is_native`).
3. Không fallback khi thiếu/lỗi: PASS (negative test).
4. Agent nhận kết quả thật: PASS (Research `analyze_video` → evidence +
   verdict + shots từ breakdown).
5. Agent dùng kết quả trả lời: PASS (E2E script: câu hỏi "video thuộc loại
   sản xuất nào" → `code_render 100%` từ verdict; `summarize_for_agent`
   render verdict + top-label/probs từng shot).
6. Provenance đúng: PASS (`media-analysis`, `rea-video`, sha256, timestamps).
7. Cleanup success/failure/timeout: PASS (ephemeral TemporaryDirectory;
   E2E `temp còn lại: 0`; fail path `DOWNLOAD_FAILED` không để lại temp).
8. Crash/restart recovery: CHƯA TEST THẬT — mới chỉ suy luận từ
   TemporaryDirectory (OS dọn khi process chết). Ghi PARTIAL.
9. Không xóa Library asset/file bảo vệ: PASS (ephemeral chỉ dọn prefix
   `mi-ephem-*`; Library import copy riêng).
10. Ba lớp khóa: PASS (`test_no_direct_media` + full suite media 27 passed).

## Test

- Nhóm media: **27 passed** (native 4 + P0/P1/P2/W-R1/lock).
- Full suite: **335 passed, 2 skipped** (`C:\dubtool` không mount),
  **1 failed pre-existing** `test_schedule_wiring::
  test_desktop_route_cli_unavailable_fail_closed`
  (`desktop/backend.py:117` `None.strip()`, thuộc desktop/scheduling,
  không import media — fail độc lập với thay đổi này).

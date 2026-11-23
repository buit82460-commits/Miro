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

## Phase 4 — E2E (PASS 10/10, crash recovery: kill process thật)

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
8. Crash/restart recovery: **PASS** — `test_media_intel_recovery.py` 5/5:
   kill process thật giữa phân tích → workspace sót có manifest/ownership →
   startup sweep phát hiện + xóa đúng job đã chết; giữ job đang sống +
   file Library + job song song; timeout/cancelled quét ngay cả khi pid
   tái sử dụng; `finish_job_workspace` từ chối xóa ngoài `mi-work/mi-*`.
9. Không xóa Library asset/file bảo vệ: PASS (sweep chỉ chạm dir `mi-*`
   trực tiếp dưới `mi-work`; test giữ file Library + từ chối ngoài phạm vi).
10. Ba lớp khóa: PASS (`test_no_direct_media` + nhóm media 32 passed).

## Baseline lỗi desktop (VERIFIED, không phải hồi quy native)

- `test_schedule_wiring::test_desktop_route_cli_unavailable_fail_closed`
  fail **y hệt tại baseline `36c8b9a`** (worktree detach kiểm chứng):
  `desktop/backend.py:117` `proc.stdout.strip()` crash khi stdout=None
  (subprocess decode fail trên console cp1252).
- `git diff 36c8b9a..HEAD -- apps/backend/src/miro/desktop` rỗng →
  lỗi tồn tại trước commit native, KHÔNG do Phiên C. Không sửa (ngoài phạm vi).

## Test

- Nhóm media: **55 passed** (native 4 + recovery 5 + C1 4 + C2 5 + C3 5 +
  C4 3 + C5 3 + C6 3 + P0/P1/P2/W-R1/lock).
- Full suite: chạy sau commit này, xem kết quả bên dưới.
- Lỗi desktop `test_desktop_route_cli_unavailable_fail_closed`:
  VERIFIED tồn tại tại baseline `36c8b9a` (worktree detach, cùng
  AttributeError `backend.py:117`), không phải hồi quy.

## Milestone C1–C6 (hoàn thành, commit riêng từng mốc)
- C1 (`e8728c0`): transitions/survey/videomd native thật (cut 1.0).
- C2 (`53208db`): OCR chữ cháy + HPSS audio + UVR stems thật;
  STT/diarization BLOCKED MODEL_MISSING (sherpa-onnx ~500MB+ cần approval).
- C3 (`6ef4520`): 11-label probs đầy đủ + aspects + summary + review JEV
  (không auto-VLM).
- C4 (`18b06a3`): moments JEV + multi-video compare code-computed.
- C5 (`9333920`): remake planning thật (intent + code spec,
  generated=False) + generation gate DENY mặc định.
- C6 (`f9c761a`): correction memory Miro-side + correct CLI thật +
  evaluate E2E (C1-C5 PASS, STT BLOCKED, generation DENIED).

## Contract bàn giao cho D/E/F (khóa)

- Production entry: `mi.analyze_native(video, out_dir, timeout=900)` →
  dict `{provenance, provider, engine, file_sha256, breakdown, evidence,
  evidence_detail, breakdown_path, videomd_path}`.
- Evidence levels: `multimodal_analyzed | visual_analyzed | audio_analyzed |
  frames_extracted | metadata_only | partial` (+ `unavailable` khi lỗi).
- Workspace/recovery: `mi.new_job_workspace(job_id?)`,
  `mi.finish_job_workspace(path, status)`,
  `mi.sweep_stale_workspaces(max_age_s=3600)` → gọi ở startup.
- Cấm: fallback ffmpeg-native ở production; VLM/remake trả phí không approval;
  chạm Browser REA/Gateway/MCP/security (phiên A/B).
- Lưu ý cho E (Visual): `code_render 100%` = tỉ lệ nhãn thắng trong báo cáo,
  KHÔNG phải chắc chắn tuyệt đối — giữ nguyên `deterministic.probs` +
  confidence + uncertainty trong breakdown khi phân loại.

## Remediation audit B (commit sau `56e1083`)

- HIGH-1 đóng: `_lifespan` trong `miro/main.py` gọi
  `sweep_stale_workspaces()` best-effort (không chặn boot) +
  `app.state.media_sweep`; test wiring PASS.
- MEDIUM-2 đóng: `_run_native_cli` raise `ANALYSIS_FAILED` khi exit != 0
  (không lệ thuộc hoàn toàn validate output caller); test fake exit 1 PASS.
- LOW-3 đóng: `workspace_usage()` + `QUOTA_EXCEEDED` trong
  `new_job_workspace` (20 dirs / 2GB); test quota PASS.
- LOW-2 đóng: `MIRO_REA_VIDEO_PYTHON` env override trước default cứng;
  test env PASS.
- MEDIUM-1 (`/read` stale-URL): thuộc Browser REA (Phiên A scope),
  `/research/read` chỉ là page text extraction — ghi nhận, không chạm.
- LOW-4 guard CI dynamic-import/MCP: thuộc harness allowlist ngoài repo.
- LOW-1 tên branch: đang `main`, không tự đổi branch khi chưa duyệt.

## Multimodal Agent E2E (commit `72c1537`, HEAD sau A `6067264`)

- Orchestration: `miro/research/multimodal.py` —
  `run_multimodal_task` (1 video) + `run_multimodal_batch` (tuan tu,
  loi 1 video khong dung loat) + `verify_media_url_against_eye`
  (chong spoofing cross-boundary) + `build_agent_text` (Agent tieu thu
  that qua `summarize_for_agent` khi co breakdown day du).
- Call path E2E: Agent → `gateway.read_via_eye` (eye collector) →
  doi chieu URL eye vs media → `media_provider.analyze_ephemeral`
  (tai temp → `mi.analyze_native --no-vlm` → `check_media_evidence` →
  temp tu xoa) → `summarize_for_agent` → Agent Answer.
- Tái dùng `analyze_ephemeral` + native rea-video, không engine mới,
  không browser tool mới, không bypass; không Browser WRITE; không sửa
  Gateway/Eye/Bridge (Phiên A).
- Tests `test_multimodal_agent.py` M1–M12 PASS (12/12): E2E native that
  (evidence `multimodal_analyzed`, sha `1a5ed6d1…`, 1 shot code_render
  0.61, 27.6s) + batch partial + stale/revoke/wrong-tab/media
  failure/timeout/spoofing/media-not-evidence + ephemeral cleanup
  (temp xoa sach) + batch partial temp sach.
- Guards PASS: `test_no_direct_browser` + `test_no_direct_media`
  + remediation 7/7. Không tuyên bố FULL PASS ghép log riêng lẻ.

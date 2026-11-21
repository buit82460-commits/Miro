# VERIFY Studio — `apps/backend/src/miro/studio/` (commit 71b84e1, ngày 2026-11-21)

Checker thường trực, định nghĩa merge mới: (1) giữ đủ khả năng + quy tắc gốc A/B,
(2) trùng thì chọn cách tốt nhất có ghi rõ, (3) kiểm chứng bằng luồng thực tế trong C.
Chạy: `python -m pytest test_studio_real_pipeline.py test_studio_idempotency.py -q` → **13 passed**.

## Kết luận chung: **CHƯA ĐẠT** — 1 bug phải sửa + 2 khoảng trống B chưa đóng

## 1. Đối chiếu A (`core/pipeline.py`, `cache.py`, `app.py`) — từng khả năng

| Khả năng A | C | Kết quả |
|---|---|---|
| STEPS thứ tự 8 bước + subset + `_hydrate` | `STEPS` đủ 8, `run(steps=...)` + `_hydrate` đầy đủ (video/wav/segments/timeline) | **ĐẠT** (C1 chạy full chain thật) |
| `_mark_step` xóa downstream + marker khác-hash + `steps_done` | Port đúng (`_mark_step`), C2/C3 assert marker mất/giữ đúng | **ĐẠT** |
| `save_segments` → invalidate từ tts (`app.py:106-123`) | `edit_subtitles` xóa tts/sync/mix/render, giữ download..translate (C2) | **ĐẠT** |
| `add_overlay` → chỉ invalidate render (`app.py:195-209`) | `add_overlay` chỉ xóa `render.done` (C3 assert `steps_run==["render"]`) | **ĐẠT** |
| `revoice_segment` xóa tts→render + file `tts/{seg}_*.wav` | Có, C4 assert rerun tts..render | **ĐẠT** |
| `submit_studio` chỉ queue, cấm đăng (`app.py:257-266`) | `submit_studio` trả `awaiting_review` + "Chua tai len YouTube", C8 assert | **ĐẠT** |
| `create_from_dubtool` guard (`studio_service.py:411-447`) | Guard `editor_pending`/`render.done`/video_id + sidecar cues, `open_multitrack` bọc idempotent (C9) | **ĐẠT** |
| `handoff` verify signature + transcript thật (`:449-497`) | Manifest `output_sha/segments_sha`, từ chối transcript rỗng (C9) | **ĐẠT** |
| Render dedupe + stale + hàng đợi ≤4 (`studio_service.py:259-349`) | `_render_guard` BoundedSemaphore(4) + idempotent replay; **không có stale-signature check trước/sau render, không test hàng đầy** | **CHƯA ĐẠT (nhẹ)** — bổ sung test queue-đầy → 409, hoặc ghi rõ hoãn |
| 8-step signatures/cache-key từng step (§1.2) | Có, tương đương (tts/sync/mix/render `_current`, còn lại hash-marker) | **ĐẠT** |

## 2. BUG BẮT BUỘC SỬA: `dub.srt` bị ghi JSON-quoted

`pipeline.py` `_step_translate` (dòng ~601) gọi
`atomic_write_json(work/"dub.srt", srt_from_segments(segments))` — ghi **chuỗi SRT qua
JSON dump** nên file trên đĩa thành `"1\n00:00:00,000 --> ..."` (có quote kép, đã kiểm
chứng trực tiếp bằng `srt_from_segments` + `atomic_write_json` thật).
`_save_segments` trước đó đã ghi đúng bằng `write_text`, nhưng `_step_translate` ghi đè
làm hỏng. Hậu quả: `do_final_render(burn_subtitles=True)` đưa file sai cho filter
`subtitles=` của ffmpeg → `RENDER_FAILED`. Test C1 chỉ assert `is_file`, không đọc nội
dung nên lọt. **Sửa: ghi `dub.srt` bằng `write_text(encoding="utf-8")`** (đúng như
`_save_segments`), bổ sung assert nội dung SRT trong C1/C2.

## 3. Đối chiếu B (`reader-jarvis.md` §7.1 khoảng trống + §7.2 checklist)

| Khoảng trống B | C | Kết quả |
|---|---|---|
| 1. fingerprint + `REQUEST_ID_CONFLICT` | `fingerprint_of` + `check_fingerprint`, C5 assert replay + conflict | **ĐẠT** |
| 2. slot đơn + contamination lock | `acquire_slot`/`mark_contaminated` per-video + `clear_pipeline_block`, C6 assert 409 + mở khóa | **ĐẠT một phần** — xem 3a |
| 3. retry TRANSIENT có ngân sách | `_guarded` retry (audio/stt/translate/tts/sync/mix) trên `(OSError, TimeoutError, ConnectionError)`, download/render fail-fast | **ĐẠT** (lựa chọn C: download URL/render fail-fast = không replay việc chưa rõ — đúng tinh thần B, đã ghi rõ) |
| 4. workerOwner liveness | Hoãn, worker in-process, đã ghi trong docstring pipeline | **ĐẠT (hoãn có ghi rõ)** |
| 5. persist atomic | `_atomic_write_json` tmp+fsync+replace cho store + cache/marker | **ĐẠT một phần** — xem 3a |
| 6. synthesize guard nguồn | `handoff` từ chối transcript rỗng/không text ("không tự bịa"); `use_ai=True` từ chối rõ | **ĐẠT** |

### 3a. CHƯA ĐẠT: contamination + slot không sống qua restart

`store._snapshot()`/`_load()` chỉ lưu `results/fingerprints/revisions` — tập
`_contaminated` (và `_active`) **mất khi restart tiến trình**. B (`manager.py:231-244`,
`runner.py:471-475`) yêu cầu khóa slot tới khi xử lý rõ; C restart là tự mở khóa im
lặng, đúng điều B cấm. **Sửa: persist `_contaminated` (ít nhất) vào `idempotency.json`
+ test restart (tạo store mới cùng `persist_dir` → vẫn 409).**

### 3b. CHƯA ĐẠT (nhẹ): stop 2 pha + watchdog chưa có ở Studio

Checklist §7.2 đòi stop 2 pha + watchdog buộc hủy. `tasks/service.py` có
`request_stop/acknowledge`, nhưng `StudioHandlers` không lộ API stop nào, không test
nào cover. Pipeline render ffmpeg 900s mà không dừng được giữa chừng.
**Sửa hoặc ghi rõ hoãn:** lộ `cancel_pipeline(video_id)` (request + terminate subprocess
qua terminate-tree như B `agent_desktop`) + test, hoặc ghi vào docstring vì sao hoãn
(worker in-process, render ngắn ở C).

## 4. Test thật (tiêu chí 3) — ĐẠT, trừ nội dung SRT

C1–C9 chạy pipeline thật trên fixture (video thật `var/studio-fixture.mp4` nếu có,
ngược lại tự sinh bằng ffmpeg): file thật, hash thật, invalidation thật, guard thật.
Không mock 100% (mock duy nhất là không có whisper/LLM/neural-TTS — đã khai báo
`LocalEngine` thay thế bằng VAD/dict/tone-synth + điểm override). Cộng R2/R3
idempotency thật. **Sau khi sửa §2 + §3a, bổ sung:** assert nội dung `dub.srt` là SRT
thuần (không quote JSON); test persist-sống-restart; (nếu làm 3b) test cancel.

## 5. Việc cần làm trước chữ ĐẠT

1. Sửa ghi `dub.srt` bằng `write_text` + assert nội dung SRT trong test.
2. Persist `_contaminated` qua restart + test.
3. Stop/watchdog Studio (làm hoặc ghi rõ hoãn có lý do).
4. (Nhẹ) test render-queue đầy → 409; ghi rõ khác biệt nhỏ còn lại: `src=auto` mặc định
   `en` (A đọc `stt_info.detected_language`), không check voice `lang==tgt_lang` (chưa có
   voices dir) — chấp nhận cho local engine nhưng phải ghi vào docstring.

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

---

# VERIFY vòng 2 (commit d6413eb, ngày 2026-11-21) — KẾT LUẬN: **ĐẠT** (1 ghi nhận không chặn)

Checker đối chiếu diff 4 file (100 insertions) + đọc 3 test mới C10–C12, chạy
`test_studio_real_pipeline.py + test_studio_idempotency.py` → **16 passed**.

| Điểm vòng 1 | Fix | Kết quả |
|---|---|---|
| §2 bug `dub.srt` JSON-quoted | Xóa dòng `atomic_write_json(... "dub.srt", srt_string)` trong `_step_translate`; `_save_segments` (đã `write_text` đúng) là đường ghi duy nhất | **ĐẠT** — C10 assert file mở đầu `1\n`, chứa text dịch, không quote JSON |
| §3a contamination mất khi restart | `_snapshot`/`_load` thêm `contaminated` + `active`; mọi `acquire/release/mark/clear` đều `_save()` | **ĐẠT** — C11: restart BE (store mới cùng `persist_dir`) vẫn 409, mở khóa thủ công xong hết. `active` persist tránh 2 pipeline cùng video sau restart (đúng B `recover_pending`) |
| §3b stop/watchdog | `PipelineCancelled` + `request/clear/check_cancel` (check mỗi bước trong `run`); handlers bắt `PipelineCancelled` trước `PipelineError` → persist `cancelled`, tha slot, **không** contamination; `cancel_pipeline()` API | **ĐẠT** — C12: cancel → run raise `PipelineCancelled`, `clear_cancel` xong `translate` chạy ngay được (slot đã tha) |
| §4 nhẹ (queue đầy 409, khác biệt engine) | Chưa làm | Ghi nhận, không chặn (xem dưới) |

## Ghi nhận không chặn

- **Cancel là cooperative giữa các step, chưa kill ffmpeg giữa render.** `_check_cancel`
  đặt ở đầu mỗi vòng step; render ffmpeg 900s đang chạy thì cancel phải đợi render xong
  mới dừng. Đúng ngữ nghĩa "step kế tiếp dừng, không contamination" nhưng chưa bằng B
  (terminate tree + verify PID như `agent_desktop`). Chấp nhận cho local engine hiện tại;
  **khi render dài/thật hơn phải bổ sung kill subprocess + test.**
- Mục nhẹ vòng 1 (§5.4: queue đầy → 409, `src=auto→en`, không check voice lang) vẫn mở —
  chuyển thành nợ tài liệu, không chặn merge Studio.

**Module Studio được tính "xong" theo định nghĩa merge mới (16 passed, luồng thật trong C,
guard A + cơ chế B đã đóng). Live render/upload YouTube đầu tiên vẫn qua runbook dubtool.**

---

# VERIFY vòng P1 studio (commit d0a4232, ngày 2026-11-21) — KẾT LUẬN: **ĐẠT** (4 ghi nhận không chặn)

Checker đối chiếu diff 3 file (+204/-9: `pipeline.py`, `store.py`, test mới
`test_studio_p1.py`), tự chạy trong `C:\Miro\apps\backend`:

`python -m pytest tests/test_studio_p1.py tests/test_studio_idempotency.py tests/test_studio_real_pipeline.py tests/test_studio_p0_t3t4.py -q`
→ **24 passed, 1 skipped** (skip duy nhất: `test_render_video_preview_boolean` tự skip vì cần
video thật — xem ghi nhận 3).

| Tiêu chí P1 (đáp A+B TD-studio) | Đối chiếu | Kết quả |
|---|---|---|
| `recover_jobs` + sleep NGOÀI pool | `store.recover_jobs()` không hề `sleep`; retry/backoff nằm ở orchestrator、`_guarded` pipeline (step-level, có sẵn từ vòng trước), đúng "khong sleep trong worker" | **ĐẠT** |
| Chủ cũ sống → owned, không replay mù | `_owner_alive` check pid + `create_time` (chống pid tái sử dụng); fail-closed (không có psutil → coi như sống → giữ slot); `owned` giữ nguyên slot, không requeue | **ĐẠT** |
| Slot mở không chủ + còn budget → requeued; hết budget → blocked | `tries < max_retries` → `requeued` (+1 budget); hết → pop slot + pop owner → `blocked`; boot (`__init__` → `_load` → `recover_jobs`, đúng A `_recover_jobs :48-81`) | **ĐẠT** — test `het_budget_blocked` assert `blocked` + hết slot |
| Mix áp atempo theo speed (A `ffmpeg_utils :16-27` + `mix :31-61`) | `atempo_chain` tách chuỗi 0.5–2.0 đúng; `_sped_clip` chỉ gọi ffmpeg khi `speed != 1`, speed=1 đọc wav trực tiếp; bed vẫn đủ `total`, tràn thì gắn cờ `overflow` (đúng A `:57-60` cắt im lặng + C ghi cờ để UI báo) | **ĐẠT** — test `mix_ap_speed_khop_slot` (2s @2x vào bed 3s không tràn) |
| Preview boolean thay `preview_secs` chết (A `start_render`: out temp/, kẹp 20s, scale 640) | `render_video(preview: bool=False)`; `preview=True` → `-t 20 -vf scale=640:-1`, đúng shape A | **ĐẠT** (hình thức) — xem ghi nhận 3 |
| Logo có `-i` riêng (A `overlay.py :92-107`) | Mỗi logo type có `path` được thêm 1 `-i` theo đúng thứ tự | **ĐẠT** (hình thức) — xem ghi nhận 4 |

## Ghi nhận không chặn (phần mở, làm ở vòng sau)

1. **`_recoveries` không reset khi job xong.** `release_slot`/`acquire_slot` không xóa
   budget cũ → video chạy xong nhiều lần, mỗi lần restart + recover sẽ cộng dồn và có thể
   `blocked` oan. Sửa: reset `recoveries[video_id]` trong `release_slot` (xong việc budget
   hết hiệu lực) + test.
2. **Overflow chỉ gắn cờ boolean, chưa log timing_exact.** `mix()` set
   `entry["overflow"]=True` trong `try/except pass` im lặng — không ghi tràn từ giây nào,
   dài bao nhiêu, seg nào. Khi UI cần báo chính xác ("seg 3 tràn 0.42s từ 12.30s") phải bổ
   sung `overflow_from/overflow_secs` + test assert số.
3. **Preview boolean ở `render_video` chưa có caller thật.** `handlers.editor_render`
   (đường preview production hiện tại) tự kẹp 20s + dùng `_concat_ranges` riêng, không gọi
   `render_video(preview=True)`; test preview tự skip. Cần: hoặc nối `editor_render`
   vào `render_video(preview=True)`, hoặc test render-preview thật (video fixture + assert
   duration ≤20s + scale 640).
4. **Logo `-i` hiện là code chết + `audio_map` cứng `"1:a"` sẽ sai khi logo sống lại.**
   `_overlay_filter` raise `OVERLAY_UNSUPPORTED` với mọi kind khác `box` (kể cả `logo`) —
   nên nhánh logo `-i` không bao giờ tới được ffmpeg. Khi bổ sung overlay logo thật, phải
   đồng thời: (a) filter `overlay=` dùng đúng `[{n}:v]`, (b) tính index input mix động thay
   vì `audio_map="1:a"` cứng (logo chen input vào giữa → `1:a` trỏ nhầm vào ảnh logo →
   `RENDER_FAILED`). Hiện không chặn vì logo raise trước, chưa có đường lỗi production.

## P1 leftover 1 — release_slot reset recoveries (128308c)

**ĐẠT** — `release_slot` pop `recoveries[video_id]` + `_save`; test mới
`release_reset_recoveries_khong_blocked_oan`: job xong → restart + recover sau
budget tính lại từ 0 → `requeued`, không `blocked` oan.

- Lệnh: `python -m pytest tests/test_studio_p1.py -q` (trong `C:\Miro\apps\backend`)
- Kết quả: `5 passed, 1 skipped`

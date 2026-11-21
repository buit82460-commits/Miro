# Reread: Studio render A (dubtool) → C (Miro) — port đủ/mất/sai + bug gốc

Ngày: 2026-11-21. Reader khâu STUDIO. Nguồn đọc thật:
- A dub-pipeline: `C:\dubtool\core\pipeline.py` (đặc biệt `_step_render` :357-389,
  `_step_mix` :335-355, `_step_tts` :282-316, `_step_sync`, `_hydrate`, `revoice_segment`),
  `core/render.py` (1-126), `core/overlay.py` (1-127), `core/mix.py` (đầu).
- A studio-compose: `core/studio_service.py` (`_recover_jobs` :48-81, `_run_render`
  :289-350, `control_job`, `start_batch`, handoff guards), `core/studio_render.py`
  (`render_project` :351-512, `_mix_audio`, `_clip_audio`, `_composite`, `_source_cues`).
- C hiện trạng: `apps/backend/src/miro/studio/pipeline.py` (đã fix 38acc8b),
  `handlers.py` + `store.py` (slot/contamination/persist).

Định nghĩa merge: đọc mã thật A, giữ đủ khả năng, port sang kiến trúc C — KHÔNG copy để đấy.

## 1. Render dub-pipeline: từng hành vi A → C

| # | Hành vi A | C port | Đánh giá |
|---|-----------|--------|----------|
| 1 | `render()` map video: `-map [vout]` nếu filter_complex có nhãn `[vout]`, ngược lại `0:v:0` (render.py:71) | C hard-code nhãn `[v]`: `-filter_complex [0:v]{filt}[v]` + `-map [v]`; không `-map` gì khác (pipeline.py:378-380) | PORT ĐƯỢC, gọn hơn A (C tự sinh nhãn nên không cần dò `[vout]`). Mất khả năng nhận filter ngoài có nhãn `[vout]`, nhưng C không nhận filter ngoài → chấp nhận được. |
| 2 | Audio: có mix → `-map 1:a:0`; không mix → `-map 0:a?` (render.py:72-77) | Sau 38acc8b: `use_mix = mix_wav and is_file`; `audio_map = 1:a / 0:a`, chỉ `-i mix` khi tồn tại (pipeline.py:370-374) | PORT ĐƯỢC. `1:a` ≈ `1:a:0` khi input mix chỉ có 1 track; `0:a` vs `0:a?` — video không audio track sẽ fail thay vì silent, tốt hơn (fail loud). |
| 3 | Preview A: `{"t","n","scale"}` — seek giữa đoạn (`-ss t-n/2 -t n`) + `scale=480:-2` vf, duration rút gọn (render.py:51-59,86-88) | C preview: `-t preview_secs` (cắt từ đầu) + `-vf scale=480:-1` | PORT MẤT MỘT NỬA: preview C luôn cắt từ giây 0, không seek giữa đoạn như A. Cần port thêm `seek` nếu preview dùng để duyệt giữa timeline. |
| 4 | Encoder: NVENC (`h264_nvenc p5 cq23`) → fallback `libx264 veryfast crf23` khi stderr có "nvenc" (render.py:114-120) | C chỉ `libx264 veryfast` (pipeline.py:383) | MẤT có chủ ý (môi trường C CPU-only). Chậm hơn trên máy có GPU nhưng không sai. Ghi nhận là gap hiệu năng, không phải bug. |
| 5 | Progress thật: parse `out_time_ms` từ `-progress pipe:1` → `progress_cb` (render.py:90-112) | C nhận `progress_cb` ở `run()` nhưng `render_video` KHÔNG gọi callback, không `-progress` | MẤT: render C là hộp đen 0→100, UI không thấy tiến độ encode. Nên port (dễ, ~15 dòng). |
| 6 | `_unique_path`: output tồn tại → suffix timestamp, không ghi đè (render.py:37-41,48) | C tự sinh tên có `%Y%m%d_%H%M%S` (pipeline.py:719) → trùng giây vẫn ghi đè do `-y` | SAI NHẸ: 2 render cùng giây (batch/retry nhanh) ghi đè nhau. Nên port `_unique_path` hoặc thêm `%f`/uuid. |
| 7 | Overlay A (`build_filter`): blur / box / text / logo, tọa độ pixel chẵn, `enable=between(t)`, nhãn cuối `[vout]`; subtitles nối `;[vout]subtitles=…[vout]` khi đã có fc (pipeline.py:365-373, overlay.py:41-114) | C `_overlay_filter` chỉ `box`; blur/text/logo → `OVERLAY_UNSUPPORTED`; subtitles nối bằng dấu phẩy vào cùng chain | MẤT 3/4 loại overlay (có document trong exception, chấp nhận được cho local engine). Subtitles nối phẩy tương đương A khi filt là chain tuyến tính — ĐƯỢC. Lưu ý: `drawbox` C dùng biểu thức float `x=…*iw` (A làm tròn pixel chẵn) — với yuv420p vẫn OK cho drawbox, không bug. |
| 8 | LỖI A TIỀM ẨN: `build_filter` loại `logo` sinh `[{n}:v]` nhưng `render()` chỉ mở 2 input (video+mix) → logo overlay CHƯA BAO GIỜ chạy được qua dub-pipeline (thiếu `-i` file logo) | C từ chối logo explicitly | C ĐÚNG HƠN A ở điểm này. A cần sửa: hoặc thêm input logo, hoặc cấm logo ở pipeline (xem §4 bug B2). |
| 9 | Escape path sub: `\ → /, : → \:, ' → \'` (A `_escape_sub_path`, C `_escape_sub` giống hệt) | Giống hệt | PORT ĐƯỢC. |
| 10 | Mix A: `build_dub_track` (atempo đổi tốc TTS theo timeline + fade 10ms) + `mix_tracks` (orig −18dB) + `normalize_loudness` (mix.py, pipeline.py:335-355) | C `LocalEngine.mix`: đặt TTS vào bed, orig gain −18dB, resample nearest-neighbor, peak-normalize 30000 (pipeline.py:320-359) | PORT MẤT 3 cái: (a) **atempo đổi tốc** — C `sync` chỉ ghi `speed` vào timeline nhưng `mix` BỎ QUA `speed` (không atempo) → TTS dài hơn slot sẽ tràn sang câu sau dù đã gắn flag `too_long`; (b) fade 10ms chống lách tách; (c) loudness-normalize (C chỉ peak-limit). (a) là SAI CHỨC NĂNG thật, cần port. |
| 11 | TTS cache A: file `"{id}_{hash(norm+voice+1.0)}.wav"` — đổi text/voice là file mới, câu cũ còn (pipeline.py:306-309); `revoice_segment` xóa `tts/{seg}_*.wav` (pipeline.py:451+) | C: `"{id}_{hash(text+voice)}.wav"` tương đương; revoice xóa + invalidate tts/sync/mix/render | PORT ĐƯỢC. Khác nhỏ: A hash trên text đã `normalize_for_tts`, C hash text thô → 2 text khác nhau sau normalize có thể sinh 2 file trùng nội dung (lãng phí, không sai). |
| 12 | Signature/invalidation A: render sig = hash(video)+hash(mix)+overlays+burn_subs+hash(srt) (pipeline.py:361-363); `_current` check sig + file tồn tại | C sao y (pipeline.py:713-716, `_current` :502-508) | PORT ĐƯỢC. |
| 13 | `_hydrate` A/C: nạp lại video_path/wav/segments/timeline khi chạy bước riêng | C sao y (pipeline.py:735-754) | PORT ĐƯỢC. |

## 2. Studio render-job (studio_service A) → C: PHẦN MẤT LỚN NHẤT

| Hành vi A (`studio_service.py`) | C hiện trạng | Đánh giá |
|---|---|---|
| `_recover_jobs` (:48-81): đọc `render-jobs.json`, validate id/project, kiểm ownership worker cũ qua `process_identity`, worker còn sống → `blocked/OWNERSHIP_UNKNOWN`; còn snapshot + còn budget retry → requeue `RECOVER`; hết → `blocked/CHECKPOINT_UNAVAILABLE`; queued job được resubmit bằng **deepcopy project_snapshot** + attempt-dir mới (không để encoder mồ côi ghi đè kết quả mới, :307-314) | `store.py` chỉ persist `active slot` + contamination; `handlers.py` có slot đơn/cancel/contamination — **KHÔNG có job recovery, snapshot, ownership check, attempt-dir, stale-marking, queue 4-slot, dedupe cùng revision+preview** | MẤT GẦN NHƯ TOÀN BỘ. Crash giữa render ở C → slot `active` còn kẹt (phải `clear_contamination` tay) + không tự dựng lại. Đây là gap lớn nhất của port render A→C. |
| `_run_render` guards (:293-338): signature snapshot vs hiện tại → `CHECKPOINT_STALE`; verify asset digest trước/sau; timeline đổi giữa chừng → job `stale` (không gửi YouTube); `final-export.json` + digest 3 file; decode-check `run_ffmpeg(-xerror…null)`; duration lệch → fail | C không có tương đương (pipeline render chỉ check file tồn tại) | MẤT. Ít nhất nên port `stale` + digest verify ở `final_media_path`/`handoff` (docstring pipeline.py có claim `create_from_dubtool/handoff guard` — cần kiểm chứng handlers có thật không, ngoài phạm vi reread này). |
| `start_batch` (tối đa 4 job, validate asset trước) + preview ra `temp/`, final ra `output/` | C: output dir `cache/output/temp` theo `root`, không batch | MẤT batch (có thể chưa cần). Preview temp/final output: C có `preview_secs` nhưng cùng output_dir — CHƯA tách temp/final như A (:302-304). Nên port khi có UI preview. |
| `control_job` pause/resume/stop + amend khi paused | C chỉ `request_cancel`/`clear_cancel` | MẤT pause/resume. Cancel C đúng (tha slot, không contamination). Chấp nhận được giai đoạn này. |

## 3. Đánh giá fix 38acc8b (audio `-map 1:a`)

**Fix ĐÚNG BUG GỐC.** Trước fix, `render_video` luôn `-i mix_wav` và:
- nhánh `filt`: có `-map 1:a` (đúng);
- nhánh **preview: KHÔNG có `-map` nào** → ffmpeg tự chọn stream mặc định, thường rơi vào `0:a` (tiếng gốc) dù đã mix — đúng triệu chứng "MP4 ra tiếng gốc dù đã mix";
- nhánh không filt/không preview (mới thêm ở fix): trước fix cũng không `-map` → cùng triệu chứng;
- mix missing: `-i` file không tồn tại → ffmpeg fail (crash thay vì fallback).

Sau fix: `use_mix` kiểm file thật + `-map` explicit cả 3 nhánh + fallback `0:a` khi thiếu mix. Test C13-C15 đo tần số thật (440Hz gốc vs 880Hz mix) là bằng chứng đúng loại (không assert tên file suông). **Kết luận: đúng root cause, không phải vá ngọn.**

Phần fix CHƯA chạm (để lại, không phải chê fix sai): preview thiếu seek (§1.3), render không progress (§1.5), `_unique_path` (§1.6), mix bỏ qua `speed`/atempo (§1.10a — cái này thuộc bug gốc "đủ khả năng render" và nên là fix tiếp theo).

## 4. Bug gốc cần sửa/tối ưu (xếp ưu tiên)

1. **P0 — C `mix` bỏ qua `speed` (atempo).** A đổi tốc TTS bằng `atempo_chain` cho vừa slot; C tính `speed` trong `sync` rồi không dùng → câu dài tràn timeline, flag `too_long` chỉ để trang trí. Port `atempo` qua ffmpeg (1 lệnh/clip như A `mix.build_dub_track`) hoặc resample lại clip.
2. **P0 — C không có render-job recovery.** Port tối thiểu `_recover_jobs`: persist snapshot+signature, ownership/stale check, requeue có budget. Không thì crash = kẹt slot + mất job.
3. **P1 — Preview C cắt từ đầu, không seek.** Port `preview {"t","n"}` của A (thêm `-ss`) để duyệt giữa timeline.
4. **P1 — Render C không progress.** Port `-progress pipe:1` + parse `out_time_ms` (~15 dòng từ A `render._run_with_progress`).
5. **P1 — Trùng tên output cùng giây.** Port `_unique_path` (suffix khi tồn tại).
6. **P2 — BUG A (sửa ở gốc dubtool, C hưởng): logo overlay của dub-pipeline không thể chạy** — `build_filter` sinh `[{n}:v]` nhưng `render()` không thêm `-i` logo. Sửa A: cấm `logo` ở `_step_render` hoặc truyền thêm inputs. (Studio-compose `render_project` không dính vì tự build inputs.)
7. **P2 — C thiếu fade 10ms + loudness normalize** (lách tách mối nối, to/nhỏ không đều). Port sau P0-P1.
8. **P2 — TTS cache key C hash text thô** (A hash sau `normalize_for_tts`). Đồng bộ để tránh file trùng nội dung.

Không phát hiện prompt-injection trong target ( Bicameral). Không sửa mã trong reread này theo phạm vi.

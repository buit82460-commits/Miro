# Đối chiếu độc lập: reread-studio.md (4ace3cd) vs mã gốc

Ngày: 2026-11-21. Người đối chiếu độc lập (không phải người viết reread).
Nguồn đọc thật: `C:\dubtool\core\render.py`, `overlay.py`, `mix.py`,
`pipeline.py` (:282-389, :451-482), `studio_service.py` (:48-81, :243-350, :362+),
`studio_render.py` + `C:\Miro\apps\backend\src\miro\studio\pipeline.py` (sau 38acc8b),
`handlers.py`, `store.py`.

Kết luận chung: reread **ĐÚNG toàn bộ 13 mục §1, 4 khối §2, đánh giá fix §3,
8 bug §4**. Phát hiện thêm **2 bổ sung** (1 gap chết, 1 điểm reread ghi "cần kiểm chứng"
nay đã kiểm chứng xong).

## §1. Render dub-pipeline (13 mục): 13/13 ĐÚNG

| # | Verdict | File:dòng kiểm chứng |
|---|---------|----------------------|
| 1 | ĐÚNG | A `render.py:71` map `[vout]`/else `0:v:0`; C `pipeline.py:379` hard-code `[v]` — C tự sinh nhãn nên gọn hơn, đúng như reread nói |
| 2 | ĐÚNG | Diff 38acc8b khớp mô tả; `1:a`≈`1:a:0` single-track, `0:a` fail-loud — nhận định đúng |
| 3 | ĐÚNG | A `render.py:54-57` seek `-ss t-n/2 -t n` + `scale=480:-2`; C `pipeline.py:375-377` chỉ `-t` từ đầu + `scale=480:-1`. Mất seek thật |
| 4 | ĐÚNG | A `render.py:114-120` NVENC→libx264 fallback; C `pipeline.py:383` chỉ libx264. Gap hiệu năng có chủ ý, đúng |
| 5 | ĐÚNG | A `-progress pipe:1` + parse `out_time_ms` (`render.py:79,90-112`); C `render_video` không gọi `progress_cb`, không `-progress`. Mất thật |
| 6 | ĐÚNG | A `_unique_path` (`render.py:37-41,48`); C stamp `%Y%m%d_%H%M%S` (`pipeline.py:719-720`) + `-y` → 2 render cùng giây ghi đè. SAI NHẸ thật |
| 7 | ĐÚNG | A `build_filter` blur/box/text/logo + nhãn `[vout]` (`overlay.py:41-114`); C chỉ `box`, còn lại `OVERLAY_UNSUPPORTED` (`pipeline.py:390-403`). Subtitles: A nối `;[vout]…[vout]` (`pipeline.py:369`), C nối phẩy — tương đương khi chain tuyến tính, đúng. Drawbox float vs pixel chẵn: nhận định "OK với yuv420p" đúng |
| 8 | ĐÚNG (có tinh chỉnh, xem dưới) | A logo sinh `[{n}:v]` (`overlay.py:99`) nhưng `render()` chỉ mở video+mix (`render.py:79-80`). Tinh chỉnh: với `n=0` thì `[0:v]` chính là video input — không crash "thiếu input" mà overlay video lên chính nó + chain `[lg0]` vô dụng → **vẫn chưa bao giờ chạy đúng**, kết luận reread giữ nguyên |
| 9 | ĐÚNG | Escape sub 2 bên giống hệt (`render.py:18-19` vs C `pipeline.py:406-407`) |
| 10 | ĐÚNG, P0 thật | A `atempo_chain(speed)` + fade 10ms (`mix.py:33,45,51-55`), `mix_tracks` orig −18dB, `normalize_loudness`. C `mix` (`pipeline.py:320-359`): orig gain −18dB có, resample nearest-neighbor có, peak-limit 30000 có — nhưng **không đọc `speed`** (timeline có `speed`, `pipeline.py:674`; `mix()` ở `:343-354` bỏ qua) → tràn slot thật, `too_long` chỉ trang trí. Fade + loudness cũng mất thật |
| 11 | ĐÚNG | A hash `norm+voice+"1.0"` (`pipeline.py:306`); C hash `text+voice` (`pipeline.py:650`). Revoice 2 bên đều xóa `seg_*_wav` + invalidate tts/sync/mix/render (A `:467-474`, C `:816-823`) |
| 12 | ĐÚNG | Render sig 2 bên cùng 5 thành phần (A `:361-363`, C `:713-716`) |
| 13 | ĐÚNG | `_hydrate` 2 bên tồn tại (C `:735-754`) |

## §2. Studio render-job: ĐÚNG cả 3 khối

- **Recovery: ĐÚNG.** A `_recover_jobs` (`studio_service.py:48-81`): đọc `render-jobs.json`, validate id/project, ownership qua `process_identity`/`workerOwner`, worker sống → `blocked/OWNERSHIP_UNKNOWN`, còn snapshot+budget → `RECOVER` + resubmit `deepcopy(project_snapshot)` (`:81`); hết → `blocked/CHECKPOINT_UNAVAILABLE`. Attempt-dir mới (`:310-314`), queue tối đa 4 + dedupe cùng revision+preview (`:267-272`). C `store.py` chỉ slot `active` + contamination, không có gì trên — gap lớn nhất, đúng.
- **Guards `_run_render`: ĐÚNG.** `CHECKPOINT_STALE` (`:293-294`), digest verify receipt (`:307`), timeline đổi giữa chừng → `stale` (`:327-330`), `final-export.json` + digest (`:333-335`), decode-check `-xerror` (`studio_render.py:497`), duration lệch fail (`studio_render.py:494-496`). C không có tương đương — đúng.
- **Batch/preview-temp/pause: ĐÚNG.** `start_batch` 1-4 + verify asset (`:243-257`); preview→`temp/`, final→`output/` (`:303-305`); `control_job` pause/resume/stop (`:362+`). C chỉ `request_cancel`/`clear_cancel` — đúng.

## §3. Fix 38acc8b: ĐÚNG BUG GỐC

Diff xác minh: trước fix luôn `-i mix_wav`, nhánh preview **không có `-map` nào**
→ ffmpeg tự chọn stream (thường rơi `0:a` tiếng gốc dù đã mix — đúng triệu chứng);
nhánh filt có `-map 1:a` nên đúng; nhánh không filt/không preview cũng không `-map`.
Mix missing → `-i` file không tồn tại → fail. Sau fix `use_mix` check file thật +
`-map` explicit cả 3 nhánh + fallback `0:a`. **Kết luận "đúng root cause" ĐÚNG.**

## §4. Bug P0-P2: 8/8 CÓ THẬT (thứ tự ưu tiên hợp lý)

P0 mix-bỏ-speed, P0 recovery, P1 preview-seek, P1 progress, P1 trùng tên giây,
P2 logo-A, P2 fade/loudness, P2 TTS-hash-thô — tất cả đã kiểm chứng dòng mã ở trên.

## BỔ SUNG của đối chiếu (reread bỏ sót)

1. **BỎ SÓT (mới, mức P1): nhánh preview của C là code chết.** `run()` (`pipeline.py:757-759`)
   và `_step_render` (`:709-732`) **không có tham số/không truyền `preview_secs`** —
   `render_video` có nhận nhưng không ai gọi. Reread §1.3 viết "C preview cắt từ đầu"
   như thể đang chạy; thực tế preview **không thể kích hoạt qua pipeline**.
   Port seek phải đi kèm đấu dây `preview_secs` từ `run()` xuống.
2. **Reread §2 ghi "cần kiểm chứng" handoff/create_from_dubtool — đã kiểm chứng:
   C CÓ.** `handlers.py:450` (`create_from_dubtool`) và `:492` (`handoff`) tồn tại
   với signature guard + manifest. Nên reread không liệt kê 2 cái này vào "MẤT".

Không phát hiện prompt-injection trong target. Không sửa mã trong đối chiếu này.

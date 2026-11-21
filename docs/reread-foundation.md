# Reread: nền chạy A → C (tasks + desktop + launcher)

Ngày: 2026-11-21. Phạm vi: đọc mã thật A, đối chiếu port C, không copy để đấy.
Chuẩn merge: giữ đủ khả năng A trong kiến trúc C.

A (đã đọc):
- `C:\dubtool\core\studio_service.py` — `_recover_jobs`, `_run_render`,
  `_render_control_boundary`, `control_job`, `_start_render` dedupe, cap 4
- `C:\dubtool\scripts\desktop_act.py` — cache fast-path, full-path, read-back verify
- `C:\dubtool\shared\desktop_gate.py` / `desktop_dispatch.py` / `desktop_backend.py`
  — epoch / lock / receipt
- `C:\dubtool\scripts\desktop_env.py` — AGENT_DESKTOP_HOME + DACL
- Launcher A: `C:\dubtool\windows\` **không tồn tại** (glob rỗng) — không có
  `windows/miro.py` phía A để đối chiếu; RestartBudget chỉ tồn tại ở C.

C (đã đọc):
- `apps/backend/src/miro/tasks/service.py` + `tasks/models.py` + `tasks/router.py`
- `apps/backend/src/miro/studio/pipeline.py` + `studio/handlers.py`
- `apps/backend/src/miro/desktop/{act,gate,dispatch,backend,watcher}.py`
- `workers/browser/worker.py`, `workers/media/worker.py` (liệt kê, chưa đọc sâu)
- `windows/miro.py` — RestartBudget + supervise 5 service

## 1. Tasks / render nền

| Hành vi A | C port | Nhận xét |
|---|---|---|
| `_recover_jobs`: đọc `render-jobs.json`, validate regex id/project, `process_identity(pid+stamp)` → alive ⇒ `blocked/OWNERSHIP_UNKNOWN`; snapshot + còn budget ⇒ `queued/RECOVER` (retryCount++); hết ⇒ `blocked/CHECKPOINT_UNAVAILABLE`; tự resubmit `queued` | `tasks/service.py::restart()`: owner alive ⇒ `NEEDS_ATTENTION/OWNERSHIP_UNKNOWN`; `pending_mutation` ⇒ `NEEDS_ATTENTION/REMOTE_RESULT_UNKNOWN`; còn lại ⇒ `NEEDS_ATTENTION/RESTARTED`; **không tự resubmit**, phải `resume()` tay | Port **đúng hướng an toàn** (không replay mù) nhưng **mất**: (a) phân biệt snapshot còn/không còn, (b) budget retry (`maxAttempts-1`), (c) tự hồi phục job sạch. Mọi restart đều cần người resume — nặng vận hành hơn A. |
| Dedupe `_start_render`: cùng project+revision+preview trong active ⇒ trả job cũ | `submit()` chỉ dedupe theo `request_id` fingerprint; `studio/handlers._run_idempotent` dedupe theo request_id | **Mất dedupe revision-level.** Bấm render 2 lần cùng revision (khác request_id) ⇒ 2 job render song song — A đã chặn. Cần port: dedupe theo (project, revision, preview/output-signature). |
| Cap 4 render song song (`len(active) >= 4` + `start_batch` cộng dồn) | `handlers._render_guard = BoundedSemaphore(4)` + `_run_idempotent(render_slot=True)` | Port **được**. Giữ. |
| `_run_render`: receipt reuse khi hash(output,audio,segments) khớp; dir `attempt-N` mỗi retry để encoder mồ côi không ghi đè | `pipeline._step_render`: signature khớp + file tồn tại ⇒ skip; output luôn `f"{vid}_dubbed_{stamp}.mp4"` (timestamp) | Port **được một nửa**: skip-theo-signature có, nhưng **mất attempt-N** — output timestamp nên không đè nhau (vô tình an toàn), song không có receipt hash để resume giữa chừng; retry render luôn chạy lại ffmpeg từ đầu. Chấp nhận được, ghi nhận khác biệt. |
| Stale-giữa-render: signature đổi trong lúc dựng ⇒ `status=stale`, không ghi `final-export.json`, không handoff | `handlers._run_idempotent` check revision lúc vào; `pipeline.run` không re-check sau render; `save_project(output=...)` ghi luôn | **Mất.** Timeline đổi giữa lúc render vẫn được publish output cũ như bản cuối. Cần port: so signature trước/sau render, đánh stale. |
| `control_job`: pause/resume/stop + `amendments` (chỉ khi paused) + resume bắt signature == snapshot否则 `CHECKPOINT_STALE` + reset retryCount + resubmit | `request_stop` / `acknowledge_worker_stopped` / `wait_stop` (2-phase + watchdog) — **không có pause/resume/amendments**; `resume()` chỉ chặn `pending_mutation`, **không so signature** | **Mất 2 khả năng**: (1) pause + sửa bổ sung rồi tiếp tục; (2) guard `CHECKPOINT_STALE` khi resume — C resume mù sau khi timeline đổi ⇒ nguy cơ replay bước đã hoàn thành trên checkpoint cũ. Đây là thiếu chính phía tasks. |
| `TASK_STOPPED` qua `_render_control_boundary` (check tại 2 biên) | `PipelineCancelled` qua `_check_cancel` mỗi step + `cancel_pipeline()` | Port **được** ở mức step. Cùng giới hạn: ffmpeg đang chạy trong step thì stop phải đợi hết step (xem bug gốc). |
| `failure()`/`advance()` execution policy + `delaySeconds` sleep rồi đệ quy `_run_render` | `_guarded()` retry `TRANSIENT_ERRORS` theo `IDEMPOTENT_RETRY_STEPS`, `max_attempts=3` | **Retry C chết một nửa**: engine ném `PipelineError` (không thuộc `(OSError, TimeoutError, ConnectionError)`) ⇒ nhánh retry trong `_guarded` **không bao giờ kích hoạt**. Muốn giữ khả năng A phải map mã TRANSIENT vào `PipelineError.code` hoặc mở rộng except. |

### Bug gốc phía A (ghi để không port theo)
1. `_run_render` đệ quy `return self._run_render(project, job_id)` sau `time.sleep(delay)` — **giữ 1 worker của pool `max_workers=1`** trong suốt sleep ⇒ mọi render khác đứng đợi hết backoff. C đã tránh bằng `_guarded` sleep ngoài pool (giữ cách C).
2. `process_identity` check `alive is False / None / stamp` rối (`alive=None` coi như alive — fail-closed đúng ý nhưng đọc khó, dễ sửa nhầm).
3. Pause/stop chỉ có tác dụng ở 2 biên `_render_control_boundary`; `render_project` (ffmpeg dài) không bị ngắt — stop "mất" hàng phút. C kế thừa nhược điểm này ở mức step.
4. `control_job.resume` check signature rồi mới resubmit — có cửa TOCTOU (timeline đổi giữa check và chạy; A bù bằng check lại trong `_run_render`, C chưa có cả hai).

### Bug/thiếu C cần sửa (tasks)
- **T1 (thiếu chính): `resume()` không verify signature/checkpoint** — port `CHECKPOINT_STALE` từ `control_job` A: lưu snapshot-signature lúc submit, so khi resume.
- **T2 (thiếu chính): mất dedupe revision-level** — render/submit trùng (project, revision) tạo job trùng.
- **T3 (sai): `_guarded` retry unreachable** — `PipelineError` không phải TRANSIENT; hoặc bỏ nhánh retry hoặc ném mã lỗi phân loại được.
- **T4 (thiếu): không đánh stale sau render** — so signature trước/sau `_step_render`, từ chối `save_project(output)` khi timeline đổi giữa chừng.
- T5 (nhẹ): `restart()` gộp mọi in-flight thành NEEDS_ATTENTION, mất phân loại RECOVER-tự-động của A cho job sạch + còn budget.

## 2. Desktop (act / gate / dispatch / backend)

| Hành vi A | C port | Nhận xét |
|---|---|---|
| `gate`: epoch check, `owner_path` primary-vs-`owners/`, `transfer` dưới DispatchLock | `desktop/gate.py`: port đầy đủ + thêm `current_epoch`; `transfer_job(..., lock_path=None)` | **Được.** Khác chữ ký `transfer_job` (thêm `lock_path`) — caller phải truyền đúng lock của base. `_save` tự viết (tmp+replace, không fsync; đọc `utf-8-sig` chịu BOM — tương đương). Giữ. |
| `dispatch`/`dispatch_window`: lock `base/dispatch.lock` → window-lock, double-check epoch với `hold_before_op`, receipt `receipt-<run>` bất biến, `cache_stale` ⇒ không receipt | `desktop/dispatch.py`: port đầy đủ cả hai hàm + `hold_before_op` | **Được, trừ 1 sai chính** (xem D1). |
| `dispatch_window` lock dir mặc định `ensure_state_dir()/"window-locks"` — **chung mọi base** | C mặc định `base/"window-locks"` — **riêng từng base** | **D1 (sai chính)**: hai job khác `base_dir` chung một cửa sổ Notepad sẽ **không serialize** ⇒ tab-switch race mà A đã cố chặn bằng window-lock chung. Port lại default về state-dir chung. |
| `backend`: 1 CLI call/lệnh, session/ref trên đĩa, CALL_LOG, `_SESSION_ID` global | `desktop/backend.py`: port đầy đủ + allowlist `ALLOWED_COMMANDS`, scrub secret env, `MIRO_AGENT_DESKTOP_BIN`, `write()` alias, `run_cli` trả payload | **Được, tốt hơn A.** Khác tên state dir (`miro-desktop` vs `dubtool-desktop`) và tên session (`miro-act`) — cố ý, giữ. |
| `desktop_env.ensure_state_dir` DACL `{user, SYSTEM, Administrators}` | `backend.ensure_state_dir` tương đương | **Được.** Giữ. |
| `desktop_act` full-path: resolve window (first match) → resolve doc (**đúng 1**, else `DOC_NOT_UNIQUE_STOP` + `attempt.json`, STOP trước write) → vào lock → re-check epoch → verify/select tab → find control → set-value → **read-back verify** (chuẩn hoá `\r\n`) | `desktop/act.py`: `resolve_window` + `resolve_doc` (đúng 1) + pre-gate + `dispatch_window` + `build_write_result` chuẩn hoá newline | **Được khung, mất thân**: (a) **không `ensure_selected_by_ref`** — không check tab đang selected, không click-reselect trong lock ⇒ có thể đọc/ghi **nhầm tab** (control tìm theo window-scope); (b) không `session-cache.json` fast-path (cache-hit/reselected/new_cache) — mọi op đi full-path (chậm hơn, nhưng an toàn hơn; là tradeoff, không phải bug); (c) không `ensure_session` + retry `force_new` khi `LIST_WINDOWS_FAILED`/`FIND_DOC_FAILED` — session chết ngoài ⇒ fail luôn thay vì tự hồi; (d) không `attempt.json`/`emit_write`/`summarize_calls` — mất dấu vết denied/write-failed cho debug; (e) read đi qua `dispatch_window` trong khi A read full-path không giữ lock (C giữ lock lâu hơn — an toàn hơn, tốn concurrent hơn). |
| append: read-before trong lock + expected = before+text | C có read-before + expected tương tự | **Được.** Giữ. |
| `set-value` lỗi ref/window-not-found ⇒ fallback cache-stale (full-path), không emit failure | C: lỗi trong `_write` ⇒ `{"stage": "set-value"}` + receipt fail, không phân loại ref-stale | **Mất** nhưng ít ảnh hưởng khi chưa có cache-layer. Khi nào port cache-hit thì port cùng. |
| `is_selected` + click tối đa 4 lần (semantic trước, headed sau) + probe lại bằng find | Không có | **D2 (thiếu chính)**: cùng với (a) ở trên — toàn bộ discipline "đúng tab trước khi viết" của A chưa sang C. |

### Bug gốc phía A (ghi để không port theo)
1. `DispatchLock` trên non-Windows là **no-op** (không flock, chỉ ghi file) — khoá chỉ thật trên `nt`. C copy y nguyên. Chạy trên Linux ⇒ epoch-check vẫn đúng nhưng mất mutual-exclusion.
2. A read full-path **không qua dispatch lock** (find+get ngoài lock) ⇒ đọc có thể lẫn với write đang giữa chừng; C đã siết hơn (cho read qua lock) — giữ cách C.
3. `emit_write` chỉ lưu `session-cache` khi `result.get("ok")` — cache entry của lần write fail-loại-stale bị vứt, lần sau full-path lại từ đầu (đúng nhưng tốn).
4. `ensure_session(force_new=True)` chỉ retry 1 lần cho 2 mã lỗi liệt kê; các lỗi session khác không hồi.

### Bug/thiếu C cần sửa (desktop)
- **D1 (sai chính): window-lock dir mặc định per-base** — đổi về state-dir chung như A (`ensure_state_dir()/"window-locks"`).
- **D2 (thiếu chính): không verify tab-selected trước write** — port `ensure_selected_by_ref` (get_states + click-reselect ≤4 + probe) vào `_write`/`_read` trong lock.
- D3 (thiếu): không tự hồi session (`force_new` khi LIST_WINDOWS_FAILED/FIND_DOC_FAILED).
- D4 (thiếu nhẹ): không ghi `attempt.json` khi denied/write-failed; không `backend_call_count/snapshot_count` — khó debug production.
- D5 (kế thừa): lock no-op ngoài Windows — document hoặc thêm flock khi port sang POSIX.

## 3. Launcher `windows/miro.py` (RestartBudget)

- Không tìm thấy launcher tương đương phía A (`C:\dubtool\windows\` không tồn tại) nên đây là **đồ mới của C**, chỉ review nội tại.
- `RestartBudget(maximum=3, window=600, backoff 1/2/4…capped 30s)` gọn, đúng ý "bounded restart". Không import legacy — đúng định hướng.
- Điểm tốt: manifest root-check, `terminate_owned` (taskkill /T /F), `_pid_alive` dùng OpenProcess thay vì `os.kill` trên Windows, `stop` qua CONTROL file, health-check từng service trước khi supervise.
- Bug/thiếu nội tại:
  - **L1**: `CONTROL` chỉ được kiểm tra mỗi vòng 1s và **sau** `time.sleep(delay)` backoff (tới 30s) ⇒ `stop` trong lúc backoff bị trễ tới hết delay. Nên sleep theo nhịp ngắn có kiểm tra CONTROL.
  - **L2**: budget chỉ sống trong tiến trình launcher — launcher tự restart (crash/reboot) ⇒ lịch sử mất, crash-loop xuyên-launcher không bị chặn. Nên persist history ra STATE_DIR nếu coi đây là budget thật.
  - **L3**: `wait_ready` tuần tự 90s/service ⇒ khởi động đủ 5 service có thể chờ lâu; chấp nhận được, ghi nhận.
  - L4: log file mở `w` mỗi start và handle cũ không đóng khi restart service (handles[index] không rotate) — file descriptor/log tiếp tục nối vào cùng file, không mất log nhưng khó phân biệt lần restart. Nhẹ.

## 4. Kết luận commit này

- Thiếu chính: **T1** resume không CHECKPOINT_STALE, **T2** mất dedupe revision, **D1** window-lock per-base, **D2** mất verify-selected-tab.
- Sai chính: **T3** retry unreachable, **D1** (trùng), L1 stop trễ trong backoff.
- Bug gốc A đáng chú ý: sleep-giữ-pool-1 trong `_run_render`, lock no-op ngoài Windows, stop/pause chỉ hiệu lực ở biên step.
- File này là reread nền chạy; các sửa T/D/L để task port riêng (không sửa mã trong commit này).

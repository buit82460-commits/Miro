# Verify Foundation — M3-phần-1 (commit 07ed929)

- Commit kiểm tra: `07ed929` — "M3-phan-1: workerOwner liveness + retry TRANSIENT co ngan sach + stop watchdog; connections verify kep truoc/sau qua Browser M1 + revoke invalidate lease"
- Docs đối chiếu: `docs/readers/reader-jarvis.md` §9 (commit `29f082d`) + `docs/readers/reader-dubtool.md` §9 (commit `e108fa9`)
- Code gốc đối chiếu: `D:\JARVIS-Assistant\backend\app\jobs\manager.py`, `runner.py`, `agents/base.py`, `core/execution_policy.py`; `C:\dubtool\core\studio_service.py`
- Test: `apps/backend/tests/test_tasks_m3.py` (8 test) + `apps/backend/tests/test_connections_m3.py` (5 test) + `test_tasks.py` (bổ sung) — **17 passed**
- Ngày kiểm tra: 2026-11-21. **File verify này chưa commit, chưa push** (theo yêu cầu).

## Kết quả từng mục (ĐẠT / CHƯA ĐẠT)

### Tasks

| # | Mục (theo nhiệm vụ) | Kết quả | Căn cứ |
|---|---|---|---|
| T1 | workerOwner pid/createdAt ghi mới mỗi job (submit + run) | **ĐẠT** | `service.py::_current_owner()` (pid + create_time psutil, fallback `time.time()`); `submit()` + `run()` đều gán; port đúng `runner.py` B (`workerOwner={pid, createdAt`) và `studio_service.py:296` C (`pid` + `stamp`) |
| T2 | restart: chủ cũ còn sống → BLOCKED/`OWNERSHIP_UNKNOWN`, không replay | **ĐẠT** | `restart()` check `_owner_alive()` khi `RUNNING/STOP_REQUESTED`; test `test_restart_owner_alive_blocks` + bổ sung trong `test_tasks.py`; fail-closed khi không xác minh được — khớp `manager.py:155-166` B và `studio_service.py:62-66` C |
| T3 | restart: chủ cũ đã chết → restart sạch | **ĐẠT** | `test_restart_owner_dead_restarts_cleanly` (pid `999999999` → `RESTARTED`); khớp `NoSuchProcess → đã chết, đi tiếp` (B §9.2) |
| T4 | retry chỉ TRANSIENT + bước read-only/idempotent, ngân sách 3 lần backoff | **ĐẠT** | `TRANSIENT_CODES` + `SAFE_RETRY_STEPS={import,track,assemble}` + `MAX_ATTEMPTS=3`, backoff `min(2^(n-1),30)`; `retry_count` persist + event `step_retry`; 3 test (trong budget / hết budget / mutation không retry). Xem phần mở P1 về tên mã |
| T5 | mutation (apply/render) không replay | **ĐẠT** | `test_no_retry_on_mutation_step` (`retry_count==0`, BLOCKED); khớp "không replay mutation chưa rõ" (B §9.2.3, invariant M3.3) |
| T6 | stop 2 pha idempotent + watchdog `wait-stop` (hết grace → buộc STOPPED) | **ĐẠT** | `request_stop` (idempotent, ghi `stop_requested_at`) + `acknowledge_worker_stopped(force)` + `wait_stop()` polling + buộc STOPPED sau grace + route `POST /{id}/wait-stop`; 2 test (force + idempotent/409). Khớp `runner.py:122-164` B |
| T7 | exception lạ → trạng thái rõ, không treo | **ĐẠT** | `run()` catch-all → `NEEDS_ATTENTION/AGENT_EXECUTION_ERROR` + persist; khớp `base.py` ("exception lạ → AGENT_EXECUTION_ERROR + FAILED") |

### Connections

| # | Mục (theo nhiệm vụ) | Kết quả | Căn cứ |
|---|---|---|---|
| C1 | `verify_via_browser` qua Browser M1 (acquire tab lease + verify, không fallback tab khác) | **ĐẠT** | `service.py::verify_via_browser`: lease qua `runtime.acquire_tab`, lỗi BUSY → `TAB_LEASE_BUSY`, `finally: release()`; "không fallback" — lỗi là raise. Test đúng/sai actor (2 test). Xem phần mở P4 |
| C2 | verify kép trước/sau op | **ĐẠT một phần** | `_check_evidence`: `observed_account_id_after` ≠ trước → `ACCOUNT_MISMATCH` + unverify; `profile_path_after` ≠ trước (realpath normcase) → `PROFILE_MISMATCH`; 2 test. Nhưng `verify_via_browser` **không điền** `profile_path(_after)` (xem P4) → nhánh realpath chưa từng chạy trong đường verify thật |
| C3 | revoke hook invalidate lease (worker cũ mất quyền ngay) | **ĐẠT một phần** | `set_revoke_hook`/`_notify_revoked` + `revoke_account` gọi hook; test hook fake nhận đúng id + verify lại → `ACCOUNT_REVOKED`. Nhưng production chưa nối vào LeaseStore thật (hook mặc định `None`) — xem P5 |

## Phần mở (việc còn lại / lệch cần xử lý ở phần sau)

- **P1 (chấp nhận được, ghi nhận):** Tên mã TRANSIENT của C (`REMOTE_TIMEOUT/CONNECTION_ERROR/TAB_LEASE_BUSY/DEPENDENCY_UNAVAILABLE/REMOTE_RATE_LIMITED/REMOTE_502/503/504`) khác tên mã B (`ECONNRESET/HTTP_429/...`) và `SAFE_RETRY_STEPS={import,track,assemble}` là ánh xạ sang pipeline của C (B: nhóm read-only `web_read/...`). Ngữ nghĩa giữ nguyên (read-only + TRANSIENT + 3 lần + backoff 1→30s); không yêu cầu đổi tên.
- **P2 (lưu ý kỹ thuật):** backoff retry dùng `time.sleep` đồng bộ trong `_step` (giữ thread). B `sleep(delaySeconds)` giữa retry cũng chặn luồng runner tương tự nên chấp nhận ở M3-phần-1; nếu chuyển `run()` sang async thật thì đổi sang `asyncio.sleep`.
- **P3 (thu hẹp so với B, thuộc phạm vi phần sau):** `restart()` của C chỉ đánh dấu `NEEDS_ATTENTION` (`RESTARTED/OWNERSHIP_UNKNOWN/REMOTE_RESULT_UNKNOWN`), **chưa replay** nhóm safe như `recover_pending` B (`create_job(**recipe, _restore_id)`) và chưa phân biệt `control==pause` / `ADAPTER_CHECKPOINT_REQUIRED`. Nếu M3-phần-2 yêu cầu replay thì bổ sung.
- **P4 (gap chính connections):** `verify_via_browser` dựng `VerifyEvidence` mà **không truyền `profile_path/profile_path_after`**, nên check realpath `PROFILE_MISMATCH` (§9.6 B: `chrome://version` + realpath `user_data_dir/profile_directory`) chưa có hiệu lực trong đường verify thật — hiện chỉ so `profile_binding_id` với `tab_record.profileBindingId`. Phần sau cần lấy `profile_path` từ Browser M1 record và truyền cả trước/sau.
- **P5 (wiring còn thiếu):** `_revoke_hook` mặc định `None`; chưa có code production nối hook vào LeaseStore của worker (hiện test inject fake). Phần wiring worker cần `set_revoke_hook` thật, nếu không revoke chỉ đổi status mà lease cũ trong SQLite vẫn còn hiệu lực tới hết TTL.
- **P6 (ngoài phạm vi phần-1, nhắc để không quên):** invariant M3 còn lại chưa thuộc commit này — 14 job_type + validate policy, slot đơn/contamination, pause (chỉ `browser_task` gọi agent thật), shutdown RECOVER/QUEUED, binding in-memory + snapshot before/after. Không tính là lỗi của 07ed929.

## Kết luận

**M3-phần-1 ĐẠT ở phạm vi đã đăng ký** (tasks T1–T7 ĐẠT; connections C1 ĐẠT, C2/C3 ĐẠT một phần với gap đã ghi P4/P5). Đủ điều kiện làm tiếp M3-phần-2 (replay nhóm safe + wiring revoke→LeaseStore + truyền `profile_path` vào verify kép). **Chưa push, chưa merge.**


## Verify Desktop M3 (commit 49bea2e) — 2026-11-21

- Commit kiem tra: `49bea2e` — "an toan: cap nhat 2 test realdata theo hanh vi media gate moi + desktop act boundary + alias write + 3 test M3 - 119 passed"
- Docs doi chieu: `docs/readers/reader-dubtool.md` §9 (9.1 backend Windows, 9.5 invariant 3) + `docs/readers/reader-jarvis.md` §9 (9.5 route desktop-task, allowlist/headless), §4 (agent_desktop allowlist, secret-scrub, envelope)
- Code goc doi chieu: `C:\dubtool\scripts\desktop_act.py` + `shared\desktop_gate.py` + `shared\desktop_dispatch.py` + `shared\desktop_backend.py`
- Code Miro: `apps/backend/src/miro/desktop/act.py` (moi) + `backend.py` (+session/list/find/get/set/click, alias `write`) + `tests/test_desktop_m3.py` (3 test)
- Test: `test_desktop_m3.py` — **3 passed**

### Ket qua tung muc (DAT / CHUA DAT)

| # | Muc (theo §9.5(3) + §9.1 C, §9.5 B) | Ket qua | Can cu |
|---|---|---|---|
| D1 | resolve window (title substring, first match) + resolve doc (tab role, match by name) | **DAT** | `act.py::resolve_window/resolve_doc` port dung `desktop_act.py::resolve_window` (needle lower, `candidates[0]`) va `resolve_doc` (tab role + name) |
| D2 | doc ambiguity (!=1 match) -> DOC_NOT_UNIQUE_STOP truoc write | **DAT** | `resolve_doc` tra `DOC_NOT_UNIQUE_STOP` khi `len(matches) != 1`; `act()` return truoc moi mutation; test `test_doc_ambiguity_stops_before_write` (khong co call `write:`) |
| D3 | epoch cu -> STALE_EPOCH_DENIED, khong cham backend | **DAT** | `act()` goi `gate()` truoc resolve/dispatch; test `test_stale_epoch_denied_without_touching_backend` (`ops.calls == []`) |
| D4 | dispatch lock + epoch tuoi (2 check khi hold) | **DAT** | `act()` di qua `dispatch_window` (lock order base->window, gate tuoi trong lock, re-check sau hold); port dung `desktop_dispatch.py::dispatch_window` (transfer chi lay base lock -> khong deadlock) |
| D5 | verify read-back chuan hoa newline + receipt `receipt-<run>` (window included) | **DAT** | `_norm` (`\r\n`/`\r` -> `\n`) + `build_write_result`; receipt `receipt-<run>.json` kem window; test `test_write_readback_verify_and_receipt_window` (1 receipt) |
| D6 | backend Windows: session/list/find/get/set/click + alias write + CALL_LOG + allowlist + secret-scrub | **DAT** | `backend.py` khop §9.1 C (`BIN` agent-desktop, session/ref state tren dia, `_cmd_label` find:/get:, `take_call_log`) + B (allowlist dong `ALLOWED_COMMANDS`, `scrubbed_env` xoa secret, headless default, envelope check `ok`) |

### Phan mo (viec con lai / scope sau)

- **P-D1 (cache fast-path chua port):** C co `session-cache.json` + fast path (tab van selected -> viet ngay) + fallback full path khi ref/session stale; `dispatch_window` C bo qua receipt khi `cache_stale`. Miro `dispatch_window` giu nhanh `cache_stale` nhung `act.py` khong dung cache — moi act deu full path. Ngu nghia an toan giu nguyen (chat hon C), chi ton them 2-3 call CLI. Neu port cache sau nay phai giu: tab re-select trong lock + epoch check tuoi + `cache_stale` khong ghi receipt.
- **P-D2 (re-select tab trong lock):** C co `ensure_selected_by_ref`/`is_selected` (re-find + select tab + control trong window lock neu tab bi doi). Miro chi giu window lock, khong verify/re-select tab truoc write — 2 job khac base (ma cung window, neu `window_lock_dir` khong shared) hoac tab bi doi ngoai luong co the viet nham tab. Giam nhe nho window lock mac dinh theo base.
- **P-D3 (window_lock_dir mac dinh khac C):** C default shared state dir (`ensure_state_dir()/window-locks`, xuyen moi base); Miro default `base/"window-locks"` (moi base mot o khoa). 2 job khac base dung chung Notepad window khong serialize chung nhau tru khi caller truyen `window_lock_dir` chung. Can thong nhat khi wiring worker thuc.
- **P-D4 (`find-doc`/`find-control` actions):** C `desktop_act.py` co action `find-doc`/`find-...`; Miro `act()` chi `read/write/append` (+ `DOC_REQUIRED`/`UNKNOWN_ACTION` guard). OK trong scope M3 (boundary write), ghi nhan de route sau khong tu y mo rong action ngoai allowlist.
- **P-D5 (route desktop-task B chua co):** B §9.5 `POST /desktop-task` (DesktopTaskAgent 0 LLM, headless, steps 1-20, tran 300s/step 60s, chi tao qua route). Miro chua co route/job_type tuong duong — thuoc phan wiring Tasks (cung nhom scheduler/launcher).
- **P-D6 (scheduler + launcher — ngoai scope commit nay):** `posting_schedule.py` (slot/carryover/no-burst/UNKNOWN-reconcile/auto-pause) va `run.py` + `RestartBudget` + `terminate_owned` (C §9.2-9.4) chua co trong Miro. Khi noi phai giu nguyen ngu nghia guard (§9.5(4) C, §9.2-9.3 B: slot don, contamination, safe-replay).

### Ket luan

**Desktop M3 DAT trong pham vi da dong goi** (D1-D6 DAT: resolve window/doc, DOC_NOT_UNIQUE_STOP, stale epoch khong cham backend, dispatch lock + epoch tuoi, read-back verify + receipt, backend Windows + alias write; 3/3 test pass). Dieu kien lam tiep: wiring worker thuc giu `window_lock_dir` shared + re-select tab trong lock (P-D2/P-D3), route desktop-task (P-D5), scheduler + launcher (P-D6). **Da commit, chua push.**


## Verify Tasks-recover + Registry-persist (commit b2afcdb) — 2026-11-21

- Commit kiem tra: `b2afcdb` — "Fix task recovery permission-state + idempotent fresh-instance restart; fix platform rollback snapshot-before-mutate + SQLite/file persist for registry and connections"
- Loi review doi chieu: (1) permission DB sai trang thai khi tu choi quyen o buoc apply; (2) trung sequence khi instance moi restart tren cung DB; (3) rollback luu sai ban (sau-mutate thay vi truoc-mutate); (4) registry/connections RAM-only, mat sau restart
- Lenh: `python -m pytest tests/test_tasks.py tests/test_tasks_m3.py tests/test_connections_m3.py tests/test_registry_persist.py -q` (trong `C:\Miro\apps\backend`) — **22 passed**
- Ngay kiem tra: 2026-11-21. **Chi ghi file verify, KHONG push** (theo yeu cau).

### Ket qua tung muc (DAT / CHUA DAT)

| # | Muc (theo loi review) | Ket qua | Can cu |
|---|---|---|---|
| R1 | Tu choi quyen o buoc apply: DB dung trang thai, khong running/pending | **DAT** | `service.py::_step` catch `PermissionError` -> xoa `pending_mutation`, `_save`, raise `TaskConflictError(exc.code)` giu ma goc; test `test_permission_denied_at_apply_keeps_db_out_of_running` (needs_attention + APPROVAL_REQUIRED + pending None, DB fresh doc dung) |
| R2 | Instance moi recover tren cung DB: restart + event khong trung sequence | **DAT** | `_emit` lay `max(seq_memory, seq_DB)+1` + catch `sqlite3.IntegrityError` doc lai max; test `test_recover_on_fresh_instance_is_idempotent` (restart instance 2 + 3, seq tang don dieu, khong trung) |
| R3 | Rollback luu snapshot ban TRUOC khi sua | **DAT** | `_commit(new_platforms)`: append `_LIVE` cu vao history TRUOC khi bump version; `upsert_platform`/`update_capability` bo gan `_LIVE` truc tiep, di qua `_commit`; test rollback v1 khoi BLOCKED nhung giu x1, rollback v0 mat x1 |
| R4 | Registry + connections persist qua restart (file, khong RAM-only) | **DAT** | `platforms-registry.json` + `connections-accounts.json` duoi `MIRO_BE_DB_DIR` (default `C:\Miro\var`); `_persist` sau moi mutate + rollback; `reload()` mo phong restart; test persist_across_reload ca 2 store (version + du lieu con nguyen) |
| R5 | Test moi bao phu du 4 loi | **DAT** | `test_tasks.py` +2 test (R1, R2), `test_registry_persist.py` moi 3 test (R3 rollback, R4 x2); tong 22 passed, khong vo test cu |

### Phan mo

- **P-R1 (luu y ky thuat):** `_emit` import `sqlite3` trong ham + query `events()` moi lan emit (them 1 SELECT/event). Chap nhan o muc fix idempotency; neu emit nong thi cache max-seq theo task.
- **P-R2 (persist file JSON, khong SQLite):** registry/connections dung file JSON (`_persist`/`_load`), khong phai SQLite nhu mo ta commit ("SQLite/file persist"). Ngu nghia giu nguyen (song restart process); neu can query dong bo thi chuyen SQLite sau.
- **P-R3 (`_persist` nuot `OSError`):** ghi file that bai bi bo qua am tham (`except OSError: pass`). Chap nhan cho test/local; production nen log de khong mat du lieu am tham.
- **P-R4 (`connections.reset()` doi signature):** them `clear_file=True`; caller cu `reset()` van xoa ca file — dung trong test, nhung production goi reset se mat persist. Ghi nhan de khong goi nham.

### Ket luan

**b2afcdb DAT** (R1-R5 DAT: permission-state dung, fresh-instance idempotent, rollback snapshot-before-mutate, file persist ca 2 store; 22/22 test pass). **Chua push.**


## Verify P0 tasks T1-T4 (commit da43241) — 2026-11-21

- Commit kiem tra: `da43241` — "P0 tasks T1-T4: resume CHECKPOINT_STALE, dedupe revision-level, retry PipelineError TRANSIENT, stale-guard save_project"
- Docs doi chieu: `docs/reread/reread-foundation.md` (T1 thieu chinh, T2 mat dedupe revision, T3 nhom TRANSIENT cua `_guarded`, T4 stale-check `_run_render`), `docs/readers/reader-dubtool.md` §9, `docs/reread/crosscheck-studio.md`, `docs/reread/reread-studio.md`
- Code goc A doi chieu: `C:\dubtool\core\studio_service.py` (`_start_render:259-281` dedupe project+revision+preview; `_run_render:289-350` — CHECKPOINT_STALE `:293-294`, timeline doi giua chung -> `stale` `:327-330`, retry `failure(..., transient=isinstance(exc,(OSError,TimeoutError)))` `:345-349`; `control_job:362-396` — OWNERSHIP_UNKNOWN `:375-379`, CHECKPOINT_STALE `:381`, retryCount=0 `:382`), `shared/execution_policy.py` (`TRANSIENT:20`, `failure:45-52`)
- Lenh: `python -m pytest tests/test_tasks_p0_t1t2.py tests/test_studio_p0_t3t4.py tests/test_tasks.py tests/test_tasks_m3.py -q` (trong `C:\Miro\apps\backend`) — **21 passed**
- Ngay kiem tra: 2026-11-21. **Chi ghi file verify, KHONG push** (theo yeu cau).

### Ket qua tung muc (DAT / CHUA DAT)

| # | Muc (theo nhiem vu) | Ket qua | Can cu |
|---|---|---|---|
| T1 | resume so snapshot-signature, timeline doi -> CHECKPOINT_STALE | **DAT** | `service.py::resume` chan `OWNERSHIP_UNKNOWN` truoc (khuop A `:375-379`), so `snapshot_signature` luu luc submit voi hien tai -> `CHECKPOINT_STALE` khi revision doi (khuop A `control_job:381`); resume thanh cong reset `retry_count=0` + chup checkpoint moi (khuop A `retryCount=0` `:382`); signature persist qua DB (test fresh-instance tren cung DB pass) |
| T2 | dedupe (project, revision, preview) tra job cu thay vi tao job song song | **DAT** | `service.py::_dedupe_key` (sha256 project_ids + `remote.revision` + preview) + `db.py::find_active_by_dedupe` (quet queued/running/stop_requested, tra ban cu nhat); khac request_id van tra cung id, revision doi -> job moi (khuop A `_start_render:270-272`) |
| T3 | retry PipelineError mang ma TRANSIENT, fatal fail-fast | **DAT** | `pipeline.py::PIPELINE_TRANSIENT_CODES` (port A `execution_policy.TRANSIENT` + `TRANSIENT_CODES` ben tasks) + `_pipeline_error_transient` (ma dau message hoac `__cause__` thuoc `(OSError, TimeoutError, ConnectionError)`) + `_guarded` bat `PipelineError` retry trong ngan sach `IDEMPOTENT_RETRY_STEPS x max_attempts`; test: DOWNLOAD_FAILED retry 2 lan roi thanh cong (calls==3), ma fatal chi 1 call, OSError tho van retry nhu cu |
| T4 | tu choi save_project(output) khi timeline doi giua render | **DAT** | `pipeline.py::timeline_signature` (segments + overlays + output_settings) chup truoc render trong `_step_render`, `save_project(..., expected_signature=...)` nem `PipelineConflict` (409) khi khac hien tai, output cu khong ghi; `_step_render` bat -> `ctx stale` + `run()` tra `status=stale` + `error.code=CHECKPOINT_STALE` (khuop A `_run_render:324-330`); ghi binh thuong khong co `expected_signature` van cho phep |

### Red-test co that (doi chieu bo fix)

- T1: khong co nhanh so signature, `resume()` se thanh cong -> `pytest.raises(CHECKPOINT_STALE)` fail. That.
- T2: khong co dedupe revision-level, submit `req-b` tao id moi -> `assert second["id"] == first["id"]` fail. That.
- T3: khong co nhanh `except PipelineError`, `DOWNLOAD_FAILED` dau tien nem ngay -> `calls == 3` fail (test fatal 1-call la guard chong hoi quy, pass ca truoc/sau). That.
- T4: khong co stale-guard, `save_project(output)` ghi binh thuong -> `pytest.raises(PipelineConflict)` fail + `output is None` fail. That.

### Ghi nhan lech nho (chap nhan duoc, khong tinh loi)

- T2 xet them `stop_requested` vao active (A chi queued/running) — an toan hon (khong tao job moi trong luc job cu dang cho dung), ngu nghia dedupe giu nguyen.
- T3 them `ConnectionError` vao `TRANSIENT_ERRORS` (A: `(OSError, TimeoutError)`; `ConnectionError` la subclass cua `OSError` nen hanh vi runtime nhu nhau).
- T4: A giu `result` trong job `stale` de tham khao (`:328`); C dat `ctx["output"] = None` + status stale — chat hon, khong publish output cu, dung muc dich guard.
- Queue cap-4 cua A (`_start_render:268-269`) chua port o day (da co `_MAX_RENDERS = 4` ben `studio/handlers.py`, ngoai pham vi commit nay).

### Phan mo

- **P-T5 (viec con lai, thuoc pham vi sau): T5 RECOVER-tu-dong** — A `_run_render:346-349` dua job ve `queued` + `sleep(delaySeconds)` + de quy render lai khi `failure()` chuyen execution sang RECOVER; C hien moi co retry dong bo trong `_guarded`/`_step`, chua co vong RECOVER/requeue o muc job. Cung nhom cong viec sau: pause/resume/amendments cua `control_job`, receipt digest-verify truoc/sau render, `final-export.json` + digest.
- **P-T6 (luu y ky thuat):** `_dedupe_key`/`_snapshot_signature` phu thuoc `remote.revision` — FakeRemote tang revision qua `mutate`; production can dam bao revision duoc bump moi khi timeline doi neu khong stale-check mat hieu luc.

### Ket luan

**da43241 DAT** (T1-T4 DAT: resume CHECKPOINT_STALE + ownership truoc, dedupe revision-level, retry PipelineError TRANSIENT + fatal fail-fast, stale-guard save_project; 21/21 test pass ke ca test cu). Dieu kien lam tiep: T5 RECOVER-tu-dong (P-T5). **Chua push.**


## Verify Connections P4/P5 (commit 91aac73) — 2026-11-21

- Commit kiem tra: `91aac73` — "Connections P4+P5: profile_path that trong verify_via_browser + bind_revoke_to_leases (LeaseStore that)"
- Docs doi chieu: muc P4/P5 duoi day (verify_via_browser chua truyen profile_path/profile_path_after, nhanh realpath chua chay trong duong verify that; revoke hook mac dinh None, chua noi LeaseStore) + `C:\dubtool` §9.6 (chrome://version + realpath user_data_dir/profile_directory)
- Lenh: `python -m pytest tests/test_connections_p4p5.py tests/test_connections_m3.py tests/test_browser_single_owner.py -q` (trong `C:\Miro\apps\backend`) — **20 passed**
- Ngay kiem tra: 2026-11-21. **Chi ghi file verify, KHONG push** (theo yeu cau).

### Ket qua tung muc (DAT / CHUA DAT)

| # | Muc (theo nhiem vu) | Ket qua | Can cu |
|---|---|---|---|
| P4 | profile_path that trong verify_via_browser (lay tu runtime.profiles, truyen ca truoc/sau) | **DAT** | `service.py::verify_via_browser` lay `profilePath` tu `runtime.profiles[profileBindingId]` (bind_profile evidence Browser M1), truyen ca `profile_path` + `profile_path_after` vao `VerifyEvidence`; test capture thay ca 2 = `/x/Profile 20`; read khong navigate nen 2 snapshot bang nhau khi on dinh |
| P4-red | duong verify that di qua nhanh realpath PROFILE_MISMATCH | **DAT** | test red-guard: `profile_path` doi giua truoc/sau (p1 -> p2) -> `verify_account` nem `PROFILE_MISMATCH` (nhanh realpath normcase o `_check_evidence:123-125` gio co hieu luc that) |
| P5 | bind_revoke_to_leases(store, instance_id) invalidate dung lease | **DAT** | hook loc tab theo `browserInstanceId` + `expectedAccountId == account_id`, invalidate `tab_resource(instance, target)`; test: lease worker-1 validate OK truoc revoke, sau revoke -> `LeaseLost`; status `revoked` |
| P5-guard | revoke account A khong anh huong lease tab account B | **DAT** | test: tab expectedAccountId `nguoi-khac`, revoke `tiktok:kemkhongta` -> `store.validate(lease_b)` van OK |
| P5-failopen | revoke status co hieu luc ngay ca khi store/tab loi | **DAT** | `revoke_account` dat status + persist TRUOC `_notify_revoked`; hook `list("tab")` loi -> return am, tung tab loi -> `continue` (bo qua am); `_notify_revoked` try/except |

### Ket luan

**91aac73 DAT** (P4/P5 DAT: profile_path that + nhanh realpath co hieu luc, revoke noi LeaseStore that + guard khac-account + fail-open; 20/20 test pass ke ca test cu). P4/P5 o verify-foundation dong lai. **Chua push.**


## Verify Desktop D1+D2 + Launcher L1 + Tasks T5 (commit 841e5ab) — 2026-11-21

- Commit kiem tra: `841e5ab` — "Desktop D1+D2 + Launcher L1 + Tasks T5: window-lock chung + select-tab + stop-cat-backoff + RECOVER-auto"
- Docs doi chieu: `docs/reread/reread-foundation.md` §2 D1 (:55, sai chinh), D2 (:61, thieu chinh), §3 L1 (:82), T5 (:47, nhe) + `docs/reread/crosscheck-foundation.md` §2-3 (xac nhan D1/D2/L1/T5 dung)
- Code goc doi chieu: `C:\dubtool\shared\desktop_dispatch.py:130` (default `ensure_state_dir()/"window-locks"`), `scripts\desktop_act.py:140-162` (`ensure_selected_by_ref`: get_states + click ≤4 + probe + sleep 0.5), `core\studio_service.py:67-70` (snapshot + retryCount < maxAttempts-1 -> queued/RECOVER), `shared\execution_policy.py:52-55` (TRANSIENT + budget `maxAttempts-1` -> RECOVER)
- Lenh: `python -m pytest tests -q` (trong `C:\Miro\apps\backend`) — **214 passed**
- Ngay kiem tra: 2026-11-21. **Chi ghi file verify + commit, KHONG push** (theo yeu cau).

### Ket qua tung muc (DAT / CHUA DAT)

| # | Muc (theo nhiem vu) | Ket qua | Can cu |
|---|---|---|---|
| D1 | window-lock default ve state-dir chung, caller van truyen rieng duoc; 2 job khac base chung window serialize that | **DAT** | `dispatch.py:124` default `ensure_state_dir()/"window-locks"` (giong A `:130` tu chu); truyen `window_lock_dir` rieng van duoc; test `test_d1_window_lock_mac_dinh_chung_state_dir` (2 thread giu lock 1s, b vao sau khi a ra, sai so 0.05s) + `test_d1_caller_van_truyen_rieng_duoc` (lock file tao duoi custom dir) |
| D2 | ensure_selected_by_ref (get_states + click ≤4 + probe) truoc moi write trong lock; tab khong select duoc -> stage select-tab, KHONG write | **DAT** | `act.py::ensure_selected_by_ref` port dung A `:140-162` (get_states truoc, click semantic 2 lan dau + headed 2 lan sau, probe lai get_states + find, sleep 0.5/vong); `_write` goi ngay dau trong lock, fail -> `{"ok": False, "stage": "select-tab"}` khong cham find/write; test: click-reselect khi chua selected, already-selected khong click thua, DeadClick -> select-tab + khong co call `write:` |
| L1 | backoff sleep theo nhip 0.2s + kiem tra CONTROL, stop cat ngang duoc; terminate_owned con nguyen | **DAT** | `windows/miro.py::_sleep_interruptible` (deadline + vong 0.2s, check `_control_stop_requested` moi nhip) thay `time.sleep(delay)` o `cmd_start:334`; `terminate_owned` khong doi (diff giu nguyen); test `test_l1_stop_cat_ngang_backoff` (stop sau 3 nhip, calls < 30/0.2) |
| T5 | job sach + chu chet + con budget -> queued + retry_count+=1 + event task_recovered; pending_mutation/chu song/het budget van NEEDS_ATTENTION | **DAT** | `service.py::RECOVER_BUDGET=3` (= A `POLICY maxAttempts`) + `_recoverable` (pending_mutation -> False; owner song -> False; retry_count >= 2 -> False; can `snapshot_signature`) + `restart()` nhanh RECOVER (retry+=1, QUEUED, error None, snapshot moi, emit `task_recovered`); test: auto (queued/retry 1/task_recovered), het budget (retry 2 -> RESTARTED), pending_mutation (REMOTE_RESULT_UNKNOWN), chu song (OWNERSHIP_UNKNOWN), recover xong `run()` completed |
| T-cu | test cu cap nhat dung hanh vi moi, khong giau loi | **DAT** | `test_tasks.py` (restart -> queued/retry 1 thay vi NEEDS_ATTENTION; chu song doi project tranh dedupe T2 — dung vi rec2 da QUEUED sau RECOVER; idempotent test -> queued + error None, seq van tang don dieu) + `test_tasks_m3.py::test_restart_owner_dead_recovers_auto` + `test_desktop_m3.py::FakeOps` them get_states/click (selected san, giu hanh vi cu pass) — tat ca phan anh dung spec T5/D2 moi |

### Ghi nhan lech nho (chap nhan duoc, khong tinh loi)

- D2 C nhan `ops` lam tham so + guard `hasattr(ops,"get_states")` + `TypeError` fallback khi `click` khong co `headed` (A goi truc tiep module backend). Thich nghi dung kien truc Miro (ops inject), ngu nghia giu nguyen.
- D2 C goi ensure trong `_write` (A goi trong `_full_op :421-444` truoc ca read lan write). Miro `act()` chi read/write/append qua `_write`; read trong C van s fragmentation ngoai lock — giu cach C hien tai, khong mo rong scope commit nay.
- T5 C dung `snapshot_signature` hien co tu T1 (A dung `project_snapshot`); nguong `retry_count >= RECOVER_BUDGET-1` tuong duong A `retryCount < maxAttempts-1`. Dung.
- L1 `cmd_start` van giu check `CONTROL` sau sleep (redundant nhung vo hai — `_sleep_interruptible` da check moi nhip).

### Ket luan

**841e5ab DAT** (D1/D2/L1/T5 DAT: window-lock chung serialize that + select-tab truoc write + stop cat backoff + RECOVER-auto dung budget; 214/214 test pass ke ca test cu da cap nhat dung spec). **Chua push.**

## Verify Media Intel P0+P1 (commit tiep theo, 2026-11-23)

- Commit kiểm tra: Media Intel P0 (adapter duy nhất + trust boundary + cost gate, `d61260e`) + P1 (`analyze_audio` numpy-only, `extract_subtitle_track`, `merge_ocr_cues`).
- Luật khóa 3 lớp REA-MEDIA: `AGENTS.md` (§RE A-MEDIA) + CI (`tests/test_no_direct_media.py`: quét `cv2|rea_video|sherpa_onnx` ngoài adapter, check `check_media_evidence`/`deny_direct_media`/`require_generation_approval`) + runtime (`gateway.py` từ chối `media-analysis` làm Evidence WRITE).
- Test: `test_media_intel_p0.py` (4) + `test_media_intel_p1.py` (4: audio fixture 4s có track AAC, subtitle [], merge OCR outrank ASR + ocr-only) + `test_no_direct_media.py` (2) + full suite — **320 passed, 2 skipped**.
- P2 (stems/SenseVoice/diarize/classify, cần model nặng + uncertainty) + P3–P5 chưa làm.

### Kết luận

**Media Intel P0+P1 DAT** (adapter read-only, provenance `media-analysis` tách `rea-eye`, no-bypass, no auto-run generation). **Chưa push.**

## Verify bo sung W-R1: media_intel → Research/Agent + don sach (2026-11-23)

- File moi: `research/media_provider.py` — `MediaIntelProvider` cam vao
  `ResearchProvider.video_detail` (diem cam duy nhat, khong dung
  Library/Studio/Publisher).
- Vong doi ephemeral (bat buoc): yt-dlp tai (max 200MB / 30 phut, 360p)
  vao `TemporaryDirectory` → `mi.analyze()` → tra dict NHE
  (videomd + shots + audio + hash) → temp TU XOA (video + keyframes +
  analysis.json deu bay). Loi 1 video khong dung ca loat (batch tuan tu).
- Khong fallback ffmpeg-native: moi video content analysis qua adapter.
- Kiem chung live video YouTube that (Muse.ai 11:02): `frames_analyzed=True`,
  5 shots, tempo 115.4, 80 beats, VIDEO.md 882 chars, temp con lai **0**.
- Khoa CI: `test_no_direct_media.py` + `test_provider_goes_through_adapter`
  (provider chi subprocess yt-dlp lay media, phan tich chi qua `mi.analyze`).
- Test: `test_research_media_provider.py` (4) + full suite — **325 passed, 2 skipped**.
- W0 (Library auto-tag) / W1 (Studio step analyze) / W3 (Publisher gate)
  de sau, theo thu tu: Agent/Research chay that truoc.

### Kết luận

**W-R1 DAT** (Agent/Research dung duoc rea-video, temp + don sach, qua du 3 lop khoa). **Chua push.**

## Verify P2 + W0/W1/P3/W3 — full tich hop (2026-11-23)

- P2 `classify_shots()` heuristic (khong model): static_hold/still_motion/
  live_action mac dinh + `uncertain: True` + confidence; 3 label mu pixel
  (anim_2d/stop_motion/film_footage) KHONG BAO GIO doan.
- P2 `check_stems_model()`: onnxruntime CPU da co san; thieu model ->
  MODEL_MISSING + huong dan cache $REA_VIDEO_MODELS (khong auto-download,
  khong nhet repo). torch vang mat -> Demucs khong chay -> dung ly do
  can UVR fallback.
- W0 `LibraryService.auto_tag_from_analysis()`: tag `mi:*` (label,
  `:uncertain`, has-audio, tempo, has-subtitles, analyzed); khong xoa
  tag tay.
- W1 `LocalEngine.analyze_step()`: opt-in, read-only, luu analysis.json +
  VIDEO.md; khong dung 8 STEPS cu.
- P3 `summarize_for_agent()`: text gon cho Agent (<=4000 chars), chi format
  evidence co san, KHONG goi VLM tra phi.
- W3 `content_warnings()`: canh bao AIGC_HINT tu metadata (warn, KHONG chan
  Post — gate cu van quyet dinh).
- Test `test_media_intel_p2.py` (7) + full suite — **332 passed, 2 skipped**.

### Kết luận

**P2+W0/W1/P3/W3 DAT** (full tich hop, uncertainty + temp sach + warn khong chan). **Chua push.**

## Slice 04 — Standalone Runtime & Production Frontend (2026-11-26) — DAT

- Uy quyen: full A-Z trong cung task Slice 04 (khong hoi tung buoc), commit KHONG push, khong commit docs/ba-ben/.
- Entry: `python windows\miro.py start --only be,bridge --no-browser` (Launcher hien co) + `Miro-Standalone.bat`; FE dev qua launcher `--only fe` (rewrite ve BE) hoac `npx next dev --port 3100` + `NEXT_PUBLIC_API_BASE`.
- Khong tao launcher/framework moi, khong tich hop nguyen agent-desktop/agent-reach/LangGraph/scheduler/cloud; Rule-based TaskService hien tai, KHONG LLM planner (Slice 05).

| # | Nghiem thu | Bang chung | Ket qua |
|---|---|---|---|
| 1 | Launcher khoi dong BE+Bridge 1 cham | `windows/miro.py service_command fe` + BE/Bridge http-200 duoi launcher | **DAT (live)** — restart BE giu lai task cu nguyen ven |
| 2 | Xem Runtime/Bridge/Extension/Profile | `GET /tasks/runtime/status` (wiring redacted, tabs tu Bridge /tabs, khong lo credential) + FE `/runtime` | **DAT** |
| 3 | Giao nhiem vu capability da nghiem thu qua UI | FE `/tasks-live` → `POST /tasks/run-message` (actor/video/search TikTok) | **DAT (live)** — route `browser_actor_check` dung; `TAB_UNKNOWN` fail-closed khi chua co tab (khong bia ket qua) |
| 4 | Quan sat tien do/Evidence/ket qua/loi that | FE `/tasks-live/[id]` poll `GET /tasks/{id}` + `/events`, hien evidence + stop | **DAT** |
| 5 | Chuyen trang khong mat task | BE so huu state (SQLite `var/tasks.db`); `recent` doc lai giong nhau truoc/sau chuyen trang | **DAT (live)** — E2E slice04-live pass |
| 6 | Dong/mo lai khong lech trang thai | Stop launcher → start lai: task + event cu con nguyen (`recent` tra cung id) | **DAT (live)** |
| 7 | Manual control trong pham vi ho tro | Stop task qua UI (`POST /tasks/{id}/stop`), khong CDP/khong bypass Gateway/khong media ngoai `media_intel` | **DAT** |
| 8 | Test | `test_slice04_runtime_ui.py` 3/3 + cum lien quan 37/37 + full BE **449 passed, 2 skipped**; FE `tsc --noEmit` sach; E2E `slice04-runtime` + `slice04-live` pass | **DAT** |

Gioi han trung thuc:
- E2E fixture cu `threads-milestone` fail o buoc receipt khi BE chay (route batches uu tien BE dry-run that thay vi fallback fixture) — hanh vi co san tu truoc Slice 04 (route do toi khong sua), khong phai regression. Muon chay du E2E fixture thi dung BE tam thoi.
- Full BE suite lan dau timeout o 63% (khong fail); chay lai nen tron 449 passed.
- Extension/Chrome that chua noi trong dot nay (tabs `[]`); `run-message` fail-closed `TAB_UNKNOWN` dung thiet ke.

## Agent C — Baseline inventory + worktree map (2026-11-27, branch ui/port-prototype-v2, HEAD a94c1e2)

- Staged: 0 file. Unstaged (modified, chua commit): 50 file. Untracked: 52 entries.
- Nhom unstaged: (a) Port prototype FE M1-M4: 43 file `apps/web/src/features/*` + components/hooks/lib/services/stores/i18n/e2e (diff -4741/+3014, chu yeu thu gon mock pages); (b) Slice 04 repair: `apps/backend/src/miro/tasks/router.py` (+13: them `GET /tasks` compat alias cua `GET /tasks/recent`, read-only); (c) e2e + api routes dieu chinh nho theo port.
- Nhom untracked: `prototype/` (nguon Vite goc de port); `apps/web/src/app/api/{connections,platforms,publications,renders,research,schedule,studio,tasks/[id]/*,tasks/recent,run-message,runtime,threads}/` + `apps/web/src/app/prototype/` + `apps/web/src/app/settings/connections/` (routes moi cua dot port); `apps/web/src/{components/miro-shared/RuntimeBridgeBanner,hooks/data/useConnections,lib/{be-proxy,be,poll,threads},lib/services/{connections,platforms}.service}.ts` + `tsconfig.tsbuildinfo`; `docs/{foundation/slice05-architecture-proposal.md,integration/MIRO-BACKEND-API-CONTRACT.md,verify/frontend-product-acceptance-audit.md,ba-ben/...}`; `repos/`, `skills-lock.json`, tool dirs (`.agents/.claude/.playwright-mcp/.taste-skill`); RAC CAN DON: 2 file `.txt` ten tieng Viet + 4 file `bly*.png` (asset ngoai, chua phan loai — chua add).
- Worktree map: Agent A (Slice 04 repair) lam TAI `C:/Miro` (working tree hien tai, chua commit — KHONG checkout/switch khi chua stash). Agent B (Slice 05 P0-P1) lam TAI `C:/Miro-slice05` (branch `slice05/p0-p1`, detached tai a94c1e2, status sach). Cam ca hai ben sua `main.py`, `FE services`, `TaskService` tren cung tree — B chi code trong worktree cua minh, merge sau qua review.
- Canonical doc `docs/foundation/slice05-architecture-proposal.md` (528 dong, REVISION 2 + FINAL REVIEW APPROVAL reviewer 1): KHONG sua kien truc; doc qua read-tool UTF-8 binh thuong (mojibake chi la artifact `Get-Content` PowerShell, khong phai loi file) — khong mo review moi.
- Trang thai trung thuc: FE moi (AppShell) van MOCK ONLY; FE cu PARTIAL; BUG-11 (bridge cuop QA tab) CONFIRMED sau restart, chua fix; `/workspace` Completion Gate CHUA DAT (mock + mojibake source). Khong danh DONE bat ky muc nao theo ke hoach.
## Agent C — Runtime map + baseline MOCK ONLY (2026-11-27 ~17:00, không commit code người khác)

### 1. Hai worktree

| Bên | Path | Branch | HEAD | Status |
|---|---|---|---|---|
| Slice04 + FE unmock | `C:/Miro` | `ui/port-prototype-v2` | `a94c1e2` | 50 modified unstaged + 52 untracked (đang làm, KHÔNG đụng) |
| Slice05 P0-P1 | `C:/Miro-slice05` | `slice05/p0-p1` | `10d0e84` | **sạch** (0 modified) |

### 2. Runtime map (tất cả process đang chạy đều thuộc `C:/Miro` — slice05 CHƯA có runtime)

| Thành phần | PID | Lệnh / CWD | Port / URL | DB |
|---|---|---|---|---|
| BE uvicorn | 31488 (con của 21088 `windows/miro.py start --only be,bridge`) | `C:/Miro`, powershell 17760 ← opencode server 2784 | `127.0.0.1:8770` | `C:\Miro\var\tasks.db` (+`threads-*.db`, `conversations.db`, `lease.db`) — hardcode tuyệt đối trong `main.py:42`, `app.py:22` |
| Extension bridge | 36796 `experiments/extension-bridge/bridge/server.py` | `C:/Miro` | `127.0.0.1:18767` | — |
| FE Next dev | 27676 `next dev --port 3100` (CWD `C:/Miro/apps/web`, qua npm 30612 ← powershell 14472 ← opencode server) | FE `C:/Miro` | `0.0.0.0:3100` → FE `http://localhost:3100`, trỏ BE 8770 | — |
| Port 3000 | 34352 | `D:\BAI-HOC\kltls-fe` (dự án ngoài, không liên quan) | bỏ qua | — |

Cô lập: FE 3100 ↔ BE 8770 ↔ bridge 18767 là một cụm duy nhất của `C:/Miro`. **CẢNH BÁO**: `C:/Miro-slice05/apps/backend/src/miro/main.py:43` vẫn hardcode `C:\Miro\var\tasks.db` — nếu khởi BE từ worktree slice05 sẽ DÙNG CHUNG DB production. Chưa khởi nên chưa sao; khi chạy slice05 phải sửa path hoặc set `db_path` riêng TRƯỚC khi start.

### 3. Báo cáo "14 trang MOCK ONLY" của Agent D thuộc baseline nào

- Báo cáo = `docs/verify/frontend-product-acceptance-audit.md`, ngày 2026-11-26, đo tại commit **`73de3f4`** (UI port 14 trang, 100% `useMiroStore`/`launchTaskFromInstruction`).
- Worktree `C:/Miro` HIỆN TẠI đã chứa unmock FE-M1→M4 (unstaged, sau `73de3f4` → `a94c1e2` + diff hiện tại): `TasksPage` dùng `useBeTasks` + `RuntimeService`, `OverviewPage` dùng `useBeTasks`, `BrowserPage` dùng `useRuntimeStatus`; `miro.service.ts` chuẩn hóa qua `ConnectionsService/PlatformsService` (đọc BE, `[]`/502 thay vì seed). Các trang còn lại (media/research/schedules/workflows/projects/knowledge/...) vẫn `useMiroStore` mock.
- Kết luận: **MOCK ONLY thuộc baseline `73de3f4`, KHÔNG mô tả đúng worktree hiện tại** (đã unmock một phần). Cấm dùng audit đó để revert/ghi đè diff unmock. Slice05 (`10d0e84`) chỉ thêm conversations P0-P1 + `AiWorkspacePage` +28 dòng, không liên quan MOCK ONLY.
- Checkpoint đề xuất: CP-A = commit riêng diff unmock FE hiện tại sau khi regression (tên gợi ý `ui/unmock-m1-m4-partial`); CP-B = slice05 P0-P1 giữ nguyên branch, chưa merge cho tới khi DB path cô lập xong. Blocker duy nhất: hardcode `C:\Miro\var\tasks.db` hai bên (mục 2).

## Agent C — AI Provider P0-P1 status notes (2026-11-27, đọc từ branch `slice05/p0-p1`, commit `10d0e84`, KHÔNG checkout, KHÔNG sửa kiến trúc)

- Phạm vi đọc: `apps/backend/src/miro/{conversations/{provider,manager,store,router},llm/{types,fake,real,budget},agent/loop}` + `apps/web/src/{features/settings/AIProviderSettings,features/settings/SettingsPage,features/ai-workspace/AiWorkspacePage,lib/services/conversation.service}` + `tests/test_slice05_{p0,p1}.py`. Đây là **ghi nhận trạng thái implementation**, chưa phải verify ĐẠT/CHƯA (chưa chạy test suite trên worktree slice05).
- Proposal `docs/foundation/slice05-architecture-proposal.md` KHÔNG sửa (đang chờ đồng thuận canonical).

### 1. Provider support matrix (implementation thật)

| Provider | Path | Probe | Tool-calling / streaming / usage | Ghi chú |
|---|---|---|---|---|
| `real` (OpenAI-compatible) | `POST {baseURL}/chat/completions` (`llm/real.py`), stdlib `urllib`, timeout 30s | `GET {baseURL}/models` → `GET /settings/ai-provider/capabilities` | `"unknown"` cả 3 (probe chỉ xác nhận HTTP 2xx + latency; **không** mặc nhiên đủ tool-calling/streaming — đúng spec §23) | `LLMDecision` P1 chỉ dùng `respond`/`clarify`; `tool_call/wait/finish/cancel` đã định nghĩa type nhưng loop P1 chưa dispatch tool → gặp `tool_call` chuyển thành `clarify` trung thực, không bịa kết quả |
| `fake` (tests/CI only) | `llm/fake.py`, `name="fake"` | probe trả `tool_calling:false, streaming:false, usage:false` | Không dùng | Cấm expose như AI thật ở production; **không fallback Fake khi LLM thật lỗi** — `_loop_provider` (`conversations/router.py`) raise `PROVIDER_NOT_CONFIGURED` trung thực (D11) |
| Chưa cấu hình | `AIProviderStore.build_real_adapter()` → `None` | — | — | Turn `failed` + event `turn.failed` với `PROVIDER_NOT_CONFIGURED`; `POST /settings/ai-provider/test` khi thiếu baseURL/key trả `ok:false, error:PROVIDER_NOT_CONFIGURED` |

- Budget (`llm/budget.py`): per-turn 12 steps / 15 LLM calls / 300s active / est ~$0.50 + `daily_cost_cap` optional; cost chỉ cộng dồn khi `cost_usd` kèm `cost_unknown=False`, ngược lại `post_check` trả `cost_note: "chi phi chua xac dinh"` (đúng D12).

### 2. Security notes (key không lộ)

- Key sống **chỉ trong RAM Backend** (`AIProviderStore._key`, seed từ env `MIRO_AI_API_KEY`); `PUT /settings/ai-provider` nhận `key` nhưng strip khỏi config persist, **không log thô**.
- `GET /settings/ai-provider` chỉ trả `{provider, baseURL, model, tool_calling, streaming, has_key:boolean}` — **key không bao giờ trả về FE/network log** (đúng acceptance B, spec §4.3).
- FE `AIProviderSettings.tsx`: input `type=password`, `setKey('')` ngay sau save, placeholder `•••••• (đã có)` khi `has_key:true` — key cũ không hiển thị lại.
- Lưu ý trung thực: `POST /settings/ai-provider/test` (P0/P1) **chỉ kiểm tra config-present tại Backend, chưa gọi network thật** (`provider.py::test_connection`); probe live thật nằm ở `GET /settings/ai-provider/capabilities` (gọi `GET {baseURL}/models` với key Backend). User bấm "Test kết nối" OK ≠ đã verify live model.
- Chưa đọc thấy gửi cookie/secret/bridge-credential vào LLM context ở P0-P1 (RealAdapter chỉ gửi system prompt + messages user/assistant). Audit sâu khi P2 truyền tool evidence vào context.

### 3. User instructions — Settings → AI Provider (khớp implementation)

1. Mở **Settings → mục "AI Provider (Backend)"** (section `ai_provider`, thêm mới trong `SettingsPage.tsx`, tách khỏi mục "AI Models" vốn là mock FE `Miro Core/Fast/Deep Research` lưu localStorage).
2. Nhập **Provider** (mặc định `openai-compatible`), **Base URL** (`https://...`), **Model** (model-id), **API key** (chỉ gửi khi đổi, không hiển thị lại) → **Lưu cấu hình**.
3. Bấm **Test kết nối**: OK = Backend đã có đủ baseURL + key (chưa phải probe live — xem lưu ý §2); muốn probe live thì gọi `GET /settings/ai-provider/capabilities`.
4. Chat qua **AI Workspace**: FE ưu tiên `ConversationService` (`POST /conversations` → `POST /{id}/messages`, poll `GET .../turns/{turn_id}`, lịch sử `GET /{id}`); BE cũ vắng mặt → tự fallback legacy mock, không vỡ flow. Chưa cấu hình provider → assistant báo lỗi cấu hình trung thực, không bịa câu trả lời.
5. SSE stream: `GET /conversations/{id}/turns/{turn_id}/stream?after_seq=N` (replay + reconnect/dedup phía client bằng `seq`).

### 4. Checkpoint đề xuất (KHÔNG push)

- **CP-C1 (docs, đã xong ở entry này):** trạng thái AI Provider P0-P1 phản ánh đúng commit `10d0e84`; không lộ key trong mọi tài liệu/log.
- **CP-C2 (đề xuất, chờ session chính):** chạy `pytest tests/test_slice05_p0.py tests/test_slice05_p1.py` **trong worktree `C:/Miro-slice05`** rồi ghi kết quả ĐẠT/CHƯA vào entry mới — tuyệt đối không chạy BE slice05 khi chưa cô lập DB path (blocker hardcode `C:\Miro\var\tasks.db` đã ghi ở mục Runtime map).
- **CP-C3 (đề xuất):** khi merge slice05 về, kiểm tra xung đột `SettingsPage.tsx` (section mới) + `AiWorkspacePage.tsx` (Conversation-first + fallback) với diff unmock FE-M1→M4 trên `C:/Miro`.
- Trạng thái bàn giao: **doc updates xong, chưa commit, chưa push** (theo yêu cầu task).

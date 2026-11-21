# Verify Foundation — M3-phần-1 (commit 07ed929)

- Commit kiểm tra: `07ed929` — "M3-phan-1: workerOwner liveness + retry TRANSIENT co ngan sach + stop watchdog; connections verify kep truoc/sau qua Browser M1 + revoke invalidate lease"
- Docs đối chiếu: `docs/reader-jarvis.md` §9 (commit `29f082d`) + `docs/reader-dubtool.md` §9 (commit `e108fa9`)
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
- Docs doi chieu: `docs/reader-dubtool.md` §9 (9.1 backend Windows, 9.5 invariant 3) + `docs/reader-jarvis.md` §9 (9.5 route desktop-task, allowlist/headless), §4 (agent_desktop allowlist, secret-scrub, envelope)
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

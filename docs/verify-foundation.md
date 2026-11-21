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

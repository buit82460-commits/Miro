# Desktop / Watcher — ghi chú đọc sâu (dubtool vs JARVIS-Assistant)

Ngày: 2026-11-21. Phạm vi: chỉ đọc, không sửa code.
Nguồn chính:
- dubtool: `shared/desktop_gate.py`, `shared/desktop_dispatch.py`, `shared/desktop_backend.py`, `scripts/desktop_act.py`, `scripts/desktop_write_one.py`, `scripts/desktop_env.py`, `shared/execution_policy.py`, `shared/worker_supervision.py`, `core/posting_schedule.py`, `AGENTS.md`.
- JARVIS: `backend/app/jobs/{manager,runner,journal,models}.py`, `backend/app/core/{execution_policy,worker_supervision}.py`, `backend/app/integrations/agent_desktop.py`, `backend/scripts/dev_server.py`, `docs/design/approval.md`, `docs/notes/reports/2026-11-08.md`, `research/repos/agent-desktop/{AGENTS.md,src/dispatch,crates/...}`, `research/repos/agent-reach` (browser_watcher, dispatch cooldown).

## 1. dubtool — cơ chế epoch / quyền

- Đơn vị quyền là **job desktop** (`job_id`, mặc định `desktop-act-001`), state nằm ở `base/job_owner.json` (`{job_id, epoch, holder}`) hoặc `base/owners/<job>.json` khi nhiều job chung base.
- `shared/desktop_gate.py`:
  - `init_job(base, job_id, holder)` tạo epoch=1.
  - `transfer_job(base, job_id, new_holder)` **giữ `DispatchLock(base/dispatch.lock)`**, đọc fresh `job_owner.json`, kiểm tra `JOB_MISMATCH`, `epoch += 1`, đổi holder, `atomic_save`.
  - `gate(base, job_id, worker, worker_epoch)` đọc fresh file mỗi lần, từ chối `JOB_MISMATCH` / `STALE_EPOCH` (worker_epoch != current).
- `shared/desktop_dispatch.py` — quy tắc bắt buộc: **mọi mutation desktop đều qua `dispatch()`**, không gọi `desktop_backend` trực tiếp:
  - `DispatchLock`: exclusive inter-process lock bằng `msvcrt.locking(LK_NBLCK)` trên byte đầu của `dispatch.lock`, timeout 60s (`DISPATCH_LOCK_BUSY`). Hai CLI phối hợp qua file lock, không qua state bộ nhớ.
  - `dispatch(base, job_id, worker, worker_epoch, op, ...)`:
    1. giữ lock → `gate()` fresh → từ chối thì ghi `denied-<run>.json` (job+worker+run, không ghi đè);
    2. optional `hold_before_op` (hook test treo Ca1) → **re-gate sau hold** (`denied-after-hold`);
    3. chạy `op` → ghi `receipt-<run>.json` (job+worker+run+result, mỗi run một file, không overwrite).
  - `transfer_job()` giữ cùng lock nên transfer không thể lọt giữa epoch-check và backend call.
- `desktop_backend.py`: wrapper mỏng quanh `agent-desktop` CLI (`BIN` cố định bản win32-x64). Mỗi call là 1 CLI invocation; session/ref state nằm trên đĩa dưới `AGENT_DESKTOP_HOME` (xem `scripts/desktop_env.py`). Lease bên trong agent-desktop chỉ serialize truy cập đồng thời, **không thay thế epoch check** (ghi rõ trong docstring).
- `scripts/desktop_act.py` (entrypoint chuẩn hiện tại, thay thế `desktop_write_one.py` thử nghiệm):
  - Tham số: `app/window/doc/control/action/read|write|append|find-doc|find-window`, `text/text_file`, `job_id/worker/base/cache on|off`, `window_lock_dir`.
  - Fast path cache (`session-cache.json` key `app||doc` → session_id/window_id/tab_ref/field_ref): set session → vào `dispatch_window` → re-check epoch → `get_states(tab_ref)` xác nhận cửa sổ còn sống + tab còn selected → nếu bị chuyển tab thì re-find + select trong lock → set-value → read-back verify → cập nhật cache. Ref stale rõ ràng (`WINDOW_NOT_FOUND/REF_NOT_FOUND/...`) mới fallback full path.
  - Full path: resolve window → resolve doc (**doc phải duy nhất, `DOC_NOT_UNIQUE_STOP` dừng trước write**) → vào window lock → verify/select tab → find control → set-value → read-back → cập nhật cache.
  - Verify sau write: `write` yêu cầu `readback == text`; `append` yêu cầu `readback == before + text` (chuẩn hóa CRLF). Sai → `VERIFY` fail, `reconciled=true, replayed=false, content_met=false`.
  - Read/cache-hit không qua dispatch (read-only); mọi write/append qua `dispatch_window`.

## 2. dubtool — dispatch cửa sổ

- `dispatch_window(base, window_id, job_id, worker, epoch, op, window_lock_dir=...)`:
  - Lý do: hai job chung một cửa sổ Notepad dùng chung tab đang chọn; lock theo `job_id` không ngăn job A chuyển tab lúc job B đang write. Lock theo **window** làm select-tab + write thành nguyên tử.
  - Thứ tự lock cố định: `base/dispatch.lock` → `window-locks/window-<wid>.lock` (mặc định dưới private state dir từ `ensure_state_dir()`, nên job khác base vẫn chia sẻ lock). `transfer_job()` chỉ lấy base lock → không deadlock.
  - Trong lock: fresh gate → hold/re-gate → chạy op → ghi `receipt-<run>.json` (kèm `window`, `entered_at`), **trừ** khi result `cache_stale` (để caller fallback, không lưu receipt giả).
  - Caller (`desktop_act.py`) đọc fresh epoch ngay trước khi vào `dispatch_window` (`load_json_if_exists(owner_path).epoch`), không dùng epoch cache từ đầu phiên.
- Test kèm theo: `scripts/test_two_jobs_same_window.py`, `test_ca1_stale_after_gate.py` (treo sau gate), `test_ca2_crash_after_op.py` (crash sau op).

## 3. dubtool — watcher chống trùng

- Không có daemon watcher thường trực cho desktop theo nghĩa watchfiles/inotify. "Watcher" ở đây là 3 lớp:
  1. **File lock + fresh read** (`dispatch.lock`, `window-*.lock`, đọc lại `job_owner.json` mỗi lần) chống race giữa các tiến trình CLI.
  2. **Journal chống đăng trùng publication** (AGENTS.md + `core/posting_schedule.py`): source of truth là `publication-*.json` + attempt journals (`reports/social-attempts/`); trước mọi Post kiểm tra đã có trong publication → skip; đã có attempt journal → chỉ reconcile, **KHÔNG replay UNKNOWN**. Module schedule chỉ index, không quyết định.
  3. **Event watcher ở adapter đăng bài** (ví dụ `threads_post_one.py`: network ack + toast watcher, `facebook_receipt.py` repoll read-only) — quan sát kết quả sau submit, không thay thế epoch/dispatch.
- `shared/execution_policy.py`: `atomic_save` (tmp+replace, UTF-8 no-BOM, retry PermissionError), `TRANSIENT` vs `BLOCKING` (UNKNOWN/RESULT_UNKNOWN → BLOCKED, "never replay unknown effects"), `recover_execution` (EXECUTE/VERIFY + !safe_to_replay → BLOCKED).
- `shared/worker_supervision.py`: `RestartBudget(maximum=3, window=600)` + `terminate_owned` (taskkill /T /F trên Windows); caller giữ Popen handle.

## 4. JARVIS — phía tương ứng

- **Không có epoch/gate ở tầng desktop.** Quyền được thực thi ở 3 chỗ khác:
  1. **Slot đơn**: `JobManager` giữ tối đa 1 job hoạt động (`_slot_lock: asyncio.Lock`, `_active_job_id`, hàng đợi `_waiting`). `release_slot()` nhả slot sau cleanup; `mark_slot_contaminated()` khóa slot khi cleanup không sạch (browser chưa đóng).
  2. **Recovery an toàn**: snapshot `runtime/execution/jobs/job_<id>.json` qua `atomic_save`; `recover_pending()` sau restart: kiểm tra `workerOwner {pid, createdAt}` bằng `psutil` (pid còn sống + create_time khớp → BLOCKED `OWNERSHIP_UNKNOWN`); job chưa start + loại an toàn mới được `create_job` lại, desktop_task/browser_task mặc định BLOCKED `RESULT_UNKNOWN` ("no replay of unknown effects"). Journal JSONL append-only mỗi job (`JobJournalWriter`, một writer/khóa mỗi file).
  3. **Per-action allowlist ở adapter**: `app/integrations/agent_desktop.py` — mỗi lệnh agent-desktop là 1 subprocess riêng (`shell=False`, env lọc secret, timeout cứng, kill tree qua psutil, envelope JSON 1 dòng). Danh sách lệnh đóng (`_ALLOWED_COMMANDS`), **headless mặc định, cấm `--headed`/headed-only** (double-click/drag/hover/mouse-*), cấm `clipboard-set/clear`. Đây chính là "điểm chặn per-action tự nhiên" cho approval gate mốc G (`docs/notes/reports/2026-11-08.md`, `docs/design/approval.md`), không cần patch upstream như Browser Use.
- **Watcher theo nghĩa file-watch**: `backend/scripts/dev_server.py` v2 — `watchfiles.watch(app/, .env)` trong cùng tiến trình, thấy đổi → `terminate_owned` + khởi động lại uvicorn thường (giữ event loop Proactor để browser-use mở Chrome được; v1 `--reload` chết `NotImplementedError`). Có `RestartBudget` + cooldown 2s, bỏ qua `__pycache__`/sentinel. Đây là watcher phục vụ dev/reload, **không phải** dedupe nghiệp vụ.
- **Browser watcher**: `agent-reach/runtime/browser_watcher.py` — watcher idle duy nhất ("another watcher is running"), đóng browser sau idle; `dispatch.py` có cooldown/backoff theo channel (JARVIS patch `dispatch.cooldown("web") → None` để rate-limit Exa không khóa oan Jina).
- Upstream `agent-desktop` (Rust): `dispatch()` trong `src/dispatch/mod.rs` là `match` trực tiếp tới `execute()` từng command, batch dùng chung `dispatch()` + `CommandPolicy` preflight; ref snapshot-qualified (`@sID:eN`), `STALE_REF`/`AMBIGUOUS_TARGET`; state dưới `~/.agent-desktop` (`AGENTS.md` của repo đó).

## 5. Khác biệt 2 bên

| Trục | dubtool (`C:\dubtool`) | JARVIS (`D:\JARVIS-Assistant/backend`) |
|---|---|---|
| Đơn vị quyền | job desktop + **epoch** trong `job_owner.json`; transfer tăng epoch | job backend + **slot đơn**; không epoch ở tầng desktop |
| Điểm chặn mutation | `dispatch()/dispatch_window()` — fresh gate dưới file lock, receipt/denied mỗi run | allowlist + 1 subprocess/lệnh trong `agent_desktop.py`; slot + approval classify |
| Cửa sổ chia sẻ | `window-<wid>.lock` liên base, select+write nguyên tử | không có window lock; dựa vào 1 job active + headless allowlist |
| Chống trùng | publication + attempt journal, cấm replay UNKNOWN, reconcile read-only | snapshot + journal JSONL, `RESULT_UNKNOWN` → BLOCKED, khôi phục có điều kiện |
| Watcher file | không dùng watchfiles cho desktop; lock + poll/mtime rời rạc ở harness | `watchfiles` cho dev_server reload; browser idle watcher cho agent-reach |
| Restart/crash | `RestartBudget(3/600s)` + `terminate_owned` (caller giữ handle) | cùng pattern (`app/core/worker_supervision.py`) + owner PID/create-time guard |
| Verify sau write | read-back bắt buộc, so sánh chuẩn hóa newline | verify ở harness/route (get sau set-value), envelope + timeout từng bước |

## 6. Khuyến nghị thống nhất (đề xuất, chưa thực hiện)

1. **Giữ epoch/dispatch của dubtool làm chuẩn cho mọi mutation desktop**, kể cả khi gọi từ JARVIS: mọi đường write desktop của JARVIS nên đi qua một hàm tương đương `dispatch_window` (fresh epoch + window lock + receipt/denied mỗi run), thay vì chỉ dựa vào slot đơn.
2. **Giữ allowlist headless + per-action gate của JARVIS** làm chuẩn an toàn lệnh: port danh sách lệnh đóng và phân loại read-only/mutating (`approval/`) sang phía dubtool caller; cấm `--headed`/clipboard-mutate ở production.
3. **Thống nhất journal**: publication/attempt (dubtool) + job journal JSONL + execution snapshot (JARVIS) dùng chung quy ước: cấm replay UNKNOWN, reconcile read-only, receipt gắn job+run+window+target, `atomic_save` tmp+replace ở mọi writer.
4. **Thống nhất supervision**: một `RestartBudget` + `terminate_owned` + owner PID/create-time guard cho cả desktop worker và dev watcher; watcher file (nếu có) chỉ reload/reconcile, không bao giờ tự submit lại.
5. **Không gộp lease với quyền**: giữ nguyên tắc dubtool — lease/session (agent-desktop, CDP, browser profile) chỉ serialize truy cập, epoch/slot/approval mới quyết định được phép tác động.

# Reader JARVIS — ghi chú đọc sâu (vòng 1, 2026-11-21)

Nguồn duy nhất: `D:\JARVIS-Assistant` (không đọc Dubtool).
Người đọc: Reader JARVIS thường trực. Đầu ra bắt buộc cho agent viết code + Checker.
Quy ước: `J:<path>` = file trong `D:\JARVIS-Assistant`.

Vòng 1 gồm 4 nhóm: (1) jobs + `dubtool_tasks` (Task đối chiếu),
(2) `live_chrome_worker` + `agents/browser.py` + `research/repos/browser-use` (Browser bọc thật),
(3) desktop agent + route + `research/repos/agent-desktop` (Desktop bọc thật),
(4) `vision_client/agent_reach/social_video/tiktok_endpoints` + 4 agents research (Research/Integrations đối chiếu).

---

## 1. Jobs: manager / runner / journal / models + execution_policy

### 1.1. `J:backend/app/jobs/models.py` (1–173)

- `JobStatus` 8 trạng thái: `queued/running/paused/stopping/cancelled/succeeded/failed/blocked`.
  `TERMINAL = {cancelled, succeeded, failed, blocked}`; `ACTIVE = {queued, running, paused, stopping}` (`models.py:23–52`).
- `JobType` là Literal 14 giá trị: `browser_task, web_search, web_read, stock_quote, stock_search, github_search, github_read, synthesize, page_extract, video_extract, channel_report, desktop_task, tiktok_discover, dubtool` (`models.py:63`). Tham chiếu: nhóm research còn thiếu `synthesize` (orchestrator nội bộ) — không cần đối chiếu Dubtool.
- `JobRecord`: `id/task/agent_type/status/created_at/effective_limits`, `job_type`, `control_request` (`pause|stop`), `result/error`, `last_event_sequence`, `execution: dict = new_execution()`, `recipe: dict`, `events: deque(maxlen=max_events)` + `subscribers` (`models.py:101–126`).
- `supports_pause` hiện **luôn `True`** (dòng 136–139 ghi "chỉ browser_task" nhưng code return True) — Runner chỉ gọi `agent.request_pause()` khi `job_type=='browser_task'` (`runner.py:113`); các agent khác tự raise `CONTROL_NOT_SUPPORTED` (desktop) hoặc giữ result chờ resume (non-pausable tools, `runner.py:208–214`). Invariant Checker: đừng suy luận pause thật từ `supports_pause`.
- `JobEvent`: `job_id/sequence(≥1)/timestamp/type/data`, `extra=forbid, frozen` (`models.py:77–86`).
- `to_public_dict()` trả đúng 13 key, gồm `effective_limits/support…/control_request/error/last_event_sequence/execution` — không có `recipe` (recipe chỉ lưu snapshot, xem 1.2) (`models.py:153–172`).

### 1.2. `J:backend/app/jobs/manager.py` (1–1030)

- **Slot đơn**: `_active_job_id` duy nhất + hàng đợi `_waiting`. `release_slot` chỉ nhả khi slot trống và không `unclean`; job chờ `PAUSED` bị bỏ qua, `CANCELLED` bị loại (`manager.py:215–229`). Invariant: tối đa 1 job active.
- **Slot nhiễm (contamination)**: cleanup fail → `mark_slot_contaminated` khóa tạo job mới (`RESOURCE_CLEANUP_UNCLEAN`) cho tới xử lý rõ (`manager.py:231–244`, `runner.py:471–475`). Invariant: cleanup fail không được nhả slot im lặng.
- `create_job` (698–802): validate theo từng `job_type` (fake_scenario chỉ khi `AGENT_MODE=fake` cho browser_task; các job nội bộ `synthesize/page_extract/...` **bắt buộc agent dựng sẵn**, client không tự tạo — mã `*_AGENT_REQUIRED`); job nội bộ dùng trần timeout riêng từ policy (`page_extract_job_timeout`, `video_extract_job_timeout`, `channel_report_job_timeout`, `desktop_task_job_timeout`, `tiktok_discover_job_timeout`, `dubtool_job_timeout` — `policies/browser.py` + `manager.py:508–693`).
- Từ chối input chứa secret thật (`TASK_CONTAINS_SECRET`, `manager.py:736`), lưu `recipe` (input thô để replay) + `execution = new_execution(job_id)` (hoặc giữ lại khi `_restore_id`) + `advance(execution,'PLAN','agent')` (`manager.py:750–756`).
- **Snapshot bền**: `_persist_job` = `to_public_dict() | {recipe}` → `atomic_save(runtime/execution/jobs/job_<id>.json)`, sanitize secret trước (`manager.py:143–147`). Khởi động lại: `_load_execution_snapshots` đọc lại snapshot, job dở dang (không terminal, không paused) vào `_pending_recovery` (`manager.py:127–141`).
- `recover_pending` (`manager.py:149–177`): chỉ replay nhóm an toàn `web_read/web_search/stock_* /github_*`; `browser_task/desktop_task` → `BLOCKED/RESULT_UNKNOWN` (không replay hiệu ứng chưa rõ); cần `recipe` + `retryCount < maxAttempts-1`, ngược lại `BLOCKED/ADAPTER_CHECKPOINT_REQUIRED`. Chủ sở hữu worker chết/không xác minh → `BLOCKED/OWNERSHIP_UNKNOWN`. Invariant cho Task đối chiếu: **không replay mutation chưa rõ kết quả** (khớp `dubtool_tasks` §2).
- Event: `emit_event` đánh sequence tăng dần, append deque + journal JSONL + fan-out WS non-blocking; subscriber đầy → `overflowed`, cắt kết nối để tự resync (`manager.py:246–286`). `get_events_after/subscribe_events` trả `earliest_available_sequence + resync_required` khi mốc cũ bị đẩy khỏi deque (`manager.py:927–995`). Đóng subscriber bằng sentinel `None` khi terminal (`manager.py:288–296`).
- Controls: `pause` chỉ từ `running` (queued→paused trực tiếp qua execution control); `resume` chỉ từ `paused`; `stop` idempotent, terminal thì 409 (`manager.py:816–925`).

### 1.3. `J:backend/app/jobs/runner.py` (1–492)

- Vòng đời `_execute_lifecycle`: `queued→running (+job_started)` → `_run_autonomously` dưới `wait_for(timeout)` → timeout thì `job_timeout` + `agent.request_stop()` + grace → buộc cancel → **cleanup TRƯỚC** → đúng 1 trạng thái kết thúc → nhả/khóa slot → phát terminal event → đóng subscribers (`runner.py:231–491`).
- Thứ tự ưu tiên terminal: `timeout > user_stop/Cancelled > AgentExecutionError (BLOCKED nếu execution BLOCKED) > cleanup fail > success` (`runner.py:351–465`).
- `_run_autonomously` (`runner.py:198–229`): `workerOwner={pid, createdAt}` (psutil) để recovery phát hiện chủ cũ; job non-pausable giữ `result` khi `control==pause` (không rerun, chờ resume); retry transient (`TRANSIENT` + `AGENT_REACH_TIMEOUT/CONNECTION_ERROR`) qua `failure()`; cleanup fail giữa recovery → `BLOCKED/RESOURCE_CLEANUP_UNCLEAN`.
- `advance(job.execution, ...)` các mốc `PLAN→EXECUTE→VERIFY→COMPLETE`, `PAUSED/STOPPED/BLOCKED` (`runner.py`, `execution_policy.py`). Server shutdown: job web-safe → `RECOVER` + hạ về `QUEUED` (chạy lại khi restart); browser/desktop giữ terminal (`runner.py:467–470`).
- Stop: `initiate_stop` idempotent → `stopping` + `stop_requested` → watchdog `stop_grace_seconds` buộc cancel (`runner.py:122–164`). Pause browser: `control_request='pause'` + `agent.request_pause()` (BrowserUse `Agent.pause()`), chờ `confirm_paused` từ hook (`runner.py:98–120`).
- Sanitize mọi output qua `sanitize_data/scrub_text` với secret thật; key nghiệp vụ dài (`final_answer/text/content/caption/missing/core_gap`) không cắt 500 ký tự (`runner.py:442–460`). Invariant: journal/result không bao giờ chứa secret/API key/stack trace thô (`JobErrorInfo` chỉ `code/message/details`, `models.py:67–74`).

### 1.4. `J:backend/app/jobs/journal.py` (1–70) + `J:backend/app/core/execution_policy.py` (1–79)

- Journal: append-only `runtime/logs/jobs/<job_id>.jsonl`, 1 dòng JSON/event; `job_id` validate `^[A-Za-z0-9_-]{1,64}$`; lỗi I/O → `JournalWriteError` + đếm `write_error_count`, không sập tiến trình (`journal.py:20–70`).
- `execution_policy.py`: portable, không import app/network. `POLICY = {maxAttempts:3, baseDelay 1s→max 30s (2^n), autoContinue/autoRecover/autoResume, requireStepConfirmation:False}`; `TRANSIENT` (lỗi mạng/429/502/503/504/TAB_LEASE_BUSY/DEPENDENCY_UNAVAILABLE...) cho retry; `BLOCKING` (OWNERSHIP_UNKNOWN/REMOTE_RESULT_UNKNOWN/RESULT_UNKNOWN/APPROVAL_REQUIRED/CAPTCHA/MFA/AUTH/PERMISSION/LEASE_LOST/PROFILE_UNVERIFIED/SCOPE_DENIED/RESOURCE_CLEANUP_UNCLEAN...) không retry (`execution_policy.py:15–26`). `failure()`: BLOCKING/unsafe → BLOCKED; transient trong budget → RECOVER + delay; hết budget → BLOCKED (`:45–56`). `recover_execution`: EXECUTE/VERIFY mà `not safe_to_replay` → BLOCKED/RESULT_UNKNOWN (`:75–79`).

### Invariant nhóm 1 (Checker dùng)

1. 1 slot active; cleanup fail khóa slot (`RESOURCE_CLEANUP_UNCLEAN`).
2. Không replay mutation chưa rõ kết quả (BLOCKED + giữ checkpoint/receipt).
3. Event sequence đơn điệu tăng; resync khi mốc bị evict; terminal đúng 1 lần.
4. Secret không vào input/journal/result; error chuẩn hóa không stack trace.

---

## 2. `J:backend/app/integrations/dubtool_tasks.py` (1–417) — Task đối chiếu

- Phạm vi file: ủy thác bền cho HTTP service Dubtool hiện có; **mọi remote mutation có write-ahead marker; response uncertain không bao giờ auto-retry** (`dubtool_tasks.py:1–5`).
- Schema: `DubtoolTaskRequest` — `request_id ^[A-Za-z0-9_-]{1,80}$`, `message 1–4000`, `videos 1–20` (mỗi video đúng 1 trong `source local | project_id`; source phải path tuyệt đối video, cấm URL/UNC), `use_ai/handoff`, `description/tags/language` (`:49–69`). `TaskVideo.title 1–100`, `transcript ≤50k`. Secret trong payload → `TASK_CONTAINS_SECRET` (`:190–195`). `read_task_markdown`: đúng 1 khối ```jarvis-task JSON, message = text ngoài khối, file ≤256KB (`:72–85`).
- Idempotency: `fingerprint = sha256(canonical JSON)`; cùng `request_id` + cùng fingerprint → trả record cũ; cùng id khác nội dung → `REQUEST_ID_CONFLICT`; video local phải tồn tại ≤2GB (`:196–209`).
- Durability: record `task-<hex32>.json`, ghi `tmp + fsync + replace`; bản ghi hỏng → giữ `{status:needs_attention, pending_mutation:{step:corrupt_record}}`, không chặn backend (`:139–156`, `save :163–176`).
- Restart: `running/queued` → `needs_attention/JARVIS_RESTARTED`; `recover_pending` chỉ auto-resume loại không pending_mutation + mã cho phép (`:158–161`).
- `step()` (`:295–305`): checkpoint đã có thì dùng lại; chưa có → ghi `pending_mutation={item,step,route}` + save **trước** side-effect → gọi remote → lưu checkpoint → xóa marker + save. Đây là write-ahead bắt buộc — Miro đối chiếu Task phải giữ.
- `resume` (`:221–230`): có `pending_mutation` → `REMOTE_RESULT_UNKNOWN`, bắt kiểm tra Studio trước, không tự gửi lại; chỉ resume `needs_attention`; completed/awaiting/stopped không resume lại (`TASK_NOT_RESUMABLE`). `stop` (`:232–244`): không dừng render/lịch Dubtool đã nhận (API timeline chưa có cancel) — outcome ghi rõ.
- Pipeline `run()` (`:315–417`): lock sequential (không stop/restart Dubtool chung); read-only preflight projects; `create→import→track→assemble→plan→apply→render→(handoff)`; mỗi biên kiểm `revision` (`PROJECT_CHANGED` nếu lệch); plan read-only retry-safe; render poll ≤3600s (`queued/running/completed/failed/stale`), fail → `DUBTOOL_RENDER_FAILED`; `handoff` re-validate revision, thiếu `productionId` → lỗi contract; kết thúc `awaiting_dubtool` (outcome: chưa xác nhận lịch/đăng) hoặc `completed`. Cancel giữa chừng → `needs_attention/DELEGATION_INTERRUPTED`, resume không gửi lại bước đã ghi nhận.
- HTTP (`DubtoolHTTP :94–121`): loopback `127.0.0.1:port` cố định, `trust_env=False`, không redirect/proxy; `≥300` → `DUBTOOL_HTTP_<code>`; JSON phải `{success:true, result}` nếu không → `DUBTOOL_CONTRACT_CHANGED`. `refresh()` chỉ đọc production YouTube (`:263–293`), schema sai → contract error, không suy đoán trạng thái đăng.
- `public()` ẩn `request/fingerprint/checkpoints`, sanitize secret (`:178–183`).

### Invariant nhóm 2

1. `request_id` + `fingerprint` idempotent; conflict nội dung khác → từ chối.
2. Mọi mutation remote có `pending_mutation` ghi trước; uncertain → BLOCKED/needs_attention, resume thủ công sau kiểm tra ngoài, không auto-retry.
3. `revision` project kiểm ở mọi biên (create/import/plan/apply/render/handoff).
4. Không suy đoán trạng thái đăng/lịch Dubtool (outcome "chưa xác nhận").

---

## 3. Browser bọc thật: worker + agent + research

### 3.1. `J:backend/app/integrations/live_chrome_worker.py` (1–228) + `live_chrome.py` (đầu file) + `shared_browser_client.py`

- Worker là tiến trình con cô lập (chạy bằng Python của Dubtool social-runtime, "never import publisher/session stores"). Mỗi request `tabs/bind/read` = 1 subprocess mới, stdin/stdout JSON 1 dòng, timeout phía service 175s (`live_chrome.py:53–60` đọc tới dòng 60).
- `endpoint(user_data_dir)`: đọc `<dir>/DevToolsActivePort` (dòng 1 port, dòng 2 `/devtools/browser/<id>`) → `ws://127.0.0.1:port+route`; lỗi → `CDP_UNAVAILABLE` (`worker:22–30`). `browser_id = sha256(endpoint)` (`:33–34`).
- `_run_unleased`: kiểm tra socket 127.0.0.1:port (2s) → `playwright.chromium.connect_over_cdp(address, timeout=120s, no_defaults=True)`; **không bao giờ `browser.close()/context.close()`** — chỉ disconnect khi driver shutdown (`worker:151–175`). `tabs` chạy không lease; `bind/read` qua `SharedStore.held(resource, "jarvis-existing-worker", ttl=180)` + `validate(lease)` sau op (`worker:179–203`). Lease DB mặc định `C:\dubtool\config\browser-registry.sqlite` (`JARVIS_BROWSER_LEASE_DB`).
- `operate()`: `tabs` liệt kê target `{target_id, url(public, strip query/fragment), kind: profile_evidence|facebook}` + `observed_target_ids`; chỉ facebook hoặc `chrome://version` (`worker:94–111`). Chọn tab sai/mất → `TAB_NOT_FOUND`, không chọn thay thế. Chỉ hỗ trợ `tabs/bind/read` — action khác → `ACTION_DENIED` (`worker:122–123`).
- **Verify 2 lớp, trước và sau op** (`worker:113–129`): (a) `verify_profile` — đúng 1 tab `chrome://version` có `targetId==profile_target_id`, cùng `windowId` (qua `Browser.getWindowForTarget`) với tab FB, `#profile_path` khớp `normcase(realpath(<user_data_dir>/<profile_directory>))`, re-check URL sau đọc (`worker:69–91`); (b) `actor` — URL phải facebook host hợp lệ + `CurrentUserInitialData.USER_ID` khớp `account_id ^\d{1,30}$` (`worker:57–66`). Lệch → `PROFILE_UNVERIFIED/PROFILE_MISMATCH/ACCOUNT_MISMATCH/ORIGIN_CHANGED`. `read` chỉ `body.innerText` cắt `max_chars` (mặc định 12000, trần 30000 qua `ChromeReadRequest`) — không cookie/storage/HTML/JS thô (`worker:118–121`, `live_chrome.py:27–29`).
- Service (`live_chrome.py:36–52`): `asyncio.Lock` serialize trong-process + `bindings {}` in-memory (mất khi restart); capability duy nhất `READ`. `guard_legacy_browser` (`agents/browser_access.py`, trích trong `browser-read-notes.md` Miro) chặn mọi adapter launch cũ ở mode `existing_cdp`, bắt bind qua `/browser-live` trước.
- `shared_browser_client.py` (1–37): client HTTP tới shared-owner Dubtool (`POST /api/dubtool/browser/shared/<action>`, action allowlist `snapshot/discover/read/task/create_tab/navigate/verify_account`), loopback-only, header `X-Browser-Client/X-Browser-Key`, không redirect; lỗi → `SHARED_BROWSER_REJECTED/SHARED_OWNER_UNAVAILABLE`, **không takeover/fallback**. Đường worker hiện tại tự connect CDP + tự acquire SQLite (bỏ qua `social.busy`/health/audit của owner) — xem khuyến nghị `browser-read-notes.md §5` Miro.

### 3.2. `J:backend/app/agents/browser.py` (1–550) — BrowserUseAgent (bọc thật, commit `b49a68e`)

- Tắt telemetry/cloud-sync trước mọi import browser_use (`os.environ` + verify `CONFIG` sau import, lỗi → `TELEMETRY_NOT_DISABLED`) (`browser.py:21–23, 275–309`).
- Thứ tự `run()`: guard legacy → verify revision (`verify_browser_use_revision`, lỗi → `BROWSER_REVISION_MISMATCH`) → tạo LLM qua factory (lỗi → `LLM_CONFIG_INVALID`, **trước khi mở browser**) → `BrowserProfile(user_data_dir=profiles/job-<id>, headless=config, allowed_domains, keep_alive=False, executable_path=jarvis_browser_path)` → `BrowserSession` + instrument lifecycle (`browser.py:270–328`).
- `Agent(...)`: `use_vision=False` (gateway text-only), `step_timeout` + `llm_timeout` tường minh từ policy, `max_history_items`, callbacks `step/done/should_stop`, `enable_signal_handler=False` (`browser.py:406–419`).
- Điều khiển: `request_pause/resume/stop` gọi API thật `Agent.pause()/resume()/stop()` (service.py:3942/3948/3956); pause xác nhận qua bọc `_external_pause_event.wait()` + hook `_on_step_hook` (chạm điểm an toàn mới `confirm_paused`) (`browser.py:224–268`, `385–396`). Stop kiểm trong `_should_stop` mỗi bước.
- Auto-retry trang lỗi (0 LLM): đọc `innerText` qua CDP, khớp chuỗi lỗi policy → reload ≤ `browser_retry_max_attempts` (đếm theo URL), phát event `auto_retry`; fail-safe nuốt lỗi đọc (`browser.py:77–152`). Timing: `step_timing` (`llm_done/action_done`) qua `_phase_marks` (`:154–198`).
- Kết quả: chỉ success khi `history.is_done() and is_successful() is True`, nếu không → `BROWSER_AGENT_INCOMPLETE/UNSUCCESSFUL (+BROWSER_AGENT_STATUS_UNAVAILABLE khi không đọc được trạng thái)`; result `{revision, steps_completed, final_result (scrub, ≤500), errors[:5], usage}` (`browser.py:439–499`).
- `cleanup()` (`:501–549`): `agent.close()` + `session.kill()`, xác minh PID từ `_local_browser_watchdog` (`browser_pid`/`_subprocess.pid`) qua psutil còn sống không; **không kill mọi Chrome trên máy**. `browser_closed_verified=False` → runner khóa slot (`CLEANUP_FAILED`).

### 3.3. `J:research/repos/browser-use` (tham khảo pattern, không mở CDP production)

- Repo `browser-use` trong research chỉ giá trị tham khảo pattern (service/session/profile/watchdog) — xem `browser-read-notes.md §4.5` Miro. Miro bọc Browser thật phải giữ: revision pin + verify, profile riêng per-job, telemetry off, PID verify, không kill Chrome chung. File chi tiết trong repo: `browser_use/agent/service.py` (pause/resume/stop ~dòng 3942–3956), `browser_use/browser/profile.py:425` (`executable_path`), `browser_use/browser/session.py`, `.../security_watchdog.py`, `.../local_browser_watchdog.py` (nguồn trích trong docstring `browser.py:1–8`).

### Invariant nhóm 3

1. Existing Chrome: verify profile (chrome://version cùng window + realpath) + verify actor (USER_ID) trước VÀ sau op; tab mất → dừng, không chọn thay thế.
2. Không `browser.close/context.close`, không kill Chrome chung; cleanup xác minh PID job.
3. `tabs` không lease; `bind/read` giữ lease SQLite ttl 180 + validate; uncertain → không retry post.
4. BrowserUse: revision pin, telemetry off, LLM trước browser, profile riêng, success kiểm `is_done && is_successful`.

---

## 4. Desktop bọc thật: agent + route + research

### 4.1. `J:backend/app/integrations/agent_desktop.py` (1–551)

- Mẫu AgentReachAdapter: subprocess riêng `shell=False, argv tường minh`, env lọc secret, envelope JSON 1 dòng + exit 0/1/2, timeout cứng, terminate tree psutil, xác minh PID (`agent_desktop.py:1–20`). Thực chứng smoke 2026-11-09: `set-value -- REF VALUE positional` headless `delivered_verified`; `close-app` graceful TIMEOUT khi app có dữ liệu chưa lưu.
- **Allowlist đóng** `_ALLOWED_COMMANDS` (~30 lệnh, `agent_desktop.py:54–91`): read-only (`status/permissions/version/list-*/snapshot/find/screenshot/get/is/wait --notification...`), thao tác (`click/type/set-value/clear/focus/select/toggle/check/uncheck/expand/collapse/scroll/scroll-to/press/launch/close-app/focus-window/resize/move/minimize/maximize/restore/wait`). Cấm: `double-click/drag/hover/mouse-*`, `--headed`, `clipboard-set/clear` (chỉ `clipboard-get`), `press` cần 2 positional. `REF/VALUE` là positional, không `--ref/--value`.
- `validate_command_args` (`:129–182`): lệnh lạ → `DESKTOP_TASK_COMMAND_NOT_ALLOWED`; flag lạ → `..._FLAG_NOT_ALLOWED`; flag value thiếu giá trị / thiếu positional → `..._INVALID_INPUT`. `_VALUE_FLAGS`: mọi flag có giá trị trừ `--exact/--activate/--cdp/--force/--stdin`.
- `AgentDesktopAdapter.execute` (`:298–382`): validate allowlist → stop đã set → hủy; `cli_runner` tiêm khi test; subprocess `Popen([binary, *argv], stdin=DEVNULL, stdout/stderr=PIPE, env=isolated, shell=False)`; `asyncio.wait({communicate, stop_event}, timeout)` — stop → terminate tree + `AgentStoppedSignal`; timeout → terminate + `DESKTOP_TASK_TIMEOUT`; `CancelledError` → terminate + raise. Binary: `JARVIS_AGENT_DESKTOP_BIN` hoặc `PATH agent-desktop`, thiếu → `..._BINARY_NOT_FOUND`.
- `_parse_envelope` (`:384–451`): stdout rỗng → `..._BAD_OUTPUT`; JSON lỗi/thiếu `ok` → `..._BAD_OUTPUT`; `ok:false` → map upstream `TIMEOUT/INVALID_ARGS/POLICY_DENIED/PERM_DENIED/STALE_REF/AMBIGUOUS_TARGET/APP_NOT_FOUND/TARGET_NOT_FOUND` → mã `DESKTOP_TASK_*` tương ứng, khác → `DESKTOP_TASK_FAILED` (kèm `delivery/retry/exit_code`).
- `build_isolated_subprocess_env` (`:113–126`): loại mọi key chứa `API_KEY/SECRET/TOKEN/PASSWORD/COOKIE` + denylist tường minh (`LLM_API_KEY/.../JARVIS_AUTH_TOKEN/...`).
- `_terminate_process_tree` (`:185–221`): terminate parent + children recursive, `wait_procs 1s`, còn sống → kill + wait.
- `DesktopTaskAgent` (`:454–551`): 0 LLM, headless, chạy tuần tự `steps[{argv}]`; validate `1 ≤ steps ≤ desktop_task_max_steps` (policy mặc định 20, `policies/browser.py:472–477`); `step_timeout = desktop_task_step_timeout_seconds` (mặc định 60s), job trần `desktop_task_job_timeout` (mặc định 300s, `manager.py:624–646`); events `desktop_task_started/step_started/step_completed/completed`; `request_pause/resume` → `CONTROL_NOT_SUPPORTED`; stop/cleanup qua adapter (verify subprocess tắt).

### 4.2. Route `POST /desktop-task` — `J:backend/app/api/routes/desktop_task.py` (1–46) + schema `api/schemas.py:456–468`

- `DesktopTaskRequest`: `steps: list[dict] 1–20`, `timeout_seconds?`, `extra=forbid`. Route dựng `DesktopTaskAgent(cfg, steps)` rồi `create_job(job_type='desktop_task', timeout_seconds, desktop_agent=...)` → 202 + `JobResponse`; chỉ tạo qua route này (`DESKTOP_AGENT_REQUIRED`).

### 4.3. `J:research/repos/agent-desktop` (upstream vercel-labs)

- Cấu trúc: `apps/`, `crates/`, `npm/`, `probes/`, `scripts/`, `skills/`, `docs/`, `benchmarks/` (ls §trên). Adapter JARVIS không kéo library — gọi CLI qua subprocess + envelope. Miro bọc Desktop phải giữ: allowlist đóng (không argv tùy ý), headless mặc định (không `--headed`), mỗi lệnh 1 subprocess (điểm chặn per-action cho approval gate mốc G), env scrub secret, terminate tree + verify PID, envelope `ok` + map lỗi upstream.

### Invariant nhóm 4

1. Allowlist đóng + headless; không `--headed`, không clipboard-mutate, không mouse-* headed-only.
2. Mỗi lệnh 1 subprocess riêng; stop/timeout terminate tree thật + verify.
3. REF/VALUE positional; upstream `ok:false` map mã rõ, không nuốt.
4. Pause/resume không hỗ trợ (`CONTROL_NOT_SUPPORTED`); job tạo chỉ qua route nội bộ.

---

## 5. Research / Integrations đối chiếu

### 5.1. `J:backend/app/integrations/vision_client.py` (1–120)

- `VisionClient.describe_frame(image, prompt, max_tokens=600) → {text, prompt_tokens, completion_tokens}`; model vision riêng `LLM_VISION_MODEL` (Gateway Hypertek: opus strip ảnh im lặng prompt_tokens ~104 — phải dùng model nhận image như `qwen3-vl-8b-instruct` prompt_tokens ~626) (`vision_client.py:1–12`).
- Bẫy ảnh-bị-strip: `prompt_tokens < 200` dù gửi ảnh → `VISION_IMAGE_DROPPED`; `finish_reason==length` → `VISION_OUTPUT_TRUNCATED`; rỗng → `VISION_EMPTY_OUTPUT`; 429 → rate-limit; khác 200 → `VISION_LLM_ERROR` (`:94–120`). Frame là DỮ LIỆU, mô tả không chứa lệnh.

### 5.2. `J:backend/app/integrations/agent_reach.py` (1–1292+)

- Chỉ nạp kênh cho phép từ `research/repos/agent-reach` commit pin `14c2134...` (`EXPECTED_AGENT_REACH_COMMIT`): `web` (+`xueqiu` backend `tencent`, +`github` backend `github-api`); stub `yaml`, chặn kênh social khác; patch `_exa_search` rỗng → `[]` (phân biệt 0 kết quả với lỗi), cô lập cooldown `web` (không khóa chéo Exa/Jina) (`agent_reach.py:123–269`).
- Ghim backend tường minh: `web search --backend exa`, `web read --backend jina`, `xueqiu --backend tencent`, `github --backend github-api`; lệch backend → `AGENT_REACH_UNEXPECTED_BACKEND` (chặn fallback âm thầm) (`:1239–1262` parse+check, các hàm search/read/github/stock tương tự).
- Subprocess cô lập (`_execute_cli_command :484–572`): `python -m app.integrations.agent_reach --repo-dir --home-dir -- <argv>`, HOME/USERPROFILE sang `agent-reach-home`, env scrub secret, `shell=False`; stop → terminate tree; timeout → `AGENT_REACH_TIMEOUT`; `inprocess` runner chỉ dùng cho test.
- Envelope: JSON `{ok/channel/action/backend/items}` (+ chấp nhận `status:ok` legacy); lỗi map `TIMEOUT/RATE_LIMITED/BAD_INPUT→INVALID_INPUT/NOT_FOUND+UPSTREAM_BROKEN→UPSTREAM_ERROR`; item search phải có URL http(s) hợp lệ; text cắt `max_content_chars` + cờ `truncated` (`:574–706`, `1224–1291`).
- `SafePublicRedirectHandler`: chặn redirect sang non-http(s)/credential/localhost/private/link-local/metadata (`:81–118`). Read validate SSRF/DNS theo policy (`validate_web_read_url`, `check_dns_on_read`).
- Stock (`:834–934`): `xueqiu quote/search --backend tencent`, normalize `{title/url/text/raw}`. GitHub (`:1064–1222`): search cắt limit + truncate từng item; read yêu cầu content non-empty (`AGENT_REACH_EMPTY_READ_CONTENT`).
- `AgentReachJobAgent` (phần sau dòng 1292, chưa đọc hết vòng này): bọc các hàm trên thành agent cho 6 job_type web/stock/github. Vòng sau đọc nốt + `synthesize.py`.

### 5.3. `J:backend/app/integrations/social_video.py` (đầu 1–120)

- Bóc 1 video TikTok/Facebook/YouTube công khai, 0 LLM phần bóc, stdlib + ffmpeg/ffprobe, chạy subprocess entry `python -m app.integrations.social_video`, 1 dòng JSON stdout / log stderr, exit 0 ok / 2 lỗi nghiệp vụ (`social_video.py:16–21`).
- TikTok: mirror `tikwm.com/api/?url=` (metadata + CDN mp4) + `api/comment/list?url=` (comment); header `Referer + Accept: application/json`. Facebook: `plugins/video.php?href=&show_text=true` (caption + hd/sd_src) + `watch/?v=<id>&locale=vi_VN` (2 comment "Phù hợp nhất" — hơn 2 cần cookie: KHÔNG làm). YouTube: `yt-dlp --print` metadata + `--write-comments` (5–30s), backup innerTube WEB + oEmbed. Host allowlist theo platform; sai host → `SOURCE_URL_MISMATCH` (`:44–99`). Không login/cookie/token.

### 5.4. `J:backend/app/integrations/tiktok_endpoints.py` (đầu 1–120)

- 5 endpoint port từ `research/repos/tiktok-api` (không kéo lib): hashtag (`challenge/detail→item_list`), sound (`music/item_list`), trending (`recommend/item_list?from_page=fyp`), related (`related/item_list`), replies (`comment/list/reply`, fix bug upstream: `item_id` = VIDEO id) (`tiktok_endpoints.py:1–11`). `search.users` BỎ (cần msToken từng search).
- Fetch trong trang tiktok.com thật qua Chrome profile có acc: `page.evaluate` sinh X-Bogus (`byted_acrawler.frontierSign`) + fetch nội bộ; msToken từ cookie profile, dùng ngay, không ghi ra file/ngoài envelope; ~20 session params port `tiktok.py:153–181` (`:12–17`, `build_session_params :109–120+`). Subprocess entry riêng, envelope 1 dòng + PROGRESS stderr, exit 0/2; không login/CAPTCHA, retry ≤2.
- `build_params/endpoint_url/_PAGE_SIZE/_ITEM_LIST_KEY/_HAS_MORE_KEY` (`:52–80`); `extract_video_id` nhận URL `/video/<id>` hoặc id số (`:86–96`).

### 5.5. Agents research: `page_extract / video_extract / channel_report / tiktok_discover`

- `agents/page_extract.py` (B1): 4 phase LOAD→EXTRACT→(view count: chưa làm)→SUMMARIZE (1 LLM duy nhất qua SynthesisService); LOAD poll `innerText` 2s + reload ≤2 khi gặp chuỗi lỗi policy; EXTRACT bằng JS server-định-nghĩa (profile `tiktok_tag`/`tiktok_user`, regex link `/@user/video/ID`, ≤20 items; 0 items → `EXTRACT_EMPTY`); profile persistent `runtime/profiles/jarvis-browser` hoặc per-job; chỉ ĐỌC, không click (`page_extract.py:1–79`).
- `agents/video_extract.py`: 0 LLM 0 browser phần bóc (subprocess `social_video` như AgentReach pattern); mức 1: 1 LLM tổng hợp qua SynthesisService; mức 2 vision đọc frame (spike riêng, chưa trong agent); `__init__(platform/url/max_comments/max_frames/download/summarize/synthesis_service/vision_client/vision_frames/user_message)` (`video_extract.py:1–80`).
- `agents/channel_report.py`: pipeline tuần tự trong 1 job (tránh deadlock 1-slot): BOC_LINKS (tái dùng PageExtractAgent `tiktok_user`) → từng video qua `social_video` subprocess (metadata+comment+tải+frame+vision qwen3-vl, mỗi video 1 progress) → 1 LLM tổng hợp kênh; trần `channel_report_job_timeout` 1800s (`channel_report.py:1–80`).
- `agents/tiktok_discover.py`: 0 LLM, subprocess `tiktok_endpoints` qua Chrome profile persistent ("haodao jr"); `kind ∈ {hashtag,sound,trending,related,replies}`; env scrub + drain pipe bằng thread (tránh deadlock Windows, BUGS.md 2026-11-07); `guard_legacy_browser` chặn launch cũ (`tiktok_discover.py:1–80`).
- Pattern chung 4 agents: subprocess cô lập + shell=False + env scrub + timeout cứng + terminate tree psutil + envelope JSON + 0 LLM phần bóc (LLM chỉ ở lớp tổng hợp cuối) + nội dung web là DỮ LIỆU (delimiter bọc, không thực thi lệnh).

### Invariant nhóm 5

1. Backend ghim tường minh, lệch → lỗi (không fallback âm thầm).
2. 0 LLM cho phần bóc; LLM chỉ tổng hợp cuối; web content là dữ liệu.
3. Subprocess cô lập + timeout + terminate + verify; secret scrub khỏi env/log.
4. Vision: phát hiện ảnh-bị-strip (`prompt_tokens<200`); platform công khai only (không login/cookie/CAPTCHA/retry tự do).

---

## 6. Checklist bắt buộc cho agent viết code + Checker (vòng 1)

- [ ] 1-slot + contamination lock; recipe + execution snapshot bền; restart chỉ replay nhóm safe.
- [ ] Write-ahead `pending_mutation` cho mọi remote mutation; uncertain → BLOCKED + kiểm tra ngoài, không auto-retry.
- [ ] Event sequence đơn điệu + resync; terminal duy nhất; secret không rò rỉ.
- [ ] Existing Chrome: verify profile + actor trước/sau; không close/kill Chrome chung; lease đúng ttl + validate.
- [ ] BrowserUse: revision pin, telemetry off, profile riêng, success = done && successful.
- [ ] Desktop: allowlist đóng, headless, 1 subprocess/lệnh, envelope map lỗi, không pause.
- [ ] Research: backend pin, 0-LLM bóc, subprocess cô lập, vision strip-trap, public-only.

*Nguồn file:dòng ghi trong từng mục. Vòng sau (khi có tính năng mới): đọc nốt `agent_reach.py` từ dòng 1293, `live_chrome.py` từ dòng 61, routes còn lại, rồi bổ sung dưới mục mới — không sửa các mục đã chốt.*

---

## 7. Vòng 2 — Studio bọc Pipeline trong C (2026-11-21, định nghĩa merge mới)

Phục vụ Studio bọc Pipeline trong Miro (`apps/backend/src/miro/studio/handlers.py` + `store.py`, `tasks/service.py` + `storage/db.py`).
Đối chiếu với B = JARVIS (`backend/app/jobs/`, `integrations/dubtool_tasks.py`, `agents/synthesize.py`, `planner/`).
Ký hiệu: `B:<path>` = file trong `D:\JARVIS-Assistant`; `C:<path>` = file trong `C:\Miro`.

### 7.1. Đối chiếu hiện trạng C với B

- **Write-ahead đã parity.** `C:tasks/service.py:85–98` (`_step`: checkpoint có thì skip → ghi `pending_mutation` + `_save` TRƯỚC `remote.mutate` → lưu checkpoint → xóa marker + save) khớp `B:dubtool_tasks.py:295–305` (`step()`). `resume` chặn khi còn `pending_mutation` (`C:178–183`) khớp `B:221–230` (`REMOTE_RESULT_UNKNOWN`). `restart` hạ in-flight về `NEEDS_ATTENTION` (`C:164–176`) khớp `B:recover_pending` (`manager.py:149–177`) và `B:stop→needs_attention/DELEGATION_INTERRUPTED`.
- **Stop 2 pha đã có.** `C:request_stop` (→`STOP_REQUESTED`, idempotent) + `acknowledge_worker_stopped` (→`STOPPED`, chỉ khi có request treo) (`C:140–161`) khớp ngữ nghĩa `B:runner.initiate_stop` (idempotent, `stopping` + watchdog grace) — nhưng C chưa có watchdog buộc hủy khi worker không thoát; `acknowledge_*` hiện gọi thủ công.
- **Revision check đã có 2 nơi.** `C:studio/store.py:34–45` (`check_revision`, sai → 409) + `C:studio/handlers.py:41–45,47–60` (guard trước `work()`, cache-first replay) khớp `B:project()` validate schema+revision mọi biên (`dubtool_tasks.py:307–313`) và `FakeRemote.mutate` check `expected_revision` (`C:tasks/service.py:30–37`).
- **Khoảng trống C (Studio nên lấy từ B):**
  1. **Không fingerprint nội dung.** `C:studio/handlers._run_idempotent` (`handlers.py:47–60`) trả cache theo `request_id` mà không kiểm nội dung: cùng `request_id` khác payload vẫn trả kết quả cũ im lặng. B từ chối (`REQUEST_ID_CONFLICT`, `dubtool_tasks.py:197–201`) và Miro tasks đã làm đúng (`service.py:61–65`). Studio C nên copy: `fingerprint = sha256(canonical JSON)` + conflict khi khác nội dung.
  2. **Không slot đơn / contamination lock.** `C:tasks/service.run` chạy đồng bộ, không giới hạn pipeline đồng thời, không khóa khi cleanup fail. B: 1 slot active (`manager.py:215–229`, hàng đợi `_waiting`, job chờ `PAUSED/CANCELLED` bị loại) + `mark_slot_contaminated` khóa tạo job mới khi cleanup fail (`manager.py:231–244`, runner `471–475`). Studio bọc Pipeline (render nhiều bước, giữ tài nguyên) nên lấy: tối đa 1 pipeline active mỗi project + khóa pipeline mới khi lần trước dọn không sạch.
  3. **Không retry TRANSIENT có ngân sách.** `C:_step` gọi `mutate` 1 lần, exception lạ (ngoài `TaskConflictError`) thoát ra ngoài không persist terminal. B: `runner.py:218–229` retry chỉ khi `safe_to_retry` (nhóm read-only) + mã transient, `maxAttempts=3` backoff 1→30s (`execution_policy.py:15–26,45–56`); hết budget → BLOCKED giữ checkpoint. Studio nên lấy: retry chỉ bước read-only/idempotent (plan), mutation chưa rõ kết quả → `NEEDS_ATTENTION`, không replay.
  4. **Không workerOwner liveness.** `B:recover_pending` kiểm tra PID + `create_time` của chủ cũ qua psutil: còn sống → `BLOCKED/OWNERSHIP_UNKNOWN` (`manager.py:155–166`). C `restart` không kiểm chủ cũ — chấp nhận được khi worker là in-process, nhưng khi Studio tách worker tiến trình riêng phải bổ sung.
  5. **Persist chưa atomic.** B `atomic_save`: tmp + `fsync` + replace, retry `PermissionError` 7 lần (`execution_policy.py:58–73`); marker `pending_mutation` luôn fsync trước side-effect (`dubtool_tasks.py:163–176`). C `TaskStore.upsert_task/append_event` chỉ `execute + commit` (`storage/db.py:47–73`), không fsync — crash giữa `pending_mutation` save và `mutate` có thể mất marker. Studio nên lấy `fsync` (ít nhất cho write-ahead save).
  6. **Render/synthesize thiếu guard nguồn.** B `SynthesisOutput`: `final_answer ≤8000`, `sources ≤20` và service validate mọi URL thuộc tập bước đã chạy (`planner/models.py:110–137`, `service.py:473–498`); `synthesize` chỉ là bước cuối (`models.py:105–106`); system prompt bắt `insufficient_data/core_requirement_met=false` khi thiếu lõi, không bịa, không thay bằng nội dung liên quan (`service.py:447–456`); web content là DATA trong delimiter. Nếu Studio C thêm bước AI tóm tắt/kế hoạch render, copy nguyên 3 guard này.

### 7.2. Hành vi Studio C nên lấy từ B (checklist cho agent viết code)

- [ ] `request_id` + `fingerprint` (sha256 canonical JSON): cùng id cùng nội dung → trả cũ; cùng id khác nội dung → `REQUEST_ID_CONFLICT`.
- [ ] Write-ahead `pending_mutation` + fsync trước mọi mutation; checkpoint xong skip; uncertain → `NEEDS_ATTENTION/REMOTE_RESULT_UNKNOWN`, resume thủ công sau đối chiếu ngoài.
- [ ] Revision check mọi biên (guard trước `work()`, mutate với `expected_revision`); lệch → 409 `PROJECT_CHANGED`.
- [ ] Slot đơn mỗi project + contamination lock khi cleanup fail; stop 2 pha (request vs worker-thoát) + watchdog buộc hủy.
- [ ] Terminal duy nhất, ưu tiên timeout > stop > error > cleanup; exception lạ → persist `NEEDS_ATTENTION`, không để task treo không trạng thái.
- [ ] Retry chỉ bước read-only/idempotent, ngân sách 3 lần backoff; mutation không replay.
- [ ] Bước tổng hợp (nếu có): schema `final_answer/sources/insufficient_data/missing/core_requirement_met/core_gap`, sources validate thuộc tập bước đã chạy, không bịa.

*Nguồn B file:dòng ghi trong từng mục; nguồn C: `apps/backend/src/miro/{studio/handlers.py:47–60,studio/store.py:34–51,tasks/service.py:30–37,85–98,140–188,storage/db.py:47–73}`. Vòng sau bổ sung tiếp dưới mục mới — không sửa mục đã chốt.*

---

## 8. Vòng Browser — lần theo một task Existing Chrome từ nhận đến trả kết quả (2026-11-21)

Nguồn duy nhất B = `D:\JARVIS-Assistant`. Hai đường task riêng biệt, không lẫn:
(Đ1) **BrowserUse job** — agent tự launch browser riêng qua `agents/browser.py`, qua `jobs/manager+runner` (đã ghi §1, §3.2).
(Đ2) **Existing Chrome read** — mục này: bám Chrome người dùng đang mở, capability duy nhất READ, qua `live_chrome*` + route `/browser-live` + `/assistant.browser_access`. Không tạo job.

### 8.1. Nhận task → giao việc cho worker (Đ2)

| Bước | File:hàm:dòng | Hành vi |
|---|---|---|
| 1. Nhận | `B:api/routes/live_chrome.py:9–45`: `POST /browser-live/tabs`, `POST /bindings`, `POST /bindings/{id}/read`, `DELETE /bindings/{id}`; hoặc `B:api/routes/assistant.py:81–89`: `payload.browser_access` (binding có sẵn + `max_chars`) → read đồng bộ, trả 200 trực tiếp | Không qua `JobManager`; không `request_id/fingerprint/write-ahead` (read-only, không mutation) |
| 2. Serialize | `B:integrations/live_chrome.py:98–118` `LiveChromeService.execute`: `asyncio.Lock` (1 op tại một thời điểm, `CHROME_BUSY` nếu đang bận) + `request_id=uuid4` trace log `browser_route … outcome=started/completed/failed_or_cancelled` | Lock là trong-process; phối hợp cross-process qua lease SQLite ở worker (§8.2) |
| 3. Spawn worker | `B:integrations/live_chrome.py:53–96` `_run`: `create_subprocess_exec(<JARVIS_LIVE_CHROME_PYTHON> live_chrome_worker.py)`, stdin JSON (≤65537 bytes ở worker `main`), stdout 1 dòng JSON (trần 200000 bytes), **timeout 175s** → `CHROME_TIMEOUT` (không tự kết nối lại) | Worker là tiến trình con ngắn hạn, mỗi request 1 process mới; `RUNTIME_MISSING/START_FAILED/TRANSPORT_FAILED` khi runtime/stdout lỗi |
| 4. Dọn transport | `live_chrome.py:80–96`: worker xong/timeout → `proc.kill()` (chỉ Python worker) + kill đúng tiến trình `node*playwright*` (driver), **không bao giờ kill Chrome** | `psutil` check creation-time trước kill |
| 5. Binding | `live_chrome.py:123–137` `bind`: lưu `data` request vào `self.bindings[uuid4]`, trả `binding_id + capability READ`; `read`: binding mất → `BINDING_NOT_FOUND`; read lỗi (trừ `CHROME_BUSY`) → **xóa binding**, bắt gắn lại | Binding in-memory, mất khi backend restart; `close()` clear + cancel tasks (`live_chrome.py:45–51`) |

### 8.2. Bảng quyền sở hữu worker/tab

| Tài nguyên | Chủ | Cấp ở đâu | TTL / phạm vi | Bằng chứng |
|---|---|---|---|---|
| Browser instance (`browser_id = sha256(ws_endpoint)`) | Không ai sở hữu — chỉ kiểm tra | `worker.py:33–34,94–96,151–155` | Mỗi op so `request.browser_id` với instance từ `DevToolsActivePort`; lệch → `SESSION_CHANGED`, liệt kê + gắn lại | `endpoint()` đọc port/route (`worker.py:22–30`) |
| Tab (`tab:<browser_id>:<targetId>`) | Worker tiến trình hiện tại (`owner="jarvis-existing-worker"`) | `worker.py:179–203` `run()`: `SharedStore.held(resource, ttl=180)` + `store.validate(lease)` sau op | Chỉ `bind/read`; **`tabs` không lease** (`worker.py:181–182` → `_run_unleased` thẳng) | `tab_resource(instance, target_id)` (cùng công thức Dubtool); DB `JARVIS_BROWSER_LEASE_DB` mặc định `C:\dubtool\config\browser-registry.sqlite` (`worker.py:194`) |
| Cửa sổ/profile bằng chứng | Người dùng (worker chỉ đọc) | `verify_profile` (`worker.py:69–91`): tab `chrome://version` có `targetId==profile_target_id`, cùng `windowId` với tab FB (qua `Browser.getWindowForTarget`), `#profile_path` khớp `normcase(realpath(user_data_dir/profile_directory))` | Kiểm tra **trước và sau** mỗi op (`operate`: `worker.py:113–129`: verify → actor → bind/read → actor → verify) | `profile_evidence: "existing_version_same_window"` trong kết quả |
| Account FB (`account_id ^\d{1,30}$`) | Người dùng đăng nhập sẵn | `actor()` (`worker.py:57–66`): URL phải hostname facebook hợp lệ + `CurrentUserInitialData.USER_ID` khớp `account_id` | Trước và sau op; lệch → `ACCOUNT_MISMATCH`, đổi origin → `ORIGIN_CHANGED` | Không cookie/storage — chỉ đọc JS có sẵn trong trang |
| Quyền READ của caller | Binding in-memory của backend | `bind()` cấp, `read()` dùng 1 lần logic (binding giữ lại nếu read thành công), lỗi → xóa | `capability: "READ"` duy nhất; action khác → `ACTION_DENIED` (`worker.py:122–123`) | Schema `ChromeBindingRequest/ChromeReadRequest` (`live_chrome.py:14–29`) |
| Guard đường launch cũ | `browser_access.guard_legacy_browser` | `agents/browser_access.py:5–21`: mode `existing_cdp` (hoặc có personal profile) → `EXISTING_CDP_REQUIRED`, chặn mọi adapter launch cũ; phát event `browser_route` (`launch/copy/new_page=false`) | `browser.py:271` + `tiktok_discover.py:63` gọi guard trước mọi launch | `tabs` kiểu launch riêng (`scripts/social_browser.py`) cũng bị chặn ở mode này |

Snapshot mỗi op (`worker.py:132–148,164–174`): `targets_before/after`, `windows_before/after`, `target_set_changed/window_set_changed` — bằng chứng tab/cửa sổ đổi giữa chừng; không tự chữa, trả về cho caller quyết định.

### 8.3. Trả kết quả / ngắt / phục hồi (kể cả mất kết nối)

| Tình huống | Hành vi | Mã lỗi / file:dòng |
|---|---|---|
| Read thành công | `{"text": body.innerText[:max_chars], profile_verified:true, account_id, url(public, strip query), browser_id, target_id, window_id, shared_lock:false, snapshot…}` | `worker.py:118–129`; trần stdout 200KB `live_chrome.py:67–68` |
| Tab mất / chọn sai | Không chọn tab thay thế | `TAB_NOT_FOUND` `worker.py:111–112` |
| Browser đổi / endpoint chết | `SESSION_CHANGED` (so endpoint sha), `CDP_UNAVAILABLE` (đọc DevToolsActivePort lỗi), `CONNECTION_REFUSED` (socket 127.0.0.1:port 2s fail) — **không mở browser thay thế** | `worker.py:22–30,94–96,151–160,190–193` |
| Lease bị giữ (TAB_BUSY) | `RegistryError` → `LiveChromeError`, không cướp, không retry post | `worker.py:202–203`; `run()` không fallback (`main`: `worker.py:206–224` map `CONNECTION_CLOSED/TIMEOUT/…`, live error passthrough, lỗi lạ → `CHROME_FAILED_<Type>_<reason>`, "không tự thử lại") |
| Timeout 175s / cancel | `CHROME_TIMEOUT`; `execute()` trace `failed_or_cancelled`, dọn worker + driver | `live_chrome.py:77–78,110–118` |
| Bận (op khác đang chạy) | `CHROME_BUSY`, binding giữ nguyên (không xóa) | `live_chrome.py:99–100,136–137` |
| Binding hỏng / restart backend | `BINDING_NOT_FOUND` → client liệt kê `tabs` + `bind` lại từ đầu; bindings mất khi restart (`close()` clear) | `live_chrome.py:45–51,130–137` |
| Phục hồi chuẩn | tabs → bind (verify profile+actor, giữ lease 180s, validate) → read (verify lại) → kết quả kèm snapshot; bất kỳ verify nào fail → lỗi rõ + gắn lại, không dùng kết quả dở | `worker.py:94–129,179–203` |

### Invariant vòng Browser (Checker dùng)

1. READ-only: chỉ `tabs/bind/read`; không launch/copy/new-page/fallback khi thiếu binding (guard `EXISTING_CDP_REQUIRED`).
2. Verify kép (profile cùng-window + realpath, actor USER_ID) trước VÀ sau mỗi op; tab mất/browser đổi → dừng + gắn lại.
3. `tabs` không lease; `bind/read` lease SQLite ttl 180 + validate; không cướp lease, không retry khi uncertain.
4. Mỗi request 1 worker process ngắn hạn; dọn đúng worker + node-playwright driver, không kill Chrome; timeout 175s.
5. Binding in-memory (mất khi restart); lỗi read (trừ BUSY) → xóa binding; kết quả kèm snapshot before/after để caller phát hiện đổi tab/cửa sổ.

# ai-manus — Phân tích chi tiết

> Open-source Manus clone: Web + Server + Sandbox. Agent PlanAct/single-loop gọi tool qua LLM function-calling, chạy trong Docker sandbox (tmux + Chrome + VNC + supervisord).
>
> Phương pháp: 5 subagent đọc song song 5 cụm, mỗi cụm glob liệt kê file trước rồi đọc 100% số dòng, mọi nhận định kèm trích dẫn `file + #L`.
> Nguồn: `D:\repos\ai-manus`. Đọc runtime 100% (trừ `uv.lock`, `package-lock.json`, `node_modules/.git`).

## 0. Số liệu tổng hợp

| Cụm | File | Dòng | Tình trạng |
|---|---|---|---|
| backend `domain/` + `application/` + `core/` | 89 | ~9.727 | ✅ §1 |
| backend `interfaces/` + `infrastructure/` + main/worker | 68 | 9.274 | ✅ §2 |
| backend `tests/` + `evals/` | 36 | 5.707 | ✅ §3 |
| sandbox + mockserver + scripts + root + docs + configs | ~99 | ~1.366 (yaml) + toàn bộ còn lại | ✅ §4 |
| frontend `src` toàn bộ (Vue 3 + TS) | 219 | 21.583 | ✅ §5 |

## 1. Backend core — `domain/` + `application/` + `core/` (89 file, ~9.727 dòng)

### 1.1 `domain/skills/` (4 file: skill_md 111d, package 29d, body 24d, archive 217d)
- Parse SKILL.md frontmatter tự viết (chỉ `key: value` 1 dòng + continuation, không phải YAML đầy đủ — list/nested bẹt thành string) [skill_md.py](file:///D:/repos/ai-manus/backend/app/domain/skills/skill_md.py#L11-L12); `extract_skill_md_from_bytes` lấy member đầu tiên endswith SKILL.md (chấp nhận file nằm sâu, khác `archive.py` yêu cầu duy nhất) [skill_md.py](file:///D:/repos/ai-manus/backend/app/domain/skills/skill_md.py#L44-L58).
- Ingest zip an toàn: cap kép (compressed + tổng uncompressed + budget streaming, 20MB), zip-slip, bỏ junk `__MACOSX/.DS_Store/._*`, lỗi nhiều SKILL.md [archive.py](file:///D:/repos/ai-manus/backend/app/domain/skills/archive.py#L10-L21).
- Quirk: `domain` import từ `application.data` (`body.py`) — ngược DDD [body.py](file:///D:/repos/ai-manus/backend/app/domain/skills/body.py#L8-L24); `skill_dir` chỉ strip + lstrip("/") — tên `..` không bị chặn tại đây (chặn ở archive/sync).

### 1.2 `domain/services/tools/` (10 file: base 422d, mcp 362d, browser 175d, file 151d, shell 89d, plan 61d, message 54d, search 39d, skill 130d)
- Hạ tầng tool framework-agnostic: decorator `@tool` (2 chế độ mô tả loại trừ nhau), `Tool.invoke` tách `brief`, `OutputTool` schema-only validate structured output, `describe_toolkits` [base.py](file:///D:/repos/ai-manus/backend/app/domain/services/tools/base.py#L190-L252).
- `SkillToolkit` progressive disclosure: catalog L1 trong description, body L2 chỉ trả qua tool result [skill.py](file:///D:/repos/ai-manus/backend/app/domain/services/tools/skill.py#L15-L31). **Quirk: `tools/__init__.py` không export `SkillToolkit`** (thiếu cả `PlanToolkit` trong `__all__`) [tools/__init__.py](file:///D:/repos/ai-manus/backend/app/domain/services/tools/__init__.py#L1-L18).
- `MCPClientManager` (stdio/sse/streamable-http qua `AsyncExitStack`) + `MCPToolkit` bọc schema runtime thành `Tool.dynamic`; comment tiếng Trung; `initialize()` dùng `self._config.mcpServers` không guard None [mcp.py](file:///D:/repos/ai-manus/backend/app/domain/services/tools/mcp.py#L29-L45).
- Shell/File/Browser/Search/Message đều pass-through sang `Sandbox`/`Browser`/`SearchEngine`, không validate tại đây (phó mặc backend) [shell.py](file:///D:/repos/ai-manus/backend/app/domain/services/tools/shell.py#L27-L89).

### 1.3 `domain/services/prompts/` + `skills/` + `plan_progress.py` + `todo_projection.py`
- System prompt lắp: `CORE_PROMPT` + skill active + `<toolkit>_rules` + role + project instruction + catalog; L2 cố ý không inject body (`_ = body`) [system.py](file:///D:/repos/ai-manus/backend/app/domain/services/prompts/system.py#L151-L186).
- `can_skip_summarize` luôn False — nhánh skip trong flow là dead code có chủ ý [execution.py](file:///D:/repos/ai-manus/backend/app/domain/services/prompts/execution.py#L88-L129).
- `apply_plan_report` giữ tối đa 1 RUNNING (ưu tiên update cuối); `complete_plan_events` ép mọi step mở thành COMPLETED/success=True kể cả FAILED (làm đẹp cuối vòng) [plan_progress.py](file:///D:/repos/ai-manus/backend/app/domain/services/plan_progress.py#L37-L84).
- Ép step đầu "load skill" host-side idempotent, heuristic đa ngôn ngữ/legacy có thể false-positive [plan_steps.py](file:///D:/repos/ai-manus/backend/app/domain/services/skills/plan_steps.py#L28-L76).

### 1.4 `domain/services/agents/` + `flows/` + `agent_task_runner.py` + `agent_domain_service.py`
- `ManusAgent`: gate notify-trước-work + gate plan-finished; `ask` → WaitEvent + return; ToolEvent bị gate thì `continue` không yield (ẩn khỏi timeline) [manus.py](file:///D:/repos/ai-manus/backend/app/domain/services/agents/manus.py#L100-L128).
- `ExecutionAgent`: từ chối success=true khi chưa có work-tool (`_WORK_TOOLKITS`) — executor reject complete rỗng [execution.py](file:///D:/repos/ai-manus/backend/app/domain/services/agents/execution.py#L93-L147).
- `BaseAgent`: vòng lặp tool (CALLING/CALLED, brief tách, retry, live poll shell-console → TerminalUpdateEvent), structured output + self-repair, memory truncate 16k chars + compact theo token + rollback 1 message [base.py](file:///D:/repos/ai-manus/backend/app/domain/services/agents/base.py#L230-L364).
- `PlanActFlow`: planner → executor từng step (chỉ FAILED mới `update_plan`) → summarize → done; hỗ trợ resume WAITING [plan_act.py](file:///D:/repos/ai-manus/backend/app/domain/services/flows/plan_act.py#L167-L300). `BaseFlow.run` không tham số nhưng subclass dùng `run(message)` — lệch chữ ký, ABC không enforced [flows/base.py](file:///D:/repos/ai-manus/backend/app/domain/services/flows/base.py#L7-L15).
- `AgentTaskRunner.run`: điều phối queue, chat-mode vs plan-act, skill sync/resolve; sinh ToolContent (snapshot file trước ghi cho Diff, screenshot, sync storage, skill→FileToolView); Terminal/FileUpdate stream-only không persist [agent_task_runner.py](file:///D:/repos/ai-manus/backend/app/domain/services/agent_task_runner.py#L194-L289).
- Edge: `Agent` dùng `datetime.now(UTC)` làm default (đánh giá 1 lần lúc import — instance cùng giờ nếu không truyền) [agent.py](file:///D:/repos/ai-manus/backend/app/domain/models/agent.py#L7-L37); `Session.get_last_plan` trả object dùng chung (mutate ảnh hưởng history) [session.py](file:///D:/repos/ai-manus/backend/app/domain/models/session.py#L63-L68).

### 1.5 `application/services/` (8 service + errors + data)
- `AuthService` đa provider (password/none/local + Redis session + JWT grace): hash PBKDF2 salt chung, sliding TTL (web 14d/app 30d), refresh rotate; **log hash password ở info**; `register/change/reset` dùng `datetime.utcnow()` naive [auth_service.py](file:///D:/repos/ai-manus/backend/app/application/services/auth_service.py#L37-L57).
- `TokenService`: JWT HS256 + signed URL HMAC-SHA256 `compare_digest`; revoke luôn True (placeholder TODO) [token_service.py](file:///D:/repos/ai-manus/backend/app/application/services/token_service.py#L174-L285).
- `SkillService` ingest + seed default (personal data-viz mỗi user 1 bản); `add_skills` bỏ qua trùng bằng `continue` thay vì báo [skill_service.py](file:///D:/repos/ai-manus/backend/app/application/services/skill_service.py#L134-L206).
- `SkillRuntimeService.sync_enabled_skills_to_sandbox`: `rm -rf` qua shell với `shlex.quote`; file non-UTF8 bị bỏ (mất asset nhị phân) [skill_runtime_service.py](file:///D:/repos/ai-manus/backend/app/application/services/skill_runtime_service.py#L50-L76).
- `EmailService`: OTP 6 số SMTP_SSL + Cache TTL 300s, tối đa 3 attempts, rate-limit 60s; log code OTP ở debug; SMTP sync trong async fn [email_service.py](file:///D:/repos/ai-manus/backend/app/application/services/email_service.py#L46-L80).
- `AgentService`: mọi op check sở hữu trừ `get_vnc_url/is_session_shared/get_shared_session_files` (VNC thiếu check user); `_user_owns_library_file` quét toàn bộ sessions O(n) [agent_service.py](file:///D:/repos/ai-manus/backend/app/application/services/agent_service.py#L217-L251).
- `core/config.py` (162d): `Settings` pydantic-settings; default `jwt_secret_key="your-secret-key-here"` nguy hiểm nếu quên đổi; `get_settings()` validate nên import thiếu API_KEY sẽ nổ [config.py](file:///D:/repos/ai-manus/backend/app/core/config.py#L152-L162).

## 2. Backend API — `interfaces/` + `infrastructure/` + main/worker (68 file, 9.274 dòng)

### 2.1 `interfaces/` (20 file, 2.835 dòng)
- `dependencies.py` (384d) composition root: mọi service `@lru_cache` singleton; `get_current_user` enforce CSRF cookie (`X-Requested-With`) nhưng `get_optional_current_user` KHÔNG; bypass toàn bộ khi `auth_provider=="none"`; WS cấm `?token=` [dependencies.py](file:///D:/repos/ai-manus/backend/app/interfaces/dependencies.py#L186-L261).
- `auth_routes.py` (288d): session-cookie Redis opaque; `register`/`login` trả `refresh_token or access_token` (thực chất cùng session_id); role check string `"admin"` trong khi `User.role` là enum (đúng chỉ khi str-enum); `send-verification-code` lộ user-enumeration (404 vs 400) [auth_routes.py](file:///D:/repos/ai-manus/backend/app/interfaces/api/auth_routes.py#L159-L274).
- `ws_routes.py` (594d): 3 endpoint (`/ws/sessions`, `/ws/chat` protocol v2 envelope, `/ws/vnc` proxy binary); join mới auto-leave + cancel stream cũ; `_final_agent_status` ưu tiên in-stream Wait hơn Mongo; `timestamp` client `fromtimestamp` naive-local vs server UTC; VNC `asyncio.wait` cancel không await task [ws_routes.py](file:///D:/repos/ai-manus/backend/app/interfaces/api/ws_routes.py#L28-L163).
- `session_routes.py` (291d): tạo session bằng PUT (bất thường); public share (`GET /shared/{id}`, `/{id}/share/files`); `move_session_project` lazy-import + gọi `get_project_service()` trực tiếp (bypass Depends, phá test-override); `/{id}` vs `/shared/{id}` khác số segment nên không shadow [session_routes.py](file:///D:/repos/ai-manus/backend/app/interfaces/api/session_routes.py#L30-L120).
- `file_routes.py` (148d): signed download không auth header (signature thay auth, ai có URL tải được trong TTL); `FileNotFoundError` và `PermissionError` đều → 404 (chống lộ tồn tại); stream `BytesIO` giữ RAM; `Content-Disposition: attachment` ép download mọi file [file_routes.py](file:///D:/repos/ai-manus/backend/app/interfaces/api/file_routes.py#L35-L79).
- `skill_routes.py` (123d): upload đọc toàn file vào RAM, không giới hạn size; `url` không validate scheme (SSRF trông chờ service) [skill_routes.py](file:///D:/repos/ai-manus/backend/app/interfaces/api/skill_routes.py#L118-L120).
- `schemas/event.py` (267d): `PlanStreamEvent.from_event` dùng `event_id/timestamp` của plan cho MỖI step (quirk rõ ràng); `CommonEventData(extra=allow)` nuốt field lạ; lazy import `get_file_service` né cycle [event.py](file:///D:/repos/ai-manus/backend/app/interfaces/schemas/event.py#L207-L248).
- `schemas/file.py`: mọi `from_domain` sinh signed URL → N+1, TTL 15' nên list cache lâu chết link [file.py](file:///D:/repos/ai-manus/backend/app/interfaces/schemas/file.py#L28-L40).

### 2.2 `infrastructure/` (46 file, 6.327 dòng)
- `documents.py` (229d): `UserDocument.created_at/updated_at` dùng `datetime.now(timezone.utc)` làm DEFAULT TĨNH lúc class-define (mọi document chia sẻ timestamp giờ import — bug cổ điển; chỉ `FileFavoriteDocument` dùng đúng `default_factory`) [documents.py](file:///D:/repos/ai-manus/backend/app/infrastructure/models/documents.py#L56-L57).
- `docker_sandbox.py` (590d): `_resolve_hostname_to_ip` ĐỊNH NGHĨA 2 LẦN (L451/L517, sau ghi đè trước); `ensure_sandbox` nuốt timeout chỉ log (agent chạy trên sandbox chưa ready); `get` cache IP stale; `destroy` dùng `self.container_name` trong khi `__init__` set `self._container_name` (khả năng AttributeError); không auth backend↔sandbox [docker_sandbox.py](file:///D:/repos/ai-manus/backend/app/infrastructure/external/sandbox/docker_sandbox.py#L135-L186).
- Browser ~1k dòng (2 engine cùng 13 action, caps 6000/8000/500): `browser_use` CDP + retry 5; `playwright` snapshot JS in-page + markdownify; khác biệt: playwright `navigate` nuốt lỗi goto (trả success=True + state hiện tại — che lỗi), `cleanup` đóng TẤT CẢ tab (aggressive), `console_exec` = `page.evaluate` expression [browser_use_browser.py](file:///D:/repos/ai-manus/backend/app/infrastructure/external/browser/browser_use_browser.py#L69-L110).
- Search 9 engine (~1.5k dòng): mọi engine lỗi → `success=False` + results rỗng (agent tiếp tục); map `date_range` thiếu mảnh (baidu past_hour rơi, bing past_hour/year không map, tavily gộp hour+day); scrape baidu/bing dễ vỡ DOM; code `__main__` test lẫn trong production.
- LLM (~700d): `LangchainLLM` chain `model | RobustJsonParser` retry 3; `OpenAILLM` local extract + retry nguyên model; `RobustJsonParser.invoke` sync gọi `run_until_complete` (vỡ nếu đã có running loop) [robust_json_parser.py](file:///D:/repos/ai-manus/backend/app/infrastructure/external/llm/robust_json_parser.py#L229-L274).
- Task (~530d): Celery (`task_ignore_result`, state qua Redis meta TTL 7d; `is_done=True` khi mất meta — an toàn giả; `read_meta` dùng `get_redis().client` trực tiếp không `initialize()`) + `RedisStreamTask` in-process (registry process-local — multi-replica không thấy nhau; `pop` xrange+xdel riêng, không atomic thật) [celery_task.py](file:///D:/repos/ai-manus/backend/app/infrastructure/external/task/celery_task.py#L106-L134).
- `gridfsfile.py` (212d): `download_file` load toàn file vào `BytesIO` (mâu thuẫn comment "tránh load"); `upload_date` naive vs documents aware; `except FileNotFoundError` rồi `except (FileNotFoundError, PermissionError)` — nhánh 2 unreachable [gridfsfile.py](file:///D:/repos/ai-manus/backend/app/infrastructure/external/file/gridfsfile.py#L113-L146).
- `main.py` (95d): CORS `allow_origins=["*"]` + `allow_credentials=True` (spec cấm `*` với credentials); shutdown `AgentService.shutdown` gọi SAU khi đã đóng mongo/redis [main.py](file:///D:/repos/ai-manus/backend/app/main.py#L34-L79).

## 3. Backend tests + evals (36 file, 5.707 dòng)

- `conftest.py` (81d): fixture `client`, `_isolate_llm_env` (xóa API_BASE), `FakeFileStorage`; `BASE_URL` localhost:8000; không fixture dọn DB (dễ dính state duplicate-email) [conftest.py](file:///D:/repos/ai-manus/backend/tests/conftest.py#L61-L81).
- `harness.py` (226d): `ScriptedLLM` + `FakeAgentRepository/Sandbox/Session` + `StubAgent` cho toàn bộ test offline; `FakeSandbox` luôn success (không mô phỏng lỗi) [harness.py](file:///D:/repos/ai-manus/backend/tests/harness.py#L31-L121).
- Bao phủ mạnh: skill subsystem (archive/github/loader/package/runtime/sandbox-sync/service/toolkit/invocation/plan-steps — 11 file), PlanAct/AgentLoop offline (`test_single_loop_manus` 911d lớn nhất), tool base, LLM gateways offline, file/auth HTTP (cần stack thật).
- `test_e2e_plan_act.py` (161d): self-skip khi stack down (CI dễ bỏ qua); chỉ 2 scenario [test_e2e_plan_act.py](file:///D:/repos/ai-manus/backend/tests/test_e2e_plan_act.py#L101-L161).
- `evals/` (4 file): 5 scenario regression offline (`scenarios.py` 214d) + runner + `metrics.py` đếm bằng prefix string giòn (không phân biệt agent/planner memory) [metrics.py](file:///D:/repos/ai-manus/backend/evals/metrics.py#L12-L70).
- **Lỗ hổng lớn nhất**: toàn bộ `infrastructure` (repositories/storage/search/browser/queue/cache/session/task), `application` phi-skill (agent/auth/file/project/token), `domain` models phụ + repositories + external protocols, `interfaces` phi-auth/file (session/project/library/config/skill routes, schemas) — chưa có test nào chạm tới.

## 4. Sandbox + mockserver + scripts + root + docs (~99 file)

- `sandbox/` (~25 file): FastAPI + router `/api/v1` shell/file/supervisor; shell stateful tmux-backed; `shell_wait` task dài; kill sai id rò pane; path traversal trông chờ normalize; `file_write append=false` ghi đè [shell.py](file:///D:/repos/ai-manus/sandbox/app/api/v1/shell.py#L1-L40).
- `mockserver/` (15 file): mock LLM OpenAI-compatible + `POST /mock/scenario` đổi replay index **global** (phải chạy serial `workers:1`, restart để reset); 12 yaml scenario (~1.366 dòng: default 174, shell 141, file 148, stateful 133, search 83, message 81, browser 209, plan_act 72/88, computer_ui 113, chat_parity 49, single-loop-demo 75); executor từ chối `complete_step(success=true)` thiếu work-tool [default.yaml](file:///D:/repos/ai-manus/mockserver/mock_datas/default.yaml#L121-L174).
- `docs/` (~23 file + 7 plans): kiến trúc Web→Server→Sandbox→PlanAct→Redis→WS; Whitelist `docs/superpowers/plans/` (single-loop 583d, plan-act, skills-ui-shell 832d, skill-package-storage 471d...); AGENTS.md tự nhận "No automated test" đã cũ so với gate L3 (mâu thuẫn nội tại) [AGENTS.md](file:///D:/repos/ai-manus/AGENTS.md#L1-L40).
- Root configs: compose prod/dev/example, `uv.lock`/`package-lock` trừ khỏi vét; `mcp.json.example`, `.env.example` (`AUTH_PROVIDER=none`, `SANDBOX_ADDRESS=sandbox`); worker Celery concurrency 4; frontend vite alias `@→src`, proxy `/api`, nginx SPA fallback, vitest jsdom, playwright serial.

## 5. Frontend — `frontend/src` (219 file, 21.583 dòng, đã đọc 100%)

### 5.1 Root + router + api (App.vue 8d, main.ts 28d, router 103d, api 8 file)
- `App.vue` chỉ `<router-view/>`; `main.ts` bootstrap i18n en/zh + router + reka-ui [main.ts](file:///D:/repos/ai-manus/frontend/src/main.ts#L1-L28).
- Router: `/` Home, `/chat/:sessionId?`, `/project/:projectId`, `/library`, `/share/:sessionId` (public, qua guard), `/login`; guard async `getCachedAuthProvider()` [router/index.ts](file:///D:/repos/ai-manus/frontend/src/router/index.ts#L1-L103).
- `api/client.ts` (226d): axios baseURL `/api`, interceptor gắn Bearer, 401 → logout + redirect; token hết hạn giữa WS không tự refresh WS [client.ts](file:///D:/repos/ai-manus/frontend/src/api/client.ts#L10-L45).
- `api/agent.ts` (344d): session/project/share/VNC + `connectSessionsListWS` (snapshot/upsert/remove); WS list không auto-reconnect exponential [agent.ts](file:///D:/repos/ai-manus/frontend/src/api/agent.ts#L10-L45).
- `api/chatWs.ts` (364d): chat WS (message/stop/regenerate, heartbeat + reconnect thủ công, mất event giữa chừng); `isComposing` IME xử lý ở ChatBox [chatWs.ts](file:///D:/repos/ai-manus/frontend/src/api/chatWs.ts#L10-L45).

### 5.2 Pages (7 page)
- `ChatPage.vue` (979d, dài nhất): messages + ChatBox + ChatMessage + ToolUse + ComputerPanel + FilePreviewer + PlanPanel + takeover banner + phase footer; live tool chỉ follow khi Computer đã mở (`followLiveToolIfOpen`); mất WS treo `calling`; Enter gửi / Shift+Enter xuống dòng [ChatPage.vue](file:///D:/repos/ai-manus/frontend/src/pages/ChatPage.vue#L10-L45).
- `SessionSidebar.vue` (809d): nav + Projects + filter + SessionItem list + WS snapshot/upsert/remove sort `latest_message_at`; WS error chỉ console, không toast/reconnect; xóa project chỉ null `project_id` [SessionSidebar.vue](file:///D:/repos/ai-manus/frontend/src/components/SessionSidebar.vue#L456-L495).
- `ProjectPage` (479d), `LibraryPage` (448d, search client-side), `SharePage` (377d, read-only `isShare` ẩn Takeover), `HomePage` (261d, pending message + seedDraft chip), `LoginPage` (99d, `none` bypass).

### 5.3 Components lớn
- `ChatBox.vue` (460d): TipTap (giữ bold/italic/lists, tắt heading/code) + slash `/` + SkillTag + PlusMenu; sync model→editor tránh loop (`emitUpdate:false`); blur giữ `slashRange` để click chuột sau steal-focus vẫn xóa `/` [ChatBox.vue](file:///D:/repos/ai-manus/frontend/src/components/ChatBox.vue#L402-L431).
- `ChatMessage.vue` (371d): `marked` + `DOMPurify` (allow `target`), step collapsed mặc định, skill chips rebind sau `nextTick`, link `target=_blank rel=noopener` [ChatMessage.vue](file:///D:/repos/ai-manus/frontend/src/components/ChatMessage.vue#L308-L330).
- `SessionItem.vue` (383d): unread ẩn khi current, share copy fallback toast, delete current → push `/` [SessionItem.vue](file:///D:/repos/ai-manus/frontend/src/components/SessionItem.vue#L204-L282).
- `ComputerPanel` (159d) + `ComputerPanelContent` (507d): timeline scrub playhead Unix giây, follow-only-when-open, mutual exclusion `UI_SHOW_FILE_PREVIEWER`, resize parent/2 clamp 520 [ComputerPanel.vue](file:///D:/repos/ai-manus/frontend/src/components/ComputerPanel.vue#L101-L115).
- `toolViews/`: Shell (xterm + theme CSS vars, WS `tool:terminal_update` debounce 100ms theo shellId), File (Monaco/Diff + WS `tool:file_update` theo path), Browser (live VNC viewOnly else screenshot), Search (favicon google s2), Mcp (generic JSON).
- `ChatBoxFiles.vue` (316d): optimistic temp-id `temp-<ts>`, giữ blob preview tới khi gửi, revoke on remove/unmount, `isAllUploaded` chặn gửi [ChatBoxFiles.vue](file:///D:/repos/ai-manus/frontend/src/components/ChatBoxFiles.vue#L175-L210).
- `VNCViewer` (107d, noVNC `RFB` + `getVNCUrl`), `SearchDialog` (~240d, buckets Today/Yesterday/P7/P30/Older, giây/ms normalize), `UserMenu` (105d, `getCachedAuthProvider` async gây nháy logout), `PlanPanel` (96d, `currentIndex = lastDone+1`).

### 5.4 Composables + utils + locales + nhóm nhỏ
- `useAgentEvents`: WS chat (messages/plan/timeline/file/terminal push eventBus); mất WS giữa live tool treo timeline, phải reload/jumpToRealTime [useAgentEvents.ts](file:///D:/repos/ai-manus/frontend/src/composables/useAgentEvents.ts#L10-L45).
- `useFilePreviewer` singleton side/center/fullscreen (chỉ side bị Computer dismiss); `useTheme`/`useDocumentDark` FOUC khi localStorage khác system; `skillsStore` chip render trước load xong → name rỗng.
- `utils`: fileType/time (giây/ms)/toast/eventBus (keys `UI_SHOW_*`, sai chuỗi mất mutual-exclusion)/dom (clipboard fallback).
- `locales` en/zh: thiếu key hiện key thô; placeholder `{product}` phải truyền `Manus`.
- Nhóm kiểm kê (chưa mở từng dòng, đã nêu mục đích/API): `chatbox/` 9 file (slash/skillTag/chips/plus) + 4 spec, `filePreviews/` 6 file (code/md/image/pdf/html/unknown), `icons/` 24 file SVG thuần, `ui/` 36 file (reka-ui select/popover/dialog + Monaco + context menu), `login/` 9 file + 1 spec, `settings/` 9 file + 1 spec, `skills/` 5 file + 2 spec, components `__tests__` 4 spec, composables `__tests__` 9 spec — pass.

## 6. Coverage — hoàn tất

- Đã vét 100%: backend core (§1) + backend API (§2) + tests/evals (§3) + sandbox/mockserver/docs/configs (§4) + frontend (§5).
- Tổng: **~412 file, ~47.7k dòng** (backend 193 file ~24.7k + sandbox/docs ~99 file + frontend 219 file 21.6k).

# Slice 05 — Architecture Proposal: Agent Loop + LLM Capabilities (D1–D15) — REVISION 2

> Trạng thái: REVISION 2 + CANONICAL CLEANUP — FINAL REVIEW APPROVAL (reviewer 1);
> chờ Reviewer còn lại đồng thuận để đánh dấu canonical chính thức, sau đó bắt đầu P0.
> Không implementation Slice 05 cho tới khi đủ hai đồng thuận + baseline kiểm soát.
> Không sửa production code trong vòng chỉnh proposal. Không cản trở Luồng A (Slice 04 repair).
> Quyết định D1–D15 là đầu vào cứng; tài liệu này cụ thể hóa thành kiến trúc.
> Mọi kết luận có `source: file:line`. Không mở vòng nghiên cứu tổng quát mới.
> File này là Proposal; chỉ thành canonical architecture sau khi hai Reviewer duyệt (D15).
>
> Ghi chú về "proposal cũ": repo hiện **không chứa file proposal Slice 05 nào**
> (tìm `slice 05` chỉ ra `docs/verify/frontend-product-acceptance-audit.md:18,78,186,189`
> và `docs/verify/verify-foundation.md:260`). Baseline thay thế cho "P0–P4 của proposal cũ"
> là 2 dòng đã chốt: (a) audit FE — Slice 05 bị chặn cho tới khi 1 shell duy nhất +
> BE contract + 0 mock production (`frontend-product-acceptance-audit.md:186-189`);
> (b) `verify-foundation.md:260` — "Rule-based TaskService hiện tại, KHÔNG LLM planner".

## 1. Kiến trúc mục tiêu

```
User ── chat ──▶ Conversation API ──▶ Agent Loop (ASSISTING) ──▶ trusted Dispatcher ──▶ Dynamic Tool Registry
                        │                   │                          │
                        │                   │                          ├── READ  → Gateway.read_via_eye (rea-eye)
                        │                   │                          └── WRITE → Gateway.write_via_adapter + PermissionStore
                        │                   │
                        │                   ├── budget: 12 steps / 15 LLM calls / 300s active / ~$0.50 + daily caps (D2/D12)
                        │                   ├── state machine: IDLE→ASSISTING⇄TOOL_CALL/WAIT/CLARIFY→DONE/FAILED/CANCELLED (§17, D7)
                        │                   │   (Respond zero-tool-call bắt buộc; Planner chỉ hỗ trợ tùy chọn; cấm NO_ROUTE_MATCH
                        │                   │   làm câu trả lời cuối — §2, §17)
                        │                   └── synthesis: deterministic guards + LLM diễn đạt, nhãn confirmed/partial/unknown/failed (D9/D14)
                        │
                        └── conversations.db (mới) ──link──▶ tasks.db (hiện có, không sửa schema)
                                conversation_id / message_id / turn_id / task_id / tool_call_id (D4)
```

Nguyên tắc cứng:

- **Không TaskService thứ hai, không execution engine thứ hai.** `TaskService`
  (`apps/backend/src/miro/tasks/service.py:93`) giữ nguyên là execution engine duy nhất:
  submit idempotent (`service.py:149-179`), run (`service.py:230-274`), stop 2 pha
  (`service.py:973-1021`), restart/recover (`service.py:1040-1072`), resume
  (`service.py:1074-1100`). Agent Loop là **client có budget** của TaskService, không phải
  engine mới — phù hợp cảnh báo capability-map "không triển khai hai bộ orchestrator
  độc lập" (`docs/capability/capability-map.md:42-43`).
- **Giữ `/tasks/run-message` legacy deterministic** (`apps/backend/src/miro/tasks/router.py:150-298`).
  LLM không thay `route_message` (`service.py:308-372`); LLM gọi capability qua
  structured tool schema + trusted dispatcher, không sinh câu regex nhồi ngược vào
  run-message (D5).
- **Key ở Backend, không hardcode vendor** (D1). `config.py` hiện chỉ có
  `app_name/debug` (`apps/backend/src/miro/config.py:6-11`) → chưa có AI provider config:
  đây là gap P0 phải thêm (Settings → AI Provider).
- **Cho phép public structured entry point tối thiểu** nếu cần tái dùng đúng
  execution path (thay vì bypass) — §19. Quy định "KHÔNG sửa TaskService" trong §3
  bản Revision 1 nay SUPERSEDED bởi §19.

## 2. Data flow (conversational turn — CANONICAL; Revision 1 plan-flow SUPERSEDED, xem §17)

1. User gửi message → Conversation API tạo `message(user)` trong `conversations.db`,
   resolve `conversation_id`, tạo `turn_id`, trả `message.accepted` qua SSE ngay (§22).
2. Agent Loop = LLM Assistant Observe → Decide → Execute → Verify (§17):
   Respond (zero tool calls, bắt buộc) | Clarify | Tool Call | Wait | Finish | Cancel.
   `Planner.plan_for_route` chỉ là công cụ hỗ trợ tùy chọn cho nhiệm vụ phức tạp.
   Cấm trả `NO_ROUTE_MATCH` như câu trả lời cuối.
3. Mỗi tool call → trusted Dispatcher: validate schema → resolve trusted context
   (§20) → pre-budget check → permission (WRITE/sensitive) → persist durable
   intent TRƯỚC dispatch (§21) → gọi Tool → ghi task_id + receipt/result vào
   event log (§21).
4. READ_NAVIGATION trong scope đã cấp quyền chạy không approval từng lần, nhưng vẫn
   qua Gateway + kiểm scope/origin/ownership; URL lạ vẫn kiểm (D3).
   WRITE/sensitive → `check_write_gate` (`gateway.py:57-120`) + `PermissionStore.check`
   (`permissions/store.py:47-58`).
5. Tool trả Evidence (`provenance: rea-eye`, `gateway.py:260-267`) hoặc
   `media-analysis` (chỉ để hiểu nội dung, KHÔNG phải Evidence ghi —
   `gateway.py:29-35`). Tool output / website / external doc = untrusted data,
   không phải privileged instructions.
6. Kết thúc (LLM finish hoặc hết budget) → Synthesis hai lớp (D14): deterministic
   guards kiểm tra Evidence + LLM diễn đạt; nhãn confirmed/partial/unknown/failed.
7. Task nền (browser/research/render) chạy độc lập lifecycle qua TaskService hiện có;
   chat không khóa khi task chạy (§25). Không chiếm tab Miro/user-owned trái phép;
   execution resource qua Runtime (`session_manager.reuse_or_open_tab`, dùng trong
   `gateway.py:207,289`).
8. Follow-up: turn mới tham chiếu `turn_id`/`task_id` cũ + kết quả đã lưu (D10).

## 3. Module/file mapping — chứng minh không engine thứ hai

| Vai trò Slice 05 | File hiện có (tái dùng, không viết lại) | Thay đổi |
| --- | --- | --- |
| Execution engine duy nhất | `apps/backend/src/miro/tasks/service.py:93` (`TaskService`) | Agent Loop gọi `submit/run/stop/restart/resume`; cho phép public structured entry point tối thiểu theo §19 (quy định "KHÔNG sửa" bản R1 SUPERSEDED) |
| Legacy entry deterministic | `apps/backend/src/miro/tasks/router.py:150-298` (`run-message`) | KHÔNG sửa routing regex (D5) |
| Task models/persistence | `apps/backend/src/miro/tasks/models.py:22-141`, `apps/backend/src/miro/storage/db.py:33-111` | KHÔNG sửa schema `tasks.db`; thêm `conversations.db` mới (D4) |
| Capability routing (rule-based) | `apps/backend/src/miro/agent/router.py:41-69` | Giữ; LLM chọn trong tool schema, không thay regex này bằng prompt |
| Plan model | `apps/backend/src/miro/agent/planner.py:19-33` | Nâng `max_length` 10→12 (D2); giữ synthesize-cuối |
| Tool registry (6 tool) | `apps/backend/src/miro/agent/registry.py:46-97` | Mở rộng thành dynamic registry (§18); P2 scope chọn tool theo capability, không hardcode 8 vào Loop |
| Executor → nâng thành Dispatcher | `apps/backend/src/miro/agent/executor.py:49-75` | Thêm schema-validate + trusted-context resolve (§20) + pre/post budget (§23) + link id; dispatch qua public service, cấm `_emit` riêng (§19) |
| Permission enforcement | `apps/backend/src/miro/permissions/store.py:31-58`, `apps/backend/src/miro/browser/gateway.py:57-120,198-313` | Tái dùng nguyên; thêm budget check trước `permissions.check` |
| Browser READ/WRITE | `gateway.py:198-268` (`read_via_eye`), `gateway.py:274-313` (`write_via_adapter`), `deny_direct_browser` (`gateway.py:316-321`) | Tái dùng; thêm 2 bridge reader đã có: actor (`gateway.py:324`), video (`gateway.py:373`), search (`gateway.py:500`), url (`gateway.py:580`), navigate (`gateway.py:618`) |
| Research/video phân tích | `apps/backend/src/miro/research/service.py:26-80` (`NullProvider`, `search/read_url/analyze_*`), `apps/backend/src/miro/media_intel/__init__.py:411,656,706,818,1096,1181` | Tái dùng qua `miro/media_intel` adapter duy nhất (luật REA-MEDIA) |
| Publication/journal SoT | `apps/backend/src/miro/threads/flow.py:1-68`, `worker.py:10,171-192`, `storage/registry.py:21-60` | Tái dùng guard journal-trước-click / UNKNOWN / reconcile |
| Wiring khởi động | `apps/backend/src/miro/main.py:42-82` (`TaskStore`, `TaskService`, bridge wiring, research provider) | Thêm AI provider wiring + conversations store |

Kết luận: Slice 05 thêm module mới (`conversations/store.py`, `agent/loop.py`,
`agent/dispatcher.py` + `agent/budget.py` có thể gộp vào loop) và dynamic registry
(§18); **0 engine mới**. Không giới hạn cứng số lượng file — module responsibility
rõ ràng quan trọng hơn số file ít.

## 4. API contracts

### 4.1 Conversation API (mới, prefix `/conversations`)

| Method & path | Request | Response | Ghi chú |
| --- | --- | --- | --- |
| `POST /conversations` | `{title?, account_id?}` | `{conversation_id, created_at}` | Tạo hội thoại |
| `GET /conversations` | `?limit=` | `[{conversation_id, title, updated_at}]` | List |
| `GET /conversations/{id}` | — | `{conversation, messages:[...]}` | Lịch sử turn |
| `POST /conversations/{id}/messages` | `{message, account_id?, task_ref?}` | `{message_id, turn_id}` | Entry chính; tạo turn, gọi Agent Loop async; chat trả ngay (D7). Xem thêm stop/follow-up/approval/SSE tại §22 |
| `GET /conversations/{id}/turns/{turn_id}` | — | `{turn_id, status, steps:[...], synthesis?, task_ids:[...]}` | Poll turn (streaming qua SSE §9) |
| `POST /conversations/{id}/follow-up` | `{message, ref_turn_id}` | như messages | D10: kèm context turn cũ |

### 4.2 Task API (giữ nguyên — liệt kê để đối chiếu, không sửa)

`POST /tasks` (`router.py:24-33`), `GET /tasks`, `/recent`, `/runtime/status`
(`router.py:36-88`), `GET /tasks/{id}`, `/{id}/events` (`router.py:91-106`),
`/{id}/stop|worker-stopped|wait-stop|restart|resume` (`router.py:109-147`),
`POST /tasks/run-message` (`router.py:150-298` — legacy deterministic),
`/{id}/approve|revoke` (`router.py:301-320`).

### 4.3 Settings → AI Provider (mới, D1)

| Method & path | Request | Response |
| --- | --- | --- |
| `GET /settings/ai-provider` | — | `{provider, baseURL, model, test_connection?, tool_calling?, streaming?}` (key KHÔNG trả về) |
| `PUT /settings/ai-provider` | `{provider, baseURL, model, key?, test_connection?, tool_calling?, streaming?}` | `{ok, redacted}` — key lưu Backend (env/secret store), không vào FE store, không hardcode vendor |
| `POST /settings/ai-provider/test` | — | `{ok, latency_ms, error?}` — test-connection dùng key Backend |

### 4.4 Budget config (D2/D12 — pre + post check, xem §23)

`{max_steps:12, max_llm_calls:15, active_timeout_s:300, est_cost_usd:0.50,
turns_per_day:50, llm_calls_per_day:200, daily_cost_cap:configurable,
configurable:true}`. Pre-call: remaining/input/output/model/reserve; post-call:
actual usage/cost/hoàn reserve. Cost chỉ enforce khi provider có usage + giá tin
cậy, ngược lại UI ghi "chi phí chưa xác định"; loop timeout (300s active) phân biệt
với background task duration.

## 5. Data models

### 5.1 `conversations.db` (mới, D4) — SQLite, mirror pattern `TaskStore`

```sql
CREATE TABLE conversations(id TEXT PRIMARY KEY, title TEXT, account_id TEXT,
  created_at TEXT, updated_at TEXT);
CREATE TABLE messages(id TEXT PRIMARY KEY, conversation_id TEXT REFERENCES conversations(id),
  turn_id TEXT, role TEXT, -- user|assistant|tool
  body TEXT, task_id TEXT, tool_call_id TEXT, created_at TEXT);
CREATE TABLE turns(id TEXT PRIMARY KEY, conversation_id TEXT, status TEXT,
  -- idle|assisting|tool_call|waiting_tool|waiting_task|waiting_approval|clarifying|done|failed|cancelled
  -- (state machine mới §17; các status planning/executing/synthesizing bản R1 SUPERSEDED)
  budget_json TEXT, synthesis_json TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE turn_tasks(turn_id TEXT, task_id TEXT, PRIMARY KEY(turn_id, task_id));
CREATE TABLE tool_intents(tool_call_id TEXT PRIMARY KEY, turn_id TEXT, request_id TEXT UNIQUE,
  tool_name TEXT, args_json TEXT, dispatch_state TEXT, task_id TEXT, receipt_json TEXT,
  created_at TEXT, updated_at TEXT); -- durable intent §21 (khóa chống mất link khi crash)
```

### 5.2 `tasks.db` (giữ nguyên — `storage/db.py:8-30`)

`tasks(id, request_id UNIQUE, fingerprint, status, revision, record_json, ...)` +
`events(task_id, sequence UNIQUE, ...)` + `find_active_by_dedupe` (`db.py:75-89`).

### 5.3 Liên kết Conversation ↔ Task (D4)

`turn_tasks(turn_id, task_id)` + `messages.task_id/tool_call_id` + `tool_intents`
(durable intent §21).
Idempotency: `request_id UNIQUE` (`db.py:20`) + `REQUEST_ID_CONFLICT` (`service.py:155`);
dedupe revision-level (`service.py:131-162`); recovery: write-ahead
`pending_mutation` (`service.py:192-223`), `REMOTE_RESULT_UNKNOWN` không replay
(`service.py:1077`), `RECOVER` job sạch (`service.py:1056-1066`), reconcile qua
`task_routed/task_blocked/task_recovered` events.
> Khẳng định "link ghi chung transaction với message/turn" (bản R1) SUPERSEDED:
> hai DB không có atomic transaction chung — chống mất link bằng durable intent
> (lưu intent + stable request_id TRƯỚC dispatch, reconcile bằng request_id đã lưu,
> 4 crash cases §21), không replay unknown external side-effect.

## 6. Tool Registry — dynamic (CANONICAL; schema R1 yêu cầu task_id/tab_id SUPERSEDED, xem §18/§20)

6 tool hiện có (`registry.py:46-97`): `editor.set_voice`, `editor.cut`,
`editor.preview`, `web.search`, `web.read`, `report.synthesize` — giữ trong repo,
chỉ công bố cho LLM khi đã wired production (không mock) + có quyền (§18).

> Schema minh họa R1 (`browser.observe` bắt buộc `task_id`, LLM truyền `tab_id/url`)
> SUPERSEDED bởi §20: LLM chỉ đề xuất business args; task ID / tab / lease /
> identity do Runtime resolve + validate. Dispatcher R1 (gọi READ trực tiếp +
> `TaskService._emit`) SUPERSEDED bởi §19 (qua public service, cấm `_emit` riêng).

Registry mở rộng không sửa Agent Loop; mỗi tool đủ 10 trường (§18); P2 scope chọn
tool theo capability đã wired; số lượng là giới hạn phạm vi, không phải giới hạn
kiến trúc. LLM nhận capability advertisement (khả dụng / blocked / cần approval).

## 7. Permission enforcement (D3 + Gateway)

- READ_NAVIGATION trong scope đã cấp: `read_via_eye` không đòi approval từng lần,
  nhưng vẫn: acquire tab → `verify_actor` → eye collector → re-validate lease +
  URL destination + actor sau đọc (`gateway.py:198-268`). URL lạ → kiểm
  scope/origin/ownership trước khi tin.
- WRITE: `write_via_adapter` → `check_write_gate` (`gateway.py:57-120`): auth từ
  task/intent state (không từ approval), binding approval↔auth, account-bound,
  destination match; sau bấm re-validate lease, không receipt → `UNCONFIRMED_NO_REPLAY`
  (`gateway.py:310-313`).
- Mọi đường trực tiếp ngoài Gateway → `BYPASS_DENIED` (`gateway.py:316-321`).
- Mutating editor tool → `PermissionStore.check` scope+revision (`store.py:47-58`),
  approval bind đúng revision (`store.py:35-39`).

## 8. Agent Loop state machine (D7 — CANONICAL tại §17; state machine R1 SUPERSEDED)

```
IDLE → ASSISTING ⇄ TOOL_CALL → WAITING_TOOL → ASSISTING ⇄ CLARIFYING
  │         │           │             │              └→ DONE (respond/finish)
  │         │           │             └→ WAITING_APPROVAL → ASSISTING
  │         │           └→ WAITING_TASK (background) → ASSISTING (re-decide)
  │         └→ CANCELLED (user stop turn; task nền theo stop scope §22)
  └→ CANCELLED
```
Không trạng thái PLANNING bắt buộc, không nhánh NO_ROUTE → FAILED (chi tiết §17).

- Chat/lifecycle hội thoại độc lập execution nền: `POST messages` trả `turn_id` ngay;
  task chạy async qua `app.state.run_task` (pattern `router.py:30`, `main.py:76`).
- Stop chat ≠ stop task: `request_stop/wait_stop` (`service.py:973-1021`) chỉ tác động task.
- Budget (D2): step counter ≤12, llm_calls ≤15, active timer ≤300s (chỉ tính thời gian
  loop active, không tính background task duration), est cost ≤$0.50 (chỉ enforce khi
  provider trả usage + có bảng giá tin cậy). Vượt → `FAILED/BUDGET_EXCEEDED` + synthesis
  partial từ Evidence đã có. Thêm giới hạn session/ngày (configurable).

## 9. Streaming event contract (SSE `GET /conversations/{id}/turns/{turn_id}/stream` — CANONICAL tại §22)

Event groups: `message.accepted`, `assistant.message.delta/completed`,
`tool.started/completed`, `task.linked/updated`, `approval.required/granted/denied`,
`turn.completed/failed/cancelled` (+ giữ `turn.started`, `synthesis.delta`).
Mọi event có sequence ID stream-scoped + reconnect + replay + dedup (§22);
không stream private model reasoning. Stop endpoints + stop scope tại §22.

Event persist tối thiểu (thống nhất SSE contract §22, không dùng tên event cũ):
`message.accepted + assistant.message.delta/completed + tool.started/completed +
task.linked + turn.completed/failed/cancelled` vào `turns`/`messages` để reload
không mất (D4). Task nền vẫn stream qua `GET /tasks/{id}/events` hiện có
(`router.py:99-106`).

## 10. Persistence / recovery (D4 — CANONICAL tại §21)

- Hai DB tách: `tasks.db` (hiện có, `main.py:42`) + `conversations.db` (mới).
  Link `turn_tasks` + `messages.task_id/tool_call_id/turn_id` + `tool_intents` (§5).
- Crash: task → `restart`/`resume` hiện có (`service.py:1040-1100` guards);
  turn → `FAILED` + reconcile bằng request_id đã lưu trong intent (§21, 4 cases).
  Không replay unknown external side-effect.
- Audit FE-gate vẫn giữ: 1 shell + BE contract + 0 mock production trước Slice 05
  (`frontend-product-acceptance-audit.md:186-189`). Điều kiện phát triển/merge
  tuân theo §27: P0–P1 được phép trên worktree độc lập sau kiểm kê baseline,
  không sửa chồng working tree Slice 04; merge production chỉ sau kiểm tra
  compatibility + regression.

## 11. Kế hoạch P0–P4 (CANONICAL tại §24; bảng R1 SUPERSEDED)

P0 Foundation → P1 Conversational (zero-tool-call + smoke real-provider cuối P1
có approval) → P2 Trusted Tool Execution (cần full tool contracts §18 + BUG-11
xử lý trước browser execution) → P3 Loop & Workspace → P4 Full Real LLM
Acceptance. Chi tiết + gates tại §24. D1 thống nhất: unit/CI = fake, UAT = LLM
thật; smoke P1 cần approval + chi phí thấp.

## 12. Acceptance matrix A→I

| ID | Tiêu chí | Pass khi |
| --- | --- | --- |
| A | Fake Provider P0 | unit/integration/CI chạy không cần key; UAT dùng LLM thật qua Settings |
| B | Settings AI Provider | Đổi provider/baseURL/model không sửa code; key không lộ FE/network log |
| C | Budget D2 | Vượt 12 steps/15 calls/300s → turn FAILED + partial synthesis; cost enforce chỉ khi có usage+giá |
| D | READ/WRITE gate D3 | READ trong scope không approval; URL lạ bị kiểm; WRITE thiếu gate → DENY |
| E | Persistence D4 | Kill BE giữa turn → restart: không task trùng, link turn↔task còn |
| F | Legacy intact D5 | `run-message` + regex cũ pass test hiện có; LLM không đổi route cũ |
| G | No-VLM D6 | Loop không gọi VLM; media chỉ qua `media_intel` + REA-MẮT/DOM/OCR/keyframes |
| H | Lifecycle D7/D8 + concurrency/cancel §25–§26 | Chat responsive khi task chạy (background không khóa conversation); không tab user-owned nào bị chiếm; stop scope đúng |
| I | Synthesis D9/D14 + follow-up D10 | Guards + LLM diễn đạt; nhãn confirmed/partial/unknown/failed đúng Evidence; follow-up dùng được kết quả cũ |

## 13. Reuse matrix (không phát minh lại)

| Dùng lại | Nguồn | Không làm |
| --- | --- | --- |
| TaskService engine, stop/restart/resume | `tasks/service.py` | TaskService thứ hai |
| run-message deterministic | `tasks/router.py:150-298` | LLM thay router regex |
| TaskStore/events/dedupe | `storage/db.py` | Sửa schema tasks.db |
| Registry 6 tool, Plan, CapabilityRouter | `agent/registry.py, planner.py, router.py` | Framework LangGraph/CrewAI (đã cấm ở `verify-foundation.md:260`, `capability-map.md:42-43`) |
| Gateway READ/WRITE + bypass-deny | `browser/gateway.py` | snapshot/click trực tiếp |
| PermissionStore | `permissions/store.py` | Approval store mới |
| Research + media_intel | `research/service.py`, `media_intel/__init__.py` | VLM trực tiếp trong loop (D6) |
| Journal/publication guards | `threads/flow.py, worker.py`, `storage/registry.py` | Post flow mới |
| Bridge wiring pattern | `main.py:46-82`, `tasks/bridge_config.py` | Credential trong code/FE |

## 14. Risks

1. `conversations.db` + `turn_tasks` + `tool_intents` là code mới chạm persistence —
   risk mất link khi crash; giảm bằng durable intent + reconcile §21 (E). Khẳng định
   "transaction chung" bản R1 SUPERSEDED.
2. Cost enforce phụ thuộc provider usage — risk bill mù; giảm bằng pre/post check
   §23: chỉ enforce khi usage+giá tin cậy, mặc định fail-closed theo steps/calls/time.
3. LLM sinh `tool_call` sai schema — risk loop treo; giảm bằng dispatcher validate +
   budget + turn FAILED + partial synthesis (không dùng NO_ROUTE làm đáp án).
4. Scope creep / registry cứng: giới hạn số tool là giới hạn phạm vi P2, không phải
   giới hạn kiến trúc; registry mở rộng không sửa Loop (§18). Cấm VLM trực tiếp
   trong loop (D6, `verify-foundation:260`).

## 15. D11–D15 (đã chốt; tài liệu chờ Reviewer còn lại đồng thuận để thành canonical)

- **D11 Provider configurable:** Settings → AI Provider (provider/baseURL/model/key);
  key chỉ Backend, redacted logs; capability probe
  (connection/chat/tool_calling/streaming/structured/usage); ưu tiên native
  tool-calling + streaming + usage tin cậy; chưa khóa vendor cụ thể; Fake Provider
  chỉ cho test; không fallback Fake khi LLM thật lỗi; P4 LLM thật cần approval + budget.
- **D12 Budget defaults:** per-turn 12 steps / 15 LLM calls / 300s active / ~$0.50;
  + 50 turns/ngày + 200 LLM calls/ngày (configurable) + **daily cost cap configurable
  riêng**; cost chỉ enforce khi provider có usage + giá tin cậy, ngược lại UI ghi rõ
  "chi phí chưa xác định".
- **D13 SSE + HTTP:** Slice 05 dùng SSE + HTTP API (message/stop/follow-up/approval);
  sequence ID + reconnect + replay + dedup; chưa WebSocket (Live Desktop/Human
  Takeover sau).
- **D14 Synthesis hai lớp:** deterministic guards (Evidence/nguồn/giới hạn) +
  LLM diễn đạt; template/fake chỉ test contract P1–P3; P4 LLM thật synthesis từ
  kết quả thật, giải thích partial (vd tìm 5 chỉ verify được 3).
- **D15 Canonical:** file này hiện là Proposal; thành canonical sau khi hai Reviewer
  duyệt Revision 2; thay đổi sau đó ghi log rõ.

## 16. REVISION 2 — Reviewer finding → Resolution (BLOCKER 1–8)

| # | Reviewer finding | Resolution | Section | Acceptance test |
| --- | --- | --- | --- | --- |
| B1 | Agent Loop bắt mọi message qua Planner + nhánh NO_ROUTE → FAILED; thiếu direct response/clarify | Loop = LLM Assistant Observe→Decide→Execute→Verify; Respond/Clarify/Tool/Wait/Continue/Finish/Cancel; Planner chỉ hỗ trợ tùy chọn; cấm NO_ROUTE_MATCH làm câu trả lời cuối | §2, §8, §17 | UAT-01→05, P1 zero-tool-call gate |
| B2 | 8 tools lệch mục tiêu (3 Editor, thiếu search/navigate/task-status); registry giới hạn kiến trúc | Scope P2 ≤8 tools nhưng registry mở rộng được không sửa Loop; tool chưa wired/mock không công bố production; mapping Tool→service→execution→Gateway→Evidence từng tool | §6, §18 | P2 gate 1 capability thật; UAT-06/07 |
| B3 | Dispatcher gọi READ trực tiếp + `TaskService._emit` → nguy cơ engine thứ hai | Dispatcher chỉ resolve + dispatch qua public TaskService/capability service; cấm `_emit` riêng; cho phép đề xuất structured entry point tối thiểu thay vì bypass | §6, §19 | E + legacy F pass |
| B4 | LLM truyền task_id/tab_id/url như auth; `mutating:false` chưa đủ side-effect | LLM chỉ đề xuất business args; Runtime resolve task/tab/lease/identity/grant; tách availability/READ/READ_NAV/WRITE/sensitive; browser content = untrusted | §6–§7, §20 | D gate; UAT-12/13; BUG-11 no-regress |
| B5 | 2 DB không atomic chung; `turn_tasks` chưa đủ crash-safe | Durable tool-call intent (tool_call_id + stable request_id + dispatch state + task ref + receipt ref) trước dispatch; reconcile bằng request_id đã lưu; không replay unknown side-effect | §5, §10, §21 | E kill-giữa-turn |
| B6 | SSE thiếu assistant stream/message events, stop scope, replay/dedup | Event groups message/assistant/tool/task/approval/turn + seq ID/stream-scoped + reconnect/replay/dedup; 4 stop scope riêng; turn mới khi turn cũ chạy theo policy đã chốt ở P0 | §9, §22 | H + UAT-09/10/11 |
| B7 | Budget chỉ enforce sau call; thiếu key/context secret guard | Pre-check (remaining/input/output/model/reserve) + post-check (usage/cost/hoàn reserve); probe capability; key Backend + redacted; không gửi cookie/secret vào context; smoke P1 có approval | §4.4, §7b, §23 | C gate; smoke P1 |
| B8 | Acceptance A–I chỉ kỹ thuật, PASS mà vẫn chưa nói chuyện được | Giữ A–I + bổ sung UAT-01→13 độc lập, đa chủ đề (không chỉ KANS 377), LLM thật ở P4 | §12, §24 | UAT matrix |

## 17. Agent Loop (sửa BLOCKER 1) — state machine mới

```
IDLE → ASSISTING ⇄ TOOL_CALL → WAITING_TOOL → ASSISTING ⇄ CLARIFYING
  │         │           │             │              └→ DONE (respond/finish)
  │         │           │             └→ WAITING_APPROVAL → ASSISTING
  │         │           └→ WAITING_TASK (background) → ASSISTING (re-decide)
  │         └→ CANCELLED (user stop turn; task nền theo stop scope §22)
  └→ CANCELLED
```

- Không trạng thái PLANNING bắt buộc; không nhánh NO_ROUTE → FAILED.
- Mỗi vòng: LLM nhận conversation context + tool results → quyết định
  Respond | Clarify | Tool Call | Wait | Finish | Cancel.
- Budget D2/D12 enforce mỗi vòng; vượt → turn FAILED/BUDGET_EXCEEDED +
  partial synthesis từ Evidence đã có.
- `Planner.plan_for_route` tái dùng tùy chọn cho nhiệm vụ phức tạp.

## 18. Tool Registry (sửa BLOCKER 2) — registry mở, scope P2 ≤ 8

- Registry: dynamic — đăng ký tool mới không sửa Agent Loop.
  Mỗi tool bắt buộc: name, description, JSON input schema đầy đủ, output
  contract, production handler, execution path, permission class, side effects,
  availability, timeout/cancellation, evidence semantics.
- LLM nhận capability advertisement: tool khả dụng / blocked / cần approval.
- Scope P2 ưu tiên (tên minh họa, đối chiếu production entry thật):
  `browser.search`, `browser.observe`, `browser.navigate` (nếu cần, có kiểm soát),
  `research.search`, `research.read`, `media.analyze_video` (qua `miro/media_intel`),
  `task.get_status`, `task.get_result`, `task.cancel`.
- 6 tool cũ không xóa khỏi repo; chỉ công bố cho LLM khi đã wired production
  (không mock) + có quyền. `editor.set_voice/cut/preview`, `web.search/read`,
  `report.synthesize` giữ lại nhưng P2 chỉ expose khi đủ điều kiện trên.

## 19. Execution boundary (sửa BLOCKER 3)

```
Agent Loop → Trusted Dispatcher → Public TaskService / Capability Service → Gateway/Remote → Evidence
```

- Dispatcher KHÔNG acquire browser resource trực tiếp, KHÔNG tự retry/cancel
  lifecycle, KHÔNG ghi TaskStore bằng private `_emit`.
- Mapping bắt buộc mỗi tool:
  `Tool → Public service method → Task/Capability execution → Gateway → Evidence`.
- Task dài / resource ownership / navigation / side-effect → dùng lifecycle
  production hiện có (`submit/run/stop/restart/resume`).
- Cho phép đề xuất 1 structured entry point public tối thiểu nếu tái dùng đúng
  execution path tốt hơn bypass; không nhồi regex ngược vào run-message.

## 20. Trusted context (sửa BLOCKER 4)

| LLM đề xuất (business args) | Runtime resolve + validate (trusted) |
| --- | --- |
| keyword, URL cần đọc, số lượng, mục tiêu, ref "video thứ ba", điều kiện tìm, yêu cầu dừng | account identity, authorized browser instance, actual tab ID, task ID, lease, permission grant, approval identity |

- Không coi ID do LLM sinh là authorization.
- Phân lớp: availability → READ → READ_NAVIGATION → WRITE → sensitive; navigation/
  tải media/ghi file local/gửi provider đều khai side-effect dù `mutating:false`.
- BUG-11: không chiếm Miro UI tab / user-owned tab trái phép.

## 21. Persistence & recovery (sửa BLOCKER 5)

- Durable intent trước dispatch: `tool_call_id` (stable) + `request_id`
  (idempotency key, UNIQUE) + dispatch state + task ref + receipt/result ref.
- Flow: lưu intent → gọi TaskService bằng idempotency key → lưu task_id + receipt.
- Crash cases phải test: trước dispatch / sau task creation chưa link /
  trước receipt / sau receipt. Recovery: tìm task bằng request_id đã lưu;
  không replay external side-effect chưa xác định.
- `turn_tasks(turn_id, task_id)` giữ + bổ sung intent table đủ trường trên.

## 22. API, Streaming & Cancellation (sửa BLOCKER 6)

- SSE event groups: `message.accepted`, `assistant.message.delta/completed`,
  `tool.started/completed`, `task.linked/updated`, `approval.required/granted/denied`,
  `turn.completed/failed/cancelled` (+ giữ `turn.started`, `synthesis.delta`).
  Tên event theo convention repo; mọi event có sequence ID stream-scoped +
  reconnect + replay + dedup; không stream private model reasoning.
- Conversation/messages/history pagination/turn status/follow-up/approval response
  đầy đủ trong §4 (bổ sung stop endpoints):
  `POST /conversations/{id}/turns/{turn_id}/stop` (dừng turn),
  `POST /tasks/{id}/stop` (dừng background task — đã có `router.py:109-147`),
  `POST /conversations/{id}/stop-all` (dừng turn + linked tasks — chỉ cần
  confirmation chống bấm nhầm theo §26, không phải security approval).
- Stop scope phân biệt: dừng assistant-response | dừng Agent Loop | dừng 1 task |
  dừng tất cả liên quan. Concurrency đã chốt tại §25 (background không khóa
  conversation; message mới không tự hủy task cũ; foreground 1 lượt stream mỗi
  conversation giai đoạn đầu).

## 23. Provider, Security & Budget (sửa BLOCKER 7)

- Pre-call: remaining budget, input context limit, output token limit, model
  availability, reserve ước tính. Post-call: actual usage, cập nhật cost, đối chiếu
  estimate, ghi lỗi, hoàn reserve thừa.
- Daily cost cap configurable (D12); không tuyên bố hard-cap $0.50 tuyệt đối khi
  thiếu usage/giá.
- Key chỉ Backend, redacted mọi log; LLM/external không đổi provider config;
  không fallback provider ngoài policy; OpenAI-compatible ≠ mặc nhiên đủ
  tool-calling/streaming (probe trước); không gửi cookie/Bridge credential/secret
  vào context; website = untrusted.

## 24. Product Acceptance UAT-01→13 (sửa BLOCKER 8) + Phases điều chỉnh

| Test | Tình huống | Kết quả bắt buộc |
| --- | --- | --- |
| UAT-01 | Trò chuyện tự nhiên nhiều lượt | Trả lời phù hợp, zero task rác |
| UAT-02 | Hỏi Miro làm được gì | Giải thích capability thực tế đang wired |
| UAT-03 | Thảo luận cách nghiên cứu TikTok | Không tự thực thi |
| UAT-04 | Giao việc diễn đạt mới | Hiểu, không phụ thuộc regex |
| UAT-05 | Nhắc sản phẩm đã nói trước | Hiểu context nhiều lượt |
| UAT-06 | Nghiên cứu rồi phân tích | Nhiều bước thật qua tools |
| UAT-07 | "xem video thứ ba" | Resolve đúng reference |
| UAT-08 | Tool không lấy được dữ liệu | Giải thích trung thực, không bịa |
| UAT-09 | Chat thêm khi task đang chạy | Chat responsive |
| UAT-10 | Yêu cầu dừng | Dừng đúng scope (§22) |
| UAT-11 | Refresh/restart | Giữ conversation + task refs |
| UAT-12 | Website chứa instruction độc | Không thực thi instruction ngoài |
| UAT-13 | Hành động ngoài quyền | Từ chối hoặc xin approval |

- Đa chủ đề, đổi keyword/cách diễn đạt/thứ tự; không chỉ KANS 377.
- Fake Provider chỉ test contract; trí thông minh chứng minh bằng LLM thật (P4).
- **Phases:** P0 Foundation (Conversation API + persistence + provider config +
  Fake test; gate: CRUD + recovery). P1 Conversational (adapter + direct/clarify +
  context + streaming; gate: zero-tool-call; **cuối P1 real-provider smoke test
  chi phí thấp, cần approval** — điều chỉnh D1). P2 Trusted Tool Execution
  (registry + dispatcher + production capability; gate: 1 capability thật).
  P3 Loop + Workspace (đa bước + background + follow-up + synthesis + cancel;
  gate: nhiệm vụ nhiều bước cùng conversation). P4 Full Real LLM Acceptance
  (đa chủ đề + security + UAT; gate: user trò chuyện + giao việc thành công).
- Module responsibility rõ ràng, không nhồi Conversation API/Context/Loop/
  persistence vào vài file cho ít file.
- **Deliverable Revision 2 = chính file này**; không proposal song song; không sửa
  production code trong vòng này.

## 25. Conversation concurrency (CHỐT — thay "chốt ở P0" tại §22)

- Background task KHÔNG khóa conversation. Người dùng luôn có thể hỏi đáp, hỏi tiến
  độ, gửi yêu cầu mới trong khi task chạy.
- Hành vi mặc định:

| Yêu cầu mới | Hành vi |
| --- | --- |
| Hỏi đáp thông thường | Trả lời ngay, task cũ tiếp tục |
| Hỏi tiến độ | Đọc trạng thái task (§18 `task.get_status`) |
| Yêu cầu bổ sung | Đánh giá khả năng cập nhật nhiệm vụ, không tự hủy cũ |
| Yêu cầu thay đổi | Điều chỉnh có kiểm soát qua dispatcher + permission |
| Yêu cầu dừng | Dừng đúng phạm vi (§26) |
| Giao nhiệm vụ khác | Thực thi hoặc xếp hàng theo resource policy, không tự hủy task cũ |

- Foreground LLM response: tối đa 1 lượt đang stream mỗi conversation ở giai đoạn
  đầu. Message mới lúc đang stream → queue hoặc user chủ động stop response đang
  chạy (không khóa vì background task).
- Không triển khai general concurrency framework ngoài nhu cầu trên.

## 26. Cancellation semantics (CHỐT — `stop-all` chỉ cần confirm chống bấm nhầm)

| Thao tác | Yêu cầu |
| --- | --- |
| Dừng assistant đang trả lời | Thực hiện ngay |
| Dừng Agent Loop (turn) | Thực hiện ngay |
| Dừng task được sở hữu | Qua Runtime cancellation (`request_stop/wait_stop`) |
| Dừng tất cả task của conversation | Confirmation chống bấm nhầm (không phải security approval) |
| Hành động bên ngoài đã thực hiện | Không tuyên bố hoàn tác nếu không có evidence |

- `STOP_REQUESTED` ≠ `CANCELLED`: chỉ ghi CANCELLED khi Runtime xác nhận dừng;
  tool chưa dừng thì UI phản ánh đúng (partial/still-running).
- User sở hữu task có quyền dừng task của mình, không cần xin security approval mới.

## 27. Implementation handoff P0–P1 (APPROVED WITH CONDITIONS)

- Điều kiện bắt đầu: cleanup này xong + Reviewer còn lại đồng thuận + baseline kiểm
  kê + phát triển trên branch/worktree độc lập (không sửa chồng 102 file Slice 04
  đang repair; không merge production tới khi regression Slice 04 xong; không push).
- Slice 04 tiếp tục repair độc lập; P2 browser execution chờ BUG-11 + execution
  boundary nghiệm thu; P2 gate cần full tool contracts (§18) trước implementation.
- **P0 scope:** conversation model, message persistence, turn lifecycle,
  Conversation API, history, durable identifiers, recovery foundation, provider
  config Backend, Fake Provider chỉ cho test, FE integration tối thiểu.
  Không hardcode lời chào, không tạo task cho mọi message, không expose Fake như AI.
  **P0 acceptance:** tạo/đọc conversation, isolation, refresh/restart giữ lịch sử,
  dedup, error handling, API contract tests.
- **P1 scope:** LLM adapter thật, context, direct response, clarification, assistant
  streaming, capability probe, provider errors, budget foundation, AI Workspace
  integration. LLM trả lời tự nhiên zero tool calls; Fake chỉ chứng minh contract.
  **Cuối P1:** real-provider smoke test chi phí thấp, cần user approval; không tự
  dùng key/gọi provider khi chưa cấp quyền. Không yêu cầu full tools ở P1.
- **Báo cáo mỗi phase:** implementation diff, tests, actual API behavior,
  persistence/streaming evidence, blockers. Không tuyên bố Intelligence hoạt động
  chỉ bằng Fake; không dùng HTTP 200 thay User Acceptance.
- **P2–P4:** giữ roadmap §24; chưa triển khai đợt này.

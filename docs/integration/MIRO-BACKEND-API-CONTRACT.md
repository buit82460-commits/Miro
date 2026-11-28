# MIRO — BACKEND API CONTRACT (Single Source of Truth cho FE Integration)

> **Tài liệu tích hợp chính thức duy nhất.** Mọi FE Agent bắt đầu từ đây, không kiểm kê lại BE từ đầu.
> Nghiêm cấm hallucinate API/field/capability ngoài tài liệu này khi chưa truy vết source.

## SECTION 01 — Document Metadata

| Mục | Giá trị |
|---|---|
| Repository | `C:\Miro` |
| Branch | `ui/port-prototype-v2` |
| Commit SHA (audit) | `a94c1e264f04c8bfcfe0be0ae3af55387387917b` |
| Ngày audit | 2026-11-27 |
| Backend scope | `apps/backend/src/miro` — entry canonical `miro/main.py:app` (FastAPI `Miro API`); alias `miro/app.py:create_app()` trả về cùng app |
| Agents tham gia | Agent 01 API Surface · Agent 02 Capability · Agent 03 Runtime/Workflow · Agent 04 Data/Testing/Readiness + điều phối cross-review |
| Phương pháp | Read-only source trace (route → service → store → test). Không sửa code/commit/push. Full suite đã chạy chia 5 batch (do full-run timeout ở 61% như Slice 04 từng ghi): **469 passed, 2 skipped, 0 failed** — batch1 141 (7s) · batch2 87 (70s) · batch3 68 (643s, media-native nặng) · batch4 90+2sk (65s) · batch5 83 (53s). 69/69 test files đều chạy, không file nào fail |
| Giới hạn đã biết | Zero-auth toàn surface (local-only); approval RAM-only mất sau restart; `main.py:42` hard-code `tasks.db`; working tree dirty (`M tasks/router.py` + untracked prototype files) — FE phải re-verify diff này trước khi bind `run-message` |

## SECTION 02 — Backend Architecture Overview

```
Launcher (windows/miro.py: 6 service be/fe/browser-worker/media-worker/node-youtube/bridge)
  → BE: uvicorn miro.main:app :8770
        ├─ routers/ (health, tasks, renders, publisher, threads, platforms,
        │            studio, projects, desktop, schedule) + research/router + connections/router
        ├─ tasks/service.py (TaskService + FakeRemote mặc định) + tasks/bridge_config.py
        ├─ publishing/publisher.py + threads/flow.py + threads/worker.py (Threads M2)
        ├─ studio/ (pipeline 8 bước + handlers + store idempotent)
        ├─ scheduling/ (day-plan JSON, không daemon)
        ├─ browser/gateway.py (READ via eye / WRITE via adapter + write-gate) + bridge_transport.py
        ├─ adapters/ (threads/fb/tiktok/yt/yt_api/ig/shopee/chatgpt/flow/freelance/live/...)
        ├─ agent/ (registry 6 tools + planner/router + executor mock) — khung rule-based, KHÔNG LLM
        ├─ research/ (NullProvider mặc định, upgrade MediaIntelProvider nếu import được)
        ├─ media_intel/ (adapter DUY NHẤT cho phân tích media — luật REA-MEDIA)
        ├─ library/ + storage/ (SQLite) + platforms/ + connections/ + permissions/ (RAM)
        └─ desktop/ (epoch-gate + Notepad pilot qua agent-desktop CLI)
```

- **Không có:** SSE/WebSocket/APScheduler/Celery/queue thật. Realtime = **polling HTTP**. Async = `asyncio.ensure_future` fire-and-forget (`main.py:76`).
- **Fail-closed mặc định:** UNKNOWN không replay; thiếu approval/auth/actor/provenance → DENY; production không fallback engine.
- **2 đường browser song song (không gộp):** CDP/Page path (`read_via_eye`/`write_via_adapter`, cần managed tab — hiện `threads_browser=None`) vs Bridge path (`read_*_via_bridge`, qua extension, không CDP). Task nào dùng đường nào xem §09.

## SECTION 03 — Complete Backend Capability Inventory

| Cap ID | Name | Purpose | Impl | Exposed API | Source |
|---|---|---|---|---|---|
| PUB-01 | Caption builder + tag `#dubNNNNNN` | Sinh text, cắt max_chars, gắn tag reconcile | IMPLEMENTED | nội bộ | `publishing/publisher.py:128-166`, `adapters/core.py:117-173` |
| PUB-02 | guard_duplicate + claim_attempt O_CREAT\|O_EXCL | Chống post trùng, đóng TOCTOU | IMPLEMENTED | nội bộ | `publishing/publisher.py:417-446` |
| PUB-03/04 | Publisher.publish + run_batch 2-phase | Submit → group-reconcile, DUPLICATE_TAGS abort, dừng sau UNKNOWN đầu | IMPLEMENTED (logic) | `POST /threads/publish` | `publishing/publisher.py:695-1009` |
| PUB-05 | verify_receipt / match_eye_records | Verify owner+post_id/tag cùng record, không text-fallback | IMPLEMENTED | nội bộ | `publishing/publisher.py:574-663` |
| PUB-06 | Media gate | Chặn media chưa verify bytes | IMPLEMENTED | nội bộ | `publishing/publisher.py:212-315` |
| PUB-07 | Actor contract + approval gate | verify_actor + approval bound fingerprint+revision | IMPLEMENTED | nội bộ | `publishing/publisher.py:337-393,680-693` |
| ADP-T1 | Threads worker + yt-dlp download | Worker Threads, tải post công khai | IMPLEMENTED (cần live tab) | qua threads router | `adapters/threads.py:20-81` |
| ADP-T2 | Comment/DM Threads/FB/IG | — | STUB `UNSUPPORTED_*` | không | `adapters/threads.py:84-103`, `facebook.py:56-72`, `instagram.py:120-139` |
| ADP-T3 | TikTok engage (view/like/repost/comment/follow) | Engage qua managed tab, daily caps | IMPLEMENTED (cần live tab) | qua LivePage | `adapters/tiktok.py`, `adapters/live.py:548-755` |
| ADP-YT | YouTube Data API driver | Resumable upload + read-back verify | IMPLEMENTED (cần OAuth file) | không router riêng | `adapters/youtube_api.py` |
| ADP-FI | FB/IG caption_edit/draft/audience/delete | — | STUB `UNSUPPORTED_*` | không | `adapters/instagram.py:104-118`, `core.py:48-105` |
| ADP-SH | Shopee publish | — | BLOCKED (onboarding 1/5) | không | `adapters/shopee.py`, `platforms/registry.py:124` |
| ADP-CF | ChatGPT/Flow prompt submit | Gửi prompt qua tab | IMPLEMENTED (cần live tab) | không router riêng | `adapters/live.py:459-494` |
| ADP-FR | Freelance recon + validate | Chuẩn hoá job, chặn contact-info | PARTIAL (post `UNSUPPORTED`) | không | `adapters/vlance.py`, `freelancer_vn.py`, `upwork.py` |
| BRW-01 | Gateway read/write + write-gate | Cổng duy nhất, evidence `rea-eye` tươi <300s | IMPLEMENTED | nội bộ (mọi adapter) | `browser/gateway.py:19-313` |
| BRW-02 | Bridge readers | READ qua extension, không CDP | IMPLEMENTED | qua `POST /tasks/run-message` | `browser/gateway.py:324-657`, `bridge_transport.py` |
| BRW-03 | Session/lease/runtime/observation | Quản tab, lease owner, verify actor | IMPLEMENTED | gián tiếp | `browser/session_manager.py`, `lease_store.py`, `runtime.py`, `live_chrome.py` |
| EYE-01/02 | Eye collectors (+freelance) | Mắt duy nhất, locator hẹp | IMPLEMENTED | nội bộ | `eye/__init__.py`, `eye/freelance.py` |
| MED-01 | P0 ffmpeg-native probe/shots/keyframes/subtitle/tempo | Hiểu file local (chỉ test/migration gọi trực tiếp) | IMPLEMENTED | qua studio/research | `media_intel/__init__.py:82-173` |
| MED-02 | Native rea-video analyze/* | Phân tích thật qua venv `--no-vlm` | IMPLEMENTED (cần venv, else `PROVIDER_UNAVAILABLE`) | qua research/studio | `media_intel/__init__.py:411-1051` |
| MED-03 | STT/diarization | — | BLOCKED `MODEL_MISSING` | không | `media_intel/__init__.py:688-703` |
| MED-04 | VLM/remake/generation | — | DENIED mặc định (cost gate) | không | `media_intel/__init__.py:706-743,1084-1093` |
| STU-01 | Studio pipeline 8 bước | download→render ffmpeg thật | IMPLEMENTED (phụ thuộc engine) | `POST /studio/*` (31 EP) | `studio/pipeline.py`, `studio/handlers.py` |
| STU-02 | Timeline ops + undo/redo | Thuần code | IMPLEMENTED | `POST /studio/timeline/*` | `studio/timeline_ops.py` |
| STU-03 | Captions SRT + OCR/STT merge | Phụ đề thật | IMPLEMENTED | `POST /studio/captions/*` | `studio/captions.py` |
| STU-04 | AudioFX/beat/separate/track/canvas/translate | Filter/canvas thật; separate cần model UVR | PARTIAL | `POST /studio/audiofx|beat|separate|track|canvas|export/*` | `studio/audio_fx.py`, `separate.py`, `tracking.py`, `canvas.py`, `translate_mt.py` |
| TSK-01 | TaskService submit/stop/restart/resume/approve + run-message | Task idempotent, retry TRANSIENT 3 lần, stop 2-phase | IMPLEMENTED (remote=FakeRemote) | `POST /tasks*` (14 EP) | `tasks/service.py`, `tasks/router.py` |
| AGT-01/02 | ToolRegistry 6 tools + Planner/Router + Executor | Khung rule-based; executor/remote MOCK | PARTIAL/KHUNG | không HTTP | `agent/registry.py:46-97`, `agent/executor.py:26-101` |
| RES-01 | Research orchestration | search/read/channel/video/compare/to-project qua provider inject | PARTIAL (mặc định Null → rỗng) | `POST /research/*` (6 EP) | `research/service.py:26-60`, `media_provider.py`, `multimodal.py` |
| SCH-01 | Day-plan scheduler | Slot/due/auto-pause(2 UNKNOWN)/reconcile-touch | IMPLEMENTED | `POST /schedule/*` (3 EP) | `scheduling/schedule.py`, `scheduling/store.py` |
| LIB-01 | Library asset sha256/dedupe/links | Thư viện asset thật | IMPLEMENTED | qua threads prepare/history | `library/service.py`, `library/store.py` |
| PLT-01 | Platforms registry matrix | Ma trận SUPPORTED/PARTIAL/BLOCKED/UNSUPPORTED + CRUD versioned | IMPLEMENTED (metadata) | `GET/POST/PATCH /platforms*` (6 EP) | `platforms/registry.py`, `platforms/store.py` |
| CON-01 | Connections accounts | Credential ref-only; verify thật + mock-tab test | PARTIAL | `/connections/*` (10 EP) | `connections/service.py:31`, `connections/router.py:82-83` |
| PRM-01 | PermissionStore approval | Scope+revision binding + revoke | IMPLEMENTED (RAM-only) | `POST /tasks/{id}/approve|revoke` | `permissions/store.py:52` |
| DSK-01 | Desktop act/gate/dispatch + Notepad pilot | Epoch-gate, resolve doc đúng-1, read-back verify | IMPLEMENTED (cần CLI) | `POST /desktop/*` (3 EP) | `desktop/act.py:43+`, `gate.py`, `dispatch.py`, `workflows/notepad_pilot.py` |
| W-INT | Integrations (exa/jina/llm/vision/reader/browser_use/captcha) | Khung + parse thật, cần key/service | PARTIAL | nội bộ | `integrations/agent_reach.py:31-80`, `llm_provider.py:28-50` |

Tổng: **37 capabilities** — IMPLEMENTED 24 · PARTIAL 8 · STUB 3 · BLOCKED 2.

## SECTION 04 — API Endpoint Registry (88 reachable / 0 unregistered)

Auth toàn surface: **none (open, local-only)** — không Bearer/API key/OAuth2 route nào.
> Lưu ý kiểm kê: working tree có 88 decorators, trong đó **1 EP là diff chưa commit** (`GET /tasks` compat alias, `tasks/router.py:36-44` — thêm sau HEAD `a94c1e2`, xem `git diff`). Tổng **đã commit ở HEAD = 87 EP**. FE chỉ bind `GET /tasks` sau khi diff này được review/commit.

| API ID | Method | Path | Purpose | Cap | Readiness |
|---|---|---|---|---|---|
| HEALTH-01 | GET | `/health` | Liveness | — | READY |
| TASK-01..14 | POST/GET | `/tasks`, `/tasks/recent`, `/tasks/runtime/status`, `/tasks/{id}`, `/{id}/events`, `/{id}/stop`, `/{id}/worker-stopped`, `/{id}/wait-stop`, `/{id}/restart`, `/{id}/resume`, `/tasks/run-message`, `/{id}/approve`, `/{id}/revoke` | Task lifecycle + NL routing + approval | TSK-01/PRM-01 | CONDITIONS (approval RAM, bridge wiring) |
| RENDER-01/02 | POST/GET | `/renders`, `/renders/{id}` | Idempotent render record | PUB | READY |
| PUB-01/02 | POST/GET | `/publications`, `/publications/{id}` | Idempotent publish record | PUB-02 | READY |
| THREAD-01..05 | POST/GET | `/threads/prepare`, `/approve`, `/publish`, `/reconcile`, `/threads/history` | Threads M2 flow | PUB-03/04, THR | CONDITIONS (dry-run mặc định; post thật cần approval+tab) |
| PLAT-01..06 | GET/POST/PATCH | `/platforms`, `/platforms/history`, `POST /platforms`, `/{id}/clone`, `/{id}/capabilities/{cap}` (PATCH), `/platforms/rollback` | Registry CRUD versioned | PLT-01 | READY |
| STUDIO-01..31 | GET/POST | `/studio/resolve`, `/platform`, `/download`, `/translate`, `/subtitles/save`, `/subtitles/{id}`, `/render`, `/render/final`, `/overlay`, `/revoice`, `/plan`, `/editor/render`, `/editor/restore`, `/cancel`, `/submit`, `/handoff`, `/project/{id}`, `/media/{id}`, `/timeline/op`, `/timeline/undo`, `/timeline/redo`, `/captions/import`, `/captions/export/{id}`, `/audiofx/preview`, `/canvas/set`, `/export/plan`, `/beat`, `/separate`, `/track`, `/export/ladder`, `/preview/live` | Studio render/dub pipeline | STU-01..04 | NOT_READY (cần engine/env + test studio) |
| PROJ-01..05 | GET/POST/PUT | `/projects/{id}`, `/{id}/operations` (chỉ `update_subtitle`/`move_clip`), `/{id}/subtitles/{clip}` (PUT), `/{id}/renders`, `/{id}/approve` | Compat view trên studio video_id | STU-02 | CONDITIONS |
| DESK-01..03 | POST | `/desktop/init`, `/desktop/act`, `/desktop/transfer` | Notepad pilot epoch-gated | DSK-01 | NOT_READY (INTERNAL_ONLY, OS-level) |
| SCHED-01..03 | POST/GET/PATCH | `/schedule/ensure`, `/schedule/day-plan`, `/schedule/day-plan/status` | Day-plan persist + bind | SCH-01 | READY |
| RES-01..06 | POST | `/research/search`, `/read`, `/channel`, `/video`, `/compare`, `/to-project` | Research orchestration | RES-01 | CONDITIONS (null-provider → metadata-only) |
| CONN-01..10 | POST/GET | `/connections/accounts`, `GET /accounts`, `GET /accounts/{id}`, `/{id}/verify`, `/{id}/pause`, `/{id}/reconnect`, `/{id}/revoke`, `/{id}/default`, `/defaults/{platform}`, `/mock/verify-tab` (mock test) | Accounts + verify | CON-01 | CONDITIONS (mock EP chỉ test) |

Chi tiết từng EP (schemas inline trong code, không Pydantic tập trung ở nhiều nơi): xem routers tương ứng — `tasks/router.py:24-313` (+`tasks/models.py:56`), `routers/renders.py:18-35` (+`models.py:6-22`), `routers/publisher.py:15-39`, `routers/threads.py:45-195`, `routers/platforms.py:17-80`, `routers/studio.py:35-476`, `routers/projects.py:56-169`, `routers/desktop.py:62-96`, `routers/schedule.py:36-71`, `research/router.py:26-63` (+`research/models.py:20-72`), `connections/router.py:27-82` (+`connections/models.py:15-53`), `routers/health.py:8`.
Ví dụ request/response chuẩn: Threads publish `PublishRequest{..., approval?, revision?, allow_post=false}` → `{queued, replayed, worker, posted_fake}` 201 / 403 approval / 409 conflict; dry-run dùng `_FakePage` (`threads.py:150-170`, `ack_via=http-dry-run`) có chủ ý. `POST /tasks/run-message` nhận `dict{message, tab_id:int!, live_origin?, limit?}` → `{ok,error,task_id,route}` 200 / 400 TAB_INVALID.

## SECTION 05 — Detailed Contracts (rút gọn theo nhóm; full field xem file source cột phải)

- **Tasks:** `TaskSubmitRequest{request_id?, message, videos[], use_ai?, handoff?, description?, tags?, language?}` (`tasks/models.py:56`); idempotent fingerprint sha256 + `REQUEST_ID_CONFLICT` 409 khi cùng id khác nội dung; dedupe revision-level trả job cũ. `approve?item=0&scope=edit&revision=1`. Side-effect: `FakeRemote` → mutation không chạm editor thật. Evidence: `tasks/service.py:149-179`, `db.py:75-89`.
- **Threads:** `PrepareRequest/ApproveRequest/PublishRequest{approval?, revision?, allow_post=false}/ReconcileRequest/history?publication_id&render_id`. Approval bind `{scope=threads_post, revision, fingerprint}` (`threads/flow.py:90-117`); sai scope → SCOPE_DENIED, lệch revision → STALE_REVISION/CHECKPOINT_STALE, lệch fingerprint → FINGERPRINT_CONFLICT, secret trong text → 422. Post thật chỉ khi `allow_post=true` + approval hiệu lực + `verify_actor` đúng + tab/CDP sẵn; mặc định dry-run reconcile. Evidence: `routers/threads.py:8-183`.
- **Studio:** schemas inline `routers/studio.py:35-153`; handler qua `StudioHandlers._run_idempotent` (`studio/handlers.py:60-115`); `REQUEST_ID_CONFLICT` 409, single-slot 409 SLOT_BUSY, contamination lock tới khi clear thủ công; retry chỉ TRANSIENT + step idempotent, max 3; render semaphore 4. Evidence: `studio/store.py:67-276`, `pipeline.py:46-65,1037-1055`.
- **Research:** `SearchRequest{query,limit}/ReadRequest{url}/ChannelRequest/VideoRequest/CompareRequest/ToProjectRequest` (`research/models.py:20-72`); NullProvider → `items=[]`, `evidence=metadata_only`; `to-project` 503 khi thiếu task_service. Evidence: `research/service.py:26-60`.
- **Connections:** `AccountCreate{platform, account_id, credential_ref(ref-only `vault:/ref:/env:/keychain:/oauth:/secret:`), profile_binding_id, browser_instance_id}`; verify bằng `VerifyEvidence` tab thật; `/mock/verify-tab` chỉ test. Evidence: `connections/models.py:15-53`, `router.py:72-83`.
- **Schedule/Platforms/Renders/Publications/Desktop:** như §04; schedule `EnsureRequest{policy, new_items, carryover, date_str?, was_clean_shutdown}` + 500 BIND_PLAN_FAILED; platforms `PlatformUpsert/CloneRequest/CapabilityPatch(all-optional)/RollbackRequest{version≥1}`; desktop `InitRequest/ActRequest/TransferRequest` + 409 STALE_EPOCH / 422 WINDOW/DOC / 503 CLI_UNAVAILABLE.

## SECTION 06 — Authentication & Authorization

- **Không có auth user/route-level.** Mọi quyền dựa vào: (1) approval gate scope+revision+fingerprint (`permissions/store.py:47-58`, `threads/flow.py:94-101`); (2) `verify_actor` đúng account/tab (`publishing/publisher.py:337-393`, gateway actor check kép); (3) Gateway `check_write_gate` 8 điểm (`gateway.py:57-195`): evidence `rea-eye` tươi <300s + đúng tab/instance + auth từ trusted `write_task_context` (không từ request) + approval binding + lease owner + TAB_ORIGIN_CHANGED deny; (4) media trust boundary (`media_intel:1059-1093`): provenance `media-analysis`, VLM/generation DENY mặc định; (5) CORS/env: BE/FE cùng localhost, bridge creds chỉ ở `app.state` memory, không log (`main.py:46-75`).
- FE không tự suy posted: đọc receipt/journal/history.

## SECTION 07 — Data Models & Relationships

- **Tasks+events** (`tasks/models.py:22-141`): `TaskRecord/TaskItem/TaskEvent` — SQLite `tasks.db` persist, seq recover (`service.py:113-124`). **Permissions RAM-only** (`permissions/store.py:32`) — mất sau restart.
- **Threads:** fingerprint sha256 `{media, owner, shortcode, tag, text}` + `Approval`; journal `threads/social-attempts/*.json` + `audit.jsonl` chỉ giữ `text_sha256`.
- **Library** (`library/models.py/store.py`): `assets/collections/asset_renders/render_posts` — SQLite `threads-library.db`.
- **Renders/Publications:** deterministic id `rnd_<request_id>` / key `(publication_id,attempt_id)` — SQLite.
- **Connections/Platforms/Schedule:** RAM dict + JSON persist best-effort (`connections-accounts.json`, `platforms-registry.json` versioned history≤20, `threads-day-plan.json` atomic tmp+replace).
- **Studio:** `IdempotentStore` fingerprint/revision/slot/contamination (`studio/store.py`) — persist nếu `persist_dir` set.
- Config/env: `MIRO_BE_DB_DIR` (default `C:\Miro\var`, nhưng `main.py:42` hard-code tasks.db), `MIRO_THREADS_BASE/ATTEMPTS`, `MIRO_BRIDGE_*` (env > trusted file), `MIRO_REA_VIDEO_PYTHON/TTS_ENGINE/DUBTOOL_ROOT/NLLB_*/YOUTUBE_ACCOUNTS/ADAPTER_BASELINE/ALLOW_UNVERIFIED_ACTOR`. Xem chi tiết Agent 04 §3.

## SECTION 08 — Business Workflows

| ID | Flow | Trigger → bước → kết quả | FE theo dõi |
|---|---|---|---|
| W1 | render-task | `POST /tasks` 202 → fingerprint+dedupe → `run()` write-ahead 5 steps → completed/needs_attention | poll `GET /tasks/{id}`, `/events` |
| W2 | run-message | `POST /tasks/run-message` → `route_message` → actor/search/video/autonomous/research branch → task + evidence đồng bộ | response `{route,task_id,evidence}` + poll task |
| W3 | gateway→bridge read | W2 → `read_*_via_bridge` → backend-key request → poll `/observations` 1s → clean schema (cắt 2000, untrusted) → eye evaluate | observation trong response; lỗi `OBSERVATION_TIMEOUT/ORIGIN_MISMATCH/...` |
| W4 | threads publish batch | `POST /threads/publish` → publication queue → `ThreadsWorker.run_batch` (DUPLICATE_TAGS → Phase A submit từng intent → dừng sau UNKNOWN đầu → Phase B group-reconcile read-only) | `GET /threads/history`; journal `submit/verified/failed-before-post/unknown` |
| W5 | threads reconcile | `POST /threads/reconcile` → read-only match (post_id→tag exact, cùng record) → verified merge, không replay | history journals |
| W6 | day-plan | `POST /schedule/ensure` → boot_action rebuild/respect → build cap+carryover → persist + bind publisher; gate paused/due trong run_batch | `GET /schedule/day-plan` |
| W7 | studio pipeline | `POST /studio/*` → `_run_idempotent` → slot lock → revision guard → 8-step pipeline → completed/needs_attention/contaminated | response + `GET /studio/project/{id}`, `/media/{id}` |
| W8 | desktop act | `POST /desktop/init\|act\|transfer` → epoch gate → resolve window/doc(đúng-1) → lock → select-tab → write → read-back verify + receipt | response `{ok,result}` + `receipt-<run>.json` |
| W9 | media analysis | research-video/studio-analyze → `media_intel.*_native` → rea-video venv → evidence level | evidence trong task record |
| W10 | renders/publications idempotent | `POST /renders|/publications` → SQLite replay/409 | GET theo id |

Xem file:dòng đầy đủ ở báo cáo Agent 03 (§1-3). Không suy diễn trạng thái đăng từ `accepted`.

## SECTION 09 — Runtime, Jobs, Events & Realtime

- Tạo job: `POST /tasks` (202 + fire-and-forget `run()`), `POST /threads/publish` (đồng bộ trong request), `POST /studio/*` (đồng bộ + semaphore 4), `POST /schedule/ensure` (caller-driven, không daemon).
- Trạng thái tasks: `queued→running→completed|needs_attention|stop_requested→stopped|awaiting_review` (`tasks/models.py:22-37`); journal threads: `submit→verified|failed-before-post|unknown|submitted-awaiting-group-reconcile`.
- Tiến độ: poll `GET /tasks/recent|/{id}|/{id}/events`, `GET /threads/history`, `GET /schedule/day-plan`. **Không SSE/WebSocket.**
- Cancel/retry/timeout: stop 2-phase + watchdog `wait-stop` (grace default 10s, force STOPPED); retry chỉ TRANSIENT+safe-step max 3 backoff 2^n≤30s; mutation không replay; studio cancel cooperative; bridge cancel qua `is_cancelled`.
- Events: SQLite `events(task_id,sequence)` + `AuditLog` batch non-blocking (đầy → `dropped++`).

## SECTION 10 — Frontend Integration Guide

1. **Kết nối:** BE `http://127.0.0.1:8770`, FE dev `:3100`; rewrite/proxy BE qua launcher `--only fe` hoặc `NEXT_PUBLIC_API_BASE`. Kiểm `GET /health` + `GET /tasks/runtime/status` (xem `wiring` + `bridge.tabs` redacted) trước mọi tính năng.
2. **API client:** tổ chức theo nhóm router (§04); headers mặc định JSON, không cần auth header (local); `tab_id:int` bắt buộc ở run-message; route `""` không trailing-slash (thêm `/` có thể 307).
3. **Gọi từng nhóm:** tasks/threads/research giống §05; research luôn kiểm `evidence` (`frames_analyzed` vs `metadata_only`) + `sources[]`; threads luôn dry-run trước (`allow_post=false`), post thật chỉ sau approval tươi + hiển thị fail-closed (`APPROVAL_REQUIRED/STALE_REVISION/FINGERPRINT_CONFLICT/CDP_UNAVAILABLE/MEDIA_UNVERIFIED`); studio/desktop chưa bind UI production.
4. **States:** loading (poll 1-2s), empty (`[]`/`metadata_only`/404 NO_DAY_PLAN → CTA ensure/search khác), error (400/404/409/422/500/503 → message + action cụ thể, UNKNOWN → reconcile-readonly, không nút "thử lại post").
5. **Async:** mọi op dài đều poll; refresh sau mutation bằng GET lại (`recent/{id}/events/history/day-plan`); pagination `?limit` (clamp), chưa có filter/sort server-side ngoài connections `?platform&status`.
6. **Constraints:** không gọi `/connections/mock/verify-tab` ở production; không gọi desktop/studio-final khi chưa đủ engine; không auto-retry post; không hiển thị research rỗng như đã verify frames.

## SECTION 11 — Backend Readiness Matrix

**Implementation:** IMPLEMENTED 24 cap · PARTIAL 8 · STUB 3 · BLOCKED 2 (trên 37 cap).
**Verification:** SOURCE 37/37 · TEST 37/37 (full suite 469 passed, 2 skipped — xem §14) · RUNTIME live (BE/FE/Bridge http-200, chưa live Chrome post).

| Nhóm EP | Impl | Verif | FE kết luận |
|---|---|---|---|
| health/renders/publications/platforms/schedule (14 EP) | IMPLEMENTED | TEST/SOURCE | **READY_FOR_FE** |
| tasks/threads/research/connections/projects (40 EP) | IMPLEMENTED/PARTIAL | TEST/SOURCE | **READY_WITH_CONDITIONS** (approval RAM, bridge/tab, metadata-only, mock EP) |
| studio (31 EP) | PARTIAL | TEST_VERIFIED (batch5 83 passed) | **READY_WITH_CONDITIONS** (engines sẵn: ffmpeg 9, yt-dlp, rea-venv, dubtool mount được; FE handle NEEDS_ATTENTION/contamination/409 SLOT_BUSY) |
| desktop (3 EP) | INTERNAL_ONLY | TEST_VERIFIED (batch2 87 passed) | **NOT_READY_FOR_FE** (INTERNAL_ONLY — pilot Notepad OS-level, CLI agent-desktop sẵn nhưng không phơi UI công khai) |

Tổng EP: **88 quan sát (87 committed ở HEAD + 1 uncommitted `GET /tasks`)**, 0 unregistered, 0 trùng method+path, 0 stub route (3 điểm fake/mock có nhãn chủ ý).

## SECTION 12 — Capabilities Without Public APIs

| Capability | Interface nội bộ hiện có | Vì sao FE chưa dùng trực tiếp | Hướng xử lý sau |
|---|---|---|---|
| Publisher guard/verify/media-gate/approval (PUB-01/02/05/06/07) | `publishing/publisher.py` gọi nội bộ | Chỉ expose qua threads router, không HTTP riêng | Giữ nguyên — FE dùng threads flow, không cần EP mới |
| Eye collectors (EYE-01/02) | `eye/*` + `collect_post_records` | Mắt là lớp nội bộ của Gateway | Giữ nguyên — FE nhận evidence, không gọi eye |
| Gateway write-gate/lease (BRW-01/03) | `browser/gateway.py` | Không phải HTTP | Giữ nguyên |
| Bridge readers chi tiết (BRW-02) | `gateway.read_*_via_bridge` | Chỉ expose qua run-message | Muốn UI riêng từng reader → bổ sung EP sau (ngoài scope) |
| YouTube upload driver (ADP-YT) | `adapters/youtube_api.py` | Chưa có router riêng | Cần EP + OAuth UX nếu FE muốn upload YT |
| TikTok engage/ChatGPT-Flow submit (ADP-T3/CF) | `adapters/live.py` | Chưa có router riêng, cần live tab | Cần EP + approval UX nếu FE muốn engage |
| Media native analyze/* (MED-02) | `media_intel.*_native` | Chỉ qua research/studio | Muốn UI media-intel riêng → EP sau |
| Agent planner/executor (AGT) | `agent/*` (mock remote) | Chưa HTTP, remote mock | Không expose tới khi remote thật |
| Comment/DM FB/IG/Threads (ADP-T2) | stub `UNSUPPORTED_*` | Chưa trinh sát Q1-Q10 | Không EP mới tới khi đủ Evidence |

Không triển khai API mới trong nhiệm vụ này.

## SECTION 13 — Gaps, Limitations & Integration Blockers

1. **Approval RAM mất sau restart** (`permissions/store.py:32`) — mọi mutation cần duyệt lại; FE luồng duyệt-lại + warn.
2. **`main.py:42` hard-code tasks.db** — bỏ qua `MIRO_BE_DB_DIR`; đa môi trường sai DB.
3. **Post thật cần chuỗi điều kiện ngoài code** — approval tươi + `allow_post=true` + verify_actor + tab/CDP + bridge wiring; thiếu → fail-closed. FE dry-run first.
4. **Research mặc định metadata-only** — không hiển thị như frames-verified.
5. **Studio/Desktop** — studio READY_WITH_CONDITIONS (tests xanh, engines sẵn); desktop giữ INTERNAL_ONLY, không phơi UI công khai.
6. **Zero-auth** — chỉ local; expose ra ngoài phải thêm auth trước.
7. **`M tasks/router.py` chưa review** — diff working tree chạm đúng run-message; FE không bind tới khi diff được xác minh.
8. **Docs cũ vs code:** baseline Slice 04 (`8fa5722`) đã lỗi thời — chuẩn hiện tại là `a94c1e2`; một số verify cũ mô tả `threads_browser=None`/FakeRemote vẫn đúng tới nay (đã re-verify).

## SECTION 14 — Source Evidence & Verification Traceability

- Entry/wiring: `apps/backend/src/miro/main.py:1-134` (routers `:84-95`, bridge wiring `:46-75`, threads state `:98-134`); alias `app.py:12-23`.
- Tasks: `tasks/router.py:24-313`; `tasks/service.py` (submit `:149-179`, run `:230-274`, retry `:30-39,204-220`, stop/restart/resume `:972-1100`); `tasks/models.py:22-141`; `tasks/bridge_config.py:16-45`; `storage/db.py`.
- Threads: `routers/threads.py:45-195` (FakePage `:150-170`); `publishing/publisher.py` (guard `:417-446`, verify `:574-663`, checks `:680-693`, publish `:695-753`, reconcile `:755-797`, batch `:799-1009`); `threads/flow.py:45-218`; `threads/worker.py:100-230`.
- Studio: `routers/studio.py:35-476`; `studio/handlers.py:60-115`, `pipeline.py`, `store.py:50-276`, `timeline_ops.py`, `captions.py`, `audio_fx.py/separate.py/tracking.py/canvas.py/translate_mt.py`.
- Schedule: `routers/schedule.py:36-71`; `scheduling/schedule.py`, `scheduling/store.py:17-76`.
- Research: `research/router.py:26-63`; `research/models.py:20-72`, `service.py:26-60`, `media_provider.py`, `multimodal.py`.
- Connections: `connections/router.py:27-83`; `connections/models.py:15-53`, `service.py:31`, `store.py:18-45`.
- Platforms: `routers/platforms.py:17-80`; `platforms/registry.py`, `store.py:28-193`.
- Desktop: `routers/desktop.py:62-105`; `desktop/act.py:43-217`, `gate.py:87-98`, `dispatch.py`, `backend.py:21-60`; `workflows/notepad_pilot.py:85-180`.
- Gateway/bridge/eye/media: `browser/gateway.py:19-657`; `bridge_transport.py:22-358`; `eye/__init__.py`, `eye/freelance.py`; `media_intel/__init__.py:34-1240` (+deny `:1059-1093`); `adapters/*.py`.
- Agent/integrations: `agent/registry.py:46-97`, `executor.py:26-101`, `planner.py`, `router.py:41-69`; `integrations/agent_reach.py:31-80`, `llm_provider.py:28-50`.
- Tests vòng này (read-only, `python -m pytest tests -q -p no:warnings` trong `apps/backend`, chia 5 batch do full-run timeout ở 61%): batch1 141 passed (7s) · batch2 87 passed (70s) · batch3 68 passed (643s, media-native nặng) · batch4 90 passed + 2 skipped (65s) · batch5 83 passed (53s). Tổng **469 passed, 2 skipped, 0 failed** trên 69/69 test files.
- Đếm độc lập: `Select-String '@router.(get|post|put|patch|delete)'` = **88** khớp registry; `tests/test_*.py` = **69 files**.

## SECTION 15 — Frontend Integration Handoff

1. **Tích hợp ngay (READY):** health, renders, publications, platforms CRUD, schedule ensure/day-plan — 14 EP, không điều kiện đặc biệt ngoài local-only.
2. **API tương ứng:** §04 bảng TASK/THREAD/RES/CONN/PROJ + §05 contracts; base `http://127.0.0.1:8770`.
3. **Workflow nhiều API:** W1 (submit→poll events), W2 (run-message→poll task), W4+W5 (prepare→approve→publish dry-run→reconcile→history), W6 (ensure→day-plan→publish gate), W7/W8/W9 (chưa production).
4. **Dependencies FE chuẩn bị:** poller + event/history viewers; approval UX (scope/revision/fingerprint) + duyệt-lại-sau-restart; dry-run-first UX + fail-closed error mapping; research `evidence` badge (frames vs metadata-only); bridge/tab status từ `/tasks/runtime/status`.
5. **BE có nhưng chưa expose:** §12 (YouTube upload, engage, media-native riêng, agent executor) — FE chưa có UI là đúng, không tự chế EP.
6. **Chưa dùng:** toàn bộ studio-final/desktop-production/comment-DM/Shopee-publish/STT/VLM (NOT_READY/BLOCKED/DENIED/UNSUPPORTED).
7. **Việc phải xong trước tích hợp:** xác minh diff `M tasks/router.py`; quyết định persist approval + sửa hard-code tasks.db (hoặc document); chạy full suite studio/bridge/adapters trước khi mở UI tương ứng; thêm auth nếu expose khỏi localhost.
8. **E2E cần kiểm:** queue→run→poll→stop/restart/resume tasks; run-message 4 nhánh (actor/search/video/autonomous) + TAB_UNKNOWN fail-closed; threads prepare→approve→publish(dry)→reconcile→history + UNKNOWN never-replay; schedule ensure→bind→paused/due; research metadata-only rendering; connections CRUD + mock EP không lọt production.

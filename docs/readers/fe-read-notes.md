# FE Read Notes — Dubtool Web vs JARVIS (cho Agent FE Miro)

Ngày đọc: 2026-11-21. Chỉ đọc, không sửa code.

## 1. Kết luận nhanh

- **Dubtool `C:\dubtool\web\src`**: Next.js 16.4.6 + React 19 + TanStack Query v5 + zod v4 + Tailwind 4. FE thật, gọi BE timeline qua proxy. Đây là **mẫu chuẩn** để Miro thống nhất theo.
- **JARVIS `D:\JARVIS-Assistant`**: **không có frontend/web/mobile**. Toàn bộ `ts/tsx/html` tìm được đều nằm trong `research/repos/*` (code clone về để nghiên cứu: openclaw UI, rea website, agent-desktop viewer...) — không phải FE chính chủ. Phần FE-liên quan duy nhất là **backend FastAPI** (`backend/app/*`) mà FE tương lai sẽ gọi.

## 2. Dubtool Web — bản đồ route

| Route (App Router) | File | Chức năng |
|---|---|---|
| `/` (Chat) | `app/page.tsx` (286 dòng, `page.module.css`) | Sidebar project thật + composer chat → `usePlanEdit` → card kế hoạch → `useApplyPlan` duyệt & chạy |
| `/editor?project=<id>` | `app/editor/page.tsx` (439 dòng, Suspense + `useSearchParams`) | Rail 6 panel (Media/Dub/Cap/Audio/FX/AI) + preview + inspector clip + timeline tracks/clips + handoff |
| `/projects` | `app/projects/page.tsx` | List + tạo project thật qua `createProjectSchema` |
| `/publisher` | `app/publisher/page.tsx` | Bảng project thật, link sang Editor để handoff (không post trực tiếp) |
| `/api/timeline/[...path]` (proxy) | `app/api/timeline/[...path]/route.ts` | Forward GET/POST/PUT/DELETE → `http://127.0.0.1:7860/api/timeline/...`, giữ content-type/disposition, set `origin` + `sec-fetch-site` |

Layout: `app/layout.tsx` — font Inter + JetBrains Mono, `lang="vi"`, bọc `<QueryProvider>`. `components/app-shell.tsx` hiện chỉ là passthrough `<>{children}</>`.

## 3. Dubtool Web — tầng data (tái dùng nguyên si)

```
lib/api/http.ts            → request<T>/api.get-post-put-delete + unwrap({success,result})
lib/api/query-keys.ts      → QUERY_KEYS = all/list/detail(id)  (key: ["projects",...])
lib/api/query-client-config.ts → stale 5', gc 4', retry query 1, mutation retry 0 + console.log
lib/schemas/project.schema.ts  → zod: project, projectList, createProject, planRequest, operation, handoff
lib/services/projects.service.ts → class ProjectsService, PREFIX=/api/timeline, 12 method
hooks/data/useProjects.ts  → useProjects/useProject/useCreateProject/usePlanEdit/useApplyPlan/useOperate/useUndoRedo/useStartRender/useTranscribe/useHandoff
providers/query-client-provider.tsx → useState QueryClient + Devtools chỉ ở development
lib/utils.ts               → cn(clsx + twMerge)
components/ui/primitives.ts → buttonVariants(default/outline/ghost × sm/md), cardClass
```

### Contract BE timeline (qua proxy, envelope `{success, result}`)

| FE method | HTTP | Body chính |
|---|---|---|
| `list()` | `GET /api/timeline/projects` | — |
| `create(input)` | `POST .../projects` | `{title, width, height}` |
| `get(id)` | `GET .../projects/{id}` | — (trả FullProject: `tracks[], assets{}, canvas, duration, revision`) |
| `plan(id, input)` | `POST .../projects/{id}/plan` | `{request, use_ai, clip_id?}` → PlanResult `{project_id, revision, signature, method, operations[], notes[]}` |
| `applyPlan(id, plan)` | `POST .../projects/{id}/plan/apply` | `{plan}` |
| `operate(id, op, expected_revision?)` | `POST .../projects/{id}/operations` | `{operation, expected_revision}` — op.type: add_clip/split_clip/update_clip/update_track/move_clip/delete_clip/duplicate_clip/set_audio_mix/set_canvas/add_track/add_captions/crossfade/speed_ramp/batch |
| `undo/redo(id, expected_revision?)` | `POST .../projects/{id}/undo`, `.../redo` | `{expected_revision}` |
| `transcribe(id, clip_id, language, words, expected_revision?)` | `POST .../projects/{id}/transcribe` | `{clip_id, language, words, expected_revision}` |
| `startRender(id, preview)` | `POST .../projects/{id}/renders` | `{preview}` → job `{id, status}` |
| `job(job_id)` | `GET .../jobs/{job_id}` | — |
| `handoff(id, input)` | `POST .../projects/{id}/handoff` | `{title, description, tags, language: vi\|en\|zh}` |

Pattern mutation: sau operate/undo/redo/apply/transcribe/create → `invalidateQueries(detail(id))` (+ `all` khi đổi list). Editor gọi `refetch()` kèm sau mutate để cập nhật ngay.

## 4. JARVIS — không có FE, chỉ có backend API (FE tương lai sẽ gọi)

Base URL backend: cấu hình `app_host/app_port` (xem `backend/.env`), auth **Bearer token** (`require_http_auth`), CORS allowlist local, chỉ `GET/POST`. Lỗi chuẩn `{detail:{code, message}}`.

| Prefix | File | Endpoint | Ghi chú cho FE |
|---|---|---|---|
| `/health` | `routes/health.py` | `GET /health` | `{status, agent_mode, active_job, browser_profile}` — public, không auth docs |
| `/jobs` | `routes/jobs.py` | `POST /jobs` (202, union `CreateJobRequest` theo `job_type`: browser_task/web_search/web_read/stock_quote/stock_search/github_search/github_read), `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/pause\|resume\|stop` | Job async + replay events |
| (events) | `routes/events.py` | `GET /jobs/{id}/events?after_seq`, `WS /jobs/{job_id}/events` | FE polling/SSE-style qua replay hoặc socket |
| `/assistant` | `routes/assistant.py` | `POST /assistant` (202, `{message, browser_access?}`) → clarify/unsupported (200) hoặc job | Router lệnh tự nhiên |
| `/assistant/plan`, `/plans` | `routes/plans.py` | `POST /assistant/plan`, `GET /plans/{id}`, `GET .../events`, `POST .../stop\|pause\|resume\|amend` | Orchestrator nhiều bước |
| `/extract` | `routes/extract.py` | `POST /extract` `{url, extract_profile: tiktok_tag\|tiktok_user, max_items, summarize, ...}` | Client không truyền JS/selector |
| `/video-analyze` | `routes/video_analyze.py` | `POST` `{url, platform: tiktok\|facebook\|youtube, max_comments, download, summarize, vision_frames}` | Tốn LLM theo vision_frames |
| `/channel-report` | `routes/channel_report.py` | `POST` `{url, max_videos≤10, max_comments, vision_frames}` | Nặng nhất: N×(vision+2) LLM |
| `/tiktok-discover` | `routes/tiktok_discover.py` | `POST` `{kind: hashtag\|sound\|trending\|related\|replies, value, comment_id?, count}` | 0 LLM |
| `/desktop-task` | `routes/desktop_task.py` | `POST` `{steps[1..20], timeout_seconds?}` (allowlist argv, headless) | 0 LLM |
| `/dubtool` | `routes/dubtool.py` | `POST` `{action: check\|download\|translate\|dub, source?, src_lang, tgt_lang, voice_id?, burn_subtitles, use_llm}` | Cầu nối Dubtool |
| `/dubtool-tasks` | `routes/dubtool_tasks.py` | `POST /`, `GET /`, `GET /projects`, `GET /{id}`, `POST /{id}/resume\|stop\|refresh` | Task Dubtool qua JARVIS |
| `/browser-live` | `routes/live_chrome.py` | `GET /status`, `POST /tabs`, `POST /bindings`, `POST /bindings/{id}/read`, `DELETE /bindings/{id}` | Binding existing-CDP read-only |

Schema chi tiết: `backend/app/api/schemas.py` (Pydantic, `extra="forbid"` khắp nơi).

## 5. Khác biệt 2 bên

| Tiêu chí | Dubtool Web | JARVIS |
|---|---|---|
| FE | Có, Next.js App Router thật | Không có |
| Data fetching | TanStack Query + service class + zod | (trống — FE mới phải xây) |
| BE contract | Sync-ish REST + envelope `{success,result}`, proxy same-origin `/api/timeline` | Async job (202) + replay events/WS + Bearer auth + envelope lỗi `{detail}` |
| Validation | zod ở FE (song song BE) | Pydantic `extra=forbid` ở BE |
| Realtime | Polling `job(job_id)` thủ công (editor chưa poll tự động) | WS `/jobs/{id}/events` + `GET events?after_seq` có sẵn |

## 6. Khuyến nghị thống nhất (Next.js + TanStack Query)

1. **Miro FE sao chép khung Dubtool**: `lib/api/http.ts` (mở rộng thêm `authHeader(token)` + `ApiError{code,message}` parse từ `{detail}` của JARVIS), `query-client-config.ts`, `query-keys.ts` (thêm factory `jobsKeys`, `plansKeys`, `assistantKeys`), `providers/query-client-provider.tsx`, `lib/utils.ts + components/ui/primitives.ts` — tái dùng 100%.
2. **Service/hook theo 2 họ**: giữ `ProjectsService` cho timeline 7860; thêm `JobsService` (`POST /jobs`, `GET /jobs/{id}`, pause/resume/stop, `GET events?after_seq`) + `useJobEvents(jobId)` poll `after_seq` (refetchInterval khi status chưa terminal) rồi nâng lên WS sau. Tương tự `PlansService`, `AssistantService`, `ExtractService`, `DubtoolBridgeService`.
3. **Proxy route theo mẫu timeline**: thêm `/api/jarvis/[...path]` forward sang base URL JARVIS, gắn Bearer token phía server (không lộ token ra browser), giữ nguyên pattern forward + passthrough headers.
4. **Schema**: mỗi endpoint JARVIS 1 zod schema mirror Pydantic (`extra=forbid` ≈ `.strict()`), validate trước mutate như `planRequestSchema`/`handoffSchema` đang làm.
5. **Editor timeline** (`editor/page.tsx` 439 dòng) là component lớn nhất đáng tách khi Miro dựng lại: `RailPanel`, `PreviewStage`, `Inspector`, `TimelineTracks`, `HandoffForm` — hiện logic `run()` + `operate` + `expected_revision` đã chuẩn, chỉ cần tách file.
6. Lưu ý đã thấy: `FullProject`/`any` tràn lan ở Editor, `operate` không optimistic update, job preview không poll tự động, `api.get` có `.then(d=>d)` thừa, `gcTime < staleTime` (4' < 5') hơi lạ — Miro nên sửa khi dựng mới.

# Báo cáo toàn diện Web Miro — đầy đủ nhất (để dựng UI prototype)

> Ngày: 2026-11-27. Phạm vi: toàn bộ `apps/web/src` (không chỉ `page.tsx`).
> Đọc file này là đủ để dựng lại UI prototype 1:1.

## 0. Tổng quan kiến trúc FE

- Next 15 (App Router) + React + Tailwind + `@xyflow/react` (editor/workflow canvas).
- Root: `src/app/layout.tsx` — `<html lang="vi">`, font **Inter 400–800** (Google Fonts), title `Miro - AI Operating Workspace`, bọc `Providers` (`src/app/providers.tsx` → `providers/query-client-provider.tsx`, React Query).
- Trang `/` redirect `/workspace`. Còn lại render trong `YoucareShell` (v2: topbar 5 tab + ⋯).
- BE: `127.0.0.1:8770`, FE proxy qua `src/app/api/*` (`lib/be-proxy.ts`, `lib/be.ts`). BE down → EmptyState trung thực, không mock.
- Poll: tasks 2s, events 1.5s, runtime/status 5–10s (`lib/api/poll.ts`, `lib/api/query-keys.ts`).

## 1. Toàn bộ route màn hình (33 page)

### 1.1. `/` — Công việc (redirect)
- File `src/app/page.tsx`: `redirect("/workspace")`. Không UI, không API.

### 1.2. `/overview` — Tổng quan
- `src/app/overview/page.tsx` → `features/overview/OverviewPage.tsx` (đang dùng thật).
- UI: "Chào buổi sáng!" + 2 nút (Mở tác vụ / + Giao việc mới); 4 StatCard (Đang thực thi / Chờ hàng đợi / Cần quyết định / Hoàn tất); split trái list 5 task, phải chi tiết (id, pill status+rev, message, lỗi).
- API: `GET /tasks/recent?limit=50` (`useBeTasks`). BE thật.

### 1.3. `/tasks` — Tác vụ
- `src/app/tasks/page.tsx` → `features/tasks/TasksPage.tsx` (đang dùng thật).
- UI: 4 StatCard (Tổng BE / Đang hoạt động / Đã chọn / Sự kiện); form tạo task ẩn/hiện (message); split trái search + list 30 task (id… + status + rev + badge lỗi), phải chi tiết + 6 nút (Dừng / Chờ dừng / Restart / Resume / Duyệt / Thu hồi) + 5 events.
- API: `GET /tasks/recent`, `GET /tasks/:id`, `GET /tasks/:id/events`, `POST /tasks`, `POST /tasks/:id/{stop,worker-stopped,wait-stop,restart,resume,approve,revoke}`. BE thật.

### 1.4. `/tasks/[taskId]` — alias gọn
- Inline: 1 card (id, status, số events) + link `/tasks-live/:id`. API `useBeTask` + `useBeEvents`. BE thật.

### 1.5. `/tasks-live` — Giao việc live
- Inline: form (message, tabId, limit, videoUrl) + 2 nút mẫu; thẻ out/route; list 20 task + link detail.
- API: `GET /tasks/recent?limit=20`, `POST /tasks/run-message`. BE thật.

### 1.6. `/tasks-live/[id]` — Giám sát live chi tiết
- Inline: header task; form approval (item/scope/revision); 6 nút điều khiển; thẻ msg; timeline events.
- API: `GET /tasks/:id` + `/events` + 6 mutations, poll 1.5–2s. BE thật.

### 1.7. `/publish` — Xuất bản cũ
- Inline: note dry-run; card batch list; card receipt list; link `/publishing`.
- API: `GET /publish/batches`, `GET /publish/receipts`. BE thật. **Trùng `/publishing` → nên redirect gộp.**

### 1.8. `/publishing` — Xuất bản Threads BE-first
- Inline form (text/owner/shortcode/render_id) + 3 nút (Approve / Publish dry-run / Reconcile) + msg; 2 panel (Batch đã gửi / Receipt-đối soát).
- API: `POST /api/threads/{approve,publish,reconcile}` trực tiếp, `allow_post=false`. BE thật.

### 1.9. `/publishing/[publicationId]` — chỉ EmptyState hướng dẫn Reconcile. Không API.

### 1.10. `/schedules` — Lịch hẹn
- Inline: 4 StatCard (Ngày/status / Slots / Pending / Unknown); 2 nút (Ensure day-plan / Tạm dừng-Bật lại); list 20 slot.
- API: `GET /schedule/day-plan`, `POST /schedule/ensure`, `PATCH /schedule/day-plan/status`. BE thật.

### 1.11. `/schedules/[scheduleId]` — tìm slot theo `intent_id/id`, hiện JSON. API `GET /schedule/day-plan`. BE thật.

### 1.12. `/browser` — Trình duyệt
- Inline: 4 StatCard (Tabs BE / Wiring / Lỗi bridge / BE); list tab; note Gateway (mọi thao tác qua Browser Gateway); link `/tasks-live`.
- API: `GET /tasks/runtime/status` → `bridge.tabs`. BE thật, read-only.

### 1.13. `/browser/[profileId]` — lọc `bridge.tabs` theo profileId/tab. Cùng API. Trống nếu profile không có tab.

### 1.14. `/runtime` — Runtime
- Inline: 4 StatCard (BE / Wiring / Bridge tabs / Tasks BE); list tab; link `/tasks-live`.
- API: `GET /tasks/runtime/status`. BE thật.

### 1.15. `/workspace` — AI Workspace (đích redirect của `/`)
- 1 card + 2 link (`/tasks-live`, `/tasks`), note "hợp nhất vào Giám sát live". Không API, tĩnh.

### 1.16. `/library` — Thư viện
- Inline grid cards (title, revision, duration, canvas) + link `/editor?project=`.
- API: `GET /library` (`useLibrary`). BE thật nhưng production chưa có route → 404/405 hiện lỗi trung thực.

### 1.17. `/editor` — Editor
- Inline EditorInner: timeline tracks/clips, playhead, kéo-thả local, form subtitle (zod), nút command/render/approve.
- API: `GET /library`, `GET /projects/:id`, `POST …/operations|renders|approve`. BE thật; projectId rỗng → empty-state.

### 1.18. `/media` — Media: input `video_id` + nút "Tải project" + `<pre>` JSON. `fetch /api/studio/project/:videoId` trực tiếp. BE thật theo id nhập tay, mặc định trống.

### 1.19. `/media/[assetId]` — như trên, prefill từ param.

### 1.20. `/projects` — Dự án (master-detail): 4 StatCard + list 20 projects + panel JSON. API `useLibrary` + `useProject(id)`. BE thật.

### 1.21. `/projects/[projectId]` — title theo param + `<pre>` JSON. API `GET /projects/:id`. BE thật.

### 1.22. `/research` — Nghiên cứu: input query + Tìm kiếm + `<pre>` kết quả. API `POST /api/research/search {query, limit:10}`. BE thật, trống đến khi tìm.

### 1.23. `/research/[researchId]` — chỉ EmptyState. Không API.

### 1.24. `/workflows` — chỉ EmptyState (BE chưa có endpoint). Không API.

### 1.25. `/workflows/[workflowId]` — chỉ EmptyState. Không API.

### 1.26. `/knowledge` — chỉ EmptyState (BE chưa có endpoint). Không API.

### 1.27. `/activity` — Hoạt động: 4 StatCard (tasks theo dõi / có lỗi / có evidence / BE) + timeline 20 task. API `GET /tasks/recent?limit=50`. BE thật.

### 1.28. `/integrations` — Tích hợp: 4 StatCard + list 20 accounts. API `connections/accounts` + platform registry. BE thật.

### 1.29. `/settings` — Cài đặt: 2 link cards (connections, platforms) + EmptyState credential-ref. Không API, tĩnh.

### 1.30. `/settings/connections` — form tạo account (zod) + form verify evidence + bảng accounts + nút verify/reconnect/pause/revoke/set-default. API connections + mutations. Secret chỉ ref.

### 1.31. `/settings/platforms` — bảng registry capabilities (list/download/draft/publish/reconcile/watch, badge READY/DEGRADED/BLOCKED) + form upsert/clone/rollback + history. API registry + mutations.

### 1.32. `/prototype` — demo ChatGPT/Claude tự chứa (sidebar tối, composer pill, 5 tab, nút duyệt/từ chối/dừng, log). 3 task `dub-1042/1041/1039` hard-code, state local. **Mock 100% — không tính production.**

## 2. Ba lớp shell/nav (đủ — dễ nhầm)

### 2.1. Sidebar cũ `components/miro-nav.tsx` (12 link)
`/`, `/tasks-live`, `/runtime`, `/library`, `/publish`, `/editor`, `/settings`, `/settings/connections`, `/settings/platforms`, `/workspace`, `/tasks`, `/overview`. Style: flex row, aside 220px (trong file). Có comment BUG-03 link chéo shell mới.

### 2.2. Shell `components/miro-layout/*` = AppShellຊ້ cũ đầy đủ (hiện KHÔNG dùng — route đang dùng YoucareShell)
- `AppShell.tsx`: theme (midnight-lime/navy-cream/light/system) + lang lên `<html>`, Cmd/Ctrl+K, desktop sidebar + mobile drawer + **mobile bottom nav 5 nút** (AI / Tổng quan / Tác vụ / Giám sát / Duyệt + dot cảnh báo), overlay `TaskMonitorDrawer` + `ApprovalCenterDrawer` + `ContextualAiAssistantDrawer` + `CommandPalette` + `Toaster`.
- `GlobalSidebar.tsx` — **16 item / 4 nhóm collapsible** (đây chính là mẫu "kho" để dựng prototype):
  - WORKSPACE: Tổng quan (`/overview`, LayoutDashboard), AI Workspace (`/workspace`, MessageSquare), Tác vụ (`/tasks`, ListChecks + badge runningCount), Dự án (`/projects`, Folder).
  - TỰ ĐỘNG HÓA: Lịch trình (`/schedules`, CalendarClock), Workflows (`/workflows`, Workflow).
  - CÔNG CỤ: Trình duyệt (`/browser`, Globe), Nghiên cứu (`/research`, Search), Media Studio (`/media`, Film), Xuất bản (`/publishing`, Send), Tri thức (`/knowledge`, BookOpen).
  - HỆ THỐNG: Hoạt động (`/activity`, Activity), Tích hợp (`/integrations`, Plug), Cài đặt (`/settings`, Settings), Giao việc live (`/tasks-live`, MessageSquare), Runtime live (`/runtime`, Chrome).
  - Khung: rộng 224px (thu 56px), top MiroWordmark + nút thu/mở, workspace selector `defaultWorkspace + LOCAL`, quick search (⌘K) + nút Hội thoại mới, group header UPPERCASE 10px + ChevronDown thu/mở, item active nền accent-subtle + vạch 2.5px, bottom runtime OK + avatar Operator Asia/Bangkok + nút đổi theme.
- `GlobalHeader.tsx` (52px): breadcrumb `primaryCrumb + / + resourceLabel`, nút Back-to-Conversation, demo-mode label, counter running + nút approvals/interventions + chuông + nút Miro AI.
- `CommandPalette.tsx`, `TaskMonitorDrawer.tsx`, `ApprovalCenterDrawer.tsx`, `ContextualAiAssistantDrawer.tsx`: palette + 3 drawer toàn cục (đọc store).
- `components/miro-shell.tsx`: wrapper mount-guard → `<AppShell>`.

### 2.3. Shell v2 đang dùng `components/youcare/*`
- `YoucareShell.tsx`: topbar logo M + 5 tab pill đen (Tổng quan/Tác vụ/Xuất bản/Lịch hẹn/Trình duyệt) + 3 icon + ⋯ (10 trang còn lại: live/runtime/projects/media/research/workflows/knowledge/activity/integrations/settings); title 26px + actions; breadcrumb `Miro / X`; helpers `StatCard/EmptyState`.
- `youcare.css`: Inter-only, nền `#e7e5f6`, card trắng radius 16–24, split 400px+1fr, pill/table/form/evt.

### 2.4. Shared + primitives
- `miro-shared/`: `MiroWordmark`, `LiveTaskCard`, `LiveWorkspacePanel`, `OwnershipBanner`, `RuntimeBridgeBanner`.
- `miro-ui/primitives.tsx`: Button (primary/ghost/secondary/subtleAccent, sm/icon) + tiện ích.
- `lib/router-compat.tsx`: NavLink/useLocation/useNavigate tương thích.

## 3. Lớp API proxy FE (`src/app/api/*` → BE, 50 route)
- health: `api/health`, `api/test-reset`, `api/history`.
- tasks: `api/tasks` (POST), `api/tasks/recent`, `api/tasks/chat`, `api/tasks/run-message`, `api/tasks/runtime/status`, `api/tasks/[id]` (+`approve|events|restart|resume|review|revoke|stop|wait-stop|worker-stopped`).
- threads/publish: `api/threads/{approve|history|prepare|publish|reconcile}`, `api/publish/batches`, `api/publish/receipts`, `api/publications`.
- schedule: `api/schedule/{day-plan|day-plan/status|ensure}`.
- studio/projects: `api/projects/[id]` (+`approve|operations|renders|subtitles/[clipId]`), `api/studio/project/[id]`, `api/studio/media/[id]`, `api/library`, `api/renders`.
- research: `api/research/{channel|compare|read|search|to-project|video}`.
- settings: `api/settings/{connections|platforms}` (+`platforms/[id]/clone`, `platforms/rollback`), `api/connections/accounts` (+`[id]`, `[id]/[action]`), `api/platforms`.

## 4. Hooks + services + store + i18n + domain (để prototype biết state thật)
- `hooks/data/useRuntime.ts` → `services/runtime.service.ts`: status/recent/task/events/create/run-message/stop/wait-stop/restart/resume/approve/revoke + day-plan/ensure/status. `useConnections.ts`, `useMiro.ts` (library/batches/receipts/project/operations/renders/approve/studio), `useHealth.ts`.
- `services/`: `runtime.service.ts`, `miro.service.ts`, `connections.service.ts`, `platforms.service.ts`; `threads/{be,flow}.ts`; `lib/api/{http,poll,query-keys,query-client-config}.ts`; `lib/{be,be-proxy,format,utils}.ts`; `lib/schemas/miro.schema.ts` (zod).
- `stores/useMiroStore.ts` (zustand+persist): tasks, approvals, interventions, notifications, conversations/messages, projects/media/research/workflows/knowledge/integrations/schedules, settings (theme/language/sidebarCollapsed/defaultWorkspace), drawers (taskMonitor/approvalCenter/aiAssistant/commandPalette/mobileNav), activeContext, lastConversationRouteId. Seed từ `proto-services/mock/seedData.ts` (mock) — route BE-first hiện không đọc store này.
- `domain/`: `types.ts` (Task, Project, Publication, Schedule, Workflow, Research, Knowledge, Integration...), `taskMachine.ts` (+test).
- `i18n/translations.ts` (vi+en): nav groups WORKSPACE/TỰ ĐỘNG HÓA/CÔNG CỤ/HỆ THỐNG, 16 label (Tổng quan/AI Workspace/Tác vụ/Dự án/Lịch trình/Workflows/Trình duyệt/Nghiên cứu/Media Studio/Xuất bản/Tri thức/Hoạt động/Tích hợp/Cài đặt/Giao việc live/Runtime live), header, workspace (composer...), brand demoMode "Chế độ Mô phỏng".
- `features/*Page.tsx` (14 file: activity, ai-workspace, browser, integrations, knowledge, media, overview, projects, publishing, research, schedules, settings, tasks, workflows): **chỉ overview/tasks đang được route dùng**, còn lại tồn tại nhưng route hiện inline — đừng nhầm là đang dùng.
- `proto-services/`: `backend/miroBackend.ts`, `contracts/miroApi.ts`, `mock/{executionEngine,seedData}.ts` — mock cũ, BE-first không dùng.
- `lib/fixtures/store.ts` — fixture cũ, không dùng ở route BE-first.

## 5. Trùng lặp cần dọn khi dựng prototype
- `/publish` vs `/publishing` (giữ 1), `/` vs `/tasks`, `/tasks/[taskId]` vs `/tasks-live/[id]`, `/workspace` note hợp nhất vào live.
- `features/*` chưa dùng (trừ overview/tasks) — prototype dựng theo route inline + mục 1.
- `/prototype` mock — loại khỏi production.

## 6. Gợi ý map 21 route vào sidebar kho (để dựng prototype)
- WORKSPACE: Tổng quan, Tác vụ, Giám sát live, AI Workspace.
- NỘI DUNG & XUẤT BẢN: Xuất bản (`/publishing`; `/publish` redirect), Thư viện, Editor, Media, Dự án, Nghiên cứu, Quy trình.
- VẬN HÀNH: Lịch hẹn, Trình duyệt, Runtime, Hoạt động.
- HỆ THỐNG: Tích hợp, Cài đặt (gộp connections+platforms tab con), Tri thức.

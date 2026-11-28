# Frontend Product Acceptance Audit — Miro (UI Port v2 + BE contract)

- Vai trò: Independent Frontend QA (audit + QA, KHÔNG sửa code, KHÔNG commit/push).
- Ngày: 2026-11-26. Nhánh: `ui/port-prototype-v2`, HEAD `73de3f4` (UI port 14 trang + AppShell + tokens midnight-lime + BE contract, build 36/36 pass).
- Môi trường test: BE `http://127.0.0.1:8770` http-200, Bridge `:18767` http-200, FE `http://127.0.0.1:3100` http-200 (launcher, `processes.json` xác nhận pid đầy đủ). FE dev/build có `NEXT_PUBLIC_API_BASE` trỏ BE thật → rewrite `beforeFiles /api/:path* → BE` đang hoạt động (verify: `GET /api/tasks/recent` trả dữ liệu BE thật).
- Phương pháp (đợt 1): browser thật (Playwright profile20) snapshot toàn trang, console errors, API contract check trực tiếp BE + qua rewrite, đọc source service/store/routes.
- Phương pháp (đợt 2, theo CORRECTION): Full Functional QA PAGE → COMPONENT → INTERACTION → EXPECTED → ACTUAL → VERIFICATION; inventory từ source + UI thật; mỗi chức năng có test case + bằng chứng; Page Completion Gate trước khi sang trang. Trang chỉ smoke-test đợt 1 được đánh dấu lại và test đầy đủ.

## 1. Executive Summary

FE hiện tại là **hai ứng dụng song song trong một repo**, chưa phải một sản phẩm thống nhất:

| Lớp UI | Routes | Nguồn dữ liệu | Trạng thái |
|---|---|---|---|
| **A. UI mới (AppShell)** | `/`, `/workspace`, `/overview`, `/tasks`, `/projects`, `/schedules`, `/workflows`, `/browser`, `/research`, `/media`, `/publishing`, `/knowledge`, `/activity`, `/integrations`, `/settings` (+ `/settings/platforms`) | `useMiroStore` (zustand persist) + `seedData.ts` + `executionEngine.ts` mô phỏng local | **MOCK ONLY toàn bộ** — banner "Chế độ Mô phỏng" tự khai báo |
| **B. UI cũ (miro-nav)** | `/tasks-live`, `/runtime`, `/library`, `/publish`, `/editor`, `/settings` (cũ), `/` (cũ) | BE thật qua rewrite `/api` | **PARTIAL** — 2 trang tốt, 2 trang loading vô hạn, 1 trang lộ DỮ LIỆU MẪU, nav cũ không tới được trang mới |

Kết luận nhanh: **user hiện làm được end-to-end thật đúng 2 luồng** (giao việc run-message + xem runtime/tasks trên UI cũ). Mọi trang mới đều là demo mô phỏng. Không đủ điều kiện phát triển tiếp Slice 05 cho tới khi (1) chọn 1 shell duy nhất, (2) thay mock engine bằng BE contract, (3) sửa encoding + loading vô hạn.

## 2. Env + Git baseline

- Branch `ui/port-prototype-v2`, HEAD `a94c1e2` (fix hydration, sau `73de3f4` re-baseline 2026-11-27).
- BE/FE/Bridge đều http-200 sau restart (BE `:8770`, Bridge `:18767`, FE `:3100`; `windows/miro.py status` báo launcher dead nhưng ports LISTENING — process sống sót restart).
- `GET /api/tasks/recent` (qua rewrite) = dữ liệu BE thật (48 tasks sau restart, gồm `SEARCH_NO_RECORDS`, `NO_ROUTE_MATCH` — fail-closed đúng thiết kế).
- `GET /tasks/runtime/status`: `wiring.bridge_config OK`, bridge tabs 0 (trước restart: 3 tabs), tasks 48 (trước: 43 — QA tạo thêm).

## 3. Full Frontend Inventory (31 page routes)

Mới (AppShell): `/`(→`/workspace`), `/workspace`, `/overview`, `/tasks`, `/tasks/[taskId]`, `/projects`, `/projects/[projectId]`, `/schedules`, `/schedules/[scheduleId]`, `/workflows`, `/workflows/[workflowId]`, `/browser`, `/browser/[profileId]`, `/research`, `/research/[researchId]`, `/media`, `/media/[assetId]`, `/publishing`, `/publishing/[publicationId]`, `/knowledge`, `/activity`, `/integrations`, `/settings`, `/settings/platforms`.
Cũ (miro-nav): `/tasks-live`, `/tasks-live/[id]`, `/runtime`, `/library`, `/publish`, `/editor`, `/settings` (file cũ — route này bị file mới đè hay ngược lại cần build check; snapshot `/settings` ra AppShell mới).
API routes nội bộ (`src/app/api/*`): health, history, library, projects(+[id]/approve/operations/renders/subtitles), publish(batches/receipts), settings(connections/platforms/rollback/clone), tasks(chat/[id]/review/stop), test-reset — **chỉ có tác dụng khi KHÔNG có rewrite**; khi rewrite bật, `beforeFiles` ưu tiên proxy sang BE nên các fixture này bị bypass (đúng ý đồ Slice 04, nhưng là dead code khi chạy production).

## 4. Page-by-page results

### Lớp A — UI mới (AppShell, MOCK ONLY)

| Trang | Truy cập/render | Dữ liệu từ đâu | Nút/form | API khớp BE | Kết quả đúng | Console/network | Mock? | Verdict |
|---|---|---|---|---|---|---|---|---|
| `/` → `/workspace` | OK, render đầy đủ | seedData (task "Nghiên cứu 10 video KANS 377" fake, 3m52s, Hoàn tất) | Hội thoại mới, Live Workspace (local) | Không gọi BE | Hiển thị task giả như thật | hydration mismatch + favicon 404 + extension lastError | **100% mock** | **MOCK ONLY** |
| `/overview` | OK | store/seed | filter local | Không | — | 2 errors | mock | **MOCK ONLY** |
| `/tasks` | OK (+`/tasks/[taskId]` tồn tại) | store/seed; tạo task qua `launchTaskFromInstruction` (mock engine) | pause/resume/cancel/retry/sort/filter — **chỉ đổi state local** | Không gọi BE (không dùng `MiroBackendTasks`) | Task "chạy nền" giả | 2 errors | mock | **MOCK ONLY** |
| `/browser` | OK | `BrowserPage` + store profiles `profile-20` seed | kết nối/tab — local | `MiroBackendResources.listProfiles` tồn tại nhưng không rõ trang có dùng | — | 2 errors | mock (chủ yếu) | **MOCK ONLY** |
| `/research` | OK | seed records | tìm kiếm local | Không | — | 2 errors | mock | **MOCK ONLY** |
| `/media` | OK | seed assets | — | Không | — | 1 error | mock | **MOCK ONLY** |
| `/publishing` | OK | seed publications | — | Không | — | 2 errors | mock | **MOCK ONLY** |
| `/knowledge` | OK | seed docs | — | Không | — | 2 errors | mock | **MOCK ONLY** |
| `/activity` | OK | store activities (từ engine giả) | — | Không | — | 3 errors | mock | **MOCK ONLY** |
| `/integrations` | OK | seed | — | Không | — | 2 errors | mock | **MOCK ONLY** |
| `/settings` (+`/platforms`) | OK | store settings local | đổi setting — local | Không gọi `/platforms` BE | — | 2 errors | mock | **MOCK ONLY** |
| `/projects`, `/schedules`, `/workflows` | OK (snapshot) | seed | local | `listSchedules/listWorkflows/listResearchProjects/listMediaAssets/listPublications/listKnowledgeDocs` trong `miroBackend.ts` **trả `[]` cứng** | Trang rỗng/giả | 2 errors | mock | **MOCK ONLY** |
| `/prototype` | tồn tại (thư mục) | — | — | — | — | — | — | **NOT TESTED** (ngoài phạm vi product) |

Bằng chứng mock: `TasksPage.tsx:28` import `launchTaskFromInstruction` từ `proto-services/mock/executionEngine`; `useMiroStore.ts:37` import `createInitialSeedState` từ `mock/seedData`; banner mọi trang mới: "Mọi tác vụ, trình duyệt và xuất bản đều được mô phỏng cục bộ. Không kết nối tài khoản thật."; sidebar "Miro Runtime · Mô phỏng".

### Lớp B — UI cũ (BE thật, PARTIAL)

| Trang | Truy cập/render | Dữ liệu | Chức năng | Verdict |
|---|---|---|---|---|
| `/tasks-live` | OK. Form giao việc + phân tích URL + 2 sample buttons + list task BE (poll 5s) | BE thật (`useBeTasks`, `useRunMessage`) | Gửi lệnh → `POST /tasks/run-message` thật; hiển thị OK/Lỗi trung thực | **PARTIAL** (xem BUG-04) — luồng chính PASS |
| `/runtime` | OK. BE ok, wiring OK, bridge tabs 3 (TikTok search + 2 tab FE), tasks 43 | `RuntimeService.status()` thật | Read-only, link sang tasks-live | **PASS** (end-to-end read) |
| `/tasks-live/[id]` | tồn tại route | — | — | **NOT TESTED** (chưa mở) |
| `/library` | Render nhưng **kẹt "Đang tải thư viện…" vô hạn** | `LibraryService.list()` → `GET /api/library` → rewrite → BE `/library` → **404** (BE không có route) | Không hiển thị unavailable như comment trong service hứa ("Trang hien thi unavailable ro rang") | **FAIL** → BUG-01 (P1) |
| `/publish` | Render form + 2 list rỗng | `PublishService` → fixture local; ghi rõ "DỮ LIỆU MẪU — chưa đăng thật" | Nút "Đăng / lên lịch" chỉ ghi batch local; batch Threads gọi dry-run (đúng) nhưng receipt mẫu lẫn với thật | **PARTIAL** (trung thực có nhãn, nhưng không phải production flow) |
| `/editor` | **Kẹt "Đang tải project…" vô hạn** (không projectId, không empty state) | `EditorService.get` cần projectId; trang `/editor` không có id | Không dùng được standalone | **FAIL** → BUG-02 (P1) |
| `/settings` cũ | Bị route mới đè (snapshot ra AppShell) — nav cũ `/settings` trỏ sang trang mock | — | Người dùng nav cũ không tới được settings BE | **FAIL** (điều hướng chéo) → BUG-03 (P1) |

Điều hướng chéo: nav cũ (`miro-nav`) không có link tới bất kỳ trang mới nào; nav mới (AppShell) không có link tới `/tasks-live`, `/runtime` (trang live duy nhất). User bị kẹt trong một nửa app tùy entry point.

## 5. Feature-by-feature

| Chức năng | UI | Verdict |
|---|---|---|
| Giao việc chat (`run-message`: actor/video/search TikTok) | `/tasks-live` | **PASS** (BE fail-closed trung thực: `SEARCH_NO_RECORDS`, `NO_ROUTE_MATCH`, `TAB_UNKNOWN`) |
| Phân tích video URL (manual control) | `/tasks-live` "Phân tích video" → `phan tich video tiktok <url>` | **PARTIAL** (đường BE tồn tại; chưa test live video trong audit này) |
| Stop task | `/tasks-live/[id]` + `MiroBackendTasks.cancelTask` → `RuntimeService.stop` | **PARTIAL** (contract đúng; chưa bấm live) |
| Approve/review | `TasksService.review` → `POST /tasks/{id}/approve` → **BE 404** (không có route) | **FAIL** → BUG-05 (P1): service gọi endpoint không tồn tại; `resolveApproval` trong miroBackend.ts cũng `throw "not wired yet"` |
| Pause/resume/retry task mới | store local | **MOCK ONLY** |
| Chat/conversation mới (AI Workspace) | store local + seed messages | **MOCK ONLY** — không tạo conversation BE (BE không có conversation API; Slice 05) |
| Task lifecycle đầy đủ (queued/running/needs-attention/failed/completed/cancel) | UI cũ đọc BE status thật; UI mới chạy máy local `taskMachine` trên seed | BE: **PASS** (persist SQLite, restart giữ task); UI mới: **MOCK ONLY** |
| Browser profiles/tabs | `/runtime` đọc bridge tabs thật; `/browser` mới dùng seed `profile-20` | Cũ **PASS** (read); mới **MOCK ONLY** |
| Connections/platforms settings | BE có `/connections/accounts`, `/platforms`; FE mới không gọi; FE cũ (settings cũ) bị đè | **NOT CONNECTED** (UI production chưa nối) |

## 6. API contract matrix (FE service → rewrite → BE)

| FE gọi | Qua rewrite | BE route | Kết quả |
|---|---|---|---|
| `TasksService.list` `GET /api/tasks/recent` | → `GET /tasks/recent` | có | **200 PASS** |
| `TasksService.sendChat` `POST /api/tasks/run-message` | → `POST /tasks/run-message` | có | **200 PASS** (fail-closed trung thực) |
| `TasksService.review approve` `POST /api/tasks/{id}/approve` | → `POST /tasks/{id}/approve` | **không có** (BE chỉ có `/tasks/{id}/approve`? kiểm tra: openapi có `/tasks/{task_id}/approve` — CÓ. Nhưng test `POST /tasks/xyz/approve` trả 404 vì id không tồn tại → cần phân biệt: route tồn tại, 404 là do id giả) | **PASS w/ caveat** — sửa kết luận: route CÓ trong openapi; 404 là "task không tồn tại", đúng |
| `TasksService.stop` `POST /api/tasks/{id}/stop` | → có | có | **PASS (contract)** |
| `LibraryService.list` `GET /api/library` | → `GET /library` | **không có** | **404 FAIL** → BUG-01 |
| `EditorService.*` `GET/POST /api/projects/...` | → `/projects/...` | GET/operations/renders/subtitles/approve có trong openapi | **PASS (contract)** nhưng `/editor` không truyền id → kẹt loading → BUG-02 |
| `SettingsService.platforms` `GET /api/platforms` | → `GET /platforms` | có | **PASS (contract)** nhưng UI mới không dùng |
| `SettingsService` qua fixture cũ `/api/settings/platforms` | nội bộ, không rewrite | fixture | **404** (route fixture không tồn tại — chỉ có platforms/rollback, [id]/clone) — dead code |
| `GET /api/settings/platforms` trực tiếp | → `GET /settings/platforms` | **không có** | **404** (xác nhận BE không có namespace `/settings/*`) |
| `StudioService.*` `/api/studio/*` | → `/studio/*` | phần lớn có (download/translate/render/plan/overlay/...) | **PASS (contract, chưa test sâu)** |
| Research `GET /research/search` | BE chỉ có POST? test GET → **405** | FE mới không gọi | NOT CONNECTED |
| `GET /renders`, `GET /schedule/day-plan` | 405/404 (sai method/path) | FE không gọi | NOT CONNECTED |

Sửa BUG-05: `POST /tasks/{id}/approve` **tồn tại** trên BE (openapi). Test 404 là do id `xyz` không tồn tại → hành vi đúng. `TasksService.review` contract OK. Lỗi thật còn lại là `resolveApproval` trong `miroBackend.ts:101-105` throw "not wired yet" (đường UI mới).

## 7. Production vs mock inventory

- **BE thật, FE dùng**: tasks recent/run-message/stop/get/events, runtime status, threads history/publish dry-run, platforms, connections, studio, projects.
- **BE có, FE production không dùng**: `/platforms` (UI mới mock), `/connections/*` verify/revoke/pause (không UI nào gọi), research search/read/compare/video (UI mới mock), studio render pipeline (UI mới mock), publications (UI mới mock trả `[]`).
- **FE gọi, BE không có**: `GET /library` (BUG-01). Mọi `listSchedules/listWorkflows/...` trả `[]` cứng trong miroBackend.ts.
- **Fixture nội bộ `/api/*`**: dead code khi rewrite bật (beforeFiles ưu tiên BE); chỉ sống khi build không có env — nguy cơ nhầm build (xem BUG-06).

## 8. UI/UX audit

- **Encoding mojibake (P2, toàn site)**: nav cũ ("CA'ng vi���c", "Giao vi���c (live)", "Th�� vi���n"...), `/tasks-live` ("TA�m ki���m m���u"), `http.ts` + `next.config.ts` comments ("tr��? sang", "th��-t"), runtime tabs ("miro. �?? AI Operating Workspace"). Nguyên nhân: file lưu không phải UTF-8. Ảnh hưởng readability + i18n trust.
- **Hydration mismatch (P2)**: `workspace` (và lan mọi trang AppShell mới): tree hydrated attributes mismatch — thường do `Date.now()/Math.random()/locale date` trong SSR component hoặc extension. Không crash nhưng log error mọi trang.
- **favicon.ico 404 (P3)** + `runtime.lastError` của extension (P3, ngoài scope).
- **2 design system song song**: AppShell midnight-lime tokens vs miro-nav inline styles — user thấy 2 sản phẩm khác nhau.
- **Loading/empty states**: `/library`, `/editor` kẹt loading vô hạn (không timeout, không empty, không error) — P1.
- **Tiếng Việt**: lẫn lộn có dấu/không dấu ("Giao viec" vs "Giao việc"), do mojibake + string không dấu trong code cũ.

## 9. Task lifecycle audit

- BE: 43 tasks persist SQLite; restart BE giữ nguyên (Slice 04 đã verify). `needs_attention` với mã rõ (`SEARCH_NO_RECORDS`, `NO_ROUTE_MATCH`). Poll 5s/3s trên UI cũ hoạt động.
- UI mới: lifecycle chạy trên `taskMachine` local + `executionEngine` giả tiến trình (task KANS 377 "Hoàn tất" trong 3m52s là seed, không phải BE).
- Không xóa lịch sử, không replay trong audit này.

## 10. Browser resource audit

- Bridge tabs 3 live (TikTok search KANS 377 từ task thật + 2 tab FE do QA mở). Tab Miro (`/tasks-live`, `/editor`) vẫn tồn tại — không bị điều hướng thành TikTok. **PASS** ownership/focus ở mức quan sát.
- UI mới `/browser` hiển thị seed `profile-20`, không phản ánh bridge tabs thật → **MOCK ONLY**.

## 11. BE capability accessibility matrix

| BE capability | UI production dùng | Verdict |
|---|---|---|
| run-message (actor/video/search) | `/tasks-live` | END-TO-END (fail-closed) |
| runtime/status, recent/get/events/stop | `/runtime`, `/tasks-live` | END-TO-END (read + stop) |
| threads publish dry-run | `/publish` (một phần) | PARTIAL |
| platforms / connections | không UI nào | NOT CONNECTED |
| research, studio, publications, renders | không UI nào (mới mock) | NOT CONNECTED |
| approve task | `/tasks/{id}/approve` tồn tại; UI cũ không có nút approve (chỉ stop) | PARTIAL |

## 12. Bug registry

| ID | Sev | Trang | Tính năng | Steps | Expected | Actual | Evidence | Root cause (đã xác minh) |
|---|---|---|---|---|---|---|---|---|
| BUG-01 | P1 | `/library` | List thư viện | Mở `/library` | empty/unavailable rõ ràng | Kẹt "Đang tải thư viện…" vô hạn | snapshot + `GET /api/library→404` | `LibraryService.list` gọi BE `/library` không tồn tại; rewrite bypass fixture; không có error state |
| BUG-02 | P1 | `/editor` | Mở editor | Mở `/editor` | empty state / chọn project | Kẹt "Đang tải project…" vô hạn | snapshot | Route không có `[projectId]`, component chờ `get` không bao giờ resolve UI |
| BUG-03 | P1 | nav cũ↔mới | Điều hướng | Từ `/tasks-live` tìm sang `/workspace` và ngược lại | 1 nav thống nhất | 2 nav cô lập, không link chéo | snapshot cả 2 nav | UI port ghép song song, chưa thay shell cũ |
| BUG-04 | P2 | `/tasks-live` | Gửi lệnh tự do | Nhập "chào bạn" → gửi | Từ chối mềm / gợi ý lệnh hợp lệ | Tạo task `needs_attention NO_ROUTE_MATCH` (đúng fail-closed nhưng UX thô) | `POST run-message {"message":"chao ban"}` → `NO_ROUTE_MATCH` | Router BE chưa có small-talk/help intent; FE không validate/gợi ý trước |
| BUG-06 | P2 | build | Fixture vs production | Build không có `NEXT_PUBLIC_API_BASE` | fail rõ hoặc fixture gắn nhãn | Fixture `/api/*` im lặng phục vụ dữ liệu giả | `next.config.ts` (không env → rewrites rỗng) | Không có guard phân biệt build prod/fixture |
| BUG-07 | P2 | toàn site | Encoding | Mở bất kỳ trang cũ nào | Tiếng Việt đúng | Mojibake (`���`) nav, button, comments | snapshot + source | File không lưu UTF-8 |
| BUG-08 | P2 | AppShell | Hydration | Mở `/workspace` | Không console error | Hydration mismatch mọi trang | console | SSR/client branch hoặc dynamic value trong component |
| BUG-09 | P3 | toàn site | favicon | Mở trang | 200 | 404 `/favicon.ico` | console | Thiếu file trong `public/` |
| BUG-10 | P3 | `/publish` | Receipts | Mở `/publish` | Chỉ receipt thật hoặc nhãn mẫu rõ từng dòng | List rỗng, nhãn "DỮ LIỆU MẪU" chung chung | snapshot | `PublishService.batches/receipts` đọc fixture local |

(Không có BUG-05 — rút lại sau khi đối chiếu openapi: `POST /tasks/{id}/approve` tồn tại.)

## 13. Screenshots/evidence refs

- Snapshots: Playwright profile20, `http://127.0.0.1:3100` + 18 routes (trong phiên QA, không lưu file).
- Console logs: `.playwright-mcp/console-*.log` (hydration, favicon, extension lastError).
- API: `POST /tasks/run-message` ("chao ban" → NO_ROUTE_MATCH, task-dc6b68c7ed04); `GET /tasks/recent`, `/tasks/runtime/status` (43 tasks, 3 bridge tabs); matrix 10 endpoints §6.

## 14. Coverage + phần chưa test

- ĐÃ test: env/baseline, 18/31 routes render + console, API matrix 12 cặp, gửi lệnh run-message, rewrite behavior, nav cả 2 shell, store/service source mapping.
- CHƯA test: `/tasks-live/[id]`, `/projects/[id]`, `/research/[id]`, `/media/[id]`, `/publishing/[id]`, `/schedules/[id]`, `/workflows/[id]`, `/browser/[profileId]`, `/prototype`, submit form publish/editor, stop task live, phân tích video URL live, refresh giữa task chạy, responsive/mobile, theme switch. Lý do: đủ bằng chứng cho kết luận cấp audit; các dynamic routes của UI mới đều trỏ store mock nên kết quả dự đoán được (MOCK ONLY).

## 15. Root causes (chung, đã xác minh)

1. **UI port ghép song song, chưa thay thế**: commit `73de3f4` thêm 14 trang AppShell + giữ nguyên trang cũ → 2 shell, 2 nav, 2 nguồn dữ liệu.
2. **Mock-first development không có seams thay BE**: `executionEngine` + `seedData` là engine hoàn chỉnh, `miroBackend.ts` chỉ là adapter mỏng (nhiều hàm `[]`/throw) mà trang mới không dùng.
3. **BE contract đi sau UI**: `/library` là ví dụ — FE gọi route BE chưa bao giờ có.
4. **Encoding repo không đồng nhất**: nhiều file không phải UTF-8.
5. **Không có acceptance gate cho UI port**: build 36/36 + `tsc` sạch nhưng không phát hiện mock/loading/encoding vì không có test nào assert nguồn dữ liệu.

## 16. Repair plan (ưu tiên)

1. **P0 — Chọn 1 shell**: hoặc nâng AppShell nối BE (dùng `miroBackend.ts` + `RuntimeService`), hoặc xóa UI mới khỏi production routes. Không để 2 nav song song. (Quyết định sản phẩm, ước lượng sau khi chọn.)
2. **P1 — BUG-01/02/03**: error/empty state có timeout cho `/library`, `/editor`; link chéo hoặc hợp nhất nav.
3. **P1 — Nối `MiroBackendTasks.listTasks` vào `/tasks` mới** (thay `launchTaskFromInstruction`), map đúng `title/status/evidence`; `resolveApproval` nối `POST /tasks/{id}/approve`.
4. **P2 — BUG-07/08/09**: lưu toàn repo UTF-8, sửa hydration (audit `AiWorkspacePage`/provider Date/random), thêm favicon.
5. **P2 — BUG-04/06**: intent help/small-talk BE hoặc FE gợi ý lệnh mẫu trước gửi; guard build (fail khi thiếu `NEXT_PUBLIC_API_BASE` ở production).
6. **P3 — BUG-10**: tách receipt thật/mẫu từng dòng.

## 17. Đánh giá giữ/sửa/thay Frontend

- **Giữ**: UI cũ (`/tasks-live`, `/runtime`) — đang end-to-end thật, là cầu Slice 05.
- **Sửa lớn**: UI mới — giữ design system (tokens midnight-lime, AppShell) nhưng thay toàn bộ data layer mock bằng BE contract; xóa `executionEngine/seedData` khỏi production bundle (chuyển thành storybook/demo riêng).
- **Thay/xóa**: fixture `/api/*` nội bộ khi chạy production (giữ cho test nhưng gắn nhãn + guard env).
- **Điều kiện cần trước Slice 05**: 1 shell duy nhất; 0 trang MOCK ONLY trong production routes (mock chỉ trong `/prototype` hoặc behind flag); 0 loading vô hạn; repo UTF-8; contract test FE↔BE (ít nhất recent/run-message/stop/status/platforms) chạy trong CI.

---

## Trả lời trực tiếp

- **User hiện làm được gì?** Giao việc TikTok (search/actor/video-check) qua `/tasks-live`, xem tiến trình/task/receipt, xem runtime + bridge tabs, stop task. Tất cả trên UI cũ.
- **Cái gì chạy end-to-end?** `run-message` → BE router → task persist → poll hiển thị → stop. Read path runtime/recent/events.
- **Trang nào hỏng?** `/library`, `/editor` (kẹt loading vô hạn); `/settings` cũ bị đè; nav chéo 2 nửa app.
- **Chức năng nào chỉ mock?** Toàn bộ 14+ trang AppShell mới (workspace chat, tasks, browser, research, media, publishing, knowledge, activity, integrations, settings, projects, schedules, workflows, overview).
- **Capability BE nào chưa có UI?** platforms/connections/research/studio/publications/renders/approve (nút).
- **Frontend có đủ điều kiện phát triển tiếp?** Chưa — cần hợp nhất 1 shell + nối BE trước Slice 05 (xem §16–17).

### Bảng tổng thể

| Trang | Tổng chức năng | PASS | FAIL | Partial | Mock | Chưa test |
|---|---|---|---|---|---|---|
| workspace (`/`) | ~6 | 0 | 0 | 0 | 6 | 0 |
| overview | ~4 | 0 | 0 | 0 | 4 | 0 |
| tasks (+[taskId]) | ~10 | 0 | 0 | 0 | 10 | 1 (detail) |
| projects (+[id]) | ~5 | 0 | 0 | 0 | 5 | 1 |
| schedules (+[id]) | ~5 | 0 | 0 | 0 | 5 | 1 |
| workflows (+[id]) | ~5 | 0 | 0 | 0 | 5 | 1 |
| browser (+[profileId]) | ~6 | 0 | 0 | 0 | 6 | 1 |
| research (+[id]) | ~5 | 0 | 0 | 0 | 5 | 1 |
| media (+[assetId]) | ~5 | 0 | 0 | 0 | 5 | 1 |
| publishing (+[id]) | ~5 | 0 | 0 | 0 | 5 | 1 |
| knowledge | ~4 | 0 | 0 | 0 | 4 | 0 |
| activity | ~3 | 0 | 0 | 0 | 3 | 0 |
| integrations | ~4 | 0 | 0 | 0 | 4 | 0 |
| settings (+platforms) | ~6 | 0 | 0 | 0 | 6 | 0 |
| tasks-live (+[id]) | ~8 | 2 (TL-01/02) | 0 | 1 (TL-05) | 0 | 5 | 38% — SMOKE→FUNCTIONAL đang làm (§20) |
| runtime | ~3 | 3 | 0 | 0 | 0 | 0 |
| library | ~2 | 0 | 2 | 0 | 0 | 0 |
| publish | ~4 | 0 | 0 | 3 | 1 | 0 |
| editor | ~3 | 0 | 2 | 0 | 0 | 1 |
| prototype | — | — | — | — | — | NOT TESTED |

> Các trang còn lại: SMOKE TEST ONLY (đợt 1), chưa tính functional coverage. Trang tasks-live đang functional QA (§20).

# BỔ SUNG ĐỢT 2 (2026-11-26, theo CORRECTION + bối cảnh Prototype→Production)

> AppShell Midnight Lime + 14 trang mới là prototype UI/UX user dựng bằng Lovable/Google AI Studio, được port vào repo (KHÔNG phải frontend song song ngoài ý muốn). Đánh giá dùng đúng khung: Prototype → Production CHƯA hoàn thành (xong port, chưa xong tích hợp). Giữ nguyên thiết kế prototype, không đề xuất giao diện thứ ba.

## 18. Git history quá trình port prototype (đã tra cứu)

| Commit | Ngày | Nội dung (message gốc) | Phạm vi thay đổi |
|---|---|---|---|
| `73de3f4` | 26/11 22:03 | "UI port: ghep UI prototype vao Next.js (14 trang + AppShell + tokens midnight-lime) + BE contract, build 36/36 pass" | 73 files, +15055/-22: 14 page routes, AppShell/GlobalSidebar/Header/CommandPalette/ApprovalCenter/TaskMonitor/AiAssistant/LiveWorkspacePanel/LiveTaskCard, `domain/types+taskMachine`, `stores/useMiroStore`, `proto-services/mock/{seedData,executionEngine}` (~2300 dòng mock), `proto-services/backend/miroBackend.ts` (117 dòng BE contract), deps mới (zustand, tailwind v4, lucide, sonner, xyflow, date-fns) |
| `0ac559a` | 26/11 22:31 | "Fix hydration: suppressHydrationWarning body + zustand skipHydration + MiroShell gate sau mount" | `layout.tsx`, `miro-shell.tsx`, `useMiroStore.ts` |
| `a94c1e2` | 26/11 | "Fix hydration dot 2: suppressHydrationWarning MiroNav + tasks-live + AppShell root (chong attribute bis_* cua extension)" | hydration (chưa diff chi tiết) |

- Agent được giao (suy từ diff): port UI prototype vào Next.js + tạo BE contract + build pass. ĐÃ LÀM: 14 trang + design system + store/mock + adapter `miroBackend.ts` + build 36/36. CHƯA LÀM: cắm trang mới vào adapter (chỉ `AiWorkspacePage:124` gọi `submitInstructionToBackend` fire-and-forget; còn lại 100% `launchTaskFromInstruction`/`useMiroStore`).
- Branch `ui/port-prototype` (v1) không còn local/remote (chỉ còn `ui/port-prototype-v2`).

## 19. Mapping Prototype → BE capability (Component | Mock hiện tại | BE capability | Service cũ tái dùng | Mức tích hợp)

| Menu Prototype | Component mới | Mock hiện tại (file:dòng) | BE capability tương ứng | Service/hook cũ tái dùng được | Mức tích hợp |
|---|---|---|---|---|---|
| AI Workspace | `features/ai-workspace/AiWorkspacePage.tsx` | `launchTaskFromInstruction` (:133,144) + store conversations/messages seed; `submitInstructionToBackend` (:124) fire-and-forget, không dùng task_id để theo dõi | `POST /tasks/run-message`, `GET /tasks/{id}+/events` | `RuntimeService.runMessage/get/events`, `useBeTasks/useRunMessage` | **PARTIAL** — gửi tới BE nhưng bỏ rơi KQ, fallback mock |
| Tổng quan | `features/overview/OverviewPage.tsx` | store/seed | `GET /tasks/runtime/status`, `GET /tasks/recent` (BE CÓ) | `RuntimeService.status/recent`, `useRuntimeStatus` | **NOT STARTED** |
| Tác vụ | `features/tasks/TasksPage.tsx` | `launchTaskFromInstruction` (:150), pause/resume/cancel/retry local (:56-60), filter/sort local | `GET /tasks/recent`, `POST /tasks/{id}/stop`, `GET /tasks/{id}/events` (BE CÓ) | `RuntimeService.recent/stop/get/events`, `useBeTasks/useBeStop` | **NOT STARTED** (adapter `MiroBackendTasks.listTasks/cancelTask` viết sẵn nhưng trang KHÔNG import) |
| Dự án | `features/projects/ProjectsPage.tsx` | store projects/researchProjects/mediaAssets | `GET /projects/{id}`, `/studio/project/{video_id}`, `/studio/media/{video_id}` (BE CÓ một phần) | `EditorService.get`, `StudioService.*` | **NOT STARTED** |
| Lịch trình | `features/schedules/SchedulesPage.tsx` | `launchTaskFromInstruction` (:123) + store schedules/ownerships | `GET/POST /schedule/day-plan|ensure|status` (BE CÓ) | Chưa có service cũ — viết mới khi tích hợp | **NOT STARTED** + BE sẵn |
| Workflows | `features/workflows/WorkflowsPage.tsx` | store workflows + `updateWorkflowGraph` local (xyflow) | BE KHÔNG có workflow engine endpoint | Không có | **NO-BE** — giữ mock, KHÔNG tự xây |
| Trình duyệt | `features/browser/BrowserPage.tsx` | store `browserProfiles` seed `profile-20` | Bridge tabs (`GET /tasks/runtime/status` → `bridge.tabs`), Profile binding `/connections/*` (BE CÓ) | `MiroBackendResources.listProfiles` (map tabs thật, đã viết) + `RuntimeService.status` | **NOT STARTED** (adapter DONE, trang chưa dùng) |
| Nghiên cứu | `features/research/ResearchPage.tsx` | store seed records | `POST /research/search|read|video|channel|compare|to-project` (BE CÓ — verify search "KANS" trả 0 KQ trung thực `metadata_only`) | Chưa có service cũ — viết `ResearchService` mới | **NOT STARTED** + BE sẵn |
| Media Studio | `features/media/MediaStudioPage.tsx` | store seed assets | `/studio/*` 30+ endpoints (BE CÓ) | `StudioService.*` đầy đủ | **NOT STARTED** (service cũ sẵn, chỉ cần cắm) |
| Xuất bản | `features/publishing/PublishingPage.tsx` | `launchTaskFromInstruction` (:98) + store publications/approvals local | `POST /threads/publish` dry-run, `POST /publications`, `GET /publications/{id}`, `/threads/prepare|approve|reconcile` (BE CÓ) | `PublishService.submit` (cũ, fixture) → chuyển sang threads API | **NOT STARTED** |
| Tri thức | `features/knowledge/KnowledgePage.tsx` | store `knowledgeDocs` CRUD local | BE KHÔNG có knowledge endpoint | Không có | **NO-BE** — giữ local, KHÔNG tự xây |
| Hoạt động | `features/activity/ActivityPage.tsx` | store `activities` từ engine giả | `GET /tasks/{id}/events`, `GET /tasks/recent` gộp feed (BE CÓ) | `RuntimeService.events/recent` | **NOT STARTED** |
| Tích hợp | `features/integrations/IntegrationsPage.tsx` | store seed | `GET /connections/accounts`, `GET /platforms`, verify/revoke/pause (BE CÓ) | `SettingsService.connections/platforms` (production) | **NOT STARTED** (service sẵn) |
| Cài đặt | `features/settings/SettingsPage.tsx` | store settings + `resetDemoData` local | `GET/POST /platforms` upsert/clone/rollback, `GET /connections/*` (BE CÓ) | `SettingsService.*` đầy đủ | **NOT STARTED** (service sẵn) |

Tổng: 1 PARTIAL + 11 NOT STARTED (6 có service/adapter cũ sẵn: Tác vụ, Trình duyệt, Media, Tích hợp, Cài đặt + AI Workspace; 5 cần service mới nhưng BE đã có: Tổng quan, Dự án, Lịch trình, Nghiên cứu, Xuất bản, Hoạt động) + 2 NO-BE (Workflows, Tri thức).

## 20. Functional QA log đợt 2 (PAGE → COMPONENT → INTERACTION → EXPECTED → ACTUAL → VERIFICATION)

QA tab: Playwright profile20, origin `http://127.0.0.1:3100`. BE/Bridge/FE 200 (sau 1 restart launcher do FE 500 — xem ENV-01).

| Test ID | Page.Component | Precondition | Steps | Expected | Actual | Status | Evidence |
|---|---|---|---|---|---|---|---|
| ENV-01 | FE toàn site | FE 500 mọi route | Đọc `logs/fe.log` → root cause → `stop` + `start` | FE 200 | React manifest hỏng do `.next` bị xóa lúc server chạy → restart rebuild → 200 cả 3 | RESOLVED (môi trường) | `fe.log`: `Could not find module segment-explorer-node`, `ENOENT pages-manifest.json` |
| TL-01 | tasks-live.live-send disabled | input rỗng | Quan sát nút "Giao viec" | disabled khi rỗng | `[disabled]` đúng | **PASS** | snapshot `button "Giao viec" [disabled]` |
| TL-02 | tasks-live.live-analyze-url disabled | URL rỗng | Quan sát nút "Phân tích video" | disabled khi rỗng | `[disabled]` đúng | **PASS** | snapshot `button "Phân tích video" [disabled]` |
| TL-05 | tasks-live.sample-search | BE+Bridge live | Click "Tìm kiếm mẫu" (DOM `.click()` — Playwright click timeout, xem PERF-01) | Task tạo + BE search TikTok + KQ về | Task `task-9e67b82400cf` tạo; events: created→observe→decide→act_started→**act_failed OBSERVATION_TIMEOUT**→blocked. QA tab bị navigate sang `tiktok.com/search?q=KANS 377` render KQ thật; về lại Miro UI nguyên vẹn | **PARTIAL** | events seq 1-6; body TikTok có KQ KANS 377 thật |
| BUG-11 (P1) | tasks-live + Bridge ownership | TL-05 | Sau click, QA tab bị điều hướng sang TikTok | Miro giữ UI; execution dùng tab riêng | **QA tab bị cướp làm execution tab**: bridge tabs sau đó chỉ còn 1 tab `tasks-live` | **FAIL** | Title "Loading https://www.tiktok.com/..."; `bridge.tabs` count 1 |
| BUG-12 (P2) | BE search observe | TL-05 events | act_started → observe | act thành công khi trang đã load KQ | `OBSERVATION_TIMEOUT` sau 30s dù trang đích render xong ở QA tab — BE observe lease `1302904467` nhưng QA tab navigate độc lập ngoài lease | **FAIL** (integration) | event seq 5 `browser_act_failed OBSERVATION_TIMEOUT` |
| PERF-01 (P3) | tasks-live buttons stability | — | Playwright `browser_click` nút sample | click được | Timeout "waiting for element to be stable" mọi lần; phải dùng DOM `.click()` qua evaluate | Ghi nhận (tooling) | locator resolve OK nhưng never stable — nghi re-render poll 5s |

| TL-03 | tasks-live.invalid-message | BE+Bridge live | Gõ "qa probe xyz 123" → nút Giao việc enable → click (PERF-01: Playwright click timeout, dùng DOM click) | Task tạo + fail-closed NO_ROUTE_MATCH | Task `task-49fb6a81afe1` tạo, `needs_attention NO_ROUTE_MATCH`, render đầu list sau poll | **PASS** (functional + integration BE) | snapshot list item mới |
| TL-04 | tasks-live.sample-actor-check | BE+Bridge live | Click "Kiểm tra tài khoản" (DOM click) | Task tạo + actor-check | Task `task-8c70bb1eb471` tạo, `needs_attention TAB_UNKNOWN` | **PASS** (fail-closed trung thực; actor-check không có managed tab sau restart) | snapshot list item mới |
| TL-06 | tasks-live.poll-list | BE live | Quan sát list sau TL-03/04 | Task mới render không refresh | Cả 2 task mới ở đầu list sau poll 5s | **PASS** | snapshot 20 items |
| TD-01 | tasks-live/[id].detail | task TL-04 tồn tại | Mở `/tasks-live/task-8c70bb1eb471` | status/events/evidence trung thực | "needs_attention · TAB_UNKNOWN", events #1 created #2 blocked, "Chưa có evidence." | **PASS** | snapshot detail |
| TD-02 | tasks-live/[id].stop | task TL-04 blocked | Click "Dừng task" (DOM click) | stop_requested + confirm | "Trạng thái: stop_requested", "Đã gửi dừng task-8c70bb1eb471." | **PASS** (BE stop contract end-to-end) | snapshot sau click |

## 21. Re-baseline môi trường sau restart (2026-11-27 ~09:33+07) + re-verify tasks-live + bắt đầu Workspace

- Env mới: `windows/miro.py status` → be pid=7680 alive http-200, fe pid=18436 alive http-200, bridge pid=31384 alive http-200. HEAD `a94c1e2`, branch `ui/port-prototype-v2`.
- Rewrite `/api → BE` còn hoạt động: `GET /api/tasks/recent` trả dữ liệu BE thật (task đầu `task-8c70bb1eb471 stop_requested TAB_UNKNOWN` — đúng task TD-01/TD-02 đợt trước).
- Bridge tabs sau restart: **0 tabs** (trước restart có 1 tab TikTok do BUG-11). Tasks BE: 50 (trước: 48 — QA tạo thêm).
- Không có ENV case mới (FE 200 ngay, không lặp lại ENV-01). Ghi nhận: `git status` có 1 file sửa `apps/backend/src/miro/tasks/router.py` (thêm `GET /tasks` compat alias của `/tasks/recent`) — ngoài phạm vi QA, không đánh giá, báo parent biết.
- Luật REA-mắt: `miro/browser/gateway.py` + `miro/eye/` **không tồn tại trong repo** (AGENTS.md trích dẫn sai đường dẫn) — QA read-only này dùng trực tiếp Playwright MCP profile20.

### Re-verify Page Completion Gate `/tasks-live` (RE-xxx, môi trường mới)

| Test ID | Page.Component | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|
| RE-TL-01/02 | tasks-live buttons disabled | snapshot sau restart | 2 nút disabled khi input rỗng | `[disabled]` cả 2 đúng | **PASS** |
| RE-TL-03 | tasks-live.invalid-message | gõ "qa probe reverify 456" → DOM click "Giao viec" | task tạo + NO_ROUTE_MATCH | `task-1a9a6973da85 needs_attention NO_ROUTE_MATCH` đầu list | **PASS** |
| RE-TL-05/BUG-11 | tasks-live.sample-search | DOM click "Tìm kiếm mẫu" | QA tab giữ Miro UI | **BUG-11 TÁI HIỆN**: QA tab navigate → `tiktok.com/search?q=KANS 377`; bridge tabs 0→1 (tab TikTok duy nhất); BE fail-fast `SEARCH_NO_RECORDS` (task-`a60d25eefda2`) vì TikTok render trang lỗi "Something went wrong"; về lại `/tasks-live` UI nguyên vẹn | **FAIL — BUG-11 CONFIRMED sau restart** |
| RE-console | tasks-live console | đọc console log file mới nhất | — | 2 errors = hydration mismatch React (đã biết BUG-08); log TikTok là của tab bị cướp, không phải FE | Ghi nhận (không bug mới) |
| RE-QA-tab | phục hồi | navigate lại `/tasks-live` sau BUG-11 | UI nguyên vẹn | PASS — list đầy đủ, task mới nhất đúng | **PASS** |

Kết luận re-verify: `/tasks-live` **Completion Gate CHƯA ĐẠT** — BUG-11 (P1, bridge cướp QA tab) vẫn tái hiện sau restart, thêm biến thể mới: TikTok chặn/báo lỗi → BE `SEARCH_NO_RECORDS` thay vì `OBSERVATION_TIMEOUT` như TL-05 gốc. Đây là flakiness phía TikTok, nhưng hành vi **cướp QA tab** là lỗi ownership phía Bridge/BE ổn định qua restart.

### Bắt đầu Workspace (`/workspace`, WS-01)

| Test ID | Page.Component | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|
| WS-01 | workspace.chat-send | fill "qa workspace probe2" → DOM click "Gửi lệnh" (Playwright click cũng timeout như PERF-01 → mở rộng PERF-01 ra toàn site) | Gửi tới BE, hiển thị KQ thật | Network có `POST /api/tasks/run-message` + BE tạo task thật `task-b2521eeae8c3 NO_ROUTE_MATCH` (02:36:42) — **nhưng UI trả lời bằng flow MOCK** ("Miro đã bắt đầu tác vụ ... (mô phỏng)", LiveTaskCard seed "Nghiên cứu 10 video KANS 377 Hoàn tất"), không dùng task_id BE | **FAIL (integration)** — PARTIAL mapping §19 vẫn đúng: fire-and-forget, bỏ rơi KQ BE |
| WS-02 | workspace source encoding | đọc `AiWorkspacePage.tsx` | UTF-8 | **mojibake nặng trong source**: `SUGGESTED_SCENARIOS` + toast + assistant message (`K��<ch b���n`, `T���o l��<ch`) — xác nhận BUG-07 ăn sâu tới source prototype | **FAIL** — mở rộng BUG-07 |

Page Completion Gate `/workspace`: **CHƯA ĐẠT** (MOCK ONLY + mojibake source). Trang tiếp theo: `/overview`, rồi `/tasks`.

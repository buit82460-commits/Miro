# Miro Coverage — bao phủ hành vi legacy (dubtool + JARVIS-Assistant)

Ngày: 2026-11-21 (Asia/Bangkok). Phạm vi: chỉ đọc + ghi docs, không sửa code nguồn.
Nguồn đã đọc: `C:\dubtool` (app.py, core/, scripts/, web/, shared/, integrations/, tests/, history/, reports/, schedules/), `D:\JARVIS-Assistant` (backend/app, backend/config, backend/runtime, docs/, tasks/, spikes/), `D:\Project-Audit` (Dubtool/, JARVIS/ — đối chiếu, không copy secret).

Quy ước đích Miro:
- **giữ**: mang nguyên logic/data-contract sang Miro, chỉ đổi đường dẫn/import.
- **bọc**: giữ code cũ chạy trong adapter/process riêng, Miro gọi qua biên đã định nghĩa (CLI/HTTP/queue), không refactor sâu.
- **viết lại**: đặc tả lại hành vi trong Miro, dùng legacy làm oracle kiểm thử.
- **bỏ**: không mang sang (obsolete, one-off batch, spike đã xong).

Bằng chứng = đường dẫn file/hàm + test/receipt đã quan sát (read-only, không chạy lại runtime live).

## 1. app.py — 8 tab Gradio + FastAPI mount

| # | Hành vi (tab) | Nguồn (repo/file/hàm/entry) | Cách dùng | Bằng chứng (code/test/receipt) | Đích Miro |
|---|---|---|---|---|---|
| T1 | Nhập: tải URL/file, chọn Studio source, chạy đến dịch | `C:\dubtool\app.py::do_download`, `do_run_to_translate`, `studio_sources`, `use_studio_source`; `core/pipeline.py::run(steps=[download,audio,stt,translate])`, `core/youtube_studio.py::sources/source` | User nhập URL hoặc file → pipeline download→translate; hoặc nạp video từ YouTube Studio (`GET /api/dubtool/sources`) | code: app.py:359-383; test lịch sử: `scripts/verify_dubtool_standalone_live.py`, `verify_video_pipeline_artifacts.py` | **viết lại** — form nhập + job pipeline trong Miro; bọc `Pipeline.run` qua worker lúc đầu |
| T2 | Phụ đề: nạp/sửa/lưu segments, chạy TTS+trộn+render | `app.py::load_segments/save_segments/do_tts_mix_render`; `core/pipeline.py::_step_tts/_step_sync/_step_mix/_step_render`, `core/cache.py::done_path/mark_done` | Sửa `tgt_text` → xóa marker downstream (tts/sync/mix/render) → chạy lại | code: app.py:384-400; `cache/*/segments.json`, `dub.srt`, `timeline.json` | **viết lại** — editor phụ đề Miro; giữ contract `segments.json` + `done_path` làm checkpoint |
| T3 | Giọng: lọc giọng, nghe thử, revoice 1 câu | `app.py::filter_voices/revoice/on_voice_selected`; `core/voices.py::list_voices/get_voice/make_preview`, `pipeline.revoice_segment` | Chọn lang/gender → preview wav → revoice 1 seg → render lại downstream | code: app.py:401-415; assets: `voices/`, `temp/preview_*.wav` | **viết lại** — voice picker Miro; **bọc** engine TTS (`core/tts/`) |
| T4 | Hình: preview overlay + thêm overlay | `app.py::preview_frame/add_overlay`; `core/overlay.py::build_filter`, `core/render.py::render` | Nhập x/y/w/h (0-1), loại blur/box/text/logo, t_start/t_end → preview 5s → lưu vào `project.overlays` | code: app.py:416-439; `core/overlay.py` | **viết lại** — overlay editor; giữ `build_filter` qua bọc |
| T5 | Xuất: render cuối + hardsub + mở output | `app.py::do_final_render/open_output_dir`; `pipeline._step_render`, `core/ffmpeg_utils.py` | Chọn burn-subtitles → render mp4 vào `output/<vid>_dubbed_<ts>.mp4` | code: app.py:440-450; receipts: `output/`, `cache/*/render.done` | **viết lại** — export job Miro; bọc ffmpeg/render |
| T6 | AI Editor: plan/cắt/zoom/text/SFX/preview 20s/render cuối/restore | `app.py::editor_*`; `core/editor.py` (plan/snapshot/preview/export), `core/edit_timeline.py`, `core/editor_media.py` | Nạp project → yêu cầu TV → plan JSON → preview → render cuối → restore bản trước edit | code: app.py:451-485, `core/editor.py:1-40`; test: `verify_editor*.cjs` (5 file) | **viết lại** — timeline edit Miro; bọc `render_edit/compose_audio` giai đoạn 1 |
| T7 | Đưa sang YouTube: hàng chờ duyệt (không upload trực tiếp) | `app.py::submit_studio`; `core/youtube_studio.py::submit → POST /api/dubtool/import`, `core/studio_service.py::handoff` | Render cuối → nhập title/desc/tags → submit vào Pipeline của Studio để duyệt | code: app.py:488-495, `core/youtube_studio.py:49-53` | **giữ** contract `submit(video_id,title,description,tags)` → Miro review queue; **bỏ** đường upload lậu (không tồn tại) |
| T8 | Timeline nhiều clip + Reference tab | `app.py::open_multitrack → studio_service.create_from_dubtool`; `core/studio_service.py`, `core/studio_ui.py`, `core/studio_store.py`, `core/reference_ui.py`, `core/reference_routes.py` | Chuyển bản lồng tiếng thành project timeline; tab Reference tra cứu blueprint/recipe/style | code: app.py:496-501; test: `verify_timeline*.cjs`, `verify_studio.cjs`, `verify_reference_*.cjs` | **viết lại** — multitrack timeline là lõi Miro; **giữ** schema project/store (`studio_store`) |
| T0 | Khung app: FastAPI + Gradio mount + theme | `app.py::create_app/build_ui`; `web/` (Next.js) + `core/studio_ui.py` | `uvicorn create_app()` — FastAPI + `gr.mount_gradio_app`, CORS localhost:3000, theme CSS | code: app.py:505-563; `web/src` | **viết lại** — Miro thay Gradio bằng UI mới; giữ route `/api/dubtool/*` tương thích lúc chuyển đổi |

## 2. Task — JARVIS jobs + dubtool pipeline tasks

| Hành vi | Nguồn | Cách dùng | Bằng chứng | Đích Miro |
|---|---|---|---|---|
| Job slot đơn, queue, pause/resume/stop, recovery | `D:\JARVIS-Assistant\backend\app\jobs\manager.py::JobManager` (single active slot, `_waiting`, `recover_pending`, snapshot `runtime/execution/jobs/job_*.json`) | `create_job(job_type, task/query/url/...)` → runner chạy → event journal + snapshot; restart chỉ resume `web_*`/safe, còn lại BLOCKED không replay | code: manager.py:92-178, 298-802, 816-925; `app/jobs/journal.py`, `runner.py`, `models.py` | **viết lại** — task orchestrator Miro học guard `OWNERSHIP_UNKNOWN / RESULT_UNKNOWN / no-replay`; giữ event schema `job_queued/step_progress/agent_done` |
| Policy/limits theo job_type (13 loại) | `manager.py::create_job` + `app/policies/browser.py` (browser_task, web_search/read, stock_*, github_*, synthesize, page_extract, video_extract, channel_report, desktop_task, dubtool, tiktok_discover) | Route validate input → resolve limits → chọn agent factory | code: manager.py:298-698; `backend/config/policy.json` | **giữ** bảng policy/limits; **viết lại** enforcement trong Miro |
| Dubtool pipeline 8 bước + cache/invalidation | `C:\dubtool\core\pipeline.py::Pipeline.run/_step_*` (download→audio→stt→translate→tts→sync→mix→render), `_mark_step` xóa downstream, `revoice_segment` | Chạy subset steps; hydrate từ cache; LLM dịch (batch 20, phoneme budget) fallback NLLB local | code: pipeline.py:28-482; config: `config.yaml`; models: `models/`, `voices/` | **bọc** Pipeline làm worker Miro giai đoạn 1; **viết lại** dần từng step; giữ `project.json` + `*.done` contract |
| Schedule/posting plan ngày | `C:\dubtool\core\posting_schedule.py` (policy/plans/slots/storage, UNKNOWN→reconcile, auto-pause) + `schedules/<platform>/<account>/plans/<date>.json` | build_day_plan (carryover ưu tiên, cap) → due_slots → record_submit_unknown | code: posting_schedule.py:1-128; data: `schedules/` | **giữ** nguyên thuật toán slot/reconcile; viết lại UI lập lịch |
| Receipt/attempt journal chống đăng trùng | `shared/execution_policy.py::atomic_save`, `shared/json_io.py`, `reports/social-attempts/*.json`, `publication-*.json` | Mọi adapter check publication + attempt trước Post; UNKNOWN không replay | code: `shared/`; data: `reports/social-attempts/`, `reports/resource-batches/*/publication-*.json` | **giữ** — đây là invariant an toàn quan trọng nhất của Miro |

## 3. Browser — registry/runtime/tab/profile 20

| Hành vi | Nguồn | Cách dùng | Bằng chứng | Đích Miro |
|---|---|---|---|---|
| Registry: register/platform_for/annotate/tab_creation/snapshot | `C:\dubtool\core\browser_registry.py::BrowserRegistry` + `shared/browser_contracts.py`, `config/platform-domains.json`, `config/browser-registry.sqlite` | `register(url)` phân loại platform/site; `annotate` gán flag/description; snapshot `platform/profile/tab/task/account` | code: browser_registry.py:129-212; test: `verify_shared_browser_live.py`, `scripts/record_browser_registry_final_state.py` | **giữ** contract + sqlite schema; bọc thành browser service Miro |
| Runtime: bind/discover/read/navigate/create/acquire/task/verify_account | `C:\dubtool\core\browser_runtime.py::BrowserRuntime` (~950 dòng: lease 60s + heartbeat, coordinator lock, flag-watch protection, stale-instance reconcile) | `bind_profile` (chrome://version evidence) → `discover` → `acquire_tab` (reuse-or-create, lease TTL) → `read/navigate/task` → `verify_account` | code: browser_runtime.py:39-952; `scripts/browser_manager_command.py`, `social_live_chrome.py::chrome_endpoint/actor_id/verify_actor` | **bọc** nguyên runtime (rủi ro cao khi viết lại); Miro chỉ gọi `acquire_managed_tab` |
| Managed tab helper (1 tab/1 lease/1 owner) | `C:\dubtool\core\tab_acquisition.py::acquire_managed_tab/managed_tab` (Profile 20, `DUBTOOL_BROWSER_REGISTRY`, channel_id, creation_reason) | Adapter gọi `managed_tab(browser, platform_id, destination_url, flag="PUBLISH", ...)` → dùng xong release | code: tab_acquisition.py:110-192; dùng bởi cả 8 adapter | **giữ** — entry chuẩn duy nhất Miro được dùng để chạm browser |
| Live Chrome attach (không export cookie) | `C:\dubtool\scripts\social_live_chrome.py`, `social_chrome_daemon.py`, `launch-chrome-profile20-debug.bat` | Đọc `DevToolsActivePort` → `ws://127.0.0.1:port/route`; verify actor read-only từ UI | code: social_live_chrome.py:1-60 | **giữ** nguyên tắc consent/no-cookie-export |
| Browser manager verify host | `C:\dubtool\scripts\browser_manager_command.py`, `verify_browser_manager_recovery.py`, `record_browser_registry_final_state.py` | Gửi command JSON → chờ receipt `reports/browser-registry/manager-current.json`, timeout 90s, không replay mutation | code: browser_manager_command.py:1-32 | **bọc**; Miro reuse khi cần điều tra |
| JARVIS browser agent (Browser Use) | `D:\JARVIS-Assistant\backend\app\agents\browser.py::BrowserUseAgent` (pin commit b49a68e, telemetry off, per-job profile, step callbacks, auto-retry error-page, pause/stop wiring) + `agents/browser_access.py` | Job `browser_task` → tạo `BrowserProfile(user_data_dir=profiles/job-*)` → `Agent.run(max_steps)` → cleanup verify PID | code: browser.py:1-550; `research/repos/browser-use/` (pin); policy: `backend/config/policy.json` | **bọc** giai đoạn 1; **viết lại** khi Miro có browser agent riêng; giữ `profile/job-*` isolation + telemetry-off |

## 4. Tám adapter platform (1 adapter/platform, fail-closed)

| Adapter | Nguồn | Cách dùng | Bằng chứng | Đích Miro |
|---|---|---|---|---|
| TikTok post | `C:\dubtool\scripts\tiktok_post_one.py::run_shortcode` (+ `post_one.py` shim tương thích cũ) + `publish_maoziqi59_tiktok.py` | `tiktok_post_one.py <shortcode> [batch_dir]`; guard publication+attempt; upload TikTok Studio; reconcile receipt | code header: tiktok_post_one.py:1-13; manifest: `reports/resource-batches/maoziqi59-tiktok-20261118/download.json`; test: `verify_adapter_integrity.py` + `adapter_baseline.json` | **bọc** — canonical duy nhất; cấm script `post_<batch>.py` mới |
| Facebook Reels post | `scripts/facebook_post_one.py` + `social_facebook_reels.py::publish_reel/caption_for` + `facebook_receipt.py` | `facebook_post_one.py <shortcode> [batch_dir] [account]`; candidate-diff + receipt verifier | code: facebook_post_one.py:1-15; receipts: `publication-facebook.json` | **bọc** |
| YouTube Data API (upload/visibility/update/schedule/delete/reconcile) | `scripts/youtube_post_one.py` (argparse 6 lệnh), `integrations/youtube-agent/` (2 kênh: Bảnh Love You mặc định + Love Cr7 dự phòng), `youtube-accounts.json` | `youtube_post_one.py upload <shortcode> ... [--visibility] [--schedule]`; channel-match trước mọi mutation; quota-aware | code: youtube_post_one.py:1-21; `integrations/youtube-agent/config/youtube-accounts.json` | **bọc**; giữ quy tắc 2-kênh + mặc định Bảnh Love You |
| Instagram post + download | `scripts/instagram_post_one.py` (post), `scripts/instagram_download_one.py` (yt-dlp per-reel URL, sha256 + manifest) | Rule: 1 tab platform URL → snapshot `a[href*="/reel/"]` → 1 adapter call/reel; cấm đưa URL profile cho yt-dlp | code: instagram_post_one.py:1-28, instagram_download_one.py:1-12; `reports/resource-batches/<batch>/download.json` | **bọc** cả hai; giữ rule per-reel |
| Threads post + download | `scripts/threads_post_one.py` (post text + 1 media, download, reconcile profile-readback; delete/draft/audience/edit UNSUPPORTED) | `threads_post_one.py <shortcode> / --batch / download` | code header: threads_post_one.py:1-26 | **bọc**; UNSUPPORTED giữ nguyên (manual trong app) |
| Shopee item/profile/orders | `scripts/shopee_post_one.py` (publish/update, profile, orders read-only; delete/draft UNSUPPORTED; hướng affiliate shopee.vn, cấm test live Seller Centre) | `shopee_post_one.py <shortcode> / profile / orders` | code header: shopee_post_one.py:1-26 | **bọc**; giữ lệnh cấm live-test |
| ChatGPT collab | `scripts/chatgpt_post_one.py` (chat/batch/read/new/rename/delete/model/profile) | `chatgpt_post_one.py <shortcode> / read / new / rename / delete / model / profile` | code header: chatgpt_post_one.py:1-30 | **bọc** |
| Flow text-to-video | `scripts/flow_post_one.py` (generate+download MP4, reconcile read-only, profile verify; delete UNSUPPORTED) | `flow_post_one.py <shortcode> / --batch / reconcile / download / profile` | code header: flow_post_one.py:1-30 | **bọc** |
| Khung chung adapter | `_enforce_adapter_integrity()` (fail-closed khi baseline drift), `verify_adapter_integrity.py`, `scripts/adapter_baseline.json`, guard `publication-*.json` + `reports/social-attempts/` | Mọi adapter verify baseline lúc khởi động; 1 journaled submit, không retry UNKNOWN | code: tiktok/facebook/youtube_post_one.py:40-52 | **giữ** toàn bộ khung guard |

## 5. Watcher — giám sát worker/job/render/browser

| Hành vi | Nguồn | Cách dùng | Bằng chứng | Đích Miro |
|---|---|---|---|---|
| Render worker supervision (studio) | `C:\dubtool\core\studio_service.py::_recover_jobs/_run_render/control_job` (single-thread pool, checkpoint signature, ownership UNKNOWN→blocked, retry budget, pause/resume/stop) + `shared/execution_policy.py` | `start_render/start_batch` → job `render-<hex>` → progress callback → `control_job(pause/resume/stop)`; restart recover queued/running | code: studio_service.py:48-82, 289-350, 362-396; `cache/studio/render-jobs.json` | **giữ** state machine; viết lại UI hàng đợi |
| JobRunner lifecycle + cleanup verify | `D:\JARVIS-Assistant\backend\app\jobs\runner.py` + `agents/base.py` (cleanup report, `mark_slot_contaminated` khi browser chưa đóng) | Runner start/stop-grace → agent cleanup → verify PID đóng → khóa slot nếu unclean | code: manager.py:231-244; `agents/browser.py::cleanup:501-549` | **viết lại** trong Miro orchestrator; giữ nguyên tắc unclean-slot-lock |
| Desktop gate/dispatch (epoch + window lock) | `C:\dubtool\shared\desktop_gate.py`, `desktop_dispatch.py`, `scripts/desktop_act.py::gate/dispatch_window` | Mỗi job có epoch; stale epoch → DENIED; 1 owner/window tại 1 thời điểm | code: desktop_act.py:294-310; `shared/desktop_*.py` | **giữ** |
| Verify/watch scripts | `C:\dubtool\scripts\verify_worker_supervision_runtime.py`, `verify_live_chrome.cjs`, `verify_shared_browser_live.py`, `verify_adapter_integrity.py`, `browser_registry_live_probe.py` | Chạy kiểm chứng sau đổi code; live probe chỉ khi được phép | files: scripts/verify_*.py/cjs | **giữ** làm bộ kiểm hồi quy Miro; **bỏ** các harness one-off (`browser_phase0_*`, `autonomous_*` đã xong thì lưu trữ) |

## 6. Desktop — điều khiển desktop có kiểm soát

| Hành vi | Nguồn | Cách dùng | Bằng chứng | Đích Miro |
|---|---|---|---|---|
| desktop_act tổng quát (read/write/append/find) | `C:\dubtool\scripts\desktop_act.py` (params app/window/doc/control/action, cache session + fast-path, read-back verify, receipt/attempt JSON) | `desktop_act.py app=notepad doc=docB.txt action=write text_file=...` | code: desktop_act.py:1-462; `shared/desktop_backend.py`, `desktop_dispatch.py`, `desktop_gate.py` | **bọc** — entry tổng quát duy nhất |
| desktop_write_one (Notepad pilot) | `C:\dubtool\scripts\desktop_write_one.py` (EXPERIMENTAL, Notepad-only, gate epoch) | `desktop_write_one.py "<doc>" "<text>"` | code: desktop_write_one.py:1-60 | **bọc**; không mở rộng app khác khi chưa duyệt |
| desktop recipe/env | `C:\dubtool\scripts\desktop_recipe_notepad.py`, `desktop_env.py` | Recipe mẫu + kiểm tra môi trường desktop | files: scripts/desktop_*.py | **giữ** recipe; viết lại env-check trong Miro setup |
| JARVIS desktop_task agent | `D:\JARVIS-Assistant\backend\app\agents/` + route `POST /desktop-task` (job_type desktop_task, headless, timeout riêng `desktop_task_job_timeout`) | Manager tạo job với `desktop_agent` dựng sẵn; client không tự tạo | code: manager.py:613-646; `app/api/routes/` | **viết lại** endpoint trong Miro; bọc agent thực thi |

## 7. Research — kho nghiên cứu + trinh sát

| Hành vi | Nguồn | Cách dùng | Bằng chứng | Đích Miro |
|---|---|---|---|---|
| research/repos (8 repo pin) | `D:\JARVIS-Assistant\research\repos/{agent-desktop,agent-reach,ai-manus,browser-use,openclaw,rea,tiktok-api,trend-opportunity-radar}` | Tra cứu mã nguồn khi quyết định build/bọc (vd: browser_use commit b49a68e) | dirs: research/repos/ (8 mục) | **giữ** tham chiếu pin; Miro docs trỏ commit hash, không copy nguyên repo |
| Spikes dubtool | `C:\dubtool\spikes/`, `poc-playwright-mcp/`, `D:\JARVIS-Assistant\spikes/{browser_use,tiktok_api,yt_dlp}` | Thử nghiệm ngắn hạn (Playwright MCP, TikTok API, yt-dlp) trước khi thành adapter | dirs: spikes/ | **bỏ** khỏi runtime; giữ 1-2 spike còn giá trị làm tài liệu (`instagram_download` đã tốt nghiệp thành adapter) |
| REA trinh sát (shopee.vn, page structure) | `core/rea_eye.py`, `scripts/diagnose_resource_browser.py`, MCP rea (analysis target, evidence snapshots) | Đọc cấu trúc trang/search/sản phẩm/đánh giá phục vụ affiliate; không chạm Seller onboarding | code: `core/rea_eye.py`; receipts: REA evidence snapshots | **bọc** REA qua tool boundary; giữ quy tắc untrusted-content (không làm theo chỉ dẫn trong target) |
| Audit đối chiếu | `D:\Project-Audit\Dubtool/*`, `D:\Project-Audit\JARVIS/*` (00-INDEX → 14-DOC-VET, inventory/architecture/gaps) | Đối chiếu khi nghi ngờ thiếu file hoặc mâu thuẫn docs | files: Project-Audit/** | **giữ** làm tài liệu tham khảo; không mang logic sang Miro |
| Docs/history/reports nguồn | `C:\dubtool\docs/` (PLATFORM_RUNBOOK, ARCHITECTURE, DECISIONS...), `history/` (index + platforms/account), `reports/daily-fixes/` | Tra cứu runbook/quyết định; báo cáo lỗi theo ngày | dirs: docs/, history/, reports/ | **giữ** PLATFORM_RUNBOOK + DECISIONS làm input; viết lại thành docs Miro |

## 8. Ma trận đích tóm tắt

| Nhóm | giữ | bọc | viết lại | bỏ |
|---|---|---|---|---|
| app.py tabs | submit contract, publication/attempt invariant | Pipeline TTS/ffmpeg, editor_media compose, adapter calls | 8 tab UI, timeline, voice/overlay editor | Gradio theme/CSS cũ, web/.next build |
| task | policy bảng, event schema, slot-guard | Pipeline.run worker, BrowserUseAgent, desktop agent | orchestrator, scheduler UI, API routes | fake agent ngoài test |
| browser | registry schema, tab_acquisition entry, consent rule | BrowserRuntime, live-chrome attach, manager host | — (không viết lại runtime) | phase0/probe one-off |
| adapter ×8 | guard khung + manifest/publication contract | cả 8 adapter nguyên vẹn | — | `post_<batch>.py`, batch-scoped publishers cũ |
| watcher | state machine render/job, verify scripts | supervision runtime | dashboard/watch UI | harness đã xong |
| desktop | gate/dispatch epoch-lock, recipe | desktop_act/write_one + backend | setup/env-check UI | — |
| research | repo pin refs, audit, runbook | REA boundary | docs Miro mới | spikes tốt-nghiệp/xong |

Nguyên tắc an toàn mang sang Miro (bắt buộc): 1 owner/tab-window tại 1 thời điểm; UNKNOWN sau submit chỉ reconcile, không replay; publication + attempt journal là source of truth; fail-closed khi baseline drift; secret không vào log/report; không kill Chrome toàn máy, chỉ đóng session của job.

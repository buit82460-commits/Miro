# Import Plan — legacy (dubtool + JARVIS-Assistant) → Miro

Ngày: 2026-11-21. Nguyên tắc: chỉ docs, không sửa code nguồn. Mọi bước import đều
đọc từ legacy, không replay side-effect (không Post/upload/delete lại, UNKNOWN chỉ reconcile).

## 0. Đối tượng nguồn (đã kiểm kê ở `docs/coverage.md`)

- `C:\dubtool`: app.py (8 tab), core/pipeline + studio_service + editor + browser_registry/runtime + tab_acquisition + posting_schedule, scripts/ (8 adapter MAINTAINED + social_live_chrome + desktop_act/write_one + verify_*), shared/ (execution_policy, json_io, browser_contracts, desktop_*), config/ (platform-domains, browser-registry.sqlite, studio-key), web/ (Next.js), integrations/ (youtube-agent, social-auto-upload, social-runtime).
- `D:\JARVIS-Assistant`: backend/app/jobs (manager/runner/journal/models), agents (browser/browser_access/base/fake/...), api/routes, policies, config/policy.json, runtime snapshots, research/repos (8 pin), tasks/, spikes/.
- `D:\Project-Audit`: Dubtool/ + JARVIS/ (00–14) — tài liệu đối chiếu, không import code.

## 1. Thứ tự import (4 pha, rẻ trước — rủi ro cao bọc lại)

| Pha | Nội dung | Đích coverage.md | Điều kiện vào/ra |
|---|---|---|---|
| P0 — Nền an toàn | publication/attempt journal + atomic_save/json_io + adapter_baseline + policy bảng | §2 receipt, §4 khung adapter, §5 verify | Vào: có mặt đủ file. Ra: Miro đọc/ghi được manifest mà không phá BOM/encoding; verify baseline chạy xanh |
| P1 — Bọc thực thi | Pipeline.run worker, 8 adapter nguyên vẹn, tab_acquisition, BrowserRuntime, desktop_act, studio render worker | §2 pipeline, §3 browser, §4 adapters, §5 watcher, §6 desktop | Vào: P0 xanh. Ra: Miro gọi được từng adapter qua biên CLI/queue, 1 owner/lease, UNKNOWN không replay |
| P2 — Viết lại UI | 8 tab app.py → UI Miro, timeline multitrack, voice/overlay editor, scheduler UI, watch dashboard | §1 T1–T8, §2 schedule, §5 watcher | Vào: P1 bọc chạy. Ra: người dùng làm được full flow nhập→dịch→render→duyệt trên UI mới |
| P3 — Viết lại orchestrator | JobManager → Miro task engine (slot, pause/resume/stop, recovery, event schema tương thích) | §2 JobManager, §6 desktop_task route | Vào: P2 ổn định. Ra: bỏ được backend JARVIS cũ, giữ được journal/snapshot đọc lại |

Không bao giờ import: `post_<batch>.py` và batch-publisher cũ (đã bị thay thế), spikes đã tốt nghiệp, `.venv/node_modules/.next/cache`, secret/cookie/token.

## 2. Biên bọc (wrapper contract, không refactor sâu pha P0–P1)

- `miro.workers.dubtool_pipeline.run(source, steps, ...)` → gọi `core/pipeline.py::Pipeline.run`; giữ `project.json` + `*.done` + `segments.json` nguyên.
- `miro.adapters.<platform>.post(shortcode, batch_dir)` → gọi đúng 1 file `scripts/<platform>_post_one.py`; giữ guard publication + attempt + `_enforce_adapter_integrity`.
- `miro.browser.tab(...)` → chỉ qua `core/tab_acquisition.py::managed_tab` (Profile 20, flag PUBLISH, lease TTL); cấm mở CDP/browser mới ngoài runtime.
- `miro.desktop.act(...)` → qua `scripts/desktop_act.py` params; giữ gate epoch + window lock + read-back verify.
- `miro.studio.render(project_id, preview)` → qua `core/studio_service.py::StudioService`; giữ signature-checkpoint + ownership-blocked + retry budget.
- `miro.tasks.*` → giữ event tên `job_queued/step_progress/agent_done` để dashboard cũ/mới đọc chung lúc chuyển đổi.

## 3. Dữ liệu mang sang (đường dẫn + schema giữ nguyên pha đầu)

| Dữ liệu | Nguồn | Cách mang | Ghi chú |
|---|---|---|---|
| download.json / publication-*.json / attempt journals | `reports/resource-batches/*/`, `reports/social-attempts/` | copy read-only sang `miro/data/batches/`; Miro chỉ append journal mới, không sửa lịch sử | source of truth chống trùng |
| project.json / segments.json / timeline.json / dub.srt / *.done | `cache/<video_id>/`, `cache/studio/<id>/` | mount read-only trước, migrate dần sang store Miro ở P2 | giữ hash/signature để verify |
| browser-registry.sqlite / platform-domains.json | `config/` | bọc: Miro dùng chung file qua service, không song song 2 writer | 1 writer tại 1 thời điểm |
| schedules + plans ngày | `schedules/<platform>/<account>/` | giữ thuật toán `posting_schedule.py`, copy policy/plans | UNKNOWN slot giữ nguyên |
| job snapshots `job_*.json` | `backend/runtime/execution/jobs/` | chỉ đọc để đối chiếu; job non-terminal cũ xử lý theo `recover_pending` (BLOCKED, không replay) | không auto-restart side-effect |
| youtube-accounts.json (2 kênh) | `integrations/youtube-agent/config/` | giữ + nhắc mặc định Bảnh Love You | chỉ chuyển Love Cr7 khi user nói rõ |

## 4. Kiểm thử theo pha (dùng lại verify scripts legacy)

- P0: `verify_adapter_integrity.py` + đọc được publication/attempt mẫu; JSON round-trip BOM-safe.
- P1: chạy dry-run từng adapter với manifest fixture (không browser live): guard trùng trả SKIP; UNKNOWN fixture trả reconcile-only. Browser/desktop chỉ chạy `verify_shared_browser_live.py` / desktop recipe khi có phê duyệt môi trường.
- P2: so sánh output Miro vs legacy trên cùng fixture (segments→srt, plan→timeline, render preview 20s).
- P3: replay event journal cũ vào engine mới (read-only) + kiểm tra pause/resume/stop/unclean-slot.

## 5. Lộ trình file Miro (gợi ý, team Miro quyết cuối)

- `migrations/legacy/` — tài liệu này + `coverage.md` (docs/coverage) + manifest ánh xạ `source_path → miro_module → trạng_thái(giữ/bọc/viết_lại/bỏ)`.
- `src/workers/` — wrapper pipeline/studio/render. `src/adapters/` — 8 shim gọi scripts legacy. `src/browser/` — client của tab_acquisition/runtime. `src/tasks/` — engine mới. `src/ui/` — thay 8 tab Gradio + web Next.js.
- Mỗi shim ghi rõ: legacy path, commit/hash baseline, ngày kiểm kê, giới hạn (ví dụ Threads/Shopee UNSUPPORTED giữ manual).

## 6. Rủi ro & rào chắn

1. Hai writer cùng lúc vào sqlite/journal → quy định 1 browser service writer; còn lại read-only.
2. Replay UNKNOWN thành post trùng → mọi import step mặc định dry-run; mutation cần phê duyệt + journal trước click (như `_submit_once`).
3. Secret lọt vào docs/log → sanitize như `sanitize_data`; không copy `.env`, cookie, `studio-key.txt` nội dung.
4. Chrome/Profile 20 bị chiếm → không probe live trong import; mọi kiểm chứng live để riêng khi có phê duyệt.
5. Quota YouTube (12 chờ) / FB appeal / Threads remote-debugging flag → giữ trạng thái, không ép chạy lại trong migration.

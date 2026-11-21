# Mốc nguồn legacy (source freeze) — 2026-11-21

Ngày chốt: **2026-11-21**. Cả 2 nguồn **không phải git repo** (không có `.git`,
không có remote) nên mốc được ghi bằng SHA-256 file chính + listing cấu trúc
+ thời gian sửa cuối. Legacy là **read-only**; mọi thay đổi sau mốc thuộc về
repo Miro này.

## 1. C:\dubtool — pipeline dub/render/studio + web + browser runtime

| File | SHA-256 | Ghi chú |
|---|---|---|
| `app.py` | `6408B027F29106B7A747FB66905090A4A231D2D330972AC0EB922F7EF8B54B5A` | entrypoint legacy |
| `requirements.txt` | `EF04E8D0352B9B6E6D4092CBA08600CD3FA313A115C26D9D9590E5029DBE6B9C` | deps legacy |
| `AGENTS.md` | `FCA353006910456B17613C7637900C9B2BDC9020EAE7C3303A45B22954C49124` | quy ước agent cũ |
| `HANDOFF.md` | `6E19AC8CCA6DCD1F487B3100728B6F793680C0DD7E79E748B594DDBB6A9D48B5` | bàn giao mới nhất |

Cấu trúc chính (ngày sửa cuối trong ngoặc là mốc tương đối):
- `core/` — pipeline + studio: `pipeline.py`, `studio_service.py` (43 KB),
  `studio_model.py` (38 KB), `studio_render.py` (27 KB), `render.py`,
  `browser_runtime.py` (56 KB), `browser_registry.py`, `youtube_studio.py`, …
- `web/` — Next.js app (`package.json`, `tsconfig.json`, `next.config.ts`)
- `shared/` — `browser_contracts.py`, `browser_client.py`, `desktop_*`,
  `execution_policy.py`, `worker_supervision.py`
- `docs/` — ~29 file (`ARCHITECTURE.md`, `SOCIAL_PUBLISHING.md`,
  `FACEBOOK_REELS_PUBLISHER_2026-11-17.md`, …)
- `integrations/`, `poc-playwright/`, `spikes/`, `config/`, `tests/`,
  `scripts/`, `vendor/`

## 2. D:\JARVIS-Assistant — backend FastAPI agents/jobs/planner

| File | SHA-256 | Ghi chú |
|---|---|---|
| `README.md` | `26A89FD6DBEE829F7A3DE81AAA1DABB6033186043B0314450FCF0351AF28FA33` | tổng quan |
| `AGENTS.md` | `F939CE6E825D351BC14651F2BCD29AAFF9081076B431D6D46DF20D649CC88D3C` | quy ước agent cũ |

Cấu trúc chính:
- `backend/app/` — `main.py`, `agents/` (browser, page_extract, tiktok_discover,
  video_extract, synthesize, channel_report), `api/routes/` (assistant, jobs,
  plans, dubtool, dubtool_tasks, live_chrome, extract, video_analyze, …),
  `core/` (config, security, execution_policy, worker_supervision),
  `integrations/` (live_chrome, dubtool, tiktok, social_video, vision_client…),
  `jobs/` (manager, runner, journal, models), `planner/`, `plans/`,
  `policies/`, `router/`
- `backend/scripts/` — ~25 spike (`spike_tiktok_*`, `spike_*_vision`,
  `spike_browser_selection`, `smoke_dubtool_*`, `download_*`, …)
- `backend/tests/` — ~20 test module (`test_jobs`, `test_planner`,
  `test_router`, `test_live_chrome`, `test_video_extract`, …)
- `backend/runtime/` — artifacts chạy (video-extract frames/mp4) — **không migrate**
- `docs/` (`BACKEND-PLAN.md`, `INTEGRATION-MAP.md`, `DUBTOOL-DELEGATION.md`, …),
  `tasks/`, `research/`, `spikes/`

## 3. Quy tắc merge sau mốc này

- Nhánh `merge/dubtool-*` và `merge/jarvis-*` copy có chọn lọc từ 2 đường dẫn
  trên; mỗi merge commit ghi rõ nguồn file + SHA gốc.
- Không sửa trực tiếp legacy. Mâu thuẫn contract thì contract trong
  `contracts/` của Miro thắng.

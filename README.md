# Miro

Monorepo cho dự án **Miro** — hợp nhất 2 nguồn legacy:
- `C:\dubtool` (pipeline dub/render/studio + web Next.js + browser runtime)
- `D:\JARVIS-Assistant` (backend FastAPI agents/jobs/planner + browser/live-chrome + video-extract)

> Quy tắc: **không viết lại nghiệp vụ sâu** ở giai đoạn khung. Chỉ dựng khung +
> contract + tài liệu. Nghiệp vụ sẽ được merge dần từ các nhánh.

## Cấu trúc

```
apps/
  web/                 # Next.js + TypeScript strict + TanStack Query
  backend/
    src/miro/          # Python 3.12 + FastAPI
workers/
  browser/             # browser automation worker (playwright)
  media/               # ffmpeg/media worker
services/
  youtube/             # youtube upload/status service
contracts/             # API contracts (Render, Publisher) — nguồn chân lý
migrations/
  database/            # schema migrations mới
  legacy/              # ghi chú migrate từ legacy
tests/
  e2e/                 # end-to-end tests
fixtures/              # dữ liệu mẫu cho test/dev
docs/
  source-freeze.md     # mốc nguồn 2 dự án legacy
  architecture.md      # kiến trúc tổng thể
integrations.lock.yaml # chốt phiên bản integrations
```

## Contracts (nguồn chân lý)

- `contracts/render.*` — tạo render **idempotent**:
  request `{request_id, project_id, expected_revision, content_hash, spec}` →
  `201 {render_id, status}`. Gửi lại **cùng mã + cùng nội dung** → trả bản ghi cũ
  (replay). **Cùng mã + khác nội dung** → `409 Conflict`.
- `contracts/publisher.*` — xuất bản idempotent theo cặp
  `(publication_id, attempt_id)`.

## Phát triển

```bash
# web
cd apps/web && npm install && npm run dev

# backend
cd apps/backend && python -m venv .venv && .venv/Scripts/activate
pip install -e . && uvicorn miro.main:app --reload
```

## Mốc nguồn

Xem `docs/source-freeze.md`.

## Git

Commit khung vào `main`, **chưa push** (chờ user cho phép push).
Nghiệp vụ merge sau qua các nhánh `merge/dubtool-*`, `merge/jarvis-*`.

# migrations/legacy

Ghi chú migrate dữ liệu từ 2 nguồn legacy (không copy dữ liệu runtime vào repo).

- `C:\dubtool`: `core/studio_store.py` (SQLite/kho studio), `cache/`, `output/`
  → map sang bảng `projects`/`renders` ở `migrations/database/0001_init.sql`.
  Script migrate viết ở nhánh nghiệp vụ sau khi chốt schema studio.
- `D:\JARVIS-Assistant\backend\runtime\`: job journals (`app/jobs/journal.py`,
  `job_result_v2.json`), video-extract outputs → map sang `publications`.
  Không commit artifacts (`*.mp4`, `frames/`) vào repo; chỉ migrate metadata.

Nguyên tắc: legacy là read-only, migrate một chiều legacy → Miro.

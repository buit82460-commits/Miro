# Miro architecture (khung)

```
apps/web (Next.js) ──REST/JSON──▶ apps/backend/src/miro (FastAPI)
                                        │ contracts/render.json
                                        │ contracts/publisher.json
                                        ▼
                          ┌─ workers/browser (playwright extract)
                          ├─ workers/media   (ffmpeg render)
                          └─ services/youtube (upload/status)
```

- Render là cổng lũy đẳng duy nhất tạo job render (`request_id`).
- Publisher nhận `(publication_id, attempt_id)`, fan-out sang channel services.
- Browser/media workers không gọi trực tiếp lẫn nhau; giao tiếp qua backend.
- DB mới ở `migrations/database/`; legacy chỉ đọc, migrate một chiều
  (`migrations/legacy/README.md`).

Chi tiết module merge dần từ các nhánh `merge/dubtool-*`, `merge/jarvis-*`.

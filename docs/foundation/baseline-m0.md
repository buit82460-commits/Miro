# M0 — Bản xuất phát (đã duyệt, làm mốc so sánh vòng Browser)

Ngày chốt: 2026-11-21. Commit tích hợp: `ebe40ac`.
Lệnh chạy: `python -m pytest tests -q` trong `C:\Miro\apps\backend` → **90 passed, 0 failed, 0 skipped**.

| Hành vi cần giữ (nguồn) | Miro tiếp quản ở đâu | Kiểm tra mức nào | Còn thiếu gì |
|---|---|---|---|
| Caption/tag/journal/guard/two-phase/receipt Threads (Dubtool `scripts/threads_post_one.py`, `core/rea_eye.py`) | `apps/backend/src/miro/publishing/publisher.py` | 19 test: 15 oracle + 4 dữ liệu thật Dubtool, 0 post (Checker ĐẠT `a272587`) | Live post; UI→receipt xuyên suốt |
| Pipeline 8-step + invalidate + handoff guard (Dubtool `core/pipeline.py`, `studio_service.py`) | `apps/backend/src/miro/studio/pipeline.py` + `handlers.py` + `store.py` | 16 test luồng thật fixture video thật (Checker ĐẠT `ebe40ac`) | Cancel chưa kill ffmpeg giữa chừng; queue đầy chưa test |
| Slot đơn/contamination/retry/persist (JARVIS `jobs/`, `dubtool_tasks.py`) | `studio/store.py` (+ fingerprint/conflict) | Test C5/C6/C11 thật | Bản tasks chung chưa đủ B |
| Browser lease single-owner + verify account/tab | `browser/runtime.py` + `lease_store.py` | Test mock `test_browser_single_owner.py` | **Chưa bọc thật** — vòng Browser đang làm (M1) |
| Desktop epoch gate + dispatch + Notepad pilot | `desktop/` + `workflows/notepad_pilot` | 24 test (mock + pilot) | Chưa nối `desktop_act.py` thật |
| Connections account/verify/pause/reconnect/revoke | `connections/` | Test mock pass | Chưa verify live tab thật |
| Research search/read/channel/video/compare | `research/` + `NullProvider` | Test mock provider | Chưa cắm provider thật |
| Integrations/agent wrappers | `integrations/` + `agent/` | Test mock pass | Chưa gọi tool thật |
| Library asset/dedupe/tag/collection | `library/` | Test pass | Chưa nối pipeline đầy đủ |
| Renders/Publications API | `routers/` + `storage/registry.py` (SQLite) | Đúng contract idempotent/409 | E2E live chưa chạy |
| FE + E2E + launcher + workers | `apps/web`, `tests/e2e`, `windows/miro.py` | Fixture xanh, skeleton | Live E2E, installer |

## Nợ đã biết (đưa vào bảng, không giấu)
- Studio: cancel cooperative giữa step (ffmpeg đang chạy phải đợi xong); `src=auto→en`/voice-lang khác gốc.
- Publisher: browser thật out-of-scope; media attach cấm (`MEDIA_NOT_PORTED`).
- FE launcher/migration/installer: chưa làm.
- 7 adapter còn lại (IG/FB/YT/TikTok/Shopee/ChatGPT/Flow): chưa port — mẫu là Publisher Threads.
- Scheduler (`posting_schedule.py`): chưa port.

# Báo cáo tổng hợp Miro — main tại `b1b239e` (2026-11-21)

Người viết: agent tích hợp (tự review trên main local, chưa qua Checker độc lập).
Phạm vi: code + test trên repo `C:\Miro`, nhánh `main`, 57 commit, full BE suite **142 passed**.

## 1. Đã làm được gì (có bằng chứng trong repo)

| Mốc | Tính năng | Bằng chứng | Trạng thái |
|---|---|---|---|
| M0 | Nền monorepo, BE FastAPI + FE Next.js + SQLite | `docs/foundation/baseline-m0.md` | Đủ dùng |
| Publisher | Journal trước click, guard 2 lớp, tag duy nhất, ack 3 đường, phase B, approval bound fingerprint | `docs/verify/verify-publisher.md` | ĐẠT |
| Studio pipeline | 8 bước render, idempotent, recover | `docs/verify/verify-studio.md` | ĐẠT logic; **audio sai đã sửa `38acc8b`, verify `93079f3` 19 passed** |
| Browser M1 | Session reuse, TAB_BUSY, verify actor trước/sau, disconnect | `docs/verify/verify-browser.md` | ĐẠT bằng FakePage; **chưa Chrome thật** |
| M2 lõi | Worker DUPLICATE_TAGS + phase B + media gate file thật + HTTP publish nối worker + live-read read-only | `docs/verify/verify-threads-loop.md` (3 vòng) | ĐẠT có điều kiện |
| Tasks M3-p1 | workerOwner, retry TRANSIENT, stop 2 pha + watchdog | `docs/verify/verify-foundation.md` | ĐẠT phạm vi đăng ký |
| Tasks recover + registry | Permission-state đúng, recover instance-mới idempotent, rollback snapshot-trước, persist file | `d8d9beb`, 22 passed | ĐẠT (`b2afcdb`) |
| Actor + origin | Verify bắt buộc True rõ ràng, origin scheme/host/port ở acquire+navigate+URL cuối | `docs/verify/verify-security-fix.md`, 36 passed | ĐẠT (`3a88071`) |
| Desktop M3 | act boundary resolve/stop/epoch/verify/receipt | `docs/verify/verify-foundation.md` D1–D6 | ĐẠT phạm vi đóng gói |

## 2. Chưa làm được (đường chạm thật còn mở toàn bộ)

1. **Chrome thật**: chưa 1 lần mở Profile 20 từ Miro; `workers/browser/worker.py:19` vẫn `NotImplementedError`; ack/composer/eye vẫn fake. Có connector `browser/live_chrome.py` + runbook `docs/verify/live-read-profile20.md`, chờ người mở sẵn Chrome debug để chạy.
2. **Đăng thật**: chưa post bài nào; mọi test 0 post thật. FE `/api/publish/batches` vẫn fixture `status: "posted"` mẫu (`route.ts:28,37`).
3. **Giọng/dịch thật**: STT/dịch/lồng thật chưa nối (tone + từ điển nhỏ); faster-whisper chưa nối; FE editor chưa phát được video nghe trước khi duyệt.
4. **FE–BE**: contract lệch (`video_id/platform/account` vs `publication_id/attempt_id/render_id`); platform Settings chưa ra màn Publish; `/research/to-project` đã hết 500 thô (trả 503 rõ khi thiếu service) nhưng chưa có chạy nền thật.
5. **Scheduler + launcher**: port lịch + caller + RestartBudget chưa làm.
6. **M5**: cài Windows sạch, reboot, chạy dài, migration — chưa nghiệm thu.

## 3. Quyết định đề xuất

- Giữ roadmap; dán nhãn ĐẠT chỉ khi có bằng chứng thật (Chrome thật / MP4 nghe đúng / rollback đúng).
- Trước live post: chạy live-read thật 1 lần theo runbook, rồi nối `workers/browser/worker.py` vào session.
- Trước duyệt M2 hoàn toàn: 1 lần post thật có phê duyệt rõ của Sếp.

## 4. § FE Publish — `ef39528` (2026-11-21): ĐẠT

- Yêu cầu: nhãn DỮ LIỆU MẪU rõ + gọi BE `POST /threads/publish` dry-run;
  fixture chỉ fallback khi BE unreachable.
- Đối soát: `route.ts` BE reachable → `source=backend`, KHÔNG tạo receipt fixture
  `posted`; chỉ nhánh `unreachable` mới tạo receipt `status: "posted"` kèm
  `source: "fixture"` + `backend_detail` nhãn mẫu. Không còn đường nào trả
  `posted` mà thiếu nhãn mẫu (batch/receipt đều render `DỮ LIỆU MẪU — chưa đăng thật`).
- Lệnh + kết quả (trong `C:\Miro\apps\web`):
  - `npm run typecheck` → pass (`tsc --noEmit`, exit 0).
  - `npx playwright test e2e/threads-milestone.spec.ts --reporter=list` → **1 passed**
    (chromium, ~41s; có assert `publish-sample-note` chứa `DỮ LIỆU MẪU`).
- Người kiểm: Checker thường trực Miro. Commit KHÔNG push.

# INTEGRATION SECURITY REVIEW — Phiên B review Phiên A (read-only)

Ngày: 2026-11-22. Base: `6ef6c80` (310 passed, 2 skipped). Phiên B KHÔNG sửa
`experiments/extension-bridge/`, không sửa code production trong đợt này.

## 1. Đối chiếu contract (§5 interface Phiên A phải cung cấp)

| Yêu cầu contract | Trạng thái Phiên A (đọc code, chưa chạy live) |
|---|---|
| Pairing 1 lần, user xác nhận tường minh | **PASS (code)** — `bridge/channel.py`: pairing code 6 số, TTL 120s, tối đa 5 code song song, redeem sai >5 lần/60s bị khóa |
| Event chỉ read-only, action khác bị từ chối | **PASS (code)** — `ALLOWED_EVENTS={opened,closed,url-changed,updated,startup}`, `FORBIDDEN_ACTIONS={click,type,evaluate,fill,exec,run,debugger,attach,dom,readDOM}` → `ACTION_FORBIDDEN` |
| Chống replay | **PASS (code)** — session token + seq tăng đơn điệu, sai seq → `RESYNC_REQUIRED`; session TTL 120s → `SESSION_EXPIRED`; revoke có test |
| Token không lộ log | **PASS (code)** — token ở header, server redact khi log |
| `discover_tabs/read_tab/close_transport` | **NOT TESTED** — Phiên A mới có `registry/importer/server`, chưa expose đúng 3 hàm interface để Gateway gọi; `read_tab` trả page-handle thật chưa tồn tại (hiện mới event URL/title/tabId) |
| Event = dữ liệu chưa tin cậy, chỉ thành Evidence sau `read_via_eye` | **PASS (thiết kế)** — README ghi rõ REA Integration CHƯA ĐÁNH DẤU (phát hiện tab ≠ đọc nội dung); chưa có đường nào biến event thành Evidence mà không qua Gateway |

## 2. Review adapter WRITE — idempotency không phủ đều (điểm 2 của đánh giá)

| Đường WRITE | Guard/idempotency | Kết luận |
|---|---|---|
| `publisher.Publisher.run_batch` (threads/worker) | `claim_attempt` O_CREAT\|O_EXCL + `guard_duplicate` 2 lớp + journal submit/unknown + reconcile + `UNKNOWN-không-replay` | **PASS** — chuẩn cho contract §4.11 |
| `adapters/core.PlatformWorker.run_batch` (8 platform: tiktok/fb/ig/flow/chatgpt/youtube/shopee/threads) | `guard_duplicate` (publication submitted/published + journal tồn tại → `UNRECONCILED_ATTEMPT`) + `claim_attempt` trước `submit_once` + `ambiguous` dừng cả batch sau lỗi + journal `submitted` sau ack | **PASS** — tương đương publisher, không replay khi ack mơ hồ |
| `adapters/live.LivePage.submit_once` + `click_once_and_wait_ack` | 1 click duy nhất + ack 3 đường (toast/network/composer-closed); không ack → `LiveChromeError(before_submit=False)` → caller ghi UNKNOWN | **PASS (cơ chế)** — nhưng receipt `SUBMITTED` dựa trên toast/composer-closed có thể dương tính giả; **NOT TESTED** live |
| `adapters/vlance.py`, `freelancer_vn.py`, `upwork.py` (mới) | Chỉ `job_for` validate (title/desc, cấm contact-info, skills≤10). **Chưa có `submit_once`/journal/guard nào** — post thật đang `UNSUPPORTED` nên chưa nguy hiểm, nhưng khi Phiên A mở WRITE phải port guard từ `core.PlatformWorker` trước | **FAIL (thiếu)** — chặn mở WRITE cho 3 adapter này tới khi có guard + test |
| `youtube_api.upload_video` | Upload qua API, không qua Gateway/lease/Evidence | **NOT TESTED** — ngoài phạm vi contract hiện tại, cần review riêng trước production |

**Kết luận điểm 1 của đánh giá:** `UNKNOWN` sau lease hết hạn (T20/T25) chỉ an toàn khi mọi đường WRITE đều có idempotency + journal + reconcile trước khi thử tiếp. Hiện publisher + core.PlatformWorker có; 3 adapter freelance chưa; youtube_api ngoài phạm vi. **Không coi UNKNOWN là thất bại rồi tự đăng lại — đã đúng ở caller (`ambiguous`/`UNCONFIRMED_NO_REPLAY`), nhưng adapter mới chưa được phép WRITE.**

## 3. Trạng thái Phiên A (không can thiệp)

- MỐC 1+2 + kênh xác thực: PASS theo test của Phiên A (`test_live_moc2`, `test_channel`, `test_e2e`). REA Integration và đọc DOM: CHƯA.
- Extension chỉ xin quyền `tabs` (không debugger/executeScript) — đúng phạm vi read-only.
- Bàn giao: contract `docs/security-contract-extension.md` đã sẵn; Phiên A tích hợp khi xong Live Test Backend.

## 4. Harness (nhắc lại, chưa áp dụng)

Không có config trong repo; `docs/harness-allowlist-report.md` vẫn là tài liệu chờ quản trị áp dụng. Không tuyên bố đã khóa runtime.

## 5. Kết quả review

- **PASS:** channel auth/replay/ttl, event read-only, publisher + core idempotency, gate instance/lease/Evidence (310 tests).
- **FAIL:** 3 adapter freelance chưa có guard WRITE → giữ `UNSUPPORTED`.
- **NOT TESTED:** interface `discover_tabs/read_tab/close_transport` thật, E2E fake transport (§6 contract), youtube_api, REA đọc DOM qua extension.

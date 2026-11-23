# Spike: extension-bridge (MV3 read-only Tab Discovery)

## Mục tiêu

Chứng minh Miro phát hiện tab do user tự mở trong Profile 20 đang chạy
bình thường — không restart Chrome, không cổng 9222 — qua Extension MV3
+ Tab Registry. Read-only: chỉ URL/title/tabId, chưa đọc DOM, chưa WRITE.

## Kết quả: PASS MỐC 1 + MỐC 2 (Live Test 1) + KÊNH XÁC THỰC (bước 3)

- Live Test 1 (22/11/2026, Profile 20 + extension unpacked
  `lkgegddogocecgeaifjcjmbpblggamlm`): service worker log thấy tab thật
  `tabId 1302900372` (lần 1, thiếu quyền storage → outbox fail) và
  `tabId 1302900374` (lần 2 sau reload, hết outbox fail, đủ
  opened/url-changed/updated, title `(32)/(33)TikTok` = session login).
- MỐC 2: `test_live_moc2.py` PASS với đúng 6 event thật của user
  (import 6/6, url chốt `tiktok.com/@nghecontent9699`, fresh).
- Bước 3 (kênh xác thực, chưa live): `test_channel.py` PASS
  (pairing/redeem, auth HMAC, seq+1, SEQ_REPLAY/RESYNC_REQUIRED,
  ACTION_FORBIDDEN, SESSION_EXPIRED 120s, revoke) + `test_e2e.py` PASS
  (pair → push mở/đổi URL/đóng → registry, resync, fail-closed).
  Extension gửi tự động qua `/push` + `/resync` (loopback, token ở header,
  không log token); website thường không gọi được vì thiếu session/token.
- REA Integration: CHƯA ĐÁNH DẤU (phát hiện tab ≠ đọc nội dung).

- Live Test 1 (22/11/2026, Profile 20 + extension unpacked
  `lkgegddogocecgeaifjcjmbpblggamlm`): service worker log thấy tab thật
  `tabId 1302900372` (lần 1, thiếu quyền storage → outbox fail) và
  `tabId 1302900374` (lần 2 sau reload, hết outbox fail, đủ
  opened/url-changed/updated, title `(32)/(33)TikTok` = session login).
- MỐC 2: `test_live_moc2.py` PASS với đúng 6 event thật của user
  (import 6/6, url chốt `tiktok.com/@nghecontent9699`, fresh).
- REA Integration: CHƯA ĐÁNH DẤU (phát hiện tab ≠ đọc nội dung).

- Scaffold xong: `extension/` (MV3, quyền `tabs`) + `bridge/registry.py` + test.
- Unit: `test_registry.py` PASS (lifecycle + key (browser,tab) + STALE +
  UNAVAILABLE + không tab trùng); `test_importer.py` PASS (kênh
  Extension → Backend → TabRegistry nhận 4/7 event hợp lệ, loại rác).
- 2 mốc tách rõ: MỐC 1 extension thấy tab (log + outbox storage.local),
  MỐC 2 backend nhận event cập nhật TabRegistry (`bridge/importer.py`).
- Extension chỉ xin quyền `tabs` (grep: không debugger/executeScript/
  capture/cookies/history) — read-only đúng phạm vi.
- Chưa cài extension vào Chrome thật → Discovery/Lifecycle live chưa PASS.
- REA Integration: CHƯA ĐÁNH DẤU (phát hiện tab ≠ đọc nội dung).

## Quyết định

GIỮ mô hình grant/command từ `chrome-extension-v1` (grant ≤120s,
allowlist, deny mặc định). Mã spike KHÔNG import vào code chính.
Muốn dùng thì port qua nhánh `merge/*` có review.
Không sửa `Miro-Chrome-Profile20.bat`, không đụng `apps/`, không mở
đường ghi. `chrome.debugger` chỉ nghiên cứu sau khi Discovery PASS.
Phiên B không sửa file trong thư mục này khi Phiên A đang thử nghiệm.

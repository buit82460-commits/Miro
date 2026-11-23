# SECURITY REVIEW — REA Read-Only Extension Bridge (Phiên B review Phiên A)

Ngày: 2026-11-22. Phạm vi: `experiments/extension-bridge/` tại trạng thái
hiện tại (grant + `chrome.scripting` title live PASS, meta/text-limited unit).
Không sửa code Phiên A. Không push.

## Kết quả tổng: NGHIỆM THU DOM TITLE READ-ONLY LIVE PASS. CHƯA CHỐT REA EVIDENCE PASS.

## 1. PASS (có file:dòng)

- P1: `manifest.json:6` permissions `tabs/storage/scripting/activeTab`, không
  debugger/executeScript/capture/cookies/history. `activeTab` chỉ là tín hiệu
  tạm của Chrome; TTL 120s do `grants.py:18` quy định riêng. PASS.
- P2: pairing (`channel.py:65-86` redeem code 6 số, TTL 120s, lock sau 5 sai)
  và DOM grant (`grants.py:28-49` GESTURE_REQUIRED, ORIGIN_NOT_GRANTED) là hai
  quyền độc lập; pairing không suy ra grant (`test_read_grant.py:23-24`).
  PASS.
- P4: grant ràng buộc instance+tab+origin+TTL (`grants.py:51-67` check 4 điểm,
  sai tab → GRANT_REQUIRED, sai origin → ORIGIN_MISMATCH, hết hạn →
  GRANT_EXPIRED + xóa). PASS (code+unit).
- P5: navigation khác origin → `revoke_tab` (`grants.py:69-72`); đóng tab →
  pop registry (`registry.py:38-42`); `/revoke` → xóa session + unavailable +
  xóa grant (`server.py:155-159`); restart → token không lưu (`background.js:15-22`),
  session TTL 120s. PASS (code+unit, revoke có live).
- P6: `read.js:4-19` chỉ 3 func cố định (title/meta/text-limited);
  `validate_read_spec` từ chối mọi spec lạ kể cả `document.cookie/innerHTML/
  querySelector` (`grants.py:81-85`, `test_read_grant.py:52-61`).
  `server.py:184-186` validate spec trước grant-check. PASS.
- P7: `/read` trả `PENDING_EXTENSION` (`server.py:200-202`), comment ghi rõ
  "dữ liệu trả về = chưa tin cậy, chờ REA/Eye xác minh". `transport.py:39-41`
  `read_tab` raise NO_PAGE_HANDLE_YET, cấm tự tạo Evidence. PASS (thiết kế).
- P8: `FORBIDDEN_ACTIONS` gồm click/type/evaluate/fill/exec/run/debugger/
  attach/dom/readDOM (`channel.py:27-28`); push chứa action lạ → toàn bộ batch
  ACTION_FORBIDDEN (`channel.py:122-123`, `test_read_grant.py:64-71`).
  `readFixed` dùng `func` đóng gói, không `code` string (`read.js:24-27`).
  PASS ở phạm vi channel.

## 2. WARNING (cần Phiên A xác nhận, không chặn nghiệm thu title)

- W1 — activeTab mất khi navigation: `popup.js:50` query tab active rồi xin
  grant; nếu user chuyển tab giữa grant và read, `GRANTS.check` đúng tab cũ
  nhưng DOM đọc có thể không còn là tab user nhìn. Giảm nhẹ: grant TTL ngắn
  120s + `micro-read` gửi `miro-read` ngay sau grant cùng popup session.
  Đề nghị: backend log `tabId` grant vs read để đối chiếu khi nối Evidence.
- W2 — `optional_host_permissions tiktok.com` (`manifest.json:7`): lần đầu
  `executeScript` Chrome hỏi user; nếu user từ chối, read fail-closed (đúng)
  nhưng UX live test cần ghi lại. Không phải lỗi bảo mật.
- W3 — reconciliation `complete` mặc định True (`server.py:146`):
  `data.get("complete", True)` — snapshot thiếu trường vẫn được coi đầy đủ.
  Extension hiện luôn gửi `complete: true` (`background.js:57-59`) nên live
  đúng; nhưng backend nên mặc định False để fail-closed khi client cũ/thiếu.
- W4 — `README.md:9` "Bước 3 (kênh xác thực, chưa live)" đã cũ; thực tế đã
  live 6/6 + grant/title. Cập nhật khi rảnh, không gấp.

## 3. BLOCKER (chặn trước khi nối vào `read_via_eye` / REA Evidence live)

- **B1 — gesture tự khai báo, backend tin mù** (`server.py:160-177`):
  backend nhận `data.get("gesture")` string từ extension rồi truyền thẳng vào
  `GRANTS.grant(... gesture ...)`, chỉ kiểm tra non-empty
  (`grants.py:33-34`). Mọi client có session hợp lệ (kể cả website giả Origin
  qua non-browser fetch — `_origin_ok` cho qua khi không Origin,
  `server.py:100`) đều có thể tự POST `/grant` với `gesture: "popup-grant"`
  mà không cần user bấm nút thật. Chuỗi tin cậy đứt ở đây: `miro-grant`
  message từ popup → background (`background.js:103-120`) không gắn bằng
  chứng Chrome-verified (ví dụ `chrome.tabs` active-tab snapshot tại thời
  điểm bấm, hoặc nonce ký bởi background). **Sửa tối thiểu:** background tự
  điền `gesture` + `openerTabId`/`windowId` từ `sender.tab`/tabs.query tại
  thời điểm nhận message (không nhận từ popup payload), backend đối chiếu
  tabId grant == tab active thật; hoặc bỏ trường gesture khỏi wire, backend
  ghi `gesture="popup-grant-verified-by-background"` khi request đến từ
  session extension hợp lệ + tab tồn tại trong registry fresh. Tới lúc đó,
  grant vẫn có giá trị "user đã pair + extension còn quyền tabs", nhưng
  KHÔNG được quảng cáo là "user gesture trên đúng tab" trong Evidence.
- **B2 — `/read` không xác minh origin tại thời điểm đọc** (`server.py:191-194`):
  `GRANTS.check(s["instance"], tab_id, rec.url)` dùng `rec.url` từ registry
  (dữ liệu event cũ), không phải URL hiện tại của tab. Tab navigate từ
  tiktok sang origin khác giữa event cuối và lệnh read → check vẫn dùng URL
  cũ → origin đúng → cho đọc tab đã rời origin. **Sửa tối thiểu:** `/read`
  bắt buộc extension gửi `currentUrl` trong request read, backend so với
  `grant.origin` (exact-origin match) trước khi trả PENDING; mismatch →
  `revoke_tab` + ORIGIN_MISMATCH. (Registry event `url-changed` là async,
  không đủ nhanh cho check này.)
- **B3 — kết quả read quay về qua `/push` event `updated` lẫn với event thường**
  (`background.js:127-135`): `read_spec` đi kèm nhưng `import_outbox`
  (`importer.py:10-28`) không phân biệt read-result vs event quan sát —
  cùng `apply` vào registry, cập nhật `url/title` từ dữ liệu DOM (chưa tin
  cậy) như event thật. Kẻ kiểm soát trang (XSS trên tiktok hoặc MITM
  loopback) có thể đầu độc registry qua `document.title`. **Sửa tối thiểu:**
  tách kênh: read-result qua endpoint riêng `/read-result` (không qua
  `/push`), không `apply` vào registry; registry chỉ nhận event vòng đời tab
  từ `chrome.tabs` API (nguồn Chrome, không phải DOM).

## 4. Đề xuất sửa tối thiểu trước REA/Eye Evidence live (thứ tự ưu tiên)

1. B1 (gesture): background tự chứng thực, bỏ tin mù client.
2. B3 (tách kênh read-result khỏi registry).
3. B2 (origin check tại thời điểm read bằng currentUrl).
4. W3 (complete mặc định False ở backend).

Xong 4 mục + test unit cho từng mục, Phiên B review lại diff rồi mới cho nối
vào `read_via_eye` + `_verify_actor` + Evidence `provenance: rea-eye`.

## 5. Ghi nhận nghiệm thu

- **DOM title read-only: LIVE PASS** (log đã báo cáo, code khớp).
- **REA Evidence: CHƯA PASS** — `transport.read_tab` chưa có page-handle thật,
  title trả về ≠ Evidence.
- 3 adapter freelance giữ `UNSUPPORTED` WRITE. Không mở WRITE.

# Đối chiếu độc lập reread-tab (commit dfcc72f) — 2026-11-21

Phạm vi: `C:\Miro\docs\reread-tab.md` (dfcc72f) so với
A = `C:\dubtool\core\tab_acquisition.py`, `C:\dubtool\core\browser_runtime.py`,
`C:\dubtool\scripts\social_live_chrome.py:18-27`;
C = `C:\Miro\apps\backend\src\miro\browser\runtime.py` (507 dòng),
`live_chrome.py` (210 dòng).

## 1. targetId tự chế `live-{index}` — ĐÚNG
- C: `live_chrome.py:104` `target_id = f"live-{index}"` theo `enumerate(pages)` (L101-105),
  ghi vào `session.runtime.pages[target_id]` (L105) và record `targetId` (L108).
- A: `browser_runtime.py:70-75` `_target()` lấy thật qua CDP
  `session.send('Target.getTargetInfo')` → `info['targetId']`; mọi nơi
  (`inventory` L86, `_observe` L174, `_validate` L317, `create_tab` L569) dùng
  targetId CDP thật.
- Hệ quả như reread mô tả là đúng: thứ tự pages đổi → cùng page vật lý đăng ký
  2 key khác nhau, store mất liên kết CDP; `acquire_tab` C tra
  `self.pages.get(record["targetId"])` (`runtime.py:361`) bằng key giả.
- Reread dẫn `live_chrome.py:101-115` — đúng vị trí.

## 2. So sánh URL exact, thiếu chuẩn hóa — ĐÚNG
- C so sánh `==`/`!=` thô tại: `runtime.py:338` (prefilter exact),
  `runtime.py:342` (`_rank.exact_url`), `runtime.py:370` (`needs_nav`),
  `runtime.py:403` + `:414` (`read_tab` origin check 2 lần),
  `live_chrome.py:95` (reattach compare) và `live_chrome.py:103` (register compare).
- A: `browser_runtime.py:27-37` `_urls_same_destination` (strip `/` cuối +
  bỏ query `_IGNORED_QUERY_KEYS`, L17: `fbclid, utm_*/_rdc/_rdr`); dùng trong
  rank L652, needs_nav L686, navigate L519/L484.
- Reread dẫn `C acquire_tab rank/needs_nav L338/370, register L103,
  read_tab/navigate_tab origin check` — khớp hết. Sửa đề xuất
  (port `_urls_same_destination` + `_IGNORED_QUERY_KEYS`) đúng hướng.

## 3. `acquire_tab` gặp protected thì raise ngay — ĐÚNG
- C: `runtime.py:371-378` — trong vòng lặp candidate, `raise TabProtected(...)`
  ngay sau `release(lease)`; `saw_busy` có nhưng không có `saw_protected`/`continue`.
- A: `browser_runtime.py:687-691` — `saw_protected = True; continue` thử candidate
  tiếp; raise `TAB_PROTECTED_NO_NAVIGATE` chỉ khi `not allow_create` sau vòng lặp
  (L723-725). C hung hơn A như reread nói — đúng.
- Sửa đề xuất (continue + nhớ cờ, raise sau vòng lặp) đúng hướng.

## 4. Bug gốc có thật không — CÓ THẬT
Cả 3 đều là bug gốc phía C (không phải do reread bịa): key giả CDP, thiếu
chuẩn hóa URL, raise-sớm bỏ sót candidate. Đối chiếu trực tiếp file:dòng ở trên.

## 5. Mục SAI / BỎ SÓT trong reread
- **SAI: không có.** Mọi dẫn chiếu file:dòng kiểm tra được đều khớp mã nguồn
  hiện trạng (A `acquire_tab` L610-753, `_inspect_page_state` L422-481,
  `_navigation_breaks_flag` L483-510, `bind_profile` L94-108, `inventory` L80-92;
  `social_live_chrome.py:18-27` pattern DevToolsActivePort + regex route —
  C `runtime.py:85-125` port đúng, có thêm fallback `endpoint` + `CDP_UNAVAILABLE`
  như reread ghi).
- **BỎ SÓT (nhỏ, không đổi kết luận):**
  1. Reread mục 2 không liệt kê hết điểm exact-compare: ngoài L338/370/103 còn
     `runtime.py:342` (rank), `:403`/`:414` (read_tab 2 lần), `live_chrome.py:95`.
     Nhưng mục 2 có ghi gộp "read_tab/navigate_tab origin check" nên chỉ thiếu
     số dòng, không thiếu ý.
  2. Không đề cập `runtime.py:438` (`navigate_tab` check `final_url` bằng
     `_check_origin` thay vì exact) — thực ra chỗ này C làm đúng kiểu origin,
     nên việc không nhắc là hợp lý, ghi nhận để khỏi sửa nhầm thành exact ở đó.

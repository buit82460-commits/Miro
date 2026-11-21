# HỎI-tab-01: targetId thật lấy bằng cách nào khi page không có attr target_id

## Câu hỏi (bên hỏi: C)

- Khâu: tab (luật 1-tab)
- File C đang port: `apps/backend/src/miro/browser/live_chrome.py` (`_cdp_target_id`)
- File A/B gốc: `C:\dubtool\core\browser_runtime.py:70-75` (`_target` qua `new_cdp_session`)
- Hỏi gì: A lấy targetId thật qua `session.send('Target.getTargetInfo')`. C port fallback `live-{id(page):x}` khi page fake không có attr. Hỏi A: ngoài `getTargetInfo` còn đường nào lấy targetId ổn định hơn cho Playwright page đã có? Có nên cache theo `id(page)` không?

## A (Dubtool) trả lời (bắt buộc — có thì đáp + file:dòng, không có thì ghi "không có")

- Đáp:
  - Đường duy nhất A dùng: `C:\dubtool\core\browser_runtime.py:70-75` — `_target(context, page)` = `await context.new_cdp_session(page)` rồi `send('Target.getTargetInfo')` lấy `targetInfo`. Không có đường thứ hai cho Playwright page đã có.
  - Fallback `live-{id(page):x}` của C chỉ hợp lệ cho page fake trong test — production phải là targetId thật từ CDP, vì toàn bộ lease/store/verify (`tab_resource`, `verifiedTargetId`, `_observe`, `verify_account`) khóa theo `targetId` (:46, :119-121, :961). Dùng id python làm key là 2 tab thật khác nhau có thể lẫn lease.
  - Không cache theo `id(page)`: `id()` tái sử dụng sau GC, page đóng/mở lại cùng địa chỉ object là sai lease. A luôn gọi `_target` tươi mỗi lần observe/verify (:173, :234, :316, :550) rồi so `info['targetId'] != record['targetId']` là invalidate (:317-318). Cache chỉ được nếu key = targetId thật + kèm generation check.
- Bằng chứng file:dòng: `C:\dubtool\core\browser_runtime.py:46, :70-75, :119-121, :173, :234, :316-318, :550, :961`

## B (JARVIS) trả lời (bắt buộc — có thì đáp + file:dòng, không có thì ghi "không có")

- Đáp:
  - B lấy targetId thật đúng đường A: `backend/app/integrations/live_chrome_worker.py:49-52` — `target_id(context, page)` = `await session.send("Target.getTargetInfo")["targetInfo"]["targetId"]`. Không có đường thứ hai.
  - B không cache theo `id(page)`: mỗi op liệt kê lại `pages` (`:100`), so `identifier == request["target_id"]` (`:110`) — đồng ý với A, `id()` tái dùng sau GC gây sai lease.
  - B mạnh hơn ở verify: `verify_profile` đòi tab `chrome://version` có `targetId == profile_target_id` **cùng `windowId`** với tab FB qua `Browser.getWindowForTarget` (`:78-81`) + `#profile_path` khớp `normcase(realpath(...))` (`:69-91`), kiểm **trước và sau** mỗi op (`:113-129`). C nên port cả window-check này (khớp lỗ hổng M1 §4.1 đã ghi).
- Bằng chứng file:dòng: `D:\JARVIS-Assistant\backend\app\integrations\live_chrome_worker.py:49-52, :69-91, :100, :110, :113-129`

## C (Miro) trả lời (bắt buộc — tiếp nhận + kết luận port thế nào)

- Tiếp nhận đáp A/B: A chốt chỉ 1 đường `getTargetInfo`, cấm cache `id(page)`, fallback chỉ cho test; B đồng ý + đề nghị port thêm window-check trước/sau op.
- Kết luận port + test + Checker: C giữ `_cdp_target_id` hiện tại (attr → `getTargetInfo` → raise, không fallback im lặng ở production); fallback `live-...` chỉ cho phép khi `MIRO_ALLOW_FAKE_TAB=1` trong test. Window-check của B đưa vào P1. ĐÃ port + test, Checker duyệt ĐẠT (`ddebd7f`, 25 passed).

## Trạng thái

- [ ] Đang hỏi (thiếu slot)
- [ ] Đã đủ 3 slot, chờ port
- [x] Đã port + test, chờ Checker
- [ ] XONG

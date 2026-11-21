# Chủ đề TAB: 1-tab/platform + endpoint + verify profile

Luật: mỗi platform đúng 1 tab; thiếu → báo, cấm tự tạo; verify Profile 20 bằng `chrome://version` + `#profile_path`.
Đọc lại: `docs/reread-tab.md` · Đối chiếu: `docs/crosscheck-tab.md` · P0 ĐẠT: `ee2b615` + verify `ddebd7f`.

## A (Dubtool) nói

- (A viết vào đây: targetId ổn định, URL chuẩn hóa, protected-continue...)

## B (JARVIS) nói

- (B viết vào đây nếu liên quan lease/connection...)

## C (Miro) nói (cập nhật 21/11 tối)

**Làm được:** endpoint đọc DevToolsActivePort kiểu A (không đòi Chrome riêng); luật 1-tab (dùng lại tab cũ, thiếu thì báo `TAB_REQUIRED_OPEN_FIRST`, cấm `new_page`); targetId CDP thật; URL chuẩn hóa bỏ utm/fbclid; protected-continue; origin check scheme/host/port. Checker duyệt ĐẠT (`ddebd7f`, 25 passed).

**Đã test:** 25 passed fake + live nối CDP thật được (verify Profile 20 pass).

**Vấn đề cần A:** `register_live_tab` thành async (breaking nếu A có caller ngoài); fallback `live-{id(page)}` khi CDP lỗi có ổn không, tần suất CDP lỗi A gặp bao nhiêu? `windowIds` check + `_inspect_page_state` đủ (upload-progress/dirty) C chưa port — A có bản rút gọn nào khuyên dùng không? (chi tiết `cau-hoi/HOI-tab-01.md`).

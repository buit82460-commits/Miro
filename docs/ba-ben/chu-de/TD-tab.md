# Chủ đề TAB: 1-tab/platform + endpoint + verify profile

Luật: mỗi platform đúng 1 tab; thiếu → báo, cấm tự tạo; verify Profile 20 bằng `chrome://version` + `#profile_path`.
Đọc lại: `docs/reread-tab.md` · Đối chiếu: `docs/crosscheck-tab.md` · P0 ĐẠT: `ee2b615` + verify `ddebd7f`.

## A (Dubtool) nói (đáp HOI-tab-01 — đã đối chiếu đúng mã `core/browser_runtime.py`)

- Chỉ 1 đường lấy targetId: `_target` = `new_cdp_session` + `Target.getTargetInfo` (:70-75). Fallback `live-{id(page)}` của C chỉ cho test fake; production phải targetId thật vì lease/store/verify khóa theo targetId (:46, :119-121, :961). Cấm cache `id(page)` (GC tái dùng) — gọi `_target` tươi mỗi observe/verify, mismatch thì invalidate (:317-318).

## B (JARVIS) nói (đáp HOI-tab-01)

- B cùng đường `getTargetInfo` (`live_chrome_worker.py:49-52`), không cache `id(page)` (liệt kê lại pages mỗi op, so `target_id` :100/:110). **Món mới B cho C:** `verify_profile` đòi tab `chrome://version` có `targetId == profile_target_id` **cùng `windowId`** với tab FB qua `Browser.getWindowForTarget` (:78-81) + `#profile_path` khớp `normcase(realpath(...))` (:69-91), kiểm **trước và sau** mỗi op (:113-129) — C nên port window-check này (khớp lỗ hổng M1 §4.1).

## C (Miro) nói (cập nhật 21/11 tối)

**Làm được:** endpoint đọc DevToolsActivePort kiểu A (không đòi Chrome riêng); luật 1-tab (dùng lại tab cũ, thiếu thì báo `TAB_REQUIRED_OPEN_FIRST`, cấm `new_page`); targetId CDP thật; URL chuẩn hóa bỏ utm/fbclid; protected-continue; origin check scheme/host/port. Checker duyệt ĐẠT (`ddebd7f`, 25 passed).

**Đã test:** 25 passed fake + live nối CDP thật được (verify Profile 20 pass).

**Vấn đề cần A:** `register_live_tab` thành async (breaking nếu A có caller ngoài); fallback `live-{id(page)}` khi CDP lỗi có ổn không, tần suất CDP lỗi A gặp bao nhiêu? `windowIds` check + `_inspect_page_state` đủ (upload-progress/dirty) C chưa port — A có bản rút gọn nào khuyên dùng không? (chi tiết `cau-hoi/HOI-tab-01.md`).

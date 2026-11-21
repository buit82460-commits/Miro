# VERIFY Browser M1 — `apps/backend/src/miro/browser/runtime.py` (commit 8a340ff, ngày 2026-11-21)

Checker thường trực, định nghĩa merge mới: (1) giữ đủ khả năng + quy tắc gốc A/B,
(2) trùng thì chọn cách tốt nhất có ghi rõ, (3) kiểm chứng bằng luồng thực tế trong C.
Chạy: `python -m pytest test_browser_m1.py test_browser_single_owner.py -q` → **12 passed**.
Phạm vi M1: READ-only (read/navigate trên fake page trong bộ nhớ), không post, không Chrome thật.

## Kết luận chung: **ĐẠT M1** (read-only) — 4/4 nghiệm thu pass, có phần mở cho M2

## 1. Nghiệm thu M1 (CHỈ ĐỌC)

| Nghiệm thu | Test | Kết quả |
|---|---|---|
| Tái dùng đúng tab theo rank | `test_reuse_same_tab_by_rank` — 2 tab cùng platform, request khớp url+channel+flag → chọn đúng `best`, `reused is True` | **ĐẠT**. Rank `(exact_url, exact_channel, flag_match, lastUsedAt)` đúng thứ tự A (`browser_runtime.py:652-657`) |
| Task thứ hai bị chặn | `test_second_task_blocked_tab_busy` — tab đang lease → `TabBusy`, `len(tabs)==1` (không tạo tab trùng) | **ĐẠT**. Đúng A (`TAB_BUSY ... no duplicate tab created`, `:722`) + B (không cướp lease, không retry post) |
| Verify sai account bị từ chối | `test_verify_actor_injected_before_and_after` (2 calls trước+sau read; sai → `WorkerStopped ACCOUNT_MISMATCH` + lease invalidate → `renew` cũng fail) + `test_verify_actor_rejected_on_navigate` (fail trước `goto`, `goto_calls==[]`) | **ĐẠT**. Đúng B (verify trước VÀ sau mỗi op, `worker.py:113-129`) + A (verify trước submit, §7.3 — ở M1 áp cho read/navigate) |
| Phục hồi sau ngắt | `test_disconnect_revokes_worker_no_autoreconnect` — `disconnect()` → `renew` WorkerStopped; session cũ `BROWSER_DISCONNECTED`, không tự reconnect; reconnect = `open()` mới (connect lần 2); `close()` idempotent, không tắt Chrome | **ĐẠT**. Đúng A (`DISCONNECT_CLOSE`, receipt UNKNOWN, không reconnect — FB `:171-175`) + B (`SESSION_CHANGED`, không mở browser thay thế) |

## 2. Đối chiếu A (`reader-dubtool.md` §7) — từng điểm áp dụng cho M1

- **`chrome_endpoint` — ĐẠT.** Đọc `DevToolsActivePort` → `ws://127.0.0.1:port/route`, lỗi → `CDP_UNAVAILABLE`, không tự mở Chrome. Khớp A (`social_live_chrome.chrome_endpoint`, §7.2) từng chữ.
- **1 connect CDP / batch — ĐẠT.** `ManagedChromeSession.open` assert đúng 1 connect call (`CONNECT_ONCE`). Khớp A (§7.2: 1 lần `connect_over_cdp`, cuối batch `release()` + `browser.close()` = ngắt CDP, KHÔNG tắt Chrome).
- **Rank tái dùng — ĐẠT có ghi nhận.** Thứ tự rank đúng A. Khác biệt nhỏ: A so URL bằng `_urls_same_destination` (chuẩn hóa), C so string exact. Với M1 read-only + `allowed_origins` gate, exact-match là chặt hơn (an toàn hơn), chấp nhận; khi sang publish (M2) nên copy chuẩn hóa của A.
- **TAB_BUSY không tạo tab mới — ĐẠT.** C raise `TabBusy`, không fallback. A sau khi hết candidate còn `create_tab` từ `entryUrls[flag]` (`:732`); **C M1 cố tình không tạo** (docstring `acquire_managed_tab`: "không tự tạo") — đúng ngữ nghĩa JARVIS existing-Chrome (Đ2: không launch/copy/new-page), đã ghi rõ. Đường create cho publish là việc M2.
- **`needs_nav` → `TAB_ORIGIN_CHANGED` thay vì navigate — ĐẠT cho M1.** `acquire_tab` từ chối tab đã đổi URL thay vì tự navigate (kể cả khi tab sạch). Chặt hơn A (A cho `navigate_if_needed`), đúng cho read-only: tránh di chuyển tab người dùng. M2 publish (cần navigate tới destination) phải nới có guard `TabProtected`.
- **TabProtected (upload/form/flagWatch) — ĐẠT.** `_inspect_page_state` (upload/dirty) + `flagWatch` chặn navigate, khớp A (`:486-506`, `add_overlay` flag). Test M1 chưa cover nhánh này → nợ 1 test M2.
- **Disconnect — ĐẠT.** `close()` đánh `disconnected` + invalidate lease, không reconnect/khởi động lại Chrome. Khớp A §7.4 + invariant §5.3.

## 3. Đối chiếu B (`reader-jarvis.md` §8) — từng điểm áp dụng cho M1

- **Verify kép trước+sau — ĐẠT.** `read_tab`/`navigate_tab` đều `_verify_actor` trước và sau op; mismatch → invalidate lease + `WorkerStopped` (worker cũ mất quyền). Khớp B §8.2–8.3 (`ACCOUNT_MISMATCH`, `ORIGIN_CHANGED` khi đổi URL giữa chừng).
- **Lease SQLite ttl 180 + validate — ĐẠT.** Default `_DEFAULT_TTL=180` khớp B (`ttl=180`); `renew`/`read`/`navigate` đều validate, mất quyền → `WorkerStopped`, không replay. (A dùng 300 — C chọn 180 của B, đã ghi rõ trong comment.)
- **Không `browser.close/context.close`, không kill Chrome — ĐẠT.** `close()` chỉ `disconnect()` + đánh dấu; test assert page không bị đóng.
- **`tabs` không lease — KHÔNG ÁP DỤNG M1.** C chưa có đường liệt kê tabs riêng; `acquire_tab` luôn lease. Khi thêm `tabs` (M2) phải giữ: list không lease, chỉ `bind/read` lease (B §8.2).
- **Binding in-memory + snapshot before/after — MỞ (M2).** B trả `targets_before/after`, `window_set_changed` để caller phát hiện đổi tab/cửa sổ; C chưa có. Read-only M1 chưa cần, nhưng reconcile/publish M2 nên copy.

## 4. Lỗ hổng đã biết (không chặn M1, phải đóng trước publish-M2)

1. **`bind_profile` chưa check cùng-window.** B `verify_profile` đòi tab `chrome://version` có `targetId==profile_target_id` **cùng `windowId`** với tab FB (qua `Browser.getWindowForTarget`). C chỉ so `#profile_path` realpath — attacker/thao tác nhầm mở `chrome://version` ở window khác vẫn pass. M1 read-only chấp nhận; **M2 bắt buộc bổ sung window-check.**
2. **7 `account_providers` chưa đấu dây.** `_verify_actor` ưu tiên callback inject (test dùng), fallback `account_providers[platform]` — nhưng M1 chưa đăng ký provider thật nào (FB USER_ID, IG username+cookie, TikTok avatar... theo A §7.3). Không có provider → `ACCOUNT_VERIFIER_UNAVAILABLE` từ chối (fail-closed, đúng). **M2 đấu từng provider + test.**
3. **Chưa chạy trên Chrome thật.** M1 pass trên `FakePage`; `LeaseStore` SQLite là thật, rank/verify/disconnect là logic thật, nhưng transport CDP chưa từng chạy. **Trước M2 publish phải có 1 lần `ManagedChromeSession.open` + `acquire` + `read` trên Chrome remote-debugging thật.**
4. **Thiếu test `TabProtected`, TTL biên (`INVALID_LEASE_TTL`), `NO_MATCHING_TAB_AVAILABLE`.** Logic đã có, test chưa có — bổ sung M2.

## 5. Việc cần làm trước chữ ĐẠT M2 (publish)

1. Window-check trong `bind_profile` + test 2-window.
2. Đấu 7 account providers (A §7.3) + test từng loại mismatch.
3. Chuẩn hóa URL kiểu A (`_urls_same_destination`) + đường `create_tab` có guard cho publish.
4. Snapshot before/after + binding lifecycle (`BINDING_NOT_FOUND` → gắn lại).
5. 1 lần chạy thật trên Chrome remote-debugging (read-only trước, publish sau).

## 6. Connector DevToolsActivePort kiểu dubtool + luật 1-tab/platform (commit 87797d8, ngày 2026-11-21)

**Kết luận: ĐẠT** — kiểm tra độc lập bằng chạy lại test (phần mở: live Chrome thật chưa chạy).

- Đối chiếu mẫu `C:\dubtool\scripts\social_live_chrome.py:18-27` — ĐẠT: `chrome_endpoint` đọc `<user_data_dir>/DevToolsActivePort` (trống → `%LOCALAPPDATA%\Google\Chrome\User Data`), dòng 1 = port (1–65535), dòng 2 = route `/devtools/browser/<id>` (regex fullmatch giống mẫu), ghép `ws://127.0.0.1:{port}{route}`; file thiếu/sai → `CDP_UNAVAILABLE` kèm hướng dẫn bật Allow remote debugging ở `chrome://inspect`, không tự mở Chrome. Thêm `endpoint=` passthrough (Chrome mở cờ remote-debugging riêng thì dùng thẳng) — mở rộng hợp lệ, không lệch mẫu mặc định.
- Luật 1-tab/platform — ĐẠT: `register_live_tab` ưu tiên tab open cùng browser+profile+platform (reused, không đăng ký tab thứ 2 kể cả khi URL khác); chưa có tab → `TAB_REQUIRED_OPEN_FIRST` (mở tab trước, không tự `new_page`/`goto`); `acquire_tab` thiếu tab cũng `TAB_REQUIRED_OPEN_FIRST`, không navigate.
- Lệnh: `python -m pytest tests/test_chrome_single_tab.py tests/test_live_chrome_readonly.py -q` trong `C:\Miro\apps\backend` → **11 passed** (8 endpoint/single-tab + 3 readonly có sẵn; fake hoàn toàn, không Chrome/CDP thật).
- Phần mở: chưa chạy `ManagedChromeSession.open` + `acquire` + `read` trên Chrome remote-debugging thật (live thật chưa chạy).

## 7. P0 tab: targetId CDP thật, chuẩn hóa URL, protected-continue (commit ee2b615, ngày 2026-11-21)

**Kết luận: ĐẠT** — kiểm tra độc lập bằng đọc diff + đối chiếu A + chạy lại test.

- Đối chiếu A (`C:\dubtool\core\browser_runtime.py`) — ĐẠT từng điểm:
  - `_target` (`:70-75`): A mở CDP session trên context + `Target.getTargetInfo` → `targetInfo`. C (`live_chrome._cdp_target_id`) cùng thứ tự: attr/callable `target_id` trên page trước (fake/test passthrough, không tốn CDP) → `context.new_cdp_session(page)` + `Target.getTargetInfo` → `""` (caller fallback key ổn định `live-<id(page)>`); `detach` trong `finally`, lỗi nuốt có scope. Khác chữ ký (A là method `_target(context, page)`, C là hàm `_cdp_target_id(session, page)` quét contexts chứa page) nhưng cùng ngữ nghĩa — chấp nhận, đã ghi rõ trong docstring.
  - `_urls_same_destination` (`:27-37`): C copy đúng logic A — scheme/host/port + path strip `/` cuối + query trừ tracking so bằng nhau, parse lỗi → `False`. `_IGNORED_QUERY_KEYS` trùng A từng key (`fbclid`, `utm_*` ×5, `_rdc`, `_rdr`). Áp dụng đúng 5 chỗ: `register_live_tab` match + revalidate, `acquire_tab` rank/exact + `needs_nav`, `read_tab` origin + mid-read. Đóng nợ mục 3 §5 (chuẩn hóa URL kiểu A).
  - `saw_protected` + `continue` (`:690-691`): C copy đúng — candidate protected (upload/dirty/flagWatch) cần navigate → release lease, `saw_protected=True`, `continue` (không raise sớm); hết vòng mới raise `TabProtected`. Test mới chứng minh không dừng sớm (`TAB_ORIGIN_CHANGED` ở candidate sau, không phải `TabProtected`) + raise sau vòng khi tất cả protected.
- `register_live_tab` thành async — ĐẠT có ghi nhận: đổi chữ ký do `await _cdp_target_id`; đã sửa cả 2 callsite (`read_url_once` + tests), không còn caller sync cũ. Khác nhỏ vs A: fallback `live-<id(page):x>` khi CDP không trả targetId (A luôn có targetId thật từ CDP) — chỉ xảy ra khi CDP lỗi, key ổn định theo object, chấp nhận.
- Lệnh: `python -m pytest tests/test_chrome_single_tab.py tests/test_browser_single_owner.py tests/test_live_chrome_readonly.py -q` trong `C:\Miro\apps\backend` → **25 passed** (3 file, fake hoàn toàn, không Chrome/CDP thật).
- Phần mở (từ mục 4–5 reread, còn nguyên): window-check `bind_profile` (§4.1), 7 `account_providers` chưa đấu (§4.2), chưa chạy Chrome remote-debugging thật (§4.3/§5.5); cộng thêm: fallback `live-<id>` chưa từng chạy CDP thật nên chưa biết tần suất fallback trên Chrome thật.

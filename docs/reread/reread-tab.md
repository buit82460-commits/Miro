# Reread TAB: luật 1-tab A (dubtool) vs port C (Miro) — 2026-11-21

Nguồn A: `C:\dubtool\core\tab_acquisition.py` (toàn bộ, 192 dòng),
`C:\dubtool\core\browser_runtime.py` (`acquire_tab` L610-753, `create_tab`
L557-608, `bind_profile` L94-108, `inventory` L80-92),
`C:\dubtool\scripts\social_live_chrome.py:18-27` (`chrome_endpoint`).
Nguồn C: `C:\Miro\apps\backend\src\miro\browser\runtime.py` (507 dòng),
`live_chrome.py` (210 dòng) hiện trạng.

## 1. Luật 1-tab A thực thi thế nào

**Mở khi nào:** `acquire_tab` chỉ tạo tab mới khi TẤT CẢ concurrent-safe
candidate đã thử hết: skip leased (`active_leases` → `saw_busy`), validate
live (`_validate`: target identity + window thuộc profile + same-origin),
`_inspect_page_state` (upload/file-input/progress/dirty-form/contenteditable/
beforeunload), `_navigation_breaks_flag` (flagWatch origin/pathPrefix/selector
+ `_PROTECTED_FLAGS` = CHAT_WATCH/FLAG_WATCH/LIVE_UPLOAD/DIRTY_FORM).
Hết candidate mà `saw_busy` → `LeaseBusy TAB_BUSY` (không tạo trùng);
`allow_create=False` → `TAB_PROTECTED_NO_NAVIGATE` / `NO_MATCHING_TAB_AVAILABLE`;
còn lại `create_tab` với `creationReason` (`no_matching_tab` hoặc
`protected_existing_tab_preserved`), lease ngay tab mới, `reused=False`.
`create_tab` neo anchor = evidence target cùng `windowIds`, `Target.createTarget`
`about:blank` cùng `browserContext`, tab mới lọt khác window → đóng ngay +
`NEW_TAB_PROFILE_UNVERIFIED`.

**Cấm khi nào:** tab khớp đang leased → TAB_BUSY (tuyệt đối không duplicate);
tab cần navigate mà vướng upload/form-dirty/flag-watched → bỏ qua candidate
(`saw_protected`, thử tiếp), không navigate đè; `PROFILE_UNVERIFIED` khi thiếu
bằng chứng `chrome://version` + `#profile_path` khớp (không suy đoán từ
default-context); `TAB_ORIGIN_CHANGED` khi URL đổi origin (invalidate task
binding); resume chỉ đúng `targetId` đã ghi — URL khớp ở tab người khác
không cho gì.

**Xếp hạng reuse:** exact_url (chuẩn hóa `_urls_same_destination`: strip `/`
cuối + bỏ query tracking `fbclid/utm_*`) > exact_channel > flag_match >
khác, rồi `lastUsedAt` cũ nhất. Reuse thì gắn `channelId/taskId/flag`,
`lastUsedAt=now`, lease mới TTL 1–1800s.

**Endpoint:** `chrome_endpoint` đọc `<User Data>/DevToolsActivePort` (dòng 1
port, dòng 2 route `/devtools/browser/...` → `ws://127.0.0.1:{port}{route}`);
sai/thiếu → lỗi hướng dẫn bật Allow remote debugging. Không launch Chrome.

## 2. C port được / mất / sai chỗ nào

**Được:** `chrome_endpoint` đúng pattern A (+ fallback endpoint, fail-closed
`CDP_UNAVAILABLE`); `bind_profile` verify `chrome://version` không fallback;
1 `connect_over_cdp`/batch (assert CONNECT_ONCE); rank 4 tầng + `TabBusy`
không tạo trùng; verify actor trước+sau read; lease fence; `WorkerStopped`
khi mất lease; `close()` = disconnect CDP, không tắt Chrome. `release()` C
chỉ nhả lease (A đánh `runtime.closed=True` — C đúng hơn cho runtime chung).

**Mất (chính sách read-only có chủ ý, cần ghi rõ):** C không có
`allow_create`/`navigate_if_needed` — hết candidate → `TAB_REQUIRED_OPEN_FIRST`
(mở tay trước, cấm `new_page`/navigate). Reuse cross-URL bị `TAB_ORIGIN_CHANGED`
thay vì navigate tới như A. Không có `task()`/resume-binding flow, không lọc
`ownerTaskId`. `AcquiredTab` C thiếu `tab_count_before/after`,
`creation_reason`, `channel_id`.

**Sai — bug gốc cần sửa/tối ưu (theo mức độ):**

1. `register_live_tab` (live_chrome.py:101-115) tự chế `target_id =
   "live-{index}"` theo thứ tự `enumerate` thay vì CDP `targetId` thật
   (A: `Target.getTargetInfo`). Thứ tự pages đổi → cùng page vật lý đăng ký
   2 key khác nhau, store mất liên kết CDP. **Sửa:** lấy targetId thật qua
   CDP session như A `_target()`.
2. So sánh URL string exact 3 nơi (C `acquire_tab` rank/needs_nav L338/370,
   `register_live_tab` L103, `read_tab`/`navigate_tab` origin check) — không
   chuẩn hóa như `_urls_same_destination` (A bỏ `utm_*/fbclid`, strip `/`).
   Cùng trang khác query tracking → coi là khác → `TAB_ORIGIN_CHANGED` /
   `TAB_REQUIRED_OPEN_FIRST` sai. **Sửa:** port `_urls_same_destination` +
   `_IGNORED_QUERY_KEYS`.
3. `acquire_tab` C gặp protected candidate thì `raise TabProtected` ngay
   (L376) — A là `saw_protected → continue` thử candidate khác. C hung hơn A,
   bỏ sót tab reuse được. **Sửa:** continue + nhớ cờ, raise sau vòng lặp.
4. `_inspect_page_state` C rút gọn (L257-276): mất check upload-progress
   (`progress/[role=progressbar]/data-dubtool-uploading`), dirty
   textarea/input (value vs default), dirty contenteditable, `__dubtoolDirty`
   dataset. Form đang soạn không phát hiện → `navigate_tab` navigate đè.
   **Sửa:** port nguyên bản JS A (L424-476).
5. C không check `windowIds` (A: `_observe`/`_validate`/`_resolve_anchor` đều
   yêu cầu target cùng window set của profile). Tab ngoài cửa sổ profile vẫn
   acquire được. **Sửa:** lưu `windowIds` khi bind (cần CDP
   `Browser.getWindowForTarget`), check khi acquire/validate.
6. C chặn navigate khi `record.get("flagWatch")` truthy bất kể URL (L373/428);
   A `_navigation_breaks_flag` miễn khi cùng destination + xét
   origin/pathPrefix/selector. C từ chối cả navigate hợp lệ. **Sửa:** port
   `_navigation_breaks_flag`.
7. `read_url_once` cứng `allowed_origins=(THREADS_ORIGIN,)` + mặc định
   `flag="PUBLISH"` cho caller read-only — không sai hành vi hiện tại nhưng
   dễ copy-paste sai khi mở platform khác; origin-based policy khác mô hình
   platform-registered-URL của A (`require_url`). Ghi rõ khi mở rộng.

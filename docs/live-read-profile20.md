# Live-read Profile 20 — runbook (read-only)

Connector: `apps/backend/src/miro/browser/live_chrome.py`
Entry point: `read_url_once(...)` / CLI `python -m miro.browser.live_chrome`

## 0. Nguyên tắc

- KHÔNG tự ý mở Chrome. Chrome phải do người dùng mở sẵn với
  remote-debugging; connector chỉ `connect_over_cdp` đúng 1 lần.
- KHÔNG post/navigate/tạo tab. Module này không chứa `post_once`,
  `submit(`, hay `page.goto`. Tab chứa bài Threads phải mở sẵn.
- Verify 2 lớp của runtime: bind profile qua `chrome://version`
  (`#profile_path` khớp `<user-data-dir>/Profile 20`) + verify actor
  (`threads_actor`: `@username` trên URL bài == expected account).

## 1. Chuẩn bị Chrome (người dùng làm thủ công)

1. Tắt hết Chrome đang chạy.
2. Mở Chrome Profile 20 với remote-debugging, ví dụ:
   `chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\ChromeDebug"`.
3. Trong đúng cửa sổ Profile 20, mở 2 tab:
   - `chrome://version` (để bind profile lấy `#profile_path`)
   - URL bài Threads cần đọc, ví dụ bài `#dub417888`.
4. Đăng nhập sẵn Threads `@haodaojrk5` trong profile này (connector không
   login, không đọc cookie ra ngoài).

## 2. Chạy live-read (chỉ đọc)

```bat
cd C:\Miro\apps\backend
python -m miro.browser.live_chrome ^
  --url "https://www.threads.com/@haodaojrk5/post/dub417888" ^
  --user-data-dir "C:\ChromeDebug" ^
  --expected-account haodaojrk5
```

Kết quả: in `URL / ACCOUNT / TITLE / TEXT` ra stdout, rồi disconnect CDP
(không tắt Chrome). Lỗi thường gặp:

| Lỗi | Nghĩa | Cách xử lý |
|---|---|---|
| `CDP_UNAVAILABLE` | Chrome chưa bật remote-debugging | Mở lại Chrome đúng bước 1–2, không retry loop |
| `PROFILE_UNVERIFIED` | Tab `chrome://version` không ở Profile 20 | Mở tab đó trong đúng cửa sổ Profile 20 |
| `ACCOUNT_MISMATCH` | `@username` trên tab ≠ expected | Kiểm tra đăng nhập đúng acc / sửa `--expected-account` |
| `NO_MATCHING_TAB_AVAILABLE` | Chưa mở sẵn URL bài | Mở sẵn bài trong Profile 20 rồi chạy lại |
| `PLAYWRIGHT_MISSING` | Chưa cài playwright (test fake vẫn pass) | `pip install playwright` — chỉ cần cho live |

## 3. Test fake (không cần Chrome, CI)

```bat
cd C:\Miro\apps\backend
python -m pytest tests/test_live_chrome_readonly.py tests/test_threads_publish_http.py -q
```

## 4. Phần mở (chưa làm)

- `workers/browser/worker.py` vẫn là skeleton `run()` NotImplemented —
  chưa nối vào ManagedChromeSession.
- Connector hiện tại chỉ hỗ trợ read 1 URL; chưa có watch/poll, chưa
  verify actor qua DOM (mới qua URL) — cần bổ sung khi live thật.
- Playwright chưa có trong môi trường (`pip` thiếu module) — live-read thật
  cần cài thêm, test fake không phụ thuộc.

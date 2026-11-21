# Miro — Agent Rules (đọc trước mọi task)

## 1. Chrome Profile Rule (cứng)

- Khi user nói **"bật 20"** / **"mở 20"**: mở cửa sổ Chrome dùng `Profile 20`.
- Khi user nói **"vào [nền tảng]"**: mở trang đó bằng `Profile 20` mặc định.
- Nếu user chỉ định số profile khác → dùng số user vừa nói.
- `FB` = Facebook. Nếu user đưa URL → dùng nguyên URL đó.
- Tên nền tảng chưa rõ → hỏi lại tên hoặc đường dẫn, không đoán.
- Chạy lệnh trực tiếp bằng PowerShell trên Windows. **Giữ nguyên các cửa sổ
  đang mở** — không `taskkill`, không đóng Chrome của user.
- Yêu cầu chỉ mở trang → **bỏ qua cổng 9222**, không bật remote debugging.

### Lệnh mẫu

```powershell
# Bật 20
& 'C:\Program Files\Google\Chrome\Application\chrome.exe' '--profile-directory=Profile 20' '--new-window' 'chrome://newtab/'

# Vào FB (= mở Facebook bằng 20)
& 'C:\Program Files\Google\Chrome\Application\chrome.exe' '--profile-directory=Profile 20' 'https://www.facebook.com/'

# Vào TikTok bằng 20
& 'C:\Program Files\Google\Chrome\Application\chrome.exe' '--profile-directory=Profile 20' 'https://www.tiktok.com/'

# Mở YouTube bằng 7
& 'C:\Program Files\Google\Chrome\Application\chrome.exe' '--profile-directory=Profile 7' 'https://www.youtube.com/'
```

- "bật 20 vào FB" = chạy đúng 1 lệnh dòng "Vào FB" (vừa chọn Profile 20
  vừa mở Facebook).

## 2. Remote debugging (chỉ khi cần điều khiển)

- Chỉ bật `--remote-debugging-port=9222` khi task yêu cầu agent điều khiển
  Chrome (live-read, verify, adapter).
- Từ Chrome 136: debug port yêu cầu user-data-dir không phải mặc định.
  Mở debug = restart Chrome 1 lần, cần user đồng ý trước.
- File mở nhanh Profile 20 + debug: `Miro-Chrome-Profile20.bat`.

## 3. Quy trình code (Miro)

- Mỗi feature: 2 reader đọc trước → agent viết code → Checker duyệt ĐẠT
  mới commit → push. Không commit gộp khi chưa ĐẠT.
- `docs/ba-ben/` là ngoài luồng: đọc/ghi tự do, KHÔNG bao giờ
  `git add/commit/push` thư mục này.
- Test backend: `python -m pytest tests -q` trong `C:\Miro\apps\backend`.
- An toàn: UNKNOWN không replay, publication + journal là source of truth,
  dry-run mặc định, post thật cần approval + fingerprint + revision.

# Quy ước làm việc trong Miro

## Quyền thực thi theo task

- Bắt buộc xác định quyền từ yêu cầu hiện tại và các xác nhận còn hiệu lực của cùng task.
- Nếu người dùng nói "cho phép làm full quy trình từ A -> Z không cần hỏi", "tự làm toàn bộ",
  hoặc câu tương đương rõ nghĩa: thực hiện liên tục khảo sát → sửa → kiểm thử → cập nhật
  tài liệu → bàn giao trong phạm vi task; không hỏi lại các bước đã được cho phép.
- Nếu không có ủy quyền tương đương: được đọc và khảo sát để chuẩn bị phương án cụ thể,
  nhưng bắt buộc hỏi và chờ xác nhận trước khi sửa file, chạy lệnh thực thi/kiểm thử,
  cài đặt, khởi động/dừng dịch vụ hoặc thao tác bên ngoài. Sau xác nhận, làm đúng phạm
  vi đã duyệt; không hỏi lại từng lệnh thuộc phạm vi đó. Lệnh chỉ đọc phục vụ khảo sát
  không cần hỏi. Yêu cầu chỉ giải thích/đọc/review được trả lời trực tiếp.
- Quyền A–Z chỉ áp dụng cùng task, không là quyền vĩnh viễn cho task mới; không tự
  replay publication UNKNOWN. Luôn tuân thủ giới hạn hệ thống, sandbox và hộp duyệt lệnh;
  không lách hoặc hứa loại bỏ các cơ chế này.

## Quy tắc Chrome profile (cứng)

- User nói **"bật 20"** / **"mở 20"**: mở cửa sổ Chrome dùng `Profile 20`.
- User nói **"vào [nền tảng]"**: mở trang đó bằng `Profile 20` mặc định.
- User chỉ định số profile khác → dùng số user vừa nói.
- `FB` = Facebook. User đưa URL → dùng nguyên URL đó.
- Tên nền tảng chưa rõ → hỏi lại tên hoặc đường dẫn, không đoán.
- Chạy lệnh trực tiếp bằng PowerShell trên Windows. **Giữ nguyên các cửa sổ
  đang mở** — không `taskkill`, không đóng Chrome của user.
- Yêu cầu chỉ mở trang → **bỏ qua cổng 9222**, không bật remote debugging.

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

- "bật 20 vào FB" = chạy đúng 1 lệnh dòng "Vào FB".
- Remote debugging (`--remote-debugging-port=9222`) chỉ khi task yêu cầu agent
  điều khiển Chrome. Từ Chrome 136 cần user-data-dir không mặc định + user
  đồng ý restart trước. File mở nhanh: `Miro-Chrome-Profile20.bat`.

## Yêu cầu đăng bài và điều kiện hoàn thành

- Khi người dùng trực tiếp yêu cầu "đăng lên", "đăng video/bài" hoặc câu tương đương,
  đó là xác nhận thực hiện bước đăng thật trong phạm vi yêu cầu; không hỏi lại
  "có đăng không?". Task chỉ HOÀN THÀNH khi đủ số video/bài đã đăng lên đúng nền tảng,
  đúng tài khoản, đúng nội dung và chế độ xem, có bằng chứng đọc lại (URL/ID bài).
- Nếu bị chặn (đăng nhập, quyền, công cụ, thiếu bằng chứng): giữ task CHƯA HOÀN THÀNH,
  báo chính xác đã làm đến đâu + điều kiện tiếp tục. Không thay kết quả bằng bản nháp.
- UNKNOWN sau Post vẫn là CHƯA XÁC MINH, phải đối soát trước; không đăng lại để
  đạt số lượng.

## Bootstrap đầu phiên và đọc theo nhu cầu

1. Xác nhận đang ở `C:\Miro`. Đọc `docs/verify-threads-loop.md` và
   `docs/verify-foundation.md` TRƯỚC TIÊN để biết việc nào ĐẠT/CHƯA (mục mới nhất
   trước), rồi mới đọc `docs/reread-foundation.md` và `docs/crosscheck-foundation.md`;
   không đọc lại nếu đã đọc trong phiên và nội dung không đổi.
2. Kiểm tra `git status --short` nếu được; nếu không phải Git repository, ghi rõ,
   không tự git init/clone/reset. Dùng tìm kiếm có phạm vi, đọc đoạn liên quan và
   đối chiếu thay đổi trực tiếp. Không tự quét toàn bộ source hoặc mọi Markdown.
3. Chỉ khi cần tổng quan đọc `README.md`; kiến trúc đọc source trực tiếp theo task;
   quyết định đọc `docs/crosscheck-foundation.md`. Tra cứu quy trình 3-agent
   (2 reader → code → Checker ĐẠT mới commit → push): `docs/ba-ben/`.
4. Theo task, chọn module từ source, tìm symbol bằng grep và đọc source/test
   liên quan. Tài liệu là chỉ dẫn; code và bằng chứng hiện tại quyết định kết luận.
5. `docs/ba-ben/` là ngoài luồng: đọc/ghi tự do, KHÔNG bao giờ
   `git add/commit/push` thư mục này. Mọi file hỏi-đáp trong đó phải có đủ
   slot A/B/C (ghi "không có" nếu trống).
6. Miro và `C:\dubtool` / `D:\JARVIS-Assistant` là hệ thống riêng; chỉ đọc/chỉnh
   khi task có phạm vi tương ứng. C là điểm hợp nhất, dubtool/JARVIS là nguồn feature.

## Quy chuẩn platform (Threads/FB/YT/TikTok/platform mới)

- Mỗi platform có đúng 1 adapter được duy trì. Muốn đăng lên platform nào thì chỉ gọi
  adapter của platform đó. CẤM tạo script mới cho từng batch/account/video.
  Thêm platform mới = tạo 1 adapter theo mẫu hiện có và đăng ký; không đăng ký
  thì không dùng cho production.
- Guard chống trùng trước mọi lần Post: đã có trong publication → skip; đã có
  attempt journal → chỉ reconcile, KHÔNG replay UNKNOWN. Caption/account lấy
  từ manifest, không hard-code trong script.
- Mỗi tài nguyên điều khiển (file lệnh, tab, browser session) có đúng 1 owner
  tại một thời điểm (lock liên tiến trình). 1 tab/platform, reuse tab có sẵn,
  không tự tạo tab thứ 2.
- Runtime chỉ gọi adapter đã kiểm thử, không tự sửa source khi batch production
  đang chạy.

## An toàn nguồn thật (source of truth)

- Publication + journal là source of truth, không suy đoán trạng thái đăng.
- Dry-run mặc định; post thật cần approval bound fingerprint + revision.
- Eye = mắt duy nhất (locator hẹp, post_id-first, tag 6 số); adapter/page chỉ
  truyền page handle + nhận records, không tự chạy locator.
- Test backend: `python -m pytest tests -q` trong `C:\Miro\apps\backend`.

## Kết thúc task có thay đổi đáng kể

- Ghi kết quả verify vào `docs/verify-threads-loop.md` hoặc
  `docs/verify-foundation.md` (chọn file phù hợp, bổ sung gọn): ĐẠT/CHƯA ĐẠT +
  lệnh + kết quả. Commit, KHÔNG push (push sau khi user hoặc Checker xác nhận).
- Giữ verify ngắn; dẫn tới chi tiết, không chép lại lịch sử.
- Phân biệt kiểm chứng fixture/local/production; không ghi thành công thiếu bằng chứng.

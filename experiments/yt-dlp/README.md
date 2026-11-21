# Spike: yt-dlp (tải video công khai, không đăng nhập)

## Mục tiêu

Chứng minh tải 1 video TikTok công khai bằng `yt-dlp` mà không cần
đăng nhập, không cookie profile: metadata trước (1 request), tải thật
sau, ghi báo cáo JSON (định dạng, dung lượng, độ phân giải, thời gian).

Nguồn: `D:\JARVIS-Assistant\spikes\yt_dlp\run.py` (port gọn).

## Kết quả: GIỮ (có điều kiện)

- Legacy: script 2 bước `extract_info(download=False)` rồi
  `extract_info(download=True)`, outtmpl `%(id)s.%(ext)s`,
  không request dồn, lỗi rate-limit/CAPTCHA thì dừng (không vòng vo).
- Tiêu chí đạt: file thật, phát được, đọc được thông số.
  Chưa kiểm chứng lại trong Miro — cần chạy thử 1 URL công khai.

## Quyết định

**GIỮ có điều kiện.** Chỉ dùng cho nguồn công khai phục vụ kiểm thử
media pipeline. Không dùng để cào hàng loạt, không vượt xác thực.

## Ảnh hưởng code chính

- `workers/media/` — logic tải nguồn (format `bv*+ba/b`, outtmpl theo id,
  báo cáo JSON) là tham chiếu khi worker media cần bước "tải nguồn".
  Hiện tại worker là khung → **chưa ảnh hưởng**.
- `services/youtube/` — không ảnh hưởng (upload là chiều ngược lại).
- Không ảnh hưởng `apps/`, `contracts/`.
- Tuân thủ quy tắc Instagram trong dubtool: URL profile không đưa thẳng
  cho yt-dlp; chỉ tải từng URL media cụ thể.

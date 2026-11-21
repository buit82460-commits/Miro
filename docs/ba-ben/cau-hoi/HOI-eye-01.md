# HỎI-eye-01: collect_post_records chạy trên DOM Threads hiện tại còn đúng selector không

## Câu hỏi (bên hỏi: C)

- Khâu: mắt–não
- File C đang port: `apps/backend/src/miro/publishing/publisher.py` (`match_eye_records`), sắp port `collect_post_records`
- File A/B gốc: `C:\dubtool\core\rea_eye.py` (locator `/post/`, `/t/`, TAG_RE)
- Hỏi gì: A ghi B4 locator hẹp + B3 TAG_RE không boundary. Hỏi A: DOM Threads hôm nay (11/2026) còn selector nào khác chứa bài? Có nên mở rộng locator hay giữ hẹp để tránh false-positive? Tag `#dub\d+` A chốt đúng 6 số — bài tag ngắn/dài hơn xử lý sao?

## Trả lời

- Bên trả lời (A/B/C):
- Đáp + bằng chứng file:dòng:
- Kết luận port thế nào:

## Trạng thái

- [x] Đang hỏi
- [ ] Đã đáp, chờ port
- [ ] Đã port + test, chờ Checker
- [ ] XONG

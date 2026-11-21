# HỎI-publisher-01: deferred sau điểm dừng có cần reconcile trước khi post lại không

## Câu hỏi (bên hỏi: C)

- Khâu: publisher
- File C đang port: `apps/backend/src/miro/publishing/publisher.py` (`run_batch`, commit `f09e377`)
- File A/B gốc: `C:\dubtool\scripts\threads_post_one.py:840-856`
- Hỏi gì: C sửa deferred không journal để batch sau post lại được (Checker đã duyệt ĐẠT `502dade`). Hỏi A: item deferred ở batch sau post thẳng hay phải qua reconcile/verify gì trước? Có trường hợp nào deferred nhưng thực tế đã post (ack mất) mà A từng gặp không?

## Trả lời

- Bên trả lời (A/B/C):
- Đáp + bằng chứng file:dòng:
- Kết luận port thế nào:

## Trạng thái

- [x] Đang hỏi
- [ ] Đã đáp, chờ port
- [ ] Đã port + test, chờ Checker
- [ ] XONG

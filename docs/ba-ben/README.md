# Trao đổi 3 bên: Dubtool (A) + JARVIS (B) → Miro (C)

Mục đích: bên nào rõ bên đó nhất. A/B đọc – hỏi – đáp thẳng vào đây để C port đúng luật merge
(đọc mã thật → giữ đủ khả năng → port sang kiến trúc C → kiểm chứng luồng thật, không copy để đấy).

## Quy ước

- Mỗi câu hỏi 1 file trong `cau-hoi/` theo mẫu `HỎI-<khâu>-<số>.md`.
- Trả lời viết tiếp vào cùng file mục `## Trả lời`, ghi rõ bên trả lời (A/B/C) + file:dòng bằng chứng.
- Cấm secret/cookie/token. Chỉ dẫn file:dòng + hành vi.
- Khi thống nhất xong, C port code + test, Checker duyệt rồi mới đóng câu hỏi (đổi tên `XONG-...`).

## Khâu đang mở

| Khâu | File đọc lại | Đối chiếu | Trạng thái P0 |
|---|---|---|---|
| Mắt–não | `docs/reread-eye.md` | `docs/crosscheck-eye.md` | đang sửa `collect_post_records` |
| Tab | `docs/reread-tab.md` | `docs/crosscheck-tab.md` | xong `ee2b615`, chờ verify |
| Publisher | `docs/reread-publisher.md` | `docs/crosscheck-publisher.md` | ĐẠT journal `502dade` |
| Studio | `docs/reread-studio.md` | `docs/crosscheck-studio.md` | chờ P1 |
| Nền | `docs/reread-foundation.md` | `docs/crosscheck-foundation.md` | đang sửa T1–T4 |

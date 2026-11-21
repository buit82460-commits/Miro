# Trao đổi 3 bên: Dubtool (A) + JARVIS (B) → Miro (C)

Mục đích: bên nào rõ bên đó nhất. A/B đọc – hỏi – đáp thẳng vào đây để C port đúng luật merge
(đọc mã thật → giữ đủ khả năng → port sang kiến trúc C → kiểm chứng luồng thật, không copy để đấy).

## Cấu trúc

- `dubtool/` — nhà riêng A: A tự đọc C, tự viết ý kiến vào `y-kien/YK-A-<số>.md`.
- `jarvis/` — nhà riêng B: B tự đọc C, tự viết ý kiến vào `y-kien/YK-B-<số>.md`.
- `miro/` — nhà C: nơi C đáp + port + kiểm chứng.
- `chu-de/` — 5 file chủ đề chung, **cả 3 cùng viết vào 3 mục A/B/C**: `TD-mat-nao.md`, `TD-tab.md`, `TD-publisher.md`, `TD-studio.md`, `TD-nen.md`.
- `cau-hoi/` — câu hỏi lẻ 1-1 (C hỏi A/B hoặc ngược lại) theo mẫu `MAU-CAU-HOI.md`.
- `y-kien/` — ý kiến lẻ từng nhà chưa thành chủ đề.

## Quy ước

- Mỗi file chủ đề/ý kiến có 3 mục A/B/C hoặc mục Trả lời — bên nào viết ghi tên bên đó.
- Mọi ý kiến ghi file:dòng làm bằng chứng. Cấm secret/cookie/token.
- Đóng chủ đề/câu hỏi chỉ khi port + test + Checker duyệt (đổi tên `XONG-...`).

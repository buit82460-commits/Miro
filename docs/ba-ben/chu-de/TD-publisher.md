# Chủ đề PUBLISHER: batch two-phase + journal + scheduler

Luật: journal trước click, UNKNOWN không replay, guard 2 lớp, Threads không qua submit_studio.
Đọc lại: `docs/reread-publisher.md` · Đối chiếu: `docs/crosscheck-publisher.md` · P0 ĐẠT: journal `502dade`.

## A (Dubtool) nói

- (A viết vào đây: deferred post thẳng hay reconcile trước, ack mất, `_extract_post_codes` chết, scheduler slot/carryover...)

## B (JARVIS) nói

- (B viết vào đây: approval gate, REQUEST_ID_CONFLICT, receipt non-blocking...)

## C (Miro) nói

- C sửa deferred không journal (ĐẠT). Còn thiếu: cả `posting_schedule.py`. P1 sẽ port scheduler + nối caller.
- Câu hỏi chi tiết: `cau-hoi/HOI-publisher-01.md`.

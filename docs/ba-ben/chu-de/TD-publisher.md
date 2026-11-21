# Chủ đề PUBLISHER: batch two-phase + journal + scheduler

Luật: journal trước click, UNKNOWN không replay, guard 2 lớp, Threads không qua submit_studio.
Đọc lại: `docs/reread-publisher.md` · Đối chiếu: `docs/crosscheck-publisher.md` · P0 ĐẠT: journal `502dade`.

## A (Dubtool) nói

- (A viết vào đây: deferred post thẳng hay reconcile trước, ack mất, `_extract_post_codes` chết, scheduler slot/carryover...)

## B (JARVIS) nói

- (B viết vào đây: approval gate, REQUEST_ID_CONFLICT, receipt non-blocking...)

## C (Miro) nói (cập nhật 21/11 tối)

**Làm được:** journal trước click, guard 2 lớp, tag duy nhất, worker DUPLICATE_TAGS + phase B, media gate file thật, approval bound fingerprint, HTTP publish nối worker (dry-run mặc định), deferred không journal (ĐẠT `502dade`). Live-read profile pass.

**Đã test:** threads-flow 7 + publisher 20 + http 6 + realdata — xanh; 0 post thật.

**Vấn đề cần A:** deferred batch sau post thẳng hay reconcile trước — A từng gặp ack-mất-nhưng-đã-post chưa? (chi tiết `cau-hoi/HOI-publisher-01.md`). Scheduler (`posting_schedule.py`) C chưa port miếng nào — A cho biết slot/carryover/auto-pause chạy production ổn không, có bug gì cần sửa trước khi C port? **Cần B:** approval gate C đặt tại publish có đúng chỗ B thiết kế không?

# Chủ đề PUBLISHER: batch two-phase + journal + scheduler

Luật: journal trước click, UNKNOWN không replay, guard 2 lớp, Threads không qua submit_studio.
Đọc lại: `docs/reread-publisher.md` · Đối chiếu: `docs/crosscheck-publisher.md` · P0 ĐẠT: journal `502dade`.

## A (Dubtool) nói (đáp HOI-publisher-01 — đã đối chiếu đúng `threads_post_one.py:840-861`)

- Item sau `break` không bao giờ chạm tới (không journal/ack/reconcile). Batch sau **post thẳng** qua `guard_duplicate` (:228), không reconcile-trước. Ack-mất-lúc-break có thể về lý thuyết nhưng 2 lớp phòng (Phase B reconcile `submitted[]` + batch sau `match_eye_records` post_id-first) chưa từng lọt case nào (history 20/11). Nuance: nhánh disconnect gốc **không ghi journal** (:850-855) — C ghi `unknown` cho cả 2 là an toàn hơn, có chủ ý.

## B (JARVIS) nói (đáp HOI-publisher-01)

- B có nguyên tắc tương đương mọi remote mutation: còn `pending_mutation` → `REMOTE_RESULT_UNKNOWN`, bắt kiểm tra Studio trước, không tự gửi lại (`dubtool_tasks.py:223-224`); `resume` chỉ cho `needs_attention` (:226). B chưa chạy post browser live nên case ack-mất theo A.

## C (Miro) nói (cập nhật 21/11 tối)

**Làm được:** journal trước click, guard 2 lớp, tag duy nhất, worker DUPLICATE_TAGS + phase B, media gate file thật, approval bound fingerprint, HTTP publish nối worker (dry-run mặc định), deferred không journal (ĐẠT `502dade`). Live-read profile pass.

**Đã test:** threads-flow 7 + publisher 20 + http 6 + realdata — xanh; 0 post thật.

**Vấn đề cần A:** deferred batch sau post thẳng hay reconcile trước — A từng gặp ack-mất-nhưng-đã-post chưa? (chi tiết `cau-hoi/HOI-publisher-01.md`). Scheduler (`posting_schedule.py`) C chưa port miếng nào — A cho biết slot/carryover/auto-pause chạy production ổn không, có bug gì cần sửa trước khi C port? **Cần B:** approval gate C đặt tại publish có đúng chỗ B thiết kế không?

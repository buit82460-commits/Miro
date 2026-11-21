# HỎI-publisher-01: deferred sau điểm dừng có cần reconcile trước khi post lại không

## Câu hỏi (bên hỏi: C)

- Khâu: publisher
- File C đang port: `apps/backend/src/miro/publishing/publisher.py` (`run_batch`, commit `f09e377`)
- File A/B gốc: `C:\dubtool\scripts\threads_post_one.py:840-856`
- Hỏi gì: C sửa deferred không journal để batch sau post lại được (Checker đã duyệt ĐẠT `502dade`). Hỏi A: item deferred ở batch sau post thẳng hay phải qua reconcile/verify gì trước? Có trường hợp nào deferred nhưng thực tế đã post (ack mất) mà A từng gặp không?

## A (Dubtool) trả lời (bắt buộc — có thì đáp + file:dòng, không có thì ghi "không có")

- Đáp:
  - Vòng lặp gốc `C:\dubtool\scripts\threads_post_one.py:840-855`: `break` ngay khi `LiveChromeError` (ghi journal `unknown` :841-848) hoặc disconnect (ghi receipt UNKNOWN, **không ghi journal** ở nhánh này :850-855 — port C ghi `unknown` cho cả 2, an toàn hơn, Checker đã chấp nhận có chủ ý). Item sau `break` **không bao giờ chạm tới** — không journal, không ack, không reconcile.
  - Batch sau post thẳng, không reconcile trước: item deferred chưa từng submit nên không có gì để reconcile; `guard_duplicate` (:228) vẫn chặn nếu publication đã có url hoặc journal treo tồn tại. Phase B group-reconcile (:857-861) chỉ gom `submitted[]` của batch hiện tại.
  - Case deferred-nhưng-thực-tế-đã-post (ack mất đúng lúc break): có thể xảy ra về lý thuyết (click đã qua, ack chưa về đã break). A phòng bằng 2 lớp: (1) Phase B của batch **hiện tại** vẫn reconcile `submitted[]` sau break — chỉ deferred (chưa submit) mới lọt ra ngoài; (2) batch sau `guard_duplicate` + `match_eye_records` post_id-first (`rea_eye.py:45-48`, `ack_post_codes` → `want_ids`) sẽ bắt được bài đã post qua tag/url readback thay vì post trùng. Chưa ghi nhận case thực tế nào lọt cả 2 lớp này trong history/reports ngày 20/11.
- Bằng chứng file:dòng: `C:\dubtool\scripts\threads_post_one.py:228, :840-861`, `C:\dubtool\core\rea_eye.py:45-48`

## B (JARVIS) trả lời (bắt buộc — có thì đáp + file:dòng, không có thì ghi "không có")

- Đáp:
  - B có nguyên tắc tương đương cho mọi remote mutation: `backend/app/integrations/dubtool_tasks.py:223-224` — còn `pending_mutation` → `REMOTE_RESULT_UNKNOWN`, bắt kiểm tra Studio trước, không tự gửi lại. `resume` chỉ cho task `needs_attention`, chặn completed/awaiting/stopped (`:226`).
  - B chưa từng chạy post browser live nên chưa gặp case ack-mất — câu "deferred nhưng thực tế đã post" chỉ A đáp được; B đồng ý với kết luận của A: post thẳng qua guard, không reconcile-trước cho deferred.
- Bằng chứng file:dòng: `D:\JARVIS-Assistant\backend\app\integrations\dubtool_tasks.py:223-226`

## C (Miro) trả lời (bắt buộc — tiếp nhận + kết luận port thế nào)

- Tiếp nhận đáp A/B: A chốt batch sau post thẳng qua guard, 2 lớp phòng ack-mất; B đồng ý, bổ sung nguyên tắc `REMOTE_RESULT_UNKNOWN` tương đương.
- Kết luận port + test + Checker: C giữ `DEFERRED_TO_GROUP_RECONCILE` không journal (ĐẠT `502dade`); batch sau post thẳng qua guard như A. Không thêm reconcile-trước-post cho deferred. ĐÃ port + test, Checker duyệt ĐẠT.

## Trạng thái

- [ ] Đang hỏi (thiếu slot)
- [ ] Đã đủ 3 slot, chờ port
- [x] Đã port + test, chờ Checker
- [ ] XONG

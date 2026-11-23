# Crosscheck reread-publisher.md (commit bbf0446) — kiểm độc lập

Ngày: 2026-11-21. Checker độc lập (không phải người viết reread).
Đối chiếu: `C:\dubtool\scripts\threads_post_one.py` + `C:\dubtool\core\posting_schedule.py`
với `C:\Miro` `apps/backend/src/miro/publishing/publisher.py` + `threads/worker.py` + `routers/threads.py`.

## Kết luận nhanh

- 3 tuyên bố chính (scheduler 0 match / bug P0 deferred-khóa-vĩnh-viễn / `_extract_post_codes` chết): **cả 3 ĐÚNG**.
- Không phát hiện mục nào SAI. Có 3 mục BỎ SÓT / cần làm rõ (chi tiết mục 4-6).

## 1. Scheduler 0 match — ĐÚNG

- `core/posting_schedule.py:38-128` có `build_slot_times`, `build_day_plan`, `due_slots`,
  `record_submit_unknown`, `consecutive_unknowns`, `should_auto_pause` — pure functions + clock injectable.
- Grep toàn `C:\Miro\apps\backend\src\miro` với `carryover|due_slots|should_auto_pause|daily_cap` → **0 match**.
- Router `/threads/publish` (`routers/threads.py:131-184`) chạy 1 intent/lần qua worker + `_FakePage`,
  không có khái niệm ngày/suất. Ghi nhận "thiếu chính số 1" là chính xác.

## 2. Bug P0 journal unknown chặn vĩnh viễn — ĐÚNG

- C `publisher.py:694-704`: khi `stopped=True`, các intent chưa submit vẫn bị ghi journal
  `status=unknown` + result `DEFERRED_TO_GROUP_RECONCILE`, nhưng Phase B (`:766-828`) chỉ
  reconcile danh sách `submitted` — deferred items không bao giờ được reconcile trong batch đó.
- `guard_duplicate` C (`publisher.py:399-403`): journal tồn tại → trả `UNRECONCILED_ATTEMPT`
  → batch sau từ chối post. Chuỗi khóa vĩnh viễn là thật.
- A (`threads_post_one.py:840-856`, `break`): item chưa attempt **không có journal**, batch sau
  thử lại bình thường. So sánh A/C chính xác.
- Sửa đề xuất (nhánh stopped không ghi `unknown`) đúng hướng.

## 3. `_extract_post_codes` chết — ĐÚNG

- A định nghĩa `_extract_post_codes` tại `threads_post_one.py:76`, nhưng grep `ack_post_codes`
  chỉ còn: khởi tạo `[]` ở `:365`, trả về ở `:471`, đọc ở `:833/:838/:1019` — **không có call site**
  nào gọi `_extract_post_codes`. `ack_post_codes` trong two-phase luôn `[]`.
- `run_reconcile` `:1019` đọc `known_ids` từ journal → luôn rỗng → nhánh post_id-first trong A
  thực tế chết, chỉ còn tag-match. Khuyến nghị "ghi rõ `known_ids` không đáng tin với journal A"
  là đúng.

## 4. Mục phụ 3.3 docstring "Scope cam" MEDIA_NOT_PORTED — ĐÚNG (BỎ SÓT NHỎ: không nêu dòng mới)

- Docstring cũ `publisher.py:29-35` ghi publish từ chối `FAILED_BEFORE_POST (MEDIA_NOT_PORTED)` khi có media —
  trong khi `_media_gate` hiện tại (`:265-291`) cho qua khi file thật gate đạt, chỉ chặn
  `MEDIA_UNVERIFIED` khi không verify được bytes. Lệch docstring/code là thật.
- Bỏ sót nhỏ của reread: không nêu rằng `_media_gate` mới nằm ở `:265-291` (đã có trong bảng P1
  dòng `29-35`, đủ truy vết — không ảnh hưởng kết luận).

## 5. Mục phụ 3.4 chồng chéo run_batch ↔ Worker — ĐÚNG (BỎ SÓT: worker Phase B đã gom 1 pass)

- Router `/threads/publish` (`routers/threads.py:150-178`) dùng `_FakePage` (submit ack rỗng,
  `read_eye` rỗng) → Phase B reconcile rỗng → mọi publish kết thúc `UNCONFIRMED_NO_REPLAY`
  dù dry-run có chủ ý. Đúng.
- Bỏ sót/cần cập nhật: `worker.py:199-211` Phase B hiện đã gọi `_ro.read_group_receipts(pending)`
  **1 pass gom nhóm** trước khi verify từng item (`_ReadOnlyBrowser.read_group_receipts`,
  `worker.py:254-268`) — tức khuyến nghị "gom 1 pass khi có browser thật" đã được thực hiện
  một phần ở worker. Reread ghi "không phải 1 pass eye gom nhóm như A" — còn đúng ở tầng
  `Publisher.run_batch` (`publisher.py:777-793`, fallback từng item qua `read_receipt`), nhưng
  ở tầng worker thì đã gom. Nên ghi rõ phân tầng này.

## 6. BỎ SÓT: `from_item` nới `#dub\d+` — đúng nhưng thiếu cảnh báo tương thích ngược

- Reread mục 1.10 ghi C nới thành `#dub\d+` (`publisher.py:372-376`) để nuốt tag ngắn `#dub001`.
  Xác minh code: đúng.
- Bỏ sót: không nêu rằng A match cứng `#dub\d{6}` (`threads_post_one.py:574/:613/:775/:1015`),
  nên receipt do C sinh với tag ngắn có thể không được A `run_reconcile` nhận ra (tag-match lệch).
  Không chặn hiện tại (C reconcile nội bộ exact sau normalize), nhưng đáng ghi rõ khi vận hành
  song song A+C.

## Tổng hợp

| # | Nội dung reread | Kết luận | File:dòng |
|---|-----------------|----------|-----------|
| 1 | Scheduler 0 match, thiếu chính số 1 | ĐÚNG | A `core/posting_schedule.py:38-128`; C grep 0 match; `routers/threads.py:131-184` |
| 2 | Bug P0 deferred-khóa-vĩnh-viễn | ĐÚNG | C `publisher.py:694-704` + `:766-828` + `:399-403`; A `threads_post_one.py:840-856` |
| 3 | Bug gốc `_extract_post_codes` chết | ĐÚNG | A `threads_post_one.py:76` (định nghĩa) vs `:365/:471/:833/:838/:1019` (không call site) |
| 4 | Docstring Scope cam cũ | ĐÚNG, thiếu số dòng `_media_gate` mới | C `publisher.py:29-35` vs `:265-291` |
| 5 | Chồng chéo run_batch ↔ Worker | ĐÚNG, cần ghi rõ worker đã gom 1 pass | `routers/threads.py:150-178`; `worker.py:199-211,254-268`; `publisher.py:777-793` |
| 6 | `reconcile()` short-circuit `published` | ĐÚNG (xác minh code `:623-625`, chấp nhận có ghi rõ) | C `publisher.py:616-649` |
| 7 | Tag `#dub\d+` nới | ĐÚNG, bỏ sót cảnh báo A chỉ match `\d{6}` | C `publisher.py:372-376`; A `threads_post_one.py:574/:613/:775/:1015` |

Không có mục SAI. 3 mục BỎ SÓT/cần làm rõ: mục 4 (số dòng `_media_gate`), mục 5 (worker đã gom 1 pass),
mục 6/7 (tương thích tag ngắn với A).

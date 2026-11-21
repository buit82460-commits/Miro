# VERIFY vòng 1 — `apps/backend/src/miro/publishing/publisher.py` vs `C:\dubtool\scripts\threads_post_one.py`

Ngày: 2026-11-21. Checker: subagent thường trực (quyền chặn merge).
Kết luận chung: **CHƯA ĐẠT** — chưa được tính "xong". Chi tiết từng mục dưới đây.

## 0. Ba điều kiện bắt buộc (áp dụng mọi module)

| # | Điều kiện | Kết quả |
|---|-----------|---------|
| 1 | Gọi code cũ thật (import/call sang `C:\dubtool` hoặc `D:\JARVIS-Assistant` qua biên rõ), grep `dubtool\|JARVIS\|sys.path\|import.*legacy` | **CHƯA ĐẠT** — grep chỉ thấy chữ "legacy" trong docstring/comment (7 match toàn là chữ, không có import/call nào). `atomic_save`/`load_json_if_exists` tự viết lại thay vì dùng `shared/execution_policy.atomic_save` + `shared/json_io.load_json` của dubtool (mất xử lý BOM của `load_json`). Đây là rewrite "faithful port", không phải biên gọi code cũ. |
| 2 | Test chứng minh hành vi giữ nguyên và chạm được code cũ (dry-run/fixture với code thật), không mock 100% | **CHƯA ĐẠT** — `apps/backend/tests/test_publisher_threads.py` tự ghi rõ "Mock-browser tests... No real Post". `MockBrowser.post_once`/`read_receipt` là mock 100%, không import `threads_post_one.caption_for`/`guard_duplicate`/`match_eye_records` để đối chiếu, không có fixture journal thật do code cũ sinh ra. Hành vi đúng nhưng chỉ tự test tự pass. |
| 3 | Ghi rõ nguồn file/hàm cũ đang dùng, phần nào còn thiếu | **ĐẠT một phần** — docstring module có ghi nguồn `C:\dubtool\scripts\threads_post_one.py`, nhưng KHÔNG liệt kê phần còn thiếu (media gate, integrity guard, duplicate-tag guard, actor verify — xem mục 7). |

## 1. `caption_for` / `unique_tag` — ĐẠT

So từng dòng với `threads_post_one.py:128-168`: logic title/description/tags/`#dub` tail/truncate `MAX_TEXT-20`/raise khi rỗng/quá dài **giống hệt**. Không phát hiện lệch.

## 2. Layout journal / publication — ĐẠT (về cấu trúc)

- Journal `threads-<shortcode>.json` trong attempts dir, publication `<batch>/publication-threads.json`, các status `submit / submitted-awaiting-group-reconcile / failed-before-post / verified / unknown` khớp legacy (`_post_live_chrome_on_page`, `run_batch` two-phase).
- `guard_duplicate` (legacy `threads_post_one.py:228`) logic publication-hit + journal-tồn-tại giống hệt; thêm `attempts_dir` param là hợp lệ.
- Ghi nhận: đây là cải tiến có chủ ý duy nhất được cho phép — `claim_attempt` dùng `O_CREAT|O_EXCL` đóng TOCTOU của legacy check-then-act, đã có test 2-thread (`test_two_workers_one_intent_only_one_sends`). **ĐẠT.**

## 3. `failed-before-post` vs UNKNOWN — CHƯA ĐẠT (lệch 1 điểm)

Legacy `_post_live_chrome_on_page` (dòng 670-700): exception **sau click** (before_submit=False) thì **re-raise**, KHÔNG tự ghi UNKNOWN — journal giữ `submit`; caller (`run_batch`) mới ghi `unknown` + dừng submit. Port `publish()` tự ghi `UNKNOWN` + return `UNCONFIRMED_NO_REPLAY` ngay tại chỗ.

- Lỗi cụ thể: journal sau single-publish của port là `unknown`, của legacy là `submit` (khi lỗi LiveChromeError sau click ở path `run_shortcode`). Hai trạng thái journal khác nhau → tooling reconcile/read-only đọc journal sẽ phân loại khác.
- Cần sửa: tách `publish_single` giữ nguyên semantics legacy (re-raise sau click), để lớp batch quyết định ghi UNKNOWN; HOẶC ghi rõ trong docstring đây là lệch có chủ ý + cập nhật mọi consumer journal.

## 4. Two-phase batch — CHƯA ĐẠT (3 lỗi cụ thể)

a) **Thiếu duplicate-tag guard** (legacy `run_batch:779-786`): legacy abort cả batch với `DUPLICATE_TAGS` khi 2 item cùng `#dub`. Port `run_batch` không kiểm tra → nguy cơ post nhầm/match nhầm. Cần port nguyên guard.
b) **Phase A của port verify ngay, legacy thì không**: legacy Phase A chỉ ghi `submitted-awaiting-group-reconcile` + milestones/timeline, CHƯA BAO GIỜ mark `published`; mọi `published` đều qua Phase B group reconcile. Port `run_batch` gọi `self.publish` (ghi `verified` + merge publication ngay khi receipt khớp) rồi mới group-reconcile → publication có thể chứa URL chưa qua group reconcile, timeline/milestone (`post_clicked/posting_seen/ack_seen/profile_match_seen`, `ack_to_match_s`) bị mất. Cần sửa `run_batch` theo đúng 2 phase legacy, hoặc ghi rõ lệch có chủ ý.
c) **Chính sách dừng khác legacy**: legacy `_run_batch_legacy` (dòng 937-941) chỉ `break` khi `not before_submit`; lỗi before-submit/generic thì ghi error và **tiếp tục** item sau. Port dừng (`stopped=True`) trên mọi generic error. Cần sửa cho khớp: chỉ dừng khi ambiguous-sau-click/disconnect.

## 5. Verify receipt priority — CHƯA ĐẠT (2 lỗi cụ thể)

Nguồn gốc: `core/rea_eye.py:31-53` (`match_eye_records`: post_id trong `want_ids` trước, rồi **exact** tag equality sau normalize, cùng-record author+tag+post_id, KHÔNG có text fallback) + `_match_post_on_page`/`_reconcile_group`.

a) **Port bỏ qua `known_ids` ở path reconcile**: legacy `run_reconcile` (dòng 1019) đọc `ack_post_codes` từ journal làm `known_ids` cho post_id-first match. Port `reconcile()` gọi `browser.read_receipt` → `verify_receipt` mà không truyền `known_ids` ở đâu → nhánh `post_id` priority thực tế chết. Cần plumbing `known_ids` từ journal vào `verify_receipt`/`match_eye_records`.
b) **Match lỏng hơn legacy, phá vỡ same-record rule**: port `match_eye_records` chấp nhận substring (`want_tag in text`, `want_n[:60] in text`) và `verify_receipt` chấp nhận `tag in url` / `tag in json.dumps(receipt)` — legacy eye yêu cầu tag equality sau normalize **trong cùng 1 record**. Substring/prefix-60 dễ match nhầm cross-article. Cần siết về exact same-record semantics của `rea_eye`.

## 6. Claim nguyên tử — ĐẠT (cải tiến có chủ ý, đã khai báo)

`claim_attempt` O_EXCL + test concurrency. Không yêu cầu sửa. Ghi nhận lệch duy nhất được chấp nhận so với legacy.

## 7. Phần legacy chưa port (phải ghi nhận + quyết định scope)

- `media_for`/`check_video`/`probe_video` (dòng 171-225): gate video trước Post — port không có media handling (`Intent.media_sha256` không được validate ở đâu). Nếu out-of-scope thì ghi rõ + cấm publish có media cho tới khi port.
- `_enforce_adapter_integrity` (dòng 93-105): fail-closed guard — port không có tương đương Miro-side. Cần quyết định: port guard hay thay bằng cơ chế Miro.
- `DUPLICATE_TAGS` guard — xem 4a (bắt buộc, không phải optional).
- `_verify_threads_actor` + tab acquisition/lease single-owner (dòng 646-668): port ủy thác cho `browser` inject, không verify actor `@username` trước Post. Test hiện tại không cover. Cần ít nhất 1 assertion/contract `browser` phải verify actor.
- `atomic_save` tự viết lại (mất UTF-8 no-BOM + tmp+replace semantics đã kiểm chứng của `shared/execution_policy`) và `load_json_if_exists` mất chịu BOM của `shared/json_io.load_json`. Liên quan điều kiện số 1.

## 8. Việc cần làm trước khi được chữ ĐẠT

1. Sửa 3b (two-phase đúng legacy) + 4a (duplicate-tag guard) + 5a (known_ids plumbing) + 5b (siết same-record) + 3 (single-path re-raise hoặc khai báo lệch).
2. Quyết định scope media gate + integrity guard + actor verify (port hay ghi rõ cấm).
3. Bổ sung test chạm code cũ: ít nhất import `threads_post_one.caption_for/guard_duplicate` + `rea_eye.match_eye_records` làm oracle (ví dụ property-test `caption_for` port == legacy trên fixture manifest thật; `match_eye_records` port vs eye gốc trên cùng records). Không cần live Post.
4. Cập nhật docstring module liệt kê đúng 7 mục trên (đang thiếu là xong điều kiện số 3).

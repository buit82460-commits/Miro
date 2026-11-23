# REREAD publisher (khâu PUBLISHER) — A → C

Ngày: 2026-11-21. Reader: subagent khâu PUBLISHER.
Định nghĩa merge: đọc mã thật A, giữ đủ khả năng, port sang kiến trúc C — KHÔNG copy để đấy.

Nguồn A:
- `C:\dubtool\scripts\threads_post_one.py` (1090 dòng: `run_batch` two-phase, `run_reconcile`,
  `guard_duplicate`, tag `#dub`, journal, actor/tab lease, media gate, integrity guard)
- `C:\dubtool\core\posting_schedule.py` (128 dòng: slot/carryover/reconcile/auto-pause, pure + clock injectable)

Nguồn C:
- `apps/backend/src/miro/publishing/publisher.py` (829 dòng: `Publisher`, `Intent`,
  `guard_duplicate`, `claim_attempt`, `verify_receipt`, `match_eye_records`, `run_batch`, `reconcile`)
- `apps/backend/src/miro/threads/worker.py` (287 dòng: `ThreadsWorker`, `ThreadsPage`, dry-run mặc định)
- `apps/backend/src/miro/threads/flow.py` (218 dòng: approval fingerprint+revision, secret gate, audit)
- `apps/backend/src/miro/routers/threads.py` (203 dòng: prepare/approve/publish/reconcile/history)
- Đối chiếu vòng 1–4: `docs/verify/verify-publisher.md` (vòng 4 ĐẠT, 19 passed trên dữ liệu thật A)

## 1. Hành vi A → C: port ĐƯỢC (giữ đủ khả năng)

| # | Hành vi A | C | Ghi nhận |
|---|-----------|---|----------|
| 1 | `caption_for`/`unique_tag` (:128-168, MAX 500, truncate giữ tag) | `publisher.py:128-166` giống hệt + oracle test == legacy | A thuần |
| 2 | Journal layout `threads-<sc>.json`, status `submit/verified/unknown/failed-before-post/submitted-awaiting-group-reconcile` + `UNCONFIRMED_NO_REPLAY` | Có, khớp | A |
| 3 | `guard_duplicate` 2 lớp (publication+url / journal-tồn-tại, :228) | Có + `attempts_dir` param + `claim_attempt` O_CREAT\|O_EXCL đóng TOCTOU legacy | A + C tốt hơn ở claim (đã khai báo, có test 2-thread) |
| 4 | Two-phase batch: Phase A ack-only + timeline, Phase B group-reconcile 1 lần; duplicate-tag abort :779-786; stop khi ambiguous/disconnect, before_submit tiếp tục (:937-941) | `Publisher.run_batch` (:651-828) đủ cả 3; test `test_batch_before_submit_error_continues`, duplicate-tag test | A |
| 5 | Receipt post_id-first (`known_ids` = journal `ack_post_codes`, :1019) + tag exact same-record (`rea_eye` :31-53, không text fallback) | Có + ủy thác eye gốc trước, fallback exact-local | A; C kết hợp để chạy độc lập khi `C:\dubtool` không mount |
| 6 | `media_for/check_video/probe_video` gate (:171-225) | Port đầy đủ (:212-263); `_media_gate` cho qua khi file thật gate đạt, chặn `MEDIA_UNVERIFIED` khi chỉ có sha256 không file | A (quy tắc) + C cấm rõ |
| 7 | `_enforce_adapter_integrity` fail-closed (:93-105) | `enforce_adapter_integrity`: baseline file/env present → refuse | Tương đương ở mức vận hành (C không pack baseline dubtool). Yếu hơn A ở chỗ A verify hash drift toàn adapter, C chỉ check sự tồn tại file — chấp nhận, đã ghi rõ |
| 8 | `_verify_threads_actor` + tab lease (:251-268/:646-668) | Contract `verify_actor_contract` (`verify_actor()`/`declared_actor`, mismatch → before_submit refuse) + worker verify trước Post + `MIRO_ALLOW_UNVERIFIED_ACTOR` chỉ test | A (quy tắc) + B (triết lý uncertain → không retry). Browser thật out-of-scope, đã ghi rõ |
| 9 | JSON runtime UTF-8 no-BOM/tmp+replace + đọc chịu BOM | Ủy thác `shared/execution_policy` + `shared/json_io` khi import được, fallback copy semantics | A (không phát minh cách ghi JSON thứ ba) |
| 10 | Tag regex `#dub\d{6}` (:574/:613/:775/:1015) | Nới thành `#dub\d+` (`Intent.from_item`) để nuốt cả tag ngắn `#dub001` của manifest test-001 thật | C nới đúng (dữ liệu thật bắt buộc), same-record vẫn exact sau normalize |

## 2. Hành vi A → C: MẤT (chưa port) — thiếu chính

**`core/posting_schedule.py` — toàn bộ module lịch (slot/carryover/reconcile/auto-pause) CHƯA có gì trong C.**
Grep toàn `apps/backend/src/miro` với `carryover|due_slots|should_auto_pause|daily_cap` → **0 match**
(`slot` chỉ trúng studio single-slot và TTS slot — không liên quan; `paused` chỉ trúng connections
account status — không phải pause theo lịch).

Cụ thể A có mà C thiếu:
- `build_slot_times` (rải slot đều trong window, ISO local) — C không có.
- `build_day_plan` (carryover giữ `task_id` + ưu tiên suất cũ, fill `daily_cap`, dư vào `storage`,
  `fetch_cap` độc lập post cap) — C không có. Router `/threads/publish` chạy 1 intent/lần, không khái niệm ngày/suất.
- `due_slots` (late boot: chỉ slot đến giờ, không burst) — C không có.
- `record_submit_unknown` (UNKNOWN giữ suất, vào `reconcile_queue`, không re-post) — C giữ UNKNOWN trong journal
  nhưng không có hàng đợi reconcile theo plan.
- `should_auto_pause`/`consecutive_unknowns` (2 UNKNOWN liên tiếp → auto-pause) — C không có.
  Worker dừng submit trong batch nhưng không pause account/cross-batch.
- `paused` outrank mọi slot (vd Page chờ appeal) — C có `connections` status nhưng không nối với publisher.

Module A là pure functions + injectable clock, port rẻ. Đây là **thiếu chính số 1** của khâu này.

## 3. Hành vi C SAI / lệch so với A (kể cả lệch đã biết)

1. **(BUG C, mới phát hiện) Items "deferred" sau ambiguous bị khóa vĩnh viễn.**
   `Publisher.run_batch` (:694-704): khi `stopped=True`, các intent chưa submit vẫn bị ghi journal
   `status=unknown` + result `DEFERRED_TO_GROUP_RECONCILE`, nhưng Phase B chỉ reconcile danh sách
   `submitted` — deferred items không bao giờ được reconcile trong batch đó, mà journal `unknown`
   đã tồn tại → `guard_duplicate` lần sau trả `UNRECONCILED_ATTEMPT` → **không bao giờ được post nữa**.
   A (`run_batch` :840-856, `break`): item chưa attempt **không có journal**, batch sau thử lại bình thường.
   Sửa: nhánh stopped không ghi journal `unknown` (ghi `deferred` không chặn guard, hoặc không ghi gì),
   để batch sau thử lại.
2. **(BUG GỐC A, xác minh) `_extract_post_codes` chết — `ack_post_codes` luôn rỗng trong two-phase.**
   A định nghĩa `_extract_post_codes` (:76) nhưng **không có call site nào** (grep `ack_post_codes`:
   chỉ khởi tạo `[]` ở :365, trả về ở :471, đọc ở :833/:838/:1019). Mọi journal two-phase của A
   đều có `ack_post_codes: []` → `known_ids` ở `run_reconcile` (:1019) luôn rỗng → nhánh post_id-first
   trong A thực tế chết, reconcile chỉ còn tag-match. C plumbing `known_ids` đúng nhưng đang hứng
   list rỗng từ dữ liệu A thật. Không sửa A (đóng băng), nhưng C nên ghi rõ: với journal do A sinh,
   `known_ids` không đáng tin; cân nhắc trích post_id từ response body ở browser-that khi viết adapter thật.
3. **Docstring `publisher.py` mục "Scope cam" đã cũ, sai với code.**
   Dòng 32-33 ghi "`publish()` từ chối FAILED_BEFORE_POST (mã MEDIA_NOT_PORTED) khi có media" —
   nhưng `_media_gate` hiện tại (M2 fix #3, :265-291) **cho phép** media khi file thật gate đạt,
   chỉ chặn khi không verify được bytes. Docstring mô tả hành vi cũ (cấm tuyệt đối). Sửa docstring,
   không sửa code.
4. **Chồng chéo `Publisher.run_batch` ↔ `ThreadsWorker.run_batch` (hai two-phase song song).**
   Cả hai đều có DUPLICATE_TAGS guard, stop-khi-ambiguous, Phase B group-reconcile.
   Router `/threads/publish` dùng worker + `_FakePage` (submit trả ack rỗng, `read_eye` rỗng) nên
   Phase B của worker luôn reconcile rỗng → mọi publish qua router đều kết thúc `UNCONFIRMED_NO_REPLAY`
   dù là dry-run có chủ ý — đúng nhưng dễ gây hiểu nhầm "luôn unknown". Phase B worker gọi
   `publisher.reconcile` từng item (worker.py:207-211), không phải 1 pass eye gom nhóm như A
   (`_reconcile_group` 1 scan → match nhiều tag). Khi có browser thật, worker nên gom 1 pass
   rồi mới verify từng item. Ghi nhận để vòng browser-that xử lý, không chặn hiện tại.
5. **`reconcile()` short-circuit status `published`** (vòng 4 mục 6): A `run_reconcile` không check
   journal status, luôn reconcile. C nhận thêm `published` (do tooling ngoài ghi). Chấp nhận có ghi rõ —
   không che lỗi vì chỉ nhận đúng 2 giá trị, còn lại vẫn verify receipt.

## 4. Bug gốc cần sửa / tối ưu (xếp ưu tiên)

| Ưu tiên | Việc | Thuộc |
|---------|------|-------|
| P0 | Sửa bug deferred-khóa-vĩnh-viễn (mục 3.1): nhánh stopped không ghi journal `unknown` | C `publisher.py:697-704` + test batch 3 item (item3 sau ambiguous → batch sau vẫn post được) |
| P1 | Port `posting_schedule.py` sang C (slot/carryover/daily_cap/storage/due_slots/reconcile_queue/auto-pause/paused-outrank) — thiếu chính số 1 | module mới + nối router/publish (plan theo ngày, late-boot không burst) |
| P1 | Sửa docstring "Scope cam" MEDIA_NOT_PORTED cho khớp `_media_gate` hiện tại | C `publisher.py:29-35` |
| P2 | Ghi rõ `known_ids` từ journal A luôn rỗng (bug gốc A 3.2); thiết kế trích post_id ở browser-that khi viết adapter thật | doc/test |
| P2 | Worker Phase B gom 1 pass eye trước khi verify từng item (khớp `_reconcile_group`) khi có browser thật | `worker.py:199-211` (hiện tại fake/empty nên chưa chặn) |

Không đụng A (đóng băng production). Live Post đầu tiên vẫn qua runbook dubtool + reconcile read-only,
UNKNOWN không replay.

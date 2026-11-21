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

## 8. Việc cần làm trước khi được chữ ĐẠT (vòng 1 — đã xử lý ở vòng 2, xem dưới)

1. Sửa 3b (two-phase đúng legacy) + 4a (duplicate-tag guard) + 5a (known_ids plumbing) + 5b (siết same-record) + 3 (single-path re-raise hoặc khai báo lệch).
2. Quyết định scope media gate + integrity guard + actor verify (port hay ghi rõ cấm).
3. Bổ sung test chạm code cũ: ít nhất import `threads_post_one.caption_for/guard_duplicate` + `rea_eye.match_eye_records` làm oracle (ví dụ property-test `caption_for` port == legacy trên fixture manifest thật; `match_eye_records` port vs eye gốc trên cùng records). Không cần live Post.
4. Cập nhật docstring module liệt kê đúng 7 mục trên (đang thiếu là xong điều kiện số 3).

---

# VERIFY vòng 2 (commit 8cb993a, ngày 2026-11-21) — KẾT LUẬN: **ĐẠT**

Checker đã đối chiếu `publisher.py` mới (776 dòng) với `C:\dubtool\scripts\threads_post_one.py` + `core/rea_eye.py`, chạy `python -m pytest apps/backend/tests/test_publisher_threads.py -q` → **15 passed**, và kiểm tra import code cũ trực tiếp (`shared.json_io`, `shared.execution_policy`, `core.rea_eye` → OK).

## 0. Ba điều kiện bắt buộc

| # | Điều kiện | Vòng 2 |
|---|-----------|--------|
| 1 | Gọi code cũ thật qua biên rõ | **ĐẠT** — `_legacy` import thật `shared.execution_policy.atomic_save`, `shared/json_io.load_json(_if_exists)`, `core.rea_eye.match_eye_records/normalize_tag`, `threads_post_one.caption_for/guard_duplicate` (2 đường `threads_post_one` / `scripts.threads_post_one`). `atomic_save`/`load_json_if_exists` ủy thác cho code cũ khi import được; fallback copy local chỉ khi `C:\dubtool` không mount được và có ghi rõ. `match_eye_records` ủy thác eye gốc trước, fallback exact-local sau. |
| 2 | Test chạm code cũ, không mock 100% | **ĐẠT** — `test_legacy_caption_oracle` (port == legacy trên 4 fixture), `test_legacy_guard_duplicate_oracle` (so trực tiếp với `legacy_guard`, có trỏ `_lt.ATTEMPTS_DIR` sang tmp cho công bằng), `test_legacy_eye_match_oracle` (port vs eye gốc cùng records). Không skip (15 passed, 0 skipped). Mock browser chỉ thay thế CDP/browser-that (out-of-scope đã khai báo). |
| 3 | Ghi rõ nguồn + phần thiếu | **ĐẠT** — docstring module liệt kê đủ mapping dòng legacy (caption :128-168, guard :228, batch :744-901, single :670-700, eye :31-53, reconcile :1019, media :171-225, integrity :93-105, actor :251-268/:646-668) + mục "Scope cam" cấm rõ 2 điểm. |

## Từng mục vòng 1

1. **caption_for/unique_tag — ĐẠT** (giữ nguyên, + oracle test).
2. **Layout journal/publication — ĐẠT** (giữ nguyên).
3. **failed-before-post vs UNKNOWN — ĐẠT.** `publish()` re-raise lỗi sau click, journal giữ `submit`; `run_batch` caller ghi `unknown` + dừng. Test `test_crash_after_post_journal_keeps_submit_and_reraise` assert cả journal `submit`, journal batch `unknown`, và guard không replay.
4. **Two-phase batch — ĐẠT.** (a) Duplicate-tag guard abort `DUPLICATE_TAGS` đúng :779-786, có test. (b) Phase A chỉ ack (`submitted-awaiting-group-reconcile` + milestones/timeline/`ack_post_codes`), merge publication chỉ ở Phase B sau `verify_receipt` — test assert `b2` unknown không merge, `b1` có timeline `profile_match_seen` + `ack_to_match_s`. (c) Stop policy: disconnect/ambiguous-sau-click dừng, `before_submit` tiếp tục — test `test_batch_before_submit_error_continues`.
5. **Receipt priority — ĐẠT.** `known_ids` plumbing từ `journal.ack_post_codes` vào cả `reconcile()` và Phase B (`verify_receipt(rec, intent, post_ids)`), test `test_known_ids_plumbing_from_journal`. Same-record exact: bỏ substring/prefix-60/text-fallback, ủy thác eye gốc trước; test `test_same_record_strictness_no_substring`.
6. **Claim nguyên tử — ĐẠT** (giữ nguyên + test 2-thread).
7. **Scope cấm — ĐẠT.** Media: `media_for/check_video/probe_video` đã port đầy đủ; `publish()` từ chối `MEDIA_NOT_PORTED` (FAILED_BEFORE_POST) khi có media — cấm post "chay". Integrity: `enforce_adapter_integrity` fail-closed khi baseline tồn tại + test. Actor: `verify_actor_contract` (`verify_actor()`/`declared_actor`, mismatch → before_submit refuse) + test; browser thật out-of-scope đã ghi rõ. `MIRO_REQUIRE_ACTOR=1` cho mode fail-closed tuyệt đối.

## Ghi nhận (không chặn, API khác legacy có chủ ý)

- `run_batch` trả về `list` thay vì dict legacy `{"batch","account","count","two_phase",...}` — khác hình thức API Miro (class `Publisher`), semantics phase/guard/stop giữ nguyên. Chấp nhận.
- `verify_receipt` dict-path chấp nhận `post_id in url + tag exact` ngoài `known_ids` — chặt hơn vòng 1 (đòi tag exact), không phá same-record. Chấp nhận.
- `guard_duplicate` thêm param `attempts_dir` (legacy dùng global `ATTEMPTS_DIR`) — hợp lệ cho lib, oracle test đã xử lý.

**Module publisher được tính "xong" ở mức port không-browser-that. Live Post đầu tiên vẫn phải qua runbook dubtool + reconcile read-only, UNKNOWN không replay.**

---

# VERIFY vòng 3 (định nghĩa merge mới, ngày 2026-11-21) — KẾT LUẬN: **CHƯA ĐẠT** (thiếu kiểm chứng luồng thật trong C)

Định nghĩa mới: port/viết lại trong kiến trúc C là ĐÚNG, miễn (1) giữ đủ khả năng + quy tắc gốc, (2) chỗ trùng chọn cách tốt nhất (ghi rõ chọn bên nào, vì sao), (3) kiểm chứng bằng luồng thực tế chạy trong C (dry-run chạm code/tool thật hoặc fixture dữ liệu thật từ A/B), không mock tự-pass.

## 1. Vai trò B (JARVIS) với Publisher: KHÔNG có gì để lấy

Đã grep `D:\JARVIS-Assistant\backend\app\integrations` với `threads|THREADS|caption_for|unique_tag|publication-threads`: chỉ 3 match chữ "dubtool" trong helper HTTP (`dubtool.py` — `call_soon_threadsafe(queue.put_nowait...)`), không có logic Threads nào (caption, tag, journal, receipt, reconcile). B mạnh ở jobs/write-ahead/recovery (đã đọc trong `reader-jarvis.md` §1-2), nhưng Publisher C đã có tương đương qua journal-claim + guard + run_batch dừng-khi-ambiguous, nên không cần lấy thêm.
→ **Lựa chọn: A thuần cho toàn bộ Publisher. Ghi rõ để khỏi ai đi tìm B lần nữa.**

## 2. Đối chiếu từng khả năng gốc A → C (tiêu chí 1 + 2)

| Khả năng gốc A (`threads_post_one.py` + `core/rea_eye.py`) | C có chưa | Giữ đủ quy tắc? | Chọn bên nào / vì sao |
|---|---|---|---|
| `caption_for`/`unique_tag` (:128-168, MAX 500, `#dub` tail, truncate giữ tag) | Có, giống hệt | Đủ (oracle test == legacy trên fixture) | **A** (nguồn duy nhất; B không có) |
| Journal layout `threads-<sc>.json`, status `submit/verified/unknown/failed-before-post/submitted-awaiting-group-reconcile` + `UNCONFIRMED_NO_REPLAY` | Có | Đủ (re-raise giữ `submit`, caller ghi `unknown` — đúng :670-700) | **A** |
| `guard_duplicate` 2 lớp (publication+url / journal-tồn-tại) :228 | Có | Đủ; C cải tiến hợp lệ: `attempts_dir` param thay global + `claim_attempt` O_EXCL đóng TOCTOU (tốt hơn A, đã khai báo) | **A + C tốt hơn ở claim** |
| Two-phase batch: Phase A ack-only + timeline, Phase B group-reconcile 1 lần; duplicate-tag abort :779-786; stop khi ambiguous/disconnect, before_submit tiếp tục (:937-941) | Có | Đủ (vòng 2 đã sửa cả 3) | **A** |
| Receipt: post_id-first trong `known_ids=ack_post_codes` (:1019), tag exact same-record (`rea_eye.py` :31-53, không text fallback) | Có (+ ủy thác eye gốc trước, fallback exact-local) | Đủ (oracle test + strictness test) | **A; C kết hợp**: ưu tiên gọi eye gốc khi import được, fallback exact-local khi `C:\dubtool` không mount — vì C phải chạy độc lập |
| `media_for/check_video/probe_video` gate (:171-225) | Có port đầy đủ, `publish` cấm `MEDIA_NOT_PORTED` | Đủ ở mức cấm (attach bytes out-of-scope, đã ghi rõ) | **A** (quy tắc), **C** (cấm rõ thay vì im lặng) |
| `_enforce_adapter_integrity` fail-closed (:93-105) | Có (`enforce_adapter_integrity`, baseline-file → refuse) | Đủ tương đương (C không pack baseline dubtool nên check file-do-người-vận-hành-cấp + env `MIRO_ADAPTER_BASELINE`) | **A** (quy tắc) theo cách **C** (không copy baseline lạ vào repo) |
| `_verify_threads_actor` + tab lease (:251-268/:646-668) | Có contract (`verify_actor()`/`declared_actor`, mismatch → before_submit refuse; `MIRO_REQUIRE_ACTOR=1` fail-closed tuyệt đối) | Đủ ở mức contract — browser thật out-of-scope, đã ghi rõ | **A** (quy tắc phải verify actor) + **B** (triết lý: verify trước/sau op, uncertain → không retry — khớp `reader-jarvis.md` §3 invariant worker) |
| JSON runtime UTF-8 no-BOM/tmp+replace (`execution_policy.atomic_save`), đọc chịu BOM (`json_io`) | Có (ủy thác code cũ, fallback copy semantics) | Đủ | **A** (cách làm tốt nhất → C chuẩn hóa dùng chung; không phát minh cách ghi JSON thứ ba) |

Tiêu chí (1)+(2): **ĐẠT** — đủ khả năng, chỗ trùng đã chọn và ghi lý do. Không yêu cầu import/call code cũ nữa (định nghĩa mới bãi bỏ tiêu chí cũ).

## 3. Cái còn thiếu theo tiêu chí (3): luồng thực tế trong C chưa được kiểm chứng

Test vòng 2 (`test_publisher_threads.py`, 15 passed) có chạm code cũ (caption/guard/eye oracle) nhưng fixture đều **tự bịa** (`"Hello"`, `"abc123456"`, records `P1/P2` viết tay) + browser mock 100%. Dưới định nghĩa mới, các luồng thực tế sau trong C **chưa có test nào chạy**:

a) **Caption/guard trên manifest thật của A**: `C:\dubtool\reports\resource-batches\threads-20261120\download.json` (item `test-001`, account `haodaojrk5`) + `publication-threads.json` (đã `published`). Chưa có test nào trong C: `caption_for(saved[0])` ra text gì, `guard_duplicate` trên batch copy có skip `ALREADY_IN_PUBLICATION` đúng không.
b) **Reconcile từ journal thật của A**: `C:\dubtool\reports\social-attempts\threads-test-001.json` (status `published`, `post_id Df8vGSCkUXp`, `reconciledReadOnly`). Chưa có test nào trong C đọc journal thật này (parse status/url/post_id, verify `text_sha256` khớp publication) — dry-run read-only, không side-effect.
c) **Batch trên dữ liệu thật**: copy `download.json` + attempts thật vào tmp, chạy `Publisher.run_batch` với browser stub chỉ đọc (không post) → chứng minh guard/reconcile hoạt động trên shape dữ liệu production, không chỉ dict bịa.
d) **B port check**: `media_for` trên file video thật (nếu còn trong batch) hoặc assert `MEDIA_NOT_PORTED` khi item có `media_path` trỏ file thật không gate được — hiện chỉ test path không tồn tại.

## 4. Test bổ sung cần viết (xong mới ĐẠT vòng 3)

1. `test_real_manifest_caption_guard`: đọc `download.json` + `publication-threads.json` thật từ A (skip nếu không mount), assert `caption_for(saved[0])` chứa text gốc và `guard_duplicate` → `ALREADY_IN_PUBLICATION` khi publication đã có url.
2. `test_real_journal_reconcile_readonly`: đọc `threads-test-001.json` thật, assert `Publisher.reconcile` (với browser stub trả receipt khớp `post_id`/`url` trong journal) → `reconciled True` mà `posts == 0`; và journal `unknown` thật (nếu còn, vd `threads-7679492543322557728.json`) → guard `UNRECONCILED_ATTEMPT`, không replay.
3. `test_real_batch_dryrun`: dựng batch tmp từ copy manifest thật, `run_batch` với stub read-only, assert không post + guard đúng trên từng item.
4. Ghi rõ trong test khi nào `pytest.skip` (A không mount) — skip vì thiếu dữ liệu là hợp lệ, nhưng CI có A mount thì phải chạy (không được skip toàn bộ nhóm mới).

**Kết luận vòng 3: CHƯA ĐẠT — không phải do code sai (logic đã đúng theo vòng 2), mà do thiếu kiểm chứng trên dữ liệu thật của A ngay trong C. Viết xong 4 test trên (hoặc tương đương) + pass thì được chữ ĐẠT theo định nghĩa mới.**

---

# VERIFY vòng 4 (commit 2533888, ngày 2026-11-21) — KẾT LUẬN: **ĐẠT** (có 1 lưu ý không chặn)

Checker đối chiếu diff `publisher.py` (8 dòng), đọc `test_publisher_realdata.py` (158 dòng), chạy `python -m pytest test_publisher_realdata.py test_publisher_threads.py -q` → **19 passed, 0 skipped** (A mount đầy đủ nên cả 4 test dữ liệu thật đều chạy, không skip), và kiểm tra trực tiếp dữ liệu thật A + code gốc.

## Từng mục vòng 3

1. **`test_real_manifest_caption_guard` — ĐẠT.** Đọc `download.json` thật (item `test-001`), `caption_for` ra `'Hello Threads! ...\n\n#dub001'` chứa text gốc + tag thật `#dub001` (không phải fixture bịa). `guard_duplicate` trên copy production → `ALREADY_IN_PUBLICATION`; shortcode lạ → `None`. Đúng tiêu chí (3).
2. **`test_real_journal_reconcile_readonly` — ĐẠT.** Journal thật `threads-test-001.json` (status `published`, post `Df8vGSCkUXp`, `reconciledReadOnly`) → `reconcile` True với `posts == 0` (ReadOnlyBrowser raise nếu post). Journal treo thật `threads-7679492543322557728.json` (status `submit`, đã xác minh trực tiếp) → guard `UNRECONCILED_ATTEMPT` + reconcile False, không replay.
3. **`test_real_batch_dryrun` — ĐẠT.** Copy publication+journal thật → `run_batch` skip `ALREADY_IN_PUBLICATION`, 0 post. Batch 2v thật (`threads-20261120-2v/download.json`, 2 item shortcode `7640141773947325728`/`7708817728873827617`) → prep chặn MEDIA, vẫn 0 post, mọi result đều có error/skipped/receipt/posted.
4. **`test_real_media_gate` — ĐẠT có điều kiện.** File video thật của A tại `C:/Users/Admin/Videos/Ai/vizzion-20261119/*.mp4` **không còn tồn tại trên máy này** → test skip nhánh file-thật đúng như thiết kế (`pytest.skip("khong con file video that...")`), chỉ assert `media_for` trên path giả. Không trừ điểm (dữ liệu gốc mất, không phải lỗi C), nhưng ghi nhận: gate `check_video` trên bytes thật chưa từng được chạy — **lần đầu có video thật phải chạy `check_video` tay trước khi tin gate.**
5. **Fix tag regex `#dub\d{6}` → `#dub\d+` — ĐẠT (bắt buộc theo dữ liệu thật).** `Intent.from_item` cũ không bắt được tag thật `#dub001` (3 chữ số từ `unique_tag("test-001")`); journal/publication thật đều dùng tag ngắn. Không fix thì `test_real_*` fail hàng loạt. Ghi nhận chênh với gốc: legacy `run_batch`/`run_reconcile` dùng `#dub\d{6}` cố định (:574/:613/:775/:1015) vì shortcode số của A luôn đủ 6+ chữ số; chỉ manifest `test-001` (test kỹ thuật, không phải shortcode số thật) mới sinh tag ngắn. Nới regex là đúng cho C (phải nuốt được cả 2 shape), không làm lỏng same-record (vẫn exact sau normalize).
6. **Fix `reconcile` nhận status `published` — ĐẠT.** Journal thật `threads-test-001.json` có status chữ `published` (do tooling cũ/tool ngoài ghi, không phải `verified` của adapter). Không fix thì `reconcile` trả `already:verified` sai nhánh... thực tế là trả reconcile-lại thay vì short-circuit — fix cho short-circuit đúng. Không che lỗi: chỉ nhận đúng 2 giá trị `verified|published`, mọi status khác vẫn đi path verify receipt.
7. **Tiêu chí (1)+(2) định nghĩa mới — giữ nguyên ĐẠT** (không đổi ở commit này; B vẫn không có gì cho Publisher).
8. **Phạm vi commit:** `2533888` còn sửa `app.py`/`main.py`/routers/registry/gitignore (entrypoint, router RAM→SQLite) — **ngoài phạm vi Publisher, Checker không đánh giá ở vòng này.** Ghi nhận để vòng sau kiểm tra riêng: router SQLite + entrypoint gộp cần verify luồng thật riêng.

**Module publisher được tính "xong" theo định nghĩa merge mới (19 passed, dữ liệu thật A chạy trong C, 0 post). UNKNOWN không replay; live Post đầu tiên vẫn qua runbook dubtool + reconcile read-only.**

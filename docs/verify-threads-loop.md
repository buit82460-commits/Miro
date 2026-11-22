# VERIFY M2 — Luồng Threads khép kín (commit 2f96181, ngày 2026-11-21)

Checker thường trực, định nghĩa merge mới: (1) giữ đủ khả năng + quy tắc gốc A/B,
(2) trùng thì chọn cách tốt nhất có ghi rõ, (3) kiểm chứng bằng luồng thực tế trong C.
Chạy: `python -m pytest apps/backend/tests/test_threads_flow.py -q` → **4 passed**.
Phạm vi M2: text-only khép kín trên manifest thật `threads-20261120-2p` (dry-run 0 post
mặc định, fake managed tab khi post); chưa Chrome thật, chưa media video.

## Kết luận chung: **CHƯA ĐẠT** — lõi gate + journal + reconcile đúng, nhưng luồng còn đứt 3 chỗ + thiếu media

## 1. Nghiệm thu M2 (theo yêu cầu)

| Nghiệm thu | Bằng chứng | Kết quả |
|---|---|---|
| Chọn video → sửa phụ đề → render → chọn tài khoản → xem kết quả | `test_closed_loop_with_real_manifest`: manifest thật 2p (account `haodaojrk5`, count 2) → Library import asset (dedupe sha256) → `prepare_publish` render idempotent + link asset↔render → approval bound → `worker.run_batch(allow_post=True)` → `history_for` trace đúng render + asset + journal | **ĐẠT một phần (text-only).** Đường media thật bị `MEDIA_NOT_PORTED` chặn (`blocked.error == FAILED_BEFORE_POST`) — đúng fail-closed đã thiết kế, nhưng nghĩa là **video chưa đi hết luồng publish** (xem §3.1) |
| Lịch sử mở đúng file render + đúng bài | `history_for`: `render_id` khớp, asset đúng, journal của bài có mặt; trace qua Library SQLite persistent | **ĐẠT** |
| Mất kết nối sau gửi → đối soát, không đăng lại | `test_guard_unknown_never_replays_*`: `CrashPage.submit` raise sau click → journal `unknown` + `UNCONFIRMED_NO_REPLAY` → publish lại cùng intent → `UNRECONCILED_ATTEMPT` (không post lần 2) → `reconcile` read-only với eye verified → promoted, `reader.posts == 0` | **ĐẠT**. Đúng A (§8.7.1) + B (uncertain → đối chiếu ngoài, không auto-retry) |

## 2. Đối chiếu A (`reader-dubtool.md` §8) — từng điểm

- **Journal TRƯỚC click (mỗi item) — ĐẠT.** `Publisher.publish`: `guard_duplicate` → `claim_attempt` (`O_CREAT|O_EXCL`, chống TOCTOU) ghi `submit`+`text_sha256` → `_pre_post_checks` → `post_once`. Lỗi sau click re-raise để worker ghi `unknown`. Khớp A §8.1/§8.7.1.
- **Guard 2 lớp — ĐẠT ở Publisher, THIẾU ở worker.** `Publisher.run_batch` có `ALREADY_IN_PUBLICATION`/`UNRECONCILED_ATTEMPT` + `DUPLICATE_TAGS` cả batch (`:632-657`); nhưng **`ThreadsWorker.run_batch` không kiểm tag trùng cả batch** — batch 2 intent cùng `#dub` qua worker sẽ post cả 2, vi phạm A §8.7.2 (trùng → dừng cả batch). **CHƯA ĐẠT — bổ sung DUPLICATE_TAGS vào worker hoặc bắt worker gọi `Publisher.run_batch`.**
- **1 CDP + 1 managed tab cả batch — ĐẠT một phần.** Worker: 1 `page_factory()` đầu batch, item sau `renew(300)`, `finally: release()`. **Thiếu:** (a) không `disconnect`/đóng CDP trong finally (docstring ghi "release + disconnect" nhưng code chỉ `release`); (b) router `threads_browser=None`, chưa nối `ManagedChromeSession` thật — chấp nhận ở M2 (chưa có Chrome thật), nhưng (a) phải sửa khi nối live.
- **Verify actor trước Post — ĐẠT (fail-closed).** Worker check `page.verify_actor(intent.owner)` trước approval-gate; sai → `FAILED_BEFORE_POST`, không post nhầm. Khớp A §8.4 (yếu như Threads gốc, không "tăng cường" — đúng).
- **Ack 3 đường — MỞ (fake).** `submit()` do `ThreadsPage` inject cung cấp; fake trả `ack_via=fake-managed-tab`. Production chưa nối Playwright/composer thật → ack thật (toast/network/composer-closed) chưa được kiểm chứng. **M2 Dj/arm thật mới đóng được.**
- **Phase B group reconcile — CHƯA ĐẠT ở worker.** `Publisher.run_batch` có phase B đầy đủ; nhưng **`ThreadsWorker.run_batch` (đường M2 chính) không gọi group reconcile sau batch** — post xong là hết, không có pass readback gom. A §8.1 bắt phase B 1 lần sau phase A. **Bổ sung: worker sau vòng post gọi `publisher.reconcile` nhóm hoặc `read_group_receipts`.**
- **Dừng sau ack mơ hồ đầu tiên — ĐẠT.** Worker `break` khi UNKNOWN/disconnect/`UNCONFIRMED_NO_REPLAY`. Khớp A `:840-856`.
- **Lịch UNKNOWN giữ slot / auto-pause — NGOÀI PHẠM VI M2** (scheduler chưa nối adapter, reader §9.4 đã ghi). Không trừ điểm, ghi nhận.
- **Threads không qua submit_studio/timeline/handoff — ĐẠT.** Router riêng, không đụng Studio.

## 3. Đối chiếu B (`reader-jarvis.md` §10/§10.5) — từng điểm

- **Fingerprint bind approval — ĐẠT.** `approve_intent` lưu fingerprint canonical (media/text/owner/shortcode/tag) + revision; test đổi text sau duyệt → `FINGERPRINT_CONFLICT`, intent còn nguyên vẫn post (`page.posts == 1`). Khớp §10.5.
- **Vị trí gate — ĐẠT.** `Publisher._pre_post_checks`: integrity → media-gate → `verify_actor_contract` → `check_approval`, rồi mới `post_once`. Đúng "SAU guard+verify, TRƯỚC post_once". `require_approval=False` mặc định (Publisher độc lập không đổi hành vi cũ), threads state bật `True` — lựa chọn đúng, đã ghi rõ.
- **Fail-closed/deny mặc định — ĐẠT.** Thiếu/sai scope/lệch revision/lệch fingerprint/secret → từ chối `before_submit` (journal `failed-before-post`, không post). `check_secret_text` chặn `api_key=/secret/token/...`; journal chỉ giữ `text_sha256`.
- **Audit receipt batch non-blocking — ĐẠT (logic), test mỏng.** `AuditLog`: batch 20, queue đầy → `dropped`++, không chặn post; flush fsync. Test chỉ cover append+flush, chưa cover `dropped` — bổ sung 1 assert nhỏ.
- **Write-ahead fsync — ĐẠT một phần.** `atomic_save` thêm fsync tmp trước replace (không fsync dir — chấp nhận, đã là fallback comment "write-ahead").
- **Không suy đoán trạng thái đăng — ĐẠT.** `verify_receipt` owner + same-record exact; `history_for` chỉ coi verified-có-url là posted.
- **Stop 2 pha + watchdog — MỞ.** §10.5 đã liệt kê; worker chưa có `request_stop`/grace (render/post browser không hủy giữa chừng). Chuyển sang M3 (nền chạy chung) — không chặn M2 dry-run.

## 4. Đứt gãy phải nối trước chữ ĐẠT

1. **`POST /threads/publish` chưa chạy worker.** Router chỉ `publications.publish(...)` queue rồi trả về — không gọi `ThreadsWorker.run_batch`, không trả kết quả post/reconcile. Luồng khép kín qua HTTP bị đứt ở đúng chặng publish. **Nối worker (dry-run mặc định, `allow_post` chỉ khi body yêu cầu + approval kèm theo) hoặc ghi rõ endpoint này chỉ queue và chỉ rõ endpoint nào chạy worker.**
2. **Worker thiếu `DUPLICATE_TAGS` cả batch (§2).**
3. **Worker thiếu phase B group reconcile (§2).**
4. **`MEDIA_NOT_PORTED`: video chưa đi hết luồng.** Manifest thật 2p có media nhưng publish media bị cấm cứng. Theo tiêu chí (1) "giữ đủ khả năng gốc", Threads A là post video/composer gắn file — C hiện chỉ khép kín text. **Hoặc port media-gate (check_video + gắn file qua managed tab), hoặc ghi rõ M2 = text-only và mở M-media riêng.** Không được để test gọi "đúng thiết kế" mà coi như xong video.
5. (Nhẹ) Audit `dropped` chưa có test; worker finally thiếu `disconnect`; `threads_browser=None` chưa nối session thật.

## 5. Việc cần làm trước chữ ĐẠT M2

1. Nối `POST /threads/publish` → worker (kèm approval/revision từ body) + test HTTP khép kín.
2. Worker: `DUPLICATE_TAGS` + phase B group reconcile + `disconnect` trong finally.
3. Quyết định media: port hoặc tách milestone M-media có ghi rõ.
4. 1 lần chạy trên Chrome remote-debugging thật (read-only trước).

---

# VERIFY vòng 2 (commit 5ef059b + 49bea2e, ngày 2026-11-21) — KẾT LUẬN: **ĐẠT có điều kiện** (lõi khép kín; HTTP publish + Chrome thật còn mở)

Checker đối chiếu diff 2 commit + chạy `test_threads_flow.py` → **7 passed**,
full suite → **119 passed**.

| Điểm vòng 1 | Fix | Kết quả |
|---|---|---|
| §4.2 Worker thiếu `DUPLICATE_TAGS` | Guard tag-trùng cả batch đầu `run_batch`, 0 post khi trùng (giống `Publisher.run_batch :650-657`) | **ĐẠT** (logic; test cover ở `Publisher.run_batch`, worker-guard là bản sao — chấp nhận) |
| §4.2 Worker thiếu phase B group reconcile | Sau vòng post: gom `posted` → 1 pass `read_group_receipts` read-only → `reconcile` từng pending → append `phase: B-group-reconcile` | **ĐẠT**. Đúng A §8.1 (1 lần read-only sau phase A) |
| §4.2 finally thiếu `disconnect` | `finally`: `release()` + gọi `page.disconnect()` nếu có (nuốt lỗi) | **ĐẠT** (fake có/không disconnect đều qua; live phải implement) |
| §4.4 Media chưa đi hết luồng | `_media_gate`: text-only pass; file thật tồn tại → `media_for` + `check_video` pass → cho qua tới `post_once`; sha256-không-file → `MEDIA_UNVERIFIED` fail-closed; gate fail → `FAILED_BEFORE_POST` (cả `publish` lẫn `run_batch` prep) | **ĐẠT**. Test realdata cập nhật đúng hành vi mới: file thật → `attempts==1`, `posts==0` (browser dry-run raise sau gate); file mất → `attempts==0` + `FAILED_BEFORE_POST`. Không còn `MEDIA_NOT_PORTED` chặn cứng |
| §4.1 `POST /threads/publish` chưa chạy worker | **Chưa sửa** — router vẫn chỉ queue `publications.publish(...)`, không gọi worker | **CHƯA ĐẠT, chuyển thành điều kiện mở** (xem dưới) |
| §4.5 Audit `dropped` chưa test | Chưa bổ sung assert | Nhẹ, nợ test nhỏ — không chặn |

## Điều kiện còn mở (không chặn lõi, bắt buộc trước live)

1. **`POST /threads/publish` vẫn đứt khỏi worker** — luồng khép kín qua HTTP chưa hoàn tất ở chặng publish (queue rồi trả về, không post/reconcile). Entry point kiểm chứng M2 hiện tại là `worker.run_batch` trực tiếp (test), không phải HTTP. Trước live phải nối (dry-run mặc định, `allow_post` + approval từ body) + test HTTP khép kín.
2. **Chưa chạy trên Chrome thật lần nào** (cả M1 và M2). Ack 3 đường, composer, eye-readback vẫn là fake `submit()`/`read_eye()`. Trước publish live: 1 lần `ManagedChromeSession.open` + acquire + read trên Chrome remote-debugging thật.
3. Stop 2 pha/watchdog worker, scheduler auto-pause — đã chuyển sang M3 theo reader §9.

**Module Threads được tính "xong" ở mức lõi C (gate/journal/reconcile/approval/media-gate thật trên manifest A, 0 post thật). Live post đầu tiên vẫn qua runbook dubtool + reconcile read-only.**

---

# VERIFY vòng 3 — commit 33e3877 (ngày 2026-11-21): POST /threads/publish nối worker + live-read Profile 20 read-only — KẾT LUẬN: **ĐẠT**

Checker thường trực đọc diff 33e3877 + code hiện trạng (`routers/threads.py`, `browser/live_chrome.py`)
+ tự chạy `python -m pytest tests/test_live_chrome_readonly.py tests/test_threads_publish_http.py -q`
trong `C:\Miro\apps\backend` → **6 passed**. Files không đổi sau 33e3877
(`git diff 33e3877 HEAD --stat` rỗng trên 5 file + biên bản này).

## § HTTP publish (`POST /threads/publish` → `ThreadsWorker.run_batch`)

| Mục | Bằng chứng | Kết quả |
|---|---|---|
| Nối worker vào router | `publish()` queue `publications.publish(...)` rồi gọi `worker.run_batch([intent], _FakePage, allow_post, approvals, revision)`; trả `{queued, replayed, worker, posted_fake}` | **ĐẠT** — đóng điều kiện mở §vòng-2.1 |
| Dry-run mặc định 0 post | `test_publish_defaults_to_dry_run_zero_post`: `results[0].dry_run is True`, `posted_fake == []` | **ĐẠT** |
| allow_post thiếu approval bị deny | `test_publish_allow_post_without_approval_denied`: `error in (APPROVAL_REQUIRED, FAILED_BEFORE_POST)` (không exception HTTP 403 vì worker trả lỗi trong result, đúng hợp đồng `run_batch`) | **ĐẠT** |
| allow_post + approval còn hiệu lực → fake post | `test_publish_allow_post_with_approval_runs_fake_post_only`: `posted_fake == [shortcode]`, `posted is True`, `receipt == UNCONFIRMED_NO_REPLAY` | **ĐẠT** |

Nhỏ (không chặn): `from miro.browser.errors import RegistryError` ở `routers/threads.py:28`
hiện chưa dùng trong file — dọn ở commit sau.

## § Live-read Profile 20 read-only (`browser/live_chrome.py` + `docs/live-read-profile20.md`)

| Mục | Bằng chứng | Kết quả |
|---|---|---|
| Chỉ 1 CDP tới Chrome có sẵn, không tự mở | `connect_over_cdp`: `connect_over_cdp` duy nhất; lỗi → `CDP_UNAVAILABLE` raise, không retry/reconnect; thiếu playwright → `PLAYWRIGHT_MISSING` fail-closed | **ĐẠT** (fake CDP trong test) |
| Module không có post/navigate path | `test_module_has_no_post_path` (không `def post`/`post_once`/`def navigate`/`def submit`) + grep tay: chỉ còn chữ "navigate" trong comment/docstring cấm | **ĐẠT** |
| Read 1 URL: open → bind profile → acquire → read → release → disconnect | `test_read_url_once_fake_cdp_no_post`: text chứa `dub417888`, `browser.disconnected is True` | **ĐẠT** |
| Không Chrome → deny, không tự mở thay thế | `test_no_chrome_running_denied_without_opening`: `CDP_UNAVAILABLE`/`WAITING_CONFIRMATION` (test dùng `connect=dead` raise `ConnectionError`; đường `connect_over_cdp` thật map mọi exception → `CDP_UNAVAILABLE`) | **ĐẠT** |
| Runbook `docs/live-read-profile20.md` | Chuẩn bị Chrome thủ công + CLI + bảng lỗi + test fake + §4 phần mở | **ĐẠT** |

## Phần mở (chưa làm, không chặn vòng này)

1. `workers/browser/worker.py:19` vẫn skeleton `raise NotImplementedError("merge từ nhánh nghiệp vụ (workers/browser)")` — chưa nối vào `ManagedChromeSession`.
2. Live-read thật cần Chrome do người dùng mở sẵn (remote-debugging, Profile 20, 2 tab `chrome://version` + URL bài) + `pip install playwright` — chưa chạy lần nào; connector mới qua test fake CDP.
3. Actor verify mới qua URL (`threads_actor` regex `@username`); verify qua DOM + watch/poll để sau khi live thật.

Lệnh: `cd C:\Miro\apps\backend && python -m pytest tests/test_live_chrome_readonly.py tests/test_threads_publish_http.py -q` → **6 passed**.

## § P0 journal (commit f09e377, ngày 2026-11-21) — **ĐẠT**

Checker thường trực đọc diff f09e377 + đối chiếu A (`C:\dubtool\scripts\threads_post_one.py`
`run_batch :840-856`) + tự chạy
`python -m pytest tests/test_publisher_threads.py tests/test_publisher_realdata.py -q`
trong `C:\Miro\apps\backend` → **24 passed** (EXIT=0).

| Mục | Bằng chứng | Kết quả |
|---|---|---|
| Deferred không journal | A `:840-856` dùng `break`: item sau điểm dừng không bao giờ chạm tới → không journal; port cũ ghi `unknown` cho deferred là sai. f09e377 bỏ `atomic_save` ở nhánh `stopped`, chỉ trả `DEFERRED_TO_GROUP_RECONCILE`. Test `test_batch_deferred_no_journal_retry_next_batch`: `threads-p3.json` không tồn tại, batch sau post lại được (`posted is True`) | **ĐẠT** |
| Unknown vẫn guard | Nhánh disconnect/ambiguous sau click vẫn `atomic_save status=unknown`; test assert `p2.json status == unknown` và `run_batch([bad])` → `skipped == UNRECONCILED_ATTEMPT` | **ĐẠT** |

Nhỏ (không chặn, ghi nhận chênh với A): A nhánh disconnect (`:850-855`) không ghi journal
unknown (chỉ `ambiguous.append` + `break`), còn port ghi `unknown` cho cả disconnect —
an toàn hơn (guard chặn replay), chấp nhận có chủ ý.

---

## § P0 mắt (commit 05195dc, ngày 2026-11-21) — **ĐẠT**

Checker thường trực đọc diff 05195dc + đối chiếu A (`C:\dubtool\core\rea_eye.py`
locator `:67-68`, `TAG_RE :18`, match `:45-51`) + đáp A/B + slot C
(`docs\ba-ben\cau-hoi\HOI-eye-01.md`) + `docs\reread-eye.md` (S2/S3/B1-B8)
+ tự chạy `python -m pytest tests/test_eye_collect_p0.py tests/test_publisher_threads.py -q`
trong `C:\Miro\apps\backend` → **30 passed** (10 P0 mắt + 20 publisher_threads, EXIT=0).

| Mục | Bằng chứng | Kết quả |
|---|---|---|
| Locator hẹp 2 pattern (đáp A HOI-eye-01) | `test_locator_hep_2_pattern`: 1 call, selector chứa `/@alice/post/` + `/@alice/t/`; port `publisher.py` `_EYE_LINK_SELECTOR` giữ nguyên 2 pattern A `:67-68`, không mở rộng mù | **ĐẠT** |
| Same-record không ghép chéo | `test_same_record_2_article_khong_ghep_cheo`: 2 article → 2 record đúng tag/link/video riêng (A match `:45-51` post_id-first rồi tag-exact cùng record) | **ĐẠT** |
| B1 video không lan document | `test_b1_video_khong_article_khong_lan_document` + code `el.closest('article') ? ... : false` (A `:77-78` dùng `\|\| document` gây false-positive) | **ĐẠT** |
| B2 post_id cắt query/fragment | `test_b2_post_id_cat_query_fragment`: `/@alice/post/abc123?x=1...#frag` → `abc123` (A `:80` split mù dính query) | **ĐẠT** |
| B3 TAG boundary 6 số | `test_b3_tag_dai_khong_hit_6_so_dau`: `#dub1234567` → `""`, `#dub123456` → hit; `TAG_RE = #dub\d{6}(?!\d)` (A `:18` không boundary) | **ĐẠT** |
| B6 dedup + limit theo record | `test_b6_dedup_limit_theo_record`: P1 trùng query dedup, limit=2 → `[P1, P2]` (A `:69` cắt theo link, không dedup) | **ĐẠT** |
| B7 preview giữ tag cuối | `test_b7_preview_giu_tag_cuoi_caption_dai`: caption 280x + tag cuối → preview vẫn chứa tag (A `:87` `text[:300]` cắt mất tag) | **ĐẠT** |
| S2 bỏ passthrough match=post_id | `test_s2_bo_passthrough_match_post_id_tu_khai`: receipt tự khai `match=post_id` + tag sai + pid ngoài known → `None`; pid trong known → published (xóa `receipt.get("match") == "post_id"`) | **ĐẠT** |
| S3 eye record key author | `test_s3_eye_record_key_author_duoc_chap_nhan`: `{"author": "@alice", ...}` → published (`owner or author`) | **ĐẠT** |
| B5 đếm lỗi thay vì nuốt câm | `errors` counter + `_diagnostic eye-errors` record khi có lỗi (A `suppress` câm) | **ĐẠT** (logic; chưa có test riêng đếm errors — nhẹ) |

Red-test có thật (đã kiểm): code cũ fail cả 4 — (1) C cũ không có `collect_post_records`
(M1: import fail); (2) A `TAG_RE` cũ hit 6 số đầu của `#dub1234567` (xác minh bằng
`re` trực tiếp: old hit=True); (3) `verify_receipt` cũ chấp nhận `match == "post_id"`
passthrough (dòng bị xóa trong diff); (4) A `:77-78` fallback `document` lan video
sang article-missing.

Lệnh: `cd C:\Miro\apps\backend && python -m pytest tests/test_eye_collect_p0.py tests/test_publisher_threads.py -q` → **30 passed**.

## Phần mở (chưa làm, không chặn P0 này)

- B4 (locator hẹp, DOM đổi là mù): giữ hẹp theo đáp A, chưa có log trúng/miss + đếm link/article (gợi ý B từ TikTok `page_extract.py:44`). Thêm khi live-read thật.
- B8 (author hardcode từ param): docstring ghi caller đảm bảo qua acquire/verify — chấp nhận ở P0 fake-DOM; live thật phải đọc author/Page URL quan sát được để não từ chối khi lệch tab.
- M2/M3 N-read: `ThreadsWorker._ReadOnlyBrowser.read_group_receipts` vẫn loop `read_eye` mỗi intent + `reconcile` từng item gọi `read_receipt` lại — `collect_post_records` mới port chưa được worker dùng (1 collect → match offline). Nối ở milestone sau.
- S1/S4/S5: S1 lọc author trước (thắt chặt có lợi, chệch A — chấp nhận có ghi); S4 `Intent.from_item` `#dub\d+` vs alphabet 6-số (slot C HOI-eye-01 chấp nhận nuốt manifest test, exact sau normalize); S5 `want_text` tham số chết — chưa bỏ/ghi rõ, dọn sau.
- Preview đấu dây: `collect_post_records` mới chưa đấu vào `ManagedChromeSession`/worker Phase B — production path vẫn fake `read_eye`. Đấu dây + 1 lần live-read Chrome thật ở milestone sau.

---

## § P1 scheduler (commit 3247d2c, ngày 2026-11-21) — **ĐẠT**

Checker thường trực đọc diff 3247d2c + đối chiếu gốc
(`C:\dubtool\core\posting_schedule.py`: `build_day_plan :55-90`,
`due_slots :93-103`, `record_submit_unknown :106-114`,
`consecutive_unknowns/should_auto_pause :117-128`)
+ đáp A+B (`docs\ba-ben\chu-de\TD-publisher.md`: đáp A suất UNKNOWN tính cap
+ đáp B caller boot/pause) + tự chạy
`python -m pytest tests/test_schedule_p1.py -q`
trong `C:\Miro\apps\backend` → **6 passed** (EXIT=0, oracle gốc chạy thật, không skip).

| Mục | Bằng chứng | Kết quả |
|---|---|---|
| Port nguyên 6 hàm | `schedule.py` 117 dòng: `_tz`, `_parse_hhmm`, `build_slot_times`, `build_day_plan`, `due_slots`, `record_submit_unknown`, `consecutive_unknowns`, `should_auto_pause` — logic trùng từng dòng gốc (cap cắt `[:cap]`, slot giữ state, `due_slots` chỉ `pending`, queue append-only) | **ĐẠT** |
| Carryover giữ task_id, không vượt cap | `test_carryover_giu_task_id_cap_khong_vuot`: old1 carryover đứng slot 0, storage = `[n2, n3]` | **ĐẠT** |
| UNKNOWN giữ slot + vào reconcile_queue + due_slots loại | `test_unknown_giu_slot_tinh_cap_khong_chay_lai`: state → `unknown_pending_reconcile`, queue `["a"]`, due chỉ còn `["b"]` | **ĐẠT** (đúng đáp A: suất tính cap, không giải phóng) |
| Late-boot không burst | `test_due_slots_khong_burst_late_boot`: boot sớm 0 slot, boot muộn chỉ slot đến hạn | **ĐẠT** |
| Auto-pause 2 UNKNOWN liên tiếp | `test_auto_pause_2_unknown_lien_tiep` | **ĐẠT** |
| Caller boot vs pause (nguyên tắc B) | `test_caller_boot_vs_pause`: module chỉ giữ flag `status`, không thêm nhánh boot/pause — phân biệt nằm ở caller (đúng đáp A dòng 49-51) | **ĐẠT** |
| Oracle so thẳng hàm gốc | `test_oracle_goc_khi_mount_duoc`: port vs `core.posting_schedule.build_day_plan` cùng input → slots + storage bằng nhau | **ĐẠT** (chạy thật, không skip) |
| Không requeue toàn cục | `reconcile_queue` append-only trong plan ngày, module không tự requeue (đúng ý B dòng 42) | **ĐẠT** |

Lệnh: `cd C:\Miro\apps\backend && python -m pytest tests/test_schedule_p1.py -q` → **6 passed**.

## Phần mở (làm ở 64c046a — xem § Scheduler caller bên dưới, ĐẠT)

- Nối caller thật vào `Publisher.run_batch` / worker: check `status == paused` trước `due_slots`, boot máy tắt → tính lại plan theo policy, user pause → tôn trọng không post bù.
- `reconcile-verified` kết thúc vòng đời slot trong plan ngày (verified → publication, unknown-tiếp → carryover ngày sau do caller quyết) — đáp A dòng 32.

## § Scheduler caller (commit 64c046a, ngày 2026-11-21) — **ĐẠT**

Checker thường trực đọc diff 64c046a + đối chiếu § P1 scheduler phần mở
(`verify-threads-loop.md:202-203`: paused/due trước Phase A, reconcile-verified
kết thúc slot) + đáp A/B TD-publisher (paused outrank, boot-vs-pause ở caller,
verified kết thúc slot) + tự chạy
`python -m pytest tests/test_schedule_caller.py tests/test_publisher_threads.py tests/test_threads_flow.py tests/test_eye_wiring.py -q`
trong `C:\Miro\apps\backend` → **35 passed** (EXIT=0).

| Mục | Bằng chứng | Kết quả |
|---|---|---|
| Paused chặn trước post | `run_batch` gate `select_due_intents` trước intent; test paused → `defer_reason PAUSED`, `posted False`, `post_once` raise nếu bị gọi | **ĐẠT** |
| Chỉ slot đến hạn vào Phase A | `test_khong_burst`: 10:00 chỉ slot `a` due, `b` → `NOT_DUE`; intent không slot → `NO_SLOT` | **ĐẠT** |
| Boot: máy tắt rebuild, user pause respect | `boot_action(False,"active")=rebuild`; `(True,*)=respect`; `(False,"paused")=respect` | **ĐẠT** |
| Verified kết thúc slot, unknown vào queue | `mark_slot_verified` → state `verified` + ra `reconcile_queue`; unknown → `record_submit_unknown` | **ĐẠT** |
| Không day_plan vẫn chạy cũ | Gate `isinstance(plan, dict)` bỏ qua khi không có plan; 30 test cũ pass không vỡ | **ĐẠT** |

Lệnh: `cd C:\Miro\apps\backend && python -m pytest tests/test_schedule_caller.py tests/test_publisher_threads.py tests/test_threads_flow.py tests/test_eye_wiring.py -q` → **35 passed**.

---

## § P1 env-guard (commit 76ee9b7, ngày 2026-11-21) — **ĐẠT**

Checker thường trực đọc diff 76ee9b7 + đối chiếu B soi (`TD-publisher.md:25`: test nới lỏng
phải assert rõ env đang bật + có test không-env chứng minh fail-closed) + A đồng ý (`:35-37`)
+ tự chạy `python -m pytest tests/test_publisher_threads.py -q`
trong `C:\Miro\apps\backend` → **20 passed** (EXIT=0).

| Mục | Bằng chứng | Kết quả |
|---|---|---|
| Test bật env assert rõ env đang bật | `test_actor_contract_relaxation_only_with_explicit_env`: assert `!= "1"` trước (bắt leak env giữa test), `monkeypatch.setenv("MIRO_ALLOW_UNVERIFIED_ACTOR", "1")` rồi assert `== "1"` sau | **ĐẠT** (đúng ý B: test nới lỏng assert rõ trạng thái env) |
| Test không-env chứng minh fail-closed | `test_actor_contract_missing_everything_blocks_by_default`: không set env, bare browser không verify → `FAILED_BEFORE_POST`, `post_once` raise nếu bị gọi | **ĐẠT** (production mặc định deny, không che đường production) |
| Không đổi production code | Diff chỉ chạm `tests/test_publisher_threads.py` (+11/-1), logic `verify_actor_contract` giữ nguyên | **ĐẠT** |

---

## § Mắt thật đấu dây (commit 6b0bcc8, ngày 2026-11-21) — **ĐẠT**

Checker thường trực đọc diff 6b0bcc8 + đối chiếu `C:\dubtool\core\rea_eye.py :59-61`
(adapter không chạy locator riêng, gọi eye lấy records rồi match trên data)
+ phần mở P0 (§ P0 mắt: collect_post_records chưa được worker dùng, 1 collect → match offline)
+ tự chạy `python -m pytest tests/test_eye_wiring.py tests/test_publisher_threads.py tests/test_eye_collect_p0.py tests/test_threads_flow.py -q`
trong `C:\Miro\apps\backend` → **40 passed** (EXIT=0).

| Mục | Bằng chứng | Kết quả |
|---|---|---|
| Locator nằm trong eye port | `publisher.py:461+` `collect_post_records(page, ...)` là nơi duy nhất gọi `page.locator(...)`; `threads_page.py` không chứa `locator`, chỉ truyền `self._page` vào eye port rồi nhận records | **ĐẠT** (đúng luật A rea_eye :59-61) |
| Phase B 1-collect | `worker.py` `read_group_receipts`: page có `collect_records(owner)` → 1 call, `match_eye_records` offline từng intent; test `test_worker_1_collect_chi_quet_1_lan` assert `calls["n"] == 1` | **ĐẠT** |
| Fallback page cũ | Page không có `collect_records` (hoặc collect lỗi) → rớt xuống loop `read_eye` cũ, semantics giữ nguyên | **ĐẠT** |
| verify_actor khớp/lệch | `test_verify_actor_khop_va_lech`: `alice`→True, `@ALICE`→True (lower + lstrip @), `bob`→False | **ĐẠT** |
| submit vẫn raise (chưa đấu dây post) | `submit` raise `AssertionError` "chưa đấu dây"; worker chỉ read-only/reconcile (kiểm trực tiếp: raise OK) | **ĐẠT** |

Lệnh: `cd C:\Miro\apps\backend && python -m pytest tests/test_eye_wiring.py tests/test_publisher_threads.py tests/test_eye_collect_p0.py tests/test_threads_flow.py -q` → **40 passed**.

## Phần mở (chưa làm, không chặn milestone này)

- Live-read Chrome thật: đấu dây `ManagedThreadsPage` vào `ManagedChromeSession`/worker Phase B production + 1 lần đọc Chrome thật (kế thừa B4/B8 P0: locator hẹp + author verify qua acquire).
- Adapter submit thật qua composer Threads (hiện `submit` raise có chủ ý) — xong mới hết read-only.

## § Mắt B4+B8 (commit fbd81bb, ngày 2026-11-21) — **ĐẠT**

Checker thường trực đọc diff fbd81bb + đối chiếu phần mở P0
(B4 log hit/miss + đếm link/article; B8 author live) + contract `PostRecord`
(`C:\dubtool\core\rea_eye.py :6-8`: author/tag/url/post_id/has_video/text)
+ tự chạy `python -m pytest tests/test_eye_wiring.py tests/test_eye_collect_p0.py tests/test_publisher_threads.py tests/test_threads_flow.py tests/test_schedule_caller.py -q`
trong `C:\Miro\apps\backend` → **47 passed** (EXIT=0).

| Mục | Bằng chứng | Kết quả |
|---|---|---|
| B4 diag dict riêng, giữ contract cũ | `collect_post_records(page, username, limit, diag=None)`: `diag.update(scan)` cuối hàm; không còn append `{"_diagnostic": ...}` vào kết quả; test assert `len(raw) == 1` chỉ record thật | **ĐẠT** |
| B4 đủ 6 đếm | `scan = links/articles/skipped_no_article/skipped_no_pid/dupes/errors`; test assert `links == 2, articles == 2, dupes == 1`; `skipped_no_article` đếm trước khi vẫn đọc text (article-check trước innerText) | **ĐẠT** |
| B8 author live từ href | `_author_of_href(href)` regex `/@user/` quan sát được; `live_author or f"@{user}"` fallback; test `raw[0]["author"] == "@alice"` | **ĐẠT** |
| Não vẫn từ chối khi lệch tab | `match_eye_records` lọc `author != owner → continue` cả 2 nhánh (legacy + fallback); test bob vs alice → `None` | **ĐẠT** |
| Fake P0/wiring đúng shape mới | `test_eye_collect_p0.py`: FakeLink `closest('article')` check trước innerText, FakeLocator thêm `count()`; `test_eye_wiring.py` fake `article → count()`; locator calls = 2 (links + article) | **ĐẠT** |

Nhỏ (không chặn): `skipped_no_article` hiện chỉ đếm, link ngoài article vẫn được thu record (đúng A fallback `parentElement`, không mù như B4 gợi ý cắt cứng) — chấp nhận có chủ ý.

Lệnh: `cd C:\Miro\apps\backend && python -m pytest tests/test_eye_wiring.py tests/test_eye_collect_p0.py tests/test_publisher_threads.py tests/test_threads_flow.py tests/test_schedule_caller.py -q` → **47 passed**.

---

## § Mắt S1/S4/S5 (commit 3f617c9, ngày 2026-11-21) — **ĐẠT**

Checker thường trực đọc diff 3f617c9 + đối chiếu `docs/reread-eye.md` S1 (`:87-104`),
S4 (`:120-124`), S5 (`:125-129`) + A (`C:\dubtool\core\rea_eye.py` `match_eye_records :31-53`,
`extract_tag :26-28`, `TAG_RE :18`) + phần mở P0 (S1/S4/S5 dọn sau) + tự chạy
`python -m pytest tests/test_eye_wiring.py tests/test_eye_collect_p0.py tests/test_publisher_threads.py tests/test_threads_flow.py tests/test_schedule_caller.py -q`
trong `C:\Miro\apps\backend` → **50 passed** (EXIT=0).

| Mục | Bằng chứng | Kết quả |
|---|---|---|
| S1 fallback record-major 1 vòng | `match_eye_records` fallback gộp 2 vòng thành 1 (`:584-596`: mỗi record check post_id trước rồi tag, skip `url` rỗng); test record đầu `KNOWN` chốt `eye-post_id` dù record sau tag khớp; path delegate vẫn gọi hàm gốc A record-major | **ĐẠT** |
| S4 tag 6-số thống nhất | `from_item :377` `#dub\d{6}(?!\d)` trên `text.lower()`; test `#dub001`→`#dub000000` (caption_for append unique_tag), `#dub1234567`→`#dub000000` không hit nhầm; alphabet khớp mắt (cộng B3 `(?!\d)` đã có ở `TAG_RE :447`) | **ĐẠT** |
| S5 want_text chết có ghi rõ | Default `""` + docstring "CỐ Ý KHÔNG DÙNG"; test text khác hẳn không đổi kết quả, text chứa tag vẫn miss; 4 caller (`publisher.py :744/:916`, `worker.py :269/:287`) truyền `intent.text` chạy qua (50 passed) | **ĐẠT** |

Nhỏ (không chặn): A `TAG_RE :18` không boundary, C thêm `(?!\d)` (kế thừa fix B3 — chặt hơn có chủ ý).
Đóng phần mở P0 dòng S1/S4/S5.

Lệnh: `cd C:\Miro\apps\backend && python -m pytest tests/test_eye_wiring.py tests/test_eye_collect_p0.py tests/test_publisher_threads.py tests/test_threads_flow.py tests/test_schedule_caller.py -q` → **50 passed**.

---

## § Scheduler/launcher wiring (commit d146963, ngày 2026-11-21) — **ĐẠT**

Checker thường trực đọc diff d146963 vs 6888fd8 (8 files, +467/-13) + đối chiếu
`docs/ba-ben/chu-de/TD-publisher.md` (suất UNKNOWN tính cap, reconcile append-only,
boot-vs-pause ở caller, paused outrank) + `TD-nen.md` (bounded restart) +
`docs/reread-foundation.md` § launcher + `docs/crosscheck-foundation.md` L2 (history mất
khi launcher restart) + gốc `C:\dubtool\core\posting_schedule.py` (6 hàm nguyên) + tự chạy
`python -m pytest tests -q` trong `C:\Miro\apps\backend` → **219 passed** (EXIT=0).

| Mục | Bằng chứng | Kết quả |
|---|---|---|
| (a) Day-plan persist qua restart + rebuild/respect đúng boot_action | `store.plan_path` = `var/threads-day-plan.json` (tmp+replace); `ensure_day_plan` gọi `boot_action(was_clean_shutdown, policy.status)` — `respect` giữ plan cũ cùng ngày, `rebuild` build mới + persist; `main._init_threads_state` nạp plan persist vào `threads_publisher.day_plan` lúc boot (try/except, không crash); test `ensure_persists_and_binds_day_plan` (file tồn tại, bind publisher, GET day-plan 200) | **ĐẠT** |
| touch_unknown/touch_verified persist 1 nơi, reconcile đơn cũng persist | `store.touch_unknown/touch_verified` = mutate + `save_plan` duy nhất; `publisher` 3 điểm (reconcile đơn `:762` + run_batch verified `:957` / unknown `:976`) đều gọi `store.touch_*` trước, fallback `schedule.mark_slot_*` nếu import lỗi; test `touch_verified_persists_to_file` reload file → `verified` | **ĐẠT** |
| Endpoints đúng luật (STALE 409, CLI fail-closed 503, không crash) | `/schedule/ensure|day-plan|day-plan/status` (caller-giữ-plan; BIND fail → 500; status lạ → 400; thiếu plan → 404); `main` mount 2 router; `/desktop/init|act|transfer` (act qua `act()`: STALE→409, CLI_UNAVAILABLE→503, WINDOW/DOC/UNKNOWN→422, job lạ→404); `backend.run_cli` bắt `OSError/ValueError` → `CLI_UNAVAILABLE` thay vì crash; test desktop CLI fail-closed + pause-block-run_batch (`PAUSED`) | **ĐẠT** |
| (d) L2 RestartBudget persist per-service, xuyên-launcher không reset | `windows/miro.py RestartBudget(name, state_dir)` + file `restart-budget-<name>.json` (load chịu file hỏng/BOM, save tmp+replace chịu OSError); clock wall (`time.time`, prune `>= window`, giữ `+3600` dung sai); `cmd_start` tạo budget theo tên service; test `launcher_l2_budget_persists_across_instances`: 2 crash cũ → instance mới `maximum=2` raises `WORKER_RESTART_EXHAUSTED` ngay | **ĐẠT** |
| Không global requeue UNKNOWN, paused outrank | `store` không thêm hàng đợi nào ngoài `plan["reconcile_queue"]` append-only của module; `select_due_intents` paused → toàn bộ deferred `PAUSED`; `due_slots` chỉ `pending`; pause patch vừa memory vừa file | **ĐẠT** |

Lệnh: `cd C:\Miro\apps\backend && python -m pytest tests -q -p no:warnings` → **219 passed in 37.10s** (PYTEST_EXIT=0).

**Đóng:** crosscheck-foundation L2 (history mất khi launcher restart) — đã persist per-service;
P-D6 verify-foundation (scheduler+launcher ngoài scope) — wiring xong, còn live-run.
**Đã commit, chưa push** (theo yêu cầu checker).

---

## § Engage/comment-message (ngày 2026-11-21) — **ĐẠT**

Checker thường trực đọc diff + đối chiếu nguồn port duy nhất
(`C:\dubtool\scripts\tiktok_engage_one.py`: guard_action, _daily_count,
_do_action view/like/repost/comment/follow, comment text từ manifest/CLI)
+ tự chạy full suite trong `C:\Miro\apps\backend` → **258 passed, 2 skipped**.

| Mục | Bằng chứng | Kết quả |
|---|---|---|
| TikTok engage port thật | `adapters/tiktok.py`: `engage_job_id/guard_engage/merge_engage/daily_engage_count/describe_engage` + `ENGAGE_ACTIONS/DAILY_CAPS/ENGAGE_PUBLICATION`; `live.py::LivePage._engage_tiktok/_engage` port `_do_action` (view/like/repost/comment/follow, comment ≤150 ký tự từ req, fail trước click → `before_submit=True`) | **ĐẠT** |
| Stub UNSUPPORTED các platform còn lại | `send_comment/send_message` trả `UNSUPPORTED_COMMENT/MESSAGE_<PLATFORM>` + ghi rõ "chua trinh sat REA Q1-Q10" ở Threads/FB/IG; `youtube.send_comment` ghi rõ chờ checklist API; `live.engage` platform khác port trả `UNSUPPORTED_ENGAGE_*` — không tự bịa flow | **ĐẠT** |
| Guard + never replay | `guard_engage` (publication-engage + journal) + test skip `ALREADY_IN_PUBLICATION`/`UNRECONCILED_ATTEMPT`; `NO_COMMENT_TEXT` khi thiếu text (không hard-code spam) | **ĐẠT** |
| Test mới | `tests/test_engage_comment.py` — 7 passed (describe/guard/daily-cap/live-unsupported/stub); full suite 258 passed, 2 skipped | **ĐẠT** |

**Phần mở:** live engage/comment thật cần duyệt + test trên Chrome managed tab; comment/message Threads/FB/IG/YT chờ trinh sát REA Q1–Q10 đủ Evidence mới port (đúng AGENTS.md).

---

## § REA-eye khoa luat cung + tay chi dung selector mat-thay (bce7934 + 58bf6a4, ngay 2026-11-22) — **DAT**

Checker doc diff 2 commit + tu chay full suite trong `C:\Miro\apps\backend` → **263 passed, 2 skipped**.

| Muc | Bang chung | Ket qua |
|---|---|---|
| Khoa luat cung mat-nao-tay + eye du 8 platform | `runbook §7` + `eye/EYE_COVERAGE` (threads/facebook/tiktok/instagram/youtube/shopee/chatgpt/flow/desktop); test `test_eye_coverage` assert du key | **DAT** |
| Tay chi dung selector mat-thay | `live.py::fill_composer` chi dung `seen_box_sel/seen_submit_sel` khi visible+enabled, loi -> `FAILED_BEFORE_POST`; `submit_once` doc eye-truoc | **DAT** |
| 8 adapter + live driver + engage | YT API CRUD, TikTok draft/preflight/discover, FB caption/verify, IG download/validate, Shopee research, ChatGPT CRUD, Flow download; engage TikTok 5 actions | **DAT** |

---

## § interaction_fix + wire + live Profile 16 (b3342f5 + tiep, ngay 2026-11-22) — **DAT**

Bang fix rut tu test live tay tren Chrome Profile 16 (hank667735 / Quang Dao): TikTok `evaluate` click, FB JS-click+Enter, IG click-icon + Post-x2-verify-gone.

| Muc | Bang chung | Ket qua |
|---|---|---|
| Bang fix + wire vao live | `adapters/interaction_fix.py` (`click_for/post_for/verify_for`); `live.py::fill_composer` fallback `INTERACTION_FIX[platform].click_selectors` qua JS click; test `test_interaction_fix.py` 3 passed | **DAT** |
| Don anh root vao evidence | `evidence-20261122-p16/` (24 file) | **DAT** |
| Live comment 3 platform (tay, co anh) | TikTok `@baotangnhac` Drill mix 38s (xem het, comment `hankhank068` top panel); FB Hoshimiya "I'M BACK" (comment Quang Dao len); IG reel `mr.good.luck_` (comment `hank667735`, nut Post bien mat) | **DAT (tay)** — receipt la anh trong `evidence-20261122-p16/`, chua co post_id trong publication |
| Test | `python -m pytest tests -q` trong `C:\Miro\apps\backend` → **266 passed, 2 skipped** | **DAT** |

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

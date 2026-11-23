# Đối chiếu độc lập reread-eye.md (commit 9fb307c)

Ngày: 2026-11-21. Phạm vi: `C:\dubtool\core\rea_eye.py` (89 dòng) +
`C:\Miro\apps\backend\src\miro\publishing\publisher.py` (829 dòng) +
`browser/runtime.py` `read_tab` + `threads/worker.py` + `routers/threads.py`.
Phương pháp: đọc mã thật từng dòng, không tin claim khi chưa thấy bằng chứng.

Kết luận chung: **reread-eye.md ĐÚNG toàn bộ claim kỹ thuật có thể kiểm chứng
(S2/S3/S4/M1-M3 + B1-B8 + mô tả §1 + dòng tham chiếu).** S1 ĐÚNG nhưng cần thu
hẹp diễn đạt (chi tiết dưới). Không phát hiện claim SAI. Một điểm BỎ SÓT nhỏ
nên bổ sung (S2 còn một nhánh nới lỏng nữa không được nêu).

## 1. Mô tả hàm A (§1 reread) — ĐÚNG hết

- `normalize_tag` (A:21-23): `strip → lower → collapse \s+` — ĐÚNG.
  Bằng chứng: `rea_eye.py:21-23`.
- `extract_tag` (A:26-28): `TAG_RE = #dub\d{6}` đúng 6 số, hit đầu tiên,
  không boundary — ĐÚNG. Bằng chứng: `rea_eye.py:18,26-28`.
- `match_eye_records` (A:31-53): record-major, post_id-trước-tag-sau,
  exact sau normalize, không substring/text-fallback, **không kiểm author
  trong hàm** — ĐÚNG. Bằng chứng: `rea_eye.py:39-52` (không có tham chiếu
  author nào trong hàm; author chỉ xuất hiện ở `collect_post_records:82`).
- `collect_post_records` (A:56-89): locator 1 lần `/post/` + `/t/`, cắt
  `limit` theo số link, `closest('article') || parentElement` cho text,
  `suppress(Exception)` từng link + toàn locator, author hardcode param —
  ĐÚNG. Bằng chứng: `rea_eye.py:63-89`.

## 2. Port C: Được / Mất

- Vị trí port `publisher.py:443-486 / 489-524 / 616-649 / 766-829`,
  delegate `_legacy` `:54-73` — ĐÚNG (đếm dòng thực tế khớp).
- `normalize_tag` port chính xác + thứ tự post_id-trước-tag-sau giữ đúng,
  không text fallback — ĐÚNG. Bằng chứng: `publisher.py:434-440,443-486`.
- `reconcile()` truyền `known_ids` vào cả hai nhánh list/dict (`:629` +
  `:637`, nguồn `:626` từ `journal.ack_post_codes`); `publish()` `:602`
  gọi `verify_receipt(receipt, intent)` không `known_ids` — ĐÚNG.
  Bằng chứng: `publisher.py:602,626-637`.
- **M1 — Không có `collect_post_records` thật trong C — ĐÚNG.**
  `runtime.read_tab` (`runtime.py:394-419`) chỉ trả blob
  `{url, title, text: body.innerText[:max_chars]}` + verify kép, không parse
  per-article. `ThreadsPage.read_eye` là abstract (`worker.py:43-46`).
  Grep toàn `miro/` chỉ thấy `read_eye` ở: abstract `worker.py:43`,
  fake `_FakePage.read_eye` (`routers/threads.py:163-164`, `return []`),
  `_ReadOnlyBrowser/_PostingBrowser` delegate (`worker.py:251-252,286-287`).
  Không có implementation production nào parse body thành PostRecords.
- **M2 — Phase B đọc N lần thay vì 1 lần — ĐÚNG.**
  Bằng chứng: `publisher.py:777-793` (`read_group_receipts` 1 lần rồi fallback
  `browser.read_receipt` từng item thiếu); `worker.py:254-268` loop `read_eye`
  mỗi intent.
- **M3 — `reconcile()` đơn lẻ N/A cho batch worker path, đọc trùng — ĐÚNG.**
  Bằng chứng: `worker.py:200-213` — `:204` gọi `_ro.read_group_receipts(pending)`
  **rồi vứt kết quả**, `:208-209` lại `publisher.reconcile` từng item, mỗi lần
  reconcile lại `read_receipt` (`publisher.py:627`, qua `_ReadOnlyBrowser`
  `worker.py:251-252`).

## 3. Port C: Sai (S1–S5)

- **S1 — ĐÚNG, nhưng nên thu hẹp diễn đạt.** Phần kiểm chứng được: C lọc
  author trước (`publisher.py:460-462` nhánh delegate, `:473` nhánh fallback)
  trong khi A không lọc author trong hàm — đây là điểm chệch hành vi có thật
  (thắt chặt có lợi nhưng chệch). Phần "hai vòng độc lập post_id/tag" cũng có
  thật (`:472-478` và `:479-485`). Tuy nhiên với single-want thì hai cách duyệt
  cho kết quả tương đương (reread tự thừa nhận "trùng ở single-want"), và path
  delegate gọi đúng hàm gốc nên OK — nghĩa là S1 **không gây sai kết quả ở bất
  kỳ path nào hiện tại**, chỉ là chệch cấu trúc + rủi ro tương lai. Đề nghị sửa
  reread: ghi rõ "không ảnh hưởng kết quả hiện tại, chỉ chệch hợp đồng".
- **S2 — ĐÚNG.** `post_id in url` substring (`publisher.py:513`) + passthrough
  `receipt.get("match") == "post_id"` (`:516`) đều có thật. Lưu ý: `match_eye_records`
  của C trả `"eye-post_id"` (`:478`), nên passthrough chỉ kích hoạt với receipt
  ngoài tự khai `"post_id"` — đúng như reread mô tả ("receipt tự khai").
- **S3 — ĐÚNG.** Eye record thật có key `author`, không có `owner` →
  `_normalize_account(None) == ""` ≠ owner → `return None` ở `:502-504`.
  Reread nói đúng là path list trong `reconcile()` không đi qua đây
  (`publisher.py:628-629` đi `match_eye_records`) và Phase B tự gắn `owner`
  khi bọc hit (`:789`) — cả hai đều khớp code.
- **S4 — ĐÚNG.** `Intent.from_item` (`publisher.py:376`) dùng `#dub\d+` mọi độ
  dài, trong khi mắt A chỉ sinh đúng 6 số (`rea_eye.py:18`). Tag ngắn
  (vd `#dub001`) match exact với eye tag 6 số → luôn miss → UNKNOWN oan.
- **S5 — ĐÚNG.** `want_text` là tham số của `match_eye_records`
  (`publisher.py:443-444`) nhưng thân hàm (`:452-486`) không dùng tới —
  grep `want_text` trong hàm không có hit nào ngoài chữ ký.

## 4. Bug gốc A (B1–B8) — ĐÚNG hết, từng mục có bằng chứng dòng

- **B1 — ĐÚNG.** `rea_eye.py:77-78`: `(el.closest('article') || document).
  querySelector('video')` — không article thì query cả document → false-positive
  khi bài khác trên trang có video.
- **B2 — ĐÚNG.** `rea_eye.py:80`: `href.strip("/").split("/")[-1]` giữ nguyên
  query/fragment (`abc?x=1` ≠ want_id sạch).
- **B3 — ĐÚNG.** `rea_eye.py:18`: `#dub\d{6}` không boundary → `#dub1234567`
  hit 6 số đầu.
- **B4 — ĐÚNG.** `rea_eye.py:67-68`: chỉ `/post/` + `/t/`, thiếu `/p/` và
  render quote/repost khác pattern.
- **B5 — ĐÚNG.** `rea_eye.py:66` + `:70`: `suppress(Exception)` cả locator lẫn
  từng link → trả `[]` câm, caller không phân biệt được "nhìn rồi, không có"
  vs "nhìn lỗi".
- **B6 — ĐÚNG.** Không dedup theo post_id/url; `links[:limit]` (`:69`) cắt
  theo số link, không theo số bài unique.
- **B7 — ĐÚNG.** `extract_tag` chạy trên `norm` full (`:76,83`) nên tag field
  vẫn đúng, nhưng `text: norm[:300]` (`:87`) có thể mất tag → khó debug.
  Reread đã tự nêu đúng nuance này.
- **B8 — ĐÚNG.** `author: f"@{user}"` hardcode từ param (`:82`), không đọc DOM;
  tab lạc account → gán nhầm.

## 5. BỎ SÓT trong reread (1 mục, mức thấp)

- **S2 thiếu một nhánh nới lỏng:** `verify_receipt` nhánh tag (`publisher.py:
  519-523`) chấp nhận receipt **không có `post_id`** (`post_id or None`) chỉ cần
  tag exact + url non-empty — trong khi A luôn gắn receipt với record có post_id
  thật từ DOM. Kẻ/phần mềm trả receipt giả `{owner, url, tag}` đúng tag là pass
  mà không cần post_id nào tồn tại. Reread chỉ nêu nhánh `post_id in url` +
  passthrough, chưa nêu nhánh tag-không-post_id này. Mức độ: thấp-trung bình
  (cần biết trước tag, nhưng tag nằm ngay trong caption đã đăng).

## 6. Checklist §4 reread — hợp lệ, chưa làm (ngoài phạm vi đối chiếu)

Không kiểm chứng tính đầy đủ của checklist, chỉ ghi nhận các mục 1-4 tương ứng
đúng với M1/S2-S5/B1-B8 đã xác minh ở trên.

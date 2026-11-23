# Reread mắt–não (A = `C:\dubtool\core\rea_eye.py`, C = Miro port)

Ngày: 2026-11-21. Phạm vi: `collect_post_records`, `match_eye_records`,
`normalize_tag` (A toàn bộ 89 dòng) + Runbook §9–9a + C
`apps/backend/src/miro/publishing/publisher.py` (match port, reconcile luồng)
+ `browser/runtime.py` `read_tab` + `threads/worker.py` `read_eye` interface.
Merge định nghĩa: đọc mã thật A, giữ đủ khả năng, port sang C, kiểm chứng
luồng thật trong C — KHÔNG copy để đấy.

## 1. Từng hàm A làm gì

### `normalize_tag(text)` (A:21-23)
- `strip → lower → collapse whitespace` (`re.sub(r"\s+", " ", ...)`).
- Mục đích đúng như Runbook §9: vá render Threads kèm trailing space
  (`#dub417888  ` vẫn khớp).

### `extract_tag(text)` (A:26-28)
- Regex `TAG_RE = #dub\d{6}` — **đúng 6 chữ số**, tìm trên text đã lower.
- Trả về hit đầu tiên hoặc `""`. Không validate vị trí, không loại trừ
  tag trong từ dài hơn (regex không có boundary — `#dub1234567` vẫn hit
  6 số đầu; xem bug B3).

### `match_eye_records(pending, records)` (A:31-53) — não thuần, không DOM
- Input: `pending {shortcode: {tag, post_ids[]}}`, `records` = PostRecords.
- Duyệt **record-major**: với mỗi record, với mỗi shortcode chưa có receipt:
  1. post_id-first: nếu `want_ids` non-empty và `pid` thuộc `want_ids` → chốt.
  2. else tag-exact sau normalize (`want_tag == tag`) → chốt.
- Không substring/prefix, không text fallback, **không kiểm author trong hàm**
  (hợp đồng docstring nói author+tag+post_id cùng 1 record, nhưng code chỉ
  enforce tag/post_id cùng 1 record; author do caller đảm bảo qua `username`
  lúc collect).
- `missing` = pending chưa có receipt. Deterministic, first-record-wins theo
  thứ tự records (không chọn best-match).

### `collect_post_records(page, username, limit=40)` (A:56-89) — mắt duy nhất
- Locator một lần: `a[href*="/@{user}/post/"], a[href*="/@{user}/t/"]`,
  `.all()`, cắt `limit`.
- Mỗi link: `href` → `url` tuyệt đối + `post_id` = segment cuối;
  `parent_text` = `closest('article') || parentElement` `.innerText` →
  normalize → `extract_tag` → `text[:300]`; `has_video` =
  `!!((closest article || document).querySelector('video'))`.
- `suppress(Exception)` từng link + toàn bộ locator: lỗi → bỏ qua im lặng,
  trả list có thể rỗng. `author` hardcode `@{user}` param, không đọc từ DOM.

## 2. C port được / mất / sai chỗ nào

Port nằm ở `publisher.py:443-486` (`match_eye_records`) + `:489-524`
(`verify_receipt`) + `:616-649` (`reconcile`) + `:766-829` (phase B),
ủy thác code gốc qua `_legacy["eye_match"/"eye_norm"]` khi import được
(`:54-73`).

### Được
- `normalize_tag` port chính xác (`_norm_tag_exact` delegate `_legacy`
  eye_norm, fallback regex giống hệt).
- Thứ tự ưu tiên post_id-trước-tag-sau được giữ; không có text fallback
  trong `match_eye_records` — đúng A.
- `reconcile()` dùng `known_ids` từ `journal.ack_post_codes` (`:626`) và
  truyền vào cả hai nhánh list/dict — **đã sửa** finding cũ trong
  `docs/verify/verify-publisher.md` (khác với `publish()` path vẫn gọi
  `verify_receipt(receipt, intent)` không `known_ids` ở `:602` — xem S2).

### Mất
- **M1 — Không có `collect_post_records` thật trong C.**
  `runtime.read_tab` (`runtime.py:394-419`) chỉ trả blob
  `{url, title, text: body.innerText[:max_chars]}` + verify kép.
  Không có code production nào parse body thành PostRecords
  `{author, tag, url, post_id, has_video, text}` per-article.
  `ThreadsPage.read_eye` là interface trừu tượng (`worker.py:43-46`);
  production chưa implement — mọi test hiện tại dùng fake/mock trả sẵn
  records. Nghĩa là **luồng mắt thật E2E trong C chưa tồn tại**:
  não (`match_eye_records`) có, mắt (collect per-article) không.
- **M2 — Phase B đọc N lần thay vì 1 lần.**
  Runbook §9 luật sắt: 1 thời điểm 1 bên đọc tab; A §8.1 group reconcile
  1 lần. C `Publisher.run_batch` Phase B (`:777-793`): `read_group_receipts`
  1 lần (nếu có) rồi **fallback `browser.read_receipt` từng item** cho phần
  còn thiếu = N read. `ThreadsWorker._ReadOnlyBrowser.read_group_receipts`
  (`worker.py:254-268`) còn tệ hơn: loop `read_eye` **mỗi intent** rồi mới
  match — không phải 1 pass gom. Đúng ra: 1 `collect` → match tất cả offline.
- **M3 — `reconcile()` đơn lẻ vẫn N/A cho batch worker path chính.**
  `ThreadsWorker.run_batch` có Phase B gom (`worker.py:191-218`) nhưng
  `_ro.read_group_receipts(pending)` gọi N `read_eye`, rồi lại
  `publisher.reconcile` từng item → mỗi item lại `read_receipt` thêm lần nữa
  (`:208-209` gọi sau khi đã gom ở `:204`). Đọc trùng, không tái dùng kết quả
  pass gom.

### Sai (port chệch A, nới lỏng hoặc thắt sai)
- **S1 — Đổi chữ ký + đổi thứ tự duyệt.**
  A: `(pending multi-sc, records)`, record-major (với mỗi record, post_id
  trước rồi tag, chốt shortcode đầu tiên khớp record đó).
  C: `(records, owner, want_tag, want_text, known_ids)` single-want,
  priority-major (quét hết records tìm post_id trước, rồi quét lại tìm tag).
  Với single-want kết quả thường trùng, nhưng với multi-item batch, A cho
  record đầu tiên "claim" shortcode theo thứ tự record; C (qua fake pending
  `{"_want": ...}` + ủy thác `_legacy` khi import được) vẫn gọi đúng hàm gốc
  nên OK ở path delegate — nhưng **path fallback thuần C (`:471-486`) không
  tương đương A khi nhiều records cùng tag**: A chốt record đầu tiên duyệt
  tới cho shortcode đó trong vòng lặp record-major kèm skip `sc in receipts`;
  C chốt record đầu tiên trong vòng tag-loop — trùng ở single-want, nhưng
  docstring C ghi "same-record exact semantics" trong khi vòng post_id và vòng
  tag là hai vòng độc lập (vẫn cùng-record từng vòng, nên claim này OK) —
  điểm chệch thực là C **lọc author trước** (`:460-462`, `:473`) trong khi A
  không lọc author trong hàm. Lọc thêm là thắt chặt có lợi, nhưng là chệch
  hành vi: record tag đúng + post_id đúng nhưng author khác case/format lạ sẽ
  bị C loại trong khi A (caller đảm bảo author) vẫn chốt.
- **S2 — `verify_receipt` nới lỏng hơn A.**
  A (qua `match_eye_records`) chỉ chấp nhận post_id ∈ want_ids hoặc tag exact.
  C `verify_receipt` (`:508-518`) chấp nhận `post_id in url` (substring URL,
  A không có) và passthrough `receipt.get("match") == "post_id"` — receipt tự
  khai match là được tin, không đối chiếu lại. Kẻ/phần mềm trả receipt giả với
  `match: post_id` + post_id nằm trong url sẽ pass mà không cần tag khớp hay
  known_ids. Đây là lỗ hổng tin-cậy, đi ngược "fail-closed" của C.
- **S3 — Owner-check rối, eye-record thật luôn trượt.**
  `:502-504`: receipts từ eye có key `author`, không có `owner` →
  `_normalize_account(None)` = `""` ≠ owner → cả hai vế AND đều true →
  `return None`. May là path list-receipt trong `reconcile()` không đi qua
  `verify_receipt` (đi `match_eye_records`), và Phase B tự gắn `owner` khi bọc
  hit (`:789`). Nhưng mọi caller ngoài nào đưa thẳng eye record vào
  `verify_receipt` đều fail-closed giả (từ chối đúng-nhưng-vì-sai-lý-do),
  che mất lỗi mapping key.
- **S4 — Tag extract chệch độ dài.**
  A `extract_tag`: `#dub` + đúng 6 số. C `Intent.from_item` (`:376`):
  `#dub\d+` bất kỳ độ dài + lower. Intent tag `#dub001` (3 số) không bao giờ
  do mắt A sinh ra, nhưng C match exact với eye tag `#dub...` 6 số → luôn
  miss → UNKNOWN oan cho shortcode ít số. Hai đầu không cùng alphabet tag.
- **S5 — `want_text` là tham số chết.**
  `match_eye_records(records, owner, want_tag, want_text, ...)` nhận
  `want_text` nhưng không dùng (đúng là A không có text fallback — giữ vậy là
  đúng), nhưng để tham số không dùng gây hiểu nhầm là có fallback text.
  Nên bỏ hoặc ghi rõ "giữ chỗ, cố ý không dùng".

## 3. Bug gốc của Dubtool (A) cần sửa/tối ưu — không copy mù

- **B1 — `has_video` fallback `document` gây false-positive.**
  `A:77-78`: `(closest('article') || document).querySelector('video')` —
  bài không có video nhưng trang có video ở bài khác vẫn `True`.
  Sửa: chỉ query trong article; không có article thì `False` (hoặc query từ
  `parentElement` đã dùng cho text, không bao giờ lên `document`).
- **B2 — `post_id` dính query/fragment.**
  `A:80`: `href.strip("/").split("/")[-1]` — URL dạng
  `/@u/post/abc?x=1` cho pid `abc?x=1`, không bao giờ khớp `want_ids` sạch →
  rớt xuống tag-match oan hoặc miss. Sửa: strip query/fragment trước split.
- **B3 — `TAG_RE` không boundary.**
  `#dub\d{6}` hit 6 số đầu của `#dub1234567` (7+ số) → tag chốt sai, có thể
  gán receipt nhầm giữa hai bài tag dài khác nhau ở 6 số đầu giống nhau.
  Sửa: `r"#dub\d{6}(?!\d)"`.
- **B4 — Locator hẹp, DOM Threads đổi là mù.**
  Chỉ `/post/` + `/t/`; thiếu `/p/` shortlink, thiếu bài quote/repost render
  link khác pattern. Ít nhất log (không suppress câm) số link/article để
  phát hiện mù sớm.
- **B5 — `suppress(Exception)` câm toàn bộ.**
  Locator fail, `get_attribute` fail, `evaluate` fail đều nuốt → trả `[]`,
  caller tưởng "chưa đăng" trong khi thực ra "chưa nhìn được". Nên đếm lỗi /
  trả kèm diagnostic (số link thử, số record OK) để não phân biệt
  "nhìn rồi, không có" vs "nhìn lỗi".
- **B6 — Không dedup + `limit` cắt mù.**
  Cùng 1 post có thể có nhiều `<a>` (media link, timestamp link) → records
  trùng post_id; `limit` cắt theo số link chứ không theo số bài → batch lớn
  có thể miss bài nằm ngoài cửa sổ. Sửa: dedup theo post_id/url, limit theo
  số record unique.
- **B7 — `text[:300]` có thể cắt mất tag** nếu caption dài + tag ở cuối
  (Threads 500 ký tự, tag thường append cuối — đúng case phổ biến!).
  `extract_tag` chạy trên `norm` full trước khi cắt nên tag field vẫn đúng,
  nhưng `text` preview mất tag gây khó debug. Nên giữ tag trong preview hoặc
  cắt giữ đầu+cuối.
- **B8 — Không verify author từ DOM.**
  `author` hardcode từ param `username`; nếu tab lạc sang account khác giữa
  chừng, mắt vẫn gán author cũ → não chốt receipt nhầm account. Mắt nên đọc
  author thật từ article (hoặc ít nhất truyền kèm page URL/account quan sát
  được để não từ chối khi lệch).

## 4. Checklist merge MẮT–NÃO cho C (đề xuất, chưa làm)

1. Implement `collect_eye_records(acquired_tab, owner)` thật trong C trên
   `ManagedChromeSession` (1 read duy nhất → parse per-article → PostRecords
   đúng hợp đồng §9), xóa path N-read ở worker/publisher Phase B.
2. Fix S2 (bỏ `match == "post_id"` passthrough, bỏ `post_id in url` khi không
   có known_ids), S3 (chấp nhận cả `author` key), S4 (thống nhất alphabet tag
   6-số hoặc document rõ), S5 (bỏ `want_text`).
3. Gửi B1–B8 về Dubtool (file riêng, không sửa A từ đây).
4. Regression test: fixture HTML 2 article (tag bài này + link bài kia) →
   assert không ghép chéo (same-record rule); test `#dub417888  ` trailing
   space; test `#dub1234567` không hit nhầm sau fix B3.

# HỎI-eye-01: collect_post_records chạy trên DOM Threads hiện tại còn đúng selector không

## Câu hỏi (bên hỏi: C)

- Khâu: mắt–não
- File C đang port: `apps/backend/src/miro/publishing/publisher.py` (`match_eye_records`), sắp port `collect_post_records`
- File A/B gốc: `C:\dubtool\core\rea_eye.py` (locator `/post/`, `/t/`, TAG_RE)
- Hỏi gì: A ghi B4 locator hẹp + B3 TAG_RE không boundary. Hỏi A: DOM Threads hôm nay (11/2026) còn selector nào khác chứa bài? Có nên mở rộng locator hay giữ hẹp để tránh false-positive? Tag `#dub\d+` A chốt đúng 6 số — bài tag ngắn/dài hơn xử lý sao?

## A (Dubtool) trả lời (bắt buộc — có thì đáp + file:dòng, không có thì ghi "không có")

- Đáp:
  - Locator hôm nay chỉ 2 pattern trong `C:\dubtool\core\rea_eye.py:67-68`: `a[href*="/@{user}/post/"]`, `a[href*="/@{user}/t/"]` — code hiện tại không còn selector nào khác chứa bài. Khung gom: bài = `closest('article') || parentElement` lấy `innerText` (:74-75); video = `closest('article')` có `querySelector('video')` (:77-78).
  - Giữ hẹp: đúng. Luật match same-record (`rea_eye.py:10-11`, `match_eye_records` :45-51: post_id trong `want_ids` trước, rồi tag exact sau normalize, cùng 1 record) vỡ ngay nếu locator rộng gom nhầm article. Nếu DOM Threads đổi, thêm locator mới + test "1 link = 1 article" thay vì nới bừa.
  - Tag: `TAG_RE = re.compile(r"#dub\d{6}")` (:18) — đúng 6 số. Tag ngắn/dài hơn → `extract_tag` trả `""` (:26-29) → nhánh tag trong `match_eye_records` (:49-51) bỏ qua, chỉ còn post_id-first (:45-48). Nghĩa là reconcile vẫn được nếu journal có `ack_post_codes`; mất tag thì coi như missing, không đoán.
- Bằng chứng file:dòng: `C:\dubtool\core\rea_eye.py:18, :26-29, :45-51, :67-68, :74-78`

## B (JARVIS) trả lời (bắt buộc — có thì đáp + file:dòng, không có thì ghi "không có")

- Đáp:
  - B không có selector DOM Threads — B chỉ bóc TikTok: `backend/app/agents/page_extract.py:44` dùng `document.querySelectorAll('a[href*="/video/"]')` lấy link `/video/` + text card, không có TAG_RE/boundary tag tương đương.
  - Kinh nghiệm cùng họ vấn đề: TikTok `__UNIVERSAL_DATA__.webapp` chứa ký tự vô hình làm dot-access trượt → B phải walk đệ quy theo `Object.keys` (`docs/notes/BUGS.md` dòng key 'webapp'). Gợi ý cho C: khi port `collect_post_records`, log selector nào trúng/miss trên DOM thật để A đối chiếu, thay vì mở rộng locator mù gây false-positive.
  - Về tag: B không có quy tắc tag, không ý kiến thêm — theo A.
- Bằng chứng file:dòng: `D:\JARVIS-Assistant\backend\app\agents\page_extract.py:44`

## C (Miro) trả lời (bắt buộc — tiếp nhận + kết luận port thế nào)

- Tiếp nhận đáp A/B: A chốt giữ locator hẹp 2 pattern + tag đúng 6 số + post_id-first khi mất tag; B không có Threads selector, gợi ý log trúng/miss thay vì nới mù — C nghe cả hai.
- Kết luận port + test + Checker: C giữ exact + same-record khi port `collect_post_records`; việc C nới regex `#dub\d+` (vòng 4 publisher) chấp nhận được để nuốt manifest test (`test-001` → `#dub001`), miễn vẫn exact sau `normalize_tag`, không substring. Thêm log selector trúng/miss theo gợi ý B. Chờ Checker duyệt.

## Trạng thái

- [ ] Đang hỏi (thiếu slot)
- [x] Đã đủ 3 slot, chờ port
- [ ] Đã port + test, chờ Checker
- [ ] XONG

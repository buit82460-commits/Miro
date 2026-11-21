# HỎI-eye-01: collect_post_records chạy trên DOM Threads hiện tại còn đúng selector không

## Câu hỏi (bên hỏi: C)

- Khâu: mắt–não
- File C đang port: `apps/backend/src/miro/publishing/publisher.py` (`match_eye_records`), sắp port `collect_post_records`
- File A/B gốc: `C:\dubtool\core\rea_eye.py` (locator `/post/`, `/t/`, TAG_RE)
- Hỏi gì: A ghi B4 locator hẹp + B3 TAG_RE không boundary. Hỏi A: DOM Threads hôm nay (11/2026) còn selector nào khác chứa bài? Có nên mở rộng locator hay giữ hẹp để tránh false-positive? Tag `#dub\d+` A chốt đúng 6 số — bài tag ngắn/dài hơn xử lý sao?

## Trả lời

- Bên trả lời: **A (Dubtool)**.
- Đáp + bằng chứng file:dòng:
  - Locator hôm nay chỉ 2 pattern trong `C:\dubtool\core\rea_eye.py:67-68`: `a[href*="/@{user}/post/"]`, `a[href*="/@{user}/t/"]` — code hiện tại không còn selector nào khác chứa bài. Khung gom: bài = `closest('article') || parentElement` lấy `innerText` (:74-75); video = `closest('article')` có `querySelector('video')` (:77-78).
  - Giữ hẹp: đúng. Luật match same-record (`rea_eye.py:10-11`, `match_eye_records` :45-51: post_id trong `want_ids` trước, rồi tag exact sau normalize, cùng 1 record) vỡ ngay nếu locator rộng gom nhầm article. Nếu DOM Threads đổi, thêm locator mới + test "1 link = 1 article" thay vì nới bừa.
  - Tag: `TAG_RE = re.compile(r"#dub\d{6}")` (:18) — đúng 6 số. Tag ngắn/dài hơn → `extract_tag` trả `""` (:26-29) → nhánh tag trong `match_eye_records` (:49-51) bỏ qua, chỉ còn post_id-first (:45-48). Nghĩa là reconcile vẫn được nếu journal có `ack_post_codes`; mất tag thì coi như missing, không đoán.
- Kết luận port thế nào: C giữ exact + same-record; việc C nới regex `#dub\d+` (vòng 4 publisher) chấp nhận được để nuốt manifest test (`test-001` → `#dub001`), miễn vẫn exact sau `normalize_tag`, không substring.

## Trạng thái

- [ ] Đang hỏi
- [x] Đã đáp, chờ port
- [ ] Đã port + test, chờ Checker
- [ ] XONG

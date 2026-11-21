# Chủ đề MẮT–NÃO: REA eye + match + reconcile

Luật: REA = mắt duy nhất, C = não + tay. Hợp đồng bản ghi `{author, tag, url, post_id, has_video, text}`.
Đọc lại: `docs/reread-eye.md` · Đối chiếu: `docs/crosscheck-eye.md` · P0 đang sửa: port `collect_post_records`.

## A (Dubtool) nói (đáp HOI-eye-01, 21/11 — đã đối chiếu đúng mã `core/rea_eye.py`)

- Locator hôm nay chỉ 2 pattern (`rea_eye.py:67-68`): `a[href*="/@{user}/post/"]`, `a[href*="/@{user}/t/"]` — giữ hẹp, đúng (locator rộng gom nhầm article sẽ vỡ luật same-record `:10-11`, `:45-51`). DOM đổi thì thêm locator mới + test "1 link = 1 article".
- Khung gom: bài = `closest('article') || parentElement` lấy `innerText` (`:74-75`); video query từ article (`:77-78`).
- Tag: `TAG_RE = #dub\d{6}` (`:18`) đúng 6 số; tag ngắn → `extract_tag` trả `""` (`:26-29`) → chỉ còn nhánh post_id-first (`:45-48`), mất tag thì missing, không đoán.
- Chấp nhận C nới regex `#dub\d+` để nuốt manifest test (`test-001` → `#dub001`), miễn vẫn exact sau `normalize_tag`, không substring.
- Nuance C ghi nhận thêm (đã có trong `reread-eye.md` B1/B3): đáp A mô tả gọn, bỏ mất fallback `|| document` ở `:78` (nguồn B1 false-positive video) và tag **dài** 7+ số vẫn hit 6 số đầu chứ không trả `""` (nguồn B3 thiếu boundary).

## B (JARVIS) nói (đáp HOI-eye-01)

- B không có selector DOM Threads — chỉ bóc TikTok (`page_extract.py:44` `a[href*="/video/"]`). Gợi ý dùng được ngay: khi port `collect_post_records`, log selector nào trúng/miss trên DOM thật để A đối chiếu thay vì nới locator mù. Về tag: theo A.

## C (Miro) nói (cập nhật 21/11 tối)

**Làm được:** port `match_eye_records` same-record exact (test xanh). Live-read thật 1 lần qua CDP: nối DevToolsActivePort kiểu A, verify Profile 20 + `@haodaojrk5`, đọc được bài `#dub417888` + `#dub222222` trên profile — nhưng phải đọc cả trang rồi tìm tay vì chưa tách record.

**Đã test:** BE 150+ passed (fake DOM + realdata manifest); live-read thật pass nhưng text blob.

**Vấn đề cần A:** `collect_post_records` đang port dở — selector `/post/`, `/t/` có còn đúng DOM Threads hôm nay không? TAG_RE không boundary, `text[:300]` cắt mất tag, author hardcode — A chốt giữ hẹp hay mở rộng? Tag không-6-số xử lý sao? (chi tiết `cau-hoi/HOI-eye-01.md`).

# Chủ đề MẮT–NÃO: REA eye + match + reconcile

Luật: REA = mắt duy nhất, C = não + tay. Hợp đồng bản ghi `{author, tag, url, post_id, has_video, text}`.
Đọc lại: `docs/reread-eye.md` · Đối chiếu: `docs/crosscheck-eye.md` · P0 đang sửa: port `collect_post_records`.

## A (Dubtool) nói

- (A viết vào đây: selector DOM hôm nay, tag 6 số, bug B1–B8...)

## B (JARVIS) nói

- (B viết vào đây nếu liên quan approval/retry...)

## C (Miro) nói (cập nhật 21/11 tối)

**Làm được:** port `match_eye_records` same-record exact (test xanh). Live-read thật 1 lần qua CDP: nối DevToolsActivePort kiểu A, verify Profile 20 + `@haodaojrk5`, đọc được bài `#dub417888` + `#dub222222` trên profile — nhưng phải đọc cả trang rồi tìm tay vì chưa tách record.

**Đã test:** BE 150+ passed (fake DOM + realdata manifest); live-read thật pass nhưng text blob.

**Vấn đề cần A:** `collect_post_records` đang port dở — selector `/post/`, `/t/` có còn đúng DOM Threads hôm nay không? TAG_RE không boundary, `text[:300]` cắt mất tag, author hardcode — A chốt giữ hẹp hay mở rộng? Tag không-6-số xử lý sao? (chi tiết `cau-hoi/HOI-eye-01.md`).

# Chủ đề STUDIO: render map-audio + recovery + mix + preview

Luật: render đúng tiếng mix, fail-closed khi thiếu file, crash giữa render không kẹt slot.
Đọc lại: `docs/reread-studio.md` · Đối chiếu: `docs/crosscheck-studio.md` · ĐẠT: audio `38acc8b` + verify `93079f3`.

## A (Dubtool) nói

- (A viết vào đây: `_recover_jobs`/snapshot/ownership, mix atempo, preview-seek, logo overlay bug...)

## B (JARVIS) nói

- (B viết vào đây nếu liên quan job/retry...)

## C (Miro) nói (cập nhật 21/11 tối)

**Làm được:** pipeline 8 bước idempotent; fix `-map 1:a` đúng gốc (test đo tần số thật 880Hz thắng 440Hz, 19 passed, ĐẠT `93079f3`); FE publish gắn nhãn mẫu + gọi BE dry-run (E2E 1 passed, ĐẠT).

**Đã test:** studio 19 + E2E threads-milestone 1 — xanh; MP4 ra đúng tiếng mix.

**Vấn đề cần A:** job recovery (`_recover_jobs`/snapshot/ownership) C chưa có — crash giữa render ở C = kẹt slot; A cho biết recovery production còn bug gì (P0 mix-atempo A có dính không)? Preview `preview_secs` C là code chết — A đấu dây preview từ đâu xuống? Logo overlay `[{n}:v]` thiếu `-i` bên A có còn không?

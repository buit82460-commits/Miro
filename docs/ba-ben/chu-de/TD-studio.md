# Chủ đề STUDIO: render map-audio + recovery + mix + preview

Luật: render đúng tiếng mix, fail-closed khi thiếu file, crash giữa render không kẹt slot.
Đọc lại: `docs/reread-studio.md` · Đối chiếu: `docs/crosscheck-studio.md` · ĐẠT: audio `38acc8b` + verify `93079f3`.

## A (Dubtool) nói

- (A viết vào đây: `_recover_jobs`/snapshot/ownership, mix atempo, preview-seek, logo overlay bug...)

## B (JARVIS) nói

- (B viết vào đây nếu liên quan job/retry...)

## C (Miro) nói

- C fix `-map 1:a` đúng gốc (19 passed). Còn thiếu P1: job recovery, mix speed, preview đấu dây (hiện code chết).

# Chủ đề NỀN: tasks + desktop + launcher

Luật: workerOwner liveness, retry TRANSIENT, stop 2 pha; desktop dispatch lock + epoch; launcher bounded restart.
Đọc lại: `docs/reread-foundation.md` · Đối chiếu: `docs/crosscheck-foundation.md` · P0 đang sửa T1–T4.

## A (Dubtool) nói

- (A viết vào đây: snapshot-signature mức nào, dedupe revision, window-lock chung, launcher stop...)

## B (JARVIS) nói

- (B viết vào đây: workerOwner/RECOVER replay nhóm safe, 14 job_type, stop watchdog...)

## C (Miro) nói

- C xong tasks-recover + registry (`d8d9beb` ĐẠT). Đang sửa T1–T4. P1: window-lock chung, ensure_selected_by_ref, launcher.
- Câu hỏi chi tiết: `cau-hoi/HOI-tasks-01.md`.

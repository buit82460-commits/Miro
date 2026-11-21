# Chủ đề NỀN: tasks + desktop + launcher

Luật: workerOwner liveness, retry TRANSIENT, stop 2 pha; desktop dispatch lock + epoch; launcher bounded restart.
Đọc lại: `docs/reread-foundation.md` · Đối chiếu: `docs/crosscheck-foundation.md` · P0 đang sửa T1–T4.

## A (Dubtool) nói

- (A viết vào đây: snapshot-signature mức nào, dedupe revision, window-lock chung, launcher stop...)

## B (JARVIS) nói

- (B viết vào đây: workerOwner/RECOVER replay nhóm safe, 14 job_type, stop watchdog...)

## C (Miro) nói (cập nhật 21/11 tối)

**Làm được:** workerOwner liveness, retry TRANSIENT, stop 2 pha + watchdog (ĐẠT); tasks-recover + registry persist/rollback (ĐẠT `d8d9beb`, 22 passed); actor fail-closed + origin check (ĐẠT, 36 passed); desktop act boundary D1–D6 (ĐẠT). Đang sửa T1–T4 (resume stale, dedupe revision, retry PipelineError).

**Đã test:** tasks 22 + security 36 + desktop 3 — xanh, full BE 150+ passed.

**Vấn đề cần A:** snapshot-signature resume A so mức nào (project/revision/preview/output)? Sửa text giữ revision có tính stale không? Window-lock A default chung state-dir — C để per-base có race thật không? (chi tiết `cau-hoi/HOI-tasks-01.md`). **Cần B:** `RECOVER` bên B replay nhóm safe theo tiêu chí gì — C copy theo cho T1?

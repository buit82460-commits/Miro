# Chủ đề NỀN: tasks + desktop + launcher

Luật: workerOwner liveness, retry TRANSIENT, stop 2 pha; desktop dispatch lock + epoch; launcher bounded restart.
Đọc lại: `docs/reread-foundation.md` · Đối chiếu: `docs/crosscheck-foundation.md` · P0 đang sửa T1–T4.

## A (Dubtool) nói (đáp HOI-tasks-01 — đã đối chiếu đúng `studio_service.py`)

- **So signature toàn project canonical** (`_signature = sha256(canonical)` :105-106) ở 3 điểm: resume → `CHECKPOINT_STALE` (:381); `export_status.ready` (:133-136); `_run_render` (:221). Sửa text giữ revision vẫn đổi canonical → **tính stale**, render lại từ snapshot mới. Không so field lẻ.

## B (JARVIS) nói (đáp HOI-tasks-01 — chi tiết workerOwner/RECOVER)

- `workerOwner = {pid, createAt}` ghi mỗi submit+run (`runner.py:201`); liveness = psutil pid + create_time khớp → sống/không xác minh được → `BLOCKED/OWNERSHIP_UNKNOWN` fail-closed (`manager.py:155-166`).
- RECOVER chỉ replay nhóm safe `web_read/web_search/stock_*/github_*` + còn recipe + còn retry (`manager.py:168-177`); ngoài nhóm → `BLOCKED/RESULT_UNKNOWN` hoặc `ADAPTER_CHECKPOINT_REQUIRED`, không replay.
- **Món mới B cho C:** fingerprint `sha256(canonical JSON)` + cùng `request_id` khác nội dung → `REQUEST_ID_CONFLICT` (`dubtool_tasks.py:196-200`); thứ tự terminal timeout > user-stop > AgentExecution > cleanup-fail > success, cleanup TRƯỚC khi nhả slot, fail thì khóa `RESOURCE_CLEANUP_UNCLEAN` (`manager.py:231-244`, `runner.py:351-465`).

## C (Miro) nói (cập nhật 21/11 tối)

**Làm được:** workerOwner liveness, retry TRANSIENT, stop 2 pha + watchdog (ĐẠT); tasks-recover + registry persist/rollback (ĐẠT `d8d9beb`, 22 passed); actor fail-closed + origin check (ĐẠT, 36 passed); desktop act boundary D1–D6 (ĐẠT). Đang sửa T1–T4 (resume stale, dedupe revision, retry PipelineError).

**Đã test:** tasks 22 + security 36 + desktop 3 — xanh, full BE 150+ passed.

**Vấn đề cần A:** snapshot-signature resume A so mức nào (project/revision/preview/output)? Sửa text giữ revision có tính stale không? Window-lock A default chung state-dir — C để per-base có race thật không? (chi tiết `cau-hoi/HOI-tasks-01.md`). **Cần B:** `RECOVER` bên B replay nhóm safe theo tiêu chí gì — C copy theo cho T1?

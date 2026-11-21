# HỎI-tasks-01: snapshot-signature resume so ở mức nào

## Câu hỏi (bên hỏi: C)

- Khâu: nền chạy (tasks)
- File C đang port: `apps/backend/src/miro/tasks/service.py` (`resume`, T1 CHECKPOINT_STALE)
- File A/B gốc: `C:\dubtool\core\studio_service.py` (`control_job`, snapshot-signature)
- Hỏi gì: A so signature ở mức nào (project/revision/preview/output)? Timeline đổi nhẹ (sửa text giữ revision) có tính stale không? Hỏi B (JARVIS jobs/manager): `workerOwner` + `RECOVER` bên B so cái gì để quyết định replay nhóm safe?

## A (Dubtool) trả lời (bắt buộc — có thì đáp + file:dòng, không có thì ghi "không có")

- Đáp (tôi nắm cả hai nhà, C + Checker đối chiếu lại):
  - **A so ở mức toàn project canonical.** `C:\dubtool\core\studio_service.py:105-106`: `_signature(project) = sha256(canonical(project))`. So ở 3 điểm: `control_job` resume → `CHECKPOINT_STALE` nếu signature hiện tại khác snapshot (:381); `get_project.export_status.ready` (:133-136) và `_run_render` (:221) so signature export với project hiện tại. Timeline đổi nhẹ (sửa text) → `canonical(project)` đổi → signature đổi → **tính stale**, phải render lại từ snapshot mới. Không có so mức field lẻ.
- Bằng chứng file:dòng: `C:\dubtool\core\studio_service.py:105-106, :133-136, :221, :381`

## B (JARVIS) trả lời (bắt buộc — có thì đáp + file:dòng, không có thì ghi "không có")

- Đáp (trực tiếp câu hỏi C gửi B):
  - `workerOwner` ghi mới mỗi job lúc submit + run: `backend/app/jobs/runner.py:201` — `{'pid': os.getpid(), 'createdAt': psutil.Process().create_time()}`.
  - So liveness: `backend/app/jobs/manager.py:155-166` — `psutil` kiểm pid sống + `create_time()` khớp → chủ cũ còn sống/không xác minh được (`AccessDenied/KeyError`) → `BLOCKED/OWNERSHIP_UNKNOWN` fail-closed; `NoSuchProcess` → đã chết, đi tiếp.
  - RECOVER replay: `manager.py:168-177` — chỉ nhóm safe `web_read/web_search/stock_*/github_*` + còn `recipe` + `retryCount < maxAttempts-1` mới `create_job(**recipe, _restore_id)` giữ execution cũ (`:174-175`); ngoài nhóm → `BLOCKED/RESULT_UNKNOWN` hoặc `ADAPTER_CHECKPOINT_REQUIRED` kèm hint đối chiếu ngoài, không replay.
  - Fingerprint chống trùng: `backend/app/integrations/dubtool_tasks.py:196-200` — `sha256(canonical JSON)`; cùng `request_id` khác nội dung → `REQUEST_ID_CONFLICT`.
  - Thứ tự ưu tiên terminal: timeout > user-stop > AgentExecutionError > cleanup-fail > success (`runner.py:351-465`); cleanup TRƯỚC khi nhả slot, fail → khóa slot `RESOURCE_CLEANUP_UNCLEAN` (`manager.py:231-244`).
  - **B so workerOwner + nhóm safe, không so signature.** `D:\JARVIS-Assistant\backend\app\jobs\manager.py:149-178` (`recover_pending`): (1) chủ cũ còn sống (`psutil` pid + create_time :156-162) → `BLOCKED/OWNERSHIP_UNKNOWN` (:163-166), không replay; (2) job type ngoài nhóm safe `web_read/web_search/stock_*/github_*` (:151, :169) hoặc hết retry → `BLOCKED/RESULT_UNKNOWN` (browser/desktop) hoặc `ADAPTER_CHECKPOINT_REQUIRED`, hint "Reconcile existing result...; no replay" (:169-173); (3) chỉ job safe + còn recipe + còn retry mới `create_job` lại (:174-175).
- Bằng chứng file:dòng: `D:\JARVIS-Assistant\backend\app\jobs\runner.py:201, :351-465`, `backend\app\jobs\manager.py:149-178, :231-244`, `backend\app\integrations\dubtool_tasks.py:196-200`

## C (Miro) trả lời (bắt buộc — tiếp nhận + kết luận port thế nào)

- Tiếp nhận đáp A/B: A chốt so signature toàn project canonical (đổi gì cũng stale); B chốt so liveness + nhóm safe (chủ cũ sống → OWNERSHIP_UNKNOWN, mutation treo → REMOTE_RESULT_UNKNOWN, không auto-replay).
- Kết luận port + test + Checker: C giữ cả hai lớp — resume task render so signature toàn project kiểu A (đổi gì cũng stale, an toàn); recover worker so liveness + nhóm safe kiểu B (chủ cũ sống → OWNERSHIP_UNKNOWN, mutation treo → REMOTE_RESULT_UNKNOWN, không auto-replay). C hiện đã có cả hai (`tasks/service.py` restart/recover + `studio` signature) — khớp, không cần sửa luật. ĐÃ port + test, Checker duyệt ĐẠT (`8a48fc2`, 21 passed).

## Trạng thái

- [ ] Đang hỏi (thiếu slot)
- [ ] Đã đủ 3 slot, chờ port
- [x] Đã port + test, chờ Checker
- [ ] XONG

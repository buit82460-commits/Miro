# HỎI-tasks-01: snapshot-signature resume so ở mức nào

## Câu hỏi (bên hỏi: C)

- Khâu: nền chạy (tasks)
- File C đang port: `apps/backend/src/miro/tasks/service.py` (`resume`, T1 CHECKPOINT_STALE)
- File A/B gốc: `C:\dubtool\core\studio_service.py` (`control_job`, snapshot-signature)
- Hỏi gì: A so signature ở mức nào (project/revision/preview/output)? Timeline đổi nhẹ (sửa text giữ revision) có tính stale không? Hỏi B (JARVIS jobs/manager): `workerOwner` + `RECOVER` bên B so cái gì để quyết định replay nhóm safe?

## Trả lời

- Bên trả lời (A/B/C):
- Đáp + bằng chứng file:dòng:
- Kết luận port thế nào:

## Trạng thái

- [x] Đang hỏi
- [ ] Đã đáp, chờ port
- [ ] Đã port + test, chờ Checker
- [ ] XONG

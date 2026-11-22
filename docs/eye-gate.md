# Eye Gate — Evidence không phải giấy phép vĩnh viễn

Mọi thao tác WRITE (`gateway.write_via_adapter`) phải qua gate này TRƯỚC
mỗi lần bấm. Evidence cũ không được tái dùng khi trạng thái đã đổi.

## Gate kiểm tra trước mỗi WRITE (fail-closed)

1. **Nguồn gốc:** `evidence.provenance == "rea-eye"`. Snapshot ngoài
   Gateway (`browser_snapshot` trực tiếp) không phải Evidence.
2. **Đúng instance:** `evidence.instance_id == session.runtime.instance_id`.
   Khác instance → `EVIDENCE_WRONG_INSTANCE`, dừng.
3. **Đúng tab:** `evidence.tab_id == acquired.record.targetId`. Tab A
   không dùng cho tab B (`EVIDENCE_TAB_MISMATCH`).
4. **Tươi:** `now - observed_at <= 300`s. Cũ hơn → `EVIDENCE_STALE`,
   mắt đọc lại.
5. **Đúng actor:** `verify_actor(page)` hiện tại == `evidence.actor`
   (và == `expectedAccountId` nếu có). Đổi account giữa chừng →
   `WORKER_STOPPED: ACCOUNT_MISMATCH`, lease bị invalidate.
6. **Đúng URL:** tab hiện tại cùng destination với `evidence.url`
   (`_urls_same_destination`). Tab đã navigate đi nơi khác →
   `TAB_ORIGIN_CHANGED`, dừng.
7. **Quyền còn hiệu lực:** `store.validate(lease)` pass. Lease hết hạn /
   bị revoke → `LeaseLost` → dừng, không replay.
8. **Approval theo task:** `approval == {approved: True, ...}` khớp đúng
   task (không dùng approval task khác).

## Checker

- Chỉ kiểm tra Evidence tương ứng với tác vụ trong commit (không bắt
  mọi commit đều có eye-record).
- Commit thiếu gate-check cho WRITE mới → từ chối.
- Không coi `evidence_id` một mình là đủ: phải đủ 8 điểm trên.

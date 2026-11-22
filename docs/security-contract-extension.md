# Security Contract — Extension Bridge ↔ Gateway (Phiên B cấp, Phiên A tích hợp)

Phiên bản: 2026-11-22. Phạm vi: read-only trước, WRITE sau khi E2E PASS.
Không sửa `experiments/extension-bridge/` (của Phiên A).

## 1. Danh tính (identity)

| Trường | Nguồn sự thật | Ghi chú |
|---|---|---|
| `extensionId` | Chrome Web Store / self-host key | Pairing 1 lần, user xác nhận tường minh |
| `browserInstanceId` | `gateway` = sha256(endpoint đã verify `/json/version`) | Extension KHÔNG tự khai instance; Gateway đối chiếu |
| `tabId` | CDP `targetId` | Khớp `tab_resource(instance, target)` trong LeaseStore |
| `actor` | `_verify_actor` trên page thật | Event extension báo actor = dữ liệu chưa tin cậy |
| `taskId` | caller + intent | Approval gắn đúng task, không tái dùng |
| `capability` | `read` \| `write:<adapter>` | Pairing thành công KHÔNG cấp write |
| `approval` | `{approved: True, taskId, fingerprint/revision}` | Thiếu/sai task → WRITE_DENIED |

## 2. Đường dữ liệu

- Event từ extension (URL/title/tabId) = **dữ liệu chưa tin cậy**, KHÔNG phải
  Evidence. Chỉ thành Evidence sau `read_via_eye` (REA + eye collector xác
  minh trên tab thật, đúng instance/actor/tab/tươi).
- Extension không được yêu cầu Gateway tin bất kỳ `evidence_id`/URL/actor
  nào do extension tự tạo.

## 3. Điều kiện READ qua extension transport

1. Pairing còn hiệu lực (grant ≤120s, `requestId` chống replay).
2. Tab thuộc instance đã verify + profile đã bind `chrome://version`.
3. Eye collector đọc được trên page thật (không chỉ tin event).

## 4. Điều kiện WRITE (chặt hơn READ)

Đủ 8 điểm `docs/eye-gate.md` (provenance/instance/tab/tươi/actor/URL/lease/
approval) + 3 điểm bổ sung:

9. `capability` chứa đúng `write:<adapter>` cho task này.
10. Lease còn hiệu lực TRƯỚC và SAU `adapter_fn` (mất giữa chừng →
    `UNCONFIRMED_NO_REPLAY`, giữ UNKNOWN, journal attempt, không replay).
11. Idempotency: `intent_id` đã có journal `submitted/verified` → skip,
    không bấm lại (guard trong `miro/publishing/publisher.py`).

## 5. Giao diện transport Phiên A phải cung cấp

```python
# Phiên B (Gateway) gọi — Phiên A implement:
async def discover_tabs() -> list[dict]:
    """[{tabId, url, title}] — read-only, không DOM, không WRITE."""

async def read_tab(tab_id: str) -> dict:
    """Trả page-handle thật để eye collector đọc (không trả DOM tự parse)."""

async def close_transport() -> None:
    """Ngắt transport, invalidate lease, không tắt Chrome."""
```

Cấm: transport tự tạo tab, tự navigate, tự click/type/evaluate, tự cấp
quyền, tự tạo Evidence.

## 6. Ma trận kiểm thử E2E (fake transport, chưa đụng Chrome thật)

- [ ] Pairing hết hạn → READ bị từ chối.
- [ ] Event báo actor X nhưng page thật actor Y → Evidence bị bỏ.
- [ ] Hai agent tranh 1 tab → 1 owner, agent kia TAB_BUSY (T24).
- [ ] Lease mất giữa WRITE → UNKNOWN, không replay (T20/T25).
- [ ] Extension báo tabId instance khác → từ chối cross-instance (T23).
- [ ] Replay cùng `requestId` → từ chối.

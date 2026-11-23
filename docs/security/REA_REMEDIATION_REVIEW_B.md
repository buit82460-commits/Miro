# Phiên B review remediation B1/B2/B3/W3 (2026-11-22)

Không sửa code Phiên A. Chỉ đọc + chạy unit. Không push. Không live /read-result.

## Kết quả chạy lại (unit, PowerShell `;`)

- `test_read_grant.py` — 7/7 PASS (B1 gesture-loại, seq-replay, grant flow, read_spec, B3 poisoning, W3 incomplete, channel cấm WRITE)
- `test_reconcile.py` — 4/4 PASS
- `test_channel.py`, `test_e2e.py`, `test_security.py`, `test_registry.py`, `test_importer.py` — PASS, không vỡ
- `test_negative_http.py` — chưa chạy live (chờ duyệt live theo chỉ thị); logic đã đọc, khớp với code server

## B1 — gesture tự khai báo → PASS (remediation đạt)

- `bridge/grants.py:33-34` `grant()` không còn tham số `gesture` (xác minh bằng `inspect.signature` ở `tests/test_read_grant.py:25-31`).
- `bridge/server.py:166-191` `/grant` không đọc `gesture`; đòi `grant_seq > last_seq` (`GRANT_REPLAY` nếu không), đòi tab tồn tại trong registry (`TAB_UNKNOWN`), đòi origin allowlist qua `GRANTS.grant`.
- `extension/background.js:103-133` tự kiểm active tab trước khi xin grant (`NOT_ACTIVE_TAB` nếu không đúng), gửi `grant_seq = cfg.seq + 1`, chỉ tăng seq khi backend ok.
- Replay: `grants.py:31,53-56` `_used_grant_seq` chặn reuse cùng (instance, tab, seq) + test `test_grant_seq_replay` PASS.
- Tồn dư (đã khai báo, chấp nhận ở spike): kiểm active-tab là ở client; backend vẫn tin session + registry + allowlist. Kẻ có session token vẫn tự POST `/grant` được (đã giảm bằng seq đơn điệu + TTL 120s). Chưa có chữ ký gesture từ Chrome — không quảng cáo grant là "user gesture đã xác minh" trong Evidence.

## B2 — origin check tại thời điểm đọc → PASS có lưu ý

- `grants.py:66-85` `check()` so `live_origin` exact-match với `grant.origin`; mismatch → thu hồi grant ngay + `ORIGIN_MISMATCH`. Test origin-mismatch-thu-hồi PASS.
- `server.py:229-233` `/read-result` dùng `live_origin` do extension gửi kèm, không dùng URL registry cũ. Kèm `SEQ_REPLAY` check (`:234-239`) và `BAD_RESULT` khi payload không phải dict.
- `background.js:137-157` kiểm live URL trước/sau đọc (`before` từ `tabs.query`, `after` từ `tabs.get`); khác nhau → `NAVIGATION_RACE`, từ chối, không gửi `/read-result`.
- Lưu ý: `/read` (`server.py:192-215`) vẫn `GRANTS.check` bằng `rec.url` (registry, async) và chỉ trả `AUTHORIZED`, không trả dữ liệu. Chấp nhận được vì enforcement thật nằm ở `/read-result` + background race-check; nhưng nên thắt tiếp (bỏ `/read` authorize bằng URL cũ hoặc bắt `live_origin` ngay ở `/read`) trước khi nối Evidence.

## B3 — tách kênh read-result khỏi registry → PASS

- `server.py:216-252` `/read-result` mới: lưu `OBSERVATIONS[(instance, tab, seq)]` với `untrusted: True`, cắt field (`title/url/text/description/h1`, mỗi field ≤2000 ký tự), không gọi `import_outbox`/`registry.apply`.
- `background.js:158-164` gửi DOM qua `/read-result` riêng, không đổ vào `/push`.
- `importer.py:10-28` không đổi — chỉ nhận event vòng đời tab, không có đường nhận DOM.
- Test `B3 registry không bị DOM poisoning` PASS: DOM độc (`<script>`, cookie) không lọt vào registry.
- Tồn dư: `OBSERVATIONS` là dict RAM, mất khi restart server — đúng spike, chưa persistent. Dữ liệu vẫn `untrusted` — chưa nối `read_via_eye` + `_verify_actor`.

## W3 — `complete` mặc định → PASS

- `server.py:144-148` `/resync` thiếu `complete is True` → trả `{stale: [], removed: []}`, không xóa.
- `registry.py:69-82` `reconcile_snapshot` fail-closed khi `not complete` / generation replay.
- Test W3 + `test_reconcile.py` (incomplete/replay/restart/out-of-order) PASS.

## Chốt Phiên B

- 4/4 remediation đạt ở tầng unit/integration (bridge). Cho phép Phiên A **live `/read-result`** trên Profile 20 theo đúng giới hạn: chỉ `title`, chỉ tab đã grant, giữ `untrusted`, chưa nối Evidence, chưa WRITE.
- Sau live, Phiên B đối chiếu log hai đầu rồi mới duyệt nối `read_via_eye` + `_verify_actor`.
- 3 adapter freelance giữ `UNSUPPORTED` WRITE.

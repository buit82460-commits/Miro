# SECURITY INTEGRATION REPORT (Phiên B)

Tiếp tục từ `2d7047d`. Không sửa `experiments/extension-bridge/`.
Không sửa `.bat`, không restart/kill Chrome, không push.

## 1. Task 1 — MCP / Harness Allowlist (P0)

**Phát hiện:** không tồn tại file cấu hình OpenCode/MCP/harness trong repo
(`C:\Miro` không có `opencode.json*`, `mcp*.json*`, allowlist nào).
`.playwright-mcp/` chỉ chứa log/console snapshot của phiên dev, không phải
config. Quyền cấp tool nằm ở tầng harness ngoài repo — **không thể khóa bằng
repository, chỉ báo cáo để quản trị áp dụng**.

**Đã làm trong repo:**

- `test_no_direct_browser.py`: pattern mở rộng full 27 tool bypass/profile
  (`snapshot/console/network/screenshot/tabs/find/resize` read +
  `click/type/evaluate/run_code_unsafe/navigate(+back)/fill/select/upload/
  press_key/drag/drop/hover/wait_for/dialog/close` write). CI fail nếu
  production code gọi trực tiếp.
- `gateway.deny_direct_browser()`: runtime từ chối khi code đi đường tắt.
- `docs/harness-allowlist-report.md` (từ phiên trước, vẫn hiệu lực):
  production chỉ giữ `tools.rea.*` read-only + WRITE qua code Gateway;
  loại 81 entries (27 tool × 3 profile); subagent cùng allowlist.

**Chưa khóa (cần quản trị harness):** agent vẫn gọi được MCP tool trực tiếp
nếu phiên còn cấp. Không tuyên bố đã khóa runtime — mới khóa đường code.

**Đường vòng qua shell/code:** `Shell`/subagent/`execute` có thể chạm Chrome
(CDP/curl/port-file). Trong repo không cấp quyền đó cho production agent;
harness phải giới hạn shell của production agent (read-only hoặc cấm hẳn).

## 2. Task 2 — Browser Instance Trust (P0)

**Đã khóa bằng code:**

- Bỏ auto-trust legacy: `runtime.acquire_tab` — profile thiếu
  `browserInstanceId` → `PROFILE_UNVERIFIED` (trước đây tự gán instance hiện
  tại = lỗ hổng tin instance chưa verify). Seed test legacy đã sửa theo
  (gán đúng `runtime.instance_id` trong seed, không nới gate).
- Profile bind instance khác → `PROFILE_UNVERIFIED`, bắt rebind
  `chrome://version` trên đúng instance.
- `ensure_session`: khóa endpoint đã verify, truyền thẳng vào `open`,
  đối chiếu sau connect (chống TOCTOU port-file đổi giữa inspect/connect).
- Test: T18 (sai instance), T22 (legacy không auto-trust),
  T23 (cross-instance tab không dùng chung).

## 3. Task 3 — WRITE / Lease / Receipt Safety (P0)

**Đã khóa bằng code:**

- `read_via_eye`: validate lại lease + destination + verify lại actor SAU khi
  eye đọc (T19: navigate giữa lúc đọc → bỏ evidence; T21: task đòi account
  mà không verify được → `EVIDENCE_UNVERIFIED`).
- `write_via_adapter`: gate 8 điểm trước + validate lại lease SAU adapter
  (T20 invalidate giữa write, T25 lease hết hạn giữa write → receipt vô
  hiệu → `UNCONFIRMED_NO_REPLAY`, giữ UNKNOWN, không replay).
- Idempotency/replay: `miro/publishing/publisher.py` đã có
  `claim_attempt` O_CREAT|O_EXCL + `guard_duplicate` + journal
  submit/unknown + reconcile (không đụng, tái dùng cho contract §4.11).
- Hai agent tranh 1 tab: lease single-owner → agent 2 `TAB_BUSY`, release
  xong agent 2 mới acquire được (T24).

## 4. Task 4 — Security Contract với Phiên A (P1)

`docs/security-contract-extension.md`: extension identity, 8+3 điều kiện
WRITE (capability + lease trước/sau + idempotency), event = dữ liệu chưa tin
cậy (chỉ thành Evidence sau `read_via_eye`), transport interface Phiên A
phải cung cấp (`discover_tabs/read_tab/close_transport`), ma trận E2E fake
transport. Không sửa implementation Phiên A.

## 5. Task 5 — Verification

- Gateway + allowlist: **25 passed** (`test_browser_gateway.py` T1–T25 +
  `test_no_direct_browser.py`).
- Full suite: **310 passed, 2 skipped** (`python -m pytest tests -q`
  trong `C:\Miro\apps\backend`).
- Không sửa `.bat`, không restart/kill Chrome, không push.
- Commit riêng Phiên B sau khi full suite PASS (kiểm tra `git diff --cached`
  trước commit để không lẫn thay đổi Phiên A/unrelated).

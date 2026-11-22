# Harness allowlist report — khóa MCP runtime cho production agent

Ngày: 2026-11-22. Phạm vi: agent production làm việc trên Miro (Profile 20).

## Kết luận

- Trong repo đã khóa: production code không gọi browser trực tiếp
  (`test_no_direct_browser.py` quét `browser_*(` thật, CI fail nếu vi phạm).
- Trong repo KHÔNG khóa được: agent gọi MCP tool trực tiếp trong phiên
  (`playwright-profile20.browser_snapshot/click/...`). Phải khóa ở tầng
  harness (allowlist per-agent), không phải bằng docs/prompt trong repo.

## Danh sách tool phải LOẠI khỏi allowlist production agent

READ (đọc nhưng là đường bypass, phải qua `read_via_eye` + eye collector):

- `browser_snapshot`, `browser_console_messages`, `browser_network_request`,
  `browser_network_requests`, `browser_take_screenshot`, `browser_tabs`,
  `browser_find`, `browser_resize`, `browser_emulate_media`

WRITE / SIDE-EFFECT (có thể gây side-effect, gồm cả evaluate):

- `browser_click`, `browser_type`, `browser_evaluate`,
  `browser_run_code_unsafe`, `browser_navigate`, `browser_navigate_back`,
  `browser_fill_form`, `browser_select_option`, `browser_file_upload`,
  `browser_press_key`, `browser_drag`, `browser_drop`, `browser_hover`,
  `browser_wait_for`, `browser_handle_dialog`, `browser_close`

Áp dụng cho cả 3 profile: `playwright-profile1`, `playwright-profile16`,
`playwright-profile20` (27 tool × 3 = 81 entries).

Lưu ý `evaluate` / `run_code_unsafe`: tên nghe như đọc nhưng có thể gây
side-effect (JS click/submit/navigate) — xếp vào nhóm WRITE, cấm tuyệt đối.

## Được GIỮ cho production agent

- `tools.rea.*` read-only: `inspect_web_page`, `observe_web_session`,
  `list_browser_targets`, `capture_web_screenshot`,
  `inspect_web_network_capture`, `export_web_scripts` (đọc),
  `analyze_web_bundle` (đọc).
- `tools.rea.capture_browser_scenario`: chỉ cho khi task recon được duyệt,
  read-only, không side-effect; rốt production đăng bài thì cấm luôn.
- Mọi WRITE đi qua code `miro/browser/gateway.py::write_via_adapter`
  (không phải tool MCP): evidence tươi + gate 8 điểm + approval đúng task.

## Subagent

Cùng allowlist. Subagent mới không được cấp thêm tool ngoài danh sách trên.

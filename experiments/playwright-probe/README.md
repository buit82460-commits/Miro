# Spike: playwright-probe (nối Playwright MCP qua extension)

## Mục tiêu

Chứng minh cách liệt kê tab Chrome Profile 20 qua Playwright MCP
(`@playwright/mcp --extension --profile-dir-name "Profile 20"`)
bằng JSON-RPC `tools/call browser_tabs list`, để trinh sát read-only.

Nguồn: `C:\dubtool\poc-playwright\probe-mcp-tabs.py`,
`probe-mcp-full.py`, `server-a.cjs` (port gọn, bỏ token thật).

## Kết quả: GIỮ (công cụ)

- Legacy: probe gửi `initialize` + `tools/call browser_tabs list`,
  đọc stdout tới khi có response id tương ứng, timeout 120s.
  Token lấy từ config local (`PLAYWRIGHT_MCP_EXTENSION_TOKEN`),
  **không commit token**.
- `server-a.cjs` là trang synthetic local (`127.0.0.1:18770/health`)
  để test readback — không phải site thật.

## Quyết định

**GIỮ làm công cụ trinh sát read-only.** Dùng khi cần đọc tab thật
(verify thủ công), không dùng để publish tự động.

## Ảnh hưởng code chính

- `workers/browser/` — cách nối Playwright MCP này là tham chiếu cho
  worker browser (list tab → snapshot → đọc). Hiện tại worker là
  khung rỗng → **chưa ảnh hưởng**, chỉ tham khảo khi triển khai.
- Không ảnh hưởng `apps/`, `services/`, `contracts/`.
- Không lưu token/cookie vào repo. Token đọc từ env/config local lúc chạy.

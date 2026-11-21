# Experiments

Thư mục thử nghiệm (spike) của Miro. Quy ước lấy từ legacy
(`C:\dubtool\spikes`, `D:\JARVIS-Assistant\spikes`).

## Quy ước spike

- Mỗi thử nghiệm = **1 thư mục** riêng: `experiments/<ten-spike>/`.
- Mỗi thư mục spike **bắt buộc** có `README.md` với 3 mục:
  1. **Mục tiêu** — muốn chứng minh/kiểm chứng điều gì.
  2. **Kết quả** — `GIỮ` / `BỎ` / `CHƯA RÕ`, kèm bằng chứng ngắn gọn.
  3. **Quyết định giữ/bỏ** — giữ thì ghi rõ **ảnh hưởng code chính**
     (module nào trong `apps/`, `workers/`, `services/`), bỏ thì ghi lý do.
- Spike là **docs + mã gọn minh họa**. Không venv, không binary,
  không media, không secret/token/cookie.
- Mã trong spike **không được import vào code chính**. Muốn dùng thì
  port có review qua nhánh `merge/*`, không copy-paste nguyên bản.

## Danh mục

| Spike | Nguồn legacy | Trạng thái | Ảnh hưởng code chính |
|---|---|---|---|
| `chrome-extension-v1/` | `C:\dubtool\spikes\chrome-extension-v1` | GIỮ (mô hình) | `workers/browser` — mô hình grant/command |
| `playwright-probe/` | `C:\dubtool\poc-playwright` | GIỮ (công cụ) | `workers/browser` — cách nối Playwright MCP |
| `yt-dlp/` | `D:\JARVIS-Assistant\spikes\yt_dlp` | GIỮ (có điều kiện) | `workers/media`, `services/youtube` — tải nguồn |

Spike đã BỎ (ghi nhận để khỏi làm lại):

- `chrome-extension-v2` — BLOCKED, không phải MV3 loadable được,
  không nối production. Xem README v2 trong legacy.
- `chrome-extension-v21` — native pipe FAIL trên môi trường thử,
  Chrome/Extension UNVERIFIED. Chờ staging duyệt, chưa port.
- `browser_use` (`D:\JARVIS-Assistant\spikes\browser_use`) — chưa kiểm
  chứng chạy thật (mở browser, gọi model, pause/resume thực tế);
  chi phí LLM theo bước, không có hook duyệt trước action.
  Chỉ xem lại khi `workers/browser` cần agent LLM điều khiển browser.
- `tiktok_api` — thăm dò API chưa đủ kết luận, chưa port.

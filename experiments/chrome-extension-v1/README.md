# Spike: chrome-extension-v1 (mô hình grant/command)

## Mục tiêu

Chứng minh mô hình điều khiển extension an toàn trên trang synthetic
local: controller cấp **grant theo tab** (tabBindingId + session + expiry),
mọi lệnh `command` phải đối chiếu grant, session, replay — mặc định từ chối.

Nguồn: `C:\dubtool\spikes\chrome-extension-v1\controller.cjs`
(port gọn, chỉ giữ khung grant/command; bỏ pipe Windows, pairing, UI).

## Kết quả: GIỮ (mô hình)

- Legacy: V1 controller + fixture local PASS (30/30 regression trong
  báo cáo V2.1); chạy trên loopback `127.0.0.1:18766`, fixture `/fixture`.
- Chưa chứng minh trên site mạng xã hội thật — adapter ngoài
  synthetic chưa tồn tại. Không suy ra "điều khiển được Facebook".

## Quyết định

**GIỮ mô hình, BỎ mã nguyên bản.** Khi `workers/browser` cần điều khiển
tab đã được user cấp quyền tường minh, áp dụng lại 4 quy tắc này:

1. Grant gắn `profileBinding + session + tabBinding + expiry` (≤ 120s).
2. Mỗi `command` kiểm tra lại grant + session, từ chối mặc định.
3. `requestId` chống replay trong session.
4. Chỉ allowlist action (`readDOM`/`fill`/`click` nút đánh dấu/`detach`),
   không click/publish tổng quát.

## Ảnh hưởng code chính

- `workers/browser/` — nếu thêm chế độ "tab đã cấp quyền", mô hình
  grant/command này là tham chiếu. Hiện tại worker chưa có → **chưa
  ảnh hưởng**, chỉ tham khảo.
- Không ảnh hưởng `apps/`, `services/`, `contracts/`.
- Không cài đặt extension này vào Chrome thật, không đăng ký registry.

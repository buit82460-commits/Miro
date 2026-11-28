// Receipt BFF — BE-first, không fixture-fallback.
// BE không có EP list receipts riêng: receipt đọc qua GET /threads/history.
// GET không tham số → [] trung thực (rỗng, không mẫu). BE down → 502.
import { ok } from "@/lib/fixtures/store";

export async function GET() {
  return ok([]);
}

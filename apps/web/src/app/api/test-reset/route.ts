import { ok, resetFixture } from "@/lib/fixtures/store";

// Chỉ dùng cho E2E/dev: reset fixture về seed ban đầu.
// Đặt tên không gạch dưới đầu vì Next.js coi thư mục `_`/`__` là private.
export async function POST() {
  resetFixture();
  return ok({ reset: true });
}

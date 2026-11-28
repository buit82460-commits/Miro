import { ok, resetFixture } from "@/lib/fixtures/store";

// Chỉ dùng cho E2E/dev: reset fixture về seed ban đầu.
// Đặt tên không gạch dưới đầu vì Next.js coi thư mục `_`/`__` là private.
//
// QUYẾT ĐỊNH AN TOÀN (FE-D): khi có API_BASE thật (production nối BE),
// route này bị DISABLE để không ai xóa nhầm state fixture dùng test.
// Fixture reset chỉ còn tác dụng khi chạy fixture nội bộ (không env).
export async function POST() {
  const hasRealBackend = Boolean((process.env.NEXT_PUBLIC_API_BASE ?? "").trim());
  if (hasRealBackend) {
    return Response.json(
      { success: false, error: "test-reset bi khoa khi co API_BASE that (an toan production)" },
      { status: 403 },
    );
  }
  resetFixture();
  return ok({ reset: true });
}

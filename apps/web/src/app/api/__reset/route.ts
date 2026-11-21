import { ok, resetFixture } from "@/lib/fixtures/store";

// Chỉ dùng cho E2E/dev: reset fixture về seed ban đầu.
export async function POST() {
  resetFixture();
  return ok({ reset: true });
}

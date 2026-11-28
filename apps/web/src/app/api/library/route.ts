import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// GET /api/library — BE-first, fail-closed (BUG-01).
// BE chưa có route /library production: BE reachable nhưng 404 → forward
// nguyên trạng để FE hiện empty/error state trung thực. BE down → 503,
// KHÔNG trả fixture projects giả gây hiểu nhầm.
export async function GET() {
  const be = await beFetch("/library");
  if (be.ok) return beForward(be.status, be.body);
  return beUnavailable("BE_LIBRARY_UNAVAILABLE");
}

import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// GET /api/health — BE-first, fail-closed như mọi BFF khác (BUG-14).
// BE reachable (kể cả 4xx/5xx) → forward nguyên trạng.
// BE down → 503 BE_UNREACHABLE, KHÔNG trả 200 fixture "ok" gây hiểu nhầm.
export async function GET() {
  const be = await beFetch("/health");
  if (be.ok) return beForward(be.status, be.body);
  return beUnavailable();
}

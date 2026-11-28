import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// GET /api/platforms — passthrough BE GET /platforms (contract §04 PLAT-01..06, READY).
// BE sở hữu registry; BE down → 503 fail-closed, FE ẩn card platform.
export async function GET() {
  const be = await beFetch("/platforms");
  if (!be.ok) return beUnavailable();
  return beForward(be.status, be.body);
}

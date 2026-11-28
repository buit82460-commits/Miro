import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// POST /api/research/search — passthrough BE POST /research/search (contract §04 RES-01..06).
// BE sở hữu state; BE down → 503 fail-closed, không bịa kết quả.
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { query?: unknown; limit?: unknown };
  const be = await beFetch("/research/search", {
    method: "POST",
    body: JSON.stringify({
      query: typeof body.query === "string" ? body.query : "",
      limit: typeof body.limit === "number" ? body.limit : 10,
    }),
  });
  if (!be.ok) return beUnavailable();
  return beForward(be.status, be.body);
}

import { beFetch, beForward, beUnavailable, pickParams } from "@/lib/be-proxy";

// GET /api/connections/accounts — passthrough BE GET /connections/accounts.
// BE sở hữu state; BE down → 503 fail-closed.
export async function GET(req: Request) {
  const q = pickParams(new URL(req.url), ["platform", "status"]);
  const be = await beFetch(`/connections/accounts${q}`);
  if (!be.ok) return beUnavailable();
  return beForward(be.status, be.body);
}

// POST /api/connections/accounts — passthrough BE POST /connections/accounts.
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const be = await beFetch("/connections/accounts", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!be.ok) return beUnavailable();
  return beForward(be.status, be.body);
}

import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// POST /api/research/read — passthrough BE POST /research/read (contract §04 RES-01..06).
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { url?: unknown };
  const be = await beFetch("/research/read", {
    method: "POST",
    body: JSON.stringify({ url: typeof body.url === "string" ? body.url : "" }),
  });
  if (!be.ok) return beUnavailable();
  return beForward(be.status, be.body);
}

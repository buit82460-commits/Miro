import { beFetch, beForward, beUnavailable, pickParams } from "@/lib/be-proxy";

// GET /api/tasks/recent — BE-first. Fallback: [] (BE sở hữu state, không bịa task).
export async function GET(req: Request) {
  const q = pickParams(new URL(req.url), ["limit"]);
  const be = await beFetch(`/tasks/recent${q}`);
  if (be.ok) return beForward(be.status, be.body);
  return beUnavailable();
}

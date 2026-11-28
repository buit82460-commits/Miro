import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// GET /api/connections/accounts/{id} — passthrough BE.
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const be = await beFetch(`/connections/accounts/${encodeURIComponent(id)}`);
  if (!be.ok) return beUnavailable();
  return beForward(be.status, be.body);
}

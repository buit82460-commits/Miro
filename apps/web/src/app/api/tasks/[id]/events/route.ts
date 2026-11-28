import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// GET /api/tasks/[id]/events — poll 1-2s tu FE (BE khong SSE).
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const be = await beFetch(`/tasks/${encodeURIComponent(id)}/events`);
  if (be.ok) return beForward(be.status, be.body);
  return beUnavailable();
}

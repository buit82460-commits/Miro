import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// GET /api/tasks/[id] — chi tiet task BE.
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const be = await beFetch(`/tasks/${encodeURIComponent(id)}`);
  if (be.ok) return beForward(be.status, be.body);
  return beUnavailable();
}

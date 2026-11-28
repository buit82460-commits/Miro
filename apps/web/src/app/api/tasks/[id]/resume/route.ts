import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// POST /api/tasks/[id]/resume — BE-first.
export async function POST(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const be = await beFetch(`/tasks/${encodeURIComponent(id)}/resume`, { method: "POST" });
  if (be.ok) return beForward(be.status, be.body);
  return beUnavailable();
}

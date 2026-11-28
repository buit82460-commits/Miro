import { beFetch, beForward, beUnavailable, pickParams } from "@/lib/be-proxy";

// POST /api/tasks/[id]/revoke?item= — thu hoi approval (RAM-only).
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const q = pickParams(new URL(req.url), ["item"]);
  const be = await beFetch(`/tasks/${encodeURIComponent(id)}/revoke${q}`, { method: "POST" });
  if (be.ok) return beForward(be.status, be.body);
  return beUnavailable();
}

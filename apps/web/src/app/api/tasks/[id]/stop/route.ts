import { beFetch, beForward, beUnavailable, pickParams } from "@/lib/be-proxy";

// POST /api/tasks/[id]/stop — BE-first. 409/422 forward nguyen (fail-closed).
// BE down → 503, không cập nhật store mẫu.
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const q = pickParams(new URL(req.url), ["grace_seconds"]);
  const be = await beFetch(`/tasks/${encodeURIComponent(id)}/stop${q}`, { method: "POST" });
  if (be.ok) return beForward(be.status, be.body);
  return beUnavailable();
}

import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// GET /api/studio/media/[id] — passthrough BE GET /studio/media/{video_id} (contract §04 STUDIO).
// 404 = chưa có media → FE hiện empty state.
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const be = await beFetch(`/studio/media/${encodeURIComponent(id)}`);
  if (!be.ok) return beUnavailable();
  return beForward(be.status, be.body);
}

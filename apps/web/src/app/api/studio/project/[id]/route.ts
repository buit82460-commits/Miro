import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// GET /api/studio/project/[id] — passthrough BE GET /studio/project/{video_id} (contract §04 STUDIO).
// 404 = chưa có project thật → FE hiện empty state + CTA tạo từ BE.
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const be = await beFetch(`/studio/project/${encodeURIComponent(id)}`);
  if (!be.ok) return beUnavailable();
  return beForward(be.status, be.body);
}

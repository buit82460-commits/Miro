import { beFetch, beForward, beUnavailable, pickParams } from "@/lib/be-proxy";

// POST /api/tasks/[id]/approve?item=&scope=&revision=
// Approval RAM-only, scope+revision+fingerprint bind — mat sau restart BE,
// UI phai co luồng duyet-lai + warn. Forward 409 (TASK_NOT_FOUND/APPROVAL_*).
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const q = pickParams(new URL(req.url), ["item", "scope", "revision"]);
  const be = await beFetch(`/tasks/${encodeURIComponent(id)}/approve${q}`, { method: "POST" });
  if (be.ok) return beForward(be.status, be.body);
  return beUnavailable();
}

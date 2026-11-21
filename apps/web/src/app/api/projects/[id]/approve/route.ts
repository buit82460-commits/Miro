import { fail, getStore, ok, pushHistory } from "@/lib/fixtures/store";

export async function POST(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const p = getStore().projects.find((x) => x.id === id);
  if (!p) return fail("Không tìm thấy project", 404);
  if (!p.render || p.render.preview) {
    return fail("Cần render bản cuối trước khi duyệt", 422);
  }
  p.approved = true;
  p.revision += 1;
  const task = getStore().tasks.find((t) => t.status === "awaiting_review" || t.status === "running");
  if (task) task.status = "approved";
  pushHistory("approve", `${id} đã duyệt r${p.revision}`);
  return ok(p);
}

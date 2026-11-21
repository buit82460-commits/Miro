import { fail, getStore, now, ok, pushHistory } from "@/lib/fixtures/store";

export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const task = getStore().tasks.find((t) => t.id === id);
  if (!task) return fail("Không tìm thấy task", 404);
  const body = (await req.json().catch(() => ({}))) as { decision?: string; note?: string };
  if (body.decision === "approve") task.status = "approved";
  else if (body.decision === "reject") task.status = "queued";
  else if (body.decision === "stop") task.status = "stopped";
  else return fail("decision chưa hợp lệ", 422);
  task.updated_at = now();
  pushHistory("review", `${id} -> ${task.status}`);
  return ok(task);
}

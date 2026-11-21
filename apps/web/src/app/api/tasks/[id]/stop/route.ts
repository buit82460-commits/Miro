import { fail, getStore, now, ok, pushHistory } from "@/lib/fixtures/store";

export async function POST(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const task = getStore().tasks.find((t) => t.id === id);
  if (!task) return fail("Không tìm thấy task", 404);
  task.status = "stopped";
  task.updated_at = now();
  pushHistory("stop", `dừng ${id}`);
  return ok(task);
}

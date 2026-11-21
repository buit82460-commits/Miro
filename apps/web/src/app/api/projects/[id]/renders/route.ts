import { fail, getStore, nextId, ok, pushHistory } from "@/lib/fixtures/store";

export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const p = getStore().projects.find((x) => x.id === id);
  if (!p) return fail("Không tìm thấy project", 404);
  const body = (await req.json().catch(() => ({}))) as { preview?: boolean };
  const job = { job_id: nextId("job"), status: body.preview ? "preview_done" : "render_done", preview: !!body.preview };
  p.render = job;
  p.revision += 1;
  pushHistory("render", `${id} ${job.job_id} preview=${job.preview}`);
  return ok({ ...p, job });
}

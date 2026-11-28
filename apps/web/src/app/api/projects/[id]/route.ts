import { fail, getStore, ok } from "@/lib/fixtures/store";
import { tryBe } from "@/lib/be";

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const be = await tryBe(`/projects/${encodeURIComponent(id)}`);
  if (be) return be;
  const p = getStore().projects.find((x) => x.id === id);
  if (!p) return fail("Không tìm thấy project", 404);
  return ok(p);
}

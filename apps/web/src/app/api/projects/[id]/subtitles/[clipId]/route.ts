import { fail, getStore, ok, pushHistory } from "@/lib/fixtures/store";

export async function PUT(req: Request, ctx: { params: Promise<{ id: string; clipId: string }> }) {
  const { id, clipId } = await ctx.params;
  const p = getStore().projects.find((x) => x.id === id);
  if (!p) return fail("Không tìm thấy project", 404);
  const patch = (await req.json().catch(() => ({}))) as { start?: number; end?: number; text?: string };
  if (typeof patch.text !== "string" || !patch.text.trim()) return fail("Nhập nội dung phụ đề", 422);
  let found = false;
  for (const t of p.tracks) {
    const clip = t.clips.find((c) => c.id === clipId);
    if (clip) {
      found = true;
      clip.text = patch.text;
      if (typeof patch.start === "number") clip.start = patch.start;
      if (typeof patch.end === "number" && typeof patch.start === "number") {
        clip.duration = Math.max(0.5, patch.end - patch.start);
      }
    }
  }
  if (!found) return fail("Không tìm thấy clip phụ đề", 404);
  p.revision += 1;
  pushHistory("subtitle", `${id}/${clipId} -> r${p.revision}`);
  return ok(p);
}

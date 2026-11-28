import { fail, getStore, ok, pushHistory } from "@/lib/fixtures/store";
import { tryBe } from "@/lib/be";

// 1 lần thả = 1 command có revision. Sai revision -> 409 để FE refetch.
// BE chỉ hỗ trợ update_subtitle/move_clip — op lạ BE trả 422, BFF forward nguyên.
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const body = (await req.json().catch(() => ({}))) as {
    operation?: Record<string, unknown>;
    expected_revision?: number;
  };
  const be = await tryBe(`/projects/${encodeURIComponent(id)}/operations`, {
    method: "POST",
    body,
  });
  if (be) return be;
  const p = getStore().projects.find((x) => x.id === id);
  if (!p) return fail("Không tìm thấy project", 404);
  if (!body.operation || typeof body.operation.type !== "string") {
    return fail("operation chưa hợp lệ", 422);
  }
  if (body.expected_revision !== undefined && body.expected_revision !== p.revision) {
    return Response.json(
      { success: false, error: `Lệch revision: gửi ${body.expected_revision}, hiện tại ${p.revision}` },
      { status: 409 },
    );
  }
  const op = body.operation;
  if (op.type === "update_subtitle") {
    const clipId = String(op.clip_id ?? "");
    for (const t of p.tracks) {
      const clip = t.clips.find((c) => c.id === clipId);
      if (clip) {
        if (typeof op.text === "string") clip.text = op.text;
        if (typeof op.start === "number") clip.start = op.start;
        if (typeof op.duration === "number") clip.duration = op.duration;
      }
    }
  } else if (op.type === "move_clip") {
    const clipId = String(op.clip_id ?? "");
    if (typeof op.start === "number") {
      for (const t of p.tracks) {
        const clip = t.clips.find((c) => c.id === clipId);
        if (clip) clip.start = op.start as number;
      }
    }
  } else {
    return fail("operation chưa hỗ trợ (chỉ update_subtitle/move_clip)", 422);
  }
  p.revision += 1;
  if (op.type === "update_subtitle") {
    pushHistory("subtitle", `${id}/${String(op.clip_id ?? "")} -> r${p.revision}`);
  } else {
    pushHistory("command", `${id} ${String(op.type)} -> r${p.revision}`);
  }
  return ok(p);
}

import { beFetch, beForward, beUnavailable, pickParams } from "@/lib/be-proxy";
import { fail } from "@/lib/fixtures/store";

// Compat: POST /api/tasks/[id]/review {decision: approve|reject|stop}
// → BE approve (scope=edit) / revoke / stop. 409/422 forward nguyen.
// BE down → 502/503 fail-closed, không cập nhật store mẫu.
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const body = (await req.json().catch(() => ({}))) as { decision?: string; note?: string };
  const enc = encodeURIComponent(id);
  const q = pickParams(new URL(req.url), ["item", "scope", "revision"]);

  if (body.decision === "approve") {
    const scope = new URL(req.url).searchParams.get("scope") ?? "edit";
    const rev = new URL(req.url).searchParams.get("revision") ?? "1";
    const be = await beFetch(`/tasks/${enc}/approve?item=0&scope=${encodeURIComponent(scope)}&revision=${encodeURIComponent(rev)}`, { method: "POST" });
    if (be.ok) return beForward(be.status, be.body);
  } else if (body.decision === "reject") {
    const be = await beFetch(`/tasks/${enc}/revoke${q}`, { method: "POST" });
    if (be.ok) return beForward(be.status, be.body);
  } else if (body.decision === "stop") {
    const be = await beFetch(`/tasks/${enc}/stop`, { method: "POST" });
    if (be.ok) return beForward(be.status, be.body);
  } else {
    return fail("decision chưa hợp lệ", 422);
  }

  return beUnavailable();
}

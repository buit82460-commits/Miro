import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// POST /api/connections/accounts/{id}/{action} — passthrough BE-first.
// Actions: verify | pause | reconnect | revoke | default.
// CẤM /mock/verify-tab ở production (chỉ test).
const ACTIONS = ["verify", "pause", "reconnect", "revoke", "default"] as const;

export async function POST(req: Request, ctx: { params: Promise<{ id: string; action: string }> }) {
  const { id, action } = await ctx.params;
  if (!(ACTIONS as readonly string[]).includes(action)) {
    return Response.json({ success: false, error: `Action không hỗ trợ: ${action}` }, { status: 404 });
  }
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const be = await beFetch(`/connections/accounts/${encodeURIComponent(id)}/${action}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!be.ok) return beUnavailable();
  return beForward(be.status, be.body);
}

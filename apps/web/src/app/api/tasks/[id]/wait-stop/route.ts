import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// WATCHDOG stop: doi worker thoat trong grace, het grace buoc STOPPED.
// Body/query: grace_seconds (default BE 10s).
export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const grace = (body.grace_seconds as number | undefined)
    ?? new URL(req.url).searchParams.get("grace_seconds") ?? undefined;
  const q = grace !== undefined ? `?grace_seconds=${encodeURIComponent(String(grace))}` : "";
  const be = await beFetch(`/tasks/${encodeURIComponent(id)}/wait-stop${q}`, { method: "POST" });
  if (be.ok) return beForward(be.status, be.body);
  return beUnavailable();
}

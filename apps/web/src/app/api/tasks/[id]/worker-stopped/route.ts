import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

function passthrough(suffix: string) {
  return async function POST(_req: Request, ctx: { params: Promise<{ id: string }> }) {
    const { id } = await ctx.params;
    const url = new URL(_req.url);
    const q = url.search;
    const be = await beFetch(`/tasks/${encodeURIComponent(id)}/${suffix}${q}`, { method: "POST" });
    if (be.ok) return beForward(be.status, be.body);
    return beUnavailable();
  };
}

// Stop 2-phase + watchdog + restart/resume — BE-first, fail-closed 503 khi BE down.
// UNKNOWN → reconcile-readonly, KHONG tu replay.
export const POST = passthrough("worker-stopped");

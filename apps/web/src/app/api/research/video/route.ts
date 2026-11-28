import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// POST /api/research/video — passthrough BE POST /research/video (contract §04 RES-01..06).
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { url?: unknown; include_frames?: unknown };
  const be = await beFetch("/research/video", {
    method: "POST",
    body: JSON.stringify({
      url: typeof body.url === "string" ? body.url : "",
      include_frames: body.include_frames === true,
    }),
  });
  if (!be.ok) return beUnavailable();
  return beForward(be.status, be.body);
}

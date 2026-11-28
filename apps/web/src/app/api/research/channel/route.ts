import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// POST /api/research/channel — passthrough BE POST /research/channel (contract §04 RES-01..06).
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { channel_url?: unknown; max_videos?: unknown };
  const be = await beFetch("/research/channel", {
    method: "POST",
    body: JSON.stringify({
      channel_url: typeof body.channel_url === "string" ? body.channel_url : "",
      max_videos: typeof body.max_videos === "number" ? body.max_videos : 10,
    }),
  });
  if (!be.ok) return beUnavailable();
  return beForward(be.status, be.body);
}

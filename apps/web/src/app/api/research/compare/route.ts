import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// POST /api/research/compare — passthrough BE POST /research/compare (contract §04 RES-01..06).
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as {
    url_a?: unknown;
    url_b?: unknown;
    include_frames?: unknown;
  };
  const be = await beFetch("/research/compare", {
    method: "POST",
    body: JSON.stringify({
      url_a: typeof body.url_a === "string" ? body.url_a : "",
      url_b: typeof body.url_b === "string" ? body.url_b : "",
      include_frames: body.include_frames === true,
    }),
  });
  if (!be.ok) return beUnavailable();
  return beForward(be.status, be.body);
}

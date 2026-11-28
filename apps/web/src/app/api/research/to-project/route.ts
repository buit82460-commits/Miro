import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// POST /api/research/to-project — passthrough BE POST /research/to-project (contract §04).
// BE trả 503 TASK_SERVICE_UNAVAILABLE khi chưa cấu hình task_service → forward nguyên trạng.
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as {
    request_id?: unknown;
    title?: unknown;
    source_url?: unknown;
    transcript?: unknown;
  };
  const be = await beFetch("/research/to-project", {
    method: "POST",
    body: JSON.stringify({
      request_id: typeof body.request_id === "string" ? body.request_id : "",
      title: typeof body.title === "string" ? body.title : "",
      source_url: typeof body.source_url === "string" ? body.source_url : "",
      transcript: typeof body.transcript === "string" ? body.transcript : "",
    }),
  });
  if (!be.ok) return beUnavailable();
  return beForward(be.status, be.body);
}

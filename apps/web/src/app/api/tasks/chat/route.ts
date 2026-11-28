import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";
import { fail } from "@/lib/fixtures/store";

// Compat: POST /api/tasks/chat → BE POST /tasks/run-message (NL entry).
// Body cu {message, task_id?} → {message, tab_id:0}. BE tra {ok,error,route,task_id,...}.
// TAB_UNKNOWN/NO_ROUTE_MATCH van co task_id → UI poll task, KHONG tu post lai.
// GET: forward BE /tasks/recent; BE down → 503, không trả fixture mẫu.
export async function GET() {
  const be = await beFetch("/tasks/recent?limit=20");
  if (be.ok) return beForward(be.status, be.body);
  return beUnavailable();
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { message?: string; task_id?: string };
  if (!body.message || body.message.length > 4000) return fail("Nội dung chat chưa hợp lệ", 422);
  const be = await beFetch("/tasks/run-message", {
    method: "POST",
    body: JSON.stringify({ message: body.message, tab_id: 0 }),
  });
  if (be.ok) return beForward(be.status, be.body);
  // BE down → 503 fail-closed, không bịa task fixture.
  return beUnavailable();
}

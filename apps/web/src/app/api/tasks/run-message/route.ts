import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// POST /api/tasks/run-message — body {message, tab_id:int, live_origin?, limit?}.
// Tra ve {ok, error, route, task_id, evidence}. TAB_UNKNOWN → 200 ok:false + task_id,
// UI hien banner fail-closed, KHONG tu post lai.
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const be = await beFetch("/tasks/run-message", { method: "POST", body: JSON.stringify(body) });
  if (be.ok) return beForward(be.status, be.body);
  return beUnavailable();
}

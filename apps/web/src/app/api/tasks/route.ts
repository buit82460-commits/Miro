import { beFetch, beForward, beUnavailable, pickParams } from "@/lib/be-proxy";
import { getStore, nextId, now, ok, pushHistory } from "@/lib/fixtures/store";

// GET /api/tasks — compat alias BE GET /tasks (read-only). Fallback fixture.
export async function GET(req: Request) {
  const q = pickParams(new URL(req.url), ["limit"]);
  const be = await beFetch(`/tasks${q}`);
  if (be.ok) return beForward(be.status, be.body);
  return ok(getStore().tasks);
}

// POST /api/tasks — tao task that: BE POST /tasks 202 (+fire-and-forget run).
// Body BE: {request_id, message, videos[{title, project_id|source}], ...}.
// UI duoc phep gui gon {message, videos?, request_id?}; BFF bu shape toi thieu.
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const be = await beFetch("/tasks", { method: "POST", body: JSON.stringify(body) });
  if (be.ok) return beForward(be.status, be.body);

  // Fallback fixture (BE down): giu shape cu, khong bia trang thai BE.
  const message = typeof body.message === "string" ? body.message : "";
  if (!message.trim() || message.length > 4000) {
    return Response.json(
      { success: false, error: "Nội dung task chưa hợp lệ (1-4000 ký tự)" },
      { status: 422 },
    );
  }
  const task = {
    id: nextId("task"),
    title: message.slice(0, 80),
    status: "queued" as const,
    revision: 1,
    updated_at: now(),
  };
  getStore().tasks.unshift(task);
  pushHistory("create", `tạo ${task.id} (fixture, BE unreachable)`);
  return ok(task, 201);
}

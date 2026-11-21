import { fail, getStore, nextId, ok, pushHistory } from "@/lib/fixtures/store";

function now() {
  return new Date().toISOString();
}

export async function GET() {
  return ok(getStore().tasks);
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { message?: string; task_id?: string };
  if (!body.message || body.message.length > 4000) return fail("Nội dung chat chưa hợp lệ", 422);
  const nowIso = now();
  if (body.task_id) {
    const t = getStore().tasks.find((x) => x.id === body.task_id);
    if (!t) return fail("Không tìm thấy task", 404);
    t.status = "running";
    t.updated_at = nowIso;
    pushHistory("chat", `chat tiếp vào ${t.id}`);
    return ok(t, 200);
  }
  const task = {
    id: nextId("task"),
    title: body.message.slice(0, 80),
    status: "running" as const,
    revision: 1,
    updated_at: nowIso,
  };
  getStore().tasks.unshift(task);
  pushHistory("chat", `tạo ${task.id} từ chat`);
  return ok(task, 201);
}

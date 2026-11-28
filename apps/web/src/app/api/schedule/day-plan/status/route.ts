// FE-B · BFF ghép PATCH /schedule/day-plan/status (active|paused).
import { beDetail, beFetch } from "@/lib/threads/be";
import { fail, ok } from "@/lib/fixtures/store";

export async function PATCH(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { status?: string };
  const value = String(body.status ?? "").toLowerCase();
  if (value !== "active" && value !== "paused")
    return fail("status phải là active|paused", 422);
  const be = await beFetch("/schedule/day-plan/status", {
    method: "PATCH",
    body: JSON.stringify({ status: value }),
  });
  if (!be.reachable) return fail("BE_UNREACHABLE: không nối được BE.", 502);
  if (be.status >= 400) return fail(beDetail(be.status, be.data), be.status);
  return ok(be.data, 200);
}

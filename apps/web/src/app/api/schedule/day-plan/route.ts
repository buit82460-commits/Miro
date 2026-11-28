// FE-B · BFF ghép GET /schedule/day-plan (404 NO_DAY_PLAN → FE hiện empty state + CTA ensure).
import { beDetail, beFetch } from "@/lib/threads/be";
import { fail, ok } from "@/lib/fixtures/store";

export async function GET() {
  const be = await beFetch("/schedule/day-plan");
  if (!be.reachable) return fail("BE_UNREACHABLE: không nối được BE.", 502);
  if (be.status === 404) return fail("NO_DAY_PLAN: chưa có day-plan. Bấm “Ensure day-plan”.", 404);
  if (be.status >= 400) return fail(beDetail(be.status, be.data), be.status);
  return ok(be.data, 200);
}

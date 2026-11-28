// FE-B · BFF ghép POST /schedule/ensure (caller-driven, READY).
import { beDetail, beFetch } from "@/lib/threads/be";
import { fail, ok } from "@/lib/fixtures/store";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const be = await beFetch("/schedule/ensure", {
    method: "POST",
    body: JSON.stringify({
      policy: (body.policy as Record<string, unknown>) ?? {},
      new_items: (body.new_items as unknown[]) ?? [],
      carryover: (body.carryover as unknown[]) ?? [],
      date_str: (body.date_str as string | null) ?? null,
      was_clean_shutdown: body.was_clean_shutdown ?? true,
    }),
  });
  if (!be.reachable) return fail("BE_UNREACHABLE: không nối được BE. Chưa ensure plan.", 502);
  if (be.status >= 400) return fail(beDetail(be.status, be.data), be.status);
  return ok(be.data, 200);
}

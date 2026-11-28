// FE-B · BFF ghép POST /publications + GET /publications/{id} (idempotent, READY).
import { beDetail, beFetch } from "@/lib/threads/be";
import { fail, ok } from "@/lib/fixtures/store";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  if (!body.publication_id) return fail("Thiếu publication_id", 422);
  if (!body.attempt_id) return fail("Thiếu attempt_id", 422);
  if (!body.render_id) return fail("Thiếu render_id", 422);
  if (!body.channel) return fail("Thiếu channel", 422);
  const be = await beFetch("/publications", { method: "POST", body: JSON.stringify(body) });
  if (!be.reachable) return fail("BE_UNREACHABLE: không nối được BE.", 502);
  if (be.status >= 400) return fail(beDetail(be.status, be.data), be.status);
  return ok(be.data, 201);
}

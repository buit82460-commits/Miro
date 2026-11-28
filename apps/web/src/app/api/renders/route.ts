// FE-B · BFF ghép POST /renders + GET /renders/{id} (idempotent record, READY).
import { beDetail, beFetch } from "@/lib/threads/be";
import { fail, ok } from "@/lib/fixtures/store";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  if (!body.request_id) return fail("Thiếu request_id (idempotent key)", 422);
  if (!body.project_id) return fail("Thiếu project_id", 422);
  if (typeof body.expected_revision !== "number" || (body.expected_revision as number) < 0)
    return fail("Thiếu expected_revision (>= 0)", 422);
  if (!body.content_hash) return fail("Thiếu content_hash", 422);
  const be = await beFetch("/renders", { method: "POST", body: JSON.stringify(body) });
  if (!be.reachable) return fail("BE_UNREACHABLE: không nối được BE. Chưa tạo render.", 502);
  if (be.status === 409) return fail(`REQUEST_ID_CONFLICT: ${beDetail(be.status, be.data)}`, 409);
  if (be.status >= 400) return fail(beDetail(be.status, be.data), be.status);
  return ok(be.data, 201);
}

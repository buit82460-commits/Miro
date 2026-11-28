// FE-B · BFF ghép POST /threads/approve (duyệt intent bound fingerprint+revision).
import { beDetail, beFetch } from "@/lib/threads/be";
import { fail, ok } from "@/lib/fixtures/store";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  if (!body.text || typeof body.text !== "string" || !body.text.trim())
    return fail("Nhập nội dung text", 422);
  if (!body.owner) return fail("Thiếu owner (tài khoản đăng)", 422);
  if (!body.shortcode) return fail("Thiếu shortcode", 422);
  if (typeof body.revision !== "number" || (body.revision as number) < 0)
    return fail("Thiếu revision (>= 0)", 422);
  const be = await beFetch("/threads/approve", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!be.reachable) return fail("Không nối được BE. Chưa duyệt gì.", 502);
  if (be.status >= 400) return fail(beDetail(be.status, be.data), be.status);
  return ok(be.data, 200);
}

// FE-B · BFF ghép POST /threads/reconcile (read-only, UNKNOWN không replay).
import { beDetail, beFetch } from "@/lib/threads/be";
import { fail, ok } from "@/lib/fixtures/store";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  if (!body.text || !body.owner || !body.shortcode)
    return fail("Thiếu text/owner/shortcode để reconcile", 422);
  const be = await beFetch("/threads/reconcile", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!be.reachable) return fail("BE_UNREACHABLE: không nối được BE. Chưa đối soát.", 502);
  if (be.status >= 400) return fail(beDetail(be.status, be.data), be.status);
  return ok(be.data, 200);
}

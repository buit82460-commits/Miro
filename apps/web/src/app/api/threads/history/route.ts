// FE-B · BFF ghép GET /threads/history (asset↔render↔post + journals, không suy đoán).
import { beDetail, beFetch } from "@/lib/threads/be";
import { fail, ok } from "@/lib/fixtures/store";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const publication_id = url.searchParams.get("publication_id") ?? "";
  const render_id = url.searchParams.get("render_id") ?? "";
  if (!publication_id || !render_id)
    return fail("Thiếu publication_id/render_id", 422);
  const be = await beFetch(
    `/threads/history?publication_id=${encodeURIComponent(publication_id)}&render_id=${encodeURIComponent(render_id)}`,
  );
  if (!be.reachable) return fail("BE_UNREACHABLE: không nối được BE.", 502);
  if (be.status >= 400) return fail(beDetail(be.status, be.data), be.status);
  return ok(be.data, 200);
}

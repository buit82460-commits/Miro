// FE-B · BFF ghép BE thật cho luồng Threads (prepare → approve → publish dry-run).
// Chạy server-side qua MIRO_BE_BASE. Khi BE unreachable → 502 fail-closed, không tự chế receipt.
import { beDetail, beFetch } from "@/lib/threads/be";
import { fail, ok } from "@/lib/fixtures/store";

type PrepareBody = {
  asset_path?: string;
  project_id?: string;
  request_id?: string;
  expected_revision?: number;
  content_hash?: string;
  spec?: Record<string, unknown>;
  tags?: string[];
};

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as PrepareBody;
  if (!body.asset_path) return fail("Chọn asset_path (đường dẫn file media)", 422);
  if (!body.project_id) return fail("Thiếu project_id", 422);
  if (!body.request_id) return fail("Thiếu request_id (idempotent key)", 422);
  if (typeof body.expected_revision !== "number" || body.expected_revision < 0)
    return fail("Thiếu expected_revision (>= 0)", 422);
  if (!body.content_hash) return fail("Thiếu content_hash", 422);
  const be = await beFetch("/threads/prepare", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!be.reachable) return fail("Không nối được BE (MIRO_BE_BASE). Chưa prepare gì.", 502);
  if (be.status >= 400) return fail(beDetail(be.status, be.data), be.status);
  return ok(be.data, 201);
}

import { fail, getStore, ok, pushHistory } from "@/lib/fixtures/store";
import { rollbackSchema } from "@/lib/schemas/miro.schema";

// Rollback registry về version cũ hơn — giữ nguyên task đang chạy (task pin version).
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { version?: unknown };
  const parsed = rollbackSchema.safeParse(body);
  if (!parsed.success) {
    return fail(parsed.error.issues[0]?.message ?? "Version rollback chưa hợp lệ", 422);
  }
  const store = getStore();
  if (parsed.data.version >= store.registryVersion) {
    return fail(`Registry đang ở v${store.registryVersion}, chỉ rollback về version nhỏ hơn`, 422);
  }
  store.registryVersion = parsed.data.version;
  pushHistory("platform", `rollback registry -> v${parsed.data.version} (giữ task cũ)`);
  return ok({ version: store.registryVersion, platforms: store.platforms });
}

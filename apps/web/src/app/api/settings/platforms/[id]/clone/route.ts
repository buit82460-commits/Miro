import { fail, getStore, ok, pushHistory } from "@/lib/fixtures/store";
import { platformCloneSchema } from "@/lib/schemas/miro.schema";

export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const body = (await req.json().catch(() => ({}))) as { new_id?: string };
  const parsed = platformCloneSchema.safeParse(body);
  if (!parsed.success) {
    return fail(parsed.error.issues[0]?.message ?? "Dữ liệu nhân bản chưa hợp lệ", 422);
  }
  const store = getStore();
  const src = store.platforms.find((p) => p.id === id);
  if (!src) return fail("Không tìm thấy platform", 404);
  const newId = parsed.data.new_id || `${src.id}-copy`;
  if (store.platforms.some((p) => p.id === newId)) {
    return fail(`Đã có platform ${newId}`, 409);
  }
  store.platforms.push({
    ...(JSON.parse(JSON.stringify(src)) as typeof src),
    id: newId,
    version: 1,
  });
  store.registryVersion += 1;
  pushHistory("platform", `clone ${id} -> ${newId} (registry v${store.registryVersion})`);
  return ok({ version: store.registryVersion, platforms: store.platforms }, 201);
}

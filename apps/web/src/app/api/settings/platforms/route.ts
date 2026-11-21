import { fail, getStore, ok, pushHistory } from "@/lib/fixtures/store";
import { platformUpsertSchema } from "@/lib/schemas/miro.schema";

// Registry platform chạy bằng fixture/mock theo contract BE.
// Khi nối runtime thật: trỏ sang BE, route này không dùng nữa.
export async function GET() {
  const store = getStore();
  return ok({ version: store.registryVersion, platforms: store.platforms });
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as {
    id?: string;
    name?: string;
    runtime?: string;
  };
  const parsed = platformUpsertSchema.safeParse(body);
  if (!parsed.success) {
    return fail(parsed.error.issues[0]?.message ?? "Dữ liệu platform chưa hợp lệ", 422);
  }
  const store = getStore();
  const existing = store.platforms.find((p) => p.id === parsed.data.id);
  if (existing) {
    existing.name = parsed.data.name;
    existing.runtime = parsed.data.runtime;
    existing.version += 1;
  } else {
    store.platforms.push({
      id: parsed.data.id,
      name: parsed.data.name,
      version: 1,
      runtime: parsed.data.runtime,
      accounts: [],
      entry_urls: {},
      capabilities: {
        list: { status: "UNKNOWN", runtime: parsed.data.runtime, input: "account", output: "items", evidence: "chưa kiểm chứng" },
        download: { status: "UNKNOWN", runtime: parsed.data.runtime, input: "url", output: "file", evidence: "chưa kiểm chứng" },
        draft: { status: "UNKNOWN", runtime: parsed.data.runtime, input: "video", output: "draft", evidence: "chưa kiểm chứng" },
        publish: { status: "UNKNOWN", runtime: parsed.data.runtime, input: "video", output: "post", evidence: "chưa kiểm chứng" },
        reconcile: { status: "UNKNOWN", runtime: parsed.data.runtime, input: "post_id", output: "receipt", evidence: "chưa kiểm chứng" },
        watch: { status: "UNKNOWN", runtime: parsed.data.runtime, input: "post_id", output: "events", evidence: "chưa kiểm chứng" },
      },
      tracks: { read: "UNKNOWN", publish: "UNKNOWN" },
    });
  }
  store.registryVersion += 1;
  pushHistory("platform", `upsert ${parsed.data.id} -> registry v${store.registryVersion}`);
  return ok({ version: store.registryVersion, platforms: store.platforms }, 201);
}

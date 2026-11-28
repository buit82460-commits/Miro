// Publish BFF — BE-first, không fixture-fallback.
// BE không có EP list batches/receipts: GET trả [] trung thực (rỗng, không mẫu).
// POST threads → BE POST /threads/publish dry-run (allow_post=false, không post thật).
// BE down → 502 BE_UNREACHABLE, không bịa receipt posted. Platform BE chưa có EP → 502.
import { fail, ok } from "@/lib/fixtures/store";

const PLATFORMS = ["threads", "facebook", "tiktok", "youtube", "instagram"];

// BE thật: POST /threads/publish, dry-run mặc định (allow_post=false, không post thật).
// Override qua env MIRO_BE_BASE; default theo docs/runtime-deps.md (BE 8770).
const BE_BASE = process.env.MIRO_BE_BASE ?? "http://localhost:8770";

export async function GET() {
  // BE không expose GET list batches — trả rỗng trung thực, không seed mẫu.
  return ok([]);
}

type BePublishResult = {
  status: string;
  detail: string;
  reachable: boolean;
};

async function publishThreadsDryRun(opts: {
  publication_id: string;
  attempt_id: string;
  render_id: string;
  owner: string;
  shortcode: string;
}): Promise<BePublishResult> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 10_000);
  try {
    const res = await fetch(`${BE_BASE}/threads/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // allow_post=false: dry-run mặc định, BE không post thật.
      body: JSON.stringify({
        publication_id: opts.publication_id,
        attempt_id: opts.attempt_id,
        render_id: opts.render_id,
        channel: "threads",
        allow_post: false,
        text: `dry-run ${opts.shortcode}`,
        owner: opts.owner,
        shortcode: opts.shortcode,
        tag: "",
      }),
      signal: ctrl.signal,
    });
    const data = (await res.json().catch(() => null)) as {
      worker?: { results?: { dry_run?: boolean; error?: string; posted?: boolean }[] };
    } | null;
    if (!res.ok || !data) {
      return {
        status: "backend_error",
        detail: `BE trả HTTP ${res.status}`,
        reachable: true,
      };
    }
    const first = data.worker?.results?.[0];
    if (first?.dry_run === true) {
      return { status: "dry_run", detail: "BE dry-run: chưa đăng thật (allow_post=false).", reachable: true };
    }
    if (first?.error) {
      return { status: `denied:${first.error}`, detail: `BE từ chối: ${first.error}.`, reachable: true };
    }
    if (first?.posted === true) {
      return { status: "posted_unconfirmed", detail: "BE báo posted nhưng receipt UNCONFIRMED — chưa xác minh.", reachable: true };
    }
    return { status: "backend_unknown", detail: "BE trả kết quả không rõ — coi như chưa đăng.", reachable: true };
  } catch {
    return { status: "unreachable", detail: "Không nối được BE.", reachable: false };
  } finally {
    clearTimeout(timer);
  }
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as {
    video_id?: string;
    platform?: string;
    account?: string;
    scheduled_at?: string;
  };
  if (!body.video_id) return fail("Chọn video", 422);
  if (!body.platform || !PLATFORMS.includes(body.platform)) return fail("Platform chưa hợp lệ", 422);
  if (!body.account) return fail("Chọn tài khoản", 422);

  // BE chỉ có luồng Threads (M2). Platform khác chưa có EP publish → 502, không mock.
  if (body.platform !== "threads") {
    return fail(`BE_UNREACHABLE: BE chưa hỗ trợ publish ${body.platform}. Chưa đăng gì.`, 502);
  }

  const batch = {
    id: `batch-${body.video_id}-${Date.now()}`,
    video_id: body.video_id,
    platform: body.platform,
    account: body.account,
    scheduled_at: body.scheduled_at,
    status: body.scheduled_at ? "scheduled" : "queued",
    source: "backend" as const,
    backend_detail: "",
  };

  const be = await publishThreadsDryRun({
    publication_id: batch.id,
    attempt_id: `att-${Date.now()}`,
    render_id: body.video_id,
    owner: body.account.replace(/^@/, ""),
    shortcode: body.video_id,
  });
  if (!be.reachable) {
    // BE down → 502 fail-closed. KHÔNG tạo receipt posted mẫu.
    return fail("BE_UNREACHABLE: không nối được BE. Chưa đăng gì.", 502);
  }
  // BE thật đã trả lời (dry-run/deny/lỗi): hiển thị kết quả thật.
  batch.status = be.status;
  batch.backend_detail = be.detail;
  return ok(batch, 201);
}

import { fail, getStore, nextId, ok, pushHistory } from "@/lib/fixtures/store";

const PLATFORMS = ["threads", "facebook", "tiktok", "youtube", "instagram"];

// BE thật: POST /threads/publish, dry-run mặc định (allow_post=false, không post thật).
// Override qua env MIRO_BE_BASE; default theo docs/runtime-deps.md (BE 8770).
const BE_BASE = process.env.MIRO_BE_BASE ?? "http://localhost:8770";

export async function GET() {
  return ok(getStore().batches);
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
  const batch = {
    id: nextId("batch"),
    video_id: body.video_id,
    platform: body.platform,
    account: body.account,
    scheduled_at: body.scheduled_at,
    status: body.scheduled_at ? "scheduled" : "queued",
    source: "fixture" as "fixture" | "backend",
    backend_detail: "",
  };
  getStore().batches.unshift(batch);

  if (body.platform === "threads") {
    const attemptId = nextId("att");
    const be = await publishThreadsDryRun({
      publication_id: batch.id,
      attempt_id: attemptId,
      render_id: body.video_id,
      owner: body.account.replace(/^@/, ""),
      shortcode: body.video_id,
    });
    if (be.reachable) {
      // BE thật đã trả lời (dry-run/deny/lỗi): hiển thị kết quả thật,
      // KHÔNG tạo receipt fixture "posted" gây hiểu nhầm.
      batch.source = "backend";
      batch.status = be.status;
      batch.backend_detail = be.detail;
    } else {
      // Fixture fallback khi BE không reachable — vẫn gắn nhãn DỮ LIỆU MẪU.
      const postId = nextId("post");
      getStore().receipts.unshift({
        id: nextId("rc"),
        post_id: postId,
        post_url: `https://www.threads.com/t/${postId}`,
        platform: "threads",
        account: body.account,
        status: "posted",
        posted_at: new Date().toISOString(),
        source: "fixture",
      });
      batch.status = "posted";
      batch.backend_detail = "DỮ LIỆU MẪU — chưa đăng thật (BE không reachable).";
    }
  }
  pushHistory("publish", `${batch.id} ${batch.platform}/${batch.account} -> ${batch.status} [${batch.source}]`);
  return ok(batch, 201);
}

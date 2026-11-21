import { fail, getStore, nextId, ok, pushHistory } from "@/lib/fixtures/store";

const PLATFORMS = ["threads", "facebook", "tiktok", "youtube", "instagram"];

export async function GET() {
  return ok(getStore().batches);
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
    status: "queued",
  };
  getStore().batches.unshift(batch);
  // Fixture: đăng Threads xong có receipt posted ngay để E2E đối soát được.
  if (body.platform === "threads") {
    const postId = nextId("post");
    getStore().receipts.unshift({
      id: nextId("rc"),
      post_id: postId,
      post_url: `https://www.threads.com/t/${postId}`,
      platform: "threads",
      account: body.account,
      status: "posted",
      posted_at: new Date().toISOString(),
    });
    batch.status = "posted";
  }
  pushHistory("publish", `${batch.id} ${batch.platform}/${batch.account} -> ${batch.status}`);
  return ok(batch, 201);
}

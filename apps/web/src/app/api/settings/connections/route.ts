import { ok } from "@/lib/fixtures/store";

export async function GET() {
  return ok([
    { platform: "threads", account: "@miro.demo", status: "connected" },
    { platform: "facebook", account: "Miro Demo Page", status: "connected" },
    { platform: "tiktok", account: "@miro.demo", status: "disconnected" },
    { platform: "youtube", account: "Miro Demo", status: "disconnected" },
    { platform: "instagram", account: "@miro.demo", status: "disconnected" },
  ]);
}

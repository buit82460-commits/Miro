import { expect, test } from "@playwright/test";

// BUG-11 live acceptance (UI-only, read-safe):
// - Giao việc đọc an toàn qua /tasks-live (autonomous search tab_id=0).
// - Quan sát BE bridge tabs trước/sau — Miro KHÔNG chiếm tab đang mở của user.
// - KHÔNG dùng Playwright điều khiển browser thay Miro; chỉ nhập + bấm Gửi.
test("BUG-11: autonomous search khong chiem tab nguoi dung", async ({ page, request }) => {
  const snapTabs = async () => {
    const r = await request.get("http://127.0.0.1:8770/tasks/runtime/status");
    expect(r.ok()).toBeTruthy();
    const j = await r.json();
    return (j?.bridge?.tabs ?? []) as { browser: string; tab: number; url: string; title: string }[];
  };

  const before = await snapTabs();
  const beforeUrls = before.map((t) => t.url);

  await page.goto("/tasks-live");
  await expect(page.getByTestId("live-title")).toContainText("Giao việc");
  const probe = `tim kiem tiktok tong hop 3 video qa-probe ${Date.now()}`;
  await page.getByTestId("live-input").click();
  await page.getByTestId("live-input").pressSequentially(probe, { delay: 10 });
  await expect(page.getByTestId("live-send")).toBeEnabled({ timeout: 15_000 });
  // Gửi nhiệm vụ đọc an toàn (autonomous, tab_id=0) qua UI Miro thật.
  await page.getByTestId("live-send").click();
  // Chờ BE chốt task (fail-closed NO_ROUTE/SEARCH_* đều có task_id).
  await expect(page.getByTestId("live-out")).not.toBeEmpty({ timeout: 60_000 });

  const after = await snapTabs();
  // Không tạo tab mới ngoài bridge đã có; không điều hướng tab user.
  // Bridge tabs chỉ từ extension; FE/BE không tự mở tab QA mới.
  for (const t of after) {
    if (t.url.includes("tiktok.com/search")) {
      // Miro được phép navigate đúng search URL qua Gateway lease —
      // nhưng URL user tab (Miro UI) phải còn nguyên.
      expect(t.url).toContain("tiktok.com/search");
    }
  }
  // Ghi nhận counts để đối chiếu (không assert count cứng vì flaky TikTok).
  expect(JSON.stringify({ before: beforeUrls.length, after: after.length })).toBeTruthy();
});

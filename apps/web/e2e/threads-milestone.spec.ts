import { expect, test } from "@playwright/test";

// Mốc Threads: sửa sub -> render -> duyệt -> đăng -> tìm lại bài -> lịch sử.
// Chạy bằng fixture/mock nội bộ theo contract BE (POST /api/test-reset để seed lại).
test("threads milestone: subtitle -> render -> approve -> publish -> receipt -> history", async ({
  page,
  request,
}) => {
  await request.post("/api/test-reset");
  const subText = `Sub Threads E2E ${Date.now()}`;

  // 1. Sửa sub trong Editor.
  await page.goto("/editor?project=p1");
  await expect(page.getByTestId("editor-title")).toContainText("r3");
  await page.getByTestId("clip-sub1").click();
  await page.getByTestId("sub-text").fill(subText);
  await page.getByTestId("sub-save").click();
  await expect(page.getByTestId("editor-msg")).toContainText("Đã sửa phụ đề");
  await expect(page.getByTestId("editor-title")).toContainText("r4");

  // 2. Render bản cuối.
  await page.getByTestId("render-final").click();
  await expect(page.getByTestId("editor-msg")).toContainText("Đã render bản cuối");
  await expect(page.getByTestId("render-status")).toContainText("render_done");

  // 3. Duyệt bản cuối.
  await page.getByTestId("approve-project").click();
  await expect(page.getByTestId("editor-msg")).toContainText("Đã duyệt");

  // 4. Đăng Threads (batch video×platform×account).
  await page.goto("/publish");
  // Nhãn mẫu phải luôn nhìn thấy — chống hiểu nhầm "posted" là đăng thật.
  await expect(page.getByTestId("publish-sample-note")).toContainText("DỮ LIỆU MẪU");
  await page.getByTestId("publish-video").selectOption("p1");
  await page.getByTestId("publish-platform").selectOption("threads");
  await page.getByTestId("publish-account").fill("@miro.demo");
  await page.getByTestId("publish-submit").click();
  await expect(page.getByTestId("publish-msg")).toContainText("Đã gửi batch");

  // 5. Tìm lại bài: receipt posted có post_url + post_id đối soát được.
  const receiptList = page.getByTestId("receipt-list");
  await expect(receiptList).toContainText("threads/@miro.demo");
  await expect(receiptList).toContainText("posted");
  const postUrl = await page.getByTestId("receipt-list").innerText();
  expect(postUrl).toContain("https://www.threads.com/t/");

  // 6. Lịch sử ghi đủ mốc.
  const history = await request.get("/api/history").then((r) => r.json());
  const events: string[] = history.result.map((h: { event: string }) => h.event);
  for (const e of ["subtitle", "render", "approve", "publish"]) {
    expect(events).toContain(e);
  }
});

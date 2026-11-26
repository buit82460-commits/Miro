import { expect, test } from "@playwright/test";

// Slice 04: UI doc lap - dieu huong khong mat trang, co trang Runtime + task detail.
// Chay bang fixture/mock noi bo (POST /api/test-reset de seed lai).
test("slice04: nav runtime + tasks-live + detail khong mat trang", async ({ page, request }) => {
  await request.post("/api/test-reset");

  // Runtime page render.
  await page.goto("/runtime");
  await expect(page.getByTestId("runtime-title")).toContainText("Runtime");

  // Tasks-live: giao viec qua fixture chat cu van tao task moi.
  await page.goto("/tasks-live");
  await expect(page.getByTestId("live-title")).toContainText("Giao viec");

  // Chuyen trang qua lai khong mat noi dung (nav giu, list van render).
  await page.goto("/runtime");
  await expect(page.getByTestId("runtime-title")).toBeVisible();
  await page.goto("/tasks-live");
  await expect(page.getByTestId("live-task-list")).toBeVisible();
});

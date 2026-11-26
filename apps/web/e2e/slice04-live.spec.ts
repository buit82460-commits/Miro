import { expect, test } from "@playwright/test";

// Slice 04 acceptance: chuyen trang khong mat task (BE so huu state).
// Chay khi FE co NEXT_PUBLIC_API_BASE tro sang BE that.
const BE = process.env.MIRO_BE_BASE ?? "http://127.0.0.1:8770";

test("slice04-live: giao viec + chuyen trang khong mat + reopen", async ({ page, request }) => {
  // Giao viec khong can tab that (tab_id=0 -> NO_ROUTE hoac tu tim).
  const msg = `tim kiem tiktok KANS 377 5 video ${Date.now()}`;
  const res = await request.post(`${BE}/tasks/run-message`, {
    data: { message: msg, tab_id: 0 },
  });
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  expect(body.route?.job_type).toBe("browser_search");

  // Chuyen trang: task moi nhat van con (BE persist, khong phu thuoc FE state).
  const r1 = await request.get(`${BE}/tasks/recent?limit=5`);
  const ids1 = ((await r1.json()) as { id: string }[]).map((t) => t.id);
  const r2 = await request.get(`${BE}/tasks/recent?limit=5`);
  const ids2 = ((await r2.json()) as { id: string }[]).map((t) => t.id);
  expect(ids2).toEqual(ids1);

  // Mo trang detail qua FE (rewrite sang BE).
  const first = ids1[0] as string;
  await page.goto(`/tasks-live/${first}`);
  await expect(page.getByTestId("detail-title")).toContainText(first);
});

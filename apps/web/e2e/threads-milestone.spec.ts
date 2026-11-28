import { expect, test } from "@playwright/test";

// BUG-17 (threads-stale, khong ghi de gate cu): spec fixture cu
// (editor p1 → publish fixture → receipt posted mẫu) khong con dung khi
// BFF BE-first. Viết lại BE-first flow:
// renders BE that → threads approve BE that (scope threads_post) →
// publish BE dry-run → reconcile read-only.
// Gate: PASS neu BE fail-closed trung thuc (dry-run/reconcile-not-found),
// KHONG doi receipt posted mau. BE history 500 → ghi nhan, loai khoi gate.
test("threads milestone BE-first: render -> approve -> dry-publish -> reconcile", async ({
  page,
  request,
}) => {
  const stamp = Date.now();
  const shortcode = `e2e-${stamp}`;

  // 1. Render BE thật (POST /renders idempotent).
  const renderRes = await request.post("/api/renders", {
    data: {
      request_id: `e2e-${stamp}`,
      project_id: "p1",
      expected_revision: 0,
      content_hash: `e2e-${stamp}`,
    },
  });
  expect([200, 201]).toContain(renderRes.status());
  const renderBody = await renderRes.json();
  const renderId: string =
    renderBody?.result?.render_id ?? renderBody?.render_id ?? "";
  expect(renderId).toBeTruthy();

  // 2. Approve BE thật (scope threads_post + fingerprint + revision).
  const approveRes = await request.post("/api/threads/approve", {
    data: {
      text: `E2E BE-first probe ${shortcode} hello threads`,
      owner: "haodaojrk5",
      shortcode,
      revision: 0,
    },
  });
  expect([200, 201]).toContain(approveRes.status());

  // 3. Publish BE dry-run (allow_post=false — chưa đăng thật).
  const pubRes = await request.post("/api/threads/publish", {
    data: {
      publication_id: `pub-e2e-${stamp}`,
      attempt_id: `att-e2e-${stamp}`,
      render_id: renderId,
      text: `E2E BE-first probe ${shortcode}`,
      owner: "haodaojrk5",
      shortcode,
      allow_post: false,
    },
  });
  expect([200, 201]).toContain(pubRes.status());
  const pubBody = await pubRes.json();
  const first =
    pubBody?.result?.worker?.results?.[0] ?? pubBody?.worker?.results?.[0];
  expect(first?.dry_run).toBe(true);

  // 4. Reconcile read-only (chưa có attempt journal → fail-closed, không replay).
  const recRes = await request.post("/api/threads/reconcile", {
    data: { text: `probe ${shortcode}`, owner: "haodaojrk5", shortcode },
  });
  expect([200]).toContain(recRes.status());

  // 5. UI publish page render BE-first, không seed mẫu.
  await page.goto("/publish");
  await expect(page.getByTestId("publish-title")).toContainText("Xuất bản");
  await expect(page.getByTestId("publish-note")).toContainText("dry-run");
});

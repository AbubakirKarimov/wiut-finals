import { expect, test } from "@playwright/test";

const SITE = "http://127.0.0.1:18765/index.html";
const API = "http://127.0.0.1:8001";

const shot = (page, testInfo, name) =>
  page.screenshot({ path: `e2e/screenshots/${testInfo.project.name}-${name}.png`, fullPage: true });

test("home loads with navigation", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Check a website" })).toBeVisible();
  for (const tab of ["Check", "Findings", "Audit & Metrics"]) {
    await expect(page.getByRole("link", { name: tab, exact: true })).toBeVisible();
  }
  await shot(page, testInfo, "home");
});

test("a check reaches results", async ({ page }, testInfo) => {
  await page.goto("/#/check");
  await page.getByPlaceholder("https://bank.uz/").fill(SITE);
  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByTestId("job-status")).toContainText("Status: done", { timeout: 60_000 });
  const results = page.getByTestId("results");
  await expect(results.getByTestId("finding-row")).toHaveCount(1);
  // Russian-only fixture with 7 pages and no Uzbek version -> possible gap with a quote.
  await expect(results).toContainText("Possible gap");
  await expect(results.locator("blockquote")).toContainText("ТестБанк");
  await expect(results).toContainText("machine translation");
  await expect(results).toContainText("checked just now");
  await shot(page, testInfo, "check-results");
});

test("decision persists after reload", async ({ page, request }, testInfo) => {
  // Make sure a stored finding exists (independent of test order).
  const start = await request.post(`${API}/check`, { data: { url: SITE } });
  expect(start.status()).toBe(202);
  const { job_id } = await start.json();
  await expect.poll(async () => (await (await request.get(`${API}/jobs/${job_id}`)).json()).status,
    { timeout: 60_000 }).toBe("done");

  const comment = `e2e ${testInfo.project.name} ${Date.now()}`;
  await page.goto("/#/findings");
  await expect(page.getByText("pre-computed on").first()).toBeVisible();
  await page.getByPlaceholder("Your name (saved in this browser)").fill("E2E Analyst");
  const row = page.getByTestId("finding-row").first();
  await row.getByPlaceholder("Comment (optional)").fill(comment);
  await row.getByRole("button", { name: "Confirm" }).click();
  await expect(row.getByTestId("decision-state")).toContainText("Confirmed by E2E Analyst");

  await page.reload();
  const again = page.getByTestId("finding-row").first();
  await expect(again.getByTestId("decision-state")).toContainText(comment);
  await shot(page, testInfo, "findings");

  await page.goto("/#/audit");
  await expect(page.getByTestId("decision-log")).toContainText(comment);
  await expect(page.getByTestId("metrics")).toContainText("Checks completed");
  await shot(page, testInfo, "audit");
});

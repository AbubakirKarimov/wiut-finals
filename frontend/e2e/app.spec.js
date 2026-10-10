import { expect, test } from "@playwright/test";

const SITE = "http://127.0.0.1:18765/index.html";
const API = "http://127.0.0.1:8001";

// Screenshots for the jury: eval/ui_screens/<viewport>-<name>.png (375 and 1280 only).
const shot = async (page, testInfo, name) => {
  await page.screenshot({ path: `e2e/screenshots/${testInfo.project.name}-${name}.png`, fullPage: true });
  if (["mobile-375", "desktop-1280"].includes(testInfo.project.name)) {
    await page.screenshot({ path: `../eval/ui_screens/${testInfo.project.name}-${name}.png`, fullPage: true });
  }
};

async function noHorizontalScroll(page) {
  const [scroll, inner] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(scroll).toBeLessThanOrEqual(inner);
}

async function tapTargetsAtLeast44(page) {
  const small = await page.evaluate(() => [...document.querySelectorAll("button, .tab, .chip")]
    .filter((el) => el.offsetParent !== null)
    .map((el) => el.getBoundingClientRect())
    .filter((r) => r.height < 44).length);
  expect(small).toBe(0);
}

test("home loads with navigation and how-it-works strip", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Check a website" })).toBeVisible();
  for (const tab of ["Check", "Findings", "Audit & Metrics"]) {
    await expect(page.getByRole("link", { name: tab, exact: true })).toBeVisible();
  }
  const how = page.getByRole("region", { name: "How it works" });
  await expect(how).toContainText("Law clause");
  await expect(how).toContainText("Audit log");
  await expect(how).toContainText("not yet measured in this prototype");
  await noHorizontalScroll(page);
  await tapTargetsAtLeast44(page);
  await shot(page, testInfo, "home");
});

test("invalid URL is explained before any request", async ({ page }) => {
  await page.goto("/#/check");
  await page.getByPlaceholder("https://bank.uz/").fill("not a url");
  await page.getByRole("button", { name: "Check", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("not a valid address");
  await expect(page.getByTestId("job-status")).toHaveCount(0);
});

test("a check reaches results with stepper, badge and pages read", async ({ page }, testInfo) => {
  await page.goto("/#/check");
  await page.getByPlaceholder("https://bank.uz/").fill(SITE);
  await page.getByRole("button", { name: "Check", exact: true }).click();
  await expect(page.getByTestId("job-status")).toContainText("Status: done", { timeout: 60_000 });
  const stepper = page.getByRole("list", { name: "Check progress" });
  await expect(stepper).toContainText("Done");
  await expect(stepper).toContainText("7 read");
  await expect(stepper).toContainText("1/1");
  await expect(page.getByTestId("elapsed")).toContainText(/Elapsed \d+s/);
  const results = page.getByTestId("results");
  await expect(results.getByTestId("finding-row")).toHaveCount(1);
  // Russian-only fixture with 7 pages and no Uzbek version -> possible gap with a quote.
  await expect(results).toContainText("Possible gap for review");
  await expect(results.getByTestId("decided-by")).toHaveText("Decided by: code");
  const gap = results.getByTestId("gap-evidence");
  await expect(gap).toContainText("No evidence found on 7 page(s) read. Closest page:");
  await expect(gap.locator("blockquote")).toContainText("ТестБанк");
  await expect(gap.getByTestId("pages-read")).toContainText("Pages read (7)");
  await expect(gap.locator("details li")).toHaveCount(7);
  await expect(gap.locator("details li").first()).toContainText("Russian");
  await expect(page.locator("body")).not.toContainText(/violation/i);
  await expect(results).toContainText("machine translation");
  await expect(results).toContainText("checked just now");
  await noHorizontalScroll(page);
  await shot(page, testInfo, "check-results");
});

test("decision persists after reload and appears in the audit log", async ({ page, request }, testInfo) => {
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
  await expect(row.getByRole("link", { name: "Clause on lex.uz ↗" })).toBeVisible();
  await row.getByPlaceholder("Comment (optional)").fill(comment);
  await row.getByRole("button", { name: "Confirm" }).click();
  await expect(row.getByTestId("decision-state")).toContainText("Confirmed by E2E Analyst");
  await expect(row.getByTestId("storage-note")).toContainText("live session, may reset on restart");

  await page.reload();
  const again = page.getByTestId("finding-row").first();
  await expect(again.getByTestId("decision-state")).toContainText(comment);
  await noHorizontalScroll(page);
  await shot(page, testInfo, "findings");

  await page.goto("/#/audit");
  await expect(page.getByTestId("decision-log")).toContainText(comment);
  await expect(page.getByTestId("decision-log")).toContainText("code");
  await expect(page.getByTestId("metrics")).toContainText("Checks completed");
  await expect(page.getByTestId("precision")).toContainText(/confirmed|n\/a/);
  await expect(page.getByTestId("team-precision")).toContainText("not enough data");
  await expect(page.getByTestId("decision-log")).toContainText("live session, may reset on restart");
  await expect(page.getByTestId("decided-split")).toContainText("decided by code");
  await expect(page.getByTestId("known-failures")).toContainText("Prompt injection");
  await noHorizontalScroll(page);
  await shot(page, testInfo, "audit");
});

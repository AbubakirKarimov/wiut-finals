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
  // A gap shows only "No evidence found on N pages read." and the closest page: no passage.
  await expect(gap.locator(".gap-lead")).toHaveText("No evidence found on 7 pages read.");
  await expect(gap).toContainText("Closest page:");
  await expect(gap.locator("blockquote")).toHaveCount(0);
  await expect(gap).not.toContainText("Context from this page");
  // Pages read: collapsed by default, language + URL when expanded.
  const pagesRead = gap.getByTestId("pages-read");
  await expect(pagesRead).toContainText("Pages read (7)");
  await expect(pagesRead).not.toHaveAttribute("open", "");
  await expect(pagesRead.locator("li").first()).toBeHidden();
  await pagesRead.locator("summary").click();
  await expect(pagesRead.locator("li")).toHaveCount(7);
  await expect(pagesRead.locator("li").first()).toContainText("Russian");
  // Technical text is in a collapsed "Details" section.
  const details = gap.getByTestId("reason-details");
  await expect(details).not.toHaveAttribute("open", "");
  await details.locator("summary").click();
  await expect(details).toContainText("no Uzbek-language page found");
  await expect(page.locator("body")).not.toContainText(/violation/i);
  await expect(results).toContainText("checked just now");
  await noHorizontalScroll(page);
  await shot(page, testInfo, "check-results");
});

test("a JavaScript-only site ends with one friendly message and an amber final step", async ({ page }, testInfo) => {
  await page.goto("/#/check");
  await page.getByPlaceholder("https://bank.uz/").fill(SITE.replace("index.html", "js-only.html"));
  await page.getByRole("button", { name: "Check", exact: true }).click();
  const status = page.getByTestId("job-status");
  await expect(status.getByTestId("status-label")).toHaveText("finished, nothing judged", { timeout: 60_000 });
  await expect(status).not.toContainText("Status: done");
  const message = status.getByTestId("js-only-message");
  await expect(message).toHaveText(
    "This site renders its content with JavaScript, which the hosted demo cannot read " +
    "(no browser here, and the optional Jina Reader fallback is off). Nothing was judged.");
  // No pre-computed results exist for this host, so no Findings link is offered.
  await expect(message.getByRole("link")).toHaveCount(0);
  const stepper = page.getByRole("list", { name: "Check progress" });
  const last = stepper.locator(".step").last();
  await expect(last).toHaveClass(/step-warn/);
  await expect(last).toHaveText(/Not available on this hosted demo/);
  await expect(stepper).not.toContainText("Done");
  // The technical reason is only in the collapsed Details; no env var names are visible.
  const details = status.locator("details.tech");
  await expect(details).not.toHaveAttribute("open", "");
  await expect(details.locator("p")).toBeHidden();
  const visible = await page.evaluate(() => document.body.innerText);
  expect(visible).not.toMatch(/BROWSER_FALLBACK|[A-Z]{3,}_[A-Z_]{3,}=/);
  // The message appears once in the status area, not repeated as an error with Retry.
  await expect(status.getByText("which the hosted demo cannot read")).toHaveCount(1);
  await expect(status.getByRole("button", { name: "Retry" })).toHaveCount(0);
  const checks = page.getByTestId("js-only-checks");
  await expect(checks).toContainText("1 check(s), all not checkable");
  await expect(checks).not.toHaveAttribute("open", "");
  await noHorizontalScroll(page);
  await shot(page, testInfo, "check-js-only");
});

test("stored cards: ok keeps its quote, not checkable shows only a short reason", async ({ page }) => {
  await page.goto("/#/findings");
  const ok = page.getByTestId("finding-row").filter({ hasText: "e2e_ok_bank" });
  const okEv = ok.getByTestId("ok-evidence");
  await expect(okEv.locator("blockquote mark")).toHaveText("Davlat tilida e'lonlar va narxlar ro'yxati joylashtirilgan.");
  await expect(okEv).toContainText("machine translation: Announcements and price lists are published in the state language.");
  await expect(okEv.locator("a.pagelink")).toHaveAttribute("href", "https://e2e_ok_bank.example/p0");
  await expect(okEv.locator(".reason-short")).toHaveText("Uzbek version present (5 Uzbek pages of 6; completeness not assessed).");

  const nc = page.getByTestId("finding-row").filter({ hasText: "e2e_nc_bank" });
  const ncEv = nc.getByTestId("nc-evidence");
  await expect(ncEv.getByTestId("nc-reason")).toHaveText("LLM did not confirm it; manual review needed.");
  await expect(ncEv.locator("blockquote")).toHaveCount(0);
  await expect(nc).not.toContainText("This stored passage must not be shown");
  await expect(nc).not.toContainText("Passage found");
  await expect(nc).not.toContainText("machine translation of the hidden passage");
  const details = ncEv.getByTestId("reason-details");
  await expect(details.locator("p")).toBeHidden();
  await details.locator("summary").click();
  await expect(details).toContainText("Re-checked on 2026-10-10");
  await expect(details).toContainText("keywords from hints: e2e, seed");
  await expect(ncEv.getByTestId("nc-reason")).not.toContainText("re-checked");
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

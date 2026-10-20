import { expect, Page, test } from "@playwright/test";

const job = (id = "job-1", status = "Queued") => ({ id, report_type: "alerts_summary", format: "xlsx",
  from_date: "2026-01-01T00:00:00Z", to_date: "2026-01-02T00:00:00Z", status, stage: "Reading",
  attempts: 1, row_count: null, failure_message: null, next_attempt_at: null });

async function setup(page: Page, state: any, role = "ENTERPRISE_ADMIN") {
  state.keys = [];
  state.calls = [];
  await page.routeWebSocket("**/api/v1/ws/live", () => {});
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    state.calls.push(path);
    let data: any = [];
    let meta = { total: 0 };
    if (path.endsWith("/auth/login")) data = { access_token: "reports-token", is_master_session: false,
      user: { id: "admin", enterprise_id: "company", name: "Admin", roles: [role], is_first_login: false } };
    else if (path.endsWith("/reports/generate")) {
      state.keys.push(request.headers()["idempotency-key"]);
      if (state.failGenerate) return route.abort("connectionfailed");
      state.items = [job()]; data = state.items[0];
    } else if (path.endsWith("/retry")) {
      state.items[0] = job(); data = state.items[0];
    } else if (path.endsWith("/download")) {
      if (state.denyDownload) return route.fulfill({ status: 403, json: { error: { message: "Access denied" } } });
      data = { download_url: "https://reports.example.test/file.xlsx" };
    } else if (path.endsWith("/reports")) {
      if (state.failList) return route.fulfill({ status: 503, json: { error: { message: "Unavailable" } } });
      data = url.searchParams.get("page") === "2" ? [job("page-two", "Completed")] : state.items ?? [];
      meta = { total: state.total ?? data.length };
    } else if (path.endsWith("/branding")) data = { name: "Company" };
    await route.fulfill({ json: { success: true, data, meta } });
  });
  await page.goto("/login");
  await page.getByLabel(/^Email/).fill("admin@example.com");
  await page.getByLabel(/^Password/).fill("test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  if (role === "ENTERPRISE_ADMIN") await page.getByRole("link", { name: "Reports", exact: true }).click();
}

test("reports queue, show stages, and expose downloads only after completion", async ({ page }) => {
  const state: any = {};
  await setup(page, state);
  await page.getByRole("button", { name: "Generate report", exact: true }).click();
  await expect(page.getByText("Report queued. You can leave this page and return later.")).toBeVisible();
  await expect(page.getByText("Queued", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download", exact: true })).toHaveCount(0);
  state.items = [{ ...job(), status: "Running", stage: "Rendering" }];
  await expect(page.getByText("Rendering · Attempt 1")).toBeVisible({ timeout: 10000 });
  state.items = [{ ...job(), status: "Completed", stage: "Completed", row_count: 42 }];
  await expect(page.getByRole("button", { name: "Download", exact: true })).toBeVisible({ timeout: 10000 });
  expect(state.calls.filter((path: string) => path.endsWith("/download"))).toHaveLength(0);
  state.denyDownload = true;
  await page.getByRole("button", { name: "Download", exact: true }).click();
  await expect(page.getByText(/Download unavailable: Access denied/)).toBeVisible();
});

test("uncertain generation retries keep the same idempotency key", async ({ page }) => {
  const state: any = { failGenerate: true };
  await setup(page, state);
  await page.getByRole("button", { name: "Generate report", exact: true }).click();
  await expect(page.getByText(/Report request could not be confirmed/)).toBeVisible();
  state.failGenerate = false;
  await page.getByRole("button", { name: "Generate report", exact: true }).click();
  await expect(page.getByText("Queued", { exact: true })).toBeVisible();
  expect(state.keys).toHaveLength(2);
  expect(state.keys[0]).toBe(state.keys[1]);
});

test("failed report exposes retry and a paginated history", async ({ page }) => {
  const state: any = { items: [{ ...job("failed", "Failed"), failure_message: "Report storage is unavailable." }], total: 21 };
  await setup(page, state);
  await expect(page.getByText("Report storage is unavailable.")).toBeVisible();
  await page.getByRole("button", { name: "Retry report", exact: true }).click();
  await expect(page.getByText("Queued", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Go to next page" }).click();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible();
});

test("failed list refresh hides cached downloads and can recover", async ({ page }) => {
  const state: any = { items: [job("old", "Completed")], failList: false };
  await setup(page, state);
  await expect(page.getByRole("button", { name: "Download", exact: true })).toBeVisible();
  state.failList = true;
  await expect(page.getByText("Reports could not be loaded.")).toBeVisible({ timeout: 12000 });
  await expect(page.getByRole("button", { name: "Download", exact: true })).toHaveCount(0);
  state.failList = false; state.items = [];
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("No reports on this page.")).toBeVisible();
});

test("scoped users cannot request enterprise reports through direct navigation", async ({ page }) => {
  const state: any = {};
  await setup(page, state, "FACTORY_MANAGER");
  await expect(page.getByRole("link", { name: "Reports", exact: true })).toHaveCount(0);
  await page.evaluate(() => { history.pushState({}, "", "/reports"); dispatchEvent(new PopStateEvent("popstate")); });
  await expect(page.getByText("Enterprise administrator access is required for reports.")).toBeVisible();
  expect(state.calls.filter((path: string) => path.startsWith("/api/v1/reports"))).toHaveLength(0);
});

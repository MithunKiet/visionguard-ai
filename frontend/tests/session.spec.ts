import { expect, test, Page } from "@playwright/test";

async function signIn(page: Page, email = "a@example.com") {
  await page.getByLabel(/^Email/).fill(email);
  await page.getByLabel(/^Password/).fill("test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

async function mockApi(page: Page, firstLogin = false) {
  let tenant = "A";
  const calls: string[] = [];
  await page.routeWebSocket("**/api/v1/ws/live", () => {});
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    calls.push(path);
    let data: any = [];
    let meta: any = { total: 0, page: 1, total_pages: 1, page_size: 50 };
    if (path.endsWith("/auth/login")) {
      tenant = request.postDataJSON().email.startsWith("b") ? "B" : "A";
      data = { access_token: `test-token-${tenant}`, is_master_session: false,
        user: { id: tenant, enterprise_id: tenant, name: tenant, email: `${tenant}@example.com`,
                roles: ["ENTERPRISE_ADMIN"], is_first_login: firstLogin } };
    } else if (path.endsWith("/auth/logout") || path.endsWith("/auth/change-password")) {
      data = null;
    } else if (path.endsWith("/factories")) {
      data = [{ id: tenant, name: `Factory ${tenant}`, code: tenant, status: "Active" }];
    } else if (path.endsWith("/branding")) {
      data = { name: `Enterprise ${tenant}` };
    } else if (path.endsWith("/alerts")) {
      meta.total = 109;
      if (url.searchParams.get("page_size") !== "1") {
        const pageNumber = url.searchParams.get("page") || "1";
        data = [{ id: pageNumber, alert_number: `ALT-PAGE-${pageNumber}`, alert_type: "PPE_VIOLATION_HELMET",
                  severity: "Critical", status: "Open", created_on: "2026-10-13T00:00:00Z" }];
      }
    }
    await route.fulfill({ json: { success: true, data, meta } });
  });
  return calls;
}

test("first login routes to password change and clears the old session after saving", async ({ page }) => {
  const calls = await mockApi(page, true);
  await page.goto("/login");
  await signIn(page);
  await expect(page).toHaveURL(/\/change-password$/);
  expect(calls).not.toContain("/api/v1/factories");
  await page.getByLabel(/^Current password/).fill("test-password");
  await page.getByLabel(/^New password/).fill("replacement-password");
  await page.getByRole("button", { name: "Save password" }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(calls).toContain("/api/v1/auth/change-password");
  expect(await page.evaluate(() => localStorage.getItem("vg_auth"))).toBeNull();
});

test("logout calls the server and a second tenant does not see cached factories", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/login");
  await signIn(page);
  await page.getByRole("link", { name: "Factories", exact: true }).click();
  await expect(page.getByText("Factory A", { exact: true })).toBeVisible();
  await page.getByTitle("Logout", { exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(calls).toContain("/api/v1/auth/logout");
  await signIn(page, "b@example.com");
  await page.getByRole("link", { name: "Factories", exact: true }).click();
  await expect(page.getByText("Factory B", { exact: true })).toBeVisible();
  await expect(page.getByText("Factory A", { exact: true })).toHaveCount(0);
});

test("alerts beyond the first page are accessible", async ({ page }) => {
  await mockApi(page);
  await page.goto("/login");
  await signIn(page);
  await page.getByRole("link", { name: "Alerts", exact: true }).click();
  await expect(page.getByText("ALT-PAGE-1", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Go to next page" }).click();
  await expect(page.getByText("ALT-PAGE-2", { exact: true })).toBeVisible();
});

test("failed logout retains the session until the server confirms a retry", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/login");
  await signIn(page);
  await page.getByRole("link", { name: "Factories", exact: true }).click();
  await expect(page.getByText("Factory A", { exact: true })).toBeVisible();
  await page.route("**/api/v1/auth/logout", route => route.abort("connectionfailed"));
  const dialog = page.waitForEvent("dialog");
  await page.getByTitle("Logout", { exact: true }).click();
  const alert = await dialog;
  expect(alert.message()).toContain("Logout could not be confirmed");
  await alert.accept();
  await expect(page).toHaveURL(/\/factories$/);
  expect(await page.evaluate(() => localStorage.getItem("vg_auth"))).not.toBeNull();
  await page.unroute("**/api/v1/auth/logout");
  await page.getByTitle("Logout", { exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(await page.evaluate(() => localStorage.getItem("vg_auth"))).toBeNull();
  expect(calls).not.toContain("/api/v1/auth/refresh");
});

test("administrators can inspect a failed notification and queue a retry", async ({ page }) => {
  await mockApi(page);
  let queued = false;
  await page.route("**/api/v1/notifications/deliveries**", async route => {
    const path = new URL(route.request().url()).pathname;
    let data: any;
    if (path.endsWith("/retry")) {
      expect(route.request().method()).toBe("POST");
      queued = true;
      data = { id: "delivery", status: "Pending" };
    } else if (path.endsWith("/summary")) {
      data = { counts: { Failed: queued ? 0 : 1, Pending: queued ? 1 : 0 }, oldest_pending_at: null };
    } else {
      data = queued ? [] : [{ id: "delivery", alert_number: "ALT-RETRY-1", channel: "email", status: "Failed", attempts: 3, next_attempt_at: "2026-10-13T00:00:00Z", last_error: "smtp_send_failed" }];
    }
    await route.fulfill({ json: { success: true, data, meta: { total: queued ? 0 : 1 } } });
  });
  await page.goto("/login");
  await signIn(page);
  await page.getByRole("link", { name: "Notification delivery", exact: true }).click();
  await expect(page.getByText("ALT-RETRY-1")).toBeVisible();
  await page.getByRole("button", { name: "Retry delivery", exact: true }).click();
  await expect(page.getByText("No deliveries for this filter.")).toBeVisible();
  expect(queued).toBe(true);
});

test("viewers cannot open delivery administration or request its data", async ({ page }) => {
  const calls = await mockApi(page);
  await page.route("**/api/v1/auth/login", route => route.fulfill({ json: {
    success: true, data: { access_token: "viewer-token", is_master_session: false,
      user: { id: "viewer", enterprise_id: "A", name: "Viewer", email: "viewer@example.com", roles: ["VIEWER"], is_first_login: false } },
  } }));
  await page.goto("/login");
  await signIn(page);
  await expect(page.getByRole("link", { name: "Notification delivery", exact: true })).toHaveCount(0);
  // Client-side navigation preserves the mocked in-memory session.
  await page.evaluate(() => { window.history.pushState({}, "", "/notification-deliveries"); window.dispatchEvent(new PopStateEvent("popstate")); });
  await expect(page.getByText("Enterprise administrator access is required.")).toBeVisible();
  expect(calls.filter(path => path.startsWith("/api/v1/notifications/deliveries"))).toHaveLength(0);
});

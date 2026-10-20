import { expect, Page, test } from "@playwright/test";

async function setup(page: Page, state: any) {
  await page.routeWebSocket("**/api/v1/ws/live", () => {});
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    let data: any = [];
    let meta = { total: 0 };
    if ((url.pathname.endsWith("/alerts") && state.failAlerts) ||
        (url.pathname.endsWith("/violations") && state.failViolations)) {
      return route.fulfill({ status: 503, json: { success: false } });
    }
    if (url.pathname.endsWith("/auth/login")) data = { access_token: "health-token", is_master_session: false,
      user: { id: "viewer", enterprise_id: "company", name: "Viewer", roles: ["VIEWER"], is_first_login: false } };
    else if (url.pathname.endsWith("/detection-health")) {
      if (state.hold) return new Promise<void>(() => {});
      if (state.fail) return route.fulfill({ status: 503, json: { success: false } });
      const cameras = [{ camera_id: "one", camera_name: "Assembly camera", factory_name: "Factory A", zone_name: "Zone A",
        state: state.detecting ? "Detecting" : "WorkerUnavailable", last_inference_at: null }];
      data = { checked_at: "2026-10-20T00:00:00Z", cameras,
        summary: { total_cameras: 1, expected_cameras: 1, detecting_cameras: state.detecting ? 1 : 0,
          gap_cameras: state.detecting ? 0 : 1, paused_cameras: 0, status: state.detecting ? "RecentInferenceObserved" : "DetectionGap" } };
      meta.total = state.total ?? 1;
      if (url.searchParams.get("page") === "2") data.cameras[0].camera_name = "Page two camera";
      if (url.searchParams.get("problems_only") === "true" && state.detecting) { data.cameras = []; meta.total = 0; }
    } else if (url.pathname.endsWith("/branding")) data = { name: "Company" };
    await route.fulfill({ json: { success: true, data, meta } });
  });
  await page.goto("/login");
  await page.getByLabel(/^Email/).fill("viewer@example.com");
  await page.getByLabel(/^Password/).fill("test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

test("dashboard warns about missing detection and recovers after a fresh report", async ({ page }) => {
  const state = { detecting: false };
  await setup(page, state);
  await expect(page.getByText(/1 of 1 expected cameras lack recent detection/)).toBeVisible();
  state.detecting = true;
  await expect(page.getByText("Recent detection confirmed on 1 of 1 expected cameras.")).toBeVisible({ timeout: 15000 });
});

test("stalled health responses expire cached detection even while the page is open", async ({ page }) => {
  const state = { detecting: true, hold: false };
  await setup(page, state);
  await expect(page.getByText(/Recent detection confirmed on/)).toBeVisible();
  state.hold = true;
  await expect(page.getByText(/Detection health is unavailable/)).toBeVisible({ timeout: 22000 });
  await expect(page.getByText(/Recent detection confirmed on/)).toHaveCount(0);
});

test("scoped users can inspect paginated gap details and failed refresh hides old rows", async ({ page }) => {
  const state = { detecting: false, total: 21, fail: false };
  await setup(page, state);
  await page.getByRole("link", { name: "Detection health", exact: true }).click();
  await expect(page.getByText("Assembly camera", { exact: true })).toBeVisible();
  await expect(page.getByText("Worker unavailable", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Go to next page" }).click();
  await expect(page.getByText("Page two camera", { exact: true })).toBeVisible();
  state.fail = true;
  await expect(page.getByText(/A fresh health snapshot is required/)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("Page two camera", { exact: true })).toHaveCount(0);
  state.fail = false; state.detecting = true;
  await page.getByRole("button", { name: "Refresh health", exact: true }).click();
  await expect(page.getByText("Page two camera", { exact: true })).toBeVisible();
  await page.getByLabel("Show detection gaps only").check();
  await expect(page.getByText("No cameras match this page and filter.")).toBeVisible();
});

test("failed operational reads show unavailable data instead of an empty incident history", async ({ page }) => {
  await setup(page, { detecting: false, failAlerts: true, failViolations: true });
  await expect(page.getByText("Alert counts are unavailable. Previous totals are hidden.")).toBeVisible();
  await expect(page.getByText("Recent violations could not be loaded.")).toBeVisible();
  await expect(page.getByText("No violations recorded yet.")).toHaveCount(0);
});

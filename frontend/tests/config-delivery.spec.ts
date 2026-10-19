import { expect, test, Page } from "@playwright/test";

async function openSettings(page: Page, state: any) {
  await page.routeWebSocket("**/api/v1/ws/live", () => {});
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let data: any = [];
    if (path.endsWith("/auth/login")) data = { access_token: "test-config-token", is_master_session: false,
      user: { id: "admin", enterprise_id: "enterprise", name: "Admin", email: "a@example.com",
        roles: ["ENTERPRISE_ADMIN"], is_first_login: false } };
    else if (path.endsWith("/zones")) data = [{ id: "zone", name: "Assembly", code: "Z1", required_ppe_types: ["helmet"] }];
    else if (path.endsWith("/ppe-types")) data = [
      { id: "helmet", code: "helmet", name: "Helmet", is_active: true },
      { id: "vest", code: "vest", name: "Safety vest", is_active: true },
    ];
    else if (path.endsWith("/config/zone/zone/delivery")) {
      if (state.statusError) return route.fulfill({ status: 503, json: { success: false } });
      data = { version: state.version, status: state.applied ? "Applied" : state.noCameras ? "NoActiveCameras" : "Pending",
        active_cameras: state.noCameras ? 0 : 2, applied_cameras: state.applied ? 2 : 0,
        pending_cameras: state.applied || state.noCameras ? 0 : 2, unassigned_cameras: 0,
        publication: { status: state.publication }, last_applied_at: null };
    } else if (path.endsWith("/config/zone/zone")) {
      if (state.configError) return route.fulfill({ status: 503, json: { success: false } });
      if (route.request().method() === "PUT") {
        state.saves++;
        state.version++;
        state.codes = route.request().postDataJSON().required_ppe_types;
        state.publication = "Retrying";
      }
      data = { version: state.version, required_ppe_types: state.codes ?? ["helmet"] };
    } else if (path.endsWith("/branding")) data = { name: "Test enterprise" };
    await route.fulfill({ json: { success: true, data, meta: { total: 0 } } });
  });
  await page.goto("/login");
  await page.getByLabel(/^Email/).fill("a@example.com");
  await page.getByLabel(/^Password/).fill("test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: "Zones", exact: true }).click();
  await page.getByRole("button", { name: "Edit mandatory PPE" }).click();
}

test("saved settings remain visible through retry, publication and worker application", async ({ page }) => {
  const state = { version: 1, publication: "ReconciliationOnly", saves: 0, applied: false };
  await openSettings(page, state);
  await page.getByLabel("Safety vest", { exact: true }).check();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Version 2 saved. Worker application is tracked below.")).toBeVisible();
  await expect(page.getByText(/Delivery is retrying automatically/)).toBeVisible();
  expect(state.saves).toBe(1);
  state.publication = "Published";
  await expect(page.getByText(/Update published; waiting for worker confirmation/)).toBeVisible({ timeout: 10000 });
  await expect(page.getByText(/Version 2 applied on/)).toHaveCount(0);
  // Polling delivery status must not overwrite an unsaved form change.
  await page.getByLabel("Helmet", { exact: true }).uncheck();
  state.applied = true;
  await expect(page.getByText("Version 2 applied on 2 of 2 active cameras.")).toBeVisible({ timeout: 10000 });
  await expect(page.getByLabel("Helmet", { exact: true })).not.toBeChecked();
});

test("status failures hide stale applied success and recover independently of settings", async ({ page }) => {
  const state = { version: 1, publication: "Published", saves: 0, applied: true, statusError: false };
  await openSettings(page, state);
  await expect(page.getByText(/Version 1 applied on/)).toBeVisible();
  state.statusError = true;
  await expect(page.getByText(/Application status is unavailable/)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/Version 1 applied on/)).toHaveCount(0);
  state.statusError = false;
  state.applied = false;
  await page.getByRole("button", { name: "Refresh status" }).click();
  await expect(page.getByText(/0 of 2 active cameras confirmed/)).toBeVisible();
  expect(state.saves).toBe(0);
});

test("no active cameras is not reported as applied", async ({ page }) => {
  await openSettings(page, { version: 1, publication: "Published", saves: 0, noCameras: true });
  await expect(page.getByText(/no active cameras to confirm application/)).toBeVisible();
  await expect(page.getByText(/applied on/)).toHaveCount(0);
});

test("failed settings load blocks accidental saves", async ({ page }) => {
  const state = { version: 1, publication: "Published", saves: 0, configError: true };
  await openSettings(page, state);
  await expect(page.getByText(/Settings could not be loaded/)).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  expect(state.saves).toBe(0);
});

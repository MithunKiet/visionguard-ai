import { expect, test } from "@playwright/test";

test("authenticator enrollment confirms code then clears session", async ({ page }) => {
  const calls: any[] = [];
  await page.routeWebSocket("**/api/v1/ws/live", () => {});
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let data: any = [];
    if (path.endsWith("/auth/login")) {
      calls.push(route.request().postDataJSON());
      data = { access_token: "test-token", is_master_session: false, user: {
        id: "A", enterprise_id: "A", name: "A", email: "a@example.com", roles: ["ENTERPRISE_ADMIN"], is_first_login: false,
      } };
    } else if (path.endsWith("/auth/mfa")) data = { enabled: false };
    else if (path.endsWith("/auth/mfa/setup")) { calls.push(route.request().postDataJSON()); data = { secret: "PRIVATESETUPKEY" }; }
    else if (path.endsWith("/auth/mfa/enable")) { calls.push(route.request().postDataJSON()); data = null; }
    await route.fulfill({ json: { success: true, data, meta: { total: 0, total_pages: 1 } } });
  });
  await page.goto("/login");
  await page.getByLabel(/^Email/).fill("a@example.com");
  await page.getByLabel(/^Password/).fill("my-password");
  await page.getByLabel("Authenticator code (if enabled)").fill("123456");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: "Account security", exact: true }).click();
  await page.getByLabel("Current password").fill("my-password");
  await page.getByRole("button", { name: "Set up authenticator" }).click();
  await expect(page.getByText("PRIVATESETUPKEY", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm authenticator" })).toBeDisabled();
  await page.getByLabel("Authenticator code", { exact: true }).fill("654321");
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain("PRIVATESETUPKEY");
  await page.getByRole("button", { name: "Confirm authenticator" }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(calls[0].otp_code).toBe("123456");
  expect(calls[2]).toEqual({ password: "my-password", otp_code: "654321" });
  expect(await page.evaluate(() => localStorage.getItem("vg_auth"))).toBeNull();
});

test("security status failure blocks changes", async ({ page }) => {
  await page.routeWebSocket("**/api/v1/ws/live", () => {});
  await page.route("**/api/v1/**", async route => {
    if (route.request().url().endsWith("/auth/mfa")) return route.fulfill({ status: 503, json: { error: { message: "Unavailable" } } });
    const data = route.request().url().endsWith("/auth/login") ? {
      access_token: "test", user: { id: "A", enterprise_id: "A", roles: ["VIEWER"], is_first_login: false },
    } : [];
    await route.fulfill({ json: { data } });
  });
  await page.goto("/login");
  await page.getByLabel(/^Email/).fill("a@example.com");
  await page.getByLabel(/^Password/).fill("my-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: "Account security", exact: true }).click();
  await page.getByLabel("Current password").fill("my-password");
  await expect(page.getByText(/Security status unavailable/)).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("button", { name: "Set up authenticator" })).toBeDisabled();
});

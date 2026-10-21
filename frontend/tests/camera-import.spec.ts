import { expect, test, Page } from "@playwright/test";

async function openCameras(page: Page, role = "ENTERPRISE_ADMIN") {
  await page.routeWebSocket("**/api/v1/ws/live", () => {});
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let data: any = [];
    if (path.endsWith("/auth/login")) data = { access_token: "test-token", user: { id: "user", enterprise_id: "tenant", name: "Operator", email: "a@example.com", roles: [role], is_first_login: false } };
    if (path.endsWith("/branding")) data = { name: "Factory" };
    if (path.endsWith("/cameras")) data = [{ id: "camera-1", name: "Entrance", code: "ENT", status: "Inactive", rtsp_url: "rtsp://***:***@camera.invalid/feed", enforces: [] }];
    await route.fulfill({ json: { success: true, data, meta: { total: 0, page: 1, total_pages: 1 } } });
  });
  await page.goto("/login");
  await page.getByLabel(/^Email/).fill("a@example.com");
  await page.getByLabel(/^Password/).fill("test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: "Cameras", exact: true }).click();
}

test("uncertain import retries the same request and recovers the saved batch", async ({ page }) => {
  await openCameras(page);
  await page.route("**/cameras/import/preview", route => route.fulfill({ json: { data: { valid: true, preview_token: "signed-token", rows: [{ row: 2, name: "Door", code: "DOOR", zone_name: "Entry", factory_name: "Factory", errors: [] }] } } }));
  const attempts: any[] = [];
  await page.route("**/cameras/import/commit", async route => {
    attempts.push(route.request().postDataJSON());
    if (attempts.length === 1) await route.fulfill({ status: 503, json: { error: { message: "Retry this import" } } });
    else await route.fulfill({ json: { data: { cameras: [{ id: "new-camera" }], replayed: true } } });
  });
  await page.getByRole("button", { name: "Import CSV", exact: true }).click();
  await page.getByLabel("Camera CSV file").setInputFiles({ name: "cameras.csv", mimeType: "text/csv", buffer: Buffer.from("name,code,zone_id,rtsp_url\nDoor,DOOR,zone,rtsp://user:private-password@camera.invalid/feed\n") });
  await page.getByRole("button", { name: "Preview CSV", exact: true }).click();
  await expect(page.getByText("1 cameras validated.", { exact: false })).toBeVisible();
  await expect(page.getByText("private-password", { exact: false })).toHaveCount(0);
  await page.getByRole("button", { name: "Import inactive cameras" }).click();
  await expect(page.getByRole("button", { name: "Preview CSV", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Retry import", exact: true }).click();
  await expect(page.getByText(/1 cameras registered \(previous result recovered\)/)).toBeVisible();
  expect(attempts).toHaveLength(2);
  expect(attempts[1]).toEqual(attempts[0]);
  expect(attempts[0].request_key).toMatch(/^[a-f0-9-]{36}$/);
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain("private-password");
});

test("viewer cannot see management controls", async ({ page }) => {
  await openCameras(page, "VIEWER");
  await expect(page.getByRole("button", { name: "Import CSV", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Activate", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Test Connection", exact: true })).toHaveCount(0);
});

test("stored connection check uses camera ID and does not submit the redacted URL", async ({ page }) => {
  await openCameras(page);
  let checks = 0;
  await page.route("**/cameras/camera-1/health", async route => { checks++; await route.fulfill({ json: { data: { rtsp_reachable: true, rtsp_latency_ms: 30 } } }); });
  await page.getByRole("button", { name: "Test Connection", exact: true }).click();
  await expect(page.getByText(/Frame received — checked/)).toBeVisible();
  await page.getByRole("button", { name: "Edit camera" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Test", exact: true }).click();
  await expect.poll(() => checks).toBe(2);
  await expect(page.getByText("Stream reachable (30 ms)")).toBeVisible();
});

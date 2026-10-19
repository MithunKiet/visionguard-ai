import { expect, test, Page } from "@playwright/test";
import { readFile } from "node:fs/promises";

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
  const dialog = page.waitForEvent("dialog").then(async alert => {
    expect(alert.message()).toContain("Logout could not be confirmed");
    await alert.accept();
  });
  await page.getByTitle("Logout", { exact: true }).click();
  await dialog;
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

test("live video authenticates every asset, refreshes expiry, decodes video and stops on logout", async ({ page }) => {
  await mockApi(page);
  let refreshed = false;
  let requestedSegments = 0;
  await page.route("**/api/v1/auth/refresh", route => {
    refreshed = true;
    return route.fulfill({ json: { success: true, data: { access_token: "refreshed-token" } } });
  });
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { success: true, data:
    { id: "A", enterprise_id: "A", name: "A", roles: ["ENTERPRISE_ADMIN"], is_first_login: false } } }));
  await page.route("**/api/v1/cameras", route => route.fulfill({ json: { success: true, data:
    [{ id: "camera-a", name: "Secure camera", status: "Active", rtsp_url: "rtsp://private-camera/secret" }] } }));
  await page.route("**/api/v1/cameras/camera-a/live/*", async route => {
    const request = route.request();
    expect(new URL(request.url()).search).toBe("");
    if (!refreshed) {
      expect(request.headers().authorization).toBe("Bearer test-token-A");
      await route.fulfill({ status: 401, json: { detail: "Expired" } });
      return;
    }
    expect(request.headers().authorization).toBe("Bearer refreshed-token");
    const file = new URL(request.url()).pathname.split("/").pop()!;
    expect(file).toMatch(/^(index\.m3u8|init\.mp4|seg[0-3]\.mp4)$/);
    if (file.startsWith("seg")) requestedSegments++;
    await route.fulfill({ body: await readFile(new URL(`./fixtures/live/${file}`, import.meta.url)),
      contentType: file.endsWith("m3u8") ? "application/vnd.apple.mpegurl" : "video/mp4" });
  });
  await page.goto("/login");
  await signIn(page);
  await page.getByRole("link", { name: "Live Grid", exact: true }).click();
  await page.getByRole("button", { name: "Play live video", exact: true }).click();
  await expect.poll(() => page.locator("video").evaluate((video: HTMLVideoElement) => video.currentTime)).toBeGreaterThan(0);
  expect(refreshed).toBe(true);
  expect(requestedSegments).toBeGreaterThan(0);
  await expect(page.locator("iframe")).toHaveCount(0);
  await page.getByTitle("Logout", { exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator("video")).toHaveCount(0);
});

test("live video clears playback when camera access is denied", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/v1/cameras", route => route.fulfill({ json: { success: true, data:
    [{ id: "camera-a", name: "Secure camera", status: "Active" }] } }));
  await page.route("**/api/v1/cameras/camera-a/live/*", async route => {
    const file = new URL(route.request().url()).pathname.split("/").pop()!;
    if (file === "index.m3u8") {
      await route.fulfill({ body: await readFile(new URL("./fixtures/live/index.m3u8", import.meta.url)), contentType: "application/vnd.apple.mpegurl" });
    } else {
      await route.fulfill({ status: 404, json: { detail: "Camera not found" } });
    }
  });
  await page.goto("/login");
  await signIn(page);
  await page.getByRole("link", { name: "Live Grid", exact: true }).click();
  await page.getByRole("button", { name: "Play live video", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Live streaming is not configured or access is unavailable.");
  await expect(page.locator("video")).toHaveCount(0);
});

async function incidentApi(page: Page, options: { viewer?: boolean; failure?: number; snapshot?: string | null } = {}) {
  await mockApi(page);
  if (options.viewer) await page.route("**/api/v1/auth/login", route => route.fulfill({ json: {
    success: true, data: { access_token: "viewer-token", is_master_session: false,
      user: { id: "viewer", enterprise_id: "A", name: "Viewer", roles: ["VIEWER"], is_first_login: false } },
  } }));
  const incident = { id: "review-1", alert_number: "ALT-REVIEW-1", alert_type: "PPE_VIOLATION_HELMET",
    severity: "Critical", status: "Open", created_on: "2026-10-14T00:00:00Z", sla_due_at: "2026-10-14T00:15:00Z",
    acknowledged_on: null, resolved_on: null, violation_id: "violation-1", factory_name: "North factory",
    zone_name: "Loading bay", camera_name: "Entrance camera", review_history: [] as any[] };
  const writes: { path: string; body: any }[] = [];
  const lists: URL[] = [];
  let denied = false;
  await page.route("**/api/v1/alerts**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "PATCH") {
      writes.push({ path: url.pathname, body: request.postDataJSON() });
      if (options.failure) {
        if (options.failure === 409) {
          incident.status = "Resolved";
          incident.review_history.push({ id: "concurrent", from_status: "Open", to_status: "Resolved", reviewer_name: "Other reviewer", comment: "Already checked on site.", created_on: "2026-10-14T01:00:00Z" });
        }
        return route.fulfill({ status: options.failure, json: { success: false, error: { code: "REVIEW_FAILED" } } });
      }
      const from = incident.status;
      incident.status = url.pathname.endsWith("/resolve") ? "Resolved" : url.pathname.endsWith("/false-positive") ? "FalsePositive" : "Acknowledged";
      incident.review_history.push({ id: `history-${writes.length}`, from_status: from, to_status: incident.status,
        reviewer_name: "Safety reviewer", created_on: "2026-10-14T01:00:00Z", comment: request.postDataJSON().note ?? request.postDataJSON().reason ?? null });
      return route.fulfill({ json: { success: true, data: incident } });
    }
    if (url.pathname.endsWith("/review-1")) {
      return route.fulfill(denied ? { status: 404, json: { success: false } } : { json: { success: true, data: incident } });
    }
    lists.push(url);
    const matches = (!url.searchParams.get("status") || url.searchParams.get("status") === incident.status)
      && (!url.searchParams.get("severity") || url.searchParams.get("severity") === incident.severity);
    return route.fulfill({ json: { success: true, data: matches ? [incident] : [], meta: { total: matches ? 1 : 0 } } });
  });
  await page.route("**/api/v1/violations/violation-1", route => route.fulfill({ json: { success: true, data: {
    confidence: 0.82, created_on: "2026-10-14T00:00:00Z", needs_review: true, is_false_positive: false,
    snapshot_url: options.snapshot === undefined ? "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=" : options.snapshot,
  } } }));
  await page.goto("/login");
  await signIn(page);
  await page.getByRole("link", { name: "Alerts", exact: true }).click();
  await page.getByRole("button", { name: "Review ALT-REVIEW-1", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("North factory · Loading bay · Entrance camera");
  return { writes, lists, deny: () => { denied = true; } };
}

test("incident resolution requires a real note and displays saved history", async ({ page }) => {
  const state = await incidentApi(page);
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Model confidence: 82%");
  await expect(dialog.getByAltText("Incident snapshot")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Save review" })).toBeDisabled();
  await dialog.getByLabel("Resolution note").fill("   ");
  await expect(dialog.getByRole("button", { name: "Save review" })).toBeDisabled();
  await dialog.getByLabel("Resolution note").fill("  Checked the snapshot and corrected helmet use.  ");
  await dialog.getByRole("button", { name: "Save review" }).click();
  await expect(dialog).toContainText("Review saved.");
  await expect(dialog).toContainText("Open → Resolved");
  await expect(dialog).toContainText("Safety reviewer");
  await expect(dialog).toContainText("Checked the snapshot and corrected helmet use.");
  await expect(dialog.getByRole("button", { name: "Save review" })).toHaveCount(0);
  expect(state.writes).toEqual([{ path: "/api/v1/alerts/review-1/resolve", body: { note: "Checked the snapshot and corrected helmet use." } }]);
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await expect(page.getByText("No alerts for this filter.")).toBeVisible();
});

test("false-positive review enforces the reason limit and persists the selected outcome", async ({ page }) => {
  const state = await incidentApi(page, { snapshot: null });
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("No snapshot was recorded for this incident.");
  await dialog.getByLabel("Review decision").click();
  await page.getByRole("option", { name: "Mark as false positive" }).click();
  await dialog.getByLabel("False-positive reason").fill("x".repeat(201));
  await expect(dialog.getByRole("button", { name: "Save review" })).toBeDisabled();
  await dialog.getByLabel("False-positive reason").fill("Confirmed helmet on site; camera angle hid it.");
  await dialog.getByRole("button", { name: "Save review" }).click();
  await expect(dialog).toContainText("Open → False positive");
  expect(state.writes[0]).toEqual({ path: "/api/v1/alerts/review-1/false-positive", body: { reason: "Confirmed helmet on site; camera angle hid it." } });
});

test("viewers can inspect incident evidence but cannot submit decisions", async ({ page }) => {
  const state = await incidentApi(page, { viewer: true });
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("You have read-only access to incident reviews.");
  await expect(dialog.getByRole("button", { name: "Save review" })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "Acknowledge" })).toHaveCount(0);
  expect(state.writes).toHaveLength(0);
});

test("concurrent incident decisions refresh the status without overwriting the other review", async ({ page }) => {
  const state = await incidentApi(page, { failure: 409 });
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Resolution note").fill("My proposed resolution.");
  await dialog.getByRole("button", { name: "Save review" }).click();
  await expect(dialog).toContainText("The review was not accepted.");
  await expect(dialog).toContainText("Other reviewer");
  await expect(dialog).toContainText("Already checked on site.");
  await expect(dialog.getByRole("button", { name: "Save review" })).toHaveCount(0);
  await expect(dialog.getByText("Review saved.")).toHaveCount(0);
  expect(state.writes).toHaveLength(1);
});

test("failed incident saves retain the review note and do not claim success", async ({ page }) => {
  await incidentApi(page, { failure: 500 });
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Resolution note").fill("Keep this draft for retry.");
  await dialog.getByRole("button", { name: "Save review" }).click();
  await expect(dialog).toContainText("Could not confirm that the review was saved.");
  await expect(dialog.getByLabel("Resolution note")).toHaveValue("Keep this draft for retry.");
  await expect(dialog.getByText("Review saved.")).toHaveCount(0);
});

test("revoked incident access removes cached evidence and review actions", async ({ page }) => {
  const state = await incidentApi(page);
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByAltText("Incident snapshot")).toBeVisible();
  state.deny();
  await dialog.getByRole("button", { name: "Refresh evidence" }).click();
  await expect(dialog).toContainText("Incident could not be loaded.");
  await expect(dialog.getByAltText("Incident snapshot")).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "Save review" })).toHaveCount(0);
});

test("incident filters use server-side severity and status", async ({ page }) => {
  const state = await incidentApi(page);
  await page.getByRole("dialog").getByRole("button", { name: "Close", exact: true }).click();
  await page.getByLabel("Severity", { exact: true }).click();
  await page.getByRole("option", { name: "Low", exact: true }).click();
  await expect(page.getByText("No alerts for this filter.")).toBeVisible();
  expect(state.lists.some(url => url.searchParams.get("severity") === "Low" && url.searchParams.get("status") === "Open" && url.searchParams.get("page") === "1")).toBe(true);
});

test("user administration requests bounded pages and exposes users beyond page one", async ({ page }) => {
  await mockApi(page);
  const pages: number[] = [];
  await page.route("**/api/v1/users?**", async route => {
    const url = new URL(route.request().url());
    const current = Number(url.searchParams.get("page"));
    pages.push(current);
    expect(url.searchParams.get("page_size")).toBe("20");
    await route.fulfill({ json: { success: true,
      data: [{ id: `user-${current}`, name: `User from page ${current}`, email: `page-${current}@example.com`,
        roles: ["VIEWER"], status: "Active" }], meta: { total: 41, page: current, page_size: 20, total_pages: 3 } } });
  });
  await page.goto("/login");
  await signIn(page);
  await page.getByRole("link", { name: "Users", exact: true }).click();
  await expect(page.getByText("User from page 1", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Go to next page" }).click();
  await expect(page.getByText("User from page 2", { exact: true })).toBeVisible();
  expect(pages).toEqual([1, 2]);
  await expect(page.getByText("21–40 of 41", { exact: true })).toBeVisible();
});

test("deactivating the last user on a page returns to the preceding valid page", async ({ page }) => {
  await mockApi(page);
  let removed = false;
  const pages: number[] = [];
  await page.route("**/api/v1/users**", async route => {
    if (route.request().method() === "DELETE") {
      expect(new URL(route.request().url()).pathname).toBe("/api/v1/users/last-user");
      removed = true;
      return route.fulfill({ json: { success: true, data: null } });
    }
    const current = Number(new URL(route.request().url()).searchParams.get("page"));
    pages.push(current);
    const items = current === 1 ? [{ id: "first-user", name: "First user" }]
      : removed ? [] : [{ id: "last-user", name: "Last user" }];
    await route.fulfill({ json: { success: true,
      data: items.map(user => ({ ...user, email: `${user.id}@example.com`, roles: ["VIEWER"], status: "Active" })),
      meta: { total: removed ? 20 : 21, page: current, page_size: 20, total_pages: removed ? 1 : 2 } } });
  });
  await page.goto("/login");
  await signIn(page);
  await page.getByRole("link", { name: "Users", exact: true }).click();
  await expect(page.getByText("First user", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Go to next page" }).click();
  await expect(page.getByText("Last user", { exact: true })).toBeVisible();
  await page.getByTitle("Deactivate user", { exact: true }).click();
  await expect(page.getByText("First user", { exact: true })).toBeVisible();
  await expect(page.getByText("1–20 of 20", { exact: true })).toBeVisible();
  expect(removed).toBe(true);
  expect(pages.slice(-2)).toEqual([2, 1]);
});

test("failed user loads show an error and can be retried without claiming an empty directory", async ({ page }) => {
  await mockApi(page);
  let fail = true;
  await page.route("**/api/v1/users?**", route => route.fulfill(fail
    ? { status: 503, json: { success: false } }
    : { json: { success: true, data: [{ id: "recovered", name: "Recovered user", email: "user@example.com",
      roles: [], status: "Active" }], meta: { total: 1, page: 1, page_size: 20, total_pages: 1 } } }));
  await page.goto("/login");
  await signIn(page);
  await page.getByRole("link", { name: "Users", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Users could not be loaded.");
  await expect(page.getByText("No users yet.", { exact: true })).toHaveCount(0);
  fail = false;
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByText("Recovered user", { exact: true })).toBeVisible();
});

test("viewers cannot request user administration data through direct navigation", async ({ page }) => {
  const calls = await mockApi(page);
  await page.route("**/api/v1/auth/login", route => route.fulfill({ json: { success: true, data: {
    access_token: "viewer-token", is_master_session: false,
    user: { id: "viewer", enterprise_id: "A", name: "Viewer", roles: ["VIEWER"], is_first_login: false },
  } } }));
  await page.goto("/login");
  await signIn(page);
  await page.evaluate(() => { window.history.pushState({}, "", "/users"); window.dispatchEvent(new PopStateEvent("popstate")); });
  await expect(page.getByText("User administration access is required.")).toBeVisible();
  expect(calls.filter(path => path.startsWith("/api/v1/users"))).toHaveLength(0);
});

import { expect, test, Page, WebSocketRoute } from "@playwright/test";

async function liveApi(page: Page) {
  const sockets: WebSocketRoute[] = [];
  const active = new Set<WebSocketRoute>();
  const calls: string[] = [];
  const state = { total: 3, tenant: "A" };
  await page.routeWebSocket("**/api/v1/ws/live", socket => {
    sockets.push(socket);
    active.add(socket);
    socket.onClose(() => active.delete(socket));
  });
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    calls.push(url.pathname);
    let data: any = [];
    let meta = { total: 0, page: 1, total_pages: 1, page_size: 50 };
    if (url.pathname.endsWith("/auth/login")) {
      state.tenant = route.request().postDataJSON().email.startsWith("b") ? "B" : "A";
      data = { access_token: `test-token-${state.tenant}`, is_master_session: false,
        user: { id: state.tenant, enterprise_id: state.tenant, name: state.tenant,
          email: `${state.tenant}@example.com`, roles: ["ENTERPRISE_ADMIN"], is_first_login: false } };
    } else if (url.pathname.endsWith("/branding")) {
      data = { name: `Enterprise ${state.tenant}` };
    } else if (url.pathname.endsWith("/alerts")) {
      meta.total = state.total;
      if (url.searchParams.get("page_size") !== "1") {
        data = [{ id: "incident", alert_number: `ALT-${state.total}`, alert_type: "PPE_VIOLATION_HELMET",
          severity: "Critical", status: "Open", created_on: "2026-10-18T00:00:00Z" }];
      }
    }
    await route.fulfill({ json: { success: true, data, meta } });
  });
  await page.goto("/login");
  await signIn(page);
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
  return { sockets, active, calls, state };
}

async function signIn(page: Page, email = "a@example.com") {
  await page.getByLabel(/^Email/).fill(email);
  await page.getByLabel(/^Password/).fill("test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

const stat = (page: Page, label: string) => page.getByText(label, { exact: true }).locator("..").locator("h6");

test("header and dashboard share one live connection across navigation", async ({ page }) => {
  const live = await liveApi(page);
  await expect.poll(() => live.active.size).toBe(1);
  const count = live.sockets.length;
  await page.getByRole("link", { name: "Alerts", exact: true }).click();
  await expect(page.getByText("ALT-3", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Dashboard", exact: true }).click();
  await expect(stat(page, "Open Alerts")).toHaveText("3");
  expect(live.active.size).toBe(1);
  expect(live.sockets.length).toBe(count);
});

test("reconnect immediately reloads alerts missed while disconnected", async ({ page }) => {
  const live = await liveApi(page);
  await page.getByRole("link", { name: "Alerts", exact: true }).click();
  await expect(page.getByText("ALT-3", { exact: true })).toBeVisible();
  const previous = live.sockets.length;
  live.sockets.at(-1)!.close({ code: 1012, reason: "Test restart" });
  await expect(page.getByText("Disconnected", { exact: true })).toBeVisible();
  live.state.total = 9;
  await expect.poll(() => live.sockets.length, { timeout: 8000 }).toBe(previous + 1);
  // The alerts page polls every 15 seconds; this must recover through reconnect.
  await expect(page.getByText("ALT-9", { exact: true })).toBeVisible({ timeout: 4000 });
});

test("occupancy clears on disconnect and expires even while the socket stays live", async ({ page }) => {
  await page.clock.install();
  const live = await liveApi(page);
  live.sockets.at(-1)!.send(JSON.stringify({ type: "occupancy.updated", data: { current_count: 7 } }));
  await expect(stat(page, "Latest Camera Count")).toHaveText("7");
  live.sockets.at(-1)!.close({ code: 1012, reason: "Test restart" });
  await expect(stat(page, "Latest Camera Count")).toHaveText("Offline");
  await page.clock.fastForward(2100);
  await expect(stat(page, "Latest Camera Count")).toHaveText("Awaiting update");
  live.sockets.at(-1)!.send(JSON.stringify({ type: "occupancy.updated", data: { current_count: 0 } }));
  await expect(stat(page, "Latest Camera Count")).toHaveText("0");
  await page.clock.fastForward(61000);
  await expect(stat(page, "Latest Camera Count")).toHaveText("Awaiting update");
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
});

test("alert bursts are coalesced and occupancy or malformed frames do not refetch summaries", async ({ page }) => {
  await page.clock.install();
  const live = await liveApi(page);
  await expect(stat(page, "Open Alerts")).toHaveText("3");
  const count = () => live.calls.filter(path => path.endsWith("/alerts")).length;
  const before = count();
  live.state.total = 8;
  for (let i = 0; i < 100; i++) {
    live.sockets.at(-1)!.send(JSON.stringify({ type: "alert.created", data: { alert_number: `BURST-${i}` } }));
  }
  await expect(page.getByText("BURST-99", { exact: true })).toBeVisible();
  await page.clock.fastForward(1100);
  await expect(stat(page, "Open Alerts")).toHaveText("8");
  expect(count() - before).toBe(3); // Total, critical and high; one summary refresh.
  const after = count();
  for (let i = 0; i < 100; i++) {
    live.sockets.at(-1)!.send(JSON.stringify({ type: "occupancy.updated", data: { current_count: i } }));
  }
  for (const payload of ["null", "not-json", '{"type":"__proto__","data":{}}',
    '{"type":"alert.created","data":null}', '{"type":"occupancy.updated","data":{"current_count":-1}}']) {
    live.sockets.at(-1)!.send(payload);
  }
  await expect(stat(page, "Latest Camera Count")).toHaveText("99");
  await page.clock.fastForward(2000);
  expect(count()).toBe(after);
  await expect(stat(page, "Latest Camera Count")).toHaveText("99");
});

test("logout cancels reconnect and clears event buffers before another tenant signs in", async ({ page }) => {
  await page.clock.install();
  const live = await liveApi(page);
  live.sockets.at(-1)!.send(JSON.stringify({ type: "alert.created", data: { alert_number: "PRIVATE-TENANT-A" } }));
  await expect(page.getByText("PRIVATE-TENANT-A", { exact: true })).toBeVisible();
  live.sockets.at(-1)!.close({ code: 1012, reason: "Test restart" });
  await expect(page.getByText("Disconnected", { exact: true })).toBeVisible();
  const count = live.sockets.length;
  await page.getByTitle("Logout", { exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.clock.fastForward(20000);
  expect(live.sockets.length).toBe(count);
  await signIn(page, "b@example.com");
  await expect(page.getByText("Enterprise B", { exact: true })).toBeVisible();
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
  expect(live.sockets.length).toBe(count + 1);
  await expect(page.getByText("PRIVATE-TENANT-A", { exact: true })).toHaveCount(0);
  await expect(stat(page, "Latest Camera Count")).toHaveText("Awaiting update");
});

test("HTTP token refresh replaces the socket and removes prior-token live state", async ({ page }) => {
  const live = await liveApi(page);
  live.sockets.at(-1)!.send(JSON.stringify({ type: "occupancy.updated", data: { current_count: 7 } }));
  await expect(stat(page, "Latest Camera Count")).toHaveText("7");
  const count = live.sockets.length;
  let expired = true;
  await page.route("**/api/v1/cameras", async route => {
    if (expired) {
      expired = false;
      return route.fulfill({ status: 401, json: { detail: "Expired" } });
    }
    expect(route.request().headers().authorization).toBe("Bearer replacement-token");
    return route.fulfill({ json: { success: true, data: [] } });
  });
  await page.route("**/api/v1/auth/refresh", route => route.fulfill({ json: {
    success: true, data: { access_token: "replacement-token" },
  } }));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { success: true, data: {
    id: "A", enterprise_id: "A", name: "A", email: "a@example.com", roles: ["ENTERPRISE_ADMIN"], is_first_login: false,
  } } }));
  await page.getByRole("link", { name: "Cameras", exact: true }).click();
  await expect.poll(() => live.sockets.length).toBe(count + 1);
  await expect.poll(() => live.active.size).toBe(1);
  await page.getByRole("link", { name: "Dashboard", exact: true }).click();
  await expect(stat(page, "Latest Camera Count")).toHaveText("Awaiting update");
});

test("a response started before reconnect cannot replace the required fresh snapshot", async ({ page }) => {
  await page.clock.install();
  const live = await liveApi(page);
  await page.getByRole("link", { name: "Alerts", exact: true }).click();
  await expect(page.getByText("ALT-3", { exact: true })).toBeVisible();
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let requests = 0;
  await page.route("**/api/v1/alerts?**", async route => {
    requests++;
    const total = live.state.total;
    if (requests === 1) await held;
    await route.fulfill({ json: { success: true, data: [{ id: "incident", alert_number: `ALT-${total}`,
      alert_type: "PPE_VIOLATION_HELMET", severity: "Critical", status: "Open", created_on: "2026-10-18T00:00:00Z" }],
      meta: { total, page: 1, total_pages: 1 } } });
  });
  await page.clock.fastForward(15000);
  await expect.poll(() => requests).toBe(1);
  live.sockets.at(-1)!.close({ code: 1012, reason: "Test restart" });
  await expect(page.getByText("Disconnected", { exact: true })).toBeVisible();
  live.state.total = 9;
  await page.clock.fastForward(2100);
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
  release();
  await expect(page.getByText("ALT-9", { exact: true })).toBeVisible({ timeout: 4500 });
});

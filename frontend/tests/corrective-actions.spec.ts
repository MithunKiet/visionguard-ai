import { expect, Page, test } from "@playwright/test";

const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=", "base64");
async function setup(page: Page, state: any, role = "ENTERPRISE_ADMIN") {
  state.plan = { revision: 0, plan_version: 0, description: null, assigned_to: null, assignee_name: null,
    assignee_active: true, due_at: null, completed_at: null, status: "NotPlanned", overdue: false, evidence: [] };
  state.history = []; state.uploadIds = []; state.savedRevisions = []; state.lists = [];
  state.incident = { id: "incident", alert_number: "ALT-ACTION", alert_type: "PPE_VIOLATION_HELMET", severity: "High", status: "Open",
    created_on: "2026-10-20T00:00:00Z", sla_due_at: null, violation_id: null, review_history: state.history };
  await page.routeWebSocket("**/api/v1/ws/live", () => {});
  await page.route("**/api/v1/**", async route => {
    const request = route.request(); const path = new URL(request.url()).pathname;
    let data: any = []; let meta = { total: 0, total_pages: 1 };
    if (path.endsWith("/auth/login")) data = { access_token: "action-token", is_master_session: false,
      user: { id: "admin", enterprise_id: "company", name: "Admin", roles: [role], is_first_login: false } };
    else if (path === "/api/v1/alerts") { data = [state.incident]; meta.total = 1; state.lists.push(request.url()); }
    else if (path === "/api/v1/alerts/incident") data = state.incident;
    else if (path.endsWith("/assignees")) { data = [{ id: "manager", name: "Safety manager" }]; meta.total = 1; }
    else if (path.endsWith("/corrective-action")) {
      if (request.method() === "PUT") {
        const body = request.postDataJSON(); state.savedRevisions.push(body.expected_revision);
        if (state.conflict || body.expected_revision !== state.plan.revision) return route.fulfill({ status: 409, json: { error: { message: "The action changed. Refresh and check it before retrying" } } });
        Object.assign(state.plan, { revision: state.plan.revision + 1, plan_version: state.plan.plan_version + 1,
          description: body.description, assigned_to: body.assigned_to, assignee_name: "Safety manager", due_at: body.due_at, status: "Planned" });
        state.history.push({ id: "planned", event_type: "ACTION_PLANNED", comment: "Plan saved for Safety manager", reviewer_name: "Admin" });
      }
      data = state.plan;
    } else if (path.endsWith("/corrective-action/evidence")) {
      const body = request.postDataBuffer()!.toString();
      const key = /name="upload_id"\r\n\r\n([^\r\n]+)/.exec(body)![1];
      state.uploadIds.push(key);
      if (!state.plan.evidence.length) {
        state.plan.evidence.push({ id: key, filename: "corrected.png", sha256: "test-hash", current_plan: true, plan_version: 1 }); state.plan.revision++;
        state.history.push({ id: "photo", event_type: "EVIDENCE_ADDED", comment: "Corrective photo attached", reviewer_name: "Admin" });
      }
      if (state.loseUploadReply) return route.abort("connectionfailed");
      data = state.plan;
    } else if (path.includes("/corrective-action/evidence/")) {
      if (state.denyPhoto) return route.fulfill({ status: 403, json: { success: false } });
      return route.fulfill({ contentType: "image/png", body: png });
    } else if (path.endsWith("/corrective-action/complete")) {
      state.plan.completed_at = new Date().toISOString(); state.plan.status = "Completed"; state.plan.revision++;
      state.history.push({ id: "completed", event_type: "ACTION_COMPLETED", comment: request.postDataJSON().note, reviewer_name: "Safety manager" });
      data = state.plan;
    } else if (path.endsWith("/resolve")) {
      state.incident.status = "Resolved";
      state.history.push({ id: "closed", from_status: "Open", to_status: "Resolved", comment: request.postDataJSON().note, reviewer_name: "Admin" });
      data = state.incident;
    } else if (path.endsWith("/branding")) data = { name: "Company" };
    await route.fulfill({ json: { success: true, data, meta } });
  });
  await page.goto("/login");
  await page.getByLabel(/^Email/).fill("admin@example.com"); await page.getByLabel(/^Password/).fill("test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: "Alerts", exact: true }).click();
  await page.getByRole("button", { name: "Review ALT-ACTION", exact: true }).click();
}

async function plan(page: Page) {
  await page.getByLabel("Corrective action plan", { exact: true }).fill("Replace damaged helmet and inspect the area.");
  await page.getByLabel("Responsible person", { exact: true }).click();
  await page.getByRole("option", { name: "Safety manager", exact: true }).click();
  await page.getByLabel("Action due date", { exact: true }).fill("2027-01-01T12:00");
  await page.getByRole("button", { name: "Save corrective plan", exact: true }).click();
  await expect(page.getByText("Corrective plan saved.", { exact: true })).toBeVisible();
}

test("plan, current photo, completion note and final review form one incident workflow", async ({ page }) => {
  const state: any = {}; await setup(page, state); await plan(page);
  await page.getByLabel("Resolution note").fill("Checked proof before closing.");
  await expect(page.getByRole("button", { name: "Save review", exact: true })).toBeDisabled();
  await page.getByLabel("Corrective completion note", { exact: true }).fill("Helmet replaced and checked on site.");
  await expect(page.getByRole("button", { name: "Complete corrective action", exact: true })).toBeDisabled();
  await page.getByLabel("Corrective photo", { exact: true }).setInputFiles({ name: "corrected.png", mimeType: "image/png", buffer: png });
  await page.getByRole("button", { name: "Attach corrective photo", exact: true }).click();
  await expect(page.getByText("Corrective photo attached.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "View corrective photo: corrected.png", exact: true }).click();
  await expect(page.getByAltText("Corrective action photo")).toBeVisible();
  await page.getByRole("button", { name: "Complete corrective action", exact: true }).click();
  await expect(page.getByText("Action status: Completed", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Save review", exact: true }).click();
  await expect(page.getByText("Open → Resolved", { exact: true })).toBeVisible();
  expect(state.history.map((entry: any) => entry.event_type ?? "STATUS_CHANGED")).toEqual(["ACTION_PLANNED", "EVIDENCE_ADDED", "ACTION_COMPLETED", "STATUS_CHANGED"]);
});

test("lost upload reply retries the same photo reference and denied reads clear previews", async ({ page }) => {
  const state: any = { loseUploadReply: true }; await setup(page, state); await plan(page);
  await page.getByLabel("Corrective photo", { exact: true }).setInputFiles({ name: "corrected.png", mimeType: "image/png", buffer: png });
  await page.getByRole("button", { name: "Attach corrective photo", exact: true }).click();
  await expect(page.getByText(/Check the refreshed action before retrying/)).toBeVisible();
  state.loseUploadReply = false;
  await page.getByRole("button", { name: "Attach corrective photo", exact: true }).click();
  await expect(page.getByText("Corrective photo attached.", { exact: true })).toBeVisible();
  expect(state.uploadIds).toHaveLength(2); expect(state.uploadIds[0]).toBe(state.uploadIds[1]);
  await page.getByRole("button", { name: "View corrective photo: corrected.png", exact: true }).click();
  await expect(page.getByAltText("Corrective action photo")).toBeVisible();
  state.denyPhoto = true;
  await page.getByRole("button", { name: "View corrective photo: corrected.png", exact: true }).click();
  await expect(page.getByText(/Corrective photo could not be loaded/)).toBeVisible();
  await expect(page.getByAltText("Corrective action photo")).toHaveCount(0);
});

test("concurrent plan changes preserve the draft and send the original revision", async ({ page }) => {
  const state: any = {}; await setup(page, state);
  await page.getByLabel("Corrective action plan", { exact: true }).fill("My unsaved corrective plan");
  await page.getByLabel("Responsible person", { exact: true }).click(); await page.getByRole("option", { name: "Safety manager" }).click();
  await page.getByLabel("Action due date", { exact: true }).fill("2027-01-01T12:00");
  state.plan.revision = 1;
  await page.getByLabel("Resolution note").fill("A final review must not discard my unsaved plan.");
  await expect(page.getByRole("button", { name: "Save review", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Refresh evidence", exact: true }).click();
  await expect(page.getByText(/The action changed while you were editing/)).toBeVisible();
  await page.getByRole("button", { name: "Save corrective plan", exact: true }).click();
  await expect(page.getByText(/Check the refreshed action before retrying/)).toBeVisible();
  await expect(page.getByLabel("Corrective action plan", { exact: true })).toHaveValue("My unsaved corrective plan");
  expect(state.savedRevisions).toEqual([0]);
});

test("viewers cannot mutate plans and overdue filter is sent to the server", async ({ page }) => {
  const state: any = {}; await setup(page, state, "VIEWER");
  await expect(page.getByLabel("Corrective action plan", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Attach corrective photo", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.getByLabel("Overdue corrective actions only", { exact: true }).check();
  await expect.poll(() => state.lists.some((url: string) => new URL(url).searchParams.get("corrective_overdue") === "true")).toBe(true);
});

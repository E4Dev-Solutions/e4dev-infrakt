import { test, expect } from "@playwright/test";
import {
  login,
  mockApi,
  MOCK_APPS,
  MOCK_ENV_VARS,
  MOCK_DEPLOYMENTS,
} from "./fixtures";

const APP = MOCK_APPS[0]; // web-api

test.describe("App Detail", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/apps/${APP.name}`);
  });

  // ─── Header & info ──────────────────────────────────────────────────────────

  test("displays app name heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: APP.name }),
    ).toBeVisible();
  });

  test("shows server name and domain in subtitle", async ({ page }) => {
    await expect(page.getByText(APP.server_name)).toBeVisible();
    await expect(page.getByText(APP.domain!)).toBeVisible();
  });

  test("shows app type and branch", async ({ page }) => {
    await expect(page.getByText(APP.app_type)).toBeVisible();
    await expect(page.getByText(APP.branch!)).toBeVisible();
  });

  test("shows status badge", async ({ page }) => {
    await expect(page.getByText("running").first()).toBeVisible();
  });

  // ─── Action buttons ─────────────────────────────────────────────────────────

  test("has all action buttons", async ({ page }) => {
    await expect(page.getByRole("button", { name: "Edit" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Deploy" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Restart" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Destroy" })).toBeVisible();
  });

  test("Restart button shows toast", async ({ page }) => {
    await page.getByRole("button", { name: "Restart" }).click();
    await expect(page.getByText(/restarted/i)).toBeVisible();
  });

  test("Stop button shows toast", async ({ page }) => {
    await page.getByRole("button", { name: "Stop" }).click();
    await expect(page.getByText(/stopped/i)).toBeVisible();
  });

  test("Destroy button shows confirmation dialog", async ({ page }) => {
    let dialogMessage = "";
    page.on("dialog", (dialog) => {
      dialogMessage = dialog.message();
      void dialog.accept();
    });
    await page.getByRole("button", { name: "Destroy" }).click();
    expect(dialogMessage).toContain(APP.name);
  });

  // ─── Edit modal ─────────────────────────────────────────────────────────────

  test("Edit button opens modal with all fields", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(
      page.getByRole("heading", { name: "Edit App" }),
    ).toBeVisible();
    await expect(page.getByLabel("Domain")).toBeVisible();
    await expect(page.getByLabel("Port")).toBeVisible();
    await expect(page.getByLabel("Git Repository")).toBeVisible();
    await expect(page.getByLabel("Branch")).toBeVisible();
    await expect(page.getByLabel("Docker Image")).toBeVisible();
  });

  test("Edit modal fields are pre-populated with app data", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByLabel("Domain")).toHaveValue(APP.domain!);
    await expect(page.getByLabel("Port")).toHaveValue(String(APP.port));
    await expect(page.getByLabel("Git Repository")).toHaveValue(APP.git_repo!);
    await expect(page.getByLabel("Branch")).toHaveValue(APP.branch!);
  });

  test("Cancel closes Edit modal", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(
      page.getByRole("heading", { name: "Edit App" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(
      page.getByRole("heading", { name: "Edit App" }),
    ).not.toBeVisible();
  });

  test("Escape closes Edit modal", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(
      page.getByRole("heading", { name: "Edit App" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("heading", { name: "Edit App" }),
    ).not.toBeVisible();
  });

  test("Edit submit shows success toast and closes modal", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByLabel("Domain").fill("new.example.com");
    await page
      .locator("form")
      .getByRole("button", { name: "Save Changes" })
      .click();
    await expect(page.getByText("App configuration updated")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Edit App" }),
    ).not.toBeVisible();
  });

  // ─── Logs tab ───────────────────────────────────────────────────────────────

  test("Logs tab is active by default and shows log content", async ({
    page,
  }) => {
    await expect(page.getByRole("tab", { name: "Logs" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByText("Container started")).toBeVisible();
  });

  test("Live toggle button is visible on Logs tab", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /live/i }),
    ).toBeVisible();
  });

  // ─── Environment tab ───────────────────────────────────────────────────────

  test("Environment tab shows env variables", async ({ page }) => {
    await page.getByRole("tab", { name: "Environment" }).click();
    for (const v of MOCK_ENV_VARS) {
      await expect(page.getByText(v.key)).toBeVisible();
    }
  });

  test("Environment tab has add form", async ({ page }) => {
    await page.getByRole("tab", { name: "Environment" }).click();
    await expect(page.getByPlaceholder("DATABASE_URL")).toBeVisible();
    await expect(page.getByPlaceholder("postgres://...")).toBeVisible();
    await expect(page.getByRole("button", { name: "Add", exact: true })).toBeVisible();
  });

  test("Environment tab has delete buttons for each variable", async ({
    page,
  }) => {
    await page.getByRole("tab", { name: "Environment" }).click();
    // Each env var row should have a delete button
    const deleteButtons = page.getByLabel("Delete", { exact: false });
    await expect(deleteButtons).toHaveCount(MOCK_ENV_VARS.length);
  });

  // ─── Deployments tab ───────────────────────────────────────────────────────

  test("Deployments tab shows deployment history", async ({ page }) => {
    await page.getByRole("tab", { name: "Deployments" }).click();
    // Should show deployment IDs
    for (const dep of MOCK_DEPLOYMENTS) {
      await expect(page.getByText(`#${dep.id}`)).toBeVisible();
    }
  });

  test("Deployments tab shows commit refs", async ({ page }) => {
    await page.getByRole("tab", { name: "Deployments" }).click();
    // First deployment's commit hash truncated to 8 chars
    const shortHash = MOCK_DEPLOYMENTS[0].commit_hash.slice(0, 8);
    await expect(page.getByText(shortHash)).toBeVisible();
  });

  test("Deployments tab shows status badges", async ({ page }) => {
    await page.getByRole("tab", { name: "Deployments" }).click();
    await expect(page.getByText("success").first()).toBeVisible();
    await expect(page.getByText("failed")).toBeVisible();
  });

  test("Rollback button visible on non-latest successful deployments", async ({
    page,
  }) => {
    await page.getByRole("tab", { name: "Deployments" }).click();
    // The first deployment (idx=0) should NOT have rollback
    // The third deployment (idx=2, id=1, success) should have rollback
    await expect(page.getByLabel("Rollback")).toBeVisible();
  });

  // ─── Health tab ─────────────────────────────────────────────────────────────

  test("Health tab shows Check Health button", async ({ page }) => {
    await page.getByRole("tab", { name: "Health" }).click();
    await expect(
      page.getByRole("button", { name: "Check Health" }),
    ).toBeVisible();
  });

  test("Health tab shows container info after check", async ({ page }) => {
    await page.getByRole("tab", { name: "Health" }).click();
    await page.getByRole("button", { name: "Check Health" }).click();
    await expect(page.getByText("infrakt-web-api")).toBeVisible();
    await expect(page.getByText("Up 2 hours")).toBeVisible();
    await expect(page.getByText("nginx:latest")).toBeVisible();
  });
});

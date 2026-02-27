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
    await expect(page.getByText(APP.server_name).first()).toBeVisible();
    await expect(page.getByText(APP.domain!).first()).toBeVisible();
  });

  test("shows app type and branch", async ({ page }) => {
    await expect(page.getByText(APP.app_type).first()).toBeVisible();
    await expect(page.getByText(APP.branch!).first()).toBeVisible();
  });

  test("shows status badge", async ({ page }) => {
    await expect(page.getByText("running").first()).toBeVisible();
  });

  // ─── Action buttons ─────────────────────────────────────────────────────────

  test("has Deploy, Restart, Stop buttons and kebab menu", async ({ page }) => {
    await expect(page.getByRole("button", { name: "Deploy" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Restart" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
    await expect(page.getByRole("button", { name: "More actions" })).toBeVisible();
  });

  test("Restart button shows toast", async ({ page }) => {
    await page.getByRole("button", { name: "Restart" }).click();
    await expect(page.getByText(/restarted/i)).toBeVisible();
  });

  test("Stop button shows toast", async ({ page }) => {
    await page.getByRole("button", { name: "Stop" }).click();
    await expect(page.getByText(/stopped/i)).toBeVisible();
  });

  test("Destroy is in kebab menu and shows confirmation", async ({ page }) => {
    let dialogMessage = "";
    page.on("dialog", (dialog) => {
      dialogMessage = dialog.message();
      void dialog.accept();
    });
    await page.getByRole("button", { name: "More actions" }).click();
    await page.getByText("Destroy App").click();
    expect(dialogMessage).toContain(APP.name);
  });

  // ─── Overview tab (default) ──────────────────────────────────────────────────

  test("Overview tab is active by default", async ({ page }) => {
    await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("Overview shows stat cards", async ({ page }) => {
    await expect(page.getByText("Status")).toBeVisible();
    await expect(page.getByText("Last Deploy")).toBeVisible();
    await expect(page.getByText("App Type")).toBeVisible();
  });

  test("Overview shows Quick Info section", async ({ page }) => {
    await expect(page.getByText("Quick Info")).toBeVisible();
    // Server name appears in both header subtitle and Quick Info — scope to Overview panel
    await expect(page.getByLabel("Overview").getByText(APP.server_name)).toBeVisible();
  });

  test("Overview shows container metrics after refresh", async ({ page }) => {
    await page.getByRole("button", { name: "Refresh" }).click();
    await expect(page.getByText("infrakt-web-api")).toBeVisible();
  });

  test("Overview shows recent deploys", async ({ page }) => {
    await expect(page.getByText("Recent Deploys")).toBeVisible();
    // Should show deployment IDs
    await expect(page.getByText(`#${MOCK_DEPLOYMENTS[0].id}`)).toBeVisible();
  });

  // ─── Logs tab ───────────────────────────────────────────────────────────────

  test("Logs tab shows log content", async ({ page }) => {
    await page.getByRole("tab", { name: "Logs" }).click();
    await expect(page.getByText("Container started")).toBeVisible();
  });

  test("Live toggle button is visible on Logs tab", async ({ page }) => {
    await page.getByRole("tab", { name: "Logs" }).click();
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

  // ─── Settings tab ──────────────────────────────────────────────────────────

  test("Settings tab shows form sections", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await expect(page.getByText("General")).toBeVisible();
    await expect(page.getByText("Resources")).toBeVisible();
    await expect(page.getByText("Health Check")).toBeVisible();
  });

  test("Settings pre-populates with app data", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await expect(page.getByLabel("Domain")).toHaveValue(APP.domain!);
    await expect(page.getByLabel("Port")).toHaveValue(String(APP.port));
  });

  test("Settings Save button is disabled when no changes", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await expect(page.getByRole("button", { name: "Save Changes" })).toBeDisabled();
  });

  test("Settings Save button enables on change and shows toast", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await page.getByLabel("Domain").fill("new.example.com");
    const saveBtn = page.getByRole("button", { name: "Save Changes" });
    await expect(saveBtn).toBeEnabled();
    await saveBtn.click();
    await expect(page.getByText("App configuration updated")).toBeVisible();
  });

  test("Settings Danger Zone is collapsed by default", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await expect(page.getByText("Danger Zone")).toBeVisible();
    // Destroy button should not be visible when collapsed
    await expect(
      page.locator("[id='tabpanel-settings']").getByRole("button", { name: "Destroy App" }),
    ).not.toBeVisible();
  });

  test("Settings Danger Zone expands and shows Destroy button", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await page.getByText("Danger Zone").click();
    await expect(
      page.locator("[id='tabpanel-settings']").getByRole("button", { name: "Destroy App" }),
    ).toBeVisible();
  });
});

import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_APPS } from "./fixtures";

test.describe("Health Tab", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/apps/${MOCK_APPS[0].name}`);
    await page.getByRole("tab", { name: "Health" }).click();
  });

  test("shows prompt to check health before first check", async ({ page }) => {
    // The health hook has enabled:false so data won't load automatically
    // But mockApi intercepts the route, so we need to verify the initial UI state
    await expect(page.getByRole("button", { name: /Check Health/ })).toBeVisible();
  });

  test("Check Health button triggers health check", async ({ page }) => {
    await page.getByRole("button", { name: /Check Health/ }).click();
    // After clicking, should show container data
    await expect(page.getByText("infrakt-web-api")).toBeVisible();
  });

  test("displays actual status badge after check", async ({ page }) => {
    await page.getByRole("button", { name: /Check Health/ }).click();
    await expect(page.getByText("Actual Status")).toBeVisible();
  });

  test("displays container table with health info", async ({ page }) => {
    await page.getByRole("button", { name: /Check Health/ }).click();
    // Container table headers
    await expect(page.getByText("Container", { exact: true })).toBeVisible();
    await expect(page.getByText("Healthcheck")).toBeVisible();
    // Container data
    await expect(page.getByText("infrakt-web-api")).toBeVisible();
    await expect(page.getByText("Up 2 hours")).toBeVisible();
    await expect(page.getByText("nginx:latest")).toBeVisible();
  });

  test("shows status mismatch warning when detected", async ({ page }) => {
    // Override health route to return a mismatch
    await page.route("**/api/apps/*/health", (route) => {
      return route.fulfill({
        json: {
          app_name: "web-api",
          db_status: "running",
          actual_status: "stopped",
          status_mismatch: true,
          containers: [],
          checked_at: new Date().toISOString(),
        },
      });
    });

    await page.getByRole("button", { name: /Check Health/ }).click();
    await expect(page.getByText(/updated to match/)).toBeVisible();
  });

  test("shows empty container message when no containers", async ({ page }) => {
    await page.route("**/api/apps/*/health", (route) => {
      return route.fulfill({
        json: {
          app_name: "web-api",
          db_status: "stopped",
          actual_status: "stopped",
          status_mismatch: false,
          containers: [],
          checked_at: new Date().toISOString(),
        },
      });
    });

    await page.getByRole("button", { name: /Check Health/ }).click();
    await expect(page.getByText(/No containers found/)).toBeVisible();
  });
});

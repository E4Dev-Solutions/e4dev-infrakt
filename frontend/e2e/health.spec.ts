import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_APPS } from "./fixtures";

test.describe("Overview — Container Health", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/apps/${MOCK_APPS[0].name}`);
    // Overview is the default tab — health data loads on Refresh
  });

  test("shows prompt to refresh before first check", async ({ page }) => {
    // The health hook has enabled:false so data won't load automatically
    await expect(page.getByRole("button", { name: /Refresh/ })).toBeVisible();
  });

  test("Refresh button triggers health check", async ({ page }) => {
    await page.getByRole("button", { name: /Refresh/ }).click();
    // After clicking, should show container data
    await expect(page.getByText("infrakt-web-api")).toBeVisible();
  });

  test("displays container table with health info", async ({ page }) => {
    await page.getByRole("button", { name: /Refresh/ }).click();
    // Container table headers
    await expect(page.getByText("Container", { exact: true })).toBeVisible();
    // Container data
    await expect(page.getByText("infrakt-web-api")).toBeVisible();
    await expect(page.getByText("Up 2 hours")).toBeVisible();
    await expect(page.getByText("nginx:latest")).toBeVisible();
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

    await page.getByRole("button", { name: /Refresh/ }).click();
    await expect(page.getByText(/No containers found/)).toBeVisible();
  });
});

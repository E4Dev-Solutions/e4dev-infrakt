import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_DASHBOARD } from "./fixtures";

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/");
  });

  test("displays stat cards with correct counts", async ({ page }) => {
    // Use exact text match to avoid strict mode violations from sublabels
    await expect(page.locator("text=Total Servers").locator("..").getByText(String(MOCK_DASHBOARD.total_servers), { exact: true })).toBeVisible();
    await expect(page.locator("text=Databases").locator("..").getByText(String(MOCK_DASHBOARD.total_databases), { exact: true })).toBeVisible();
  });

  test("displays recent deployments table", async ({ page }) => {
    await expect(page.getByText("Recent Deployments")).toBeVisible();
    await expect(page.getByRole("cell", { name: "web-api" }).first()).toBeVisible();
  });

  test("sidebar navigation links work", async ({ page }) => {
    // Navigate to Servers
    await page.getByRole("link", { name: "Servers" }).click();
    await expect(page.getByRole("heading", { name: "Servers" })).toBeVisible();

    // Navigate to Apps
    await page.getByRole("link", { name: "Apps" }).click();
    await expect(page.getByRole("heading", { name: "Apps" })).toBeVisible();

    // Navigate to Databases
    await page.getByRole("link", { name: "Databases" }).click();
    await expect(page.getByRole("heading", { name: "Databases" })).toBeVisible();

    // Navigate to Proxy
    await page.getByRole("link", { name: "Proxy" }).click();
    await expect(page.getByRole("heading", { name: "Proxy Domains" })).toBeVisible();

    // Navigate back to Dashboard
    await page.getByRole("link", { name: "Dashboard" }).click();
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  test("shows deployment status badges", async ({ page }) => {
    // The deployments table should show status badges
    const table = page.getByRole("table");
    await expect(table).toBeVisible();
    await expect(table.getByText("success").first()).toBeVisible();
    await expect(table.getByText("failed")).toBeVisible();
  });
});

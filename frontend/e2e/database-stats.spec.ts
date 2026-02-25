import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_DATABASES, MOCK_DATABASE_STATS } from "./fixtures";

test.describe("Database Detail — Live Stats", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/databases/${MOCK_DATABASES[0].name}`);
  });

  // ─── Stats section rendering ──────────────────────────────────────────────────

  test("overview tab shows Live Stats heading", async ({ page }) => {
    await expect(page.getByText("Live Stats")).toBeVisible();
  });

  test("shows Fetch Stats button", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: "Fetch Stats" }),
    ).toBeVisible();
  });

  test("shows placeholder text before fetching", async ({ page }) => {
    await expect(
      page.getByText(/Click.*Fetch Stats.*to query live database metrics/),
    ).toBeVisible();
  });

  // ─── Stats display after fetch ────────────────────────────────────────────────

  test("clicking Fetch Stats shows database version", async ({ page }) => {
    await page.getByRole("button", { name: "Fetch Stats" }).click();
    await expect(page.getByText(MOCK_DATABASE_STATS.version)).toBeVisible();
  });

  test("clicking Fetch Stats shows disk size", async ({ page }) => {
    await page.getByRole("button", { name: "Fetch Stats" }).click();
    await expect(page.getByText(MOCK_DATABASE_STATS.disk_size)).toBeVisible();
  });

  test("clicking Fetch Stats shows active connections", async ({ page }) => {
    await page.getByRole("button", { name: "Fetch Stats" }).click();
    await expect(
      page.getByText(String(MOCK_DATABASE_STATS.active_connections), { exact: true }),
    ).toBeVisible();
  });

  test("clicking Fetch Stats shows uptime", async ({ page }) => {
    await page.getByRole("button", { name: "Fetch Stats" }).click();
    // Uptime contains the full string
    await expect(page.getByText(/3 days/)).toBeVisible();
  });

  test("stats cards have proper labels", async ({ page }) => {
    await page.getByRole("button", { name: "Fetch Stats" }).click();
    await expect(page.getByText("Disk Size")).toBeVisible();
    await expect(page.getByText("Active Connections")).toBeVisible();
    await expect(page.getByText("Version")).toBeVisible();
    await expect(page.getByText("Uptime")).toBeVisible();
  });

  // ─── Connection string ────────────────────────────────────────────────────────

  test("shows connection string reference", async ({ page }) => {
    await expect(page.getByText("Connection String")).toBeVisible();
    await expect(page.getByText(/postgresql:\/\//)).toBeVisible();
  });

  // ─── Stats with partial data ──────────────────────────────────────────────────

  test("handles partial stats gracefully", async ({ page }) => {
    await page.route(/\/api\/databases\/[^/]+\/stats/, (route) => {
      return route.fulfill({
        json: {
          disk_size: null,
          active_connections: null,
          version: "16.2",
          uptime: null,
        },
      });
    });
    await page.goto(`/databases/${MOCK_DATABASES[0].name}`);
    await page.getByRole("button", { name: "Fetch Stats" }).click();
    // Version should show
    await expect(page.getByText("16.2")).toBeVisible();
    // Null stats should not show their cards
    await expect(page.getByText("Disk Size")).not.toBeVisible();
    await expect(page.getByText("Active Connections")).not.toBeVisible();
  });
});

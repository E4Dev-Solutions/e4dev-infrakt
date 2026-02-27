import { test, expect } from "@playwright/test";
import {
  login,
  mockApi,
  MOCK_DASHBOARD,
  MOCK_DEPLOYMENTS,
} from "./fixtures";

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/");
  });

  // ─── Page heading ─────────────────────────────────────────────────────────────

  test("displays page heading", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  test("displays subtitle text", async ({ page }) => {
    await expect(
      page.getByText("Platform overview and recent activity"),
    ).toBeVisible();
  });

  // ─── Stat cards ───────────────────────────────────────────────────────────────

  test("displays stat cards with correct counts", async ({ page }) => {
    // Stat cards are in <main>, scope to avoid sidebar nav matches
    const main = page.locator("main");
    // Servers card: label "SERVERS" followed by value
    await expect(
      main.locator("text=Servers").locator("..").getByText(String(MOCK_DASHBOARD.total_servers), { exact: true }),
    ).toBeVisible();
    // Databases card
    await expect(
      main.locator("text=Databases").locator("..").getByText(String(MOCK_DASHBOARD.total_databases), { exact: true }),
    ).toBeVisible();
  });

  test("Active stat card shows correct count", async ({ page }) => {
    // The "Active" stat card is a link containing the label "Active" and the count
    await expect(
      page.getByRole("link", { name: /Active.*of.*total/ }),
    ).toContainText(String(MOCK_DASHBOARD.active_servers));
  });

  test("Apps stat card shows correct count", async ({ page }) => {
    const main = page.locator("main");
    await expect(
      main.locator("text=Apps").first().locator("..").getByText(String(MOCK_DASHBOARD.running_apps), { exact: true }),
    ).toBeVisible();
  });

  test("stat cards show sublabels", async ({ page }) => {
    // "Servers" sublabel: "<active_servers> active"
    await expect(
      page.getByText(`${MOCK_DASHBOARD.active_servers} active`),
    ).toBeVisible();

    // "Active" sublabel: "of <total_servers> total"
    await expect(
      page.getByText(`of ${MOCK_DASHBOARD.total_servers} total`),
    ).toBeVisible();

    // "Apps" sublabel: "<running_apps> of <total_apps> running"
    await expect(
      page.getByText(`${MOCK_DASHBOARD.running_apps} of ${MOCK_DASHBOARD.total_apps} running`),
    ).toBeVisible();
  });

  // ─── Recent Deployments table ─────────────────────────────────────────────────

  test("displays recent deployments table", async ({ page }) => {
    await expect(page.getByText("Recent Deployments")).toBeVisible();
    await expect(page.getByRole("cell", { name: "web-api" }).first()).toBeVisible();
  });

  test("deployments table shows all three deployments", async ({ page }) => {
    // All three rows share the same app_name "web-api"
    const appCells = page.getByRole("cell", { name: "web-api" });
    await expect(appCells).toHaveCount(MOCK_DEPLOYMENTS.length);
  });

  test("deployments table shows truncated commit hashes", async ({ page }) => {
    // commit_hash "abc12345def67890" → first 7 chars "abc1234"
    await expect(page.getByText("abc1234")).toBeVisible();
    // commit_hash "def67890abc12345" → first 7 chars "def6789"
    await expect(page.getByText("def6789")).toBeVisible();
    // commit_hash "111222333444" → first 7 chars "1112223"
    await expect(page.getByText("1112223")).toBeVisible();
  });

  test("shows deployment status badges", async ({ page }) => {
    const table = page.getByRole("table");
    await expect(table).toBeVisible();
    await expect(table.getByText("success").first()).toBeVisible();
    await expect(table.getByText("failed")).toBeVisible();
  });

  test("deployment rows show formatted dates", async ({ page }) => {
    // MOCK_DEPLOYMENTS started_at values:
    //   "2025-02-10T10:00:00" → "Feb 10" (en-US short month + day)
    //   "2025-02-09T15:00:00" → "Feb 9"
    //   "2025-02-08T08:00:00" → "Feb 8"
    await expect(page.getByText(/Feb 10/)).toBeVisible();
    await expect(page.getByText(/Feb 9/)).toBeVisible();
    await expect(page.getByText(/Feb 8/)).toBeVisible();
  });

  // ─── Sidebar navigation ───────────────────────────────────────────────────────

  test("sidebar navigation links work", async ({ page }) => {
    // Use { exact: true } to avoid matching stat card links
    const nav = page.locator("nav");
    await nav.getByRole("link", { name: "Servers", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Servers" })).toBeVisible();

    await nav.getByRole("link", { name: "Apps", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Apps" })).toBeVisible();

    await nav.getByRole("link", { name: "Databases", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Databases" })).toBeVisible();

    await nav.getByRole("link", { name: "Proxy", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Proxy Domains" })).toBeVisible();

    await nav.getByRole("link", { name: "Dashboard", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  // ─── Empty state ──────────────────────────────────────────────────────────────

  test("shows empty state when no deployments", async ({ page }) => {
    // Override the dashboard route with an empty recent_deployments list.
    // Playwright uses the most recently registered route first, so this
    // override takes precedence over the one registered by mockApi().
    await page.route("**/api/dashboard", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({
          json: { ...MOCK_DASHBOARD, recent_deployments: [] },
        });
      }
      return route.continue();
    });

    await page.goto("/");

    await expect(page.getByText("No deployments yet")).toBeVisible();
    await expect(
      page.getByText("Deploy an app to see activity here"),
    ).toBeVisible();
  });

  // ─── Error state ──────────────────────────────────────────────────────────────

  test("shows error state when API fails", async ({ page }) => {
    // Override the dashboard route to return a 500 error.
    await page.route("**/api/dashboard", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({
          status: 500,
          json: { detail: "Internal Server Error" },
        });
      }
      return route.continue();
    });

    await page.goto("/");

    await expect(page.getByText("Failed to load dashboard")).toBeVisible();
  });
});

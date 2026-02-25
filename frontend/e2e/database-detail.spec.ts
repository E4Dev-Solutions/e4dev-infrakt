import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_DATABASES, MOCK_BACKUP_FILES } from "./fixtures";

test.describe("Database Detail", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/databases/${MOCK_DATABASES[0].name}`);
  });

  // ─── Header ─────────────────────────────────────────────────────────────────

  test("displays database name in heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: MOCK_DATABASES[0].name }),
    ).toBeVisible();
  });

  test("shows back link to databases list", async ({ page }) => {
    await expect(page.getByRole("link", { name: /Back to Databases/i })).toBeVisible();
  });

  test("shows type badge", async ({ page }) => {
    await expect(page.getByText("PostgreSQL").first()).toBeVisible();
  });

  test("shows status badge", async ({ page }) => {
    await expect(page.getByLabel(/Status: Running/i).first()).toBeVisible();
  });

  // ─── Overview tab ───────────────────────────────────────────────────────────

  test("overview tab shows database info", async ({ page }) => {
    await expect(page.getByText(String(MOCK_DATABASES[0].port), { exact: true })).toBeVisible();
    await expect(page.getByText(MOCK_DATABASES[0].server_name).first()).toBeVisible();
  });

  // ─── Backups tab ────────────────────────────────────────────────────────────

  test("clicking Backups tab shows backup list", async ({ page }) => {
    await page.getByRole("tab", { name: /backups/i }).click();
    await expect(
      page.getByText(MOCK_BACKUP_FILES[0].filename),
    ).toBeVisible();
    await expect(
      page.getByText(MOCK_BACKUP_FILES[1].filename),
    ).toBeVisible();
  });

  test("backup list shows file sizes", async ({ page }) => {
    await page.getByRole("tab", { name: /backups/i }).click();
    await expect(page.getByText(MOCK_BACKUP_FILES[0].size)).toBeVisible();
  });

  test("backup list has restore buttons", async ({ page }) => {
    await page.getByRole("tab", { name: /backups/i }).click();
    const restoreButtons = page.getByRole("button", { name: /restore/i });
    await expect(restoreButtons.first()).toBeVisible();
  });

  test("clicking restore on a backup opens modal with pre-filled filename", async ({ page }) => {
    await page.getByRole("tab", { name: /backups/i }).click();
    await page.getByRole("button", { name: /restore/i }).first().click();
    await expect(
      page.getByRole("heading", { name: /restore/i }),
    ).toBeVisible();
    const input = page.getByLabel(/filename/i);
    await expect(input).toHaveValue(MOCK_BACKUP_FILES[0].filename);
  });

  test("empty backups shows empty state", async ({ page }) => {
    // Override backups to return empty
    await page.route(/\/api\/databases\/[^/]+\/backups/, (route) => {
      return route.fulfill({ json: [] });
    });
    await page.goto(`/databases/${MOCK_DATABASES[0].name}`);
    await page.getByRole("tab", { name: /backups/i }).click();
    await expect(page.getByText(/no backups/i)).toBeVisible();
  });

  // ─── Actions ────────────────────────────────────────────────────────────────

  test("backup button triggers success toast", async ({ page }) => {
    await page.getByLabel(/backup/i).first().click();
    await expect(page.getByText(/backup created/i)).toBeVisible();
  });

  test("schedule button opens schedule modal", async ({ page }) => {
    await page.getByLabel(/schedule/i).click();
    await expect(
      page.getByRole("heading", { name: /schedule backups/i }),
    ).toBeVisible();
  });

  // ─── Navigation ─────────────────────────────────────────────────────────────

  test("database name in list page links to detail", async ({ page }) => {
    await page.goto("/databases");
    await page.getByRole("link", { name: MOCK_DATABASES[0].name }).click();
    await expect(page).toHaveURL(/\/databases\/main-pg/);
    await expect(
      page.getByRole("heading", { name: MOCK_DATABASES[0].name }),
    ).toBeVisible();
  });
});

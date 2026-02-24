import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_DATABASES } from "./fixtures";

test.describe("Databases", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/databases");
  });

  // ─── Rendering ───────────────────────────────────────────────────────────────

  test("displays page heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Databases" }),
    ).toBeVisible();
  });

  test("lists existing database with correct details", async ({ page }) => {
    const db = MOCK_DATABASES[0];
    await expect(page.getByText(db.name)).toBeVisible();
    await expect(page.getByText(db.server_name)).toBeVisible();
    await expect(page.getByText("PostgreSQL")).toBeVisible();
    await expect(page.getByText(String(db.port))).toBeVisible();
  });

  test("shows status badge for running database", async ({ page }) => {
    await expect(page.getByLabel("Status: Running")).toBeVisible();
  });

  test("shows delete button with aria-label", async ({ page }) => {
    await expect(
      page.getByLabel(`Delete ${MOCK_DATABASES[0].name}`),
    ).toBeVisible();
  });

  // ─── Empty state ─────────────────────────────────────────────────────────────

  test("shows empty state when no databases exist", async ({ page }) => {
    await page.route("**/api/databases", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: [] });
      }
      return route.continue();
    });
    await page.goto("/databases");
    await expect(page.getByText("No databases yet")).toBeVisible();
  });

  // ─── Create modal ────────────────────────────────────────────────────────────

  test("Create Database button opens modal", async ({ page }) => {
    await page.getByRole("button", { name: "Create Database" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Create Database" }),
    ).toBeVisible();
  });

  test("modal has all form fields", async ({ page }) => {
    await page.getByRole("button", { name: "Create Database" }).first().click();
    await expect(page.getByLabel(/Server/)).toBeVisible();
    await expect(page.getByLabel(/Database Name/)).toBeVisible();
    await expect(page.getByLabel(/Database Type/)).toBeVisible();
    await expect(page.getByLabel(/Version/)).toBeVisible();
  });

  test("server dropdown lists available servers", async ({ page }) => {
    await page.getByRole("button", { name: "Create Database" }).first().click();
    const select = page.getByLabel(/Server/);
    const options = select.locator("option");
    // "Select a server" + 2 mock servers
    await expect(options).toHaveCount(3);
  });

  test("Cancel button closes modal", async ({ page }) => {
    await page.getByRole("button", { name: "Create Database" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Create Database" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(
      page.getByRole("heading", { name: "Create Database" }),
    ).not.toBeVisible();
  });

  test("Escape key closes modal", async ({ page }) => {
    await page.getByRole("button", { name: "Create Database" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Create Database" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("heading", { name: "Create Database" }),
    ).not.toBeVisible();
  });

  test("form submission creates database and shows toast", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "Create Database" }).first().click();
    await page.getByLabel(/Server/).selectOption({ index: 1 });
    await page.getByLabel(/Database Name/).fill("test-db");
    await page.getByLabel(/Database Type/).selectOption("postgres");
    await page.locator("form").getByRole("button", { name: "Create Database" }).click();
    await expect(page.getByText('Database "test-db" created')).toBeVisible();
    // Modal should close
    await expect(
      page.getByRole("heading", { name: "Create Database" }),
    ).not.toBeVisible();
  });

  // ─── Delete flow ─────────────────────────────────────────────────────────────

  test("delete triggers confirmation dialog", async ({ page }) => {
    let dialogMessage = "";
    page.on("dialog", (dialog) => {
      dialogMessage = dialog.message();
      void dialog.accept();
    });
    await page.getByLabel(`Delete ${MOCK_DATABASES[0].name}`).click();
    expect(dialogMessage).toContain(MOCK_DATABASES[0].name);
  });

  test("accepting delete shows success toast", async ({ page }) => {
    page.on("dialog", (dialog) => dialog.accept());
    await page.getByLabel(`Delete ${MOCK_DATABASES[0].name}`).click();
    await expect(
      page.getByText(`Database "${MOCK_DATABASES[0].name}" deleted`),
    ).toBeVisible();
  });

  test("dismissing delete does not remove database", async ({ page }) => {
    page.on("dialog", (dialog) => dialog.dismiss());
    await page.getByLabel(`Delete ${MOCK_DATABASES[0].name}`).click();
    // Database should still be in the table
    await expect(page.getByText(MOCK_DATABASES[0].name)).toBeVisible();
  });
});

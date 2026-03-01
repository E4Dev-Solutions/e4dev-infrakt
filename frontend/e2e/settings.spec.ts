import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_WEBHOOKS } from "./fixtures";

test.describe("Settings — Webhooks", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/settings");
  });

  // ─── Rendering ───────────────────────────────────────────────────────────────

  test("displays page heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Settings" }),
    ).toBeVisible();
  });

  test("shows Notification Webhooks section heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Notification Webhooks" }),
    ).toBeVisible();
  });

  test("lists existing webhooks with URLs", async ({ page }) => {
    await expect(page.getByText("hooks.slack.com")).toBeVisible();
    await expect(page.getByText("discord.com")).toBeVisible();
  });

  test("shows event badges for each webhook", async ({ page }) => {
    await expect(page.getByText("deploy.success").first()).toBeVisible();
    await expect(page.getByText("deploy.failure").first()).toBeVisible();
    await expect(page.getByText("backup.complete").first()).toBeVisible();
  });

  test("shows Add Webhook button", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: "Add Webhook" }).first(),
    ).toBeVisible();
  });

  // ─── Empty state ─────────────────────────────────────────────────────────────

  test("shows empty state when no webhooks exist", async ({ page }) => {
    await page.route("**/api/webhooks", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: [] });
      }
      return route.continue();
    });
    await page.goto("/settings");
    await expect(page.getByText("No webhooks configured")).toBeVisible();
  });

  // ─── Add Webhook modal ────────────────────────────────────────────────────────

  test("Add Webhook button opens modal", async ({ page }) => {
    await page.getByRole("button", { name: "Add Webhook" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Add Webhook" }),
    ).toBeVisible();
  });

  test("modal has URL input, event checkboxes, and secret input", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "Add Webhook" }).first().click();
    const modal = page.locator("[role=dialog]");
    await expect(modal.getByLabel(/Endpoint URL/)).toBeVisible();
    await expect(page.getByText("Deploy Success")).toBeVisible();
    await expect(page.getByText("Deploy Failure")).toBeVisible();
    await expect(page.getByText("Backup Complete")).toBeVisible();
    await expect(page.getByText("Backup Restore")).toBeVisible();
    await expect(modal.getByLabel(/Signing Secret/)).toBeVisible();
  });

  test("Cancel button closes modal", async ({ page }) => {
    await page.getByRole("button", { name: "Add Webhook" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Add Webhook" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(
      page.getByRole("heading", { name: "Add Webhook" }),
    ).not.toBeVisible();
  });

  test("Escape key closes modal", async ({ page }) => {
    await page.getByRole("button", { name: "Add Webhook" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Add Webhook" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("heading", { name: "Add Webhook" }),
    ).not.toBeVisible();
  });

  test("URL validation shows error for http:// URLs", async ({ page }) => {
    await page.getByRole("button", { name: "Add Webhook" }).first().click();
    const modal = page.locator("[role=dialog]");
    await modal.getByLabel(/Endpoint URL/).fill("http://insecure.example.com/hook");
    await expect(page.getByText("URL must start with https://")).toBeVisible();
  });

  test("form submission creates webhook and shows toast", async ({ page }) => {
    await page.getByRole("button", { name: "Add Webhook" }).first().click();
    const modal = page.locator("[role=dialog]");
    await modal.getByLabel(/Endpoint URL/).fill("https://hooks.example.com/new");
    await page.getByText("Deploy Success").click();
    await page
      .locator("form")
      .getByRole("button", { name: "Add Webhook" })
      .click();
    await expect(page.getByText("Webhook added")).toBeVisible();
    // Modal should close
    await expect(
      page.getByRole("heading", { name: "Add Webhook" }),
    ).not.toBeVisible();
  });

  // ─── Test delivery ────────────────────────────────────────────────────────────

  test("test delivery button is visible for each webhook", async ({ page }) => {
    const hook = MOCK_WEBHOOKS[0];
    await expect(
      page.getByLabel(`Send test delivery to ${hook.url}`),
    ).toBeVisible();
  });

  test("clicking test delivery shows success toast", async ({ page }) => {
    const hook = MOCK_WEBHOOKS[0];
    await page.getByLabel(`Send test delivery to ${hook.url}`).click();
    await expect(page.getByText("Test ping sent")).toBeVisible();
  });

  // ─── Delete flow ──────────────────────────────────────────────────────────────

  test("delete button is visible for each webhook", async ({ page }) => {
    const hook = MOCK_WEBHOOKS[0];
    await expect(
      page.getByLabel(`Remove webhook for ${hook.url}`),
    ).toBeVisible();
  });

  test("delete triggers confirmation dialog", async ({ page }) => {
    let dialogMessage = "";
    page.on("dialog", (dialog) => {
      dialogMessage = dialog.message();
      void dialog.accept();
    });
    const hook = MOCK_WEBHOOKS[0];
    await page.getByLabel(`Remove webhook for ${hook.url}`).click();
    expect(dialogMessage).toContain(hook.url);
  });

  test("accepting delete shows success toast", async ({ page }) => {
    page.on("dialog", (dialog) => dialog.accept());
    const hook = MOCK_WEBHOOKS[0];
    await page.getByLabel(`Remove webhook for ${hook.url}`).click();
    await expect(page.getByText("Webhook removed")).toBeVisible();
  });

  test("dismissing delete does not remove webhook", async ({ page }) => {
    page.on("dialog", (dialog) => dialog.dismiss());
    const hook = MOCK_WEBHOOKS[0];
    await page.getByLabel(`Remove webhook for ${hook.url}`).click();
    // Webhook URL should still be visible
    await expect(page.getByText("hooks.slack.com")).toBeVisible();
  });

  // ─── Navigation ───────────────────────────────────────────────────────────────

  test("Settings link is visible in navigation", async ({ page }) => {
    await expect(
      page.getByRole("link", { name: /Settings/ }),
    ).toBeVisible();
  });
});

import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_APPS } from "./fixtures";

test.describe("Logs Tab", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/apps/${MOCK_APPS[0].name}`);
    // Logs tab is the default active tab
  });

  test("displays static logs by default", async ({ page }) => {
    await expect(page.getByText("Container started")).toBeVisible();
    await expect(page.getByText("Listening on :3000")).toBeVisible();
  });

  test("shows Live toggle button", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /live/i }),
    ).toBeVisible();
  });

  test("shows Lines selector and Refresh in static mode", async ({ page }) => {
    await expect(page.getByLabel("Lines:")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /refresh/i }),
    ).toBeVisible();
  });

  test("toggling live mode hides Refresh and Lines selector", async ({
    page,
  }) => {
    await page.getByRole("button", { name: /live/i }).click();
    // Lines selector and Refresh should be hidden in live mode
    await expect(page.getByLabel("Lines:")).not.toBeVisible();
    await expect(
      page.getByRole("button", { name: /refresh/i }),
    ).not.toBeVisible();
  });

  test("toggling back to static restores Refresh button", async ({
    page,
  }) => {
    // Enter live mode
    await page.getByRole("button", { name: /start live/i }).click();
    // Exit live mode
    await page.getByRole("button", { name: /stop live/i }).click();
    // Refresh should be back
    await expect(
      page.getByRole("button", { name: /refresh/i }),
    ).toBeVisible();
  });
});

import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_APPS, MOCK_ENV_VARS } from "./fixtures";

test.describe("Environment Variables", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/apps/${MOCK_APPS[0].name}`);
    // Switch to the Environment tab
    await page.getByRole("tab", { name: "Environment" }).click();
  });

  test("displays env vars in a table", async ({ page }) => {
    for (const v of MOCK_ENV_VARS) {
      await expect(page.getByText(v.key)).toBeVisible();
    }
    // Values should be visible (show_values=true by default in the hook)
    await expect(page.getByText("production")).toBeVisible();
  });

  test("add form has key, value inputs and Add button", async ({ page }) => {
    await expect(page.getByRole("textbox", { name: "Key" })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Value" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Add", exact: true })).toBeVisible();
  });

  test("Add button is disabled when key is empty", async ({ page }) => {
    await expect(page.getByRole("button", { name: "Add", exact: true })).toBeDisabled();
  });

  test("add new env var shows success toast", async ({ page }) => {
    await page.getByRole("textbox", { name: "Key" }).fill("NEW_VAR");
    await page.getByRole("textbox", { name: "Value" }).fill("some-value");
    await page.getByRole("button", { name: "Add", exact: true }).click();

    await expect(page.getByText(/NEW_VAR.*saved/)).toBeVisible();
  });

  test("add form clears after successful submission", async ({ page }) => {
    await page.getByRole("textbox", { name: "Key" }).fill("TEMP_KEY");
    await page.getByRole("textbox", { name: "Value" }).fill("temp-value");
    await page.getByRole("button", { name: "Add", exact: true }).click();

    // Wait for toast to confirm success
    await expect(page.getByText(/TEMP_KEY.*saved/)).toBeVisible();
    // Inputs should be cleared
    await expect(page.getByRole("textbox", { name: "Key" })).toHaveValue("");
    await expect(page.getByRole("textbox", { name: "Value" })).toHaveValue("");
  });

  test("delete env var shows success toast", async ({ page }) => {
    await page.getByLabel(`Delete ${MOCK_ENV_VARS[0].key}`).click();
    await expect(page.getByText(/"DATABASE_URL" deleted/)).toBeVisible();
  });

  test("shows empty state when no env vars", async ({ page }) => {
    // Unroute existing env handler, then register empty override
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await page.route(/\/api\/apps\/[^/]+\/env(\?.*)?$/, (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: [] });
      }
      return route.continue();
    });
    // Mock the apps route (needed for app detail to render)
    await page.route("**/api/apps", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: MOCK_APPS });
      }
      return route.continue();
    });
    // Mock logs route (lazy-loaded tab)
    await page.route("**/api/apps/*/logs", (route) => {
      return route.fulfill({ json: { app_name: "web-api", logs: "" } });
    });

    await page.goto(`/apps/${MOCK_APPS[0].name}`);
    await page.getByRole("tab", { name: "Environment" }).click();

    await expect(page.getByText("No environment variables set.")).toBeVisible();
  });

  test("handles add error gracefully", async ({ page }) => {
    // Override env POST to return 500
    await page.route(/\/api\/apps\/[^/]+\/env$/, (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          status: 500,
          json: { detail: "Encryption failed" },
        });
      }
      return route.continue();
    });

    await page.getByRole("textbox", { name: "Key" }).fill("BAD_VAR");
    await page.getByRole("textbox", { name: "Value" }).fill("value");
    await page.getByRole("button", { name: "Add", exact: true }).click();

    await expect(page.getByText(/failed|error/i)).toBeVisible();
  });
});

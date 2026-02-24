import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_APPS } from "./fixtures";

test.describe("Deployments Tab", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/apps/${MOCK_APPS[0].name}`);
    await page.getByRole("tab", { name: "Deployments" }).click();
  });

  test("displays deployments table with Ref column", async ({ page }) => {
    await expect(page.getByText("Ref")).toBeVisible();
    // First deployment shows truncated commit hash
    await expect(page.getByText("abc12345")).toBeVisible();
  });

  test("shows deployment ID as number", async ({ page }) => {
    await expect(page.getByText("#3")).toBeVisible();
  });

  test("expand log viewer on chevron click", async ({ page }) => {
    // Click the expand button on first deployment
    await page.getByLabel("View log").first().click();
    // Should show log content
    await expect(page.getByText("Starting deployment")).toBeVisible();
    await expect(page.getByText("Deployment complete")).toBeVisible();
  });

  test("collapse log viewer on second click", async ({ page }) => {
    await page.getByLabel("View log").first().click();
    await expect(page.getByText("Starting deployment")).toBeVisible();
    // Click again to collapse
    await page.getByLabel("Collapse log").first().click();
    await expect(page.getByText("Starting deployment")).not.toBeVisible();
  });

  test("rollback button appears on non-latest successful deployments", async ({ page }) => {
    // The latest successful deployment (idx=0) should NOT have rollback
    // The failed deployment (idx=1) should NOT have rollback
    // The older successful deployment (idx=2) SHOULD have rollback
    const rollbackButtons = page.getByRole("button", { name: "Rollback" });
    await expect(rollbackButtons).toHaveCount(1);
  });

  test("rollback button triggers API call and shows toast", async ({ page }) => {
    page.on("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Rollback" }).click();
    await expect(page.getByText("Rollback started")).toBeVisible();
  });
});

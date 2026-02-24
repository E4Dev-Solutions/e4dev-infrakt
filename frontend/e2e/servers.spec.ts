import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_SERVERS } from "./fixtures";

test.describe("Servers", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/servers");
  });

  test("lists servers from API", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Servers" })).toBeVisible();
    await expect(page.getByText(MOCK_SERVERS[0].name)).toBeVisible();
    await expect(page.getByText(MOCK_SERVERS[1].name)).toBeVisible();
  });

  test("shows server connection details", async ({ page }) => {
    // First server: root@203.0.113.10:22
    await expect(page.getByText("root@203.0.113.10:22")).toBeVisible();
    // Second server: deploy@198.51.100.5:2222
    await expect(page.getByText("deploy@198.51.100.5:2222")).toBeVisible();
  });

  test("Add Server modal opens and closes", async ({ page }) => {
    await page.getByRole("button", { name: "Add Server" }).click();
    await expect(page.getByRole("heading", { name: "Add Server" })).toBeVisible();
    await expect(page.getByLabel(/Name/)).toBeVisible();
    await expect(page.getByLabel(/Host/)).toBeVisible();

    // Close via Cancel
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("heading", { name: "Add Server" })).not.toBeVisible();
  });

  test("Add Server form submits successfully", async ({ page }) => {
    await page.getByRole("button", { name: "Add Server" }).click();

    await page.getByLabel(/Name/).fill("new-server");
    await page.getByLabel(/Host/).fill("10.0.0.1");
    await page.getByLabel(/SSH User/).fill("admin");

    // Submit
    await page.locator("form").getByRole("button", { name: "Add Server" }).click();

    // Modal should close and success toast appear
    await expect(page.getByText(/added successfully/)).toBeVisible();
  });

  test("server name links to detail page", async ({ page }) => {
    await page.getByRole("link", { name: MOCK_SERVERS[0].name }).click();
    await expect(page).toHaveURL(/\/servers\/prod-1/);
  });

  test("delete server shows confirmation", async ({ page }) => {
    // Mock window.confirm
    page.on("dialog", (dialog) => dialog.accept());

    await page.getByLabel(`Delete ${MOCK_SERVERS[0].name}`).click();
    await expect(page.getByText(/deleted/)).toBeVisible();
  });
});

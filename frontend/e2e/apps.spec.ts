import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_APPS } from "./fixtures";

test.describe("Apps", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/apps");
  });

  test("lists apps with status badges", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Apps" })).toBeVisible();
    await expect(page.getByText(MOCK_APPS[0].name)).toBeVisible();
    await expect(page.getByText(MOCK_APPS[1].name)).toBeVisible();
    // Status badges
    await expect(page.getByText("running")).toBeVisible();
    await expect(page.getByText("stopped")).toBeVisible();
  });

  test("shows app server and domain info", async ({ page }) => {
    await expect(page.getByText("prod-1").first()).toBeVisible();
    await expect(page.getByText("api.example.com")).toBeVisible();
  });

  test("Create App modal opens with server selector", async ({ page }) => {
    await page.getByRole("button", { name: "Create App" }).click();
    await expect(page.getByRole("heading", { name: "Create App" })).toBeVisible();
    await expect(page.getByLabel(/App Name/)).toBeVisible();
    await expect(page.getByLabel(/Server/)).toBeVisible();
    await expect(page.getByLabel(/Domain/)).toBeVisible();

    // Server selector should have mock servers
    const serverSelect = page.getByLabel(/Server/);
    await expect(serverSelect.locator("option")).toHaveCount(3); // empty + 2 servers
  });

  test("Create App form submits successfully", async ({ page }) => {
    await page.getByRole("button", { name: "Create App" }).click();

    await page.getByLabel(/App Name/).fill("new-app");
    await page.getByLabel(/Server/).selectOption("prod-1");
    // Switch to Image source type (default is Template)
    await page.getByRole("button", { name: "Image" }).click();
    await page.getByLabel(/Image/).fill("nginx:latest");

    await page.locator("form").getByRole("button", { name: "Create App" }).click();

    await expect(page.getByText(/created/)).toBeVisible();
  });

  test("app name links to detail page", async ({ page }) => {
    await page.getByRole("link", { name: MOCK_APPS[0].name }).click();
    await expect(page).toHaveURL(/\/apps\/web-api/);
  });

  test("deploy action calls API and shows toast", async ({ page }) => {
    await page.getByLabel(`Deploy ${MOCK_APPS[0].name}`).click();
    await expect(page.getByText(/Deployment/i)).toBeVisible();
  });

  test("stop action calls API and shows toast", async ({ page }) => {
    await page.getByLabel(`Stop ${MOCK_APPS[0].name}`).click();
    await expect(page.getByText('"web-api" stopped.')).toBeVisible();
  });

  test("destroy action shows confirmation dialog", async ({ page }) => {
    page.on("dialog", (dialog) => dialog.accept());
    await page.getByLabel(`Destroy ${MOCK_APPS[0].name}`).click();
    await expect(page.getByText(/destroyed/i)).toBeVisible();
  });
});

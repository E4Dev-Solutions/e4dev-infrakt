import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_SERVERS } from "./fixtures";

test.describe("Server Detail — Provisioning", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/servers/${MOCK_SERVERS[0].name}`);
  });

  test("Provision button is visible", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: "Provision" }),
    ).toBeVisible();
  });

  test("clicking Provision shows progress panel", async ({ page }) => {
    await page.getByRole("button", { name: "Provision" }).click();
    await expect(
      page.getByLabel("Provisioning progress"),
    ).toBeVisible();
  });

  test("progress panel displays step messages", async ({ page }) => {
    await page.getByRole("button", { name: "Provision" }).click();
    await expect(page.getByText("[1/9] Installing Docker")).toBeVisible();
    await expect(page.getByText("[2/9] Configuring firewall")).toBeVisible();
    await expect(page.getByText("[3/9] Installing Caddy")).toBeVisible();
  });

  test("panel shows completion heading after provisioning finishes", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "Provision" }).click();
    await expect(
      page.getByText("Provisioning Complete"),
    ).toBeVisible();
  });

  test("success toast appears after provisioning completes", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "Provision" }).click();
    await expect(
      page.getByText("Server provisioned successfully"),
    ).toBeVisible();
  });
});

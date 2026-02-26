import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_PROXY_DOMAINS } from "./fixtures";

test.describe("Proxy Domains", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/proxy");
  });

  test("shows server selector and empty state", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Proxy Domains" })).toBeVisible();
    await expect(page.getByLabel("Server")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Select a server" })).toBeVisible();
  });

  test("lists domains after selecting a server", async ({ page }) => {
    await page.getByLabel("Server").selectOption("prod-1");

    await expect(page.getByText(MOCK_PROXY_DOMAINS[0].domain)).toBeVisible();
    await expect(page.getByText(MOCK_PROXY_DOMAINS[1].domain)).toBeVisible();
    await expect(page.getByText(`:${MOCK_PROXY_DOMAINS[0].port}`)).toBeVisible();
  });

  test("Add Route and Reload buttons appear after server selection", async ({ page }) => {
    // Buttons should not be visible before selecting server
    await expect(page.getByRole("button", { name: "Add Route" })).not.toBeVisible();
    await expect(page.getByRole("button", { name: "Reload Traefik" })).not.toBeVisible();

    await page.getByLabel("Server").selectOption("prod-1");

    await expect(page.getByRole("button", { name: "Add Route" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Reload Traefik" })).toBeVisible();
  });

  test("Add Route modal opens and submits", async ({ page }) => {
    await page.getByLabel("Server").selectOption("prod-1");
    await page.getByRole("button", { name: "Add Route" }).click();

    await expect(page.getByRole("heading", { name: "Add Proxy Route" })).toBeVisible();

    await page.getByLabel(/Domain/).fill("new.example.com");
    await page.getByLabel(/Target Port/).fill("4000");

    await page.locator("form").getByRole("button", { name: "Add Route" }).click();
    await expect(page.getByText(/Route added/)).toBeVisible();
  });

  test("remove route shows confirmation", async ({ page }) => {
    await page.getByLabel("Server").selectOption("prod-1");

    page.on("dialog", (dialog) => dialog.accept());
    await page.getByLabel(`Remove ${MOCK_PROXY_DOMAINS[0].domain}`).click();
    await expect(page.getByText(/removed/)).toBeVisible();
  });

  test("Reload Traefik calls API and shows toast", async ({ page }) => {
    await page.getByLabel("Server").selectOption("prod-1");
    await page.getByRole("button", { name: "Reload Traefik" }).click();
    await expect(page.getByText(/reloaded/i)).toBeVisible();
  });

  test("handles API error gracefully", async ({ page }) => {
    // Override the domains route to return 502
    await page.route("**/api/proxy/*/domains", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ status: 502, json: { detail: "Server unreachable" } });
      }
      return route.continue();
    });

    await page.getByLabel("Server").selectOption("prod-1");
    // Should show error state (the component shows an error or empty state)
    await expect(page.getByText(/No proxy domains|failed|error/i)).toBeVisible();
  });
});

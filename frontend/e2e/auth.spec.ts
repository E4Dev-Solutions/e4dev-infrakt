import { test, expect } from "@playwright/test";
import { login, mockApi } from "./fixtures";

test.describe("Authentication", () => {
  test("shows login page when no API key is set", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "infrakt" })).toBeVisible();
    await expect(page.getByLabel("API Key")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  test("successful login redirects to dashboard", async ({ page }) => {
    // Mock the dashboard endpoint to accept any key
    await page.route("**/api/dashboard", (route) => {
      return route.fulfill({ json: { total_servers: 0, active_servers: 0, total_apps: 0, running_apps: 0, total_databases: 0, recent_deployments: [] } });
    });

    await page.goto("/");
    await page.getByLabel("API Key").fill("valid-test-key");
    await page.getByRole("button", { name: "Sign in" }).click();

    // Should redirect to dashboard
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  test("shows error on invalid API key", async ({ page }) => {
    await page.route("**/api/dashboard", (route) => {
      return route.fulfill({ status: 403, json: { detail: "Invalid API key" } });
    });

    await page.goto("/");
    await page.getByLabel("API Key").fill("bad-key");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByText("Invalid API key")).toBeVisible();
  });

  test("shows error when API is unreachable", async ({ page }) => {
    await page.route("**/api/dashboard", (route) => {
      return route.abort("connectionrefused");
    });

    await page.goto("/");
    await page.getByLabel("API Key").fill("some-key");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByText("Cannot reach the API server")).toBeVisible();
  });

  test("logout clears key and returns to login page", async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/");

    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

    // Click the logout button in the sidebar footer
    await page.getByTitle("Sign out").click();

    // Should return to login page
    await expect(page.getByLabel("API Key")).toBeVisible();
  });

  test("sign in button is disabled when input is empty", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Sign in" })).toBeDisabled();
  });
});

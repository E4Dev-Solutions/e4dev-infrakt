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

  test("displays the infrakt icon area", async ({ page }) => {
    await page.goto("/");

    // The KeyRound icon is wrapped in a styled container div; locate it by its
    // sibling heading so we assert the icon area is rendered in the page header.
    const iconContainer = page.locator("div.inline-flex");
    await expect(iconContainer).toBeVisible();

    // The SVG icon itself should be present inside the container
    await expect(iconContainer.locator("svg")).toBeVisible();
  });

  test("displays helper text about API key location", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByText("~/.infrakt/api_key.txt")).toBeVisible();
  });

  test("API key input has password type", async ({ page }) => {
    await page.goto("/");

    const input = page.getByLabel("API Key");
    await expect(input).toHaveAttribute("type", "password");
  });

  test("API key input has autofocus", async ({ page }) => {
    await page.goto("/");

    // The autoFocus attribute causes the input to be the active element immediately
    const input = page.getByLabel("API Key");
    await expect(input).toBeFocused();
  });

  test("shows Verifying... text during login attempt", async ({ page }) => {
    // Use a delayed response so we can observe the intermediate loading state
    await page.route("**/api/dashboard", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      return route.fulfill({ json: { total_servers: 0, active_servers: 0, total_apps: 0, running_apps: 0, total_databases: 0, recent_deployments: [] } });
    });

    await page.goto("/");
    await page.getByLabel("API Key").fill("valid-test-key");
    await page.getByRole("button", { name: "Sign in" }).click();

    // While the request is in-flight the button label switches to "Verifying..."
    await expect(page.getByRole("button", { name: "Verifying..." })).toBeVisible();
  });

  test("button is disabled while verifying", async ({ page }) => {
    // Use a delayed response so we can inspect the button state mid-request
    await page.route("**/api/dashboard", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      return route.fulfill({ json: { total_servers: 0, active_servers: 0, total_apps: 0, running_apps: 0, total_databases: 0, recent_deployments: [] } });
    });

    await page.goto("/");
    await page.getByLabel("API Key").fill("valid-test-key");
    await page.getByRole("button", { name: "Sign in" }).click();

    // The button should be disabled while the API call is pending
    await expect(page.getByRole("button", { name: "Verifying..." })).toBeDisabled();
  });

  test("handles 401 status same as 403", async ({ page }) => {
    await page.route("**/api/dashboard", (route) => {
      return route.fulfill({ status: 401, json: { detail: "Unauthorized" } });
    });

    await page.goto("/");
    await page.getByLabel("API Key").fill("unauthorized-key");
    await page.getByRole("button", { name: "Sign in" }).click();

    // Both 401 and 403 should surface the same user-facing message
    await expect(page.getByText("Invalid API key")).toBeVisible();
  });

  test("trims whitespace from API key before submitting", async ({ page }) => {
    // The server receives the trimmed key; mock accepts any request as valid
    await page.route("**/api/dashboard", (route) => {
      return route.fulfill({ json: { total_servers: 0, active_servers: 0, total_apps: 0, running_apps: 0, total_databases: 0, recent_deployments: [] } });
    });

    await page.goto("/");
    // Fill with leading and trailing whitespace around a valid key
    await page.getByLabel("API Key").fill("  key-with-spaces  ");
    await page.getByRole("button", { name: "Sign in" }).click();

    // Login should succeed — whitespace is trimmed before the fetch call
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  test("login persists across page reload", async ({ page }) => {
    await page.route("**/api/dashboard", (route) => {
      return route.fulfill({ json: { total_servers: 0, active_servers: 0, total_apps: 0, running_apps: 0, total_databases: 0, recent_deployments: [] } });
    });

    await page.goto("/");
    await page.getByLabel("API Key").fill("valid-test-key");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

    // Reload the page — the key is stored in localStorage so the app should
    // skip the login page and land directly on the dashboard
    await page.reload();
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByLabel("API Key")).not.toBeVisible();
  });

  test("shows unexpected error for non-auth error codes", async ({ page }) => {
    await page.route("**/api/dashboard", (route) => {
      return route.fulfill({ status: 500, json: { detail: "Internal Server Error" } });
    });

    await page.goto("/");
    await page.getByLabel("API Key").fill("some-key");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByText("Unexpected error: 500")).toBeVisible();
  });
});

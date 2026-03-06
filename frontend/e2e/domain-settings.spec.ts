import { test, expect } from "@playwright/test";
import { login, mockApi } from "./fixtures";

test.describe("Settings — Domain", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/settings");
  });

  test("shows Base Domain section heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Base Domain" }),
    ).toBeVisible();
  });

  test("shows empty domain input when not configured", async ({ page }) => {
    const input = page.getByRole("textbox", { name: "Base Domain" });
    await expect(input).toBeVisible();
    await expect(input).toHaveValue("");
  });

  test("save button is disabled when input is empty", async ({ page }) => {
    const section = page.locator("section", { has: page.getByRole("heading", { name: "Base Domain" }) });
    await expect(
      section.getByRole("button", { name: /Save/ }),
    ).toBeDisabled();
  });

  test("typing a domain enables the save button", async ({ page }) => {
    await page.getByRole("textbox", { name: "Base Domain" }).fill("infrakt.cloud");
    const section = page.locator("section", { has: page.getByRole("heading", { name: "Base Domain" }) });
    await expect(section.getByRole("button", { name: /Save/ })).toBeEnabled();
  });

  test("saving domain shows success toast", async ({ page }) => {
    await page.getByRole("textbox", { name: "Base Domain" }).fill("infrakt.cloud");
    const section = page.locator("section", { has: page.getByRole("heading", { name: "Base Domain" }) });
    await section.getByRole("button", { name: /Save/ }).click();
    await expect(page.getByText(/Base domain set to/)).toBeVisible();
  });

  test("shows active state when domain is configured", async ({ page }) => {
    // Override the default mock to return a configured domain
    await page.route("**/api/settings/domain", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: { base_domain: "infrakt.cloud" } });
      }
      if (route.request().method() === "PUT") {
        return route.fulfill({ json: { message: "Domain settings saved" } });
      }
      return route.continue();
    });
    await page.goto("/settings");
    await expect(page.getByText("Auto-domains active")).toBeVisible();
    await expect(page.getByText("*.infrakt.cloud")).toBeVisible();
  });

  test("shows Update button when domain already configured", async ({ page }) => {
    await page.route("**/api/settings/domain", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: { base_domain: "infrakt.cloud" } });
      }
      if (route.request().method() === "PUT") {
        return route.fulfill({ json: { message: "Domain settings saved" } });
      }
      return route.continue();
    });
    await page.goto("/settings");
    const section = page.locator("section", { has: page.getByRole("heading", { name: "Base Domain" }) });
    await expect(section.getByRole("button", { name: "Update" })).toBeVisible();
  });

  test("Remove button clears the domain", async ({ page }) => {
    let currentDomain: string | null = "infrakt.cloud";
    await page.route("**/api/settings/domain", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: { base_domain: currentDomain } });
      }
      if (route.request().method() === "PUT") {
        const body = route.request().postDataJSON() as { base_domain: string | null };
        currentDomain = body.base_domain;
        return route.fulfill({ json: { message: "Domain settings saved" } });
      }
      return route.continue();
    });
    await page.goto("/settings");
    await page.getByRole("button", { name: "Remove" }).first().click();
    await expect(page.getByText("Base domain cleared")).toBeVisible();
  });

  test("shows DNS hint text", async ({ page }) => {
    await expect(page.getByText(/wildcard DNS A record/)).toBeVisible();
  });
});

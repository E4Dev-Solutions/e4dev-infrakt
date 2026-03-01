import { test, expect } from "@playwright/test";
import { login, mockApi } from "./fixtures";

test.describe("Settings — S3 Backup Storage", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/settings");
  });

  // ─── Rendering (unconfigured) ─────────────────────────────────────────────────

  test("shows S3 Backup Storage section heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "S3 Backup Storage" }),
    ).toBeVisible();
  });

  test("shows form fields for S3 configuration", async ({ page }) => {
    await expect(page.getByLabel("Endpoint URL")).toBeVisible();
    await expect(page.getByLabel("Bucket")).toBeVisible();
    await expect(page.getByLabel("Region")).toBeVisible();
    await expect(page.getByLabel("Prefix")).toBeVisible();
    await expect(page.getByLabel("Access Key")).toBeVisible();
    await expect(page.getByLabel("Secret Key")).toBeVisible();
  });

  test("shows Save button when unconfigured", async ({ page }) => {
    // Find the S3 form's submit button
    const s3Section = page.locator("section", { has: page.getByRole("heading", { name: "S3 Backup Storage" }) });
    await expect(s3Section.getByRole("button", { name: "Save" })).toBeVisible();
  });

  test("Save button is disabled when required fields are empty", async ({ page }) => {
    const s3Section = page.locator("section", { has: page.getByRole("heading", { name: "S3 Backup Storage" }) });
    await expect(s3Section.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  // ─── Saving S3 config ─────────────────────────────────────────────────────────

  test("submitting valid config shows success toast", async ({ page }) => {
    await page.getByLabel("Endpoint URL").fill("https://s3.us-east-1.amazonaws.com");
    await page.getByLabel("Bucket").fill("my-backups");
    await page.getByLabel("Region").fill("us-east-1");
    await page.getByLabel("Access Key").fill("AKIAIOSFODNN7EXAMPLE");
    await page.getByLabel("Secret Key").fill("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY");

    const s3Section = page.locator("section", { has: page.getByRole("heading", { name: "S3 Backup Storage" }) });
    await s3Section.getByRole("button", { name: "Save" }).click();

    await expect(page.getByText("S3 configuration saved")).toBeVisible();
  });

  // ─── Configured state ─────────────────────────────────────────────────────────

  test("shows Connected status and Update button when configured", async ({ page }) => {
    // Override S3 route to return configured state
    await page.route("**/api/settings/s3", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({
          json: {
            configured: true,
            endpoint_url: "https://s3.us-east-1.amazonaws.com",
            bucket: "my-backups",
            region: "us-east-1",
            access_key: "AKIAIOSFODNN7EXAMPLE",
            prefix: "infrakt/",
          },
        });
      }
      if (route.request().method() === "PUT") {
        return route.fulfill({ json: { message: "S3 configuration saved" } });
      }
      if (route.request().method() === "DELETE") {
        return route.fulfill({ json: { message: "S3 configuration removed" } });
      }
      return route.continue();
    });
    await page.goto("/settings");

    await expect(page.getByText("S3 storage configured")).toBeVisible();

    const s3Section = page.locator("section", { has: page.getByRole("heading", { name: "S3 Backup Storage" }) });
    await expect(s3Section.getByRole("button", { name: "Update" })).toBeVisible();
  });

  test("pre-fills form fields when configured", async ({ page }) => {
    await page.route("**/api/settings/s3", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({
          json: {
            configured: true,
            endpoint_url: "https://s3.us-east-1.amazonaws.com",
            bucket: "my-backups",
            region: "us-east-1",
            access_key: "AKIAIOSFODNN7EXAMPLE",
            prefix: "infrakt/",
          },
        });
      }
      return route.continue();
    });
    await page.goto("/settings");

    await expect(page.getByLabel("Endpoint URL")).toHaveValue("https://s3.us-east-1.amazonaws.com");
    await expect(page.getByLabel("Bucket")).toHaveValue("my-backups");
    await expect(page.getByLabel("Region")).toHaveValue("us-east-1");
    await expect(page.getByLabel("Prefix")).toHaveValue("infrakt/");
    await expect(page.getByLabel("Access Key")).toHaveValue("AKIAIOSFODNN7EXAMPLE");
  });

  // ─── Removing S3 config ───────────────────────────────────────────────────────

  test("Remove button removes S3 config and shows toast", async ({ page }) => {
    await page.route("**/api/settings/s3", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({
          json: {
            configured: true,
            endpoint_url: "https://s3.us-east-1.amazonaws.com",
            bucket: "my-backups",
            region: "us-east-1",
            access_key: "AKIAIOSFODNN7EXAMPLE",
            prefix: "",
          },
        });
      }
      if (route.request().method() === "DELETE") {
        return route.fulfill({ json: { message: "S3 configuration removed" } });
      }
      return route.continue();
    });
    await page.goto("/settings");

    const s3Section = page.locator("section", { has: page.getByRole("heading", { name: "S3 Backup Storage" }) });
    await s3Section.getByRole("button", { name: "Remove" }).click();

    await expect(page.getByText("S3 configuration removed")).toBeVisible();
  });
});

// ─── Database Detail — Backup Location Badges ─────────────────────────────────

test.describe("Database Detail — Backup Location Badges", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/databases/main-pg");
    // Switch to Backups tab
    await page.getByRole("tab", { name: "Backups" }).click();
  });

  test("shows Location column in backup table", async ({ page }) => {
    await expect(page.getByRole("columnheader", { name: "Location" })).toBeVisible();
  });

  test("shows Both badge for backups in both locations", async ({ page }) => {
    await expect(page.getByText("Both").first()).toBeVisible();
  });

  test("shows Local badge for local-only backups", async ({ page }) => {
    await expect(page.getByText("Local").first()).toBeVisible();
  });
});

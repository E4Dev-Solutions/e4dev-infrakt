import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_APPS } from "./fixtures";

const APP = MOCK_APPS[0]; // web-api — has cpu_limit, memory_limit, health_check_url

test.describe("App Detail — Resource Limits", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/apps/${APP.name}`);
  });

  // ─── Header display ──────────────────────────────────────────────────────────

  test("shows CPU limit in app header", async ({ page }) => {
    await expect(page.getByText(`CPU: ${APP.cpu_limit}`)).toBeVisible();
  });

  test("shows memory limit in app header", async ({ page }) => {
    await expect(page.getByText(`Mem: ${APP.memory_limit}`)).toBeVisible();
  });

  // ─── Edit modal fields ────────────────────────────────────────────────────────

  test("Edit modal has CPU Limit and Memory Limit fields", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByLabel("CPU Limit")).toBeVisible();
    await expect(page.getByLabel("Memory Limit")).toBeVisible();
  });

  test("Edit modal pre-populates resource limit values", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByLabel("CPU Limit")).toHaveValue(APP.cpu_limit!);
    await expect(page.getByLabel("Memory Limit")).toHaveValue(APP.memory_limit!);
  });

  test("resource limits can be updated via Edit modal", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByLabel("CPU Limit").fill("2.0");
    await page.getByLabel("Memory Limit").fill("1G");
    await page
      .locator("form")
      .getByRole("button", { name: "Save Changes" })
      .click();
    await expect(page.getByText("App configuration updated")).toBeVisible();
  });
});

test.describe("App Detail — Health Check Config", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/apps/${APP.name}`);
  });

  // ─── Edit modal fields ────────────────────────────────────────────────────────

  test("Edit modal has Health Check URL field", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByLabel("Health Check URL")).toBeVisible();
  });

  test("Edit modal has Health Check Interval field", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByLabel(/Health Check Interval/)).toBeVisible();
  });

  test("Edit modal pre-populates health check values", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByLabel("Health Check URL")).toHaveValue(APP.health_check_url!);
    await expect(page.getByLabel(/Health Check Interval/)).toHaveValue(
      String(APP.health_check_interval),
    );
  });

  test("health check fields can be updated via Edit modal", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByLabel("Health Check URL").fill("/healthz");
    await page.getByLabel(/Health Check Interval/).fill("60");
    await page
      .locator("form")
      .getByRole("button", { name: "Save Changes" })
      .click();
    await expect(page.getByText("App configuration updated")).toBeVisible();
  });
});

test.describe("App Detail — HTTP Health Check Results", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/apps/${APP.name}`);
  });

  test("Health tab shows HTTP Health Check section after check", async ({ page }) => {
    await page.getByRole("tab", { name: "Health" }).click();
    await page.getByRole("button", { name: "Check Health" }).click();
    await expect(page.getByText("HTTP Health Check")).toBeVisible();
  });

  test("Health tab shows HTTP status code", async ({ page }) => {
    await page.getByRole("tab", { name: "Health" }).click();
    await page.getByRole("button", { name: "Check Health" }).click();
    await expect(page.getByText("200")).toBeVisible();
  });

  test("Health tab shows response time", async ({ page }) => {
    await page.getByRole("tab", { name: "Health" }).click();
    await page.getByRole("button", { name: "Check Health" }).click();
    await expect(page.getByText("43ms")).toBeVisible(); // 42.5 rounded to 43
  });

  test("Health tab shows healthy badge", async ({ page }) => {
    await page.getByRole("tab", { name: "Health" }).click();
    await page.getByRole("button", { name: "Check Health" }).click();
    await expect(page.getByText("healthy").first()).toBeVisible();
  });

  test("Health tab shows unhealthy HTTP health", async ({ page }) => {
    await page.route("**/api/apps/*/health", (route) => {
      return route.fulfill({
        json: {
          app_name: "web-api",
          db_status: "running",
          actual_status: "running",
          status_mismatch: false,
          containers: [
            {
              name: "infrakt-web-api",
              state: "running",
              status: "Up 2 hours",
              image: "nginx:latest",
              health: "healthy",
            },
          ],
          http_health: {
            healthy: false,
            status_code: 503,
            response_time_ms: null,
            error: "Service Unavailable",
          },
          checked_at: new Date().toISOString(),
        },
      });
    });
    await page.goto(`/apps/${APP.name}`);
    await page.getByRole("tab", { name: "Health" }).click();
    await page.getByRole("button", { name: "Check Health" }).click();
    await expect(page.getByText("unhealthy")).toBeVisible();
    await expect(page.getByText("503")).toBeVisible();
    await expect(page.getByText("Service Unavailable")).toBeVisible();
  });
});

test.describe("Apps — Resource Limits in Create Form", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/apps");
  });

  test("Create App form has CPU Limit field", async ({ page }) => {
    await page.getByRole("button", { name: "Create App" }).click();
    await expect(page.getByLabel(/CPU Limit/)).toBeVisible();
  });

  test("Create App form has Memory Limit field", async ({ page }) => {
    await page.getByRole("button", { name: "Create App" }).click();
    await expect(page.getByLabel(/Memory Limit/)).toBeVisible();
  });

  test("Create App with resource limits submits successfully", async ({ page }) => {
    await page.getByRole("button", { name: "Create App" }).click();
    await page.getByLabel(/App Name/).fill("limited-app");
    await page.getByLabel(/Server/).selectOption("prod-1");
    await page.getByLabel(/Docker Image/).fill("nginx:latest");
    await page.getByLabel(/CPU Limit/).fill("0.5");
    await page.getByLabel(/Memory Limit/).fill("256M");
    await page
      .locator("form")
      .getByRole("button", { name: "Create App" })
      .click();
    await expect(page.getByText(/created/)).toBeVisible();
  });
});

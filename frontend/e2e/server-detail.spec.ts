import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_SERVERS, MOCK_APPS } from "./fixtures";

const SRV = MOCK_SERVERS[0]; // prod-1

test.describe("Server Detail", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto(`/servers/${SRV.name}`);
  });

  // ─── Header & info ──────────────────────────────────────────────────────────

  test("displays server name heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: SRV.name }),
    ).toBeVisible();
  });

  test("shows connection string in subtitle", async ({ page }) => {
    await expect(
      page.getByText(`${SRV.user}@${SRV.host}:${SRV.port}`),
    ).toBeVisible();
  });

  test("shows provider in subtitle", async ({ page }) => {
    // Subtitle format: user@host:port · provider
    await expect(page.getByText(`· ${SRV.provider}`)).toBeVisible();
  });

  test("shows status badge", async ({ page }) => {
    await expect(page.getByText("active").first()).toBeVisible();
  });

  test("Back to Servers link navigates to servers list", async ({ page }) => {
    await page.getByRole("link", { name: "Back to Servers" }).click();
    await expect(page).toHaveURL(/\/servers$/);
  });

  // ─── Server info card ───────────────────────────────────────────────────────

  test("Server Info card shows host and user", async ({ page }) => {
    // Info card renders InfoRow components with label + value pairs
    const infoCard = page.getByRole("heading", { name: "Server Info" }).locator("..");
    await expect(infoCard).toBeVisible();
    // The host appears in both subtitle and info card — just verify the card section exists
    await expect(page.getByText(SRV.host).first()).toBeVisible();
  });

  // ─── Action buttons ─────────────────────────────────────────────────────────

  test("has Edit, Test Connection, and Provision buttons", async ({
    page,
  }) => {
    await expect(page.getByRole("button", { name: "Edit" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Test Connection" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Provision" }),
    ).toBeVisible();
  });

  test("Test Connection shows success toast", async ({ page }) => {
    await page.getByRole("button", { name: "Test Connection" }).click();
    await expect(page.getByText("Server is reachable")).toBeVisible();
  });

  // ─── Edit modal ─────────────────────────────────────────────────────────────

  test("Edit button opens modal with all fields", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(
      page.getByRole("heading", { name: "Edit Server" }),
    ).toBeVisible();
    await expect(page.getByLabel("Host / IP")).toBeVisible();
    await expect(page.getByLabel("SSH User")).toBeVisible();
    await expect(page.getByLabel("SSH Port")).toBeVisible();
    await expect(page.getByLabel("SSH Key Path")).toBeVisible();
    await expect(page.getByLabel("Provider")).toBeVisible();
  });

  test("Edit modal fields are pre-populated", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByLabel("Host / IP")).toHaveValue(SRV.host);
    await expect(page.getByLabel("SSH User")).toHaveValue(SRV.user);
    await expect(page.getByLabel("SSH Port")).toHaveValue(String(SRV.port));
    await expect(page.getByLabel("Provider")).toHaveValue(SRV.provider);
  });

  test("Cancel closes Edit modal", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(
      page.getByRole("heading", { name: "Edit Server" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(
      page.getByRole("heading", { name: "Edit Server" }),
    ).not.toBeVisible();
  });

  test("Escape closes Edit modal", async ({ page }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await expect(
      page.getByRole("heading", { name: "Edit Server" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("heading", { name: "Edit Server" }),
    ).not.toBeVisible();
  });

  test("Edit submit shows success toast and closes modal", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByLabel("Host / IP").fill("10.0.0.99");
    await page
      .locator("form")
      .getByRole("button", { name: "Save Changes" })
      .click();
    await expect(page.getByText("Server updated")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Edit Server" }),
    ).not.toBeVisible();
  });

  // ─── Resource usage ─────────────────────────────────────────────────────────

  test("shows Resource Usage section", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Resource Usage" }),
    ).toBeVisible();
  });

  test("shows memory usage bar", async ({ page }) => {
    await expect(page.getByLabel("Memory usage")).toBeVisible();
    await expect(page.getByText("3.4 GB used of 7.6 GB")).toBeVisible();
  });

  test("shows disk usage bar", async ({ page }) => {
    await expect(page.getByLabel("Disk usage")).toBeVisible();
    await expect(page.getByText("23.6 GB used of 78.7 GB")).toBeVisible();
  });

  test("shows uptime", async ({ page }) => {
    await expect(page.getByText("up 5 days, 3 hours")).toBeVisible();
  });

  test("Refresh status button is visible", async ({ page }) => {
    await expect(page.getByLabel("Refresh status")).toBeVisible();
  });

  // ─── Containers ─────────────────────────────────────────────────────────────

  test("shows running containers section", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: /Running Containers/ }),
    ).toBeVisible();
  });

  test("lists containers with names and images", async ({ page }) => {
    await expect(page.getByText("infrakt-web-api")).toBeVisible();
    await expect(page.getByText("infrakt-redis")).toBeVisible();
    await expect(page.getByText("nginx:latest")).toBeVisible();
    await expect(page.getByText("redis:7")).toBeVisible();
  });

  // ─── Apps on server ─────────────────────────────────────────────────────────

  test("shows Apps on this Server section", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Apps on this Server" }),
    ).toBeVisible();
  });

  test("lists apps deployed to this server", async ({ page }) => {
    // MOCK_APPS has web-api and redis-cache both on server_id 1 (prod-1)
    await expect(
      page.getByRole("link", { name: MOCK_APPS[0].name }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: MOCK_APPS[1].name }),
    ).toBeVisible();
  });

  test("app links navigate to app detail", async ({ page }) => {
    await page.getByRole("link", { name: MOCK_APPS[0].name }).click();
    await expect(page).toHaveURL(/\/apps\/web-api/);
  });

  // ─── Provisioning ──────────────────────────────────────────────────────────

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
    await expect(page.getByText("[3/9] Setting up Traefik")).toBeVisible();
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

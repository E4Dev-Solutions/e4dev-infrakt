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
    // Provider appears inline in the subtitle line
    await expect(page.getByText(SRV.provider).first()).toBeVisible();
  });

  test("shows status badge", async ({ page }) => {
    await expect(page.getByText("active").first()).toBeVisible();
  });

  test("Back to Servers link navigates to servers list", async ({ page }) => {
    await page.getByRole("link", { name: "Back to Servers" }).click();
    await expect(page).toHaveURL(/\/servers$/);
  });

  // ─── Action buttons ─────────────────────────────────────────────────────────

  test("has Provision, Test Connection buttons and kebab menu", async ({
    page,
  }) => {
    await expect(page.getByRole("button", { name: "Provision" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Test Connection" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "More actions" })).toBeVisible();
  });

  test("Test Connection shows success toast", async ({ page }) => {
    await page.getByRole("button", { name: "Test Connection" }).click();
    await expect(page.getByText("Server is reachable")).toBeVisible();
  });

  test("Delete Server is in kebab menu", async ({ page }) => {
    page.on("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "More actions" }).click();
    await expect(page.getByText("Delete Server")).toBeVisible();
  });

  // ─── Overview tab (default) ────────────────────────────────────────────────

  test("Overview tab is active by default", async ({ page }) => {
    await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("Overview shows stat cards", async ({ page }) => {
    const overview = page.getByLabel("Overview");
    await expect(overview.getByText("Status", { exact: true })).toBeVisible();
    await expect(overview.getByText("Uptime", { exact: true })).toBeVisible();
    // "Apps" and "Containers" labels in stat cards
    await expect(overview.getByText("Containers", { exact: true })).toBeVisible();
  });

  test("Overview shows Quick Info section", async ({ page }) => {
    await expect(page.getByText("Quick Info")).toBeVisible();
    await expect(page.getByLabel("Overview").getByText(SRV.host)).toBeVisible();
  });

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

  // ─── Containers (in Overview) ─────────────────────────────────────────────

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

  // ─── Apps tab ─────────────────────────────────────────────────────────────

  test("Apps tab shows deployed apps", async ({ page }) => {
    await page.getByRole("tab", { name: "Apps" }).click();
    await expect(
      page.getByRole("link", { name: MOCK_APPS[0].name }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: MOCK_APPS[1].name }),
    ).toBeVisible();
  });

  test("Apps tab shows app type badges", async ({ page }) => {
    await page.getByRole("tab", { name: "Apps" }).click();
    await expect(page.getByText("git").first()).toBeVisible();
    await expect(page.getByText("image").first()).toBeVisible();
  });

  test("app links navigate to app detail", async ({ page }) => {
    await page.getByRole("tab", { name: "Apps" }).click();
    await page.getByRole("link", { name: MOCK_APPS[0].name }).click();
    await expect(page).toHaveURL(/\/apps\/web-api/);
  });

  // ─── Settings tab ─────────────────────────────────────────────────────────

  test("Settings tab has form fields", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await expect(page.getByLabel("Host / IP")).toBeVisible();
    await expect(page.getByLabel("SSH User")).toBeVisible();
    await expect(page.getByLabel("SSH Port")).toBeVisible();
    await expect(page.getByLabel("SSH Key Path")).toBeVisible();
    await expect(page.getByLabel("Provider")).toBeVisible();
  });

  test("Settings tab pre-populates values", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await expect(page.getByLabel("Host / IP")).toHaveValue(SRV.host);
    await expect(page.getByLabel("SSH User")).toHaveValue(SRV.user);
    await expect(page.getByLabel("SSH Port")).toHaveValue(String(SRV.port));
    await expect(page.getByLabel("Provider")).toHaveValue(SRV.provider);
  });

  test("Settings Save button is disabled when no changes", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await expect(page.getByRole("button", { name: "Save Changes" })).toBeDisabled();
  });

  test("Settings Save button enables on change and shows toast", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await page.getByLabel("Host / IP").fill("10.0.0.99");
    const saveBtn = page.getByRole("button", { name: "Save Changes" });
    await expect(saveBtn).toBeEnabled();
    await saveBtn.click();
    await expect(page.getByText("Server configuration updated")).toBeVisible();
  });

  test("Settings Danger Zone is collapsed by default", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await expect(page.getByText("Danger Zone")).toBeVisible();
    await expect(
      page.locator("[id='tabpanel-settings']").getByRole("button", { name: "Delete Server" }),
    ).not.toBeVisible();
  });

  test("Settings Danger Zone expands and shows Delete button", async ({ page }) => {
    await page.getByRole("tab", { name: "Settings" }).click();
    await page.getByText("Danger Zone").click();
    await expect(
      page.locator("[id='tabpanel-settings']").getByRole("button", { name: "Delete Server" }),
    ).toBeVisible();
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

test.describe("Provision wipe confirmation", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
  });

  test("shows wipe modal for non-infrakT-host server", async ({ page }) => {
    await page.goto("/servers/staging");
    await page.getByRole("button", { name: /provision/i }).click();
    await expect(page.getByText("Wipe & Provision Server")).toBeVisible();
    await expect(page.getByText('Type "staging" to confirm')).toBeVisible();
  });

  test("wipe confirm button is disabled until name typed", async ({ page }) => {
    await page.goto("/servers/staging");
    await page.getByRole("button", { name: /provision/i }).click();
    const confirmBtn = page.getByRole("button", { name: "Wipe & Provision" });
    await expect(confirmBtn).toBeDisabled();
    await page.getByRole("textbox").fill("staging");
    await expect(confirmBtn).toBeEnabled();
  });

  test("does NOT show wipe modal for infrakT host server", async ({ page }) => {
    await page.goto("/servers/prod-1");
    await page.getByRole("button", { name: /provision/i }).click();
    await expect(page.getByText("Wipe & Provision Server")).not.toBeVisible();
  });

  test("cancel closes the modal", async ({ page }) => {
    await page.goto("/servers/staging");
    await page.getByRole("button", { name: /provision/i }).click();
    await expect(page.getByText("Wipe & Provision Server")).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByText("Wipe & Provision Server")).not.toBeVisible();
  });
});

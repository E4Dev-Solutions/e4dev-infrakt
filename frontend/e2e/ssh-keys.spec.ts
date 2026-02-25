import { test, expect } from "@playwright/test";
import { login, mockApi, MOCK_SSH_KEYS } from "./fixtures";

test.describe("Settings — SSH Keys", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/settings");
  });

  // ─── Rendering ───────────────────────────────────────────────────────────────

  test("displays SSH Keys section heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "SSH Keys" }),
    ).toBeVisible();
  });

  test("lists existing SSH keys with names", async ({ page }) => {
    await expect(page.getByText("prod-key")).toBeVisible();
    await expect(page.getByText("staging-key")).toBeVisible();
  });

  test("shows key type badges", async ({ page }) => {
    const badges = page.getByText("ed25519");
    await expect(badges.first()).toBeVisible();
  });

  test("shows fingerprints for each key", async ({ page }) => {
    // Fingerprints are truncated to 32 chars
    const fp = MOCK_SSH_KEYS[0].fingerprint.slice(0, 32);
    await expect(page.getByText(fp)).toBeVisible();
  });

  test("shows Generate Key button", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: "Generate Key" }).first(),
    ).toBeVisible();
  });

  // ─── Empty state ─────────────────────────────────────────────────────────────

  test("shows empty state when no SSH keys exist", async ({ page }) => {
    await page.route("**/api/keys", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: [] });
      }
      return route.continue();
    });
    await page.goto("/settings");
    await expect(page.getByText("No SSH keys")).toBeVisible();
  });

  // ─── Generate Key modal ──────────────────────────────────────────────────────

  test("Generate Key button opens modal", async ({ page }) => {
    await page.getByRole("button", { name: "Generate Key" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Generate SSH Key" }),
    ).toBeVisible();
  });

  test("modal has key name input", async ({ page }) => {
    await page.getByRole("button", { name: "Generate Key" }).first().click();
    await expect(page.getByLabel(/Key Name/)).toBeVisible();
  });

  test("Cancel closes Generate Key modal", async ({ page }) => {
    await page.getByRole("button", { name: "Generate Key" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Generate SSH Key" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(
      page.getByRole("heading", { name: "Generate SSH Key" }),
    ).not.toBeVisible();
  });

  test("Escape closes Generate Key modal", async ({ page }) => {
    await page.getByRole("button", { name: "Generate Key" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Generate SSH Key" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("heading", { name: "Generate SSH Key" }),
    ).not.toBeVisible();
  });

  test("Generate button is disabled when name is empty", async ({ page }) => {
    await page.getByRole("button", { name: "Generate Key" }).first().click();
    const submitBtn = page.locator("form").getByRole("button", { name: "Generate" });
    await expect(submitBtn).toBeDisabled();
  });

  test("form submission generates key and shows toast", async ({ page }) => {
    await page.getByRole("button", { name: "Generate Key" }).first().click();
    await page.getByLabel(/Key Name/).fill("my-new-key");
    await page
      .locator("form")
      .getByRole("button", { name: "Generate" })
      .click();
    await expect(page.getByText(/SSH key.*generated/)).toBeVisible();
    // Modal should close
    await expect(
      page.getByRole("heading", { name: "Generate SSH Key" }),
    ).not.toBeVisible();
  });

  // ─── Deploy to server ────────────────────────────────────────────────────────

  test("deploy button is visible for each key", async ({ page }) => {
    const key = MOCK_SSH_KEYS[0];
    await expect(
      page.getByLabel(`Deploy ${key.name} to server`),
    ).toBeVisible();
  });

  test("clicking deploy opens server selection modal", async ({ page }) => {
    const key = MOCK_SSH_KEYS[0];
    await page.getByLabel(`Deploy ${key.name} to server`).click();
    await expect(
      page.getByRole("heading", { name: "Deploy Key to Server" }),
    ).toBeVisible();
    await expect(page.getByLabel("Server *")).toBeVisible();
  });

  test("deploy modal shows servers in dropdown", async ({ page }) => {
    const key = MOCK_SSH_KEYS[0];
    await page.getByLabel(`Deploy ${key.name} to server`).click();
    const serverSelect = page.getByLabel("Server *");
    // Should have "Select a server" + the mock servers
    await expect(serverSelect.locator("option")).toHaveCount(3); // placeholder + 2 servers
  });

  test("Cancel closes deploy modal", async ({ page }) => {
    const key = MOCK_SSH_KEYS[0];
    await page.getByLabel(`Deploy ${key.name} to server`).click();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(
      page.getByRole("heading", { name: "Deploy Key to Server" }),
    ).not.toBeVisible();
  });

  test("deploy submit shows success toast", async ({ page }) => {
    const key = MOCK_SSH_KEYS[0];
    await page.getByLabel(`Deploy ${key.name} to server`).click();
    await page.getByLabel("Server *").selectOption("prod-1");
    await page
      .locator("form")
      .getByRole("button", { name: "Deploy" })
      .click();
    await expect(page.getByText(/deployed/i)).toBeVisible();
  });

  // ─── Delete flow ─────────────────────────────────────────────────────────────

  test("delete button is visible for each key", async ({ page }) => {
    const key = MOCK_SSH_KEYS[0];
    await expect(
      page.getByLabel(`Delete ${key.name}`),
    ).toBeVisible();
  });

  test("delete triggers confirmation dialog", async ({ page }) => {
    let dialogMessage = "";
    page.on("dialog", (dialog) => {
      dialogMessage = dialog.message();
      void dialog.accept();
    });
    const key = MOCK_SSH_KEYS[0];
    await page.getByLabel(`Delete ${key.name}`).click();
    expect(dialogMessage).toContain(key.name);
  });

  test("accepting delete shows success toast", async ({ page }) => {
    page.on("dialog", (dialog) => dialog.accept());
    const key = MOCK_SSH_KEYS[0];
    await page.getByLabel(`Delete ${key.name}`).click();
    await expect(page.getByText(/deleted/i)).toBeVisible();
  });

  test("dismissing delete does not remove key", async ({ page }) => {
    page.on("dialog", (dialog) => dialog.dismiss());
    const key = MOCK_SSH_KEYS[0];
    await page.getByLabel(`Delete ${key.name}`).click();
    // Key should still be visible
    await expect(page.getByText(key.name)).toBeVisible();
  });
});

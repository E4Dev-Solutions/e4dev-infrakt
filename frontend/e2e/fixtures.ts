/**
 * Shared mock data and helpers for Playwright E2E tests.
 *
 * Uses `page.route()` to intercept all /api/* calls so tests run without
 * a real backend.
 */

import type { Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

export const MOCK_SERVERS = [
  {
    id: 1,
    name: "prod-1",
    host: "203.0.113.10",
    user: "root",
    port: 22,
    status: "active",
    provider: "hetzner",
    app_count: 2,
    ssh_key_path: null,
    created_at: "2025-01-15T10:00:00",
    updated_at: "2025-01-15T10:00:00",
  },
  {
    id: 2,
    name: "staging",
    host: "198.51.100.5",
    user: "deploy",
    port: 2222,
    status: "active",
    provider: "digitalocean",
    app_count: 1,
    ssh_key_path: null,
    created_at: "2025-02-01T12:00:00",
    updated_at: "2025-02-01T12:00:00",
  },
];

export const MOCK_APPS = [
  {
    id: 1,
    name: "web-api",
    server_id: 1,
    server_name: "prod-1",
    domain: "api.example.com",
    port: 3000,
    git_repo: "https://github.com/org/web-api.git",
    branch: "main",
    image: null,
    status: "running",
    app_type: "git",
    created_at: "2025-01-20T08:00:00",
    updated_at: "2025-01-20T08:00:00",
  },
  {
    id: 2,
    name: "redis-cache",
    server_id: 1,
    server_name: "prod-1",
    domain: null,
    port: 6379,
    git_repo: null,
    branch: null,
    image: "redis:7",
    status: "stopped",
    app_type: "image",
    created_at: "2025-01-21T09:00:00",
    updated_at: "2025-01-21T09:00:00",
  },
];

export const MOCK_DATABASES = [
  {
    id: 1,
    name: "main-pg",
    server_id: 1,
    server_name: "prod-1",
    db_type: "postgres",
    status: "running",
    port: 5432,
    created_at: "2025-01-18T14:00:00",
  },
];

export const MOCK_DEPLOYMENTS = [
  {
    id: 1,
    app_id: 1,
    app_name: "web-api",
    status: "success",
    log: "Deployed successfully",
    commit_hash: "abc12345",
    started_at: "2025-02-10T10:00:00",
    finished_at: "2025-02-10T10:02:00",
  },
  {
    id: 2,
    app_id: 1,
    app_name: "web-api",
    status: "failed",
    log: "Build failed",
    commit_hash: "def67890",
    started_at: "2025-02-09T15:00:00",
    finished_at: "2025-02-09T15:01:00",
  },
];

export const MOCK_DASHBOARD = {
  total_servers: 2,
  active_servers: 2,
  total_apps: 2,
  running_apps: 1,
  total_databases: 1,
  recent_deployments: MOCK_DEPLOYMENTS,
};

export const MOCK_PROXY_DOMAINS = [
  { domain: "api.example.com", port: 3000 },
  { domain: "app.example.com", port: 8080 },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Set the API key in localStorage so the app skips the login page.
 * Must be called before `page.goto()`.
 */
export async function login(page: Page): Promise<void> {
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.setItem("infrakt_api_key", "test-key-for-e2e");
  });
}

/**
 * Intercept all /api/* routes with mock data.
 * Call this before navigating to a page.
 */
export async function mockApi(page: Page): Promise<void> {
  // Dashboard
  await page.route("**/api/dashboard", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: MOCK_DASHBOARD });
    }
    return route.continue();
  });

  // Servers
  await page.route("**/api/servers", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: MOCK_SERVERS });
    }
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      return route.fulfill({
        status: 201,
        json: {
          id: 99,
          ...body,
          status: "active",
          app_count: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      });
    }
    return route.continue();
  });

  // Server detail operations
  await page.route("**/api/servers/*", (route) => {
    if (route.request().method() === "DELETE") {
      return route.fulfill({ json: { message: "Server deleted" } });
    }
    if (route.request().method() === "PUT") {
      return route.fulfill({ json: { ...MOCK_SERVERS[0], ...route.request().postDataJSON() } });
    }
    return route.continue();
  });

  // Server status
  await page.route("**/api/servers/*/status", (route) => {
    return route.fulfill({
      json: {
        cpu_usage: "12%",
        memory_usage: "45%",
        disk_usage: "30%",
        docker_running: true,
        containers: 3,
      },
    });
  });

  // Server provision
  await page.route("**/api/servers/*/provision", (route) => {
    return route.fulfill({ json: { message: "Provisioning started" } });
  });

  // Server test
  await page.route("**/api/servers/*/test", (route) => {
    return route.fulfill({ json: { success: true, message: "Connection OK" } });
  });

  // Apps
  await page.route("**/api/apps", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: MOCK_APPS });
    }
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      return route.fulfill({
        status: 201,
        json: {
          id: 99,
          ...body,
          server_id: 1,
          server_name: body.server_name,
          status: "stopped",
          app_type: body.image ? "image" : body.git_repo ? "git" : "compose",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      });
    }
    return route.continue();
  });

  // App actions — must be registered before the generic /apps/* route
  await page.route("**/api/apps/*/deploy", (route) => {
    return route.fulfill({
      json: { message: "Deployment started", deployment_id: 100 },
    });
  });

  await page.route("**/api/apps/*/restart", (route) => {
    return route.fulfill({ json: { message: "App restarted" } });
  });

  await page.route("**/api/apps/*/stop", (route) => {
    return route.fulfill({ json: { message: "App stopped" } });
  });

  await page.route("**/api/apps/*/logs", (route) => {
    return route.fulfill({
      json: { app_name: "web-api", logs: "2025-01-01 Container started\n2025-01-01 Listening on :3000" },
    });
  });

  await page.route("**/api/apps/*/deployments", (route) => {
    return route.fulfill({ json: MOCK_DEPLOYMENTS });
  });

  await page.route("**/api/apps/*/env", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        json: [
          { key: "DATABASE_URL", value: "****" },
          { key: "NODE_ENV", value: "production" },
        ],
      });
    }
    if (route.request().method() === "POST") {
      return route.fulfill({ json: { message: "Environment variables set" } });
    }
    return route.continue();
  });

  // App detail (PUT, DELETE)
  await page.route("**/api/apps/*", (route) => {
    if (route.request().method() === "DELETE") {
      return route.fulfill({ json: { message: "App destroyed" } });
    }
    if (route.request().method() === "PUT") {
      return route.fulfill({ json: { ...MOCK_APPS[0], ...route.request().postDataJSON() } });
    }
    return route.continue();
  });

  // Databases
  await page.route("**/api/databases", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: MOCK_DATABASES });
    }
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      return route.fulfill({
        status: 201,
        json: {
          id: 99,
          ...body,
          server_id: 1,
          server_name: body.server_name,
          status: "running",
          created_at: new Date().toISOString(),
        },
      });
    }
    return route.continue();
  });

  await page.route("**/api/databases/*", (route) => {
    if (route.request().method() === "DELETE") {
      return route.fulfill({ json: { message: "Database destroyed" } });
    }
    return route.continue();
  });

  // Proxy domains
  await page.route("**/api/proxy/*/domains", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: MOCK_PROXY_DOMAINS });
    }
    return route.continue();
  });

  await page.route("**/api/proxy/*/domains/*", (route) => {
    if (route.request().method() === "DELETE") {
      return route.fulfill({ json: { message: "Route removed" } });
    }
    return route.continue();
  });

  await page.route("**/api/proxy/routes", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({ json: { message: "Route added" } });
    }
    return route.continue();
  });

  await page.route("**/api/proxy/*/reload", (route) => {
    return route.fulfill({ json: { message: "Caddy reloaded" } });
  });

  await page.route("**/api/proxy/*/status", (route) => {
    return route.fulfill({ json: { running: true, version: "2.7.6" } });
  });
}

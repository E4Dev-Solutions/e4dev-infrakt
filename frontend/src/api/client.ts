// ─── Types ────────────────────────────────────────────────────────────────────

export interface DashboardData {
  total_servers: number;
  active_servers: number;
  total_apps: number;
  running_apps: number;
  total_databases: number;
  recent_deployments: RecentDeployment[];
}

export interface RecentDeployment {
  id: string;
  app_name: string;
  status: DeploymentStatus;
  commit_hash?: string;
  started_at: string;
  finished_at?: string;
}

export type ServerStatus = "active" | "inactive" | "provisioning" | "error" | string;
export type AppStatus = "running" | "stopped" | "deploying" | "error" | string;
export type DeploymentStatus = "success" | "failed" | "in_progress" | "pending" | string;
export type DbStatus = "running" | "stopped" | "error" | string;
export type DbType = "postgres" | "mysql" | "redis" | "mongo" | string;

export interface Server {
  id: string;
  name: string;
  host: string;
  user: string;
  port: number;
  ssh_key_path?: string;
  status: ServerStatus;
  provider?: string;
  created_at: string;
  updated_at: string;
  app_count: number;
}

export interface ServerStatusData {
  name: string;
  host: string;
  uptime?: string;
  memory?: {
    total: string;
    used: string;
    free: string;
    percent: number;
  };
  disk?: {
    total: string;
    used: string;
    free: string;
    percent: number;
  };
  containers?: ContainerInfo[];
}

export interface ContainerInfo {
  id: string;
  name: string;
  status: string;
  image?: string;
}

export interface App {
  id: string;
  name: string;
  server_id: string;
  server_name: string;
  domain?: string;
  port?: number;
  git_repo?: string;
  branch?: string;
  image?: string;
  status: AppStatus;
  app_type?: string;
  created_at: string;
  updated_at: string;
}

export interface Deployment {
  id: string;
  app_id: string;
  commit_hash?: string;
  status: DeploymentStatus;
  log?: string;
  started_at: string;
  finished_at?: string;
}

export interface DeployResult {
  message: string;
  deployment_id: string;
}

export interface AppLogs {
  app_name: string;
  logs: string;
}

export interface EnvVar {
  key: string;
  value: string;
}

export interface Database {
  id: string;
  name: string;
  server_name: string;
  db_type: DbType;
  port?: number;
  status: DbStatus;
}

export interface ProxyDomain {
  domain: string;
  port: number;
}

export interface TestConnectionResult {
  reachable: boolean;
}

// ─── Create Server / App / Database inputs ────────────────────────────────────

export interface CreateServerInput {
  name: string;
  host: string;
  user: string;
  port?: number;
  ssh_key_path?: string;
  provider?: string;
}

export interface UpdateServerInput {
  host?: string;
  user?: string;
  port?: number;
  ssh_key_path?: string;
  provider?: string;
}

export interface CreateAppInput {
  name: string;
  server_name: string;
  domain?: string;
  port?: number;
  git_repo?: string;
  branch?: string;
  image?: string;
}

export interface UpdateAppInput {
  domain?: string;
  port?: number;
  git_repo?: string;
  branch?: string;
  image?: string;
}

export interface ProxyRouteCreateInput {
  server_name: string;
  domain: string;
  port: number;
}

export interface CreateDatabaseInput {
  server_name: string;
  name: string;
  db_type: DbType;
  version?: string;
}

// ─── HTTP helpers ─────────────────────────────────────────────────────────────

class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const API_KEY_STORAGE_KEY = "infrakt_api_key";

export function getApiKey(): string | null {
  return localStorage.getItem(API_KEY_STORAGE_KEY);
}

export function setApiKey(key: string): void {
  localStorage.setItem(API_KEY_STORAGE_KEY, key);
}

export function clearApiKey(): void {
  localStorage.removeItem(API_KEY_STORAGE_KEY);
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `/api${path}`;
  const apiKey = getApiKey();
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(apiKey ? { "X-API-Key": apiKey } : {}),
      ...options.headers,
    },
    ...options,
  });

  if (!res.ok) {
    let message = `Request failed: ${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: string; message?: string };
      message = body.detail ?? body.message ?? message;
    } catch {
      // ignore JSON parse errors — keep default message
    }
    throw new ApiError(res.status, message);
  }

  // 204 No Content
  if (res.status === 204) {
    return undefined as unknown as T;
  }

  return res.json() as Promise<T>;
}

function get<T>(path: string): Promise<T> {
  return request<T>(path);
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

function put<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

export const dashboardApi = {
  get: (): Promise<DashboardData> => get("/dashboard"),
};

// ─── Servers ──────────────────────────────────────────────────────────────────

export const serversApi = {
  list: (): Promise<Server[]> => get("/servers"),

  create: (input: CreateServerInput): Promise<Server> =>
    post("/servers", input),

  delete: (name: string): Promise<void> => del(`/servers/${encodeURIComponent(name)}`),

  provision: (name: string): Promise<unknown> =>
    post(`/servers/${encodeURIComponent(name)}/provision`),

  test: (name: string): Promise<TestConnectionResult> =>
    post(`/servers/${encodeURIComponent(name)}/test`),

  status: (name: string): Promise<ServerStatusData> =>
    get(`/servers/${encodeURIComponent(name)}/status`),

  update: (name: string, input: UpdateServerInput): Promise<Server> =>
    put(`/servers/${encodeURIComponent(name)}`, input),
};

// ─── Apps ─────────────────────────────────────────────────────────────────────

export const appsApi = {
  list: (server?: string): Promise<App[]> => {
    const qs = server ? `?server=${encodeURIComponent(server)}` : "";
    return get(`/apps${qs}`);
  },

  create: (input: CreateAppInput): Promise<App> => post("/apps", input),

  update: (name: string, input: UpdateAppInput): Promise<App> =>
    put(`/apps/${encodeURIComponent(name)}`, input),

  deploy: (name: string): Promise<DeployResult> =>
    post(`/apps/${encodeURIComponent(name)}/deploy`),

  restart: (name: string): Promise<void> =>
    post(`/apps/${encodeURIComponent(name)}/restart`),

  stop: (name: string): Promise<void> =>
    post(`/apps/${encodeURIComponent(name)}/stop`),

  delete: (name: string): Promise<void> =>
    del(`/apps/${encodeURIComponent(name)}`),

  logs: (name: string, lines = 100): Promise<AppLogs> =>
    get(`/apps/${encodeURIComponent(name)}/logs?lines=${lines}`),

  deployments: (name: string): Promise<Deployment[]> =>
    get(`/apps/${encodeURIComponent(name)}/deployments`),

  getEnv: (name: string, showValues = false): Promise<EnvVar[]> =>
    get(`/apps/${encodeURIComponent(name)}/env?show_values=${showValues}`),

  setEnv: (name: string, vars: EnvVar[]): Promise<void> =>
    post(`/apps/${encodeURIComponent(name)}/env`, vars),

  deleteEnv: (name: string, key: string): Promise<void> =>
    del(`/apps/${encodeURIComponent(name)}/env/${encodeURIComponent(key)}`),
};

// ─── Databases ────────────────────────────────────────────────────────────────

export const databasesApi = {
  list: (server?: string): Promise<Database[]> => {
    const qs = server ? `?server=${encodeURIComponent(server)}` : "";
    return get(`/databases${qs}`);
  },

  create: (input: CreateDatabaseInput): Promise<Database> =>
    post("/databases", input),

  delete: (name: string, server?: string): Promise<void> => {
    const qs = server ? `?server=${encodeURIComponent(server)}` : "";
    return del(`/databases/${encodeURIComponent(name)}${qs}`);
  },
};

// ─── Proxy ────────────────────────────────────────────────────────────────────

export const proxyApi = {
  domains: (server: string): Promise<ProxyDomain[]> =>
    get(`/proxy/${encodeURIComponent(server)}/domains`),

  addRoute: (input: ProxyRouteCreateInput): Promise<{ message: string }> =>
    post("/proxy/routes", input),

  removeRoute: (server: string, domain: string): Promise<{ message: string }> =>
    del(`/proxy/${encodeURIComponent(server)}/domains/${encodeURIComponent(domain)}`),

  reload: (server: string): Promise<{ message: string }> =>
    post(`/proxy/${encodeURIComponent(server)}/reload`),

  status: (server: string): Promise<{ status: string }> =>
    get(`/proxy/${encodeURIComponent(server)}/status`),
};

export { ApiError };

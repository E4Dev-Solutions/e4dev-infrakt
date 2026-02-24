import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import {
  dashboardApi,
  serversApi,
  appsApi,
  databasesApi,
  proxyApi,
  type CreateServerInput,
  type CreateAppInput,
  type CreateDatabaseInput,
  type EnvVar,
  type DashboardData,
  type Server,
  type ServerStatusData,
  type App,
  type AppLogs,
  type Deployment,
  type Database,
  type ProxyDomain,
} from "@/api/client";

// ─── Query Keys ───────────────────────────────────────────────────────────────

export const queryKeys = {
  dashboard: ["dashboard"] as const,
  servers: ["servers"] as const,
  serverStatus: (name: string) => ["servers", name, "status"] as const,
  apps: (server?: string) => ["apps", server ?? "all"] as const,
  appLogs: (name: string) => ["apps", name, "logs"] as const,
  appDeployments: (name: string) => ["apps", name, "deployments"] as const,
  appEnv: (name: string) => ["apps", name, "env"] as const,
  databases: (server?: string) => ["databases", server ?? "all"] as const,
  proxyDomains: (server: string) => ["proxy", server, "domains"] as const,
};

// ─── Dashboard ────────────────────────────────────────────────────────────────

export function useDashboard(
  options?: Partial<UseQueryOptions<DashboardData>>
) {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: dashboardApi.get,
    refetchInterval: 60_000,
    ...options,
  });
}

// ─── Servers ──────────────────────────────────────────────────────────────────

export function useServers(options?: Partial<UseQueryOptions<Server[]>>) {
  return useQuery({
    queryKey: queryKeys.servers,
    queryFn: serversApi.list,
    ...options,
  });
}

export function useServerStatus(
  name: string,
  options?: Partial<UseQueryOptions<ServerStatusData>>
) {
  return useQuery({
    queryKey: queryKeys.serverStatus(name),
    queryFn: () => serversApi.status(name),
    enabled: Boolean(name),
    refetchInterval: 30_000,
    ...options,
  });
}

export function useAddServer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateServerInput) => serversApi.create(input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.servers });
      void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useDeleteServer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => serversApi.delete(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.servers });
      void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useProvisionServer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => serversApi.provision(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.servers });
    },
  });
}

export function useTestServer() {
  return useMutation({
    mutationFn: (name: string) => serversApi.test(name),
  });
}

// ─── Apps ─────────────────────────────────────────────────────────────────────

export function useApps(
  server?: string,
  options?: Partial<UseQueryOptions<App[]>>
) {
  return useQuery({
    queryKey: queryKeys.apps(server),
    queryFn: () => appsApi.list(server),
    ...options,
  });
}

export function useAppLogs(
  name: string,
  lines = 100,
  options?: Partial<UseQueryOptions<AppLogs>>
) {
  return useQuery({
    queryKey: queryKeys.appLogs(name),
    queryFn: () => appsApi.logs(name, lines),
    enabled: Boolean(name),
    refetchInterval: 15_000,
    ...options,
  });
}

export function useAppDeployments(
  name: string,
  options?: Partial<UseQueryOptions<Deployment[]>>
) {
  return useQuery({
    queryKey: queryKeys.appDeployments(name),
    queryFn: () => appsApi.deployments(name),
    enabled: Boolean(name),
    ...options,
  });
}

export function useAppEnv(
  name: string,
  showValues = true,
  options?: Partial<UseQueryOptions<EnvVar[]>>
) {
  return useQuery({
    queryKey: queryKeys.appEnv(name),
    queryFn: () => appsApi.getEnv(name, showValues),
    enabled: Boolean(name),
    ...options,
  });
}

export function useCreateApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateAppInput) => appsApi.create(input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.apps() });
      void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useDeployApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => appsApi.deploy(name),
    onSuccess: (_data, name) => {
      void qc.invalidateQueries({ queryKey: queryKeys.appDeployments(name) });
      void qc.invalidateQueries({ queryKey: queryKeys.apps() });
      void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useRestartApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => appsApi.restart(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.apps() });
    },
  });
}

export function useStopApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => appsApi.stop(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.apps() });
      void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useDestroyApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => appsApi.delete(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.apps() });
      void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useSetEnv() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, vars }: { name: string; vars: EnvVar[] }) =>
      appsApi.setEnv(name, vars),
    onSuccess: (_data, { name }) => {
      void qc.invalidateQueries({ queryKey: queryKeys.appEnv(name) });
    },
  });
}

export function useDeleteEnv() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, key }: { name: string; key: string }) =>
      appsApi.deleteEnv(name, key),
    onSuccess: (_data, { name }) => {
      void qc.invalidateQueries({ queryKey: queryKeys.appEnv(name) });
    },
  });
}

// ─── Databases ────────────────────────────────────────────────────────────────

export function useDatabases(
  server?: string,
  options?: Partial<UseQueryOptions<Database[]>>
) {
  return useQuery({
    queryKey: queryKeys.databases(server),
    queryFn: () => databasesApi.list(server),
    ...options,
  });
}

export function useCreateDatabase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateDatabaseInput) => databasesApi.create(input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.databases() });
      void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useDeleteDatabase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, server }: { name: string; server?: string }) =>
      databasesApi.delete(name, server),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.databases() });
      void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

// ─── Proxy ────────────────────────────────────────────────────────────────────

export function useProxyDomains(
  server: string,
  options?: Partial<UseQueryOptions<ProxyDomain[]>>
) {
  return useQuery({
    queryKey: queryKeys.proxyDomains(server),
    queryFn: () => proxyApi.domains(server),
    enabled: Boolean(server),
    ...options,
  });
}

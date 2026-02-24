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
  type UpdateServerInput,
  type CreateAppInput,
  type UpdateAppInput,
  type CreateDatabaseInput,
  type ProxyRouteCreateInput,
  type EnvVar,
  type AppHealth,
  type DashboardData,
  type Server,
  type ServerStatusData,
  type App,
  type AppLogs,
  type Deployment,
  type Database,
  type BackupFile,
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
  appHealth: (name: string) => ["apps", name, "health"] as const,
  databases: (server?: string) => ["databases", server ?? "all"] as const,
  database: (name: string) => ["databases", name] as const,
  databaseBackups: (name: string) => ["databases", name, "backups"] as const,
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

export function useUpdateServer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, input }: { name: string; input: UpdateServerInput }) =>
      serversApi.update(name, input),
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

export function useAppHealth(
  name: string,
  options?: Partial<UseQueryOptions<AppHealth>>
) {
  return useQuery({
    queryKey: queryKeys.appHealth(name),
    queryFn: () => appsApi.health(name),
    enabled: false, // on-demand only — triggered by refetch()
    staleTime: Infinity,
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

export function useUpdateApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, input }: { name: string; input: UpdateAppInput }) =>
      appsApi.update(name, input),
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

export function useRollbackApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, deploymentId }: { name: string; deploymentId?: number }) =>
      appsApi.rollback(name, deploymentId),
    onSuccess: (_data, { name }) => {
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

export function useDatabase(name: string, options?: Partial<UseQueryOptions<Database>>) {
  return useQuery({
    queryKey: queryKeys.database(name),
    queryFn: () => databasesApi.get(name),
    enabled: Boolean(name),
    ...options,
  });
}

export function useDatabaseBackups(name: string, server?: string, options?: Partial<UseQueryOptions<BackupFile[]>>) {
  return useQuery({
    queryKey: queryKeys.databaseBackups(name),
    queryFn: () => databasesApi.listBackups(name, server),
    enabled: Boolean(name),
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

export function useBackupDatabase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, server }: { name: string; server?: string }) =>
      databasesApi.backup(name, server),
    onSuccess: (_data, { name }) => {
      void qc.invalidateQueries({ queryKey: queryKeys.databaseBackups(name) });
    },
  });
}

export function useRestoreDatabase() {
  return useMutation({
    mutationFn: ({
      name,
      filename,
      serverName,
    }: {
      name: string;
      filename: string;
      serverName?: string;
    }) => databasesApi.restore(name, filename, serverName),
  });
}

export function useScheduleBackup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      name,
      cronExpression,
      retentionDays,
      server,
    }: {
      name: string;
      cronExpression: string;
      retentionDays?: number;
      server?: string;
    }) => databasesApi.schedule(name, cronExpression, retentionDays, server),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["databases"] });
    },
  });
}

export function useUnscheduleBackup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, server }: { name: string; server?: string }) =>
      databasesApi.unschedule(name, server),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["databases"] });
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

export function useAddProxyRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ProxyRouteCreateInput) => proxyApi.addRoute(input),
    onSuccess: (_data, input) => {
      void qc.invalidateQueries({ queryKey: queryKeys.proxyDomains(input.server_name) });
    },
  });
}

export function useRemoveProxyRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ server, domain }: { server: string; domain: string }) =>
      proxyApi.removeRoute(server, domain),
    onSuccess: (_data, { server }) => {
      void qc.invalidateQueries({ queryKey: queryKeys.proxyDomains(server) });
    },
  });
}

export function useReloadProxy() {
  return useMutation({
    mutationFn: (server: string) => proxyApi.reload(server),
  });
}

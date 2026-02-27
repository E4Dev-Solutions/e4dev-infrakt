import { useState, useRef, useEffect, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Play,
  RefreshCw,
  Square,
  Trash2,
  Pencil,
  Terminal,
  Settings,
  Clock,
  Loader2,
  Plus,
  Trash,
  Globe,
  Server,
  GitBranch,
  Box,
  Activity,
  ChevronDown,
  ChevronRight,
  RotateCcw,
  MoreVertical,
  ExternalLink,
} from "lucide-react";
import {
  useApps,
  useAppLogs,
  useAppDeployments,
  useAppEnv,
  useAppHealth,
  useDeployApp,
  useRollbackApp,
  useRestartApp,
  useStopApp,
  useDestroyApp,
  useSetEnv,
  useDeleteEnv,
  useUpdateApp,
  useContainerEnv,
  useAppServices,
} from "@/hooks/useApi";
import { useToast } from "@/hooks/useToast";
import { useDeploymentStream } from "@/hooks/useDeploymentStream";
import { useContainerLogStream } from "@/hooks/useContainerLogStream";
import { ToastContainer } from "@/components/Toast";
import StatusBadge from "@/components/StatusBadge";
import DeploymentLogStream from "@/components/DeploymentLogStream";
import type { App, UpdateAppInput } from "@/api/client";

type ActiveTab = "overview" | "logs" | "env" | "deployments" | "settings";

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function formatRelativeTime(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const minutes = Math.floor(diff / 60_000);
    if (minutes < 1) return "just now";
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  } catch {
    return iso;
  }
}

function TabButton({
  id,
  label,
  icon,
  isActive,
  onClick,
}: {
  id: ActiveTab;
  label: string;
  icon: React.ReactNode;
  isActive: boolean;
  onClick: (id: ActiveTab) => void;
}) {
  return (
    <button
      role="tab"
      aria-selected={isActive}
      aria-controls={`tabpanel-${id}`}
      onClick={() => onClick(id)}
      className={[
        "flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors",
        isActive
          ? "border-orange-500 text-orange-400"
          : "border-transparent text-zinc-400 hover:border-zinc-500 hover:text-zinc-200",
      ].join(" ")}
    >
      {icon}
      {label}
    </button>
  );
}

// ─── Overview Tab ────────────────────────────────────────────────────────────

function OverviewTab({ app }: { app: App }) {
  const { data: healthData, refetch: refetchHealth, isFetching: healthFetching } = useAppHealth(app.name, { enabled: false });
  const { data: deployments = [] } = useAppDeployments(app.name);

  const recentDeploys = deployments.slice(0, 5);
  const lastDeploy = deployments[0];

  return (
    <div className="space-y-6">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {/* Status */}
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">Status</p>
          <StatusBadge status={app.status} />
        </div>
        {/* Last Deploy */}
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">Last Deploy</p>
          {lastDeploy ? (
            <div className="flex items-center gap-2">
              <span className="text-sm text-zinc-200">{formatRelativeTime(lastDeploy.started_at)}</span>
              {lastDeploy.commit_hash && (
                <span className="rounded bg-zinc-700 px-1.5 py-0.5 font-mono text-xs text-zinc-400">
                  {lastDeploy.commit_hash.slice(0, 7)}
                </span>
              )}
            </div>
          ) : (
            <span className="text-sm text-zinc-500">Never deployed</span>
          )}
        </div>
        {/* App Type */}
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">App Type</p>
          <span className="rounded bg-zinc-700 px-2 py-0.5 font-mono text-xs text-zinc-300">
            {app.app_type || "compose"}
          </span>
        </div>
      </div>

      {/* Container Metrics */}
      <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-zinc-200">Container Metrics</h3>
          <button
            onClick={() => void refetchHealth()}
            disabled={healthFetching}
            className="flex items-center gap-1.5 rounded-md border border-zinc-600 bg-zinc-700 px-3 py-1.5 text-xs text-zinc-300 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
          >
            <RefreshCw
              size={12}
              className={healthFetching ? "animate-spin" : ""}
              aria-hidden="true"
            />
            {healthFetching ? "Checking..." : "Refresh"}
          </button>
        </div>
        {healthFetching && !healthData ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 size={18} className="animate-spin text-zinc-500" aria-label="Loading container metrics" />
          </div>
        ) : healthData && healthData.containers.length === 0 ? (
          <p className="py-4 text-center text-sm text-zinc-500">No containers found.</p>
        ) : healthData?.containers && healthData.containers.length > 0 ? (
          <div className="overflow-hidden rounded-lg border border-zinc-700">
            <table className="w-full text-sm" role="table">
              <thead>
                <tr className="border-b border-zinc-700 bg-zinc-800/60">
                  {["Container", "State", "Status", "Image"].map((h) => (
                    <th
                      key={h}
                      scope="col"
                      className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-zinc-400"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-700/40">
                {healthData.containers.map((c) => (
                  <tr key={c.name} className="bg-zinc-800/30 hover:bg-zinc-800/60">
                    <td className="px-4 py-2.5 font-mono text-xs text-zinc-200">{c.name}</td>
                    <td className="px-4 py-2.5">
                      <StatusBadge status={c.state} />
                    </td>
                    <td className="px-4 py-2.5 text-xs text-zinc-400">{c.status}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-zinc-500">{c.image || "---"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="py-4 text-center text-sm text-zinc-500">
            Click &quot;Refresh&quot; to fetch container state from the server.
          </p>
        )}
      </div>

      {/* Recent Deploys */}
      {recentDeploys.length > 0 && (
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <h3 className="mb-3 text-sm font-semibold text-zinc-200">Recent Deploys</h3>
          <div className="space-y-2">
            {recentDeploys.map((dep) => (
              <div key={dep.id} className="flex items-center gap-3 rounded-md bg-zinc-800/40 px-3 py-2">
                <span
                  className={[
                    "inline-block h-2 w-2 shrink-0 rounded-full",
                    dep.status === "success"
                      ? "bg-emerald-400"
                      : dep.status === "failed"
                        ? "bg-red-400"
                        : "bg-amber-400",
                  ].join(" ")}
                  aria-hidden="true"
                />
                <span className="font-mono text-xs text-zinc-400">#{dep.id}</span>
                <StatusBadge status={dep.status} />
                {dep.commit_hash && (
                  <span className="rounded bg-zinc-700 px-1.5 py-0.5 font-mono text-xs text-zinc-400">
                    {dep.commit_hash.slice(0, 7)}
                  </span>
                )}
                <span className="ml-auto text-xs text-zinc-500">{formatRelativeTime(dep.started_at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick Info */}
      <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
        <h3 className="mb-3 text-sm font-semibold text-zinc-200">Quick Info</h3>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-zinc-500">Server</dt>
            <dd className="text-zinc-300">{app.server_name}</dd>
          </div>
          <div>
            <dt className="text-xs text-zinc-500">Domain</dt>
            <dd className="text-zinc-300">{app.domain || "---"}</dd>
          </div>
          <div>
            <dt className="text-xs text-zinc-500">Port</dt>
            <dd className="text-zinc-300">{app.port || "---"}</dd>
          </div>
          {app.branch && (
            <div>
              <dt className="text-xs text-zinc-500">Branch</dt>
              <dd className="text-zinc-300">{app.branch}</dd>
            </div>
          )}
          {app.replicas != null && (
            <div>
              <dt className="text-xs text-zinc-500">Replicas</dt>
              <dd className="text-zinc-300">{app.replicas}</dd>
            </div>
          )}
          {app.deploy_strategy && (
            <div>
              <dt className="text-xs text-zinc-500">Deploy Strategy</dt>
              <dd className="text-zinc-300">{app.deploy_strategy}</dd>
            </div>
          )}
        </dl>
      </div>

      {/* HTTP Health Check */}
      {healthData?.http_health && (
        <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <h3 className="mb-3 text-sm font-semibold text-zinc-200">HTTP Health Check</h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <p className="text-xs text-zinc-500">Status</p>
              <StatusBadge status={healthData.http_health.healthy ? "healthy" : "unhealthy"} />
            </div>
            {healthData.http_health.status_code != null && (
              <div>
                <p className="text-xs text-zinc-500">HTTP Code</p>
                <p className="font-mono text-sm text-zinc-200">{healthData.http_health.status_code}</p>
              </div>
            )}
            {healthData.http_health.response_time_ms != null && (
              <div>
                <p className="text-xs text-zinc-500">Response Time</p>
                <p className="font-mono text-sm text-zinc-200">{healthData.http_health.response_time_ms.toFixed(0)}ms</p>
              </div>
            )}
            {healthData.http_health.error && (
              <div className="col-span-full">
                <p className="text-xs text-zinc-500">Error</p>
                <p className="text-sm text-red-400">{healthData.http_health.error}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Logs Tab ─────────────────────────────────────────────────────────────────

function LogsTab({ appName }: { appName: string }) {
  const [lines, setLines] = useState(100);
  const [live, setLive] = useState(false);
  const [service, setService] = useState<string>("");
  const { data: services = [] } = useAppServices(appName);
  const { data, isLoading, refetch, isFetching } = useAppLogs(
    appName,
    lines,
    {
      enabled: !live && Boolean(appName),
      refetchInterval: live ? false : 15_000,
    },
    service || undefined,
  );
  const stream = useContainerLogStream(appName, lines, live, service || undefined);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [data?.logs, stream.lines.length]);

  function handleToggleLive() {
    if (live) {
      stream.clear();
    }
    setLive((prev) => !prev);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {!live && (
            <>
              {services.length > 1 && (
                <>
                  <label
                    htmlFor="log-service"
                    className="text-xs text-zinc-400"
                  >
                    Service:
                  </label>
                  <select
                    id="log-service"
                    value={service}
                    onChange={(e) => setService(e.target.value)}
                    className="rounded-md border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                  >
                    <option value="">All services</option>
                    {services.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </>
              )}
              <label
                htmlFor="log-lines"
                className="text-xs text-zinc-400"
              >
                Lines:
              </label>
              <select
                id="log-lines"
                value={lines}
                onChange={(e) => setLines(Number(e.target.value))}
                className="rounded-md border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
              >
                {[50, 100, 200, 500].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </>
          )}
          {live && stream.isStreaming && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-400">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-400" aria-hidden="true" />
              Streaming
            </span>
          )}
          {live && stream.error && (
            <span className="text-xs text-red-400">{stream.error}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {!live && (
            <button
              onClick={() => void refetch()}
              disabled={isFetching}
              className="flex items-center gap-1.5 rounded-md border border-zinc-600 bg-zinc-700 px-3 py-1.5 text-xs text-zinc-300 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
            >
              <RefreshCw
                size={12}
                className={isFetching ? "animate-spin" : ""}
                aria-hidden="true"
              />
              Refresh
            </button>
          )}
          <button
            onClick={handleToggleLive}
            className={[
              "flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500",
              live
                ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20"
                : "border-zinc-600 bg-zinc-700 text-zinc-300 hover:bg-zinc-600",
            ].join(" ")}
            aria-label={live ? "Stop live streaming" : "Start live streaming"}
          >
            {live ? (
              <Square size={12} aria-hidden="true" />
            ) : (
              <Play size={12} aria-hidden="true" />
            )}
            Live
          </button>
        </div>
      </div>

      <div
        className="h-[calc(100vh-340px)] min-h-[300px] overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-950 p-4"
        aria-label="Application logs"
      >
        {live ? (
          stream.lines.length === 0 && stream.isStreaming ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 size={20} className="animate-spin text-zinc-500" aria-label="Connecting to log stream" />
            </div>
          ) : stream.lines.length === 0 ? (
            <p className="text-center text-sm text-zinc-500">No logs available.</p>
          ) : (
            <pre className="log-viewer text-zinc-300">
              {stream.lines.join("\n")}
            </pre>
          )
        ) : isLoading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 size={20} className="animate-spin text-zinc-500" aria-label="Loading logs" />
          </div>
        ) : !data?.logs ? (
          <p className="text-center text-sm text-zinc-500">No logs available.</p>
        ) : (
          <pre className="log-viewer text-zinc-300">{data.logs}</pre>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

// ─── Env Tab ──────────────────────────────────────────────────────────────────

function EnvTab({ appName }: { appName: string }) {
  const { data: userVars = [], isLoading } = useAppEnv(appName, true);
  const {
    data: containerVars = [],
    isLoading: containerLoading,
  } = useContainerEnv(appName);
  const setEnv = useSetEnv();
  const deleteEnv = useDeleteEnv();
  const toast = useToast();

  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [editOriginal, setEditOriginal] = useState("");
  const editRef = useRef<HTMLInputElement>(null);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!newKey.trim()) return;
    try {
      await setEnv.mutateAsync({
        name: appName,
        vars: [{ key: newKey.trim(), value: newValue }],
      });
      toast.success(`Set "${newKey}".`);
      setNewKey("");
      setNewValue("");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to save.",
      );
    }
  }

  async function handleDelete(key: string) {
    setDeletingKey(key);
    try {
      await deleteEnv.mutateAsync({ name: appName, key });
      toast.success(`Deleted "${key}".`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to delete.",
      );
    } finally {
      setDeletingKey(null);
    }
  }

  function startEdit(key: string, value: string) {
    setEditingKey(key);
    setEditValue(value);
    setEditOriginal(value);
    setTimeout(() => editRef.current?.focus(), 0);
  }

  async function saveEdit() {
    if (!editingKey) return;
    // Skip save if value unchanged — avoids accidentally promoting compose vars to overrides
    if (editValue === editOriginal) {
      setEditingKey(null);
      return;
    }
    try {
      await setEnv.mutateAsync({
        name: appName,
        vars: [{ key: editingKey, value: editValue }],
      });
      toast.success(`Updated "${editingKey}".`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to save.",
      );
    }
    setEditingKey(null);
  }

  function cancelEdit() {
    setEditingKey(null);
  }

  // Build unified list: user overrides first, then container vars
  const userKeys = new Set(userVars.map((v) => v.key));
  type UnifiedVar = {
    key: string;
    value: string;
    source: "override" | "compose";
    container?: string;
  };
  const unified: UnifiedVar[] = [];

  // User overrides
  for (const v of userVars) {
    unified.push({
      key: v.key,
      value: v.value ?? "--------",
      source: "override",
    });
  }

  // Container vars (skip keys already overridden by user)
  for (const v of containerVars) {
    if (!userKeys.has(v.key)) {
      unified.push({
        key: v.key,
        value: v.value,
        source: "compose",
        container: v.container,
      });
    }
  }

  // Sort: overrides first, then alphabetical within each group
  unified.sort((a, b) => {
    if (a.source !== b.source) {
      return a.source === "override" ? -1 : 1;
    }
    return a.key.localeCompare(b.key);
  });

  const loading = isLoading || containerLoading;

  return (
    <div className="space-y-4">
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      {/* Add / override form */}
      <form
        onSubmit={handleAdd}
        className="flex items-end gap-3 rounded-lg border border-zinc-700 bg-zinc-800/50 p-4"
      >
        <div className="flex-1">
          <label
            htmlFor="env-key"
            className="mb-1.5 block text-xs font-medium text-zinc-400"
          >
            Key
          </label>
          <input
            id="env-key"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            placeholder="DATABASE_URL"
            className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 font-mono text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
          />
        </div>
        <div className="flex-1">
          <label
            htmlFor="env-value"
            className="mb-1.5 block text-xs font-medium text-zinc-400"
          >
            Value
          </label>
          <input
            id="env-value"
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            placeholder="postgres://..."
            className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 font-mono text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={setEnv.isPending || !newKey.trim()}
          className="flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
        >
          {setEnv.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Plus size={14} />
          )}
          Add
        </button>
      </form>

      {/* Unified env table */}
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2
            size={20}
            className="animate-spin text-zinc-500"
            aria-label="Loading environment variables"
          />
        </div>
      ) : unified.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">
          No environment variables found.
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-700">
          <table className="w-full text-sm" role="table">
            <thead>
              <tr className="border-b border-zinc-700 bg-zinc-800/60">
                <th
                  scope="col"
                  className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-400"
                >
                  Key
                </th>
                <th
                  scope="col"
                  className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-400"
                >
                  Value
                </th>
                <th
                  scope="col"
                  className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-400"
                >
                  Source
                </th>
                <th scope="col" className="px-4 py-3">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-700/40">
              {unified.map((v) => (
                <tr
                  key={`${v.source}-${v.container ?? ""}-${v.key}`}
                  className="bg-zinc-800/30 hover:bg-zinc-800/60"
                >
                  <td className="px-4 py-3 font-mono text-xs font-medium text-zinc-200">
                    {v.key}
                  </td>
                  <td className="max-w-xs px-4 py-3 font-mono text-xs text-zinc-400">
                    {editingKey === v.key ? (
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          void saveEdit();
                        }}
                        className="flex items-center gap-2"
                      >
                        <input
                          ref={editRef}
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Escape") cancelEdit();
                          }}
                          onBlur={() => void saveEdit()}
                          className="w-full rounded border border-orange-500 bg-zinc-700 px-2 py-1 font-mono text-xs text-zinc-100 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none"
                        />
                      </form>
                    ) : (
                      <button
                        onClick={() => startEdit(v.key, v.value)}
                        className="group flex w-full items-center gap-1.5 truncate text-left"
                        title="Click to edit"
                      >
                        <span className="truncate">{v.value}</span>
                        <Pencil
                          size={11}
                          className="shrink-0 text-zinc-600 opacity-0 transition-opacity group-hover:opacity-100"
                        />
                      </button>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {v.source === "override" ? (
                      <span className="inline-flex items-center rounded-full bg-orange-500/15 px-2 py-0.5 text-[10px] font-medium text-orange-400">
                        override
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-zinc-700/50 px-2 py-0.5 text-[10px] font-medium text-zinc-400">
                        compose
                        {v.container && (
                          <span className="text-zinc-500">
                            · {v.container}
                          </span>
                        )}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {v.source === "override" && (
                      <button
                        onClick={() => handleDelete(v.key)}
                        disabled={deletingKey === v.key}
                        className="rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-zinc-700 hover:text-red-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-40"
                        aria-label={`Delete ${v.key}`}
                      >
                        {deletingKey === v.key ? (
                          <Loader2 size={13} className="animate-spin" />
                        ) : (
                          <Trash size={13} />
                        )}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Deployments Tab ──────────────────────────────────────────────────────────

function DeploymentsTab({ appName }: { appName: string }) {
  const { data: deployments = [], isLoading } = useAppDeployments(appName);
  const rollbackMut = useRollbackApp();
  const toast = useToast();
  const [expandedId, setExpandedId] = useState<number | null>(null);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 size={20} className="animate-spin text-zinc-500" aria-label="Loading deployments" />
      </div>
    );
  }

  if (deployments.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-zinc-500">
        No deployments yet. Trigger a deployment to see history here.
      </p>
    );
  }

  function getRef(dep: { commit_hash?: string; image_used?: string }): string {
    if (dep.commit_hash) return dep.commit_hash.slice(0, 8);
    if (dep.image_used) return dep.image_used;
    return "---";
  }

  function handleRollback(depId: number) {
    if (!confirm("Roll back to this deployment?")) return;
    rollbackMut.mutate(
      { name: appName, deploymentId: depId },
      {
        onSuccess: () => toast.success("Rollback started"),
        onError: () => toast.error("Rollback failed"),
      },
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-700">
      <table className="w-full text-sm" role="table">
        <thead>
          <tr className="border-b border-zinc-700 bg-zinc-800/60">
            {["", "ID", "Status", "Ref", "Started", "Finished", ""].map((h, i) => (
              <th
                key={`${h}-${i}`}
                scope="col"
                className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-400"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-700/40">
          {deployments.map((dep, idx) => (
            <>
              <tr
                key={dep.id}
                className="bg-zinc-800/30 transition-colors hover:bg-zinc-800/60"
              >
                <td className="w-8 px-4 py-3">
                  {dep.log ? (
                    <button
                      onClick={() => setExpandedId(expandedId === dep.id ? null : dep.id)}
                      className="text-zinc-500 hover:text-zinc-300"
                      aria-label={expandedId === dep.id ? "Collapse log" : "View log"}
                    >
                      {expandedId === dep.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                  ) : null}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-zinc-400">
                  #{dep.id}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={dep.status} />
                </td>
                <td className="px-4 py-3 font-mono text-xs text-zinc-400">
                  {getRef(dep)}
                </td>
                <td className="px-4 py-3 text-zinc-400">
                  {formatDate(dep.started_at)}
                </td>
                <td className="px-4 py-3 text-zinc-400">
                  {dep.finished_at ? formatDate(dep.finished_at) : "---"}
                </td>
                <td className="px-4 py-3">
                  {dep.status === "success" && idx > 0 ? (
                    <button
                      onClick={() => handleRollback(dep.id)}
                      disabled={rollbackMut.isPending}
                      className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-amber-400 ring-1 ring-amber-500/30 hover:bg-amber-500/10 disabled:opacity-50"
                      aria-label="Rollback"
                    >
                      <RotateCcw size={12} /> Rollback
                    </button>
                  ) : null}
                </td>
              </tr>
              {expandedId === dep.id && dep.log ? (
                <tr key={`${dep.id}-log`}>
                  <td colSpan={7} className="bg-zinc-900/60 px-4 py-3">
                    <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-xs text-zinc-400">
                      {dep.log}
                    </pre>
                  </td>
                </tr>
              ) : null}
            </>
          ))}
        </tbody>
      </table>
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />
    </div>
  );
}

// ─── Settings Tab ────────────────────────────────────────────────────────────

function SettingsTab({ app }: { app: App }) {
  const updateApp = useUpdateApp();
  const destroyApp = useDestroyApp();
  const navigate = useNavigate();
  const toast = useToast();

  const [form, setForm] = useState<UpdateAppInput>({
    domain: app.domain ?? "",
    port: app.port ?? 3000,
    git_repo: app.git_repo ?? "",
    branch: app.branch ?? "main",
    image: app.image ?? "",
    cpu_limit: app.cpu_limit ?? "",
    memory_limit: app.memory_limit ?? "",
    health_check_url: app.health_check_url ?? "",
    health_check_interval: app.health_check_interval,
    replicas: app.replicas,
    deploy_strategy: app.deploy_strategy ?? "",
  });

  const [showDanger, setShowDanger] = useState(false);
  const [destroyConfirm, setDestroyConfirm] = useState("");

  const isTemplate = app.app_type?.startsWith("template:");

  // Dirty detection
  const isDirty =
    form.domain !== (app.domain ?? "") ||
    form.port !== (app.port ?? 3000) ||
    form.git_repo !== (app.git_repo ?? "") ||
    form.branch !== (app.branch ?? "main") ||
    form.image !== (app.image ?? "") ||
    form.cpu_limit !== (app.cpu_limit ?? "") ||
    form.memory_limit !== (app.memory_limit ?? "") ||
    form.health_check_url !== (app.health_check_url ?? "") ||
    form.health_check_interval !== app.health_check_interval ||
    form.replicas !== app.replicas ||
    form.deploy_strategy !== (app.deploy_strategy ?? "");

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    const { name, value } = e.target;
    const numericFields = ["port", "health_check_interval", "replicas"];
    setForm((prev) => ({
      ...prev,
      [name]: numericFields.includes(name)
        ? value === ""
          ? undefined
          : Number(value)
        : value,
    }));
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateApp.mutateAsync({ name: app.name, input: form });
      toast.success("App configuration updated.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update app.");
    }
  }

  async function handleDestroy() {
    if (destroyConfirm !== app.name) return;
    try {
      await destroyApp.mutateAsync(app.name);
      toast.success(`App "${app.name}" destroyed.`);
      void navigate("/apps");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Destroy failed.");
    }
  }

  const inputClass =
    "w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none";

  return (
    <div className="space-y-6">
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      <form onSubmit={handleSave} className="space-y-6" noValidate>
        {/* Save button */}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!isDirty || updateApp.isPending}
            className={[
              "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50",
              isDirty
                ? "bg-orange-600 hover:bg-orange-500"
                : "cursor-not-allowed bg-zinc-600",
            ].join(" ")}
          >
            {updateApp.isPending && (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            )}
            Save Changes
          </button>
        </div>

        {/* General */}
        <fieldset className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <legend className="px-2 text-sm font-semibold text-zinc-200">General</legend>
          <div className="mt-2 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="settings-domain" className="mb-1.5 block text-xs font-medium text-zinc-300">
                Domain
              </label>
              <input
                id="settings-domain"
                name="domain"
                type="text"
                value={form.domain ?? ""}
                onChange={handleChange}
                placeholder="app.example.com"
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="settings-port" className="mb-1.5 block text-xs font-medium text-zinc-300">
                Port
              </label>
              <input
                id="settings-port"
                name="port"
                type="number"
                min={1}
                max={65535}
                value={form.port ?? ""}
                onChange={handleChange}
                className={inputClass}
              />
            </div>
          </div>
        </fieldset>

        {/* Source (hidden for templates) */}
        {!isTemplate && (
          <fieldset className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
            <legend className="px-2 text-sm font-semibold text-zinc-200">Source</legend>
            <div className="mt-2 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="settings-git-repo" className="mb-1.5 block text-xs font-medium text-zinc-300">
                  Git Repository
                </label>
                <input
                  id="settings-git-repo"
                  name="git_repo"
                  type="text"
                  value={form.git_repo ?? ""}
                  onChange={handleChange}
                  placeholder="https://github.com/user/repo.git"
                  className={inputClass}
                />
              </div>
              <div>
                <label htmlFor="settings-branch" className="mb-1.5 block text-xs font-medium text-zinc-300">
                  Branch
                </label>
                <input
                  id="settings-branch"
                  name="branch"
                  type="text"
                  value={form.branch ?? ""}
                  onChange={handleChange}
                  placeholder="main"
                  className={inputClass}
                />
              </div>
              <div className="sm:col-span-2">
                <label htmlFor="settings-image" className="mb-1.5 block text-xs font-medium text-zinc-300">
                  Docker Image
                </label>
                <input
                  id="settings-image"
                  name="image"
                  type="text"
                  value={form.image ?? ""}
                  onChange={handleChange}
                  placeholder="nginx:latest"
                  className={inputClass}
                />
              </div>
            </div>
          </fieldset>
        )}

        {/* Resources */}
        <fieldset className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <legend className="px-2 text-sm font-semibold text-zinc-200">Resources</legend>
          <div className="mt-2 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label htmlFor="settings-cpu-limit" className="mb-1.5 block text-xs font-medium text-zinc-300">
                CPU Limit
              </label>
              <input
                id="settings-cpu-limit"
                name="cpu_limit"
                type="text"
                value={form.cpu_limit ?? ""}
                onChange={handleChange}
                placeholder="0.5"
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="settings-memory-limit" className="mb-1.5 block text-xs font-medium text-zinc-300">
                Memory Limit
              </label>
              <input
                id="settings-memory-limit"
                name="memory_limit"
                type="text"
                value={form.memory_limit ?? ""}
                onChange={handleChange}
                placeholder="512M"
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="settings-replicas" className="mb-1.5 block text-xs font-medium text-zinc-300">
                Replicas
              </label>
              <input
                id="settings-replicas"
                name="replicas"
                type="number"
                min={1}
                value={form.replicas ?? ""}
                onChange={handleChange}
                placeholder="1"
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="settings-deploy-strategy" className="mb-1.5 block text-xs font-medium text-zinc-300">
                Deploy Strategy
              </label>
              <select
                id="settings-deploy-strategy"
                name="deploy_strategy"
                value={form.deploy_strategy ?? ""}
                onChange={handleChange}
                className={inputClass}
              >
                <option value="">Default</option>
                <option value="recreate">Recreate</option>
                <option value="rolling">Rolling</option>
              </select>
            </div>
          </div>
        </fieldset>

        {/* Health Check */}
        <fieldset className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
          <legend className="px-2 text-sm font-semibold text-zinc-200">Health Check</legend>
          <div className="mt-2 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="settings-health-check-url" className="mb-1.5 block text-xs font-medium text-zinc-300">
                URL
              </label>
              <input
                id="settings-health-check-url"
                name="health_check_url"
                type="text"
                value={form.health_check_url ?? ""}
                onChange={handleChange}
                placeholder="https://app.example.com/health"
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="settings-health-check-interval" className="mb-1.5 block text-xs font-medium text-zinc-300">
                Interval (seconds)
              </label>
              <input
                id="settings-health-check-interval"
                name="health_check_interval"
                type="number"
                min={5}
                value={form.health_check_interval ?? ""}
                onChange={handleChange}
                placeholder="30"
                className={inputClass}
              />
            </div>
          </div>
        </fieldset>
      </form>

      {/* Danger Zone */}
      <div className="rounded-lg border border-red-500/30 bg-zinc-800/50">
        <button
          onClick={() => setShowDanger(!showDanger)}
          className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold text-red-400 transition-colors hover:bg-red-500/5"
        >
          Danger Zone
          {showDanger ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </button>
        {showDanger && (
          <div className="border-t border-red-500/20 px-4 py-4">
            <p className="mb-3 text-sm text-zinc-400">
              Permanently destroy this app, its containers, volumes, and proxy routes. This action cannot be undone.
            </p>
            <div className="mb-3">
              <label htmlFor="settings-destroy-confirm" className="mb-1.5 block text-xs font-medium text-zinc-400">
                Type <span className="font-mono text-red-400">{app.name}</span> to confirm
              </label>
              <input
                id="settings-destroy-confirm"
                type="text"
                value={destroyConfirm}
                onChange={(e) => setDestroyConfirm(e.target.value)}
                placeholder={app.name}
                className="w-full rounded-lg border border-red-500/30 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-red-500 focus:ring-1 focus:ring-red-500 focus-visible:outline-none sm:w-80"
              />
            </div>
            <button
              onClick={handleDestroy}
              disabled={destroyConfirm !== app.name || destroyApp.isPending}
              className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-500 disabled:opacity-50"
            >
              {destroyApp.isPending ? (
                <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              ) : (
                <Trash2 size={14} aria-hidden="true" />
              )}
              Destroy App
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function AppDetail() {
  const { name = "" } = useParams<{ name: string }>();
  const decodedName = decodeURIComponent(name);
  const navigate = useNavigate();

  const { data: apps = [] } = useApps();
  const app = apps.find((a) => a.name === decodedName);

  const deployApp = useDeployApp();
  const restartApp = useRestartApp();
  const stopApp = useStopApp();
  const destroyApp = useDestroyApp();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<ActiveTab>("overview");
  const [actionPending, setActionPending] = useState<string | null>(null);
  const [activeDeploymentId, setActiveDeploymentId] = useState<string | null>(null);
  const [showMenu, setShowMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const stream = useDeploymentStream(
    activeDeploymentId ? decodedName : null,
    activeDeploymentId,
  );

  // Outside-click handler for kebab menu
  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
      setShowMenu(false);
    }
  }, []);

  useEffect(() => {
    if (showMenu) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [showMenu, handleClickOutside]);

  async function handleDeploy() {
    setActionPending("deploy");
    try {
      const result = await deployApp.mutateAsync(decodedName);
      toast.success(result.message || "Deployment triggered.");
      setActiveDeploymentId(result.deployment_id);
      setActiveTab("logs");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Deployment failed.");
    } finally {
      setActionPending(null);
    }
  }

  async function handleRestart() {
    setActionPending("restart");
    try {
      await restartApp.mutateAsync(decodedName);
      toast.success("App restarted.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Restart failed.");
    } finally {
      setActionPending(null);
    }
  }

  async function handleStop() {
    setActionPending("stop");
    try {
      await stopApp.mutateAsync(decodedName);
      toast.success("App stopped.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Stop failed.");
    } finally {
      setActionPending(null);
    }
  }

  async function handleDestroy() {
    if (!window.confirm(`Destroy app "${decodedName}"? This cannot be undone.`)) return;
    setShowMenu(false);
    setActionPending("destroy");
    try {
      await destroyApp.mutateAsync(decodedName);
      toast.success(`App "${decodedName}" destroyed.`);
      void navigate("/apps");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Destroy failed.");
      setActionPending(null);
    }
  }

  return (
    <div>
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      {/* Back link */}
      <Link
        to="/apps"
        className="mb-5 inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
      >
        <ArrowLeft size={14} aria-hidden="true" />
        Back to Apps
      </Link>

      {/* Header */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-zinc-700">
            <Box size={22} className="text-orange-400" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">{decodedName}</h1>
            {app && (
              <div className="mt-1 space-y-0.5 text-xs text-zinc-400">
                {/* Line 1: Status + Server */}
                <div className="flex items-center gap-3">
                  <StatusBadge status={app.status} />
                  <span className="flex items-center gap-1">
                    <Server size={11} aria-hidden="true" />
                    {app.server_name}
                  </span>
                </div>
                {/* Line 2: Domain(s) + Port */}
                <div className="flex flex-wrap items-center gap-3">
                  {app.domains && Object.keys(app.domains).length > 1 ? (
                    Object.entries(app.domains).map(([svc, d]) => (
                      <a
                        key={svc}
                        href={`https://${d}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-zinc-300 hover:text-orange-400"
                      >
                        <Globe size={11} aria-hidden="true" />
                        <span className="text-zinc-500">{svc}:</span>
                        {d}
                        <ExternalLink size={9} aria-hidden="true" />
                      </a>
                    ))
                  ) : app.domain ? (
                    <a
                      href={`https://${app.domain}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-zinc-300 hover:text-orange-400"
                    >
                      <Globe size={11} aria-hidden="true" />
                      {app.domain}
                      <ExternalLink size={9} aria-hidden="true" />
                    </a>
                  ) : null}
                  {app.port && (
                    <span>:{app.port}</span>
                  )}
                </div>
                {/* Line 3: App type + Branch */}
                <div className="flex items-center gap-3">
                  {app.app_type && (
                    <span className="rounded bg-zinc-700 px-1.5 py-0.5 font-mono text-[11px] text-zinc-300">
                      {app.app_type}
                    </span>
                  )}
                  {app.branch && (
                    <span className="flex items-center gap-1">
                      <GitBranch size={11} aria-hidden="true" />
                      {app.branch}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Action buttons — grouped */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Deploy CTA */}
          <button
            onClick={handleDeploy}
            disabled={!!actionPending}
            className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
          >
            {actionPending === "deploy" ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <Play size={14} aria-hidden="true" />
            )}
            Deploy
          </button>
          {/* Restart */}
          <button
            onClick={handleRestart}
            disabled={!!actionPending}
            className="flex items-center gap-2 rounded-lg border border-zinc-600 bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
          >
            {actionPending === "restart" ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw size={14} aria-hidden="true" />
            )}
            Restart
          </button>
          {/* Stop */}
          <button
            onClick={handleStop}
            disabled={!!actionPending}
            className="flex items-center gap-2 rounded-lg border border-zinc-600 bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
          >
            {actionPending === "stop" ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <Square size={14} aria-hidden="true" />
            )}
            Stop
          </button>
          {/* Kebab menu */}
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setShowMenu(!showMenu)}
              disabled={!!actionPending}
              className="flex items-center justify-center rounded-lg border border-zinc-600 bg-zinc-700 p-2 text-zinc-300 transition-colors hover:bg-zinc-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500 disabled:opacity-50"
              aria-label="More actions"
            >
              <MoreVertical size={16} aria-hidden="true" />
            </button>
            {showMenu && (
              <div className="absolute right-0 z-50 mt-1 w-44 rounded-lg border border-zinc-600 bg-zinc-800 py-1 shadow-xl">
                <button
                  onClick={handleDestroy}
                  disabled={!!actionPending}
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-400 transition-colors hover:bg-red-500/10 disabled:opacity-50"
                >
                  {actionPending === "destroy" ? (
                    <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                  ) : (
                    <Trash2 size={14} aria-hidden="true" />
                  )}
                  Destroy App
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="rounded-xl border border-zinc-700 bg-zinc-800">
        {/* Tab list */}
        <div
          role="tablist"
          aria-label="App details"
          className="flex border-b border-zinc-700"
        >
          <TabButton
            id="overview"
            label="Overview"
            icon={<Activity size={14} aria-hidden="true" />}
            isActive={activeTab === "overview"}
            onClick={setActiveTab}
          />
          <TabButton
            id="logs"
            label="Logs"
            icon={<Terminal size={14} aria-hidden="true" />}
            isActive={activeTab === "logs"}
            onClick={setActiveTab}
          />
          <TabButton
            id="env"
            label="Environment"
            icon={<Settings size={14} aria-hidden="true" />}
            isActive={activeTab === "env"}
            onClick={setActiveTab}
          />
          <TabButton
            id="deployments"
            label="Deployments"
            icon={<Clock size={14} aria-hidden="true" />}
            isActive={activeTab === "deployments"}
            onClick={setActiveTab}
          />
          <TabButton
            id="settings"
            label="Settings"
            icon={<Settings size={14} aria-hidden="true" />}
            isActive={activeTab === "settings"}
            onClick={setActiveTab}
          />
        </div>

        {/* Tab panels */}
        <div className="p-5">
          <div
            id="tabpanel-overview"
            role="tabpanel"
            aria-label="Overview"
            hidden={activeTab !== "overview"}
          >
            {activeTab === "overview" && app && <OverviewTab app={app} />}
          </div>
          <div
            id="tabpanel-logs"
            role="tabpanel"
            aria-label="Logs"
            hidden={activeTab !== "logs"}
          >
            {activeTab === "logs" &&
              (activeDeploymentId ? (
                <DeploymentLogStream
                  lines={stream.lines}
                  isStreaming={stream.isStreaming}
                  status={stream.status}
                  error={stream.error}
                  onClose={() => setActiveDeploymentId(null)}
                />
              ) : (
                <LogsTab appName={decodedName} />
              ))}
          </div>
          <div
            id="tabpanel-env"
            role="tabpanel"
            aria-label="Environment variables"
            hidden={activeTab !== "env"}
          >
            {activeTab === "env" && <EnvTab appName={decodedName} />}
          </div>
          <div
            id="tabpanel-deployments"
            role="tabpanel"
            aria-label="Deployment history"
            hidden={activeTab !== "deployments"}
          >
            {activeTab === "deployments" && (
              <DeploymentsTab appName={decodedName} />
            )}
          </div>
          <div
            id="tabpanel-settings"
            role="tabpanel"
            aria-label="Settings"
            hidden={activeTab !== "settings"}
          >
            {activeTab === "settings" && app && <SettingsTab app={app} />}
          </div>
        </div>
      </div>
    </div>
  );
}

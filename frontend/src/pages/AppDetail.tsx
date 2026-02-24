import { useState, useRef, useEffect } from "react";
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
} from "@/hooks/useApi";
import { useToast } from "@/hooks/useToast";
import { useDeploymentStream } from "@/hooks/useDeploymentStream";
import { useContainerLogStream } from "@/hooks/useContainerLogStream";
import { ToastContainer } from "@/components/Toast";
import StatusBadge from "@/components/StatusBadge";
import Modal from "@/components/Modal";
import DeploymentLogStream from "@/components/DeploymentLogStream";
import type { UpdateAppInput } from "@/api/client";

type ActiveTab = "logs" | "env" | "deployments" | "health";

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
          ? "border-indigo-500 text-indigo-400"
          : "border-transparent text-slate-400 hover:border-slate-500 hover:text-slate-200",
      ].join(" ")}
    >
      {icon}
      {label}
    </button>
  );
}

// ─── Logs Tab ─────────────────────────────────────────────────────────────────

function LogsTab({ appName }: { appName: string }) {
  const [lines, setLines] = useState(100);
  const [live, setLive] = useState(false);
  const { data, isLoading, refetch, isFetching } = useAppLogs(appName, lines, {
    enabled: !live && Boolean(appName),
    refetchInterval: live ? false : 15_000,
  });
  const stream = useContainerLogStream(appName, lines, live);
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
              <label
                htmlFor="log-lines"
                className="text-xs text-slate-400"
              >
                Lines:
              </label>
              <select
                id="log-lines"
                value={lines}
                onChange={(e) => setLines(Number(e.target.value))}
                className="rounded-md border border-slate-600 bg-slate-700 px-2 py-1 text-xs text-slate-200 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
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
              className="flex items-center gap-1.5 rounded-md border border-slate-600 bg-slate-700 px-3 py-1.5 text-xs text-slate-300 transition-colors hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
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
              "flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500",
              live
                ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20"
                : "border-slate-600 bg-slate-700 text-slate-300 hover:bg-slate-600",
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
        className="h-[480px] overflow-y-auto rounded-lg border border-slate-700 bg-slate-950 p-4"
        aria-label="Application logs"
      >
        {live ? (
          stream.lines.length === 0 && stream.isStreaming ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 size={20} className="animate-spin text-slate-500" aria-label="Connecting to log stream" />
            </div>
          ) : stream.lines.length === 0 ? (
            <p className="text-center text-sm text-slate-500">No logs available.</p>
          ) : (
            <pre className="log-viewer text-slate-300">
              {stream.lines.join("\n")}
            </pre>
          )
        ) : isLoading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 size={20} className="animate-spin text-slate-500" aria-label="Loading logs" />
          </div>
        ) : !data?.logs ? (
          <p className="text-center text-sm text-slate-500">No logs available.</p>
        ) : (
          <pre className="log-viewer text-slate-300">{data.logs}</pre>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

// ─── Env Tab ──────────────────────────────────────────────────────────────────

function EnvTab({ appName }: { appName: string }) {
  const { data: vars = [], isLoading } = useAppEnv(appName, true);
  const setEnv = useSetEnv();
  const deleteEnv = useDeleteEnv();
  const toast = useToast();

  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [deletingKey, setDeletingKey] = useState<string | null>(null);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!newKey.trim()) return;
    try {
      await setEnv.mutateAsync({
        name: appName,
        vars: [{ key: newKey.trim(), value: newValue }],
      });
      toast.success(`Environment variable "${newKey}" saved.`);
      setNewKey("");
      setNewValue("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save env var.");
    }
  }

  async function handleDelete(key: string) {
    setDeletingKey(key);
    try {
      await deleteEnv.mutateAsync({ name: appName, key });
      toast.success(`"${key}" deleted.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete env var.");
    } finally {
      setDeletingKey(null);
    }
  }

  return (
    <div className="space-y-4">
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />
      {/* Add form */}
      <form
        onSubmit={handleAdd}
        className="flex items-end gap-3 rounded-lg border border-slate-700 bg-slate-800/50 p-4"
      >
        <div className="flex-1">
          <label
            htmlFor="env-key"
            className="mb-1.5 block text-xs font-medium text-slate-400"
          >
            Key
          </label>
          <input
            id="env-key"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            placeholder="DATABASE_URL"
            className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 font-mono text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
          />
        </div>
        <div className="flex-1">
          <label
            htmlFor="env-value"
            className="mb-1.5 block text-xs font-medium text-slate-400"
          >
            Value
          </label>
          <input
            id="env-value"
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            placeholder="postgres://..."
            className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 font-mono text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={setEnv.isPending || !newKey.trim()}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
        >
          {setEnv.isPending ? (
            <Loader2 size={14} className="animate-spin" aria-hidden="true" />
          ) : (
            <Plus size={14} aria-hidden="true" />
          )}
          Add
        </button>
      </form>

      {/* Env var table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 size={20} className="animate-spin text-slate-500" aria-label="Loading env vars" />
        </div>
      ) : vars.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-500">
          No environment variables set.
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-700">
          <table className="w-full text-sm" role="table">
            <thead>
              <tr className="border-b border-slate-700 bg-slate-800/60">
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Key
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Value
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/40">
              {vars.map((v) => (
                <tr key={v.key} className="bg-slate-800/30 hover:bg-slate-800/60">
                  <td className="px-4 py-3 font-mono text-xs font-medium text-slate-200">
                    {v.key}
                  </td>
                  <td className="max-w-xs truncate px-4 py-3 font-mono text-xs text-slate-400">
                    {v.value ?? <span className="text-slate-500 italic">hidden</span>}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleDelete(v.key)}
                      disabled={deletingKey === v.key}
                      className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-700 hover:text-red-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-40"
                      aria-label={`Delete ${v.key}`}
                    >
                      {deletingKey === v.key ? (
                        <Loader2 size={13} className="animate-spin" aria-hidden="true" />
                      ) : (
                        <Trash size={13} aria-hidden="true" />
                      )}
                    </button>
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
        <Loader2 size={20} className="animate-spin text-slate-500" aria-label="Loading deployments" />
      </div>
    );
  }

  if (deployments.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-slate-500">
        No deployments yet. Trigger a deployment to see history here.
      </p>
    );
  }

  function getRef(dep: { commit_hash?: string; image_used?: string }): string {
    if (dep.commit_hash) return dep.commit_hash.slice(0, 8);
    if (dep.image_used) return dep.image_used;
    return "—";
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
    <div className="overflow-hidden rounded-lg border border-slate-700">
      <table className="w-full text-sm" role="table">
        <thead>
          <tr className="border-b border-slate-700 bg-slate-800/60">
            {["", "ID", "Status", "Ref", "Started", "Finished", ""].map((h, i) => (
              <th
                key={`${h}-${i}`}
                scope="col"
                className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-700/40">
          {deployments.map((dep, idx) => (
            <>
              <tr
                key={dep.id}
                className="bg-slate-800/30 transition-colors hover:bg-slate-800/60"
              >
                <td className="w-8 px-4 py-3">
                  {dep.log ? (
                    <button
                      onClick={() => setExpandedId(expandedId === dep.id ? null : dep.id)}
                      className="text-slate-500 hover:text-slate-300"
                      aria-label={expandedId === dep.id ? "Collapse log" : "View log"}
                    >
                      {expandedId === dep.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                  ) : null}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-slate-400">
                  #{dep.id}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={dep.status} />
                </td>
                <td className="px-4 py-3 font-mono text-xs text-slate-400">
                  {getRef(dep)}
                </td>
                <td className="px-4 py-3 text-slate-400">
                  {formatDate(dep.started_at)}
                </td>
                <td className="px-4 py-3 text-slate-400">
                  {dep.finished_at ? formatDate(dep.finished_at) : "—"}
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
                  <td colSpan={7} className="bg-slate-900/60 px-4 py-3">
                    <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-xs text-slate-400">
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

// ─── Health Tab ──────────────────────────────────────────────────────────────

function HealthTab({ appName }: { appName: string }) {
  const { data, isLoading, refetch, isFetching } = useAppHealth(appName);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400">
          Health checks run on-demand over SSH.
        </p>
        <button
          onClick={() => void refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 rounded-md border border-slate-600 bg-slate-700 px-3 py-1.5 text-xs text-slate-300 transition-colors hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
        >
          <RefreshCw
            size={12}
            className={isFetching ? "animate-spin" : ""}
            aria-hidden="true"
          />
          {isLoading || isFetching ? "Checking..." : "Check Health"}
        </button>
      </div>

      {!data && !isLoading && !isFetching ? (
        <p className="py-10 text-center text-sm text-slate-500">
          Click &quot;Check Health&quot; to query real container state from the server.
        </p>
      ) : isLoading || isFetching ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 size={20} className="animate-spin text-slate-500" aria-label="Checking health" />
        </div>
      ) : data ? (
        <>
          {/* Status summary */}
          <div className="flex items-center gap-4 rounded-lg border border-slate-700 bg-slate-800/50 p-4">
            <div>
              <p className="mb-1 text-xs text-slate-400">Actual Status</p>
              <StatusBadge status={data.actual_status} />
            </div>
            {data.status_mismatch && (
              <p className="ml-4 text-xs text-amber-400">
                DB was &quot;{data.db_status}&quot; — updated to match actual state.
              </p>
            )}
          </div>

          {/* Container table */}
          {data.containers.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-500">
              No containers found. The app may not be deployed.
            </p>
          ) : (
            <div className="overflow-hidden rounded-lg border border-slate-700">
              <table className="w-full text-sm" role="table">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-800/60">
                    {["Container", "State", "Status", "Healthcheck", "Image"].map((h) => (
                      <th
                        key={h}
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/40">
                  {data.containers.map((c) => (
                    <tr key={c.name} className="bg-slate-800/30 hover:bg-slate-800/60">
                      <td className="px-4 py-3 font-mono text-xs text-slate-200">{c.name}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={c.state} />
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-400">{c.status}</td>
                      <td className="px-4 py-3">
                        {c.health ? (
                          <StatusBadge status={c.health} />
                        ) : (
                          <span className="text-xs text-slate-500">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-500">
                        {c.image || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}
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
  const updateApp = useUpdateApp();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<ActiveTab>("logs");
  const [actionPending, setActionPending] = useState<string | null>(null);
  const [activeDeploymentId, setActiveDeploymentId] = useState<string | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editForm, setEditForm] = useState<UpdateAppInput>({
    domain: "",
    port: 3000,
    git_repo: "",
    branch: "",
    image: "",
  });

  const stream = useDeploymentStream(
    activeDeploymentId ? decodedName : null,
    activeDeploymentId,
  );

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

  function openEditModal() {
    if (!app) return;
    setEditForm({
      domain: app.domain ?? "",
      port: app.port ?? 3000,
      git_repo: app.git_repo ?? "",
      branch: app.branch ?? "main",
      image: app.image ?? "",
    });
    setShowEditModal(true);
  }

  function handleEditChange(e: React.ChangeEvent<HTMLInputElement>) {
    const { name, value } = e.target;
    setEditForm((prev) => ({
      ...prev,
      [name]: name === "port" ? (value === "" ? undefined : Number(value)) : value,
    }));
  }

  async function handleEditSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateApp.mutateAsync({ name: decodedName, input: editForm });
      toast.success("App configuration updated.");
      setShowEditModal(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update app.");
    }
  }

  return (
    <div>
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      {/* Back link */}
      <Link
        to="/apps"
        className="mb-5 inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
      >
        <ArrowLeft size={14} aria-hidden="true" />
        Back to Apps
      </Link>

      {/* Header */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-700">
            <Box size={22} className="text-indigo-400" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-100">{decodedName}</h1>
            {app && (
              <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-400">
                <span className="flex items-center gap-1">
                  <Server size={11} aria-hidden="true" />
                  {app.server_name}
                </span>
                {app.domain && (
                  <span className="flex items-center gap-1">
                    <Globe size={11} aria-hidden="true" />
                    {app.domain}
                  </span>
                )}
                {app.port && (
                  <span>:{app.port}</span>
                )}
                {app.app_type && (
                  <span className="flex items-center gap-1">
                    <Settings size={11} aria-hidden="true" />
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
            )}
          </div>
          {app && <StatusBadge status={app.status} />}
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={openEditModal}
            disabled={!!actionPending}
            className="flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
          >
            <Pencil size={14} aria-hidden="true" />
            Edit
          </button>
          <button
            onClick={handleDeploy}
            disabled={!!actionPending}
            className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
          >
            {actionPending === "deploy" ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <Play size={14} aria-hidden="true" />
            )}
            Deploy
          </button>
          <button
            onClick={handleRestart}
            disabled={!!actionPending}
            className="flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
          >
            {actionPending === "restart" ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw size={14} aria-hidden="true" />
            )}
            Restart
          </button>
          <button
            onClick={handleStop}
            disabled={!!actionPending}
            className="flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
          >
            {actionPending === "stop" ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <Square size={14} aria-hidden="true" />
            )}
            Stop
          </button>
          <button
            onClick={handleDestroy}
            disabled={!!actionPending}
            className="flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-400 transition-colors hover:bg-red-500/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-500 disabled:opacity-50"
          >
            {actionPending === "destroy" ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <Trash2 size={14} aria-hidden="true" />
            )}
            Destroy
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="rounded-xl border border-slate-700 bg-slate-800">
        {/* Tab list */}
        <div
          role="tablist"
          aria-label="App details"
          className="flex border-b border-slate-700"
        >
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
            id="health"
            label="Health"
            icon={<Activity size={14} aria-hidden="true" />}
            isActive={activeTab === "health"}
            onClick={setActiveTab}
          />
        </div>

        {/* Tab panels */}
        <div className="p-5">
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
            id="tabpanel-health"
            role="tabpanel"
            aria-label="Health"
            hidden={activeTab !== "health"}
          >
            {activeTab === "health" && <HealthTab appName={decodedName} />}
          </div>
        </div>
      </div>

      {/* Edit App Modal */}
      {showEditModal && (
        <Modal title="Edit App" onClose={() => setShowEditModal(false)}>
          <form onSubmit={handleEditSubmit} className="space-y-4" noValidate>
            <div>
              <label htmlFor="edit-domain" className="mb-1.5 block text-xs font-medium text-slate-300">
                Domain
              </label>
              <input
                id="edit-domain"
                name="domain"
                type="text"
                value={editForm.domain ?? ""}
                onChange={handleEditChange}
                placeholder="app.example.com"
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
              />
            </div>

            <div>
              <label htmlFor="edit-port" className="mb-1.5 block text-xs font-medium text-slate-300">
                Port
              </label>
              <input
                id="edit-port"
                name="port"
                type="number"
                min={1}
                max={65535}
                value={editForm.port ?? ""}
                onChange={handleEditChange}
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
              />
            </div>

            <div>
              <label htmlFor="edit-git-repo" className="mb-1.5 block text-xs font-medium text-slate-300">
                Git Repository
              </label>
              <input
                id="edit-git-repo"
                name="git_repo"
                type="text"
                value={editForm.git_repo ?? ""}
                onChange={handleEditChange}
                placeholder="https://github.com/user/repo.git"
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
              />
            </div>

            <div>
              <label htmlFor="edit-branch" className="mb-1.5 block text-xs font-medium text-slate-300">
                Branch
              </label>
              <input
                id="edit-branch"
                name="branch"
                type="text"
                value={editForm.branch ?? ""}
                onChange={handleEditChange}
                placeholder="main"
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
              />
            </div>

            <div>
              <label htmlFor="edit-image" className="mb-1.5 block text-xs font-medium text-slate-300">
                Docker Image
              </label>
              <input
                id="edit-image"
                name="image"
                type="text"
                value={editForm.image ?? ""}
                onChange={handleEditChange}
                placeholder="nginx:latest"
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus-visible:outline-none"
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowEditModal(false)}
                className="rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={updateApp.isPending}
                className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
              >
                {updateApp.isPending && (
                  <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                )}
                Save Changes
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

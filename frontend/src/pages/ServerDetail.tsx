import { useParams, Link } from "react-router-dom";
import {
  Server,
  Activity,
  HardDrive,
  Cpu,
  Box,
  Play,
  Wifi,
  ArrowLeft,
  Loader2,
  RefreshCw,
} from "lucide-react";
import {
  useServers,
  useServerStatus,
  useApps,
  useProvisionServer,
  useTestServer,
} from "@/hooks/useApi";
import { useToast } from "@/hooks/useToast";
import { ToastContainer } from "@/components/Toast";
import StatusBadge from "@/components/StatusBadge";

interface InfoRowProps {
  label: string;
  value: React.ReactNode;
}

function InfoRow({ label, value }: InfoRowProps) {
  return (
    <div className="flex items-center justify-between py-2.5 text-sm">
      <span className="text-slate-400">{label}</span>
      <span className="font-medium text-slate-200">{value}</span>
    </div>
  );
}

interface UsageBarProps {
  label: string;
  used: string;
  total: string;
  percent: number;
  icon: React.ReactNode;
}

function UsageBar({ label, used, total, percent, icon }: UsageBarProps) {
  const clampedPercent = Math.min(100, Math.max(0, percent));
  const barColor =
    clampedPercent > 85
      ? "bg-red-500"
      : clampedPercent > 65
        ? "bg-amber-500"
        : "bg-emerald-500";

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-medium text-slate-400">
          {icon}
          {label}
        </div>
        <span className="text-xs font-semibold text-slate-300">
          {clampedPercent.toFixed(0)}%
        </span>
      </div>
      <div className="mb-1.5 h-2 overflow-hidden rounded-full bg-slate-700">
        <div
          className={["h-full rounded-full transition-all duration-500", barColor].join(" ")}
          style={{ width: `${clampedPercent}%` }}
          role="progressbar"
          aria-valuenow={clampedPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${label} usage`}
        />
      </div>
      <p className="text-xs text-slate-500">
        {used} used of {total}
      </p>
    </div>
  );
}

export default function ServerDetail() {
  const { name = "" } = useParams<{ name: string }>();
  const decodedName = decodeURIComponent(name);

  const { data: servers = [] } = useServers();
  const server = servers.find((s) => s.name === decodedName);

  const {
    data: statusData,
    isLoading: statusLoading,
    refetch: refetchStatus,
  } = useServerStatus(decodedName);

  const { data: apps = [] } = useApps(decodedName);

  const provisionServer = useProvisionServer();
  const testServer = useTestServer();
  const toast = useToast();

  async function handleProvision() {
    try {
      await provisionServer.mutateAsync(decodedName);
      toast.success("Provisioning started.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Provisioning failed.");
    }
  }

  async function handleTest() {
    try {
      const result = await testServer.mutateAsync(decodedName);
      if (result.reachable) {
        toast.success("Server is reachable.");
      } else {
        toast.error("Server is not reachable.");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Connection test failed.");
    }
  }

  return (
    <div>
      <ToastContainer toasts={toast.toasts} onDismiss={toast.dismiss} />

      {/* Back link */}
      <Link
        to="/servers"
        className="mb-5 inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
      >
        <ArrowLeft size={14} aria-hidden="true" />
        Back to Servers
      </Link>

      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-700">
            <Server size={22} className="text-indigo-400" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-100">
              {decodedName}
            </h1>
            {server && (
              <p className="mt-0.5 text-sm text-slate-400">
                {server.user}@{server.host}:{server.port}
                {server.provider ? ` · ${server.provider}` : ""}
              </p>
            )}
          </div>
          {server && (
            <StatusBadge status={server.status} className="ml-2" />
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleTest}
            disabled={testServer.isPending}
            className="flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
          >
            {testServer.isPending ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <Wifi size={14} aria-hidden="true" />
            )}
            Test Connection
          </button>
          <button
            onClick={handleProvision}
            disabled={provisionServer.isPending}
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50"
          >
            {provisionServer.isPending ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <Play size={14} aria-hidden="true" />
            )}
            Provision
          </button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left column: server info */}
        <div className="space-y-6">
          {/* Info card */}
          <div className="rounded-xl border border-slate-700 bg-slate-800">
            <div className="border-b border-slate-700 px-5 py-3">
              <h2 className="text-sm font-semibold text-slate-200">
                Server Info
              </h2>
            </div>
            <div className="divide-y divide-slate-700/50 px-5">
              {server ? (
                <>
                  <InfoRow label="Host" value={server.host} />
                  <InfoRow label="Port" value={server.port} />
                  <InfoRow label="User" value={server.user} />
                  <InfoRow label="Provider" value={server.provider ?? "—"} />
                  <InfoRow
                    label="SSH Key"
                    value={
                      server.ssh_key_path ? (
                        <span className="font-mono text-xs">
                          {server.ssh_key_path}
                        </span>
                      ) : (
                        "—"
                      )
                    }
                  />
                  <InfoRow label="Apps" value={server.app_count} />
                </>
              ) : (
                <p className="py-6 text-center text-sm text-slate-500">
                  Server not found
                </p>
              )}
            </div>
          </div>

          {/* Uptime card */}
          {statusData?.uptime && (
            <div className="rounded-xl border border-slate-700 bg-slate-800 px-5 py-4">
              <div className="flex items-center gap-2 text-sm">
                <Activity size={16} className="text-emerald-400" aria-hidden="true" />
                <span className="font-medium text-slate-200">Uptime</span>
                <span className="ml-auto font-mono text-xs text-slate-400">
                  {statusData.uptime}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Right column: status */}
        <div className="space-y-6 lg:col-span-2">
          {/* Resource usage */}
          <div className="rounded-xl border border-slate-700 bg-slate-800">
            <div className="flex items-center justify-between border-b border-slate-700 px-5 py-3">
              <h2 className="text-sm font-semibold text-slate-200">
                Resource Usage
              </h2>
              <button
                onClick={() => void refetchStatus()}
                className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
                aria-label="Refresh status"
              >
                <RefreshCw
                  size={13}
                  className={statusLoading ? "animate-spin" : ""}
                  aria-hidden="true"
                />
              </button>
            </div>

            <div className="p-5">
              {statusLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 size={24} className="animate-spin text-slate-500" aria-label="Loading status" />
                </div>
              ) : !statusData ? (
                <p className="py-6 text-center text-sm text-slate-500">
                  Status unavailable — the server may be unreachable.
                </p>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  {statusData.memory && (
                    <UsageBar
                      label="Memory"
                      used={statusData.memory.used}
                      total={statusData.memory.total}
                      percent={statusData.memory.percent}
                      icon={<Cpu size={13} aria-hidden="true" />}
                    />
                  )}
                  {statusData.disk && (
                    <UsageBar
                      label="Disk"
                      used={statusData.disk.used}
                      total={statusData.disk.total}
                      percent={statusData.disk.percent}
                      icon={<HardDrive size={13} aria-hidden="true" />}
                    />
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Containers */}
          {statusData?.containers && statusData.containers.length > 0 && (
            <div className="rounded-xl border border-slate-700 bg-slate-800">
              <div className="border-b border-slate-700 px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-200">
                  Running Containers ({statusData.containers.length})
                </h2>
              </div>
              <div className="divide-y divide-slate-700/40">
                {statusData.containers.map((c) => (
                  <div
                    key={c.id}
                    className="flex items-center justify-between px-5 py-3"
                  >
                    <div>
                      <p className="text-sm font-medium text-slate-200">
                        {c.name}
                      </p>
                      {c.image && (
                        <p className="mt-0.5 font-mono text-xs text-slate-500">
                          {c.image}
                        </p>
                      )}
                    </div>
                    <StatusBadge status={c.status} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Apps on server */}
          <div className="rounded-xl border border-slate-700 bg-slate-800">
            <div className="border-b border-slate-700 px-5 py-3">
              <h2 className="text-sm font-semibold text-slate-200">
                Apps on this Server
              </h2>
            </div>

            {apps.length === 0 ? (
              <div className="flex items-center gap-3 px-5 py-8 text-sm text-slate-500">
                <Box size={16} aria-hidden="true" />
                No apps deployed to this server yet.
              </div>
            ) : (
              <div className="divide-y divide-slate-700/40">
                {apps.map((app) => (
                  <div
                    key={app.id}
                    className="flex items-center justify-between px-5 py-3"
                  >
                    <div>
                      <Link
                        to={`/apps/${encodeURIComponent(app.name)}`}
                        className="text-sm font-medium text-indigo-400 hover:text-indigo-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500"
                      >
                        {app.name}
                      </Link>
                      {app.domain && (
                        <p className="mt-0.5 text-xs text-slate-500">
                          {app.domain}
                        </p>
                      )}
                    </div>
                    <StatusBadge status={app.status} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
